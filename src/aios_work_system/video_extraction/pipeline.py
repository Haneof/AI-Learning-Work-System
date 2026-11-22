"""End-to-end downloaded-video processing with local small-first open-weight models."""

from __future__ import annotations

import json
import os
import subprocess
import time
from collections import Counter
from pathlib import Path
from typing import Any

from aios_work_system.video_extraction.episode import (
    align_transcript_to_events,
    build_decision_episode,
)
from aios_work_system.video_extraction.frames import (
    CursorTracker,
    detect_frame_changes,
    extract_sampled_frames,
    infer_click_candidates,
    run_ocr,
)
from aios_work_system.video_extraction.model_router import (
    run_ui_grounding,
    synthesize_episode_decision,
)
from aios_work_system.video_extraction.transcript import load_transcript
from aios_work_system.video_extraction.verification import (
    LocalDecisionEpisodeVerifier,
    training_dataset_admission_status,
)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def probe_video(video_path: str | Path) -> dict[str, Any]:
    """Read authoritative file duration and stream metadata with ffprobe."""
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_streams",
        "-show_format",
        "-of",
        "json",
        str(video_path),
    ]
    try:
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError("ffprobe is not installed or is not on PATH") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"ffprobe failed: {exc.stderr[-2000:]}") from exc
    payload = json.loads(completed.stdout)
    video_stream = next(
        (stream for stream in payload.get("streams", []) if stream.get("codec_type") == "video"),
        {},
    )
    duration = float(payload.get("format", {}).get("duration") or video_stream.get("duration") or 0)
    if duration <= 0:
        raise RuntimeError("video duration could not be read from the local video file")
    return {
        "duration_ms": round(duration * 1000),
        "width": video_stream.get("width"),
        "height": video_stream.get("height"),
        "video_codec": video_stream.get("codec_name"),
        "audio_streams": sum(
            stream.get("codec_type") == "audio" for stream in payload.get("streams", [])
        ),
    }


def _first_frame_dimensions(frames: list[dict[str, Any]]) -> tuple[int, int]:
    if not frames:
        return 960, 540
    try:
        from PIL import Image

        with Image.open(frames[0]["path"]) as image:
            return image.size
    except Exception:
        return 960, 540


class VideoExtractionPipeline:
    """Subtitle/ASR -> frame changes -> OCR/cursor -> local UI grounding -> local episode JSON."""

    def __init__(
        self,
        sample_fps: float = 2.0,
        ocr_language: str = "eng",
        whisper_model: str = "tiny",
        language: str | None = None,
        *,
        ui_model_path: str | Path | None = None,
        ui_secondary_small_model_path: str | Path | None = None,
        ui_fallback_model_path: str | Path | None = None,
        grounding_benchmark_path: str | Path | None = None,
        episode_model_path: str | Path | None = None,
        episode_fallback_model_path: str | Path | None = None,
        allow_model_download: bool = False,
        maximum_vlm_frames: int = 24,
        minimum_grounding_accuracy: float = 0.75,
        llama_gpu_layers: int = -1,
        vlm_model: str | None = None,
        decision_verifier_model_path: str | Path | None = None,
        decision_verifier_endpoint: str | None = None,
        decision_verifier_model_name: str = "local-open-model",
        decision_verifier_server_binary: str = "llama-server",
        decision_verifier_port: int = 8089,
        decision_verifier_gpu_layers: int | None = None,
        decision_verifier: Any | None = None,
    ) -> None:
        if maximum_vlm_frames < 1:
            raise ValueError("maximum_vlm_frames must be at least 1")
        if not 0.0 <= minimum_grounding_accuracy <= 1.0:
            raise ValueError("minimum_grounding_accuracy must be between 0 and 1")
        self.sample_fps = sample_fps
        self.ocr_language = ocr_language
        self.whisper_model = whisper_model
        self.language = language
        self.ui_model_path = ui_model_path or os.getenv(
            "AIOS_UI_MODEL_PATH",
            "artifacts/models/showui-2b",
        )
        self.ui_secondary_small_model_path = ui_secondary_small_model_path or os.getenv(
            "AIOS_UI_SECONDARY_SMALL_MODEL_PATH",
            "artifacts/models/ui-tars-2b",
        )
        self.ui_fallback_model_path = ui_fallback_model_path or os.getenv(
            "AIOS_UI_FALLBACK_MODEL_PATH",
            "artifacts/models/ui-tars-7b",
        )
        self.grounding_benchmark_path = grounding_benchmark_path
        self.episode_model_path = episode_model_path or os.getenv(
            "AIOS_EPISODE_MODEL_PATH",
            "artifacts/models/aurum-4b-q4.gguf",
        )
        self.episode_fallback_model_path = episode_fallback_model_path or os.getenv(
            "AIOS_EPISODE_FALLBACK_MODEL_PATH",
            "artifacts/models/deepseek-v4-pro-9b-q4.gguf",
        )
        self.allow_model_download = allow_model_download
        self.maximum_vlm_frames = maximum_vlm_frames
        self.minimum_grounding_accuracy = minimum_grounding_accuracy
        self.llama_gpu_layers = llama_gpu_layers
        # Kept only for backwards compatibility. Hosted and legacy Qwen VLM inference
        # is not used by this pipeline; local ShowUI/UI-TARS weights are the default.
        self.legacy_vlm_model = vlm_model
        self.decision_verifier_endpoint = decision_verifier_endpoint or os.getenv(
            "AIOS_DECISION_VERIFIER_ENDPOINT"
        )
        self.decision_verifier_model_path = decision_verifier_model_path or os.getenv(
            "AIOS_DECISION_VERIFIER_MODEL_PATH"
        )
        if self.decision_verifier_model_path is None and not self.decision_verifier_endpoint:
            self.decision_verifier_model_path = str(self.episode_model_path)
        self.decision_verifier_model_name = decision_verifier_model_name
        self.decision_verifier_server_binary = decision_verifier_server_binary
        self.decision_verifier_port = decision_verifier_port
        self.decision_verifier_gpu_layers = (
            llama_gpu_layers
            if decision_verifier_gpu_layers is None
            else decision_verifier_gpu_layers
        )
        self.decision_verifier = decision_verifier

    def run(
        self,
        video_path: str | Path,
        output_dir: str | Path,
        captions_path: str | Path | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        pipeline_started = time.perf_counter()
        video = Path(video_path)
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        if not video.is_file():
            raise FileNotFoundError(f"video file does not exist: {video}")

        video_metadata = dict(metadata or {})
        file_metadata = probe_video(video)
        video_metadata.update(file_metadata)
        if not video_metadata.get("video_id"):
            video_metadata["video_id"] = video.stem
        video_metadata["filename"] = video.name

        stages: dict[str, Any] = {}
        stage_started = time.perf_counter()
        transcript, stages["subtitle_asr"] = load_transcript(
            video,
            captions_path,
            whisper_model=self.whisper_model,
            language=self.language,
        )
        valid_transcript = []
        for segment in transcript:
            start_ms = max(0, int(segment["start_ms"]))
            end_ms = min(int(segment["end_ms"]), file_metadata["duration_ms"])
            if start_ms >= file_metadata["duration_ms"] or end_ms < start_ms:
                continue
            segment["start_ms"] = start_ms
            segment["end_ms"] = end_ms
            segment["words"] = [
                word
                for word in segment.get("words", [])
                if start_ms <= int(word["start_ms"]) and int(word["end_ms"]) <= end_ms
            ]
            valid_transcript.append(segment)
        transcript = valid_transcript
        stages["subtitle_asr"]["segments"] = len(transcript)
        if not transcript and stages["subtitle_asr"]["status"] == "completed":
            stages["subtitle_asr"]["status"] = "failed"
            stages["subtitle_asr"]["error"] = "all transcript cues were outside the video duration"
        _write_json(output / "transcript.json", transcript)
        stages["subtitle_asr"]["latency_ms"] = round(
            (time.perf_counter() - stage_started) * 1000,
            2,
        )

        stage_started = time.perf_counter()
        sampled_frames = extract_sampled_frames(
            video,
            output / "frames",
            sample_fps=self.sample_fps,
        )
        analyzed_frames = detect_frame_changes(sampled_frames)
        change_frames = [frame for frame in analyzed_frames if frame.get("is_change")]
        stages["frame_change"] = {
            "status": "completed",
            "method": "grayscale_pixel_difference",
            "sample_fps": self.sample_fps,
            "sampled_frames": len(analyzed_frames),
            "changed_frames": len(change_frames),
            "initial_frames": sum(bool(frame.get("is_initial")) for frame in analyzed_frames),
            "changed_timestamps_ms": [frame["timestamp_ms"] for frame in change_frames],
            "change_ratio_threshold": 0.004,
            "minimum_gap_ms": 750,
            "latency_ms": round((time.perf_counter() - stage_started) * 1000, 2),
        }

        stage_started = time.perf_counter()
        try:
            ocr_records, stages["ocr"] = run_ocr(
                analyzed_frames,
                language=self.ocr_language,
            )
        except Exception as exc:
            ocr_records = []
            stages["ocr"] = {
                "status": "failed",
                "frames_processed": 0,
                "text_regions": 0,
                "error": f"{type(exc).__name__}: {exc}",
            }
        stages["ocr"]["latency_ms"] = round(
            (time.perf_counter() - stage_started) * 1000,
            2,
        )
        _write_json(output / "ocr.json", ocr_records)

        stage_started = time.perf_counter()
        cursor_events: list[dict[str, Any]] = []
        try:
            cursor_frames = CursorTracker().track(analyzed_frames)
            cursor_events = infer_click_candidates(cursor_frames)
            stages["cursor_tracking"] = {
                "status": "completed",
                "method": "multiscale_arrow_template_match",
                "sampled_frames": len(cursor_frames),
                "cursor_candidates": sum(bool(frame.get("cursor")) for frame in cursor_frames),
                "inferred_click_candidates": len(cursor_events),
                "certainty": "inferred_from_video",
                "warning": "Downloaded video contains no native click telemetry.",
            }
        except Exception as exc:
            stages["cursor_tracking"] = {
                "status": "failed",
                "cursor_candidates": 0,
                "inferred_click_candidates": 0,
                "error": f"{type(exc).__name__}: {exc}",
            }
        stages["cursor_tracking"]["latency_ms"] = round(
            (time.perf_counter() - stage_started) * 1000,
            2,
        )
        _write_json(output / "cursor-and-click-inferences.json", cursor_events)

        stage_started = time.perf_counter()
        grounding_results: list[dict[str, Any]] = []
        try:
            grounding_results, stages["ui_grounding"] = run_ui_grounding(
                primary_model_path=self.ui_model_path,
                secondary_small_model_path=self.ui_secondary_small_model_path,
                fallback_model_path=self.ui_fallback_model_path,
                benchmark_path=self.grounding_benchmark_path,
                allow_download=self.allow_model_download,
                frames=analyzed_frames,
                ocr_records=ocr_records,
                transcript=transcript,
                maximum_frames=self.maximum_vlm_frames,
                frame_dimensions=_first_frame_dimensions(analyzed_frames),
                minimum_accuracy=self.minimum_grounding_accuracy,
            )
        except Exception as exc:
            stages["ui_grounding"] = {
                "status": "failed",
                "small_first": True,
                "local_only_inference": True,
                "external_inference_provider_calls": 0,
                "error": f"{type(exc).__name__}: {exc}",
            }
        stages["ui_grounding"]["stage_latency_ms"] = round(
            (time.perf_counter() - stage_started) * 1000,
            2,
        )
        _write_json(output / "ui-grounding.json", grounding_results)
        if stages["ui_grounding"].get("selected_model_evaluation"):
            _write_json(
                output / "ui-grounding-model-evaluation.json",
                {
                    "primary_evaluation": stages["ui_grounding"].get("primary_evaluation"),
                    "secondary_small_evaluation": stages["ui_grounding"].get(
                        "secondary_small_evaluation"
                    ),
                    "large_fallback_evaluation": stages["ui_grounding"].get(
                        "large_fallback_evaluation"
                    ),
                    "selected_model_id": stages["ui_grounding"].get("selected_model_id"),
                    "selection_reason": stages["ui_grounding"].get("selection_reason"),
                    "selected_model_evaluation": stages["ui_grounding"].get(
                        "selected_model_evaluation"
                    ),
                },
            )

        visual_events = [
            {
                "event_id": f"frame-change-{frame['frame_index']:06d}",
                "timestamp_ms": int(frame["timestamp_ms"]),
                "event_type": "screen_change",
            }
            for frame in change_frames
        ]
        stage_started = time.perf_counter()
        alignment = align_transcript_to_events(transcript, visual_events)
        stages["narration_alignment"] = {
            "status": "completed" if transcript else "failed",
            "transcript_segments": len(transcript),
            "visual_change_events": len(visual_events),
            "segments_with_visual_matches": sum(
                bool(row["matched_event_ids"]) for row in alignment["alignment"]
            ),
            "alignment_method": "timestamp_window",
            "error": None if transcript else stages["subtitle_asr"].get("error", "no transcript"),
            "latency_ms": round((time.perf_counter() - stage_started) * 1000, 2),
        }
        _write_json(output / "narration-alignment.json", alignment)

        stage_started = time.perf_counter()
        episode = build_decision_episode(
            video_path=video,
            video_metadata=video_metadata,
            transcript=transcript,
            frames=analyzed_frames,
            ocr_records=ocr_records,
            cursor_events=cursor_events,
            vlm_results=grounding_results,
            alignment=alignment,
        )
        stages["episode_assembly"] = {
            "status": "completed",
            "latency_ms": round((time.perf_counter() - stage_started) * 1000, 2),
        }

        stage_started = time.perf_counter()
        episode, stages["decision_synthesis"] = synthesize_episode_decision(
            episode=episode,
            transcript=transcript,
            frames=analyzed_frames,
            ocr_records=ocr_records,
            cursor_events=cursor_events,
            grounding_results=grounding_results,
            small_model_path=self.episode_model_path,
            fallback_model_path=self.episode_fallback_model_path,
            allow_download=self.allow_model_download,
            n_gpu_layers=self.llama_gpu_layers,
        )
        stages["decision_synthesis"]["stage_latency_ms"] = round(
            (time.perf_counter() - stage_started) * 1000,
            2,
        )
        _write_json(output / "decision-synthesis.json", stages["decision_synthesis"])

        from contracts.validate import validate_episode

        stage_started = time.perf_counter()
        validation_errors = validate_episode(episode)
        stages["contract_validation"] = {
            "status": "passed" if not validation_errors else "failed",
            "validator": "contracts.validate.validate_episode",
            "error_count": len(validation_errors),
            "latency_ms": round((time.perf_counter() - stage_started) * 1000, 2),
        }
        validation = {
            "valid": not validation_errors,
            "errors": validation_errors,
            "validator": "contracts.validate.validate_episode",
        }
        # Keep the time-aligned source packet beside the proposal so the local gate
        # checks the actual extraction inputs and PM can independently inspect them.
        source_evidence = {
            "source_metadata": video_metadata,
            "transcript": transcript,
            "frames": analyzed_frames,
            "ocr_records": ocr_records,
            "cursor_events": cursor_events,
            "grounding_results": grounding_results,
            "alignment": alignment,
        }
        _write_json(output / "decision-source-evidence.json", source_evidence)

        stage_started = time.perf_counter()
        verifier = self.decision_verifier or LocalDecisionEpisodeVerifier(
            model_path=self.decision_verifier_model_path,
            endpoint=self.decision_verifier_endpoint,
            model_name=self.decision_verifier_model_name,
            server_binary=self.decision_verifier_server_binary,
            port=self.decision_verifier_port,
            n_gpu_layers=self.decision_verifier_gpu_layers,
        )
        local_verification = verifier.verify(episode, source_evidence)
        training_admission = training_dataset_admission_status(local_verification, None)
        stages["local_decision_verification"] = {
            "status": "passed" if local_verification["overall_status"] == "pass" else "held",
            "overall_status": local_verification["overall_status"],
            "model_provider": local_verification["verifier"]["provider"],
            "latency_ms": round((time.perf_counter() - stage_started) * 1000, 2),
        }
        _write_json(output / "decision-verification.json", local_verification)
        _write_json(output / "training-admission.json", training_admission)
        # A locally passing episode is still only a proposal until the PM gate is complete.
        _write_json(output / "decision-episode.json", episode)
        _write_json(output / "validation.json", validation)

        event_counts = Counter(
            "screen_change" if frame.get("is_change") else "sampled_unchanged"
            for frame in analyzed_frames
        )
        summary = {
            "status": "validated" if not validation_errors else "validation_failed",
            "video_file": str(video),
            "video_metadata": video_metadata,
            "part_breakdown": stages,
            "timings_ms": {
                name: stage.get("stage_latency_ms", stage.get("latency_ms"))
                for name, stage in stages.items()
                if stage.get("stage_latency_ms", stage.get("latency_ms")) is not None
            },
            "total_pipeline_ms": round((time.perf_counter() - pipeline_started) * 1000, 2),
            "model_policy": {
                "inference_mode": "local_open_weights_only",
                "local_only_inference": True,
                "external_inference_provider_calls": 0,
                "forbidden_inference_providers": [
                    "OpenAI GPT",
                    "Google Gemini",
                    "hosted moderation APIs",
                ],
                "model_downloads_are_weights_only": True,
            },
            "counts": {
                "sampled_frames": len(analyzed_frames),
                "changed_frames": len(change_frames),
                "ocr_text_regions": sum(len(record.get("regions", [])) for record in ocr_records),
                "subtitle_or_asr_segments": len(transcript),
                "cursor_candidates": stages.get("cursor_tracking", {}).get("cursor_candidates", 0),
                "inferred_click_candidates": len(cursor_events),
                "ui_grounding_results": len(grounding_results),
                "episode_synthesis_status": stages["decision_synthesis"].get("status"),
                "frame_event_counts": dict(event_counts),
            },
            "evidence_semantics": {
                "observed_from_video": ("Visible pixels, timestamped frame changes, and OCR text."),
                "inferred_from_video": (
                    "Cursor/click hypotheses and local GUI-model target coordinates."
                ),
                "instructor_words": (
                    "Subtitle/ASR transcript; contextual evidence, not a business rule."
                ),
            },
            "episode_id": episode["episode_id"],
            "validation": validation,
            "local_decision_verification": local_verification,
            "training_admission": training_admission,
        }
        _write_json(output / "part-breakdown.json", summary)
        return {
            "summary": summary,
            "episode": episode,
            "validation": validation,
            "local_verification": local_verification,
            "training_admission": training_admission,
        }
