# ruff: noqa: I001
import json
from pathlib import Path


ANNOTATION = (
    Path(__file__).parent
    / "fixtures"
    / "content_translation_timeline_unreviewed.json"
)


def test_unreviewed_tutorial_steps_have_recovery_and_traceable_timestamps():
    payload = json.loads(ANNOTATION.read_text(encoding="utf-8"))
    assert payload["annotation_status"] == "unreviewed"
    assert len(payload["steps"]) >= 8
    timestamps = []
    for step in payload["steps"]:
        assert step["step_id"]
        assert step["goal"]
        assert step["preconditions"]
        assert step["action"]
        assert step["target"]
        assert step["expected_state"]
        assert step["recovery_strategy"]
        assert step["ui_verification_status"] == "pending_frame_review"
        assert step["evidence_refs"]
        timestamps.extend(
            evidence["timestamp_seconds"] for evidence in step["evidence_refs"]
        )
    assert timestamps == sorted(timestamps)
    duration = payload["source"]["duration_seconds"]
    assert all(0 <= timestamp < duration for timestamp in timestamps)
