"""Persistent media-asset registry with source provenance and hash deduplication."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aios_work_system.media.download_jobs import DownloadJob
from aios_work_system.media.source import register_source, sha256_file


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class MediaAsset:
    asset_id: str
    sha256: str
    storage_uri: str
    original_name: str
    mime_type: str
    size_bytes: int
    manifest_path: str
    created_at: str


class MediaAssetRepository:
    """Store immutable asset identity separately from each acquisition source."""

    def __init__(
        self,
        database_path: str | Path,
        manifest_dir: str | Path,
    ) -> None:
        self._database_path = str(database_path)
        self.manifest_dir = Path(manifest_dir).expanduser().resolve()
        if self._database_path != ":memory:":
            Path(self._database_path).expanduser().resolve().parent.mkdir(
                parents=True, exist_ok=True
            )
        self.manifest_dir.mkdir(parents=True, exist_ok=True)
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
                CREATE TABLE IF NOT EXISTS media_assets (
                    asset_id TEXT PRIMARY KEY,
                    sha256 TEXT NOT NULL UNIQUE,
                    storage_uri TEXT NOT NULL,
                    original_name TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    manifest_path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS media_asset_sources (
                    asset_id TEXT NOT NULL REFERENCES media_assets(asset_id),
                    candidate_id TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    engine TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(asset_id, job_id)
                );
                CREATE INDEX IF NOT EXISTS idx_media_assets_created
                    ON media_assets(created_at, asset_id);
                CREATE INDEX IF NOT EXISTS idx_media_asset_sources_candidate
                    ON media_asset_sources(candidate_id, created_at);
                """
            )

    @staticmethod
    def _from_row(row: sqlite3.Row) -> MediaAsset:
        return MediaAsset(**dict(row))

    def register_download(
        self,
        job: DownloadJob,
        path: str | Path,
        expected_sha256: str,
        expected_size_bytes: int,
    ) -> str:
        """Register a verified download and return its stable asset ID.

        The hash and size are checked again at this persistence boundary so a
        stale path or mismatched verifier result cannot enter the asset catalog.
        Identical content reuses the existing asset ID but retains each job's
        source provenance in a separate relation.
        """
        file_path = Path(path).expanduser().resolve(strict=True)
        if not file_path.is_file():
            raise ValueError(f"asset path is not a file: {file_path}")
        if isinstance(expected_size_bytes, bool) or not isinstance(
            expected_size_bytes, int
        ):
            raise ValueError("expected_size_bytes must be an integer")
        actual_size = file_path.stat().st_size
        if actual_size <= 0 or actual_size != expected_size_bytes:
            raise ValueError("asset size does not match verified download size")
        if (
            len(expected_sha256) != 64
            or any(character not in "0123456789abcdef" for character in expected_sha256.lower())
        ):
            raise ValueError("expected_sha256 must be a 64-character hexadecimal digest")
        actual_sha256 = sha256_file(file_path)
        if actual_sha256 != expected_sha256.lower():
            raise ValueError("asset SHA-256 does not match verified download digest")

        source_type = "VIDEO" if job.engine == "yt-dlp" else "FILE"
        manifest = register_source(
            file_path,
            source_type,
            parser_name=f"download-engine:{job.engine}",
            parser_version="1",
        )
        if manifest.sha256 != actual_sha256 or manifest.size_bytes != actual_size:
            raise ValueError("source manifest differs from the verified asset")
        created_at = _now()
        created_manifest: Path | None = None

        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    "SELECT asset_id FROM media_assets WHERE sha256=?",
                    (actual_sha256,),
                ).fetchone()
                if existing is not None:
                    asset_id = str(existing["asset_id"])
                else:
                    asset_id = manifest.source_id
                    manifest_path = self.manifest_dir / f"{asset_id}.json"
                    payload: dict[str, Any] = manifest.to_dict()
                    payload["acquisition"] = {
                        "candidate_id": job.candidate_id,
                        "job_id": job.job_id,
                        "source_url": job.source_url,
                        "engine": job.engine,
                    }
                    temporary = manifest_path.with_name(manifest_path.name + ".tmp")
                    temporary.write_text(
                        json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    temporary.replace(manifest_path)
                    created_manifest = manifest_path
                    connection.execute(
                        """
                        INSERT INTO media_assets
                        (asset_id, sha256, storage_uri, original_name, mime_type,
                         size_bytes, manifest_path, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            asset_id,
                            actual_sha256,
                            manifest.storage_uri,
                            manifest.original_name,
                            manifest.mime_type,
                            actual_size,
                            str(manifest_path),
                            created_at,
                        ),
                    )
                connection.execute(
                    """
                    INSERT OR IGNORE INTO media_asset_sources
                    (asset_id, candidate_id, job_id, source_url, engine, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        asset_id,
                        job.candidate_id,
                        job.job_id,
                        job.source_url,
                        job.engine,
                        created_at,
                    ),
                )
            return asset_id
        except Exception:
            if created_manifest is not None:
                created_manifest.unlink(missing_ok=True)
            raise

    def get(self, asset_id: str) -> MediaAsset:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM media_assets WHERE asset_id=?",
                (asset_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"media asset not found: {asset_id}")
        return self._from_row(row)

    def list(self, *, limit: int = 100) -> list[MediaAsset]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM media_assets
                ORDER BY created_at, asset_id
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def list_sources(self, asset_id: str) -> list[dict[str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT candidate_id, job_id, source_url, engine, created_at
                FROM media_asset_sources
                WHERE asset_id=?
                ORDER BY created_at, job_id
                """,
                (asset_id,),
            ).fetchall()
        return [dict(row) for row in rows]
