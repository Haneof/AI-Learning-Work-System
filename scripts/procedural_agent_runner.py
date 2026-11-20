"""Bounded orchestration loop for a model proposing simulator actions.

The runner is provider-agnostic: callers supply a function that accepts a prompt and
returns raw model text. No network client or model dependency is bundled.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from scripts.procedural_action_protocol import (
    ALLOWED_ACTIONS,
    ALLOWED_TARGETS,
    ActionProposalError,
    execute_proposal,
)
from scripts.procedural_simulator import MockTranslationApp

ModelCall = Callable[[str], str]


def build_prompt(snapshot: dict[str, Any], step_index: int) -> str:
    """Build a compact, state-grounded prompt for exactly one next action."""
    contract = {
        "action": sorted(ALLOWED_ACTIONS),
        "target": sorted(ALLOWED_TARGETS),
        "required_fields": ["action", "target"],
        "optional_fields": ["value"],
    }
    return (
        "You control a deterministic local translation-app simulator. "
        "Choose exactly one next action that advances the task safely. "
        "Return only one JSON object, with no markdown or explanation. "
        "If the task is complete, return {\"action\":\"stop\",\"target\":\"task\"}.\n"
        f"Step index: {step_index}\n"
        f"Current state: {json.dumps(snapshot, ensure_ascii=False, sort_keys=True)}\n"
        f"Allowed proposal contract: {json.dumps(contract, sort_keys=True)}"
    )


def parse_proposal(raw: str) -> dict[str, Any] | None:
    """Parse one exact JSON object; return None only for the explicit stop signal."""
    if not isinstance(raw, str):
        raise ActionProposalError("Model response must be text")
    try:
        proposal = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ActionProposalError(f"Model response is not strict JSON: {exc.msg}") from exc
    if not isinstance(proposal, dict):
        raise ActionProposalError("Model response must be a JSON object")
    if proposal == {"action": "stop", "target": "task"}:
        return None
    return proposal


def run_agent(
    app: MockTranslationApp,
    model_call: ModelCall,
    *,
    max_steps: int = 20,
) -> dict[str, Any]:
    """Run at most max_steps model proposals and return auditable episode data."""
    if isinstance(max_steps, bool) or not isinstance(max_steps, int) or max_steps < 1:
        raise ValueError("max_steps must be a positive integer")

    events: list[dict[str, Any]] = []
    attempted = 0
    successful = 0
    stop_reason = "max_steps_reached"

    for step_index in range(max_steps):
        prompt = build_prompt(app.snapshot(), step_index)
        try:
            raw = model_call(prompt)
        except Exception as exc:  # Provider failures are recorded, not hidden.
            stop_reason = "model_call_error"
            events.append({
                "step": step_index,
                "status": "model_error",
                "error": f"{type(exc).__name__}: {exc}",
            })
            break

        attempted += 1
        try:
            proposal = parse_proposal(raw)
            if proposal is None:
                attempted -= 1
                stop_reason = "model_requested_stop"
                events.append({"step": step_index, "status": "stopped"})
                break
            result = execute_proposal(app, proposal)
        except ActionProposalError as exc:
            events.append({
                "step": step_index,
                "status": "rejected",
                "raw_response": raw,
                "error": str(exc),
            })
            continue

        successful += 1
        events.append({
            "step": step_index,
            "status": "executed",
            "proposal": proposal,
            "result": result,
        })
        if app.state == "published_mock":
            stop_reason = "task_completed"
            break

    completed = app.state == "published_mock"
    return {
        "episode_id": "runtime-episode",
        "attempted_actions": attempted,
        "successful_actions": successful,
        "task_completed": completed,
        "recovery_opportunity": False,
        "recovery_attempted": False,
        "recovery_succeeded": None,
        "stop_reason": stop_reason,
        "final_state": app.snapshot(),
        "events": events,
        "limitations": [
            "No real model provider is bundled; model_call must be supplied by the caller.",
            "The simulator is deterministic and local; no browser or external UI is controlled.",
            "Recovery metrics are not measured by this runner because no recovery event is injected.",
        ],
    }
