"""Metadata-aware dataset preparation for the Brain LoRA SFT run.

Axolotl consumes OpenAI-style messages but does not apply arbitrary per-row
sidecar loss weights in its standard SFT config. This module turns those
weights into deterministic, bounded repeat counts before Axolotl loads data.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aios_work_system.training_data.compiler import validate_training_sample

BASE_MODEL_ID = "DreamFast/qwen3-4b-heretic"
EXCLUDED_STATUSES = frozenset(
    {"excluded", "held", "rejected", "quarantined", "not_approved", "blocked"}
)
OBSERVATION_WEIGHTS = {
    "direct_capture": 1.0,
    "screen_capture": 0.9,
    "video_inferred": 0.75,
    "visual_inference": 0.75,
    "transcript": 0.7,
    "not_applicable": 0.8,
    "unknown": 0.5,
}
RATIONALE_WEIGHTS = {
    "instructor_explicit": 1.0,
    "hybrid": 0.9,
    "behavioral_inference": 0.8,
    "user_provided": 0.75,
    "not_applicable": 0.65,
    "unknown": 0.5,
}
LORA_TARGET_MODULES = frozenset(
    {"q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"}
)


@dataclass(frozen=True)
class WeightedSample:
    """One model-facing conversation paired with its private evidence sidecar."""

    sample: dict[str, Any]
    metadata: dict[str, Any]
    weight: float


@dataclass(frozen=True)
class PreparedDataset:
    """Loaded train/test rows with aligned metadata."""

    train: tuple[WeightedSample, ...]
    test: tuple[WeightedSample, ...]


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"required JSONL file does not exist: {source}")
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{source}:{line_number}: invalid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{source}:{line_number}: each JSONL row must be an object")
        rows.append(value)
    return rows


def _reject_excluded(metadata: Mapping[str, Any], *, sample_index: int) -> None:
    for flag in ("excluded", "is_excluded", "do_not_train"):
        if metadata.get(flag) is True:
            raise ValueError(f"sidecar sample {sample_index} is marked excluded ({flag}=true)")
    for flag in ("eligible_for_training", "eligible_for_dataset", "trainable"):
        if flag in metadata and metadata[flag] is False:
            raise ValueError(f"sidecar sample {sample_index} is not eligible ({flag}=false)")
    status = metadata.get("status")
    if isinstance(status, str) and status.strip().lower() in EXCLUDED_STATUSES:
        raise ValueError(f"sidecar sample {sample_index} has excluded status {status!r}")
    if metadata.get("exclusion_reason") or metadata.get("exclusion_reasons"):
        raise ValueError(f"sidecar sample {sample_index} carries an exclusion reason")


def _mean_weighted(values: Sequence[str], weights: Mapping[str, float]) -> float:
    if not values:
        return 0.5
    return sum(weights.get(value, 0.5) for value in values) / len(values)


def calculate_sample_weight(metadata: Mapping[str, Any]) -> float:
    """Calculate a bounded priority from both evidence axes and confidence.

    The score affects training-row frequency, not the content of a prompt or label.
    Missing confidence is neutral (0.5); malformed confidence fails closed.
    """
    evidence_tier = metadata.get("evidence_tier")
    if not isinstance(evidence_tier, Mapping):
        raise ValueError("sidecar evidence_tier must be an object")

    observations = evidence_tier.get("observation_channel")
    rationales = evidence_tier.get("rationale_source")
    confidences = evidence_tier.get("confidence")
    if not isinstance(observations, list) or not all(
        isinstance(value, str) for value in observations
    ):
        raise ValueError("evidence_tier.observation_channel must be a list of strings")
    if not isinstance(rationales, list) or not all(
        isinstance(value, str) for value in rationales
    ):
        raise ValueError("evidence_tier.rationale_source must be a list of strings")
    if not isinstance(confidences, Mapping):
        raise ValueError("evidence_tier.confidence must be an object")

    confidence_values: list[float] = []
    for value in confidences.values():
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("evidence confidence values must be numbers or null")
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise ValueError("evidence confidence values must be between 0 and 1")
        confidence_values.append(float(value))

    rationale_loss_weight = metadata.get("rationale_loss_weight")
    if (
        isinstance(rationale_loss_weight, bool)
        or not isinstance(rationale_loss_weight, (int, float))
        or not math.isfinite(rationale_loss_weight)
        or not 0.0 <= rationale_loss_weight <= 1.0
    ):
        raise ValueError("rationale_loss_weight must be a finite number between 0 and 1")

    observation_score = _mean_weighted(observations, OBSERVATION_WEIGHTS)
    rationale_score = _mean_weighted(rationales, RATIONALE_WEIGHTS)
    confidence_score = (
        sum(confidence_values) / len(confidence_values) if confidence_values else 0.5
    )
    score = (
        0.30 * observation_score
        + 0.30 * rationale_score
        + 0.20 * confidence_score
        + 0.20 * float(rationale_loss_weight)
    )
    return round(min(1.0, max(0.05, score)), 6)


def load_weighted_split(
    model_jsonl: str | Path,
    sidecar_jsonl: str | Path,
    *,
    expected_partition: str,
    allow_empty: bool = False,
) -> tuple[WeightedSample, ...]:
    """Read a model JSONL and its row-aligned sidecar; never silently drop metadata."""
    if expected_partition not in {"train", "test"}:
        raise ValueError("expected_partition must be 'train' or 'test'")
    samples = _read_jsonl(model_jsonl)
    sidecars = _read_jsonl(sidecar_jsonl)
    if len(samples) != len(sidecars):
        raise ValueError(
            f"{expected_partition} model/sidecar row-count mismatch: "
            f"{len(samples)} != {len(sidecars)}"
        )
    if not samples and not allow_empty:
        raise ValueError(f"{expected_partition} dataset has no approved samples")

    loaded: list[WeightedSample] = []
    seen_ids: set[str] = set()
    for index, (sample, metadata) in enumerate(zip(samples, sidecars, strict=True), start=1):
        _reject_excluded(metadata, sample_index=index)
        sample_id = metadata.get("sample_id")
        if not isinstance(sample_id, str) or not sample_id.strip():
            raise ValueError(f"{expected_partition} sidecar row {index} has no sample_id")
        if sample_id in seen_ids:
            raise ValueError(\n                f"{expected_partition} sidecar contains duplicate sample_id {sample_id}"\n            )
        seen_ids.add(sample_id)
        if metadata.get("partition") != expected_partition:
            raise ValueError(
                f"{expected_partition} sidecar row {index} has partition "
                f"{metadata.get('partition')!r}"
            )
        validate_training_sample(sample)
        loaded.append(
            WeightedSample(
                sample=sample,
                metadata=metadata,
                weight=calculate_sample_weight(metadata),
            )
        )
    return tuple(loaded)


def weighted_training_rows(
    samples: Sequence[WeightedSample], *, max_repeat_factor: int = 3
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Repeat high-weight rows more often while retaining every original row at least once.

    Repetition is deterministic and bounded. Equal-weight datasets are left unchanged.
    """
    if isinstance(max_repeat_factor, bool) or not isinstance(max_repeat_factor, int):
        raise ValueError("max_repeat_factor must be an integer")
    if not 1 <= max_repeat_factor <= 10:
        raise ValueError("max_repeat_factor must be between 1 and 10")
    if not samples:
        raise ValueError("cannot materialize an empty training split")

    weights = [sample.weight for sample in samples]
    low = min(weights)
    high = max(weights)
    repeats: dict[str, int] = {}
    rows: list[dict[str, Any]] = []
    for item in samples:
        sample_id = str(item.metadata["sample_id"])
        if max_repeat_factor == 1 or math.isclose(low, high):
            repeat = 1
        else:
            relative = (item.weight - low) / (high - low)
            repeat = 1 + round(relative * (max_repeat_factor - 1))
        repeats[sample_id] = repeat
        rows.extend([item.sample] * repeat)
    return rows, repeats


def write_jsonl(path: str | Path, rows: Sequence[Mapping[str, Any]]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
            stream.write("\n")


def prepare_axolotl_datasets(
    *,
    train_jsonl: str | Path,
    train_meta_jsonl: str | Path,
    test_jsonl: str | Path,
    test_meta_jsonl: str | Path,
    output_dir: str | Path,
    max_repeat_factor: int = 3,
) -> dict[str, Any]:
    """Join compiler outputs, reject held rows, and write Axolotl-ready chat JSONL."""
    train = load_weighted_split(
        train_jsonl,
        train_meta_jsonl,
        expected_partition="train",
    )
    test = load_weighted_split(
        test_jsonl,
        test_meta_jsonl,
        expected_partition="test",
    )
    train_rows, repeats = weighted_training_rows(train, max_repeat_factor=max_repeat_factor)
    if not test:
        raise ValueError(
            "test split is empty; source-grouped compiler output needs at least two "
            "eligible source groups before training/evaluation"
        )

    destination = Path(output_dir)
    train_path = destination / "train.weighted.jsonl"
    test_path = destination / "test.jsonl"
    manifest_path = destination / "weight_manifest.json"
    write_jsonl(train_path, train_rows)
    write_jsonl(test_path, [item.sample for item in test])

    manifest = {
        "weighting": "deterministic_bounded_row_repetition",
        "max_repeat_factor": max_repeat_factor,
        "sidecar_fields_used": [
            "evidence_tier.observation_channel",
            "evidence_tier.rationale_source",
            "evidence_tier.confidence",
            "rationale_loss_weight",
        ],
        "train_original_count": len(train),
        "train_materialized_count": len(train_rows),
        "test_count": len(test),
        "train_samples": [
            {
                "sample_id": item.metadata["sample_id"],
                "weight": item.weight,
                "repeat_count": repeats[str(item.metadata["sample_id"])],
            }
            for item in train
        ],
        "test_samples": [
            {"sample_id": item.metadata["sample_id"], "weight": item.weight} for item in test
        ],
        "sidecar_in_model_messages": False,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "train_path": str(train_path),
        "test_path": str(test_path),
        "manifest_path": str(manifest_path),
        "train_original_count": len(train),
        "train_materialized_count": len(train_rows),
        "test_count": len(test),
    }


def load_training_config(path: str | Path) -> dict[str, Any]:
    """Load an Axolotl YAML config (PyYAML is supplied by the training-config extra)."""
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError(
            "PyYAML is required to read the training config; install the training-config extra"
        ) from exc

    config_path = Path(path)
    if not config_path.is_file():
        raise FileNotFoundError(f"training config does not exist: {config_path}")
    with config_path.open(encoding="utf-8") as stream:
        value = yaml.safe_load(stream)
    if not isinstance(value, dict):
        raise ValueError("Axolotl config must contain a YAML object")
    return value


def validate_lora_config(config: Mapping[str, Any], *, gpu_profile: str = "t4") -> None:
    """Validate the project-specific 4B Brain LoRA profile before any model download."""
    if config.get("base_model") != BASE_MODEL_ID:
        raise ValueError(f"base_model must be the full HF checkpoint {BASE_MODEL_ID!r}")
    if config.get("adapter") != "lora":
        raise ValueError("adapter must be 'lora'; quantized QLoRA is not the T4 full-weight path")
    if config.get("load_in_4bit") is True or config.get("load_in_8bit") is True:
        raise ValueError("quantized loading is forbidden for the full-weight Brain LoRA setup")

    sequence_len = config.get("sequence_len")
    if isinstance(sequence_len, bool) or not isinstance(sequence_len, int) or sequence_len < 128:
        raise ValueError("sequence_len must be an integer of at least 128")
    if gpu_profile == "t4" and sequence_len > 1024:
        raise ValueError("T4 profile sequence_len must not exceed 1024")

    rank = config.get("lora_r")
    alpha = config.get("lora_alpha")
    if isinstance(rank, bool) or not isinstance(rank, int) or rank < 1:
        raise ValueError("lora_r must be a positive integer")
    if isinstance(alpha, bool) or not isinstance(alpha, int) or alpha < 1:
        raise ValueError("lora_alpha must be a positive integer")
    targets = config.get("lora_target_modules")
    if not isinstance(targets, list) or not LORA_TARGET_MODULES.issubset(set(targets)):
        raise ValueError(f"lora_target_modules must include {sorted(LORA_TARGET_MODULES)}")

    micro_batch = config.get("micro_batch_size")
    accumulation = config.get("gradient_accumulation_steps")
    epochs = config.get("num_epochs")
    learning_rate = config.get("learning_rate")
    if micro_batch != 1:
        raise ValueError("T4 profile requires micro_batch_size: 1")
    if isinstance(accumulation, bool) or not isinstance(accumulation, int) or accumulation < 1:
        raise ValueError("gradient_accumulation_steps must be a positive integer")
    if isinstance(epochs, bool) or not isinstance(epochs, (int, float)) or epochs <= 0:
        raise ValueError("num_epochs must be positive")
    if (
        isinstance(learning_rate, bool)
        or not isinstance(learning_rate, (int, float))
        or not math.isfinite(learning_rate)
        or learning_rate <= 0
    ):
        raise ValueError("learning_rate must be a positive finite number")
    if config.get("activation_checkpointing") is not True:
        raise ValueError("T4 profile requires activation_checkpointing: true")
    if config.get("fp16") is not True:
        raise ValueError("T4 profile requires fp16: true")
    if config.get("bf16") is not False:
        raise ValueError(
            "BF16 is unsupported on the T4 profile (compute capability 7.5); set bf16: false"
        )
    if config.get("type_of_model") != "AutoModelForCausalLM":
        raise ValueError("type_of_model must be AutoModelForCausalLM")

    for dataset_key, expected_partition in (("datasets", "train"), ("test_datasets", "test")):
        datasets = config.get(dataset_key)
        if not isinstance(datasets, list) or len(datasets) != 1:
            raise ValueError(f"{dataset_key} must contain exactly one local dataset")
        dataset = datasets[0]
        if (
            not isinstance(dataset, Mapping)
            or dataset.get("type") != "chat_template"
            or not isinstance(dataset.get("path"), str)
            or not dataset["path"].strip()
        ):
            raise ValueError(
                f"{dataset_key} must use a local path with type: chat_template "
                f"({expected_partition})"
            )


def tokenize_sample(
    sample: Mapping[str, Any], tokenizer: Any, *, max_sequence_length: int
) -> list[int]:
    """Exercise the model's chat template; used for CPU tokenizer smoke tests."""
    validate_training_sample(sample)
    if not hasattr(tokenizer, "apply_chat_template"):
        raise TypeError("tokenizer must provide apply_chat_template")
    token_ids = tokenizer.apply_chat_template(
        sample["messages"],
        tokenize=True,
        add_generation_prompt=False,
    )
    if isinstance(token_ids, Mapping):
        token_ids = token_ids.get("input_ids")
    if hasattr(token_ids, "tolist"):
        token_ids = token_ids.tolist()
    if (
        isinstance(token_ids, list)
        and token_ids
        and isinstance(token_ids[0], list)
    ):
        if len(token_ids) != 1:
            raise ValueError("tokenizer returned a batch for one sample")
        token_ids = token_ids[0]
    if not isinstance(token_ids, list) or not all(
        isinstance(token_id, int) and not isinstance(token_id, bool) for token_id in token_ids
    ):
        raise ValueError("tokenizer must return a flat list of integer input_ids")
    if len(token_ids) > max_sequence_length:
        raise ValueError(
            f"tokenized sample has {len(token_ids)} tokens, exceeding "
            f"sequence length {max_sequence_length}"
        )
    return token_ids


def tokenize_dataset(
    samples: Sequence[Mapping[str, Any]], tokenizer: Any, *, max_sequence_length: int
) -> list[list[int]]:
    """Tokenize a small dataset using the model chat template without loading model weights."""
    return [
        tokenize_sample(sample, tokenizer, max_sequence_length=max_sequence_length)
        for sample in samples
    ]
