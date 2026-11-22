"""Tests for the workflow decision data contracts."""

import json
from pathlib import Path

from contracts.validate import (
    validate_episode,
    validate_protocol,
    validate_training_jsonl,
    validate_workflow,
)

CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"
EXAMPLES = CONTRACTS / "examples"


def load_example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def test_shop_decision_episode_example_is_structurally_and_semantically_valid():
    episode = load_example("shop-list-product.episode.json")

    assert validate_episode(episode) == []
    assert episode["review"]["approved_for_training"] is False
    assert episode["quality"]["trainable"] is False
    assert episode["decision"]["decision_basis"] == ["user_provided"]


def test_episode_rejects_unresolved_evidence_reference():
    episode = load_example("shop-list-product.episode.json")
    episode["decision"]["evidence_refs"] = ["missing-evidence"]

    errors = validate_episode(episode)

    assert any("unresolved evidence reference" in error for error in errors)


def test_episode_requires_evidence_or_explicit_unknown_for_decision():
    episode = load_example("shop-list-product.episode.json")
    episode["decision"]["evidence_refs"] = []
    episode["decision"]["decision_basis"] = ["workflow_rule"]

    errors = validate_episode(episode)

    assert any("explicitly include 'unknown'" in error for error in errors)


def test_success_requires_passed_postcondition_and_direct_verification_evidence():
    episode = load_example("shop-list-product.episode.json")
    episode["outcome"]["status"] = "success"
    episode["outcome"]["postcondition_checks"] = []

    errors = validate_episode(episode)

    assert any("passed postcondition" in error for error in errors)


def test_training_gate_requires_both_review_and_quality_approval():
    episode = load_example("shop-list-product.episode.json")
    episode["quality"]["trainable"] = True
    episode["quality"]["annotation_status"] = "human_reviewed"

    errors = validate_episode(episode)

    assert any("review.status=approved" in error for error in errors)


def test_auto_extracted_episode_cannot_be_trainable():
    episode = load_example("shop-list-product.episode.json")
    episode["review"]["status"] = "approved"
    episode["review"]["approved_for_training"] = True
    episode["quality"]["annotation_status"] = "auto_extracted"
    episode["quality"]["trainable"] = True
    episode["quality"]["exclusion_reasons"] = []

    errors = validate_episode(episode)

    assert any("human_reviewed or gold" in error for error in errors)


def test_shop_workflow_example_passes():
    workflow = load_example("shop-list-product.workflow.json")
    episode = load_example("shop-list-product.episode.json")
    evidence_ids = {item["evidence_id"] for item in episode["evidence"]}

    assert validate_workflow(workflow, evidence_ids) == []


def test_workflow_rejects_hard_dependency_cycle():
    workflow = load_example("shop-list-product.workflow.json")
    workflow["edges"].append(
        {
            "from_task_id": "set_price",
            "to_task_id": "enter_title",
            "relation": "hard_dependency",
            "rationale": "Intentional cycle for validator test.",
        }
    )

    episode = load_example("shop-list-product.episode.json")
    evidence_ids = {item["evidence_id"] for item in episode["evidence"]}
    errors = validate_workflow(workflow, evidence_ids)

    assert any("contain a cycle" in error for error in errors)


def test_workflow_rejects_primitive_task_without_registered_capability():
    workflow = load_example("shop-list-product.workflow.json")
    workflow["capabilities"] = [
        item
        for item in workflow["capabilities"]
        if item["capability_id"] != "shop.listing.set_price"
    ]

    episode = load_example("shop-list-product.episode.json")
    evidence_ids = {item["evidence_id"] for item in episode["evidence"]}
    errors = validate_workflow(workflow, evidence_ids)

    assert any("unregistered capability" in error for error in errors)


def test_workflow_rejects_invariant_precondition_bypass():
    workflow = load_example("shop-list-product.workflow.json")
    set_price = next(task for task in workflow["tasks"] if task["task_id"] == "set_price")
    set_price["preconditions"] = []

    episode = load_example("shop-list-product.episode.json")
    evidence_ids = {item["evidence_id"] for item in episode["evidence"]}
    errors = validate_workflow(workflow, evidence_ids)

    assert any("invariant" in error and "could be bypassed" in error for error in errors)


def delegation_message() -> dict:
    return {
        "protocol_version": "0.1",
        "message_type": "operation_delegation",
        "call_id": "call-001",
        "task_id": "task-001",
        "workflow_ref": {
            "workflow_id": "shop.list_new_product",
            "version": "0.1",
            "node_id": "enter_title",
        },
        "objective": {
            "description": "Enter the supplied title.",
            "capability_id": "shop.listing.enter_title",
            "arguments": {"title_text": "Example title"},
        },
        "preconditions": [],
        "constraints": {
            "must_not": ["Do not set the price."],
            "allowed_scope": ["product.title"],
        },
        "expected_postconditions": [
            {
                "condition_id": "title-saved",
                "path": "title.status",
                "operator": "equals",
                "value": "saved",
            }
        ],
        "observation_requirements": ["Return the saved title."],
        "safety": {
            "risk_level": "low",
            "requires_human_approval": False,
        },
        "idempotency_key": "task-001-enter-title",
    }


def test_protocol_rejects_unregistered_brain_capability():
    message = delegation_message()

    errors = validate_protocol(message, {"shop.listing.verify_title"})

    assert any("unregistered capability_id" in error for error in errors)


def test_protocol_requires_registry_for_delegation():
    errors = validate_protocol(delegation_message())

    assert any("capability registry is required" in error for error in errors)


def test_protocol_accepts_registered_brain_capability():
    errors = validate_protocol(
        delegation_message(),
        {"shop.listing.enter_title", "shop.listing.verify_title"},
    )

    assert errors == []


def test_successful_hands_result_requires_postcondition_evidence():
    message = {
        "protocol_version": "0.1",
        "message_type": "operation_result",
        "call_id": "call-001",
        "task_id": "task-001",
        "status": "succeeded",
        "result_summary": "Completed.",
        "observed_state": {"title": {"status": "saved"}},
        "postcondition_results": [
            {
                "condition_id": "title-saved",
                "result": "passed",
                "evidence_refs": [],
            }
        ],
        "actions_summary": [],
        "error": None,
        "evidence_refs": [],
        "completed_at": "2026-11-21T20:30:00Z",
    }

    errors = validate_protocol(message)

    assert any("requires a passed postcondition" in error for error in errors)


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def training_record(
    example_id: str, sample_type: str, last_result: dict | None
) -> dict:
    user_payload = {
        "goal": "List a new product",
        "current_state": {"title.status": "missing", "price.status": "not_set"},
        "last_execution_result": last_result,
    }
    target = {
        "decision_action": "ask_user" if sample_type == "normal_decision" else "replan",
        "rationale_summary": "The next step follows from the current state.",
    }
    return {
        "training_example_id": example_id,
        "messages": [
            {
                "role": "system",
                "content": "Return a JSON decision.",
            },
            {
                "role": "user",
                "content": json.dumps(user_payload),
            },
            {
                "role": "assistant",
                "content": json.dumps(target),
            },
        ],
    }


def sidecar_record(example_id: str, sample_type: str) -> dict:
    return {
        "training_example_id": example_id,
        "sample_type": sample_type,
        "episode_refs": ["shop-list-product-title-first-001"],
        "evidence_tier": "user_provided_rule",
        "rationale_loss_weight": None,
    }


def test_training_jsonl_accepts_normal_and_error_recovery_samples(tmp_path: Path):
    training_path = tmp_path / "train.jsonl"
    sidecar_path = tmp_path / "training_meta.jsonl"
    write_jsonl(
        training_path,
        [
            training_record("normal-001", "normal_decision", None),
            training_record(
                "recovery-001",
                "error_recovery",
                {"status": "failed", "error": {"category": "validation_error"}},
            ),
        ],
    )
    write_jsonl(
        sidecar_path,
        [
            sidecar_record("normal-001", "normal_decision"),
            sidecar_record("recovery-001", "error_recovery"),
        ],
    )

    assert validate_training_jsonl(training_path, sidecar_path) == []


def test_training_rejects_execution_outcome_leakage(tmp_path: Path):
    training_path = tmp_path / "train.jsonl"
    sidecar_path = tmp_path / "training_meta.jsonl"
    record = training_record("normal-001", "normal_decision", None)
    assistant = json.loads(record["messages"][2]["content"])
    assistant["execution_outcome"] = {"status": "success"}
    record["messages"][2]["content"] = json.dumps(assistant)
    write_jsonl(training_path, [record])
    write_jsonl(sidecar_path, [sidecar_record("normal-001", "normal_decision")])

    errors = validate_training_jsonl(training_path, sidecar_path)

    assert any("leaks execution result" in error for error in errors)


def test_training_recovery_requires_hands_result_in_user_input(tmp_path: Path):
    training_path = tmp_path / "train.jsonl"
    sidecar_path = tmp_path / "training_meta.jsonl"
    write_jsonl(
        training_path,
        [training_record("recovery-001", "error_recovery", None)],
    )
    write_jsonl(
        sidecar_path,
        [sidecar_record("recovery-001", "error_recovery")],
    )

    errors = validate_training_jsonl(training_path, sidecar_path)

    assert any("requires user.last_execution_result" in error for error in errors)


def test_training_meta_must_not_be_embedded_in_model_messages(tmp_path: Path):
    training_path = tmp_path / "train.jsonl"
    sidecar_path = tmp_path / "training_meta.jsonl"
    record = training_record("normal-001", "normal_decision", None)
    record["training_meta"] = sidecar_record("normal-001", "normal_decision")
    write_jsonl(training_path, [record])
    write_jsonl(sidecar_path, [sidecar_record("normal-001", "normal_decision")])

    errors = validate_training_jsonl(training_path, sidecar_path)

    assert any("training_meta must be stored in sidecar" in error for error in errors)
