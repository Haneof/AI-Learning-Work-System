"""Tests for metadata-aware Brain LoRA data preparation."""

from __future__ import annotations

import json

import pytest

from aios_work_system.training_data.compiler import compile_episodes, write_compilation
from aios_work_system.training_data.lora import (
    calculate_sample_weight,
    load_training_config,
    load_weighted_split,
    prepare_axolotl_datasets,
    tokenize_dataset,
    validate_lora_config,
    weighted_training_rows,
)


def _sample(action: str = "ask_user") -> dict:
    target = {"action": action}
    if action == "ask_user":
        target["question"] = "Which target language should I use?"
    return {
        "messages": [
            {"role": "system", "content": "Choose the next safe workflow action."},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "goal": "Create a translation draft",
                        "current_state": {"page": "dashboard"},
                        "available_capabilities": [],
                        "last_execution_result": None,
                    }
                ),
            },
            {"role": "assistant", "content": json.dumps(target)},
        ]
    }


def _meta(
    sample_id: str,
    *,
    partition: str = "train",
    observations: list[str] | None = None,
    rationales: list[str] | None = None,
    confidence: float = 0.9,
    rationale_loss_weight: float = 0.9,
) -> dict:
    return {
        "sample_id": sample_id,
        "partition": partition,
        "evidence_tier": {
            "observation_channel": observations or ["direct_capture"],
            "rationale_source": rationales or ["instructor_explicit"],
            "confidence": {"evidence-1": confidence},
            "user_provided": False,
            "user_provided_evidence_ids": [],
        },
        "rationale_loss_weight": rationale_loss_weight,
    }


def _write_split(
    directory, name: str, samples: list[dict], metadata: list[dict]
) -> tuple[str, str]:
    model_path = directory / f"{name}.jsonl"
    sidecar_path = directory / f"{name}.training_meta.jsonl"
    model_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in samples),
        encoding="utf-8",
    )
    sidecar_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in metadata),
        encoding="utf-8",
    )
    return str(model_path), str(sidecar_path)


def _episode(episode_id: str, source_id: str) -> dict:
    return {
        "episode_id": episode_id,
        "source": {"source_id": source_id, "sha256": f"sha-{source_id}"},
        "task": {"goal": "Create a translation draft"},
        "state_before": {"page": "Content Translation dashboard", "selected_language": None},
        "available_capabilities": [],
        "decision": {
            "rationale_summary": "The target language is missing, so ask before proceeding.",
            "evidence_refs": ["ev-narration", "ev-owner-rule"],
            "selected_next_step": {
                "action": "ask_user",
                "objective": "Obtain the target language",
                "question": "Which target language should I use?",
            },
        },
        "evidence": [
            {
                "evidence_id": "ev-narration",
                "observation_channel": "direct_capture",
                "rationale_source": "instructor_explicit",
                "confidence": 0.9,
                "labels": ["instructor_words"],
            },
            {
                "evidence_id": "ev-owner-rule",
                "observation_channel": "not_applicable",
                "rationale_source": "not_applicable",
                "confidence": 1.0,
                "labels": ["user_provided"],
            },
        ],
        "review": {"status": "approved", "approved_for_training": True},
        "quality": {
            "annotation_status": "human_reviewed",
            "trainable": True,
            "exclusion_reasons": [],
        },
    }


def _bundle(episode_id: str, source_id: str) -> dict:
    episode = _episode(episode_id, source_id)
    return {
        "episode": episode,
        "local_verification": {
            "episode_id": episode_id,
            "overall_status": "pass",
            "levels": {
                "extraction_fidelity": {"status": "pass"},
                "decision_validity": {"status": "pass"},
                "outcome_validity": {"status": "pass"},
            },
        },
        "pm_verification": {
            "status": "pass",
            "source_evidence_refs": ["video:00:02:10"],
            "proposed_record_evidence_refs": ["episode:decision.selected_next_step"],
        },
    }


def test_loader_joins_model_rows_to_matching_sidecars_and_uses_evidence_weights(tmp_path):
    model_path, sidecar_path = _write_split(
        tmp_path,
        "train",
        [_sample()],
        [
            _meta(
                "sample-1",
                observations=["direct_capture", "not_applicable"],
                rationales=["instructor_explicit", "not_applicable"],
            )
        ],
    )

    loaded = load_weighted_split(
        model_path,
        sidecar_path,
        expected_partition="train",
    )

    assert len(loaded) == 1
    assert loaded[0].metadata["sample_id"] == "sample-1"
    assert 0.05 <= loaded[0].weight <= 1.0
    assert loaded[0].weight == calculate_sample_weight(loaded[0].metadata)


def test_evidence_tier_and_rationale_loss_weight_change_sample_priority():
    strong = _meta(
        "strong",
        observations=["direct_capture"],
        rationales=["instructor_explicit"],
        confidence=1.0,
        rationale_loss_weight=1.0,
    )
    weak = _meta(
        "weak",
        observations=["unknown"],
        rationales=["unknown"],
        confidence=0.1,
        rationale_loss_weight=0.1,
    )

    assert calculate_sample_weight(strong) > calculate_sample_weight(weak)


def test_sidecar_marked_excluded_is_refused(tmp_path):
    excluded = _meta("blocked")
    excluded["excluded"] = True
    model_path, sidecar_path = _write_split(
        tmp_path,
        "train",
        [_sample()],
        [excluded],
    )

    with pytest.raises(ValueError, match="marked excluded"):
        load_weighted_split(model_path, sidecar_path, expected_partition="train")


def test_sidecar_eligibility_false_and_excluded_status_are_refused(tmp_path):
    for marker in ({"eligible_for_training": False}, {"status": "held"}):
        metadata = _meta("blocked")
        metadata.update(marker)
        model_path, sidecar_path = _write_split(
            tmp_path,
            "train",
            [_sample()],
            [metadata],
        )
        with pytest.raises(ValueError, match="excluded|not eligible"):
            load_weighted_split(model_path, sidecar_path, expected_partition="train")


def test_missing_or_misaligned_sidecar_is_not_silently_accepted(tmp_path):
    model_path, sidecar_path = _write_split(
        tmp_path,
        "train",
        [_sample(), _sample()],
        [_meta("sample-1")],
    )

    with pytest.raises(ValueError, match="row-count mismatch"):
        load_weighted_split(model_path, sidecar_path, expected_partition="train")


def test_weighted_materialization_keeps_every_sample_and_repeats_high_weight(tmp_path):
    model_path, sidecar_path = _write_split(
        tmp_path,
        "train",
        [_sample(), _sample()],
        [
            _meta(
            "low",
            observations=["unknown"],
            rationales=["unknown"],
            confidence=0.1,
            rationale_loss_weight=0.1,
        ),
            _meta(
            "high",
            observations=["direct_capture"],
            rationales=["instructor_explicit"],
            confidence=1.0,
            rationale_loss_weight=1.0,
        ),
        ],
    )
    loaded = load_weighted_split(model_path, sidecar_path, expected_partition="train")

    rows, repeats = weighted_training_rows(loaded, max_repeat_factor=3)

    assert repeats == {"low": 1, "high": 3}
    assert len(rows) == 4
    assert all(row == _sample() for row in rows)


def test_config_validation_loads_t4_full_weight_fp16_profile():
    config = load_training_config("configs/brain_lora_t4.yml")

    validate_lora_config(config, gpu_profile="t4")

    assert config["base_model"] == "DreamFast/qwen3-4b-heretic"
    assert config["adapter"] == "lora"
    assert config["fp16"] is True
    assert config["bf16"] is False
    assert config["load_in_4bit"] is False
    assert config["lora_r"] == 16
    assert config["lora_alpha"] == 32
    assert config["sequence_len"] == 512
    assert config["micro_batch_size"] == 1
    assert config["activation_checkpointing"] is True


def test_t4_config_rejects_bf16_and_quantized_base_model():
    config = load_training_config("configs/brain_lora_t4.yml")
    config["bf16"] = True

    with pytest.raises(ValueError, match="BF16 is unsupported"):
        validate_lora_config(config, gpu_profile="t4")

    config["bf16"] = False
    config["load_in_4bit"] = True
    with pytest.raises(ValueError, match="quantized loading is forbidden"):
        validate_lora_config(config, gpu_profile="t4")


class _SyntheticTokenizer:
    """A deterministic tokenizer stand-in; no model or remote tokenizer is downloaded."""

    def apply_chat_template(self, messages, *, tokenize, add_generation_prompt):
        assert tokenize is True
        assert add_generation_prompt is False
        rendered = " ".join(message["content"] for message in messages)
        return list(range(max(1, len(rendered) // 8)))


def test_pr40_style_synthetic_fixture_pipeline_tokenizes_train_and_test_without_gpu(tmp_path):
    # These are synthetic fixtures with the same approved DecisionEpisode shape
    # used by the PR #40 compiler contract tests; no real tutorial data is present.
    compilation = compile_episodes(
        [
            _bundle("synthetic-episode-a", "synthetic-tutorial-a"),
            _bundle("synthetic-episode-b", "synthetic-tutorial-b"),
        ],
        seed=42,
        train_fraction=0.5,
    )
    assert len(compilation.train_samples) == 1
    assert len(compilation.test_samples) == 1

    raw_dir = tmp_path / "compiled"
    paths = write_compilation(compilation, raw_dir)
    prepared = prepare_axolotl_datasets(
        train_jsonl=paths["train"],
        train_meta_jsonl=paths["train_meta"],
        test_jsonl=paths["test"],
        test_meta_jsonl=paths["test_meta"],
        output_dir=tmp_path / "axolotl",
        max_repeat_factor=3,
    )


    train_rows = [
        json.loads(line)
        for line in (tmp_path / "axolotl" / "train.weighted.jsonl").read_text().splitlines()
    ]
    test_rows = [
        json.loads(line)
        for line in (tmp_path / "axolotl" / "test.jsonl").read_text().splitlines()
    ]
    tokenizer = _SyntheticTokenizer()
    train_tokens = tokenize_dataset(train_rows, tokenizer, max_sequence_length=512)
    test_tokens = tokenize_dataset(test_rows, tokenizer, max_sequence_length=512)

    assert prepared["train_original_count"] == 1
    assert prepared["test_count"] == 1
    assert train_tokens and test_tokens
    assert all(tokens and len(tokens) <= 512 for tokens in train_tokens + test_tokens)
    manifest = json.loads((tmp_path / "axolotl" / "weight_manifest.json").read_text())
    assert manifest["sidecar_in_model_messages"] is False
