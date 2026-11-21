"""Persistent download-job state and lifecycle transitions.

This module deliberately manages job metadata only. yt-dlp and aria2 remain the
download engines; orchestration and process supervision are layered on later.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(UTC).isoformat()


class DownloadJobStatus(StrEnum):
    QUEUED = "QUEUED"
    PREPARING = "PREPARING"
    DOWNLOADING = "DOWNLOADING"
    PAUSED = "PAUSED"
    VERIFYING = "VERIFYING"
    RETRY_WAIT = "RETRY_WAIT"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


_ALLOWED_TRANSITIONS: dict[DownloadJobStatus, set[DownloadJobStatus]] = {
    DownloadJobStatus.QUEUED: {
        DownloadJobStatus.PREPARING,
        DownloadJobStatus.CANCELLED,
    },
    DownloadJobStatus.PREPARING: {
        DownloadJobStatus.DOWNLOADING,
        DownloadJobStatus.RETRY_WAIT,
        DownloadJobStatus.FAILED,
        DownloadJobStatus.CANCELLED,
    },
    DownloadJobStatus.DOWNLOADING: {
        DownloadJobStatus.PAUSED,
        DownloadJobStatus.VERIFYING,
        DownloadJobStatus.RETRY_WAIT,
        DownloadJobStatus.FAILED,
        DownloadJobStatus.CANCELLED,
    },
    DownloadJobStatus.PAUSED: {
        DownloadJobStatus.QUEUED,
        DownloadJobStatus.CANCELLED,
    },
    DownloadJobStatus.VERIFYING: {
        DownloadJobStatus.COMPLETED,
        DownloadJobStatus.RETRY_WAIT,
        DownloadJobStatus.FAILED,
        DownloadJobStatus.CANCELLED,
    },
    DownloadJobStatus.RETRY_WAIT: {
        DownloadJobStatus.QUEUED,
        DownloadJobStatus.FAILED,
        DownloadJobStatus.CANCELLED,
    },
    DownloadJobStatus.FAILED: {DownloadJobStatus.QUEUED},
    DownloadJobStatus.COMPLETED: set(),
    DownloadJobStatus.CANCELLED: set(),
}


@dataclass(frozen=True)
class DownloadJob:
    job_id: str
    candidate_id: str
    source_url: str
    engine: str
    destination: str
    status: DownloadJobStatus
    bytes_downloaded: int
    total_bytes: int | None
    speed_bytes_per_second: float | None
    eta_seconds: float | None
    retry_count: int
    error: str | None
    asset_id: str | None
    sha256: str | None
    created_at: str
    updated_at: str

    @property
    def progress_percent(self) -> float | None:
        if self.total_bytes is None or self.total_bytes <= 0:
            return None
        return min(100.0, self.bytes_downloaded / self.total_bytes * 100)


class DownloadJobRepository:
    """SQLite-backed job repository with guarded state transitions."""

    def __init__(self, database_path: str | Path) -> None:
        self._database_path = str(database_path)
        if self._database_path != ":memory:":
            Path(self._database_path).expanduser().resolve().parent.mkdir(
                parents=True, exist_ok=True
            )
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS download_jobs (
                    job_id TEXT PRIMARY KEY,
                    candidate_id TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    engine TEXT NOT NULL,
                    destination TEXT NOT NULL,
                    status TEXT NOT NULL,
                    bytes_downloaded INTEGER NOT NULL DEFAULT 0,
                    total_bytes INTEGER,
                    speed_bytes_per_second REAL,
                    eta_seconds REAL,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    error TEXT,
                    asset_id TEXT,
                    sha256 TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_download_jobs_status_created
                    ON download_jobs(status, created_at);
                CREATE INDEX IF NOT EXISTS idx_download_jobs_candidate
                    ON download_jobs(candidate_id, created_at);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_download_jobs_one_active_candidate
                    ON download_jobs(candidate_id)
                    WHERE status NOT IN ('COMPLETED', 'FAILED', 'CANCELLED');
                """
            )

    @staticmethod
    def _from_row(row: sqlite3.Row) -> DownloadJob:
        values: dict[str, Any] = dict(row)
        values["status"] = DownloadJobStatus(values["status"])
        return DownloadJob(**values)

    def create(
        self,
        *,
        candidate_id: str,
        source_url: str,
        engine: str,
        destination: str | Path,
        job_id: str | None = None,
    ) -> DownloadJob:
        if not candidate_id.strip():
            raise ValueError("candidate_id must not be empty")
        if not source_url.startswith(("http://", "https://")):
            raise ValueError("source_url must use HTTP or HTTPS")
        if engine not in {"yt-dlp", "aria2"}:
            raise ValueError("engine must be 'yt-dlp' or 'aria2'")
        if not str(destination).strip():
            raise ValueError("destination must not be empty")
        now = _now()
        identifier = job_id or str(uuid.uuid4())
        with self._connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO download_jobs
                    (job_id, candidate_id, source_url, engine, destination, status,
                     created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        identifier, candidate_id, source_url, engine, str(destination),
                        DownloadJobStatus.QUEUED.value, now, now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                if "idx_download_jobs_one_active_candidate" in str(exc) or (
                    "UNIQUE constraint failed: download_jobs.candidate_id" in str(exc)
                ):
                    raise ValueError(
                        f"candidate already has an active download job: {candidate_id}"
                    ) from exc
                raise
        return self.get(identifier)

    def get(self, job_id: str) -> DownloadJob:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM download_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"download job not found: {job_id}")
        return self._from_row(row)

    def list(
        self, *, status: DownloadJobStatus | None = None, limit: int = 100
    ) -> list[DownloadJob]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        query = "SELECT * FROM download_jobs"
        values: tuple[str | int, ...] = ()
        if status is not None:
            query += " WHERE status=?"
            values = (status.value,)
        query += " ORDER BY created_at, job_id LIMIT ?"
        values += (limit,)
        with self._connect() as connection:
            rows = connection.execute(query, values).fetchall()
        return [self._from_row(row) for row in rows]

    def transition(
        self,
        job_id: str,
        new_status: DownloadJobStatus,
        *,
        expected_status: DownloadJobStatus | None = None,
        error: str | None = None,
        asset_id: str | None = None,
        sha256: str | None = None,
    ) -> DownloadJob:
        now = _now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT status, retry_count FROM download_jobs WHERE job_id=?",
                (job_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"download job not found: {job_id}")
            current = DownloadJobStatus(row["status"])
            if expected_status is not None and current != expected_status:
                raise ValueError(
                    f"download job status conflict: expected {expected_status}, found {current}"
                )
            if new_status not in _ALLOWED_TRANSITIONS[current]:
                raise ValueError(
                    f"invalid download job transition: {current} -> {new_status}"
                )
            if new_status == DownloadJobStatus.COMPLETED and not (asset_id and sha256):
                raise ValueError("completed jobs require both asset_id and sha256")
            if new_status in {DownloadJobStatus.FAILED, DownloadJobStatus.RETRY_WAIT}:
                if not error or not error.strip():
                    raise ValueError(f"{new_status} jobs require a non-empty error")
            retry_count = row["retry_count"]
            if new_status == DownloadJobStatus.RETRY_WAIT:
                retry_count += 1
            connection.execute(
                """
                UPDATE download_jobs
                SET status=?, retry_count=?, error=?, asset_id=?, sha256=?, updated_at=?
                WHERE job_id=?
                """,
                (
                    new_status.value,
                    retry_count,
                    error if new_status in {
                        DownloadJobStatus.FAILED, DownloadJobStatus.RETRY_WAIT
                    } else None,
                    asset_id if new_status == DownloadJobStatus.COMPLETED else None,
                    sha256 if new_status == DownloadJobStatus.COMPLETED else None,
                    now,
                    job_id,
                ),
            )
        return self.get(job_id)

    def update_progress(
        self,
        job_id: str,
        *,
        bytes_downloaded: int,
        total_bytes: int | None = None,
        speed_bytes_per_second: float | None = None,
        eta_seconds: float | None = None,
    ) -> DownloadJob:
        if bytes_downloaded < 0:
            raise ValueError("bytes_downloaded must be non-negative")
        if total_bytes is not None and total_bytes < 0:
            raise ValueError("total_bytes must be non-negative")
        if speed_bytes_per_second is not None and speed_bytes_per_second < 0:
            raise ValueError("speed_bytes_per_second must be non-negative")
        if eta_seconds is not None and eta_seconds < 0:
            raise ValueError("eta_seconds must be non-negative")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE download_jobs
                SET bytes_downloaded=?, total_bytes=?, speed_bytes_per_second=?,
                    eta_seconds=?, updated_at=?
                WHERE job_id=? AND status=?
                """,
                (
                    bytes_downloaded, total_bytes, speed_bytes_per_second,
                    eta_seconds, _now(), job_id, DownloadJobStatus.DOWNLOADING.value,
                ),
            )
            if cursor.rowcount == 0:
                row = connection.execute(
                    "SELECT status FROM download_jobs WHERE job_id=?", (job_id,)
                ).fetchone()
                if row is None:
                    raise KeyError(f"download job not found: {job_id}")
                raise ValueError(
                    f"progress can only be updated while DOWNLOADING; found {row['status']}"
                )
        return self.get(job_id)

    def recover_interrupted(self) -> int:
        """Move in-flight jobs to RETRY_WAIT after an unclean process shutdown."""
        now = _now()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE download_jobs
                SET status=?, retry_count=retry_count+1,
                    error='process interrupted; resume required', updated_at=?
                WHERE status IN (?, ?, ?)
                """,
                (
                    DownloadJobStatus.RETRY_WAIT.value,
                    now,
                    DownloadJobStatus.PREPARING.value,
                    DownloadJobStatus.DOWNLOADING.value,
                    DownloadJobStatus.VERIFYING.value,
                ),
            )
        return cursor.rowcount
