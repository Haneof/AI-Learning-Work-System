"""End-to-end processing for downloaded tutorial video files."""

from __future__ import annotations

import json
import subprocess
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
from aios_work_system.video_extraction.transcript import load_transcript


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


class VideoExtractionPipeline:
    """Subtitle/ASR -> frame changes -> OCR/cursor -> changed-frame VLM -> episode."""

    def __init__(
        self,
        sample_fps: float = 2.0,
        ocr_language: str = "eng",
        whisper_model: str = "tiny",
        language: str | None = None,
        vlm_model: str | None = "Qwen/Qwen3-VL-2B-Instruct",
        maximum_vlm_frames: int = 24,
    ) -> None:
        if maximum_vlm_frames < 1:
            raise ValueError("maximum_vlm_frames must be at least 1")
        self.sample_fps = sample_fps
        self.ocr_language = ocr_language
        self.whisper_model = whisper_model
        self.language = language
        self.vlm_model = vlm_model
        self.maximum_vlm_frames = maximum_vlm_frames

    def run(
        self,
        video_path: str | Path,
        output_dir: str | Path,
        captions_path: str | Path | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
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
        }

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
        _write_json(output / "ocr.json", ocr_records)

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
        _write_json(output / "cursor-and-click-inferences.json", cursor_events)

        vlm_results: list[dict[str, Any]] = []
        changed_for_vlm = change_frames[: self.maximum_vlm_frames]
        if not self.vlm_model:
            stages["vlm_grounding"] = {
                "status": "disabled",
                "frames_submitted": 0,
                "candidate_changed_frames": len(change_frames),
                "results": [],
            }
        elif changed_for_vlm:
            try:
                from aios_work_system.video_extraction.vlm import Qwen3VLGrounder

                grounder = Qwen3VLGrounder(self.vlm_model)
                ocr_by_timestamp = {
                    int(record["timestamp_ms"]): record.get("text", "") for record in ocr_records
                }
                for index, frame in enumerate(changed_for_vlm, start=1):
                    timestamp_ms = int(frame["timestamp_ms"])
                    nearest_ocr = min(
                        ocr_by_timestamp,
                        key=lambda value: abs(value - timestamp_ms),
                        default=None,
                    )
                    ocr_text = (
                        ocr_by_timestamp.get(nearest_ocr, "")
                        if nearest_ocr is not None and abs(nearest_ocr - timestamp_ms) <= 1500
                        else ""
                    )
                    nearby_narration = [
                        segment
                        for segment in transcript
                        if int(segment["start_ms"]) - 3500
                        <= timestamp_ms
                        <= int(segment["end_ms"]) + 3500
                    ]
                    narration_context = " ".join(segment["text"] for segment in nearby_narration)
                    try:
                        result = grounder.ground(
                            frame["path"],
                            timestamp_ms,
                            ocr_text,
                            narration_context,
                        )
                    except Exception as exc:
                        result = {
                            "status": "failed",
                            "timestamp_ms": timestamp_ms,
                            "frame_path": frame["path"],
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    result["grounding_index"] = index
                    result["ocr_context"] = ocr_text
                    result["narration_context"] = narration_context
                    vlm_results.append(result)
                completed = sum(item.get("status") == "completed" for item in vlm_results)
                stages["vlm_grounding"] = {
                    "status": (
                        "completed"
                        if completed == len(changed_for_vlm)
                        else "partial"
                        if completed
                        else "failed"
                    ),
                    "model": self.vlm_model,
                    "candidate_changed_frames": len(change_frames),
                    "frames_submitted": len(changed_for_vlm),
                    "frames_omitted_by_configured_cap": max(
                        0, len(change_frames) - len(changed_for_vlm)
                    ),
                    "completed": completed,
                    "failed": len(vlm_results) - completed,
                    "selection_rule": "only frame_change.is_change == true",
                    "generation_max_new_tokens": 192,
                }
            except Exception as exc:
                stages["vlm_grounding"] = {
                    "status": "failed",
                    "model": self.vlm_model,
                    "candidate_changed_frames": len(change_frames),
                    "frames_submitted": 0,
                    "error": f"{type(exc).__name__}: {exc}",
                }
        else:
            stages["vlm_grounding"] = {
                "status": "no_changed_frames",
                "model": self.vlm_model,
                "candidate_changed_frames": 0,
                "frames_submitted": 0,
            }
        _write_json(output / "vlm-grounding.json", vlm_results)

        visual_events = [
            {
                "event_id": f"frame-change-{frame['frame_index']:06d}",
                "timestamp_ms": int(frame["timestamp_ms"]),
                "event_type": "screen_change",
            }
            for frame in change_frames
        ]
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
        }
        _write_json(output / "narration-alignment.json", alignment)

        episode = build_decision_episode(
            video_path=video,
            video_metadata=video_metadata,
            transcript=transcript,
            frames=analyzed_frames,
            ocr_records=ocr_records,
            cursor_events=cursor_events,
            vlm_results=vlm_results,
            alignment=alignment,
        )
        from contracts.validate import validate_episode

        validation_errors = validate_episode(episode)
        validation = {
            "valid": not validation_errors,
            "errors": validation_errors,
            "validator": "contracts.validate.validate_episode",
        }
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
            "counts": {
                "sampled_frames": len(analyzed_frames),
                "changed_frames": len(change_frames),
                "ocr_text_regions": sum(len(record.get("regions", [])) for record in ocr_records),
                "subtitle_or_asr_segments": len(transcript),
                "cursor_candidates": stages.get("cursor_tracking", {}).get("cursor_candidates", 0),
                "inferred_click_candidates": len(cursor_events),
                "vlm_grounding_results": len(vlm_results),
                "frame_event_counts": dict(event_counts),
            },
            "evidence_semantics": {
                "observed_from_video": ("Visible pixels, timestamped frame changes, and OCR text."),
                "inferred_from_video": (
                    "Cursor/click hypotheses and VLM target/action hypotheses."
                ),
                "instructor_words": ("Subtitle/ASR transcript; context only, not a business rule."),
            },
            "episode_id": episode["episode_id"],
            "validation": validation,
        }
        _write_json(output / "part-breakdown.json", summary)
        return {"summary": summary, "episode": episode, "validation": validation}
