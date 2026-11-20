"""Score Tesseract Chinese OCR against manually transcribed keyframe labels."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def normalize(value: str) -> str:
    """Keep CJK ideographs only; this benchmark targets the main Chinese phrase."""
    return "".join(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", value))


def edit_distance(reference: str, hypothesis: str) -> int:
    previous = list(range(len(hypothesis) + 1))
    for i, ref_char in enumerate(reference, start=1):
        current = [i]
        for j, hyp_char in enumerate(hypothesis, start=1):
            current.append(min(
                current[-1] + 1,
                previous[j] + 1,
                previous[j - 1] + (ref_char != hyp_char),
            ))
        previous = current
    return previous[-1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ocr-report", required=True, type=Path)
    parser.add_argument("--ground-truth", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    report = json.loads(args.ocr_report.read_text(encoding="utf-8"))
    truth = json.loads(args.ground_truth.read_text(encoding="utf-8"))
    predictions = {row["frame"]: row.get("text", "") for row in report["frames"]}

    rows = []
    total_edits = 0
    total_reference_chars = 0
    missing_frames = []
    for item in truth["frames"]:
        frame = item["frame"]
        reference = normalize(item["reference"])
        if frame not in predictions:
            missing_frames.append(frame)
            hypothesis = ""
        else:
            hypothesis = normalize(predictions[frame])
        edits = edit_distance(reference, hypothesis)
        total_edits += edits
        total_reference_chars += len(reference)
        rows.append({
            "frame": frame,
            "timestamp_seconds": item["timestamp_seconds"],
            "reference": reference,
            "hypothesis": hypothesis,
            "edit_distance": edits,
            "reference_characters": len(reference),
            "cer": round(edits / len(reference), 6) if reference else None,
        })

    cer = total_edits / total_reference_chars if total_reference_chars else 1.0
    result = {
        "status": "SCORED" if not missing_frames else "INCOMPLETE",
        "metric": "Chinese-character CER (edit distance / reference characters)",
        "dataset": truth["dataset"],
        "frames_scored": len(rows) - len(missing_frames),
        "frames_expected": len(rows),
        "missing_frames": missing_frames,
        "total_edit_distance": total_edits,
        "total_reference_characters": total_reference_chars,
        "cer": round(cer, 6),
        "character_accuracy_proxy": round(max(0.0, 1.0 - cer), 6),
        "interpretation": "Diagnostic score on 10 manually labeled keyframes only; not a general OCR accuracy estimate.",
        "frames": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "frames"}, ensure_ascii=False, indent=2))
    if missing_frames:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
