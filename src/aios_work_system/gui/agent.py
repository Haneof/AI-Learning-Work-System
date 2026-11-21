"""Minimal observe-decide-act-verify browser agent with one correction attempt."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from aios_work_system.gui.browser import (
    ensure_same_origin,
    execute_action,
    install_local_only_guard,
    local_origin,
    observe_page,
    verify_expectation,
)
from aios_work_system.gui.contracts import GuiAction
from aios_work_system.gui.trace import BrowserEventCapture, JsonlTraceRecorder


class DecisionModel(Protocol):
    """Replaceable async protocol; production model adapters are intentionally absent."""

    async def decide(self, request: Mapping[str, Any]) -> Mapping[str, Any] | str:
        """Return one JSON object (or JSON string) matching the GUI action contract."""


@dataclass(frozen=True, slots=True)
class AgentConfig:
    max_steps: int = 20
    model_timeout_s: float = 10.0
    action_timeout_s: float = 5.0
    max_corrections: int = 1

    def __post_init__(self) -> None:
        if self.max_steps < 1:
            raise ValueError("max_steps must be positive")
        if self.model_timeout_s <= 0 or self.action_timeout_s <= 0:
            raise ValueError("timeouts must be positive")
        if self.max_corrections != 1:
            raise ValueError("this milestone supports exactly one correction attempt")


@dataclass(frozen=True, slots=True)
class RunReport:
    status: str
    steps: int
    corrections: int
    trace_path: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "steps": self.steps,
            "corrections": self.corrections,
            "trace_path": self.trace_path,
            "error": self.error,
        }


class BrowserAgent:
    """A local-origin-only browser loop driven by an injected decision model."""

    def __init__(
        self,
        page: object,
        model: DecisionModel,
        trace_path: str,
        config: AgentConfig | None = None,
    ) -> None:
        self.page = page
        self.model = model
        self.trace_path = trace_path
        self.config = config or AgentConfig()

    async def _decide(self, request: Mapping[str, Any]) -> GuiAction:
        response = await asyncio.wait_for(
            self.model.decide(request),
            timeout=self.config.model_timeout_s,
        )
        if isinstance(response, str):
            import json

            response = json.loads(response)
        if not isinstance(response, Mapping):
            raise ValueError("model decision must be a JSON object")
        return GuiAction.from_mapping(response)

    async def _observation(self) -> Any:
        return await asyncio.wait_for(
            observe_page(self.page),
            timeout=self.config.action_timeout_s,
        )

    def _request(
        self,
        objective: str,
        observation: Any,
        history: list[dict[str, Any]],
        *,
        correction: bool,
        last_failure: Mapping[str, Any] | None = None,
        failed_action: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "objective": objective,
            "observation": observation.to_dict(),
            "history": list(history[-10:]),
            "correction": correction,
            "last_failure": dict(last_failure) if last_failure is not None else None,
            "failed_action": dict(failed_action) if failed_action is not None else None,
            "allowed_actions": ["click", "type", "scroll", "wait", "done"],
            "constraints": {
                "local_origin_only": True,
                "no_arbitrary_code": True,
                "one_correction_attempt": True,
            },
        }

    async def run(self, objective: str) -> RunReport:
        if not objective.strip():
            raise ValueError("objective must not be empty")
        origin = local_origin(self.page.url)  # type: ignore[attr-defined]
        recorder = JsonlTraceRecorder(self.trace_path, objective, origin)
        events = BrowserEventCapture()
        await install_local_only_guard(self.page, origin)
        await events.attach(self.page)
        try:
            observation = await self._observation()
        except TimeoutError as exc:
            recorder.record_error(step=0, stage="observation", message=str(exc) or "timeout")
            return RunReport("timed_out", 0, 0, self.trace_path, "initial observation timed out")

        history: list[dict[str, Any]] = []
        executed_steps = 0
        corrections = 0

        for step_number in range(1, self.config.max_steps + 1):
            request = self._request(objective, observation, history, correction=False)
            try:
                action = await self._decide(request)
            except TimeoutError:
                recorder.record_error(
                    step=step_number,
                    stage="model_decision",
                    message="model decision timed out",
                )
                return RunReport(
                    "timed_out",
                    executed_steps,
                    corrections,
                    self.trace_path,
                    "model decision timed out",
                )
            except Exception as exc:
                message = f"{type(exc).__name__}: {exc}"
                recorder.record_error(step=step_number, stage="model_decision", message=message)
                return RunReport("failed", executed_steps, corrections, self.trace_path, message)

            if action.action == "done":
                recorder.record_step(
                    before=observation,
                    after=observation,
                    action=action,
                    events=[],
                    verification={"passed": True, "kind": "done"},
                )
                return RunReport("done", executed_steps, corrections, self.trace_path)

            correction_attempt = False
            while True:
                cursor = events.cursor()
                try:
                    ensure_same_origin(self.page.url, origin)  # type: ignore[attr-defined]
                    await asyncio.wait_for(
                        execute_action(self.page, action),
                        timeout=self.config.action_timeout_s,
                    )
                    await self.page.wait_for_timeout(10)  # type: ignore[attr-defined]
                    ensure_same_origin(self.page.url, origin)  # type: ignore[attr-defined]
                    after = await self._observation()
                    verification = await asyncio.wait_for(
                        verify_expectation(
                            self.page,
                            action.expected_result,  # type: ignore[arg-type]
                        ),
                        timeout=self.config.action_timeout_s,
                    )
                except TimeoutError:
                    try:
                        ensure_same_origin(self.page.url, origin)  # type: ignore[attr-defined]
                        after = await self._observation()
                    except Exception:
                        after = observation
                    verification = {
                        "passed": False,
                        "timed_out": True,
                        "error": "action or observation timed out",
                    }
                    timed_out = True
                except Exception as exc:
                    try:
                        ensure_same_origin(self.page.url, origin)  # type: ignore[attr-defined]
                        after = await self._observation()
                    except Exception:
                        after = observation
                    verification = {
                        "passed": False,
                        "timed_out": type(exc).__name__ == "TimeoutError",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                    timed_out = verification["timed_out"] is True
                else:
                    timed_out = False
                timed_out = timed_out or verification.get("timed_out") is True

                recorder.record_step(
                    before=observation,
                    after=after,
                    action=action,
                    events=events.since(cursor),
                    verification=verification,
                    correction_attempt=correction_attempt,
                )
                executed_steps += 1
                if verification.get("passed") is True:
                    history.append(
                        {"action": action.to_dict(), "verification": dict(verification)}
                    )
                    observation = after
                    break

                if timed_out:
                    return RunReport(
                        "timed_out",
                        executed_steps,
                        corrections,
                        self.trace_path,
                        str(verification.get("error")),
                    )
                if correction_attempt:
                    return RunReport(
                        "failed",
                        executed_steps,
                        corrections,
                        self.trace_path,
                        str(verification.get("error", "result verification failed")),
                    )

                corrections += 1
                correction_request = self._request(
                    objective,
                    after,
                    history,
                    correction=True,
                    last_failure=verification,
                    failed_action=action.to_dict(),
                )
                try:
                    action = await self._decide(correction_request)
                except TimeoutError:
                    recorder.record_error(
                        step=step_number,
                        stage="correction_decision",
                        message="correction decision timed out",
                    )
                    return RunReport(
                        "timed_out",
                        executed_steps,
                        corrections,
                        self.trace_path,
                        "correction decision timed out",
                    )
                except Exception as exc:
                    message = f"{type(exc).__name__}: {exc}"
                    recorder.record_error(
                        step=step_number,
                        stage="correction_decision",
                        message=message,
                    )
                    return RunReport(
                        "failed", executed_steps, corrections, self.trace_path, message
                    )
                if action.action == "done":
                    return RunReport(
                        "failed",
                        executed_steps,
                        corrections,
                        self.trace_path,
                        "model returned done before the failed action was corrected",
                    )
                observation = after
                correction_attempt = True

        return RunReport(
            "step_limit",
            executed_steps,
            corrections,
            self.trace_path,
            f"maximum step count reached: {self.config.max_steps}",
        )
