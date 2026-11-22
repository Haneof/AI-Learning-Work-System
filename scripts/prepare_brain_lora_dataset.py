"""Prepare compiler JSONL + sidecars for Axolotl's chat-template SFT loader."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from aios_work_system.training_data.lora import (
    load_training_config,
    prepare_axolotl_datasets,
    validate_lora_config,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path("artifacts/brain-training"))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/brain-training/axolotl"),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/brain_lora_t4.yml"),
    )
    parser.add_argument("--max-repeat-factor", type=int, default=3)
    args = parser.parse_args()

    config = load_training_config(args.config)
    validate_lora_config(config, gpu_profile="t4")
    result = prepare_axolotl_datasets(
        train_jsonl=args.input_dir / "train.jsonl",
        train_meta_jsonl=args.input_dir / "train.training_meta.jsonl",
        test_jsonl=args.input_dir / "test.jsonl",
        test_meta_jsonl=args.input_dir / "test.training_meta.jsonl",
        output_dir=args.output_dir,
        max_repeat_factor=args.max_repeat_factor,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("Dataset preparation only: no base model was downloaded and no training was started.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
