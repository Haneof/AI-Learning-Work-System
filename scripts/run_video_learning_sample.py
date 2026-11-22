"""Run the video evidence pipeline on the licensed Content Translation screencast.

Captions are used as a deterministic ASR substitute and curated screen labels as an
OCR substitute. This exercises real FFmpeg extraction without claiming model accuracy.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from aios_work_system.media.adapters import TranscriptSegment
from aios_work_system.video_learning import (
    StaticASRAdapter,
    StaticOCRAdapter,
    VideoLearningPipeline,
)


def _timestamp_ms(value: str) -> int:
    hours, minutes, seconds = value.replace(",", ".").split(":")
    return round((int(hours) * 3600 + int(minutes) * 60 + float(seconds)) * 1000)


def parse_srt(path: Path) -> list[TranscriptSegment]:
    content = path.read_text(encoding="utf-8-sig")
    cue_pattern = re.compile(
        r"(?m)^\s*\d+\s*\n"
        r"(\d{2}:\d{2}:\d{2}[,.]\d{3})\s+-->\s+"
        r"(\d{2}:\d{2}:\d{2}[,.]\d{3})[^\n]*\n"
        r"([\s\S]*?)(?=\n\s*\n|\Z)"
    )
    segments = []
    for match in cue_pattern.finditer(content):
        text = " ".join(line.strip() for line in match.group(3).splitlines() if line.strip())
        if text:
            segments.append(
                TranscriptSegment(
                    start_ms=_timestamp_ms(match.group(1)),
                    end_ms=_timestamp_ms(match.group(2)),
                    text=text,
                )
            )
    if not segments:
        raise ValueError(f"No timestamped SRT cues found in {path}")
    return segments


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--captions", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    # These deterministic labels are not OCR results. They are anchored to the
    # benchmark's procedural landmarks so the fixture provenance remains explicit.
    ocr_stub = {
        15_000: "Beta features settings",
        60_000: "Contributions / Translation dashboard",
        75_000: "Source and target language selection",
        90_000: "Three-column translation editor",
        120_000: "Source sentence and links",
        150_000: "Review and revise translated paragraph",
        165_000: "Create links",
        180_000: "Categories / autosaved draft",
        195_000: "Resume draft from dashboard",
        210_000: "Publish translation",
    }
    pipeline = VideoLearningPipeline(
        asr=StaticASRAdapter(
            name="wikimedia-timed-text-asr-stub",
            version="1",
            segments=parse_srt(args.captions),
        ),
        ocr=StaticOCRAdapter(
            name="curated-screencast-ocr-stub",
            version="1",
            text_by_timestamp=ocr_stub,
        ),
    )
    result = pipeline.ingest(
        args.input,
        args.output_dir,
        expert_id="software-tutorial-learning",
        applicability_scope=(
            "Wikipedia Content Translation workflow as demonstrated in the "
            "2015 screencast; verify current UI and behavior before reuse."
        ),
        source_version="commons-2015-01-13",
        knowledge_version=1,
        frame_interval_seconds=15,
        chunk_duration_seconds=30,
    )
    report = {
        "status": "PASS",
        "execution": "real_ffmpeg_with_asr_ocr_stubs",
        "source_file": result.source.original_name,
        "source_sha256": result.source.sha256,
        "audio_extracted": result.audio_path.is_file(),
        "frames_extracted": len(result.frame_paths),
        "timestamped_text_segments": len(result.temporal_segments),
        "candidate_knowledge_records": len(result.evidence_records),
        "manifest": str(result.manifest_path),
        "knowledge_evidence": str(result.evidence_path),
        "asr_adapter": "wikimedia-timed-text-asr-stub (captions, no inference)",
        "ocr_adapter": "curated-screencast-ocr-stub (illustrative labels, no inference)",
    }
    report_path = Path(args.output_dir).resolve() / "video-learning-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
