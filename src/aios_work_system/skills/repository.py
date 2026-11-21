"""Durable expert-scoped skill review and immutable version registry."""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from aios_work_system.skills.registry import SkillVersionRecord


@dataclass(frozen=True)
class StoredSkillReview:
    review_id: str
    expert_id: str
    skill_id: str
    version: str
    spec_hash: str
    reviewer_id: str
    annotator_id: str | None
    decision: str
    note: str
    reviewed_at: str


@dataclass(frozen=True)
class StoredSkillVersion:
    expert_id: str
    skill_id: str
    version: str
    package_hash: str
    package_path: str
    lifecycle_status: str
    review_id: str
    registered_at: str


class SkillVersionRepository:
    """Persist immutable versions and review attestations bound to spec hashes.

    This repository records caller-supplied reviewer identities; it is not an
    authentication service. A production application must bind reviewer_id to
    an authenticated user session before calling record_review().
    """

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        if self.database_path != ":memory:":
            Path(self.database_path).expanduser().resolve().parent.mkdir(
                parents=True, exist_ok=True
            )
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS skill_reviews (
                    review_id TEXT PRIMARY KEY,
                    expert_id TEXT NOT NULL,
                    skill_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    spec_hash TEXT NOT NULL,
                    reviewer_id TEXT NOT NULL,
                    annotator_id TEXT,
                    decision TEXT NOT NULL,
                    note TEXT NOT NULL,
                    reviewed_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_skill_reviews_spec
                    ON skill_reviews(expert_id, skill_id, version, spec_hash);
                CREATE TABLE IF NOT EXISTS skill_versions (
                    expert_id TEXT NOT NULL,
                    skill_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    package_hash TEXT NOT NULL,
                    package_path TEXT NOT NULL,
                    lifecycle_status TEXT NOT NULL,
                    review_id TEXT,
                    registered_at TEXT NOT NULL,
                    PRIMARY KEY(expert_id, skill_id, version),
                    FOREIGN KEY(review_id) REFERENCES skill_reviews(review_id)
                );
                CREATE INDEX IF NOT EXISTS idx_skill_versions_expert
                    ON skill_versions(expert_id, skill_id, registered_at);
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(skill_versions)").fetchall()
            }
            if "review_id" not in columns:
                connection.execute("ALTER TABLE skill_versions ADD COLUMN review_id TEXT")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def record_review(
        self,
        *,
        expert_id: str,
        skill_id: str,
        version: str,
        spec_hash: str,
        reviewer_id: str,
        annotator_id: str | None,
        decision: str,
        note: str,
    ) -> StoredSkillReview:
        for value, label in (
            (expert_id, "expert_id"),
            (skill_id, "skill_id"),
            (version, "version"),
            (reviewer_id, "reviewer_id"),
            (note, "note"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{label} is required")
        if annotator_id is not None and not annotator_id.strip():
            raise ValueError("annotator_id must be None or non-empty")
        if annotator_id is not None and reviewer_id == annotator_id:
            raise ValueError("reviewer_id must differ from annotator_id")
        if decision not in {"APPROVED", "REJECTED"}:
            raise ValueError("decision must be APPROVED or REJECTED")
        if (
            not isinstance(spec_hash, str)
            or len(spec_hash) != 64
            or any(character not in "0123456789abcdef" for character in spec_hash.lower())
        ):
            raise ValueError("spec_hash must be a 64-character SHA-256 digest")

        review = StoredSkillReview(
            review_id=str(uuid.uuid4()),
            expert_id=expert_id,
            skill_id=skill_id,
            version=version,
            spec_hash=spec_hash.lower(),
            reviewer_id=reviewer_id,
            annotator_id=annotator_id,
            decision=decision,
            note=note.strip(),
            reviewed_at=datetime.now(UTC).isoformat(),
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO skill_reviews
                (review_id, expert_id, skill_id, version, spec_hash, reviewer_id,
                 annotator_id, decision, note, reviewed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    review.review_id,
                    review.expert_id,
                    review.skill_id,
                    review.version,
                    review.spec_hash,
                    review.reviewer_id,
                    review.annotator_id,
                    review.decision,
                    review.note,
                    review.reviewed_at,
                ),
            )
        return review

    def get_review(self, review_id: str, expert_id: str) -> StoredSkillReview:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM skill_reviews
                WHERE review_id=? AND expert_id=?
                """,
                (review_id, expert_id),
            ).fetchone()
        if row is None:
            raise KeyError(f"skill review not found: {review_id}")
        return StoredSkillReview(**dict(row))

    def reviews_for_spec(
        self,
        *,
        expert_id: str,
        skill_id: str,
        version: str,
        spec_hash: str,
    ) -> list[StoredSkillReview]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM skill_reviews
                WHERE expert_id=? AND skill_id=? AND version=? AND spec_hash=?
                ORDER BY reviewed_at, review_id
                """,
                (expert_id, skill_id, version, spec_hash),
            ).fetchall()
        return [StoredSkillReview(**dict(row)) for row in rows]

    def register(
        self,
        record: SkillVersionRecord,
        *,
        expert_id: str,
        package_path: str | Path,
        review_id: str,
        spec_hash: str,
        lifecycle_status: str = "REVIEWED",
    ) -> StoredSkillVersion:
        if not expert_id.strip():
            raise ValueError("expert_id is required")
        if not record.skill_id.strip() or not record.version.strip():
            raise ValueError("skill_id and version are required")
        if len(record.package_hash) != 64 or any(
            character not in "0123456789abcdef" for character in record.package_hash.lower()
        ):
            raise ValueError("package_hash must be a 64-character SHA-256 digest")
        if lifecycle_status != "REVIEWED":
            raise ValueError("only reviewed skills can be registered")
        resolved_path = str(Path(package_path).expanduser().resolve(strict=True))
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            review = connection.execute(
                """
                SELECT * FROM skill_reviews
                WHERE review_id=? AND expert_id=? AND skill_id=? AND version=?
                  AND spec_hash=? AND decision='APPROVED'
                """,
                (
                    review_id,
                    expert_id,
                    record.skill_id,
                    record.version,
                    spec_hash,
                ),
            ).fetchone()
            if review is None:
                raise ValueError(
                    "registered skill requires an approved review for this exact spec hash"
                )
            row = connection.execute(
                """
                SELECT * FROM skill_versions
                WHERE expert_id=? AND skill_id=? AND version=?
                """,
                (expert_id, record.skill_id, record.version),
            ).fetchone()
            if row is not None:
                if row["package_hash"] != record.package_hash:
                    raise ValueError(
                        "Skill content changed without a version increment; create a new version"
                    )
                if row["review_id"] != review_id:
                    raise ValueError("skill version is already bound to another review")
                return self._from_row(row)
            connection.execute(
                """
                INSERT INTO skill_versions
                (expert_id, skill_id, version, package_hash, package_path,
                 lifecycle_status, review_id, registered_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    expert_id,
                    record.skill_id,
                    record.version,
                    record.package_hash.lower(),
                    resolved_path,
                    lifecycle_status,
                    review_id,
                    now,
                ),
            )
            saved = connection.execute(
                """
                SELECT * FROM skill_versions
                WHERE expert_id=? AND skill_id=? AND version=?
                """,
                (expert_id, record.skill_id, record.version),
            ).fetchone()
        return self._from_row(saved)

    @staticmethod
    def _from_row(row: sqlite3.Row) -> StoredSkillVersion:
        return StoredSkillVersion(
            expert_id=row["expert_id"],
            skill_id=row["skill_id"],
            version=row["version"],
            package_hash=row["package_hash"],
            package_path=row["package_path"],
            lifecycle_status=row["lifecycle_status"],
            review_id=row["review_id"],
            registered_at=row["registered_at"],
        )

    def get(self, expert_id: str, skill_id: str, version: str) -> StoredSkillVersion:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM skill_versions
                WHERE expert_id=? AND skill_id=? AND version=?
                """,
                (expert_id, skill_id, version),
            ).fetchone()
        if row is None:
            raise KeyError(f"skill version not found: {skill_id}@{version}")
        return self._from_row(row)

    def list_for_expert(
        self,
        expert_id: str,
        *,
        skill_id: str | None = None,
        limit: int = 1000,
    ) -> list[StoredSkillVersion]:
        if not 1 <= limit <= 10000:
            raise ValueError("limit must be between 1 and 10000")
        query = "SELECT * FROM skill_versions WHERE expert_id=?"
        params: list[object] = [expert_id]
        if skill_id is not None:
            query += " AND skill_id=?"
            params.append(skill_id)
        query += " ORDER BY skill_id, registered_at, version LIMIT ?"
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._from_row(row) for row in rows]
