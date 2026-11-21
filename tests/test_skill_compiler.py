"""Evidence gates for deterministic knowledge package compilation."""

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


def _approved_knowledge(tmp_path, *, visual_frames=8, knowledge_type=KnowledgeType.PROCEDURE):
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
        knowledge_type=knowledge_type,
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
        note="Reviewed evidence links and confirmed the supported knowledge claim.",
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
        "goal": f"Reference step {index}; not a mandatory instruction.",
        "preconditions": ["The application is available."],
        "action": "Select the relevant settings control when appropriate.",
        "target": f"settings control {index}",
        "expected_state": f"Relevant setting {index} is visible.",
        "evidence_refs": [evidence],
        "recovery_strategy": "Return to a verified state and reassess.",
        "ui_verification_status": status,
    }


def _spec(*, annotation_status="unreviewed", suggested_steps=None, evidence_refs=None):
    selected_steps = (
        list(suggested_steps) if suggested_steps is not None else [_step(1, visual=False)]
    )
    if evidence_refs is None:
        evidence_refs = [
            reference for step in selected_steps for reference in step.get("evidence_refs", [])
        ]
    reviewed = annotation_status == "reviewed"
    return ProcedureSkillSpec(
        expert_id="expert-office",
        skill_id="office.account-settings",
        version="1.0.0",
        title="Account settings knowledge",
        purpose="Choose a safe way to reach and verify account settings.",
        scope="Office application account management.",
        source_id="asset-tutorial-1",
        knowledge_ids=("knowledge-open-settings",),
        conditions={
            "applicable_when": ["The user has permission to manage account settings."],
            "not_applicable_when": ["The account is locked or access is not authorized."],
        },
        judgement_criteria=(
            "The selected setting is visible in the intended account context.",
            "The resulting state is independently observable.",
        ),
        experience={
            "success": ["Confirm the resulting state after any change."],
            "failure": ["A hidden or ambiguous control is not proof of success."],
        },
        counterexamples=("A click animation is not evidence that the setting changed.",),
        recovery=(
            "Stop when the observed state differs from the expected state.",
            "Return to a known state and reassess before trying another approach.",
        ),
        evidence_refs=tuple(evidence_refs),
        suggested_steps=tuple(selected_steps),
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
        note="Reviewed the knowledge content and its linked evidence.",
    )
    return replace(reviewable, review_id=record.review_id)


def test_asr_only_compile_produces_unregistered_knowledge_package(tmp_path):
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
    assert procedure["suggested_steps"][0]["ui_verification_status"] == "pending_frame_review"
    assert procedure["schema_version"] == "2.0"
    assert procedure["evidence_refs"]
    assert "steps" not in procedure
    assert manifest["purpose"].startswith("Choose a safe way")
    assert manifest["conditions"]["not_applicable_when"]
    assert manifest["experience"]["failure"]
    assert validation.passed is True
    assert versions.list_for_expert("expert-office") == []
    assert (output / "SKILL.md").is_file()
    assert (output / "manifest.json").is_file()
    assert (output / "procedure.json").is_file()
    assert (output / "tests" / "test_knowledge_contract.py").is_file()
    assert (output / "references" / "evidence_manifest.json").is_file()


def test_knowledge_package_compiles_without_any_suggested_steps(tmp_path):
    knowledge = _approved_knowledge(tmp_path, visual_frames=0)
    compiler = ProceduralSkillCompiler(
        knowledge, SkillVersionRepository(tmp_path / "skills.sqlite3")
    )
    spec = _spec(
        suggested_steps=[],
        evidence_refs=[
            {
                "kind": "asr_segment",
                "ref": "asr-1",
                "timestamp_seconds": 1.0,
            }
        ],
    )

    result = compiler.compile(spec, tmp_path / "knowledge-only")
    procedure = json.loads(
        (tmp_path / "knowledge-only" / "procedure.json").read_text(encoding="utf-8")
    )

    assert result.lifecycle_status == "DRAFT"
    assert procedure["suggested_steps"] == []


def test_approved_rule_knowledge_can_be_compiled_not_only_procedure_items(tmp_path):
    knowledge = _approved_knowledge(
        tmp_path,
        visual_frames=0,
        knowledge_type=KnowledgeType.RULE,
    )
    compiler = ProceduralSkillCompiler(
        knowledge, SkillVersionRepository(tmp_path / "skills.sqlite3")
    )

    result = compiler.compile(_spec(), tmp_path / "rule-knowledge")

    assert result.execution_status == "SPEC_ONLY"


def test_unreviewed_caller_cannot_promote_suggested_step_by_setting_frame_verified(tmp_path):
    knowledge = _approved_knowledge(tmp_path, visual_frames=1)
    compiler = ProceduralSkillCompiler(
        knowledge, SkillVersionRepository(tmp_path / "skills.sqlite3")
    )

    result = compiler.compile(
        _spec(suggested_steps=[_step(0, visual=True, status="frame_verified")]),
        tmp_path / "draft",
    )
    procedure = json.loads((tmp_path / "draft" / "procedure.json").read_text(encoding="utf-8"))

    assert result.annotation_status == "unreviewed"
    assert procedure["suggested_steps"][0]["ui_verification_status"] == "pending_frame_review"


def test_reviewed_knowledge_package_with_one_reference_step_registers(tmp_path):
    knowledge = _approved_knowledge(tmp_path, visual_frames=1)
    versions = SkillVersionRepository(tmp_path / "skills.sqlite3")
    compiler = ProceduralSkillCompiler(knowledge, versions)
    reviewed_spec = _record_review(
        compiler,
        _spec(
            annotation_status="reviewed",
            suggested_steps=[_step(0, visual=True)],
        ),
    )

    result = compiler.compile(reviewed_spec, tmp_path / "reviewed-knowledge")
    stored = SkillVersionRepository(tmp_path / "skills.sqlite3").get(
        "expert-office", "office.account-settings", "1.0.0"
    )
    procedure = json.loads(
        (tmp_path / "reviewed-knowledge" / "procedure.json").read_text(encoding="utf-8")
    )

    assert result.lifecycle_status == "REVIEWED"
    assert result.registered is True
    assert procedure["suggested_steps"][0]["ui_verification_status"] == "frame_verified"
    assert procedure["review"]["reviewer_id"] == "independent-reviewer"
    assert stored.package_hash == result.package_hash
    assert stored.lifecycle_status == "REVIEWED"


def test_reviewed_knowledge_package_rejects_asr_only_evidence(tmp_path):
    knowledge = _approved_knowledge(tmp_path, visual_frames=0)
    compiler = ProceduralSkillCompiler(
        knowledge, SkillVersionRepository(tmp_path / "skills.sqlite3")
    )
    reviewable = _spec(annotation_status="reviewed")

    with pytest.raises(ValueError, match="requires visual frame/UI evidence"):
        compiler.review_spec(
            reviewable,
            reviewer_id="independent-reviewer",
            decision="APPROVED",
            note="Attempted review with narration-only evidence.",
        )


def test_reviewed_knowledge_package_requires_independent_annotator(tmp_path):
    knowledge = _approved_knowledge(tmp_path, visual_frames=1)
    compiler = ProceduralSkillCompiler(
        knowledge, SkillVersionRepository(tmp_path / "skills.sqlite3")
    )
    spec = _spec(
        annotation_status="reviewed",
        suggested_steps=[_step(0, visual=True)],
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
            _spec(suggested_steps=[bad_step]),
            tmp_path / "bad-timestamp",
        )


def test_evidence_must_be_linked_as_supports_not_only_present_in_source(tmp_path):
    knowledge = _approved_knowledge(tmp_path, visual_frames=0)
    knowledge.add_segment(
        _segment(
            "context-only",
            modality="asr",
            locator={"start_ms": 0, "end_ms": 2500},
            text="Context segment is not supporting evidence.",
        )
    )
    compiler = ProceduralSkillCompiler(
        knowledge, SkillVersionRepository(tmp_path / "skills.sqlite3")
    )

    with pytest.raises(ValueError, match="linked as SUPPORTS"):
        compiler.compile(
            _spec(
                suggested_steps=[],
                evidence_refs=[
                    {
                        "kind": "asr_segment",
                        "ref": "context-only",
                        "timestamp_seconds": 1.0,
                    }
                ],
            ),
            tmp_path / "context-only",
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


def test_compiler_rejects_content_changed_after_spec_bound_review(tmp_path):
    from dataclasses import replace

    knowledge = _approved_knowledge(tmp_path, visual_frames=1)
    compiler = ProceduralSkillCompiler(
        knowledge, SkillVersionRepository(tmp_path / "skills.sqlite3")
    )
    reviewed_spec = _record_review(
        compiler,
        _spec(
            annotation_status="reviewed",
            suggested_steps=[_step(0, visual=True)],
        ),
    )
    changed_steps = list(reviewed_spec.suggested_steps)
    changed_steps[0] = {
        **changed_steps[0],
        "target": "a different UI element",
    }
    tampered = replace(reviewed_spec, suggested_steps=tuple(changed_steps))

    with pytest.raises(ValueError, match="differs from the reviewed spec hash"):
        compiler.compile(tampered, tmp_path / "tampered-knowledge")
