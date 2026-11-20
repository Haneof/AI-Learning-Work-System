#!/usr/bin/env python3
"""Evaluate extracted procedural steps against a human-authored reference.

Matching is deliberately conservative: action and target must both match exactly.
Evidence completeness is scored separately and cannot turn an unmatched step into
a correct one. This evaluator does not claim task execution capability.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _steps(payload: dict[str, Any]) -> list[dict[str, Any]]:
    steps = payload.get("steps")
    if not isinstance(steps, list):
        raise ValueError("payload.steps must be a list")
    return steps


def _key(step: dict[str, Any]) -> tuple[str, str]:
    return (str(step.get("action", "")).strip().casefold(),
            str(step.get("target", "")).strip().casefold())


def evaluate(reference: dict[str, Any], prediction: dict[str, Any]) -> dict[str, Any]:
    refs = _steps(reference)
    preds = _steps(prediction)
    ref_keys = [_key(s) for s in refs]
    pred_keys = [_key(s) for s in preds]

    # Greedy one-to-one matching preserves duplicate-step accounting.
    unmatched = list(range(len(refs)))
    pairs: list[tuple[int, int]] = []
    for pi, key in enumerate(pred_keys):
        match = next((ri for ri in unmatched if ref_keys[ri] == key), None)
        if match is not None:
            unmatched.remove(match)
            pairs.append((match, pi))

    tp = len(pairs)
    precision = tp / len(preds) if preds else 0.0
    recall = tp / len(refs) if refs else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    ordered_pairs = sorted(pairs, key=lambda pair: pair[1])
    ref_positions = [ri for ri, _ in ordered_pairs]
    order_accuracy = (sum(a < b for a, b in zip(ref_positions, ref_positions[1:])) /
                      (len(ref_positions) - 1)) if len(ref_positions) > 1 else (1.0 if tp else 0.0)

    def valid_evidence(ev: Any) -> bool:
        return (
            isinstance(ev, dict)
            and bool(ev.get("ref"))
            and isinstance(ev.get("timestamp_seconds"), (int, float))
            and ev.get("timestamp_seconds") >= 0
        )

    evidence_complete = sum(
        bool(step.get("evidence_refs"))
        and all(valid_evidence(ev) for ev in step.get("evidence_refs", []))
        for step in preds
    )
    evidence_rate = evidence_complete / len(preds) if preds else 0.0

    ui_evidence_complete = sum(
        any(
            valid_evidence(ev) and ev.get("kind") in {"video_frame", "ui_snapshot"}
            for ev in step.get("evidence_refs", [])
        )
        for step in preds
    )
    ui_evidence_rate = ui_evidence_complete / len(preds) if preds else 0.0

    state_correct = sum(
        str(preds[pi].get("expected_state", "")).strip().casefold()
        == str(refs[ri].get("expected_state", "")).strip().casefold()
        for ri, pi in pairs
    )
    state_accuracy = state_correct / tp if tp else 0.0

    return {
        "report_version": "1.0",
        "reference_annotation_status": reference.get("annotation_status", "unspecified"),
        "prediction_source_id": prediction.get("source_id"),
        "counts": {"reference_steps": len(refs), "predicted_steps": len(preds),
                   "matched_steps": tp, "missed_reference_steps": len(refs) - tp,
                   "unmatched_prediction_steps": len(preds) - tp},
        "extraction": {"precision": round(precision, 4), "recall": round(recall, 4),
                       "f1": round(f1, 4)},
        "order_accuracy": round(order_accuracy, 4),
        "expected_state_accuracy_on_matched_steps": round(state_accuracy, 4),
        "evidence_completeness": round(evidence_rate, 4),
        "ui_evidence_completeness": round(ui_evidence_rate, 4),
        "matched_pairs": [{"reference_index": ri, "prediction_index": pi} for ri, pi in pairs],
        "limitations": [
            "Exact action/target matching is conservative and does not perform "
            "semantic equivalence.",
            "This report measures step extraction only; it does not measure UI "
            "execution or task success.",
            "Synthetic or unreviewed reference annotations are not authoritative ground truth."
        ]
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--prediction", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    reference = json.loads(args.reference.read_text(encoding="utf-8"))
    prediction = json.loads(args.prediction.read_text(encoding="utf-8"))
    report = evaluate(reference, prediction)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
