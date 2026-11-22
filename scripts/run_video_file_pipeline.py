"""Process a downloaded tutorial video file into a validated DecisionEpisode."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Local downloaded video file.")
    parser.add_argument("--captions", type=Path, help="Optional local SRT/VTT subtitle file.")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--sample-fps", type=float, default=2.0)
    parser.add_argument("--ocr-language", default="eng")
    parser.add_argument("--whisper-model", default="tiny")
    parser.add_argument("--language")
    parser.add_argument("--ui-model-path", type=Path, default=Path("artifacts/models/showui-2b"))
    parser.add_argument(
        "--ui-secondary-small-model-path",
        type=Path,
        default=Path("artifacts/models/ui-tars-2b"),
    )
    parser.add_argument(
        "--ui-fallback-model-path",
        type=Path,
        default=Path("artifacts/models/ui-tars-7b"),
    )

    parser.add_argument(
        "--grounding-benchmark",
        type=Path,
        help=(
            "Human-annotated changed-frame target bounding boxes used to measure "
            "grounding accuracy."
        ),
    )
    parser.add_argument(
        "--episode-model-path",
        type=Path,
        default=Path("artifacts/models/aurum-4b-q4.gguf"),
    )
    parser.add_argument(
        "--episode-fallback-model-path",
        type=Path,
        default=Path("artifacts/models/deepseek-v4-pro-9b-q4.gguf"),
    )
    parser.add_argument(
        "--decision-verifier-model-path",
        type=Path,
        help="Local open-weight verifier GGUF; defaults to the primary 4B episode model.",
    )
    parser.add_argument(
        "--decision-verifier-endpoint",
        help="Optional local loopback llama-server /v1/chat/completions URL.",
    )
    parser.add_argument("--decision-verifier-model-name", default="local-open-model")
    parser.add_argument("--decision-verifier-server-binary", default="llama-server")
    parser.add_argument("--decision-verifier-port", type=int, default=8089)
    parser.add_argument("--decision-verifier-gpu-layers", type=int)
    parser.add_argument(
        "--allow-model-download",
        action="store_true",
        help="Allow Hugging Face to download model WEIGHTS only; all inference remains local.",
    )
    parser.add_argument("--minimum-grounding-accuracy", type=float, default=0.75)
    parser.add_argument(
        "--maximum-changed-frames",
        "--maximum-vlm-frames",
        dest="maximum_vlm_frames",
        type=int,
        default=24,
    )
    parser.add_argument("--llama-gpu-layers", type=int, default=-1)
    parser.add_argument("--source-id")
    parser.add_argument("--source-platform", default="youtube")
    args = parser.parse_args()

    from aios_work_system.video_extraction.pipeline import VideoExtractionPipeline

    try:
        pipeline = VideoExtractionPipeline(
            sample_fps=args.sample_fps,
            ocr_language=args.ocr_language,
            whisper_model=args.whisper_model,
            language=args.language,
            ui_model_path=args.ui_model_path,
            ui_fallback_model_path=args.ui_fallback_model_path,
            ui_secondary_small_model_path=args.ui_secondary_small_model_path,
            grounding_benchmark_path=args.grounding_benchmark,
            episode_model_path=args.episode_model_path,
            episode_fallback_model_path=args.episode_fallback_model_path,
            allow_model_download=args.allow_model_download,
            maximum_vlm_frames=args.maximum_vlm_frames,
            minimum_grounding_accuracy=args.minimum_grounding_accuracy,
            llama_gpu_layers=args.llama_gpu_layers,
            decision_verifier_model_path=(
                args.decision_verifier_model_path or args.episode_model_path
            ),
            decision_verifier_endpoint=args.decision_verifier_endpoint,
            decision_verifier_model_name=args.decision_verifier_model_name,
            decision_verifier_server_binary=args.decision_verifier_server_binary,
            decision_verifier_port=args.decision_verifier_port,
            decision_verifier_gpu_layers=(
                args.llama_gpu_layers
                if args.decision_verifier_gpu_layers is None
                else args.decision_verifier_gpu_layers
            ),
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
    print("=== LOCAL DECISION VERIFICATION ===")
    print(json.dumps(result["local_verification"], ensure_ascii=False, indent=2))
    print("=== TRAINING DATASET ADMISSION ===")
    print(json.dumps(result["training_admission"], ensure_ascii=False, indent=2))
    return 0 if result["validation"]["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
