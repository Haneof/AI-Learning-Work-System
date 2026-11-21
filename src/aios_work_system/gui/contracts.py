"""Typed contracts for browser observations and GUI actions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal, Mapping


class ContractError(ValueError):
    """Raised when a model response does not satisfy the GUI action contract."""


ActionName = Literal["click", "type", "scroll", "wait", "done"]
ExpectationName = Literal[
    "text_contains",
    "text_equals",
    "value_equals",
    "visible",
    "hidden",
    "attribute_equals",
    "url_contains",
    "title_contains",
]


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field_name} must be a non-empty string")
    return value


def _optional_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ContractError(f"{field_name} must be a string")
    return value


def _integer(value: Any, field_name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractError(f"{field_name} must be an integer")
    if not minimum <= value <= maximum:
        raise ContractError(f"{field_name} must be between {minimum} and {maximum}")
    return value


@dataclass(frozen=True, slots=True)
class BrowserObservation:
    """A point-in-time visual and semantic browser observation."""

    timestamp: str
    url: str
    origin: str
    title: str
    screenshot_b64: str
    dom_snapshot: str
    accessibility_snapshot: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ExpectedResult:
    """A deterministic post-action assertion against the local browser page."""

    kind: ExpectationName
    selector: str | None = None
    value: str | None = None
    attribute: str | None = None

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> ExpectedResult:
        allowed = {"kind", "selector", "value", "attribute"}
        extra = set(payload) - allowed
        if extra:
            raise ContractError(f"unexpected expectation fields: {sorted(extra)}")

        kind = _text(payload.get("kind"), "expected_result.kind")
        valid_kinds = {
            "text_contains",
            "text_equals",
            "value_equals",
            "visible",
            "hidden",
            "attribute_equals",
            "url_contains",
            "title_contains",
        }
        if kind not in valid_kinds:
            raise ContractError(f"unsupported expectation kind: {kind}")

        selector = _optional_text(payload.get("selector"), "expected_result.selector")
        value = _optional_text(payload.get("value"), "expected_result.value")
        attribute = _optional_text(payload.get("attribute"), "expected_result.attribute")

        if kind in {"text_contains", "text_equals", "value_equals", "visible", "hidden"}:
            if selector is None:
                raise ContractError(f"{kind} requires expected_result.selector")
        if kind in {
            "text_contains",
            "text_equals",
            "value_equals",
            "attribute_equals",
            "url_contains",
            "title_contains",
        } and value is None:
            raise ContractError(f"{kind} requires expected_result.value")
        if kind == "attribute_equals":
            if selector is None or attribute is None:
                raise ContractError("attribute_equals requires selector and attribute")

        return cls(
            kind=kind,  # type: ignore[arg-type]
            selector=selector,
            value=value,
            attribute=attribute,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class GuiAction:
    """One constrained browser action emitted as structured JSON by a model."""

    action: ActionName
    target: str
    selector: str | None = None
    value: str | None = None
    direction: Literal["up", "down"] = "down"
    amount: int = 500
    timeout_ms: int = 1000
    expected_result: ExpectedResult | None = None

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> GuiAction:
        allowed = {
            "action",
            "target",
            "selector",
            "value",
            "direction",
            "amount",
            "timeout_ms",
            "expected_result",
        }
        extra = set(payload) - allowed
        if extra:
            raise ContractError(f"unexpected action fields: {sorted(extra)}")

        action = _text(payload.get("action"), "action")
        if action not in {"click", "type", "scroll", "wait", "done"}:
            raise ContractError(f"unsupported action: {action}")

        target = _text(payload.get("target"), "target")
        selector = _optional_text(payload.get("selector"), "selector")
        value = _optional_text(payload.get("value"), "value")
        direction = payload.get("direction", "down")
        if direction not in {"up", "down"}:
            raise ContractError("direction must be 'up' or 'down'")

        amount = _integer(payload.get("amount", 500), "amount", 1, 5000)
        timeout_ms = _integer(payload.get("timeout_ms", 1000), "timeout_ms", 0, 5000)

        expected_payload = payload.get("expected_result")
        expected: ExpectedResult | None = None
        if expected_payload is not None:
            if not isinstance(expected_payload, Mapping):
                raise ContractError("expected_result must be an object")
            expected = ExpectedResult.from_mapping(expected_payload)

        if action in {"click", "type"} and selector is None:
            raise ContractError(f"{action} requires selector")
        if action == "type" and value is None:
            raise ContractError("type requires value")
        if action != "done" and expected is None:
            raise ContractError(f"{action} requires expected_result")

        return cls(
            action=action,  # type: ignore[arg-type]
            target=target,
            selector=selector,
            value=value,
            direction=direction,  # type: ignore[arg-type]
            amount=amount,
            timeout_ms=timeout_ms,
            expected_result=expected,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
