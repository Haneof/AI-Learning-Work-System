"""Acceptance and mechanics tests for the Brain/Hands closed loop."""

from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from aios_work_system.brain_hands import (
    BrainContext,
    BrainDecision,
    BrainHandsLoop,
    LoopConfig,
    OperationDelegation,
    ProtocolError,
    SimulatedHands,
    SimulatedOutcome,
    WorkflowBrain,
    shop_listing_handlers,
)

WORKFLOW_PATH = (
    Path(__file__).parent.parent
    / "contracts"
    / "examples"
    / "shop-list-product.workflow.json"
)
PROTOCOL_SCHEMA_PATH = (
    Path(__file__).parent.parent / "contracts" / "brain-hands-protocol.schema.json"
)


def _workflow() -> dict[str, Any]:
    return json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))


def _run(hands: SimulatedHands, *, brain: Any | None = None, max_decisions: int = 20):
    workflow = _workflow()
    loop = BrainHandsLoop(
        workflow,
        brain or WorkflowBrain(workflow),
        hands,
        LoopConfig(max_decisions=max_decisions),
    )
    return asyncio.run(
        loop.run({"product_title": "Portable Pet Water Fountain", "price": 39.99})
    )


def test_brain_only_simulated_hands_reaches_business_goal() -> None:
    workflow = _workflow()
    hands = SimulatedHands(workflow["initial_state"], shop_listing_handlers())

    report = _run(hands)

    assert report.status == "succeeded"
    assert report.goal_satisfied is True
    assert report.final_state["title.status"] == "verified"
    assert report.final_state["price.status"] == "set"
    assert report.final_state["title.value"] == "Portable Pet Water Fountain"
    assert report.final_state["price.amount"] == 39.99
    assert [call.task_id for call in hands.calls] == [
        "enter_title",
        "verify_title",
        "set_price",
    ]
    assert report.operations == 3
    assert report.decisions == 4  # Three delegations, then a goal-checked finish decision.


@pytest.mark.parametrize("returned_status", ["failed", "partially_succeeded"])
def test_failed_or_partial_result_replans_from_fresh_state(returned_status: str) -> None:
    workflow = _workflow()
    handlers = shop_listing_handlers()
    enter_title = handlers["shop.listing.enter_title"]

    def apply_title_but_report_incomplete(state, arguments, delegation):
        enter_title(state, arguments, delegation)
        return SimulatedOutcome(
            status=returned_status,
            result_summary="Title write had a non-success return despite a visible state change.",
        )

    handlers["shop.listing.enter_title"] = apply_title_but_report_incomplete
    hands = SimulatedHands(workflow["initial_state"], handlers)

    report = _run(hands)

    assert report.status == "succeeded"
    assert report.history[0]["execution_result"]["status"] == returned_status
    assert report.history[0]["verified_state_after"]["title.status"] == "saved"
    # The Brain sees the saved title and recovers by verifying it; it does not
    # blindly repeat the write or skip directly to price configuration.
    assert hands.calls[1].task_id == "verify_title"
    assert hands.calls[1].preconditions[0]["path"] == "title.status"
    assert [call.task_id for call in hands.calls] == [
        "enter_title",
        "verify_title",
        "set_price",
    ]


def test_brain_receives_each_new_observation_and_the_previous_hands_result() -> None:
    workflow = _workflow()
    hands = SimulatedHands(workflow["initial_state"], shop_listing_handlers())

    class RecordingBrain:
        def __init__(self) -> None:
            self.delegate = WorkflowBrain(workflow)
            self.contexts: list[BrainContext] = []

        def decide(self, context: BrainContext) -> BrainDecision:
            self.contexts.append(copy.deepcopy(context))
            return self.delegate.decide(context)

    brain = RecordingBrain()
    report = _run(hands, brain=brain)

    assert report.goal_satisfied is True
    assert len(brain.contexts) == 4
    assert brain.contexts[0].current_state["title.status"] == "missing"
    assert brain.contexts[1].current_state["title.status"] == "saved"
    assert brain.contexts[1].last_execution_result["status"] == "succeeded"
    assert brain.contexts[2].current_state["title.status"] == "verified"
    assert brain.contexts[2].last_execution_result["task_id"] == "verify_title"
    assert brain.contexts[3].current_state["price.status"] == "set"
    assert brain.contexts[3].last_execution_result["task_id"] == "set_price"


def test_non_idempotent_partial_result_is_not_blindly_retried() -> None:
    workflow = _workflow()
    handlers = shop_listing_handlers()
    calls = 0

    def uncertain_price(state, arguments, delegation):
        nonlocal calls
        calls += 1
        return SimulatedOutcome(
            status="partially_succeeded",
            result_summary="Price operation outcome is uncertain.",
        )

    handlers["shop.listing.set_price"] = uncertain_price
    hands = SimulatedHands(workflow["initial_state"], handlers)

    report = _run(hands)

    assert report.status == "failed"
    assert "non-idempotent" in (report.error or "")
    assert calls == 1
    assert [call.task_id for call in hands.calls].count("set_price") == 1
    assert report.final_state["price.status"] == "not_set"


def test_succeeded_status_without_evidence_and_fresh_postconditions_is_demoted() -> None:
    workflow = _workflow()

    class BareDoneHands(SimulatedHands):
        async def execute(self, delegation: OperationDelegation):
            self.calls.append(delegation)
            return {
                "protocol_version": "0.1",
                "message_type": "operation_result",
                "call_id": delegation.call_id,
                "task_id": delegation.task_id,
                "status": "succeeded",
                "result_summary": "done",
                "observed_state": dict(await self.observe()),
                "postcondition_results": [],
                "actions_summary": [{"action": "opaque", "status": "succeeded"}],
                "error": None,
                "evidence_refs": [],
                "completed_at": "2026-11-22T00:00:00Z",
            }

    hands = BareDoneHands(workflow["initial_state"], shop_listing_handlers())
    report = _run(hands, max_decisions=1)

    assert report.status == "step_limit"
    assert report.goal_satisfied is False
    first_result = report.history[0]["execution_result"]
    assert first_result["status"] == "partially_succeeded"
    assert first_result["error"]["code"] == "postcondition_verification_failed"
    assert report.final_state["title.status"] == "missing"


def test_brain_cannot_finish_when_business_goal_is_not_satisfied() -> None:
    workflow = _workflow()
    hands = SimulatedHands(workflow["initial_state"], shop_listing_handlers())

    class PrematureFinishBrain:
        def decide(self, _context: BrainContext) -> BrainDecision:
            return BrainDecision("finish", "The GUI model said done.")

    report = _run(hands, brain=PrematureFinishBrain())

    assert report.status == "failed"
    assert report.goal_satisfied is False
    assert "success conditions were unmet" in (report.error or "")
    assert hands.calls == []


def test_delegation_is_high_level_and_rejects_mouse_coordinates() -> None:
    workflow = _workflow()
    brain = WorkflowBrain(workflow)
    context = BrainContext(
        workflow=workflow,
        current_state=workflow["initial_state"],
        workflow_inputs={"product_title": "Example"},
    )
    decision = brain.decide(context)

    assert decision.action == "delegate"
    assert decision.delegation is not None
    message = decision.delegation.to_dict()
    assert message["message_type"] == "operation_delegation"
    assert message["objective"]["capability_id"] == "shop.listing.enter_title"
    assert "click" not in message
    assert "mouse" not in json.dumps(message).lower()
    assert "coordinates" not in json.dumps(message).lower()
    assert "selector" not in json.dumps(message).lower()
    assert OperationDelegation.from_mapping(message) == decision.delegation

    malicious = copy.deepcopy(message)
    malicious["objective"]["arguments"]["mouse_coordinates"] = {"x": 20, "y": 40}
    with pytest.raises(ProtocolError, match="coordinates"):
        OperationDelegation.from_mapping(malicious)


def test_delegation_and_execution_result_match_brain_hands_json_schema() -> None:
    workflow = _workflow()
    schema = json.loads(PROTOCOL_SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    brain = WorkflowBrain(workflow)
    decision = brain.decide(
        BrainContext(
            workflow=workflow,
            current_state=workflow["initial_state"],
            workflow_inputs={"product_title": "Example"},
        )
    )
    assert decision.delegation is not None
    validator.validate(decision.delegation.to_dict())

    hands = SimulatedHands(workflow["initial_state"], shop_listing_handlers())
    result = asyncio.run(hands.execute(decision.delegation))
    validator.validate(result.to_dict())


def test_high_risk_capability_cannot_be_delegated_without_approval() -> None:
    workflow = _workflow()
    high_risk = copy.deepcopy(workflow)
    task = next(item for item in high_risk["tasks"] if item["task_id"] == "enter_title")
    capability = next(
        item
        for item in high_risk["capabilities"]
        if item["capability_id"] == task["capability_id"]
    )
    capability["risk_level"] = "high"
    brain = WorkflowBrain(high_risk)
    hands = SimulatedHands(high_risk["initial_state"], shop_listing_handlers())

    report = asyncio.run(
        BrainHandsLoop(high_risk, brain, hands).run({"product_title": "Example", "price": 5})
    )

    assert report.status == "blocked"
    assert "human approval" in (report.error or "")
    assert hands.calls == []


def test_workflow_state_condition_supports_flat_and_nested_state_paths() -> None:
    from aios_work_system.brain_hands.engine import condition_matches

    condition = {"path": "title.status", "operator": "equals", "value": "verified"}
    assert condition_matches({"title.status": "verified"}, condition)
    assert condition_matches({"title": {"status": "verified"}}, condition)
    assert not condition_matches({"title": {"status": "saved"}}, condition)
