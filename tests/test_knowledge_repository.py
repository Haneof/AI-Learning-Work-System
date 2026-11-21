"""Durability, evidence validation, and expert-scope tests for KnowledgeRepository."""

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


def _segment(
    segment_id="segment-1",
    *,
    expert_id="expert-a",
    source_id="asset-1",
    modality="asr",
    locator=None,
    text="The user selects the settings tab.",
    shared_with_experts=frozenset(),
):
    return SourceSegment(
        segment_id=segment_id,
        source_id=source_id,
        expert_id=expert_id,
        locator=locator or {"start_ms": 1000, "end_ms": 2500},
        text_content=text,
        shared_with_experts=shared_with_experts,
        modality=modality,
        artifact_ref=None,
    )


def _item(
    knowledge_id="knowledge-1",
    *,
    expert_id="expert-a",
    statement="Select the settings tab.",
    evidence=None,
    conflict_key=None,
):
    return KnowledgeItem(
        knowledge_id=knowledge_id,
        expert_id=expert_id,
        statement=statement,
        knowledge_type=KnowledgeType.PROCEDURE,
        epistemic_type=EpistemicType.INFERENCE,
        state=KnowledgeState.CANDIDATE,
        confidence=ConfidenceLabel.MEDIUM,
        version=1,
        conflict_key=conflict_key,
        evidence=evidence
        or [
            EvidenceLink(
                source_id="asset-1",
                segment_id="segment-1",
                relation=EvidenceRelation.SUPPORTS,
            )
        ],
    )


def test_segments_and_knowledge_survive_repository_reopen(tmp_path):
    database = tmp_path / "knowledge.sqlite3"
    repository = KnowledgeRepository(database)
    repository.add_segment(_segment())
    result = repository.add_knowledge(_item())

    assert result["accepted"] is True
    reopened = KnowledgeRepository(database)
    stored_segment = reopened.get_segment("segment-1", "expert-a")
    stored_item = reopened.get("knowledge-1", "expert-a")

    assert stored_segment.modality == "asr"
    assert stored_item.statement == "Select the settings tab."
    assert stored_item.state == KnowledgeState.CANDIDATE
    assert stored_item.evidence[0].segment_id == "segment-1"


def test_knowledge_cannot_be_inserted_as_approved_without_review(tmp_path):
    repository = KnowledgeRepository(tmp_path / "knowledge.sqlite3")
    repository.add_segment(_segment())
    item = _item()
    item.state = KnowledgeState.APPROVED

    with pytest.raises(ValueError, match="start in CANDIDATE"):
        repository.add_knowledge(item)


def test_human_review_is_audited_and_required_for_approval(tmp_path):
    database = tmp_path / "knowledge.sqlite3"
    repository = KnowledgeRepository(database)
    repository.add_segment(_segment())
    repository.add_knowledge(_item())

    approved = repository.review(
        "knowledge-1",
        "expert-a",
        reviewer_id="reviewer-human-1",
        decision=KnowledgeState.APPROVED,
        note="Checked the source segment and confirmed the procedure statement.",
    )
    history = repository.review_history("knowledge-1", "expert-a")

    assert approved.state == KnowledgeState.APPROVED
    assert history[0]["reviewer_id"] == "reviewer-human-1"
    assert history[0]["decision"] == "APPROVED"
    assert KnowledgeRepository(database).get("knowledge-1", "expert-a").state == (
        KnowledgeState.APPROVED
    )


def test_approval_fails_without_supporting_evidence(tmp_path):
    repository = KnowledgeRepository(tmp_path / "knowledge.sqlite3")
    repository.add_segment(_segment())
    item = _item(
        evidence=[
            EvidenceLink(
                source_id="asset-1",
                segment_id="segment-1",
                relation=EvidenceRelation.CONTEXT,
            )
        ]
    )
    repository.add_knowledge(item)

    with pytest.raises(ValueError, match="requires at least one SUPPORTS"):
        repository.review(
            "knowledge-1",
            "expert-a",
            reviewer_id="reviewer-1",
            decision=KnowledgeState.APPROVED,
            note="Review attempted without support.",
        )


def test_cross_expert_reads_and_knowledge_links_are_denied(tmp_path):
    repository = KnowledgeRepository(tmp_path / "knowledge.sqlite3")
    repository.add_segment(_segment())

    with pytest.raises(PermissionError, match="another expert"):
        repository.get_segment("segment-1", "expert-b")

    foreign_item = _item(expert_id="expert-b")
    result = repository.add_knowledge(foreign_item)
    assert result["accepted"] is False
    assert any("crosses expert scope" in error for error in result["errors"])


def test_explicit_segment_sharing_is_required_and_enforced(tmp_path):
    repository = KnowledgeRepository(tmp_path / "knowledge.sqlite3")
    repository.add_segment(
        _segment(shared_with_experts=frozenset({"expert-b"}))
    )

    shared = repository.get_segment("segment-1", "expert-b")
    assert shared.segment_id == "segment-1"
    listed = repository.list_segments("expert-b", source_id="asset-1")
    assert [segment.segment_id for segment in listed] == ["segment-1"]


def test_conflicting_items_are_retained_and_moved_to_review_required(tmp_path):
    repository = KnowledgeRepository(tmp_path / "knowledge.sqlite3")
    repository.add_segment(_segment())
    first = _item(conflict_key="settings-tab")
    repository.add_knowledge(first)
    second = _item(
        knowledge_id="knowledge-2",
        statement="Select the profile tab.",
        conflict_key="settings-tab",
    )

    result = repository.add_knowledge(second)

    assert result["accepted"] is True
    assert result["conflict_ids"] == ["knowledge-1"]
    assert repository.get("knowledge-1", "expert-a").state == (
        KnowledgeState.REVIEW_REQUIRED
    )
    assert repository.get("knowledge-2", "expert-a").state == (
        KnowledgeState.REVIEW_REQUIRED
    )


def test_duplicate_normalized_knowledge_is_idempotent(tmp_path):
    repository = KnowledgeRepository(tmp_path / "knowledge.sqlite3")
    repository.add_segment(_segment())
    repository.add_knowledge(_item())
    duplicate = _item(
        knowledge_id="knowledge-duplicate",
        statement="  SELECT   the settings tab. ",
    )

    result = repository.add_knowledge(duplicate)

    assert result["accepted"] is True
    assert result["duplicate_of"] == "knowledge-1"
    assert len(repository.list_for_expert("expert-a")) == 1


def test_segment_id_is_immutable_and_modality_is_persisted(tmp_path):
    repository = KnowledgeRepository(tmp_path / "knowledge.sqlite3")
    repository.add_segment(_segment(modality="video_frame", locator={"timestamp_ms": 1000}))
    repository.add_segment(
        _segment(modality="video_frame", locator={"timestamp_ms": 1000})
    )

    with pytest.raises(ValueError, match="cannot be reused"):
        repository.add_segment(
            _segment(text="A different claim.", modality="video_frame")
        )


def test_new_repository_migrates_existing_segment_table(tmp_path):
    import sqlite3

    database = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE knowledge_source_segments (
                segment_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                expert_id TEXT,
                locator_json TEXT NOT NULL,
                text_content TEXT NOT NULL,
                shared_with_experts_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

    repository = KnowledgeRepository(database)
    repository.add_segment(_segment())
    stored = repository.get_segment("segment-1", "expert-a")

    assert stored.modality == "text"
    assert stored.artifact_ref is None
