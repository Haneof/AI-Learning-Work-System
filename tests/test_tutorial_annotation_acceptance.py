# ruff: noqa: I001
import json
from pathlib import Path

from scripts.validate_tutorial_annotation import validate_annotation


DRAFT = (
    Path(__file__).parent
    / "fixtures"
    / "content_translation_timeline_unreviewed.json"
)


def _reviewed_payload():
    payload = json.loads(DRAFT.read_text(encoding="utf-8"))
    payload["annotation_status"] = "reviewed"
    payload["annotator"] = "Annotator A"
    payload["review"] = {"reviewer": "Reviewer B", "reviewed_at": "2026-11-20"}
    for step in payload["steps"]:
        step["ui_verification_status"] = "frame_verified"
        step["evidence_refs"].append(
            {
                "kind": "video_frame",
                "ref": f"artifacts/tutorial-media/frames/{step['step_id']}.jpg",
                "timestamp_seconds": 10.0,
            }
        )
    return payload


def test_unreviewed_subtitle_only_draft_is_not_accepted():
    payload = json.loads(DRAFT.read_text(encoding="utf-8"))
    errors = validate_annotation(payload)
    assert any("annotation_status" in error for error in errors)
    assert any("visual evidence" in error for error in errors)


def test_independently_reviewed_visual_annotation_is_accepted():
    assert validate_annotation(_reviewed_payload()) == []


def test_same_person_cannot_annotate_and_independently_review():
    payload = _reviewed_payload()
    payload["review"]["reviewer"] = payload["annotator"]
    assert any("independent" in error for error in validate_annotation(payload))


def test_fewer_than_eight_visual_steps_are_rejected():
    payload = _reviewed_payload()
    for step in payload["steps"][8:]:
        step["evidence_refs"] = [
            evidence for evidence in step["evidence_refs"] if evidence["kind"] != "video_frame"
        ]
    errors = validate_annotation(payload)
    assert any("at least 8 steps" in error for error in errors)
