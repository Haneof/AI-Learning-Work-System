"""Compile a JSON review-bundle manifest into Brain training JSONL files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from aios_work_system.training_data import compile_episodes, write_compilation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compile only DecisionEpisodes that passed local verification, independent PM "
            "review, and the trainable-quality gate."
        )
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="UTF-8 JSON list of review bundles (episode/local_verification/pm_verification).",
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--train-fraction", type=float, default=0.8)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    with args.input.open(encoding="utf-8") as handle:
        payload: Any = json.load(handle)
    bundles = payload.get("episodes") if isinstance(payload, dict) else payload
    if not isinstance(bundles, list):
        raise SystemExit("Input JSON must be a list or an object containing an 'episodes' list.")

    result = compile_episodes(
        bundles,
        seed=args.seed,
        train_fraction=args.train_fraction,
    )
    paths = write_compilation(result, args.output_dir)
    print(
        json.dumps(
            {
                "train_samples": len(result.train_samples),
                "test_samples": len(result.test_samples),
                "excluded_items": len(result.exclusions),
                "exclusions": result.exclusions,
                "paths": paths,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
