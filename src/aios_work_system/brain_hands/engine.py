"""Workflow-driven Brain stub and evidence-gated Brain/Hands runtime loop."""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from aios_work_system.brain_hands.interfaces import (
    Brain,
    BrainContext,
    BrainDecision,
    ExecutionResult,
    OperationDelegation,
    ProtocolError,
)

_MISSING = object()
_CONDITION_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+)\s*(==|!=|>=|<=|>|<)\s*(.*?)\s*$")
_OPERATOR_MAP = {
    "==": "equals",
    "!=": "not_equals",
    ">": "greater_than",
    ">=": "greater_than_or_equal",
    "<": "less_than",
    "<=": "less_than_or_equal",
}


def get_state_path(state: Mapping[str, Any], path: str) -> Any:
    """Read a dotted path, supporting both nested maps and dotted-key workflow examples."""
    if path in state:
        return state[path]
    value: Any = state
    for part in path.split("."):
        if not isinstance(value, Mapping) or part not in value:
            return _MISSING
        value = value[part]
    return value


def set_state_path(state: dict[str, Any], path: str, value: Any) -> None:
    """Set a dotted state path while preserving an existing flat dotted-key convention."""
    if path in state:
        state[path] = value
        return
    parts = path.split(".")
    current = state
    for part in parts[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    current[parts[-1]] = value


def parse_condition(expression: str, *, condition_id: str) -> dict[str, Any]:
    """Compile the simple workflow expression form into the protocol condition shape."""
    match = _CONDITION_RE.match(expression)
    if match is None:
        raise ValueError(f"unsupported workflow condition expression: {expression!r}")
    path, token, raw_value = match.groups()
    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError:
        value = raw_value.strip().strip("'\"")
    return {
        "condition_id": condition_id,
        "path": path,
        "operator": _OPERATOR_MAP[token],
        "value": value,
    }


def condition_matches(state: Mapping[str, Any], condition: Mapping[str, Any]) -> bool:
    """Evaluate a v0.1 workflow or BrainHands condition against observed state."""
    actual = get_state_path(state, str(condition.get("path", "")))
    operator = condition.get("operator")
    expected = condition.get("value")
    exists = actual is not _MISSING
    if operator == "exists":
        return exists
    if operator == "not_exists":
        return not exists
    if not exists:
        return False
    if operator == "equals":
        return actual == expected
    if operator == "not_equals":
        return actual != expected
    if operator == "in":
        return isinstance(expected, (list, tuple, set, frozenset)) and actual in expected
    if operator == "not_in":
        return isinstance(expected, (list, tuple, set, frozenset)) and actual not in expected
    if operator in {"greater_than", "greater_than_or_equal", "less_than", "less_than_or_equal"}:
        try:
            if operator == "greater_than":
                return actual > expected
            if operator == "greater_than_or_equal":
                return actual >= expected
            if operator == "less_than":
                return actual < expected
            return actual <= expected
        except TypeError:
            return False
    return False


def _task_conditions(task: Mapping[str, Any], *, task_id: str) -> list[dict[str, Any]]:
    conditions: list[dict[str, Any]] = []
    for index, expression in enumerate(task.get("postconditions", []), start=1):
        if not isinstance(expression, str):
            continue
        try:
            conditions.append(
                parse_condition(expression, condition_id=f"{task_id}.postcondition.{index}")
            )
        except ValueError:
            continue
    return conditions


def _task_complete(task: Mapping[str, Any], state: Mapping[str, Any]) -> bool:
    conditions = _task_conditions(task, task_id=str(task.get("task_id", "task")))
    return bool(conditions) and all(condition_matches(state, item) for item in conditions)


def workflow_goal_satisfied(workflow: Mapping[str, Any], state: Mapping[str, Any]) -> bool:
    """Independently evaluate all parseable workflow business success conditions."""
    success_conditions = workflow.get("success_conditions")
    if not isinstance(success_conditions, list) or not success_conditions:
        return False
    try:
        parsed = [
            parse_condition(item, condition_id=f"goal.{index}")
            for index, item in enumerate(success_conditions, start=1)
        ]
    except (TypeError, ValueError):
        return False
    return all(condition_matches(state, condition) for condition in parsed)


class WorkflowBrain:
    """Deterministic stand-in for a future Brain LoRA, driven by WorkflowDefinition.

    This is a testing policy, not a trained model or a fixed click script. It
    selects applicable primitive workflow capabilities using live state,
    conditions, hard dependencies, invariants, and postconditions.
    """

    def __init__(self, workflow: Mapping[str, Any]) -> None:
        self.workflow = copy.deepcopy(dict(workflow))
        self._tasks = {
            str(task["task_id"]): task
            for task in self.workflow.get("tasks", [])
            if isinstance(task, Mapping) and task.get("task_id")
        }
        self._capabilities = {
            str(item["capability_id"]): item
            for item in self.workflow.get("capabilities", [])
            if isinstance(item, Mapping) and item.get("capability_id")
        }

    def decide(self, context: BrainContext) -> BrainDecision:
        """Choose the next applicable capability from the latest observed business state."""
        if workflow_goal_satisfied(self.workflow, context.current_state):
            return BrainDecision("finish", "All workflow business success conditions are verified.")

        last_result = context.last_execution_result or {}
        last_status = last_result.get("status")
        last_task_id = str(last_result.get("task_id", ""))
        if last_status in {"failed", "partially_succeeded", "timed_out", "needs_observation"}:
            previous_task = self._tasks.get(last_task_id, {})
            capability = self._capabilities.get(str(previous_task.get("capability_id", "")), {})
            if capability.get("idempotent") is False and not _task_complete(
                previous_task, context.current_state
            ):
                return BrainDecision(
                    "stop",
                    "A non-idempotent operation has an unverified partial/failed result; "
                    "manual reconciliation is required before retry.",
                )

        for task in self.workflow.get("tasks", []):
            if not isinstance(task, Mapping) or task.get("kind") != "primitive":
                continue
            task_id = str(task.get("task_id", ""))
            if not task_id or _task_complete(task, context.current_state):
                continue
            if not self._dependencies_met(task_id, context.current_state):
                continue
            preconditions = task.get("preconditions", [])
            if not all(
                isinstance(condition, Mapping)
                and condition_matches(context.current_state, condition)
                for condition in preconditions
            ):
                continue

            capability_id = str(task.get("capability_id", ""))
            capability = self._capabilities.get(capability_id)
            if capability is None:
                continue
            postconditions = _task_conditions(task, task_id=task_id)
            if not postconditions:
                continue

            task_arguments = context.workflow_inputs.get(task_id)
            capability_arguments = context.workflow_inputs.get(capability_id)
            if isinstance(task_arguments, Mapping):
                arguments = dict(task_arguments)
            elif isinstance(capability_arguments, Mapping):
                arguments = dict(capability_arguments)
            else:
                arguments = dict(context.workflow_inputs)

            attempt = context.attempt_counts.get(task_id, 0) + 1
            risk_level = str(task.get("risk_level") or capability.get("risk_level") or "unknown")
            delegation = OperationDelegation(
                call_id=f"{self.workflow['workflow_id']}:{context.decision_number}:{task_id}",
                task_id=task_id,
                workflow_id=str(self.workflow["workflow_id"]),
                workflow_version=str(self.workflow["version"]),
                node_id=task_id,
                description=str(task.get("description", capability.get("description", task_id))),
                capability_id=capability_id,
                arguments=arguments,
                preconditions=tuple(dict(item) for item in preconditions),
                constraints={
                    "must_not": [
                        "Do not perform an operation outside the named capability.",
                        "Do not claim business success without checking expected postconditions.",
                    ],
                    "allowed_scope": [str(self.workflow["workflow_id"]), task_id, capability_id],
                },
                expected_postconditions=tuple(postconditions),
                observation_requirements=(
                    "Return a fresh business-state observation after execution.",
                    "Provide evidence for every verified postcondition.",
                ),
                risk_level=risk_level,
                requires_human_approval=risk_level in {"high", "critical", "unknown"},
                idempotency_key=f"{self.workflow['workflow_id']}:{task_id}:attempt-{attempt}",
            )
            return BrainDecision(
                "delegate",
                f"Task {task_id} is applicable in the current observed state; "
                "delegating its business capability.",
                delegation,
            )

        return BrainDecision(
            "stop",
            "No remaining primitive task is applicable and the business goal is not satisfied.",
        )

    def _dependencies_met(self, task_id: str, state: Mapping[str, Any]) -> bool:
        for edge in self.workflow.get("edges", []):
            if (
                isinstance(edge, Mapping)
                and edge.get("relation") == "hard_dependency"
                and edge.get("to_task_id") == task_id
            ):
                predecessor = self._tasks.get(str(edge.get("from_task_id", "")))
                if predecessor is None or not _task_complete(predecessor, state):
                    return False
        for constraint in self.workflow.get("ordering_constraints", []):
            if isinstance(constraint, Mapping) and constraint.get("after_task_id") == task_id:
                predecessor = self._tasks.get(str(constraint.get("before_task_id", "")))
                if predecessor is None or not _task_complete(predecessor, state):
                    return False
        for invariant in self.workflow.get("invariants", []):
            if (
                isinstance(invariant, Mapping)
                and task_id in invariant.get("must_hold_before_task_ids", [])
                and not condition_matches(state, invariant.get("condition", {}))
            ):
                return False
        return True


@dataclass(frozen=True, slots=True)
class LoopConfig:
    """Bound the number of Brain decisions to prevent runaway recovery loops."""

    max_decisions: int = 30

    def __post_init__(self) -> None:
        if self.max_decisions < 1:
            raise ValueError("max_decisions must be positive")


@dataclass(frozen=True, slots=True)
class LoopReport:
    """Outcome of a Brain/Hands run, scored at the business-goal level."""

    status: str
    goal_satisfied: bool
    decisions: int
    operations: int
    final_state: Mapping[str, Any]
    history: tuple[Mapping[str, Any], ...] = ()
    error: str | None = None


class BrainHandsLoop:
    """Observe -> decide -> delegate -> execute -> verify state -> decide again."""

    def __init__(
        self,
        workflow: Mapping[str, Any],
        brain: Brain,
        hands: Any,
        config: LoopConfig | None = None,
    ) -> None:
        self.workflow = copy.deepcopy(dict(workflow))
        self.brain = brain
        self.hands = hands
        self.config = config or LoopConfig()
        self._tasks = {
            str(task["task_id"]): task
            for task in self.workflow.get("tasks", [])
            if isinstance(task, Mapping) and task.get("task_id")
        }
        self._capabilities = {
            str(item["capability_id"]): item
            for item in self.workflow.get("capabilities", [])
            if isinstance(item, Mapping) and item.get("capability_id")
        }

    async def run(self, workflow_inputs: Mapping[str, Any] | None = None) -> LoopReport:
        """Run until the Brain finishes a verified goal or a bounded safe stop."""
        try:
            current_state = dict(await self.hands.observe())
        except Exception as exc:
            return LoopReport("failed", False, 0, 0, {}, error=f"initial observation failed: {exc}")

        history: list[dict[str, Any]] = []
        attempts: dict[str, int] = {}
        last_result: dict[str, Any] | None = None
        operations = 0

        for decision_number in range(1, self.config.max_decisions + 1):
            context = BrainContext(
                workflow=self.workflow,
                current_state=copy.deepcopy(current_state),
                workflow_inputs=dict(workflow_inputs or {}),
                last_execution_result=copy.deepcopy(last_result),
                history=tuple(copy.deepcopy(history)),
                attempt_counts=dict(attempts),
                decision_number=decision_number,
            )
            try:
                decision = self.brain.decide(context)
            except Exception as exc:
                return self._report(
                    "failed",
                    False,
                    decision_number,
                    operations,
                    current_state,
                    history,
                    f"Brain decision failed: {type(exc).__name__}: {exc}",
                )
            if not isinstance(decision, BrainDecision):
                return self._report(
                    "failed",
                    False,
                    decision_number,
                    operations,
                    current_state,
                    history,
                    "Brain must return a validated BrainDecision object",
                )

            if decision.action == "finish":
                if workflow_goal_satisfied(self.workflow, current_state):
                    return self._report(
                        "succeeded", True, decision_number, operations, current_state, history
                    )
                return self._report(
                    "failed",
                    False,
                    decision_number,
                    operations,
                    current_state,
                    history,
                    "Brain attempted to finish while workflow success conditions were unmet",
                )
            if decision.action in {"ask_user", "request_approval"}:
                return self._report(
                    "blocked",
                    False,
                    decision_number,
                    operations,
                    current_state,
                    history,
                    f"{decision.action}: {decision.reason}",
                )
            if decision.action == "stop":
                return self._report(
                    "failed",
                    False,
                    decision_number,
                    operations,
                    current_state,
                    history,
                    decision.reason,
                )

            delegation = decision.delegation
            if delegation is None:
                return self._report(
                    "failed",
                    False,
                    decision_number,
                    operations,
                    current_state,
                    history,
                    "delegate decision did not contain an operation_delegation",
                )
            try:
                self._validate_delegation(delegation, current_state)
            except ProtocolError as exc:
                return self._report(
                    "blocked",
                    False,
                    decision_number,
                    operations,
                    current_state,
                    history,
                    f"delegation rejected: {exc}",
                )
            if delegation.requires_human_approval:
                return self._report(
                    "blocked",
                    False,
                    decision_number,
                    operations,
                    current_state,
                    history,
                    "operation requires human approval before Hands execution",
                )

            before = copy.deepcopy(current_state)
            attempts[delegation.task_id] = attempts.get(delegation.task_id, 0) + 1
            operations += 1
            try:
                hands_result = await self.hands.execute(delegation)
                if not isinstance(hands_result, ExecutionResult):
                    hands_result = ExecutionResult.from_mapping(hands_result)
            except Exception as exc:
                hands_result = ExecutionResult(
                    call_id=delegation.call_id,
                    task_id=delegation.task_id,
                    status="failed",
                    result_summary="Hands raised an exception before returning a result.",
                    observed_state={},
                    postcondition_results=(),
                    actions_summary=(
                        {
                            "action": delegation.capability_id,
                            "status": "failed",
                            "detail": f"{type(exc).__name__}: {exc}",
                        },
                    ),
                    error={
                        "category": "hands_exception",
                        "code": type(exc).__name__,
                        "message": str(exc),
                        "retryable": True,
                    },
                )

            if (
                hands_result.call_id != delegation.call_id
                or hands_result.task_id != delegation.task_id
            ):
                hands_result = self._demote(
                    hands_result,
                    "hands_correlation_mismatch",
                    "Hands result call_id/task_id did not match the delegation.",
                )
            try:
                refreshed_state = dict(await self.hands.observe())
            except Exception as exc:
                return self._report(
                    "failed",
                    False,
                    decision_number,
                    operations,
                    current_state,
                    history,
                    f"post-execution observation failed: {type(exc).__name__}: {exc}",
                )

            hands_result = self._verify_return(delegation, hands_result, refreshed_state)
            current_state = refreshed_state
            history.append(
                {
                    "decision_number": decision_number,
                    "state_before": before,
                    "decision_reason": decision.reason,
                    "delegation": delegation.to_dict(),
                    "execution_result": hands_result.to_dict(),
                    "verified_state_after": copy.deepcopy(current_state),
                    "business_goal_satisfied": workflow_goal_satisfied(
                        self.workflow, current_state
                    ),
                }
            )
            last_result = hands_result.to_dict()
            # The Brain receives this fresh state and result on the next iteration.
            # A failed/partial result is never treated as permission to advance.

        return self._report(
            "step_limit",
            workflow_goal_satisfied(self.workflow, current_state),
            self.config.max_decisions,
            operations,
            current_state,
            history,
            f"maximum Brain decisions reached: {self.config.max_decisions}",
        )

    def _validate_delegation(
        self, delegation: OperationDelegation, current_state: Mapping[str, Any]
    ) -> None:
        if delegation.workflow_id != self.workflow.get(
            "workflow_id"
        ) or delegation.workflow_version != self.workflow.get("version"):
            raise ProtocolError("delegation workflow_ref does not match the active workflow")
        task = self._tasks.get(delegation.task_id)
        if task is None or task.get("kind") != "primitive":
            raise ProtocolError("delegation task_id is not a primitive task in the active workflow")
        if task.get("capability_id") != delegation.capability_id:
            raise ProtocolError("delegation capability_id does not match the workflow task")
        capability = self._capabilities.get(delegation.capability_id)
        if capability is None:
            raise ProtocolError("delegation capability_id is not registered")
        declared_risk = str(task.get("risk_level") or capability.get("risk_level") or "unknown")
        if delegation.risk_level != declared_risk:
            raise ProtocolError("delegation risk_level does not match the workflow capability")
        if (
            declared_risk in {"high", "critical", "unknown"}
            and not delegation.requires_human_approval
        ):
            raise ProtocolError("high/critical/unknown risk capabilities require human approval")
        if delegation.node_id != delegation.task_id:
            raise ProtocolError("delegation workflow_ref.node_id must identify its task")
        if delegation.capability_id not in delegation.constraints.get("allowed_scope", []):
            raise ProtocolError("delegation allowed_scope does not include its capability")
        for condition in delegation.preconditions:
            if not condition_matches(current_state, condition):
                raise ProtocolError(
                    f"delegation precondition failed: {condition.get('path', '<unknown>')}"
                )
        for invariant in self.workflow.get("invariants", []):
            if (
                isinstance(invariant, Mapping)
                and delegation.task_id in invariant.get("must_hold_before_task_ids", [])
                and not condition_matches(current_state, invariant.get("condition", {}))
            ):
                raise ProtocolError(f"workflow invariant failed before task {delegation.task_id}")
        expected = {
            (item.get("path"), item.get("operator"), json.dumps(item.get("value"), sort_keys=True))
            for item in delegation.expected_postconditions
        }
        task_expected = {
            (item["path"], item["operator"], json.dumps(item["value"], sort_keys=True))
            for item in _task_conditions(task, task_id=delegation.task_id)
        }
        if expected != task_expected:
            raise ProtocolError("delegation expected_postconditions do not match workflow task")

    def _verify_return(
        self,
        delegation: OperationDelegation,
        result: ExecutionResult,
        refreshed_state: Mapping[str, Any],
    ) -> ExecutionResult:
        if result.status != "succeeded":
            return result
        checks = {str(item.get("condition_id")): item for item in result.postcondition_results}
        missing: list[str] = []
        for expected in delegation.expected_postconditions:
            condition_id = str(expected.get("condition_id"))
            returned = checks.get(condition_id)
            state_passed = condition_matches(refreshed_state, expected)
            evidence_refs = returned.get("evidence_refs", []) if returned else []
            passed = (
                returned is not None
                and returned.get("result") == "passed"
                and bool(evidence_refs)
                and all(ref in result.evidence_refs for ref in evidence_refs)
                and state_passed
            )
            if not passed:
                missing.append(condition_id)
        if missing:
            return self._demote(
                result,
                "postcondition_verification_failed",
                "Hands claimed success without matching fresh state and evidence for: "
                + ", ".join(missing),
            )
        if dict(result.observed_state) != dict(refreshed_state):
            return self._demote(
                result,
                "observed_state_stale",
                "Hands result observed_state differs from the fresh post-execution observation.",
            )
        return result

    @staticmethod
    def _demote(result: ExecutionResult, code: str, message: str) -> ExecutionResult:
        return ExecutionResult(
            call_id=result.call_id,
            task_id=result.task_id,
            status="partially_succeeded",
            result_summary=result.result_summary,
            observed_state=result.observed_state,
            postcondition_results=result.postcondition_results,
            actions_summary=result.actions_summary,
            error={"category": "verification", "code": code, "message": message},
            evidence_refs=result.evidence_refs,
            trace_ref=result.trace_ref,
            completed_at=result.completed_at,
        )

    @staticmethod
    def _report(
        status: str,
        goal_satisfied: bool,
        decisions: int,
        operations: int,
        final_state: Mapping[str, Any],
        history: list[dict[str, Any]],
        error: str | None = None,
    ) -> LoopReport:
        return LoopReport(
            status=status,
            goal_satisfied=goal_satisfied,
            decisions=decisions,
            operations=operations,
            final_state=copy.deepcopy(dict(final_state)),
            history=tuple(copy.deepcopy(history)),
            error=error,
        )
