"""Traceable knowledge and evidence contracts."""

from aios_work_system.knowledge.registry import KnowledgeRegistry, RegistryResult
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
from aios_work_system.knowledge.validation import validate_knowledge

__all__ = [
    "ConfidenceLabel",
    "EpistemicType",
    "EvidenceLink",
    "EvidenceRelation",
    "KnowledgeItem",
    "KnowledgeRegistry",
    "KnowledgeState",
    "KnowledgeType",
    "RegistryResult",
    "SourceSegment",
    "validate_knowledge",
]
