"""Run a real CPU faster-whisper transcription smoke test on the tutorial sample."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from faster_whisper import WhisperModel


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model", default="tiny.en")
    args = parser.parse_args()

    audio_path = args.input.expanduser().resolve(strict=True)
    output_path = args.output.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    model = WhisperModel(args.model, device="cpu", compute_type="int8")
    segments, info = model.transcribe(
        str(audio_path),
        language="en",
        beam_size=1,
        vad_filter=True,
        word_timestamps=False,
    )
    rows = [
        {
            "start": round(item.start, 3),
            "end": round(item.end, 3),
            "text": item.text.strip(),
        }
        for item in segments
    ]
    elapsed = time.perf_counter() - started
    transcript = " ".join(item["text"] for item in rows).strip()
    if not rows or not transcript:
        raise SystemExit("FAIL: ASR returned no transcript segments")
    if any(item["start"] < 0 or item["end"] <= item["start"] for item in rows):
        raise SystemExit("FAIL: ASR returned invalid segment timestamps")

    report = {
        "status": "PASS",
        "test_kind": "REAL_AUDIO_FASTER_WHISPER_CPU_INT8",
        "model": args.model,
        "device": "cpu",
        "compute_type": "int8",
        "detected_language": info.language,
        "language_probability": round(info.language_probability, 4),
        "audio_duration_seconds": round(info.duration, 3),
        "transcription_elapsed_seconds": round(elapsed, 3),
        "segment_count": len(rows),
        "transcript_characters": len(transcript),
        "segments": rows,
    }
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({key: value for key, value in report.items() if key != "segments"}, indent=2))


if __name__ == "__main__":
    main()
