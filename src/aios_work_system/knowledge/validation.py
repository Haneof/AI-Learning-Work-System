"""Evidence integrity and expert-scope validation."""

from __future__ import annotations

import hashlib
import re

from aios_work_system.knowledge.types import (
    EpistemicType,
    EvidenceRelation,
    KnowledgeItem,
    KnowledgeState,
    SourceSegment,
)


def normalize_statement(statement: str) -> str:
    return re.sub(r"\s+", " ", statement).strip().casefold()


def statement_hash(statement: str) -> str:
    normalized = normalize_statement(statement)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _valid_locator(locator: dict[str, int]) -> bool:
    if not isinstance(locator, dict) or not locator:
        return False

    allowed_keys = {"page", "start_ms", "end_ms", "timestamp_ms"}
    if set(locator) - allowed_keys:
        return False
    if any(isinstance(value, bool) or not isinstance(value, int) for value in locator.values()):
        return False

    if "page" in locator and locator["page"] < 1:
        return False
    if ("start_ms" in locator) != ("end_ms" in locator):
        return False
    if "start_ms" in locator and (
        locator["start_ms"] < 0 or locator["end_ms"] <= locator["start_ms"]
    ):
        return False
    if "timestamp_ms" in locator and locator["timestamp_ms"] < 0:
        return False

    return bool(locator)


def validate_knowledge(
    item: KnowledgeItem,
    segments: dict[str, SourceSegment],
) -> list[str]:
    errors: list[str] = []
    if not item.knowledge_id.strip():
        errors.append("knowledge_id is required")
    if not item.expert_id.strip():
        errors.append("expert_id is required")
    if not item.statement.strip():
        errors.append("statement is required")
    if item.version < 1:
        errors.append("version must be at least 1")

    supporting_count = 0
    for index, evidence in enumerate(item.evidence):
        segment = segments.get(evidence.segment_id)
        if segment is None:
            errors.append(f"evidence[{index}] references an unknown source segment")
            continue
        if segment.source_id != evidence.source_id:
            errors.append(f"evidence[{index}] source_id does not match its segment")
        if segment.expert_id != item.expert_id:
            if item.expert_id not in segment.shared_with_experts:
                errors.append(f"evidence[{index}] crosses expert scope without explicit sharing")
        if not _valid_locator(segment.locator):
            errors.append(f"evidence[{index}] source locator is invalid")
        if evidence.relation == EvidenceRelation.SUPPORTS:
            supporting_count += 1
        if evidence.excerpt and evidence.excerpt not in segment.text_content:
            errors.append(f"evidence[{index}] excerpt is not present in source text")

    if item.state == KnowledgeState.APPROVED and supporting_count == 0:
        errors.append("approved knowledge requires at least one SUPPORTS evidence link")
    if item.epistemic_type == EpistemicType.DIRECT_QUOTE:
        has_verifiable_quote = any(
            evidence.relation == EvidenceRelation.SUPPORTS
            and evidence.excerpt
            and evidence.segment_id in segments
            and evidence.excerpt in segments[evidence.segment_id].text_content
            for evidence in item.evidence
        )
        if not has_verifiable_quote:
            errors.append("DIRECT_QUOTE requires a verifiable SUPPORTS excerpt")
    return errors
