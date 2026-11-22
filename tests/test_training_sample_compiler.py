"""Contract tests for the fail-closed Brain training-sample compiler."""

from __future__ import annotations

import json

import pytest

from aios_work_system.training_data.compiler import (
    compile_episodes,
    validate_training_sample,
    write_compilation,
)


def _episode(episode_id: str = "ep-001", source_id: str = "tutorial-a") -> dict:
    return {
        "episode_id": episode_id,
        "source": {"source_id": source_id, "sha256": f"sha-{source_id}"},
        "task": {"goal": "Create a translation draft"},
        "state_before": {"page": "Content Translation dashboard", "selected_language": None},
        "available_capabilities": [
            {"capability_id": "open_translation", "description": "Open a translation draft"}
        ],
        "decision": {
            "rationale_summary": (
                "The target language has not been selected, so ask before opening a draft."
            ),
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


def _local_pass(episode: dict) -> dict:
    return {
        "episode_id": episode["episode_id"],
        "overall_status": "pass",
        "levels": {
            "extraction_fidelity": {"status": "pass"},
            "decision_validity": {"status": "pass"},
            "outcome_validity": {"status": "pass"},
        },
    }


def _pm_pass() -> dict:
    return {
        "status": "pass",
        "source_evidence_refs": ["video:00:02:10"],
        "proposed_record_evidence_refs": ["episode:decision.selected_next_step"],
    }


def _bundle(episode: dict | None = None) -> dict:
    selected = episode or _episode()
    return {
        "episode": selected,
        "local_verification": _local_pass(selected),
        "pm_verification": _pm_pass(),
    }


def test_held_episode_is_excluded_from_compilation():
    bundle = _bundle()
    bundle["local_verification"]["overall_status"] = "unknown"

    result = compile_episodes([bundle])

    assert result.train_samples == []
    assert result.test_samples == []
    assert result.exclusions == [{"episode_id": "ep-001", "reason": "local_verification_not_pass"}]


def test_future_result_leaked_into_input_is_rejected():
    bundle = _bundle()
    bundle["episode"]["state_before"]["future_result"] = {"status": "success"}

    result = compile_episodes([bundle])

    assert result.train_samples == []
    assert result.test_samples == []
    assert "future result leaked" in result.exclusions[0]["reason"]

    malformed = {
        "messages": [
            {"role": "system", "content": "system"},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "goal": "do it",
                        "current_state": {"outcome": {"status": "success"}},
                        "available_capabilities": [],
                        "last_execution_result": None,
                    }
                ),
            },
            {"role": "assistant", "content": '{"action":"ask_user","question":"What?"}'},
        ]
    }
    with pytest.raises(ValueError, match="future result leaked"):
        validate_training_sample(malformed)


def test_train_test_split_keeps_each_source_entirely_in_one_partition():
    bundles = [
        _bundle(_episode("ep-a1", "tutorial-a")),
        _bundle(_episode("ep-a2", "tutorial-a")),
        _bundle(_episode("ep-b1", "tutorial-b")),
        _bundle(_episode("ep-c1", "tutorial-c")),
        _bundle(_episode("ep-d1", "tutorial-d")),
    ]

    result = compile_episodes(bundles, seed=7)

    assignments: dict[str, set[str]] = {}
    for meta in result.train_meta + result.test_meta:
        source_group = meta["split_group_id"]
        assignments.setdefault(source_group, set()).add(meta["partition"])
    assert all(len(partitions) == 1 for partitions in assignments.values())
    assert {meta["partition"] for meta in result.train_meta + result.test_meta} == {"train", "test"}
    assert len(result.train_samples) + len(result.test_samples) == 5


def test_error_recovery_puts_hands_json_in_user_input_and_meta_only():
    episode = _episode()
    episode["decision"] = {
        **episode["decision"],
        "selected_next_step": {
            "action": "replan",
            "objective": "Recover from a partial navigation result",
            "reason": "The target page did not load fully.",
        },
    }
    episode["decision_points"] = [
        {
            "decision_point_id": "after-hands-1",
            "decision": episode["decision"],
            "goal": "Create a translation draft",
            "current_state": {"page": "Partially loaded translation dashboard"},
            "available_capabilities": episode["available_capabilities"],
            "last_execution_result": {
                "status": "partial_success",
                "completed": ["open browser tab"],
                "failed": ["load translation dashboard"],
            },
            "evidence_refs": ["ev-narration", "ev-owner-rule"],
        }
    ]

    result = compile_episodes([_bundle(episode)])
    samples = result.train_samples + result.test_samples
    metas = result.train_meta + result.test_meta

    assert len(samples) == 1
    user = json.loads(samples[0]["messages"][1]["content"])
    assert user["last_execution_result"]["status"] == "partial_success"
    assert metas[0]["sample_type"] == "ERROR_RECOVERY"


def test_evidence_axes_and_confidence_are_sidecar_only():
    result = compile_episodes([_bundle()])
    samples = result.train_samples + result.test_samples
    metas = result.train_meta + result.test_meta

    assert len(samples) == 1
    assert "instructor_explicit" not in _json_messages(samples[0])
    assert "user_provided" not in _json_messages(samples[0])
    assert metas[0]["evidence_tier"]["rationale_source"] == [
        "instructor_explicit",
        "not_applicable",
    ]
    assert metas[0]["evidence_tier"]["user_provided"] is True
    assert metas[0]["rationale_loss_weight"] == pytest.approx(0.9)


def test_conflicting_tutorial_decisions_are_preserved_as_separate_samples():
    first = _episode("ep-a", "tutorial-a")
    second = _episode("ep-b", "tutorial-b")
    second["decision"]["selected_next_step"] = {
        "action": "ask_user",
        "question": "Should I use the existing draft or create a new one?",
    }

    result = compile_episodes([_bundle(first), _bundle(second)])

    all_meta = result.train_meta + result.test_meta
    assert {meta["episode_id"] for meta in all_meta} == {"ep-a", "ep-b"}
    assert len(all_meta) == 2


def test_missing_required_context_cannot_be_compiled_as_execution():
    episode = _episode()
    episode["state_before"] = {}
    episode["decision"]["selected_next_step"] = {
        "action": "delegate",
        "capability_id": "open_translation",
    }

    result = compile_episodes([_bundle(episode)])

    assert result.train_samples == []
    assert "must be handled with ask_user" in result.exclusions[0]["reason"]


def test_dual_gate_and_trainable_quality_are_all_required():
    bundle = _bundle()
    bundle["pm_verification"] = {"status": "pass"}
    result = compile_episodes([bundle])
    assert result.train_samples == []
    assert result.test_samples == []
    assert "pm_independent_review_not_pass" in result.exclusions[0]["reason"]

    bundle = _bundle()
    bundle["episode"]["quality"]["trainable"] = False
    result = compile_episodes([bundle])
    assert result.train_samples == []
    assert result.test_samples == []
    assert result.exclusions[0]["reason"] == "episode_quality_not_trainable"


def test_write_compilation_keeps_training_meta_out_of_model_jsonl(tmp_path):
    result = compile_episodes([_bundle()])
    paths = write_compilation(result, tmp_path)

    model_records = [
        json.loads(line) for line in (tmp_path / "train.jsonl").read_text().splitlines()
    ]
    meta_records = [
        json.loads(line)
        for line in (tmp_path / "train.training_meta.jsonl").read_text().splitlines()
    ]
    assert len(model_records) == len(meta_records) == 1
    assert "training_meta" not in model_records[0]
    assert "evidence_tier" not in model_records[0]
    assert paths["manifest"].endswith("dataset_manifest.json")


def test_local_pipeline_pending_pm_admission_is_rechecked_after_pm_pass():
    bundle = _bundle()
    bundle["training_admission"] = {
        "status": "held_pending_pm_independent_verification",
        "eligible_for_dataset": False,
    }

    result = compile_episodes([bundle])

    assert len(result.train_samples) + len(result.test_samples) == 1


def test_held_pm_episode_is_excluded_from_compilation():
    bundle = _bundle()
    bundle["pm_verification"] = {
        "status": "held",
        "source_evidence_refs": ["video:00:02:10"],
        "proposed_record_evidence_refs": ["episode:decision.selected_next_step"],
    }

    result = compile_episodes([bundle])

    assert result.train_samples == []
    assert result.test_samples == []
    assert result.exclusions == [
        {
            "episode_id": "ep-001",
            "reason": "pm_independent_review_not_pass_or_missing_citations",
        }
    ]


def test_evidence_annotation_labels_are_rejected_from_user_and_assistant_messages():
    result = compile_episodes([_bundle()])
    sample = (result.train_samples + result.test_samples)[0]
    user_payload = json.loads(sample["messages"][1]["content"])
    user_payload["current_state"]["observation_channel"] = "direct_capture"
    sample["messages"][1]["content"] = json.dumps(user_payload)
    with pytest.raises(ValueError, match="evidence labels/metadata leaked into model input"):
        validate_training_sample(sample)

    result = compile_episodes([_bundle()])
    sample = (result.train_samples + result.test_samples)[0]
    target_payload = json.loads(sample["messages"][2]["content"])
    target_payload["rationale_source"] = "instructor_explicit"
    sample["messages"][2]["content"] = json.dumps(target_payload)
    with pytest.raises(ValueError, match="evidence labels/metadata leaked into assistant target"):
        validate_training_sample(sample)


def _json_messages(sample: dict) -> str:
    return " ".join(message["content"] for message in sample["messages"])
