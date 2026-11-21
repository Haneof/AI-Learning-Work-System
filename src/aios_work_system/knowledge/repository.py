"""SQLite-backed knowledge and evidence repository with audited human review."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
from aios_work_system.knowledge.validation import statement_hash, validate_knowledge


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _segment_to_dict(segment: SourceSegment) -> dict[str, Any]:
    return {
        "segment_id": segment.segment_id,
        "source_id": segment.source_id,
        "expert_id": segment.expert_id,
        "locator": segment.locator,
        "text_content": segment.text_content,
        "shared_with_experts": sorted(segment.shared_with_experts),
        "modality": segment.modality,
        "artifact_ref": segment.artifact_ref,
    }


def _item_to_dict(item: KnowledgeItem) -> dict[str, Any]:
    return {
        "knowledge_id": item.knowledge_id,
        "expert_id": item.expert_id,
        "statement": item.statement,
        "knowledge_type": item.knowledge_type.value,
        "epistemic_type": item.epistemic_type.value,
        "state": item.state.value,
        "confidence": item.confidence.value,
        "version": item.version,
        "conflict_key": item.conflict_key,
        "evidence": [
            {
                "source_id": evidence.source_id,
                "segment_id": evidence.segment_id,
                "relation": evidence.relation.value,
                "excerpt": evidence.excerpt,
            }
            for evidence in item.evidence
        ],
        "content_hash": item.content_hash or statement_hash(item.statement),
    }


def _item_from_payload(payload: dict[str, Any]) -> KnowledgeItem:
    return KnowledgeItem(
        knowledge_id=payload["knowledge_id"],
        expert_id=payload["expert_id"],
        statement=payload["statement"],
        knowledge_type=KnowledgeType(payload["knowledge_type"]),
        epistemic_type=EpistemicType(payload["epistemic_type"]),
        state=KnowledgeState(payload["state"]),
        confidence=ConfidenceLabel(payload["confidence"]),
        version=int(payload["version"]),
        conflict_key=payload.get("conflict_key"),
        evidence=[
            EvidenceLink(
                source_id=evidence["source_id"],
                segment_id=evidence["segment_id"],
                relation=EvidenceRelation(evidence["relation"]),
                excerpt=evidence.get("excerpt"),
            )
            for evidence in payload.get("evidence", [])
        ],
        content_hash=payload.get("content_hash", ""),
    )


class KnowledgeRepository:
    """Persist expert-scoped source segments and knowledge with review history.

    This repository enforces evidence linkage and expert scope but is not an
    authentication service. Callers must derive expert_id and reviewer_id from
    trusted application identity, not from untrusted model output.
    """

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        if self.database_path != ":memory:":
            Path(self.database_path).expanduser().resolve().parent.mkdir(
                parents=True, exist_ok=True
            )
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS knowledge_source_segments (
                    segment_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    expert_id TEXT,
                    locator_json TEXT NOT NULL,
                    text_content TEXT NOT NULL,
                    shared_with_experts_json TEXT NOT NULL,
                    modality TEXT NOT NULL DEFAULT 'text',
                    artifact_ref TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_knowledge_segments_source
                    ON knowledge_source_segments(source_id, segment_id);
                CREATE TABLE IF NOT EXISTS knowledge_items (
                    knowledge_id TEXT PRIMARY KEY,
                    expert_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    conflict_key TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_knowledge_expert_state
                    ON knowledge_items(expert_id, state, knowledge_id);
                CREATE INDEX IF NOT EXISTS idx_knowledge_conflicts
                    ON knowledge_items(expert_id, conflict_key, content_hash);
                CREATE TABLE IF NOT EXISTS knowledge_reviews (
                    review_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    knowledge_id TEXT NOT NULL REFERENCES knowledge_items(knowledge_id),
                    expert_id TEXT NOT NULL,
                    reviewer_id TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    note TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(knowledge_source_segments)"
                ).fetchall()
            }
            if "modality" not in columns:
                connection.execute(
                    "ALTER TABLE knowledge_source_segments ADD COLUMN modality TEXT NOT NULL DEFAULT 'text'"
                )
            if "artifact_ref" not in columns:
                connection.execute(
                    "ALTER TABLE knowledge_source_segments ADD COLUMN artifact_ref TEXT"
                )

    @staticmethod
    def _segment_from_row(row: sqlite3.Row) -> SourceSegment:
        return SourceSegment(
            segment_id=row["segment_id"],
            source_id=row["source_id"],
            expert_id=row["expert_id"],
            locator=json.loads(row["locator_json"]),
            text_content=row["text_content"],
            shared_with_experts=frozenset(
                json.loads(row["shared_with_experts_json"])
            ),
            modality=row["modality"],
            artifact_ref=row["artifact_ref"],
        )

    def add_segment(self, segment: SourceSegment) -> None:
        if not segment.segment_id.strip() or not segment.source_id.strip():
            raise ValueError("segment_id and source_id are required")
        if not segment.text_content.strip():
            raise ValueError("source segment text_content must not be empty")
        payload = _segment_to_dict(segment)
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT * FROM knowledge_source_segments WHERE segment_id=?",
                (segment.segment_id,),
            ).fetchone()
            if existing is not None:
                if self._segment_from_row(existing) != segment:
                    raise ValueError(
                        "A source segment ID cannot be reused for different content"
                    )
                return
            connection.execute(
                """
                INSERT INTO knowledge_source_segments
                (segment_id, source_id, expert_id, locator_json, text_content,
                 shared_with_experts_json, modality, artifact_ref, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["segment_id"],
                    payload["source_id"],
                    payload["expert_id"],
                    json.dumps(payload["locator"], sort_keys=True),
                    payload["text_content"],
                    json.dumps(payload["shared_with_experts"], sort_keys=True),
                    payload["modality"],
                    payload["artifact_ref"],
                    _now(),
                ),
            )

    def get_segment(self, segment_id: str, expert_id: str) -> SourceSegment:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM knowledge_source_segments WHERE segment_id=?",
                (segment_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"source segment not found: {segment_id}")
        segment = self._segment_from_row(row)
        if segment.expert_id != expert_id and expert_id not in segment.shared_with_experts:
            raise PermissionError("Source segment belongs to another expert scope")
        return segment

    def list_segments(
        self,
        expert_id: str,
        *,
        source_id: str | None = None,
        limit: int = 1000,
    ) -> list[SourceSegment]:
        if not 1 <= limit <= 10000:
            raise ValueError("limit must be between 1 and 10000")
        query = """
            SELECT * FROM knowledge_source_segments
            WHERE (expert_id=? OR shared_with_experts_json LIKE ?)
        """
        params: list[Any] = [expert_id, f'%"{expert_id}"%']
        if source_id is not None:
            query += " AND source_id=?"
            params.append(source_id)
        query += " ORDER BY source_id, segment_id LIMIT ?"
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._segment_from_row(row) for row in rows]

    def _load_evidence_segments(
        self, connection: sqlite3.Connection, item: KnowledgeItem
    ) -> dict[str, SourceSegment]:
        segment_ids = list(dict.fromkeys(evidence.segment_id for evidence in item.evidence))
        if not segment_ids:
            return {}
        placeholders = ",".join("?" for _ in segment_ids)
        rows = connection.execute(
            f"SELECT * FROM knowledge_source_segments WHERE segment_id IN ({placeholders})",
            segment_ids,
        ).fetchall()
        segments = {
            row["segment_id"]: self._segment_from_row(row) for row in rows
        }
        return segments

    def add_knowledge(self, item: KnowledgeItem) -> dict[str, Any]:
        """Validate and persist a candidate; caller cannot self-mark it approved."""
        if item.state != KnowledgeState.CANDIDATE:
            raise ValueError("new knowledge must start in CANDIDATE state")
        now = _now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            segments = self._load_evidence_segments(connection, item)
            errors = validate_knowledge(item, segments)
            if errors:
                return {"accepted": False, "item_id": None, "errors": errors}

            normalized_hash = statement_hash(item.statement)
            duplicate = connection.execute(
                """
                SELECT knowledge_id FROM knowledge_items
                WHERE expert_id=? AND content_hash=? AND
                      json_extract(payload_json, '$.epistemic_type')=?
                LIMIT 1
                """,
                (item.expert_id, normalized_hash, item.epistemic_type.value),
            ).fetchone()
            if duplicate is not None:
                return {
                    "accepted": True,
                    "item_id": duplicate["knowledge_id"],
                    "duplicate_of": duplicate["knowledge_id"],
                    "conflict_ids": [],
                    "errors": [],
                }

            conflict_ids: list[str] = []
            stored = replace(item, content_hash=normalized_hash)
            if item.conflict_key:
                rows = connection.execute(
                    """
                    SELECT knowledge_id, payload_json FROM knowledge_items
                    WHERE expert_id=? AND conflict_key=? AND content_hash<>?
                    """,
                    (item.expert_id, item.conflict_key, normalized_hash),
                ).fetchall()
                for row in rows:
                    existing = _item_from_payload(json.loads(row["payload_json"]))
                    if existing.state in {
                        KnowledgeState.CANDIDATE,
                        KnowledgeState.APPROVED,
                    }:
                        existing.state = KnowledgeState.REVIEW_REQUIRED
                        payload = _item_to_dict(existing)
                        connection.execute(
                            """
                            UPDATE knowledge_items SET state=?, payload_json=?, updated_at=?
                            WHERE knowledge_id=?
                            """,
                            (
                                existing.state.value,
                                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                                now,
                                existing.knowledge_id,
                            ),
                        )
                    conflict_ids.append(existing.knowledge_id)
                if conflict_ids:
                    stored.state = KnowledgeState.REVIEW_REQUIRED

            payload = _item_to_dict(stored)
            connection.execute(
                """
                INSERT INTO knowledge_items
                (knowledge_id, expert_id, state, content_hash, conflict_key,
                 payload_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stored.knowledge_id,
                    stored.expert_id,
                    stored.state.value,
                    normalized_hash,
                    stored.conflict_key,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    now,
                    now,
                ),
            )
        return {
            "accepted": True,
            "item_id": stored.knowledge_id,
            "duplicate_of": None,
            "conflict_ids": conflict_ids,
            "errors": [],
        }

    def get(self, knowledge_id: str, expert_id: str) -> KnowledgeItem:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM knowledge_items WHERE knowledge_id=?",
                (knowledge_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"knowledge item not found: {knowledge_id}")
        if row["expert_id"] != expert_id:
            raise PermissionError("Knowledge item belongs to another expert scope")
        return _item_from_payload(json.loads(row["payload_json"]))

    def list_for_expert(
        self,
        expert_id: str,
        *,
        state: KnowledgeState | None = None,
        knowledge_type: KnowledgeType | None = None,
        limit: int = 1000,
    ) -> list[KnowledgeItem]:
        if not 1 <= limit <= 10000:
            raise ValueError("limit must be between 1 and 10000")
        query = "SELECT payload_json FROM knowledge_items WHERE expert_id=?"
        params: list[Any] = [expert_id]
        if state is not None:
            query += " AND state=?"
            params.append(state.value)
        if knowledge_type is not None:
            query += " AND json_extract(payload_json, '$.knowledge_type')=?"
            params.append(knowledge_type.value)
        query += " ORDER BY created_at, knowledge_id LIMIT ?"
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [_item_from_payload(json.loads(row["payload_json"])) for row in rows]

    def review(
        self,
        knowledge_id: str,
        expert_id: str,
        *,
        reviewer_id: str,
        decision: KnowledgeState,
        note: str,
    ) -> KnowledgeItem:
        """Record an explicit human approval/rejection with a durable audit event."""
        if not reviewer_id.strip():
            raise ValueError("reviewer_id is required")
        if not isinstance(note, str) or not note.strip():
            raise ValueError("review note is required")
        if decision not in {KnowledgeState.APPROVED, KnowledgeState.REJECTED}:
            raise ValueError("review decision must be APPROVED or REJECTED")

        now = _now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM knowledge_items WHERE knowledge_id=?",
                (knowledge_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"knowledge item not found: {knowledge_id}")
            if row["expert_id"] != expert_id:
                raise PermissionError("Knowledge item belongs to another expert scope")
            item = _item_from_payload(json.loads(row["payload_json"]))
            if item.state not in {
                KnowledgeState.CANDIDATE,
                KnowledgeState.REVIEW_REQUIRED,
            }:
                raise ValueError(f"knowledge cannot be reviewed from state {item.state}")
            updated = replace(item, state=decision)
            if decision == KnowledgeState.APPROVED:
                segments = self._load_evidence_segments(connection, updated)
                errors = validate_knowledge(updated, segments)
                if errors:
                    raise ValueError("knowledge approval failed: " + "; ".join(errors))
            payload = _item_to_dict(updated)
            connection.execute(
                """
                UPDATE knowledge_items
                SET state=?, payload_json=?, updated_at=?
                WHERE knowledge_id=?
                """,
                (
                    decision.value,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    now,
                    knowledge_id,
                ),
            )
            connection.execute(
                """
                INSERT INTO knowledge_reviews
                (knowledge_id, expert_id, reviewer_id, decision, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    knowledge_id,
                    expert_id,
                    reviewer_id,
                    decision.value,
                    note.strip(),
                    now,
                ),
            )
        return updated

    def review_history(self, knowledge_id: str, expert_id: str) -> list[dict[str, str]]:
        # get() performs the expert-scope check before returning audit history.
        self.get(knowledge_id, expert_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT reviewer_id, decision, note, created_at
                FROM knowledge_reviews
                WHERE knowledge_id=?
                ORDER BY review_id
                """,
                (knowledge_id,),
            ).fetchall()
        return [dict(row) for row in rows]
