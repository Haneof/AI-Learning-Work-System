"""SQLite persistence for discovered candidates and human curation state."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict
from enum import StrEnum
import json
from pathlib import Path
import sqlite3

from aios_work_system.acquisition.models import ResourceCandidate


class CandidateStatus(StrEnum):
    DISCOVERED = "DISCOVERED"
    REVIEW_PENDING = "REVIEW_PENDING"
    SELECTED = "SELECTED"
    REJECTED = "REJECTED"
    QUEUED = "QUEUED"


_ALLOWED_TRANSITIONS = {
    CandidateStatus.DISCOVERED: {
        CandidateStatus.REVIEW_PENDING,
        CandidateStatus.SELECTED,
        CandidateStatus.REJECTED,
    },
    CandidateStatus.REVIEW_PENDING: {
        CandidateStatus.SELECTED,
        CandidateStatus.REJECTED,
    },
    CandidateStatus.SELECTED: {
        CandidateStatus.QUEUED,
        CandidateStatus.REJECTED,
    },
    CandidateStatus.REJECTED: {CandidateStatus.REVIEW_PENDING},
    CandidateStatus.QUEUED: set(),
}


class CandidateRepository:
    """Persist normalized candidates, search-batch membership, and review status."""

    def __init__(self, database_path: str | Path) -> None:
        self._database_path = str(database_path)
        if self._database_path != ":memory:":
            Path(self._database_path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS candidates (
                    candidate_id TEXT PRIMARY KEY,
                    platform TEXT NOT NULL,
                    canonical_url TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    status_reason TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(platform, canonical_url)
                );
                CREATE TABLE IF NOT EXISTS search_batch_candidates (
                    batch_id TEXT NOT NULL,
                    candidate_id TEXT NOT NULL REFERENCES candidates(candidate_id),
                    PRIMARY KEY(batch_id, candidate_id)
                );
                CREATE INDEX IF NOT EXISTS idx_candidates_status
                    ON candidates(status, created_at);
                CREATE INDEX IF NOT EXISTS idx_batch_candidates
                    ON search_batch_candidates(batch_id, candidate_id);
                """
            )

    def save_candidates(
        self, batch_id: str, candidates: Iterable[ResourceCandidate]
    ) -> int:
        if not batch_id.strip():
            raise ValueError("batch_id must not be empty")
        inserted = 0
        with self._connect() as connection:
            for candidate in candidates:
                payload = json.dumps(asdict(candidate), ensure_ascii=False, sort_keys=True)
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO candidates
                    (candidate_id, platform, canonical_url, payload_json, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        candidate.candidate_id,
                        candidate.platform.lower(),
                        candidate.canonical_url,
                        payload,
                        CandidateStatus.DISCOVERED.value,
                        candidate.discovered_at,
                    ),
                )
                inserted += cursor.rowcount
                row = connection.execute(
                    "SELECT candidate_id FROM candidates WHERE platform=? AND canonical_url=?",
                    (candidate.platform.lower(), candidate.canonical_url),
                ).fetchone()
                connection.execute(
                    "INSERT OR IGNORE INTO search_batch_candidates(batch_id, candidate_id) "
                    "VALUES (?, ?)",
                    (batch_id, row["candidate_id"]),
                )
        return inserted

    def list_candidates(
        self,
        *,
        batch_id: str | None = None,
        status: CandidateStatus | None = None,
        limit: int = 100,
    ) -> list[tuple[ResourceCandidate, CandidateStatus, str | None]]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        clauses: list[str] = []
        values: list[str | int] = []
        join = ""
        if batch_id is not None:
            join = " JOIN search_batch_candidates b ON b.candidate_id=c.candidate_id"
            clauses.append("b.batch_id=?")
            values.append(batch_id)
        if status is not None:
            clauses.append("c.status=?")
            values.append(status.value)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT c.payload_json, c.status, c.status_reason FROM candidates c"
                + join
                + where
                + " ORDER BY c.created_at, c.candidate_id LIMIT ?",
                (*values, limit),
            ).fetchall()
        return [
            (
                ResourceCandidate(**json.loads(row["payload_json"])),
                CandidateStatus(row["status"]),
                row["status_reason"],
            )
            for row in rows
        ]

    def transition(
        self,
        candidate_id: str,
        new_status: CandidateStatus,
        *,
        reason: str | None = None,
    ) -> None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status FROM candidates WHERE candidate_id=?", (candidate_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"candidate not found: {candidate_id}")
            current = CandidateStatus(row["status"])
            if new_status not in _ALLOWED_TRANSITIONS[current]:
                raise ValueError(f"invalid candidate status transition: {current} -> {new_status}")
            connection.execute(
                "UPDATE candidates SET status=?, status_reason=? WHERE candidate_id=?",
                (new_status.value, reason, candidate_id),
            )
