import json
from pathlib import Path


ANNOTATION = (
    Path(__file__).parent
    / "fixtures"
    / "content_translation_timeline_unreviewed.json"
)


def test_tutorial_draft_is_explicitly_unreviewed_and_visual_pending():
    payload = json.loads(ANNOTATION.read_text(encoding="utf-8"))
    assert payload["annotation_status"] == "unreviewed"
    assert len(payload["steps"]) >= 8
    assert all(
        step["ui_verification_status"] == "pending_frame_review"
        for step in payload["steps"]
    )
    assert all(
        evidence["kind"] == "subtitle"
        for step in payload["steps"]
        for evidence in step["evidence_refs"]
    )
