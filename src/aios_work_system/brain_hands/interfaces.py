"""Versioned Brain-to-Hands messages and replaceable component protocols.

The Brain expresses business capabilities and postconditions. Low-level GUI
operations remain an implementation detail of Hands and the existing GUI Agent.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, Protocol


ExecutionStatus = Literal[
    "succeeded",
    "failed",
    "partially_succeeded",
    "blocked",
    "needs_observation",
    "timed_out",
    "cancelled",
]
BrainDecisionAction = Literal["delegate", "finish", "stop", "ask_user", "request_approval"]

EXECUTION_STATUSES = frozenset(
    {
        "succeeded",
        "failed",
        "partially_succeeded",
        "blocked",
        "needs_observation",
        "timed_out",
        "cancelled",
    }
)
RISK_LEVELS = frozenset({"low", "medium", "high", "critical", "unknown"})
CONDITION_OPERATORS = frozenset(
    {"equals", "not_equals", "in", "not_in", "exists", "not_exists"}
)
_FORBIDDEN_COORDINATE_KEYS = frozenset(
    {
        "coordinates",
        "mouse_coordinates",
        "screen_coordinates",
        "cursor_position",
        "screen_position",
        "click_coordinates",
        "click_x",
        "click_y",
        "mouse_x",
        "mouse_y",
        "x_coordinate",
        "y_coordinate",
    }
)


class ProtocolError(ValueError):
    """Raised when a Brain/Hands message violates the versioned JSON contract."""


def _non_empty_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProtocolError(f"{field_name} must be a non-empty string")
    return value


def _object(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ProtocolError(f"{field_name} must be an object")
    return dict(value)


def _string_list(value: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ProtocolError(f"{field_name} must be an array of non-empty strings")
    return tuple(value)


def _reject_coordinate_payload(value: Any, path: str = "objective.arguments") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).lower() in _FORBIDDEN_COORDINATE_KEYS:
                raise ProtocolError(
                    f"Brain delegation must not contain low-level GUI coordinates ({path}.{key})"
                )
            _reject_coordinate_payload(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_coordinate_payload(child, f"{path}[{index}]")


@dataclass(frozen=True, slots=True)
class OperationDelegation:
    """A high-level capability request; it never contains click/mouse coordinates."""

    call_id: str
    task_id: str
    workflow_id: str
    workflow_version: str
    node_id: str
    description: str
    capability_id: str
    arguments: Mapping[str, Any]
    preconditions: tuple[Mapping[str, Any], ...]
    constraints: Mapping[str, Any]
    expected_postconditions: tuple[Mapping[str, Any], ...]
    observation_requirements: tuple[str, ...]
    risk_level: str
    requires_human_approval: bool
    idempotency_key: str
    approval_ref: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    protocol_version: str = "0.1"

    def __post_init__(self) -> None:
        for name in (
            "call_id",
            "task_id",
            "workflow_id",
            "workflow_version",
            "node_id",
            "description",
            "capability_id",
            "idempotency_key",
        ):
            _non_empty_text(getattr(self, name), name)
        if self.protocol_version != "0.1":
            raise ProtocolError("protocol_version must be '0.1'")
        if self.risk_level not in RISK_LEVELS:
            raise ProtocolError(f"unsupported risk_level: {self.risk_level}")
        if not isinstance(self.requires_human_approval, bool):
            raise ProtocolError("requires_human_approval must be a boolean")
        _reject_coordinate_payload(self.arguments)
        if not isinstance(self.arguments, Mapping):
            raise ProtocolError("objective.arguments must be an object")
        if not isinstance(self.constraints, Mapping):
            raise ProtocolError("constraints must be an object")
        if not {"must_not", "allowed_scope"} <= set(self.constraints):
            raise ProtocolError("constraints require must_not and allowed_scope")
        for key in ("must_not", "allowed_scope"):
            values = self.constraints[key]
            if not isinstance(values, (tuple, list)) or not all(
                isinstance(item, str) for item in values
            ):
                raise ProtocolError(f"constraints.{key} must be an array of strings")
        if not self.expected_postconditions:
            raise ProtocolError("expected_postconditions must contain at least one condition")
        for item in (*self.preconditions, *self.expected_postconditions):
            if not isinstance(item, Mapping):
                raise ProtocolError("conditions and postconditions must be objects")

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> OperationDelegation:
        """Validate a Brain JSON object against the delegation portion of v0.1."""
        allowed = {
            "protocol_version",
            "message_type",
            "call_id",
            "task_id",
            "workflow_ref",
            "objective",
            "preconditions",
            "constraints",
            "expected_postconditions",
            "observation_requirements",
            "safety",
            "idempotency_key",
            "created_at",
        }
        if set(payload) - allowed:
            raise ProtocolError(f"unexpected delegation fields: {sorted(set(payload) - allowed)}")
        if payload.get("protocol_version") != "0.1":
            raise ProtocolError("protocol_version must be '0.1'")
        if payload.get("message_type") != "operation_delegation":
            raise ProtocolError("message_type must be 'operation_delegation'")
        workflow_ref = _object(payload.get("workflow_ref"), "workflow_ref")
        if set(workflow_ref) != {"workflow_id", "version", "node_id"}:
            raise ProtocolError("workflow_ref requires workflow_id, version, and node_id")
        objective = _object(payload.get("objective"), "objective")
        if set(objective) != {"description", "capability_id", "arguments"}:
            raise ProtocolError("objective requires description, capability_id, and arguments")
        safety = _object(payload.get("safety"), "safety")
        if not {"risk_level", "requires_human_approval"} <= set(safety):
            raise ProtocolError("safety requires risk_level and requires_human_approval")
        if set(safety) - {"risk_level", "requires_human_approval", "approval_ref"}:
            raise ProtocolError("safety contains unsupported fields")
        preconditions = payload.get("preconditions")
        postconditions = payload.get("expected_postconditions")
        if not isinstance(preconditions, list) or not isinstance(postconditions, list):
            raise ProtocolError("preconditions and expected_postconditions must be arrays")
        return cls(
            call_id=_non_empty_text(payload.get("call_id"), "call_id"),
            task_id=_non_empty_text(payload.get("task_id"), "task_id"),
            workflow_id=_non_empty_text(
                workflow_ref.get("workflow_id"), "workflow_ref.workflow_id"
            ),
            workflow_version=_non_empty_text(workflow_ref.get("version"), "workflow_ref.version"),
            node_id=_non_empty_text(workflow_ref.get("node_id"), "workflow_ref.node_id"),
            description=_non_empty_text(objective.get("description"), "objective.description"),
            capability_id=_non_empty_text(
                objective.get("capability_id"), "objective.capability_id"
            ),
            arguments=_object(objective.get("arguments"), "objective.arguments"),
            preconditions=tuple(_object(item, "precondition") for item in preconditions),
            constraints=_object(payload.get("constraints"), "constraints"),
            expected_postconditions=tuple(
                _object(item, "expected_postcondition") for item in postconditions
            ),
            observation_requirements=_string_list(
                payload.get("observation_requirements"), "observation_requirements"
            ),
            risk_level=_non_empty_text(safety.get("risk_level"), "safety.risk_level"),
            requires_human_approval=safety.get("requires_human_approval"),
            approval_ref=safety.get("approval_ref"),
            idempotency_key=_non_empty_text(payload.get("idempotency_key"), "idempotency_key"),
            created_at=payload.get("created_at") or datetime.now(UTC).isoformat(),
            protocol_version="0.1",
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the schema-compatible JSON message."""
        return {
            "protocol_version": self.protocol_version,
            "message_type": "operation_delegation",
            "call_id": self.call_id,
            "task_id": self.task_id,
            "workflow_ref": {
                "workflow_id": self.workflow_id,
                "version": self.workflow_version,
                "node_id": self.node_id,
            },
            "objective": {
                "description": self.description,
                "capability_id": self.capability_id,
                "arguments": dict(self.arguments),
            },
            "preconditions": [dict(item) for item in self.preconditions],
            "constraints": {
                key: list(value) if isinstance(value, (tuple, list)) else value
                for key, value in self.constraints.items()
            },
            "expected_postconditions": [dict(item) for item in self.expected_postconditions],
            "observation_requirements": list(self.observation_requirements),
            "safety": {
                "risk_level": self.risk_level,
                "requires_human_approval": self.requires_human_approval,
                **({"approval_ref": self.approval_ref} if self.approval_ref else {}),
            },
            "idempotency_key": self.idempotency_key,
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """A structured Hands return; success requires evidence-backed state verification."""

    call_id: str
    task_id: str
    status: ExecutionStatus
    result_summary: str
    observed_state: Mapping[str, Any]
    postcondition_results: tuple[Mapping[str, Any], ...]
    actions_summary: tuple[Mapping[str, Any], ...]
    error: Mapping[str, Any] | None = None
    evidence_refs: tuple[str, ...] = ()
    trace_ref: str | None = None
    completed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    protocol_version: str = "0.1"

    def __post_init__(self) -> None:
        _non_empty_text(self.call_id, "call_id")
        _non_empty_text(self.task_id, "task_id")
        _non_empty_text(self.result_summary, "result_summary")
        if self.protocol_version != "0.1":
            raise ProtocolError("protocol_version must be '0.1'")
        if self.status not in EXECUTION_STATUSES:
            raise ProtocolError(f"unsupported Hands status: {self.status}")
        if not isinstance(self.observed_state, Mapping):
            raise ProtocolError("observed_state must be an object")
        for item in (*self.postcondition_results, *self.actions_summary):
            if not isinstance(item, Mapping):
                raise ProtocolError(
                    "postcondition_results and actions_summary must contain objects"
                )

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> ExecutionResult:
        """Parse a schema-compatible Hands result JSON object."""
        allowed = {
            "protocol_version",
            "message_type",
            "call_id",
            "task_id",
            "status",
            "result_summary",
            "observed_state",
            "postcondition_results",
            "actions_summary",
            "error",
            "evidence_refs",
            "trace_ref",
            "completed_at",
        }
        if set(payload) - allowed:
            raise ProtocolError(
                f"unexpected execution-result fields: {sorted(set(payload) - allowed)}"
            )
        if (
            payload.get("protocol_version") != "0.1"
            or payload.get("message_type") != "operation_result"
        ):
            raise ProtocolError("expected BrainHandsProtocol v0.1 operation_result")
        postcondition_results = payload.get("postcondition_results")
        actions_summary = payload.get("actions_summary")
        if not isinstance(postcondition_results, list) or not isinstance(actions_summary, list):
            raise ProtocolError("postcondition_results and actions_summary must be arrays")
        evidence_refs = payload.get("evidence_refs")
        if not isinstance(evidence_refs, list) or not all(
            isinstance(item, str) for item in evidence_refs
        ):
            raise ProtocolError("evidence_refs must be an array of strings")
        error = payload.get("error")
        return cls(
            call_id=_non_empty_text(payload.get("call_id"), "call_id"),
            task_id=_non_empty_text(payload.get("task_id"), "task_id"),
            status=payload.get("status"),
            result_summary=_non_empty_text(payload.get("result_summary"), "result_summary"),
            observed_state=_object(payload.get("observed_state"), "observed_state"),
            postcondition_results=tuple(
                _object(item, "postcondition_result") for item in postcondition_results
            ),
            actions_summary=tuple(_object(item, "action_summary") for item in actions_summary),
            error=_object(error, "error") if error is not None else None,
            evidence_refs=tuple(evidence_refs),
            trace_ref=payload.get("trace_ref"),
            completed_at=payload.get("completed_at") or datetime.now(UTC).isoformat(),
            protocol_version="0.1",
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the schema-compatible JSON message."""
        return {
            "protocol_version": self.protocol_version,
            "message_type": "operation_result",
            "call_id": self.call_id,
            "task_id": self.task_id,
            "status": self.status,
            "result_summary": self.result_summary,
            "observed_state": dict(self.observed_state),
            "postcondition_results": [dict(item) for item in self.postcondition_results],
            "actions_summary": [dict(item) for item in self.actions_summary],
            "error": dict(self.error) if self.error is not None else None,
            "evidence_refs": list(self.evidence_refs),
            **({"trace_ref": self.trace_ref} if self.trace_ref else {}),
            "completed_at": self.completed_at,
        }


@dataclass(frozen=True, slots=True)
class BrainDecision:
    """One Brain-level control decision; low-level GUI actions are not an option."""

    action: BrainDecisionAction
    reason: str
    delegation: OperationDelegation | None = None

    def __post_init__(self) -> None:
        if self.action not in {"delegate", "finish", "stop", "ask_user", "request_approval"}:
            raise ProtocolError(f"unsupported Brain decision: {self.action}")
        _non_empty_text(self.reason, "reason")
        if (self.action == "delegate") != (self.delegation is not None):
            raise ProtocolError("only a delegate decision may carry an operation delegation")


@dataclass(frozen=True, slots=True)
class BrainContext:
    """Fresh workflow context supplied to the Brain for each decision."""

    workflow: Mapping[str, Any]
    current_state: Mapping[str, Any]
    workflow_inputs: Mapping[str, Any] = field(default_factory=dict)
    last_execution_result: Mapping[str, Any] | None = None
    history: tuple[Mapping[str, Any], ...] = ()
    attempt_counts: Mapping[str, int] = field(default_factory=dict)
    decision_number: int = 1


class Brain(Protocol):
    """Replaceable workflow-reasoning component (stub now, LoRA adapter later)."""

    def decide(self, context: BrainContext) -> BrainDecision:
        """Choose a business capability, recover, or finish after checking the goal."""


class Hands(Protocol):
    """Replaceable operation executor (simulated in CI, GUI adapter manually)."""

    async def observe(self) -> Mapping[str, Any]:
        """Return a fresh, normalized state snapshot."""

    async def execute(self, delegation: OperationDelegation) -> ExecutionResult:
        """Execute one high-level capability and return evidence-backed observations."""
