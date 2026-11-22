"""Process a downloaded tutorial video file into a validated DecisionEpisode."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from aios_work_system.video_extraction.pipeline import VideoExtractionPipeline


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Local downloaded video file.")
    parser.add_argument("--captions", type=Path, help="Optional local SRT/VTT subtitle file.")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--sample-fps", type=float, default=2.0)
    parser.add_argument("--ocr-language", default="eng")
    parser.add_argument("--whisper-model", default="tiny")
    parser.add_argument("--language")
    parser.add_argument(
        "--vlm-model",
        default="Qwen/Qwen3-VL-2B-Instruct",
        help="Qwen3-VL model ID; pass 'none' to disable VLM.",
    )
    parser.add_argument("--maximum-vlm-frames", type=int, default=24)
    parser.add_argument("--source-id")
    parser.add_argument("--source-platform", default="youtube")
    args = parser.parse_args()

    try:
        pipeline = VideoExtractionPipeline(
            sample_fps=args.sample_fps,
            ocr_language=args.ocr_language,
            whisper_model=args.whisper_model,
            language=args.language,
            vlm_model=None if args.vlm_model.lower() == "none" else args.vlm_model,
            maximum_vlm_frames=args.maximum_vlm_frames,
        )
        metadata = {
            "video_id": args.source_id or args.input.stem,
            "extractor": args.source_platform,
        }
        result = pipeline.run(
            args.input,
            args.output_dir,
            captions_path=args.captions,
            metadata=metadata,
        )
    except Exception as exc:
        print(
            f"Video file pipeline failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1

    print("=== PER-PART BREAKDOWN ===")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print("=== VALIDATED DECISION EPISODE ===")
    print(json.dumps(result["episode"], ensure_ascii=False, indent=2))
    print("=== CONTRACT VALIDATION ===")
    print(json.dumps(result["validation"], ensure_ascii=False, indent=2))
    return 0 if result["validation"]["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
