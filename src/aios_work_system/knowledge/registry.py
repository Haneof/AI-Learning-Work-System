"""In-memory MVP registry with deduplication and conflict coexistence."""

from __future__ import annotations

import copy
from dataclasses import dataclass

from aios_work_system.knowledge.types import KnowledgeItem, KnowledgeState, SourceSegment
from aios_work_system.knowledge.validation import statement_hash, validate_knowledge


@dataclass(frozen=True)
class RegistryResult:
    accepted: bool
    item_id: str | None
    duplicate_of: str | None = None
    conflict_ids: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


class KnowledgeRegistry:
    def __init__(self) -> None:
        self._segments: dict[str, SourceSegment] = {}
        self._items: dict[str, KnowledgeItem] = {}

    def add_segment(self, segment: SourceSegment) -> None:
        existing = self._segments.get(segment.segment_id)
        if existing and existing != segment:
            raise ValueError("A source segment ID cannot be reused for different content")
        self._segments[segment.segment_id] = copy.deepcopy(segment)

    def add_knowledge(self, item: KnowledgeItem) -> RegistryResult:
        if item.knowledge_id in self._items:
            return RegistryResult(
                False,
                None,
                errors=("knowledge_id already exists; create a new version or ID",),
            )
        errors = validate_knowledge(item, self._segments)
        if errors:
            return RegistryResult(False, None, errors=tuple(errors))
        item.content_hash = statement_hash(item.statement)
        stored_item = copy.deepcopy(item)

        for existing in self._items.values():
            if (
                existing.expert_id == stored_item.expert_id
                and existing.content_hash == stored_item.content_hash
                and existing.epistemic_type == stored_item.epistemic_type
            ):
                return RegistryResult(
                    accepted=True,
                    item_id=existing.knowledge_id,
                    duplicate_of=existing.knowledge_id,
                )

        conflicts: list[str] = []
        if stored_item.conflict_key:
            for existing in self._items.values():
                if (
                    existing.expert_id == stored_item.expert_id
                    and existing.conflict_key == stored_item.conflict_key
                    and existing.content_hash != stored_item.content_hash
                ):
                    existing.state = KnowledgeState.REVIEW_REQUIRED
                    conflicts.append(existing.knowledge_id)
            if conflicts:
                stored_item.state = KnowledgeState.REVIEW_REQUIRED

        self._items[stored_item.knowledge_id] = stored_item
        return RegistryResult(
            accepted=True,
            item_id=item.knowledge_id,
            conflict_ids=tuple(conflicts),
        )

    def get(self, knowledge_id: str, expert_id: str) -> KnowledgeItem:
        item = self._items[knowledge_id]
        if item.expert_id != expert_id:
            raise PermissionError("Knowledge item belongs to another expert scope")
        return copy.deepcopy(item)

    def list_for_expert(self, expert_id: str) -> list[KnowledgeItem]:
        return [copy.deepcopy(item) for item in self._items.values() if item.expert_id == expert_id]
