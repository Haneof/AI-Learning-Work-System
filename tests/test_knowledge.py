"""Tests for evidence provenance, expert isolation, deduplication, and conflicts."""

from aios_work_system.knowledge import (
    ConfidenceLabel,
    EpistemicType,
    EvidenceLink,
    EvidenceRelation,
    KnowledgeItem,
    KnowledgeRegistry,
    KnowledgeState,
    KnowledgeType,
    SourceSegment,
)


def make_segment(
    segment_id="seg-1",
    expert_id="expert-a",
    text="The return window is 30 days.",
    shared_with_experts=frozenset(),
):
    return SourceSegment(
        segment_id=segment_id,
        source_id="source-1",
        expert_id=expert_id,
        locator={"page": 2},
        text_content=text,
        shared_with_experts=shared_with_experts,
    )


def make_item(
    knowledge_id="knowledge-1",
    expert_id="expert-a",
    statement="The return window is 30 days.",
    epistemic_type=EpistemicType.EXTRACTED_FACT,
    state=KnowledgeState.APPROVED,
    conflict_key="return-window",
    evidence=None,
):
    return KnowledgeItem(
        knowledge_id=knowledge_id,
        expert_id=expert_id,
        statement=statement,
        knowledge_type=KnowledgeType.RULE,
        epistemic_type=epistemic_type,
        state=state,
        confidence=ConfidenceLabel.HIGH,
        conflict_key=conflict_key,
        evidence=evidence if evidence is not None else [
            EvidenceLink(
                source_id="source-1",
                segment_id="seg-1",
                relation=EvidenceRelation.SUPPORTS,
                excerpt="30 days",
            )
        ],
    )


def test_approved_knowledge_requires_valid_supporting_evidence():
    registry = KnowledgeRegistry()
    registry.add_segment(make_segment())
    item = make_item(evidence=[])

    result = registry.add_knowledge(item)

    assert not result.accepted
    assert "approved knowledge requires at least one SUPPORTS evidence link" in result.errors


def test_direct_quote_must_exist_in_source_segment():
    registry = KnowledgeRegistry()
    registry.add_segment(make_segment())
    item = make_item(
        epistemic_type=EpistemicType.DIRECT_QUOTE,
        evidence=[
            EvidenceLink(
                source_id="source-1",
                segment_id="seg-1",
                relation=EvidenceRelation.SUPPORTS,
                excerpt="90 days",
            )
        ],
    )

    result = registry.add_knowledge(item)

    assert not result.accepted
    assert any("excerpt is not present" in error for error in result.errors)


def test_cross_expert_evidence_is_denied_without_explicit_share():
    registry = KnowledgeRegistry()
    registry.add_segment(make_segment(expert_id="expert-b"))

    result = registry.add_knowledge(make_item())

    assert not result.accepted
    assert any("crosses expert scope" in error for error in result.errors)


def test_explicitly_shared_segment_can_support_another_expert():
    registry = KnowledgeRegistry()
    registry.add_segment(
        make_segment(expert_id="expert-b", shared_with_experts=frozenset({"expert-a"}))
    )

    result = registry.add_knowledge(make_item())

    assert result.accepted


def test_duplicate_knowledge_is_deduplicated_within_expert():
    registry = KnowledgeRegistry()
    registry.add_segment(make_segment())
    first = registry.add_knowledge(make_item())
    second = registry.add_knowledge(
        make_item(knowledge_id="knowledge-2", statement="  THE return window is 30 days. ")
    )

    assert first.accepted and second.accepted
    assert second.duplicate_of == "knowledge-1"
    assert len(registry.list_for_expert("expert-a")) == 1


def test_conflicting_items_coexist_but_require_review():
    registry = KnowledgeRegistry()
    registry.add_segment(make_segment())
    registry.add_segment(
        make_segment(
            segment_id="seg-2",
            text="The return window is 60 days.",
        )
    )
    first = registry.add_knowledge(make_item())
    second = registry.add_knowledge(
        make_item(
            knowledge_id="knowledge-2",
            statement="The return window is 60 days.",
            evidence=[
                EvidenceLink(
                    source_id="source-1",
                    segment_id="seg-2",
                    relation=EvidenceRelation.SUPPORTS,
                    excerpt="60 days",
                )
            ],
        )
    )

    assert first.accepted and second.accepted
    assert second.conflict_ids == ("knowledge-1",)
    assert registry.get("knowledge-1", "expert-a").state == KnowledgeState.REVIEW_REQUIRED
    assert registry.get("knowledge-2", "expert-a").state == KnowledgeState.REVIEW_REQUIRED


def test_duplicate_id_does_not_mutate_existing_conflict_state():
    registry = KnowledgeRegistry()
    registry.add_segment(make_segment())
    registry.add_segment(
        make_segment(segment_id="seg-2", text="The return window is 60 days.")
    )
    registry.add_knowledge(make_item())
    duplicate_id = registry.add_knowledge(
        make_item(
            knowledge_id="knowledge-1",
            statement="The return window is 60 days.",
            evidence=[
                EvidenceLink(
                    source_id="source-1",
                    segment_id="seg-2",
                    relation=EvidenceRelation.SUPPORTS,
                    excerpt="60 days",
                )
            ],
        )
    )

    assert not duplicate_id.accepted
    assert registry.get("knowledge-1", "expert-a").state == KnowledgeState.APPROVED


def test_expert_cannot_read_another_experts_knowledge():
    registry = KnowledgeRegistry()
    registry.add_segment(make_segment())
    registry.add_knowledge(make_item())

    try:
        registry.get("knowledge-1", "expert-b")
    except PermissionError:
        pass
    else:
        raise AssertionError("cross-expert knowledge access must be denied")
