"""A deterministic Hands simulator for business-state and recovery tests."""

from __future__ import annotations

import copy
import inspect
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from aios_work_system.brain_hands.engine import condition_matches, get_state_path, set_state_path
from aios_work_system.brain_hands.interfaces import ExecutionResult, OperationDelegation


@dataclass(frozen=True, slots=True)
class SimulatedOutcome:
    """Optional result returned by one simulated capability handler."""

    status: str = "succeeded"
    result_summary: str = "Simulated business operation applied."
    error: Mapping[str, Any] | None = None


OperationHandler = Callable[
    [dict[str, Any], Mapping[str, Any], OperationDelegation],
    SimulatedOutcome | None,
]


class SimulatedHands:
    """Apply named business capabilities to a simulated application state."""

    def __init__(
        self,
        initial_state: Mapping[str, Any],
        handlers: Mapping[str, OperationHandler] | None = None,
    ) -> None:
        self._state = copy.deepcopy(dict(initial_state))
        self.handlers = dict(handlers or {})
        self.calls: list[OperationDelegation] = []

    async def observe(self) -> Mapping[str, Any]:
        """Return an isolated copy of the latest simulated application state."""
        return copy.deepcopy(self._state)

    async def execute(self, delegation: OperationDelegation) -> ExecutionResult:
        """Run one registered capability and verify its postconditions against state."""
        self.calls.append(delegation)
        for condition in delegation.preconditions:
            if not condition_matches(self._state, condition):
                return self._result(
                    delegation,
                    status="blocked",
                    summary=f"Precondition failed: {condition.get('path')}",
                    error={
                        "category": "precondition",
                        "code": "precondition_failed",
                        "message": f"Precondition failed: {condition.get('path')}",
                    },
                )

        handler = self.handlers.get(delegation.capability_id)
        if handler is None:
            return self._result(
                delegation,
                status="failed",
                summary=f"No simulated handler for {delegation.capability_id}.",
                error={
                    "category": "capability",
                    "code": "handler_not_registered",
                    "message": f"No handler for {delegation.capability_id}",
                },
            )

        try:
            outcome = handler(self._state, delegation.arguments, delegation)
            if inspect.isawaitable(outcome):
                outcome = await outcome
            if outcome is None:
                outcome = SimulatedOutcome()
            if not isinstance(outcome, SimulatedOutcome):
                raise TypeError("simulated handlers must return SimulatedOutcome or None")
        except Exception as exc:
            outcome = SimulatedOutcome(
                status="failed",
                result_summary="Simulated handler raised an exception.",
                error={
                    "category": "simulated_handler",
                    "code": type(exc).__name__,
                    "message": str(exc),
                },
            )

        results: list[dict[str, Any]] = []
        evidence_refs: list[str] = []
        for condition in delegation.expected_postconditions:
            passed = condition_matches(self._state, condition)
            evidence_ref = (
                f"simulated://{delegation.call_id}/postconditions/"
                f"{condition.get('condition_id', 'unknown')}"
            )
            evidence_refs.append(evidence_ref)
            results.append(
                {
                    "condition_id": condition["condition_id"],
                    "result": "passed" if passed else "failed",
                    "observed_value": self._observed_value(condition),
                    "evidence_refs": [evidence_ref],
                }
            )

        status = outcome.status
        if status == "succeeded" and not all(item["result"] == "passed" for item in results):
            status = (
                "partially_succeeded"
                if any(item["result"] == "passed" for item in results)
                else "failed"
            )
        action_status = (
            "succeeded"
            if status == "succeeded"
            else "partially_succeeded"
            if status == "partially_succeeded"
            else "failed"
        )
        return ExecutionResult(
            call_id=delegation.call_id,
            task_id=delegation.task_id,
            status=status,  # type: ignore[arg-type]
            result_summary=outcome.result_summary,
            observed_state=copy.deepcopy(self._state),
            postcondition_results=tuple(results),
            actions_summary=(
                {
                    "action": delegation.capability_id,
                    "status": action_status,
                    "detail": "Simulated business capability; no GUI clicks were generated.",
                },
            ),
            error=outcome.error,
            evidence_refs=tuple(evidence_refs),
        )

    def _result(
        self,
        delegation: OperationDelegation,
        *,
        status: str,
        summary: str,
        error: Mapping[str, Any] | None = None,
    ) -> ExecutionResult:
        results = []
        evidence_refs = []
        for condition in delegation.expected_postconditions:
            evidence_ref = (
                f"simulated://{delegation.call_id}/postconditions/{condition['condition_id']}"
            )
            evidence_refs.append(evidence_ref)
            results.append(
                {
                    "condition_id": condition["condition_id"],
                    "result": "not_checked",
                    "observed_value": self._observed_value(condition),
                    "evidence_refs": [evidence_ref],
                }
            )
        return ExecutionResult(
            call_id=delegation.call_id,
            task_id=delegation.task_id,
            status=status,  # type: ignore[arg-type]
            result_summary=summary,
            observed_state=copy.deepcopy(self._state),
            postcondition_results=tuple(results),
            actions_summary=(
                {"action": delegation.capability_id, "status": "failed", "detail": summary},
            ),
            error=error,
            evidence_refs=tuple(evidence_refs),
        )

    def _observed_value(self, condition: Mapping[str, Any]) -> Any:
        value = get_state_path(self._state, str(condition.get("path", "")))
        return None if value.__class__ is object else value


def shop_listing_handlers() -> dict[str, OperationHandler]:
    """Handlers for the repository's shop-list-product WorkflowDefinition example."""

    def enter_title(
        state: dict[str, Any], arguments: Mapping[str, Any], _delegation: OperationDelegation
    ) -> SimulatedOutcome:
        title = arguments.get("product_title", arguments.get("title"))
        if not isinstance(title, str) or not title.strip():
            return SimulatedOutcome(
                status="failed",
                result_summary="No product_title was supplied.",
                error={
                    "category": "input",
                    "code": "missing_product_title",
                    "message": "product_title is required",
                },
            )
        set_state_path(state, "title.value", title)
        set_state_path(state, "title.status", "saved")
        return SimulatedOutcome(result_summary="Product title entered and saved.")

    def verify_title(
        state: dict[str, Any], arguments: Mapping[str, Any], _delegation: OperationDelegation
    ) -> SimulatedOutcome:
        actual = state.get("title.value")
        expected = arguments.get("product_title", arguments.get("title"))
        if not isinstance(actual, str) or (expected is not None and actual != expected):
            return SimulatedOutcome(
                status="failed",
                result_summary="Saved title did not match the supplied title.",
                error={
                    "category": "verification",
                    "code": "title_mismatch",
                    "message": "Saved title did not match the supplied title",
                },
            )
        set_state_path(state, "title.status", "verified")
        return SimulatedOutcome(result_summary="Product title independently verified.")

    def set_price(
        state: dict[str, Any], arguments: Mapping[str, Any], _delegation: OperationDelegation
    ) -> SimulatedOutcome:
        if state.get("title.status") != "verified":
            return SimulatedOutcome(
                status="blocked",
                result_summary="Price cannot be set before title verification.",
                error={
                    "category": "invariant",
                    "code": "title_not_verified",
                    "message": "title.status must equal verified",
                },
            )
        price = arguments.get("price")
        if price is None:
            return SimulatedOutcome(
                status="failed",
                result_summary="No price was supplied.",
                error={
                    "category": "input",
                    "code": "missing_price",
                    "message": "price is required",
                },
            )
        set_state_path(state, "price.amount", price)
        set_state_path(state, "price.status", "set")
        return SimulatedOutcome(result_summary="Product price set after title verification.")

    return {
        "shop.listing.enter_title": enter_title,
        "shop.listing.verify_title": verify_title,
        "shop.listing.set_price": set_price,
    }
