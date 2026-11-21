"""Typed records and controlled enums for traceable knowledge."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class KnowledgeType(StrEnum):
    FACT = "FACT"
    CONCEPT = "CONCEPT"
    PROCEDURE = "PROCEDURE"
    RULE = "RULE"
    EXCEPTION = "EXCEPTION"
    RISK = "RISK"


class EpistemicType(StrEnum):
    DIRECT_QUOTE = "DIRECT_QUOTE"
    EXTRACTED_FACT = "EXTRACTED_FACT"
    INFERENCE = "INFERENCE"
    RECOMMENDATION = "RECOMMENDATION"


class EvidenceRelation(StrEnum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    CONTEXT = "CONTEXT"


class KnowledgeState(StrEnum):
    CANDIDATE = "CANDIDATE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    APPROVED = "APPROVED"
    SUPERSEDED = "SUPERSEDED"
    REJECTED = "REJECTED"


class ConfidenceLabel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass(frozen=True)
class SourceSegment:
    segment_id: str
    source_id: str
    expert_id: str | None
    locator: dict[str, int]
    text_content: str
    shared_with_experts: frozenset[str] = frozenset()
    modality: str = "text"
    artifact_ref: str | None = None


@dataclass(frozen=True)
class EvidenceLink:
    source_id: str
    segment_id: str
    relation: EvidenceRelation
    excerpt: str | None = None


@dataclass
class KnowledgeItem:
    knowledge_id: str
    expert_id: str
    statement: str
    knowledge_type: KnowledgeType
    epistemic_type: EpistemicType
    state: KnowledgeState = KnowledgeState.CANDIDATE
    confidence: ConfidenceLabel = ConfidenceLabel.MEDIUM
    version: int = 1
    conflict_key: str | None = None
    evidence: list[EvidenceLink] = field(default_factory=list)
    content_hash: str = ""
