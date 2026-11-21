"""Durable expert-scoped skill version registry."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from aios_work_system.skills.registry import SkillVersionRecord


@dataclass(frozen=True)
class StoredSkillVersion:
    expert_id: str
    skill_id: str
    version: str
    package_hash: str
    package_path: str
    lifecycle_status: str
    registered_at: str


class SkillVersionRepository:
    """Persist immutable version-to-package-hash bindings per expert."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        if self.database_path != ":memory:":
            Path(self.database_path).expanduser().resolve().parent.mkdir(
                parents=True, exist_ok=True
            )
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS skill_versions (
                    expert_id TEXT NOT NULL,
                    skill_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    package_hash TEXT NOT NULL,
                    package_path TEXT NOT NULL,
                    lifecycle_status TEXT NOT NULL,
                    registered_at TEXT NOT NULL,
                    PRIMARY KEY(expert_id, skill_id, version)
                );
                CREATE INDEX IF NOT EXISTS idx_skill_versions_expert
                    ON skill_versions(expert_id, skill_id, registered_at);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def register(
        self,
        record: SkillVersionRecord,
        *,
        expert_id: str,
        package_path: str | Path,
        lifecycle_status: str = "REVIEWED",
    ) -> StoredSkillVersion:
        if not expert_id.strip():
            raise ValueError("expert_id is required")
        if not record.skill_id.strip() or not record.version.strip():
            raise ValueError("skill_id and version are required")
        if len(record.package_hash) != 64 or any(
            character not in "0123456789abcdef"
            for character in record.package_hash.lower()
        ):
            raise ValueError("package_hash must be a 64-character SHA-256 digest")
        if lifecycle_status not in {"REVIEWED", "VALIDATED"}:
            raise ValueError("only reviewed and validated skills can be registered")
        resolved_path = str(Path(package_path).expanduser().resolve(strict=True))
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
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
                        "Skill content changed without a version increment; "
                        "create a new version"
                    )
                return self._from_row(row)
            connection.execute(
                """
                INSERT INTO skill_versions
                (expert_id, skill_id, version, package_hash, package_path,
                 lifecycle_status, registered_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    expert_id,
                    record.skill_id,
                    record.version,
                    record.package_hash.lower(),
                    resolved_path,
                    lifecycle_status,
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
            registered_at=row["registered_at"],
        )

    def get(
        self, expert_id: str, skill_id: str, version: str
    ) -> StoredSkillVersion:
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
