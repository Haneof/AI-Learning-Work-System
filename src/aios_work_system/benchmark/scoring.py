"""Transparent deterministic checks; no subjective model grading is performed."""

from __future__ import annotations

import json
from typing import Any


def score_output(output: str, checks: dict[str, Any]) -> dict[str, bool]:
    results: dict[str, bool] = {}
    required = checks.get("contains_all", [])
    if required:
        results["contains_all"] = all(str(item) in output for item in required)

    if checks.get("valid_json_object"):
        try:
            parsed = json.loads(output)
            results["valid_json_object"] = isinstance(parsed, dict)
        except json.JSONDecodeError:
            results["valid_json_object"] = False

    if checks.get("non_empty"):
        results["non_empty"] = bool(output.strip())

    return results
