"""Aggregate execution outcomes without conflating step, task, and recovery success.

Input episodes are structured simulator/model-run records. This evaluator does not
execute actions or infer missing outcomes; it validates denominators explicitly.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _validate_episode(episode: Any, index: int) -> dict[str, Any]:
    if not isinstance(episode, dict):
        raise ValueError(f"episodes[{index}] must be an object")
    required = {
        "episode_id",
        "attempted_actions",
        "successful_actions",
        "task_completed",
        "recovery_opportunity",
        "recovery_attempted",
        "recovery_succeeded",
    }
    missing = required - set(episode)
    extra = set(episode) - required
    if missing:
        raise ValueError(f"episodes[{index}] missing fields: {sorted(missing)}")
    if extra:
        raise ValueError(f"episodes[{index}] has unknown fields: {sorted(extra)}")
    if not isinstance(episode["episode_id"], str) or not episode["episode_id"].strip():
        raise ValueError(f"episodes[{index}].episode_id must be a non-empty string")

    for field in ("attempted_actions", "successful_actions"):
        value = episode[field]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"episodes[{index}].{field} must be a non-negative integer")
    if episode["successful_actions"] > episode["attempted_actions"]:
        raise ValueError(f"episodes[{index}] successful_actions exceeds attempted_actions")

    for field in ("task_completed", "recovery_opportunity", "recovery_attempted"):
        if not isinstance(episode[field], bool):
            raise ValueError(f"episodes[{index}].{field} must be boolean")

    recovered = episode["recovery_succeeded"]
    if recovered is not None and not isinstance(recovered, bool):
        raise ValueError(f"episodes[{index}].recovery_succeeded must be boolean or null")
    if episode["recovery_attempted"] and not episode["recovery_opportunity"]:
        raise ValueError(f"episodes[{index}] cannot attempt recovery without an opportunity")
    if episode["recovery_attempted"] != (recovered is not None):
        raise ValueError(
            f"episodes[{index}] recovery_succeeded must be set exactly when recovery was attempted"
        )
    if not episode["recovery_opportunity"] and episode["recovery_attempted"]:
        raise ValueError(f"episodes[{index}] has inconsistent recovery fields")
    return episode


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def evaluate(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    if set(payload) - {"benchmark_id", "episodes"}:
        raise ValueError("payload contains unknown fields")
    episodes = payload.get("episodes")
    if not isinstance(episodes, list):
        raise ValueError("payload.episodes must be a list")
    validated = [_validate_episode(item, i) for i, item in enumerate(episodes)]
    ids = [item["episode_id"] for item in validated]
    if len(ids) != len(set(ids)):
        raise ValueError("episode_id values must be unique")

    attempted = sum(item["attempted_actions"] for item in validated)
    successful = sum(item["successful_actions"] for item in validated)
    completed = sum(item["task_completed"] for item in validated)
    recovery_eligible = [item for item in validated if item["recovery_opportunity"]]
    recovery_attempted = [item for item in recovery_eligible if item["recovery_attempted"]]
    recovery_succeeded = sum(item["recovery_succeeded"] is True for item in recovery_attempted)

    return {
        "report_version": "1.0",
        "benchmark_id": payload.get("benchmark_id"),
        "episode_count": len(validated),
        "step_success_rate": _rate(successful, attempted),
        "task_completion_rate": _rate(completed, len(validated)),
        "recovery_success_rate": _rate(recovery_succeeded, len(recovery_attempted)),
        "counts": {
            "attempted_actions": attempted,
            "successful_actions": successful,
            "completed_episodes": completed,
            "recovery_opportunities": len(recovery_eligible),
            "recovery_attempted_episodes": len(recovery_attempted),
            "recovery_succeeded_episodes": recovery_succeeded,
            "recovery_not_attempted_episodes": len(recovery_eligible) - len(recovery_attempted),
        },
        "denominators": {
            "step_success_rate": "all attempted actions",
            "task_completion_rate": "all episodes",
            "recovery_success_rate": (\n                "episodes with an attempted recovery after an explicit opportunity"\n            ),
        },
        "limitations": [
            "A simulator-accepted action is not evidence of real-world UI competence.",
            "Task completion is an episode-level outcome and is not inferred from step success.",
            "Episodes without a recovery opportunity are excluded from the recovery denominator.",
            "A null rate means its denominator is zero; it is not a zero-percent result.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    report = evaluate(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
