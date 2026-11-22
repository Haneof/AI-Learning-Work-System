"""Run Tesseract OCR over real keyframes extracted from the tutorial video."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import pytesseract
from PIL import Image

from aios_work_system.media import FFmpegProcessor


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--interval-seconds", type=float, default=60.0)
    parser.add_argument("--language", default="eng")
    args = parser.parse_args()

    source = args.input.expanduser().resolve(strict=True)
    output_dir = args.output_dir.expanduser().resolve()
    frames_dir = output_dir / "frames"
    output_dir.mkdir(parents=True, exist_ok=True)

    processor = FFmpegProcessor(timeout_seconds=2400)
    frames = processor.extract_frames(source, frames_dir, args.interval_seconds)
    rows = []
    started = time.perf_counter()
    for frame in frames:
        frame_started = time.perf_counter()
        image = Image.open(frame).convert("L")
        image.thumbnail((640, 360))
        extracted = pytesseract.image_to_string(
            image, lang=args.language, config="--psm 11"
        ).strip()
        rows.append(
            {
                "frame": frame.name,
                "timestamp_seconds": round(len(rows) * args.interval_seconds, 3),
                "characters": len(extracted),
                "text": extracted,
                "elapsed_ms": round((time.perf_counter() - frame_started) * 1000, 1),
            }
        )

    report = {
        "status": "PASS" if rows and any(item["characters"] for item in rows) else "FAIL",
        "test_kind": "REAL_VIDEO_KEYFRAME_TESSERACT_OCR",
        "engine": "Tesseract",
        "engine_version": str(pytesseract.get_tesseract_version()),
        "language": args.language,
        "resize_max": "640x360",
        "interval_seconds": args.interval_seconds,
        "frame_count": len(rows),
        "frames_with_text": sum(item["characters"] > 0 for item in rows),
        "total_characters": sum(item["characters"] for item in rows),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "frames": rows,
    }
    (output_dir / "ocr-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {key: value for key, value in report.items() if key != "frames"},
            ensure_ascii=False,
            indent=2,
        )
    )
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
