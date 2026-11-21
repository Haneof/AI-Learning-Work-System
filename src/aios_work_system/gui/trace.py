"""Timestamped JSONL recording and strict Playwright trace replay."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from aios_work_system.gui.browser import (
    ensure_same_origin,
    execute_action,
    install_local_only_guard,
    local_origin,
    observe_page,
    verify_expectation,
)
from aios_work_system.gui.contracts import BrowserObservation, GuiAction


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


class TraceFormatError(ValueError):
    """Raised when a JSONL trace is malformed or incomplete."""


class ReplayVerificationError(RuntimeError):
    """Raised at the first action whose replayed result does not match its assertion."""

    def __init__(self, step_number: int, message: str, actual_result: Mapping[str, Any] | None = None):
        super().__init__(f"trace replay stopped at step {step_number}: {message}")
        self.step_number = step_number
        self.actual_result = dict(actual_result or {})


class BrowserEventCapture:
    """Capture DOM-level pointer, mouse, keyboard, input, and scroll events."""

    _SCRIPT = r"""
(() => {
  if (window.__aiosTraceInstalled) return;
  const describe = (element) => {
    if (!element || !element.tagName) return null;
    const type = (element.getAttribute("type") || "").toLowerCase();
    const name = element.getAttribute("name") || "";
    const redacted = type === "password" || /password|secret|token/i.test(name);
    return {
      tag: element.tagName.toLowerCase(),
      id: element.id || null,
      role: element.getAttribute("role"),
      aria_label: element.getAttribute("aria-label"),
      name: name || null,
      type: type || null,
      text: ((element.innerText || element.textContent || "").trim()).slice(0, 160),
      redacted: redacted
    };
  };
  const send = (event) => {
    const element = event.target && event.target.nodeType === 1 ? event.target : null;
    const target = describe(element);
    const redacted = target && target.redacted;
    const record = {
      timestamp: new Date().toISOString(),
      event_type: event.type,
      target: target,
      key: event.key ? (redacted ? "<redacted>" : event.key) : null,
      text: event.data ? (redacted ? "<redacted>" : event.data) : null,
      button: typeof event.button === "number" ? event.button : null,
      client_x: typeof event.clientX === "number" ? event.clientX : null,
      client_y: typeof event.clientY === "number" ? event.clientY : null
    };
    const pending = window.__aiosTraceEmit(record);
    if (pending && typeof pending.catch === "function") pending.catch(() => {});
  };
  [
    "pointerdown", "pointerup", "mousedown", "mouseup", "click",
    "keydown", "keyup", "input", "change", "scroll"
  ].forEach((name) => document.addEventListener(name, send, true));
  window.__aiosTraceInstalled = true;
})();
"""

    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []

    async def _receive(self, _source: object, event: Mapping[str, Any]) -> None:
        self._events.append(dict(event))

    async def attach(self, page: object) -> None:
        await page.expose_binding("__aiosTraceEmit", self._receive)  # type: ignore[attr-defined]
        await page.add_init_script(self._SCRIPT)  # type: ignore[attr-defined]
        await page.evaluate(self._SCRIPT)  # type: ignore[attr-defined]

    def cursor(self) -> int:
        return len(self._events)

    def since(self, cursor: int) -> list[dict[str, Any]]:
        if not 0 <= cursor <= len(self._events):
            raise ValueError("event cursor is outside the captured event range")
        return [dict(event) for event in self._events[cursor:]]


class JsonlTraceRecorder:
    """Write one header and one independently replayable record per action to JSONL."""

    def __init__(self, path: str | Path, objective: str, origin: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.objective = objective
        self.origin = local_origin(origin)
        self.trace_id = str(uuid4())
        self._sequence = 0
        header = {
            "kind": "header",
            "schema_version": "gui-trace-v1",
            "trace_id": self.trace_id,
            "created_at": _timestamp(),
            "objective": objective,
            "origin": self.origin,
            "environment": "playwright-local-browser",
            "training_format": "observation_to_action",
        }
        self.path.write_text(json.dumps(header, ensure_ascii=False) + "\n", encoding="utf-8")

    def record_step(
        self,
        *,
        before: BrowserObservation,
        after: BrowserObservation,
        action: GuiAction,
        events: list[dict[str, Any]],
        verification: Mapping[str, Any],
        correction_attempt: bool = False,
    ) -> None:
        self._sequence += 1
        before_data = before.to_dict()
        action_data = action.to_dict()
        row = {
            "kind": "step",
            "schema_version": "gui-trace-v1",
            "trace_id": self.trace_id,
            "step": self._sequence,
            "timestamp": _timestamp(),
            "correction_attempt": correction_attempt,
            "before": before_data,
            "events": events,
            "action": action_data,
            "expected_result": (
                action.expected_result.to_dict() if action.expected_result is not None else None
            ),
            "after": after.to_dict(),
            "actual_result": dict(verification),
            "verified": verification.get("passed") is True,
            "training_example": {
                "input": {"objective": self.objective, "observation": before_data},
                "output": action_data,
            },
        }
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")

    def record_error(self, *, step: int, stage: str, message: str) -> None:
        row = {
            "kind": "error",
            "schema_version": "gui-trace-v1",
            "trace_id": self.trace_id,
            "step": step,
            "timestamp": _timestamp(),
            "stage": stage,
            "message": message,
        }
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_trace(path: str | Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Load and validate the JSONL header and contiguous step sequence."""
    rows: list[dict[str, Any]] = []
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise TraceFormatError(f"cannot read trace: {exc}") from exc
    if not lines:
        raise TraceFormatError("trace is empty")
    for line_number, line in enumerate(lines, start=1):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise TraceFormatError(f"invalid JSON on line {line_number}") from exc
        if not isinstance(payload, dict):
            raise TraceFormatError(f"line {line_number} must contain a JSON object")
        rows.append(payload)

    header = rows[0]
    if header.get("kind") != "header" or header.get("schema_version") != "gui-trace-v1":
        raise TraceFormatError("missing or unsupported trace header")
    if not isinstance(header.get("origin"), str):
        raise TraceFormatError("trace header is missing its origin")

    steps: list[dict[str, Any]] = []
    for expected_number, row in enumerate(rows[1:], start=1):
        if row.get("kind") == "error":
            steps.append(row)
            continue
        if row.get("kind") != "step" or row.get("step") != expected_number:
            raise TraceFormatError(f"invalid or non-contiguous step on line {expected_number + 1}")
        if not isinstance(row.get("action"), dict) or not isinstance(row.get("before"), dict):
            raise TraceFormatError(f"step {expected_number} is missing action or observation")
        steps.append(row)
    return header, steps


class ReplayReport:
    """Summary of a fully verified trace replay."""

    def __init__(self, trace_id: str, steps_replayed: int) -> None:
        self.trace_id = trace_id
        self.steps_replayed = steps_replayed
        self.verified = True


class TraceReplayer:
    """Replay actions in order and stop immediately on the first mismatch."""

    def __init__(self, path: str | Path, action_timeout_ms: int = 3000) -> None:
        self.path = Path(path)
        self.action_timeout_ms = action_timeout_ms

    async def replay(self, page: object) -> ReplayReport:
        header, rows = load_trace(self.path)
        allowed_origin = local_origin(page.url)  # type: ignore[attr-defined]
        if allowed_origin != header["origin"]:
            raise ReplayVerificationError(
                0,
                f"origin mismatch: trace={header['origin']} page={allowed_origin}",
            )
        await install_local_only_guard(page, allowed_origin)
        replayed = 0
        for row in rows:
            step_number = row.get("step", replayed + 1)
            if row.get("kind") == "error":
                raise ReplayVerificationError(step_number, "trace contains an incomplete error record")
            action = GuiAction.from_mapping(row["action"])
            if action.action == "done":
                replayed += 1
                continue
            ensure_same_origin(page.url, allowed_origin)  # type: ignore[attr-defined]
            try:
                await execute_action(page, action)
                ensure_same_origin(page.url, allowed_origin)  # type: ignore[attr-defined]
                actual = await verify_expectation(
                    page,
                    action.expected_result,  # type: ignore[arg-type]
                    timeout_ms=self.action_timeout_ms,
                )
            except Exception as exc:
                raise ReplayVerificationError(
                    step_number,
                    f"action execution failed: {type(exc).__name__}: {exc}",
                ) from exc
            if actual.get("passed") is not True:
                raise ReplayVerificationError(step_number, "expected result did not match", actual)
            replayed += 1
        return ReplayReport(header["trace_id"], replayed)
