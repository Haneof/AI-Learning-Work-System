"""Evidence gates for deterministic procedural skill compilation."""

import json

import pytest

from aios_work_system.knowledge.repository import KnowledgeRepository
from aios_work_system.knowledge.types import (
    ConfidenceLabel,
    EpistemicType,
    EvidenceLink,
    EvidenceRelation,
    KnowledgeItem,
    KnowledgeState,
    KnowledgeType,
    SourceSegment,
)
from aios_work_system.skills.compiler import (
    ProceduralSkillCompiler,
    ProcedureSkillSpec,
)
from aios_work_system.skills.repository import SkillVersionRepository
from aios_work_system.skills.validator import validate_skill_package


def _segment(segment_id, *, modality, locator, text):
    return SourceSegment(
        segment_id=segment_id,
        source_id="asset-tutorial-1",
        expert_id="expert-office",
        locator=locator,
        text_content=text,
        modality=modality,
        artifact_ref=f"/derived/{segment_id}",
    )


def _approved_knowledge(tmp_path, *, visual_frames=8):
    knowledge = KnowledgeRepository(tmp_path / "knowledge.sqlite3")
    evidence_segments = [
        _segment(
            "asr-1",
            modality="asr",
            locator={"start_ms": 0, "end_ms": 2500},
            text="Open the settings menu.",
        )
    ]
    evidence_segments.extend(
        _segment(
            f"frame-{index}",
            modality="video_frame",
            locator={"timestamp_ms": index * 1000},
            text="Visual frame evidence. Human review required.",
        )
        for index in range(visual_frames)
    )
    for segment in evidence_segments:
        knowledge.add_segment(segment)
    item = KnowledgeItem(
        knowledge_id="knowledge-open-settings",
        expert_id="expert-office",
        statement="Open the settings menu before changing account preferences.",
        knowledge_type=KnowledgeType.PROCEDURE,
        epistemic_type=EpistemicType.INFERENCE,
        state=KnowledgeState.CANDIDATE,
        confidence=ConfidenceLabel.HIGH,
        version=1,
        evidence=[
            EvidenceLink(
                source_id=segment.source_id,
                segment_id=segment.segment_id,
                relation=EvidenceRelation.SUPPORTS,
            )
            for segment in evidence_segments
        ],
    )
    added = knowledge.add_knowledge(item)
    assert added["accepted"] is True
    knowledge.review(
        item.knowledge_id,
        "expert-office",
        reviewer_id="knowledge-reviewer",
        decision=KnowledgeState.APPROVED,
        note="Reviewed evidence links and confirmed the supported procedure claim.",
    )
    return knowledge


def _step(index, *, visual=False, status="frame_verified"):
    evidence = (
        {
            "kind": "video_frame",
            "ref": f"frame-{index}",
            "timestamp_seconds": float(index),
        }
        if visual
        else {
            "kind": "asr_segment",
            "ref": "asr-1",
            "timestamp_seconds": 1.0,
        }
    )
    return {
        "step_id": f"step-{index}",
        "knowledge_id": "knowledge-open-settings",
        "goal": f"Complete procedure step {index}.",
        "preconditions": ["The tutorial application is open."],
        "action": "click",
        "target": f"tutorial control {index}",
        "expected_state": f"Control {index} is selected.",
        "evidence_refs": [evidence],
        "recovery_strategy": "Return to the previous stable screen and retry once.",
        "ui_verification_status": status,
    }


def _spec(*, annotation_status="unreviewed", steps=None):
    reviewed = annotation_status == "reviewed"
    return ProcedureSkillSpec(
        expert_id="expert-office",
        skill_id="office.account-settings",
        version="1.0.0",
        title="Account settings procedure",
        goal="Navigate to the account settings area.",
        scope="Office application account management.",
        source_id="asset-tutorial-1",
        knowledge_ids=("knowledge-open-settings",),
        steps=tuple(steps if steps is not None else [_step(1, visual=False)]),
        annotation_status=annotation_status,
        annotator_id="annotator-1" if reviewed else None,
        reviewer_id="independent-reviewer" if reviewed else None,
        reviewed_at="2026-11-21T10:00:00+08:00" if reviewed else None,
    )



def _record_review(compiler, spec, *, reviewer_id="independent-reviewer"):
    from dataclasses import replace

    reviewable = replace(spec, reviewer_id=None, reviewed_at=None, review_id=None)
    record = compiler.review_spec(
        reviewable,
        reviewer_id=reviewer_id,
        decision="APPROVED",
        note="Reviewed the exact procedure and its linked visual evidence.",
    )
    return replace(reviewable, review_id=record.review_id)


def test_asr_only_compile_produces_unregistered_draft(tmp_path):
    knowledge = _approved_knowledge(tmp_path, visual_frames=0)
    versions = SkillVersionRepository(tmp_path / "skills.sqlite3")
    compiler = ProceduralSkillCompiler(knowledge, versions)
    output = tmp_path / "packages" / "account-settings"

    result = compiler.compile(_spec(), output)
    procedure = json.loads((output / "procedure.json").read_text(encoding="utf-8"))
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    validation = validate_skill_package(output)

    assert result.lifecycle_status == "DRAFT"
    assert result.registered is False
    assert result.execution_status == "SPEC_ONLY"
    assert procedure["steps"][0]["ui_verification_status"] == "pending_frame_review"
    assert manifest["lifecycle_status"] == "DRAFT"
    assert manifest["execution_status"] == "SPEC_ONLY"
    assert validation.passed is True
    assert versions.list_for_expert("expert-office") == []


def test_unreviewed_caller_cannot_promote_step_by_setting_frame_verified(tmp_path):
    knowledge = _approved_knowledge(tmp_path, visual_frames=1)
    compiler = ProceduralSkillCompiler(
        knowledge, SkillVersionRepository(tmp_path / "skills.sqlite3")
    )

    result = compiler.compile(
        _spec(steps=[_step(0, visual=True, status="frame_verified")]),
        tmp_path / "draft",
    )
    procedure = json.loads(
        (tmp_path / "draft" / "procedure.json").read_text(encoding="utf-8")
    )

    assert result.annotation_status == "unreviewed"
    assert procedure["steps"][0]["ui_verification_status"] == "pending_frame_review"


def test_reviewed_skill_requires_eight_visually_verified_steps_and_registers(tmp_path):
    knowledge = _approved_knowledge(tmp_path, visual_frames=8)
    versions = SkillVersionRepository(tmp_path / "skills.sqlite3")
    compiler = ProceduralSkillCompiler(knowledge, versions)
    reviewed_steps = [_step(index, visual=True) for index in range(8)]

    reviewed_spec = _record_review(
        compiler,
        _spec(annotation_status="reviewed", steps=reviewed_steps),
    )
    result = compiler.compile(reviewed_spec, tmp_path / "reviewed-skill")
    stored = SkillVersionRepository(tmp_path / "skills.sqlite3").get(
        "expert-office", "office.account-settings", "1.0.0"
    )
    procedure = json.loads(
        (tmp_path / "reviewed-skill" / "procedure.json").read_text(encoding="utf-8")
    )

    assert result.lifecycle_status == "REVIEWED"
    assert result.registered is True
    assert all(
        step["ui_verification_status"] == "frame_verified"
        for step in procedure["steps"]
    )
    assert procedure["review"]["reviewer_id"] == "independent-reviewer"
    assert stored.package_hash == result.package_hash
    assert stored.lifecycle_status == "REVIEWED"


def test_reviewed_skill_rejects_asr_only_evidence(tmp_path):
    knowledge = _approved_knowledge(tmp_path, visual_frames=0)
    compiler = ProceduralSkillCompiler(
        knowledge, SkillVersionRepository(tmp_path / "skills.sqlite3")
    )
    steps = [_step(index, visual=False) for index in range(8)]

    reviewable = _spec(annotation_status="reviewed", steps=steps)
    from dataclasses import replace

    reviewable = replace(reviewable, reviewer_id=None, reviewed_at=None)
    with pytest.raises(ValueError, match="requires visual frame/UI evidence"):
        compiler.review_spec(
            reviewable,
            reviewer_id="independent-reviewer",
            decision="APPROVED",
            note="Attempted review of narration-only steps.",
        )


def test_reviewed_skill_requires_independent_annotator_and_review_date(tmp_path):
    knowledge = _approved_knowledge(tmp_path, visual_frames=8)
    compiler = ProceduralSkillCompiler(
        knowledge, SkillVersionRepository(tmp_path / "skills.sqlite3")
    )
    spec = _spec(
        annotation_status="reviewed",
        steps=[_step(index, visual=True) for index in range(8)],
    )
    from dataclasses import replace

    spec = replace(spec, reviewer_id=None, reviewed_at=None)
    with pytest.raises(ValueError, match="differ from annotator"):
        compiler.review_spec(
            spec,
            reviewer_id="annotator-1",
            decision="APPROVED",
            note="Self-review should be denied.",
        )


def test_evidence_reference_must_match_timestamp_and_approved_source(tmp_path):
    knowledge = _approved_knowledge(tmp_path, visual_frames=1)
    compiler = ProceduralSkillCompiler(
        knowledge, SkillVersionRepository(tmp_path / "skills.sqlite3")
    )
    bad_step = _step(0, visual=True)
    bad_step["evidence_refs"][0]["timestamp_seconds"] = 42.0

    with pytest.raises(ValueError, match="timestamp does not match"):
        compiler.compile(
            _spec(steps=[bad_step]),
            tmp_path / "bad-timestamp",
        )


def test_package_output_is_not_overwritten(tmp_path):
    knowledge = _approved_knowledge(tmp_path, visual_frames=0)
    compiler = ProceduralSkillCompiler(
        knowledge, SkillVersionRepository(tmp_path / "skills.sqlite3")
    )
    output = tmp_path / "draft"
    output.mkdir()

    with pytest.raises(FileExistsError):
        compiler.compile(_spec(), output)
