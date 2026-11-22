"""Real browser Hands adapter reusing the existing BrowserAgent operation loop.

A local UI-TARS-class model can implement the existing GUI DecisionModel contract
and be supplied here. This module deliberately does not instantiate or download
an operation model; see docs/BRAIN_HANDS_CLOSED_LOOP.md for the manual harness.
"""

from __future__ import annotations

import inspect
import json
import re
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any

from aios_work_system.brain_hands.engine import condition_matches, get_state_path
from aios_work_system.brain_hands.interfaces import ExecutionResult, OperationDelegation
from aios_work_system.gui.agent import AgentConfig, BrowserAgent, DecisionModel

BusinessStateObserver = Callable[[object], Awaitable[Mapping[str, Any]]]


class BrowserAgentHandsAdapter:
    """Map one Brain capability delegation onto the existing constrained BrowserAgent.

    The injected state observer is application-specific and must expose normalized
    business fields such as title.status. A browser trace or a model's done response
    alone is never considered proof of business success.
    """

    def __init__(
        self,
        page: object,
        operation_model: DecisionModel,
        state_observer: BusinessStateObserver,
        trace_dir: str | Path,
        config: AgentConfig | None = None,
    ) -> None:
        self.page = page
        self.operation_model = operation_model
        self.state_observer = state_observer
        self.trace_dir = Path(trace_dir)
        self.config = config or AgentConfig()

    async def observe(self) -> Mapping[str, Any]:
        state = self.state_observer(self.page)
        if inspect.isawaitable(state):
            state = await state
        if not isinstance(state, Mapping):
            raise TypeError("business state observer must return a mapping")
        return dict(state)

    async def execute(self, delegation: OperationDelegation) -> ExecutionResult:
        if delegation.requires_human_approval:
            return ExecutionResult(
                call_id=delegation.call_id,
                task_id=delegation.task_id,
                status="blocked",
                result_summary="The delegated operation requires human approval.",
                observed_state=dict(await self.observe()),
                postcondition_results=(),
                actions_summary=(
                    {
                        "action": delegation.capability_id,
                        "status": "skipped",
                        "detail": "Human approval was required.",
                    },
                ),
                error={
                    "category": "authorization",
                    "code": "human_approval_required",
                    "message": "Human approval was required.",
                },
            )

        self.trace_dir.mkdir(parents=True, exist_ok=True)
        safe_call_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", delegation.call_id)
        trace_path = self.trace_dir / f"{safe_call_id}.jsonl"
        objective = (
            f"Business capability: {delegation.capability_id}\n"
            f"Objective: {delegation.description}\n"
            "Arguments: "
            f"{json.dumps(dict(delegation.arguments), ensure_ascii=False, sort_keys=True)}\n"
            f"Preconditions: {json.dumps(list(delegation.preconditions), ensure_ascii=False)}\n"
            f"Expected business postconditions: "
            f"{json.dumps(list(delegation.expected_postconditions), ensure_ascii=False)}\n"
            "Perform only this delegated operation. Do not claim completion until "
            "the business postconditions are visible in the application."
        )
        report = await BrowserAgent(
            self.page,
            self.operation_model,
            str(trace_path),
            self.config,
        ).run(objective)
        state = dict(await self.observe())
        trace_ref = str(trace_path.resolve())
        evidence_refs = [trace_ref]
        postcondition_results = []
        passed_count = 0
        for condition in delegation.expected_postconditions:
            passed = condition_matches(state, condition)
            if passed:
                passed_count += 1
            postcondition_results.append(
                {
                    "condition_id": condition["condition_id"],
                    "result": "passed" if passed else "failed",
                    "observed_value": self._observed_value(state, condition),
                    "evidence_refs": [trace_ref],
                }
            )

        all_passed = passed_count == len(delegation.expected_postconditions)
        if report.status == "timed_out":
            status = "timed_out"
        elif report.status == "done" and all_passed:
            status = "succeeded"
        elif passed_count:
            status = "partially_succeeded"
        else:
            status = "failed"

        action_status = "succeeded" if report.status == "done" else "partially_succeeded"
        return ExecutionResult(
            call_id=delegation.call_id,
            task_id=delegation.task_id,
            status=status,  # type: ignore[arg-type]
            result_summary=(
                f"BrowserAgent status={report.status}; verified "
                f"{passed_count}/{len(delegation.expected_postconditions)} business postconditions."
            ),
            observed_state=state,
            postcondition_results=tuple(postcondition_results),
            actions_summary=(
                {
                    "action": "BrowserAgent",
                    "status": action_status,
                    "detail": (
                        f"steps={report.steps}; corrections={report.corrections}; "
                        f"trace={trace_ref}; error={report.error}"
                    ),
                },
            ),
            error=(
                {
                    "category": "browser_agent",
                    "code": report.status,
                    "message": report.error or "Browser operation did not complete and verify.",
                }
                if status != "succeeded"
                else None
            ),
            evidence_refs=tuple(evidence_refs),
            trace_ref=trace_ref,
        )

    @staticmethod
    def _observed_value(state: Mapping[str, Any], condition: Mapping[str, Any]) -> Any:
        value = get_state_path(state, str(condition.get("path", "")))
        return None if value.__class__ is object else value
