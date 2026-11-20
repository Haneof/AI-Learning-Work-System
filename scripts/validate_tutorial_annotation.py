#!/usr/bin/env python3
"""Validate that a tutorial annotation has enough independently reviewed UI evidence."""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

MINIMUM_VERIFIED_STEPS = 8
VISUAL_EVIDENCE_KINDS = {"video_frame", "ui_snapshot"}


def validate_annotation(payload: dict[str, Any]) -> list[str]:
    """Return acceptance errors; an empty list means reviewed ground truth is acceptable."""
    errors: list[str] = []
    if payload.get("annotation_status") != "reviewed":
        errors.append("annotation_status must be 'reviewed'")

    review = payload.get("review")
    if not isinstance(review, dict):
        errors.append("review metadata is required")
        review = {}
    if not str(review.get("reviewer", "")).strip():
        errors.append("review.reviewer is required")
    reviewed_at = review.get("reviewed_at")
    try:
        date.fromisoformat(str(reviewed_at))
    except (TypeError, ValueError):
        errors.append("review.reviewed_at must be an ISO date (YYYY-MM-DD)")

    annotator = payload.get("annotator")
    reviewer = review.get("reviewer")
    same_reviewer = (
        annotator
        and reviewer
        and str(annotator).strip().casefold() == str(reviewer).strip().casefold()
    )
    if same_reviewer:
        errors.append("reviewer must be independent from the annotator")

    steps = payload.get("steps")
    if not isinstance(steps, list) or not steps:
        errors.append("steps must be a non-empty list")
        return errors

    visually_verified = 0
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            errors.append(f"step {index} must be an object")
            continue
        step_id = str(step.get("step_id", f"step-{index}"))
        if step.get("ui_verification_status") != "frame_verified":
            errors.append(f"{step_id}: ui_verification_status must be 'frame_verified'")
        evidence_refs = step.get("evidence_refs", [])
        has_visual_evidence = any(
            isinstance(evidence, dict)
            and evidence.get("kind") in VISUAL_EVIDENCE_KINDS
            and str(evidence.get("ref", "")).strip()
            and isinstance(evidence.get("timestamp_seconds"), (int, float))
            and evidence["timestamp_seconds"] >= 0
            for evidence in evidence_refs
        )
        if has_visual_evidence:
            visually_verified += 1
        else:
            errors.append(f"{step_id}: timestamped video_frame or ui_snapshot evidence is required")

    if visually_verified < MINIMUM_VERIFIED_STEPS:
        errors.append(
            f"at least {MINIMUM_VERIFIED_STEPS} steps need timestamped visual evidence; "
            f"found {visually_verified}"
        )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "annotation",
        nargs="?",
        type=Path,
        default=Path("tests/fixtures/content_translation_timeline_unreviewed.json"),
    )
    args = parser.parse_args()
    payload = json.loads(args.annotation.read_text(encoding="utf-8"))
    errors = validate_annotation(payload)
    if errors:
        print("ANNOTATION NOT ACCEPTED")
        for error in errors:
            print(f"- {error}")
        return 1
    print("ANNOTATION ACCEPTED AS REVIEWED GROUND TRUTH")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
