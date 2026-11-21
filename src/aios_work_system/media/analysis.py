"""Durable, timestamp-aware analysis of registered media assets."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from aios_work_system.media.adapters import ASRAdapter, OCRAdapter, OCRSegment, TranscriptSegment
from aios_work_system.media.assets import MediaAssetRepository
from aios_work_system.media.ffmpeg import FFmpegProcessor
from aios_work_system.media.source import sha256_file


class AnalysisStatus(StrEnum):
    RUNNING = "RUNNING"
    PARTIAL = "PARTIAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class AnalysisArtifact:
    artifact_key: str
    kind: str
    path: str
    sha256: str
    size_bytes: int
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class MediaAnalysisResult:
    run_id: str
    asset_id: str
    source_sha256: str
    config_hash: str
    status: AnalysisStatus
    attempts: int
    duration_seconds: float | None
    artifacts: tuple[AnalysisArtifact, ...]
    transcripts: tuple[TranscriptSegment, ...]
    ocr_segments: tuple[OCRSegment, ...]
    warnings: tuple[str, ...]
    error: str | None

    @property
    def audio_path(self) -> Path | None:
        for artifact in self.artifacts:
            if artifact.kind == "AUDIO":
                return Path(artifact.path)
        return None

    @property
    def frame_paths(self) -> tuple[Path, ...]:
        return tuple(
            Path(artifact.path)
            for artifact in self.artifacts
            if artifact.kind == "FRAME"
        )


def _now() -> str:
    return datetime.now(UTC).isoformat()


class MediaAnalysisRepository:
    """Persist analysis runs, derived files, ASR segments, and OCR evidence."""

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
                CREATE TABLE IF NOT EXISTS media_analysis_runs (
                    run_id TEXT PRIMARY KEY,
                    asset_id TEXT NOT NULL,
                    source_sha256 TEXT NOT NULL,
                    config_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL,
                    duration_seconds REAL,
                    settings_json TEXT NOT NULL,
                    warnings_json TEXT NOT NULL DEFAULT '[]',
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(asset_id, source_sha256, config_hash)
                );
                CREATE TABLE IF NOT EXISTS media_analysis_artifacts (
                    run_id TEXT NOT NULL REFERENCES media_analysis_runs(run_id),
                    artifact_key TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    path TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    metadata_json TEXT NOT NULL,
                    PRIMARY KEY(run_id, artifact_key)
                );
                CREATE TABLE IF NOT EXISTS media_transcript_segments (
                    run_id TEXT NOT NULL REFERENCES media_analysis_runs(run_id),
                    segment_index INTEGER NOT NULL,
                    start_ms INTEGER NOT NULL,
                    end_ms INTEGER NOT NULL,
                    text_content TEXT NOT NULL,
                    adapter_name TEXT NOT NULL,
                    adapter_version TEXT NOT NULL,
                    PRIMARY KEY(run_id, segment_index)
                );
                CREATE TABLE IF NOT EXISTS media_ocr_segments (
                    run_id TEXT NOT NULL REFERENCES media_analysis_runs(run_id),
                    segment_index INTEGER NOT NULL,
                    timestamp_ms INTEGER NOT NULL,
                    text_content TEXT NOT NULL,
                    bounding_box_json TEXT,
                    adapter_name TEXT NOT NULL,
                    adapter_version TEXT NOT NULL,
                    PRIMARY KEY(run_id, segment_index)
                );
                CREATE INDEX IF NOT EXISTS idx_analysis_asset
                    ON media_analysis_runs(asset_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_transcript_time
                    ON media_transcript_segments(run_id, start_ms, end_ms);
                CREATE INDEX IF NOT EXISTS idx_ocr_time
                    ON media_ocr_segments(run_id, timestamp_ms);
                """
            )

    def start_or_resume(
        self,
        *,
        asset_id: str,
        source_sha256: str,
        config_hash: str,
        settings: dict[str, Any],
    ) -> tuple[str, bool]:
        """Return (run_id, should_execute); completed identical runs are reused."""
        now = _now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT run_id, status
                FROM media_analysis_runs
                WHERE asset_id=? AND source_sha256=? AND config_hash=?
                """,
                (asset_id, source_sha256, config_hash),
            ).fetchone()
            if row is not None:
                run_id = str(row["run_id"])
                status = AnalysisStatus(row["status"])
                if status in {AnalysisStatus.COMPLETED, AnalysisStatus.PARTIAL}:
                    return run_id, False
                connection.execute(
                    """
                    UPDATE media_analysis_runs
                    SET status=?, attempts=attempts+1, error=NULL, updated_at=?
                    WHERE run_id=?
                    """,
                    (AnalysisStatus.RUNNING.value, now, run_id),
                )
                return run_id, True

            run_id = str(uuid.uuid4())
            connection.execute(
                """
                INSERT INTO media_analysis_runs
                (run_id, asset_id, source_sha256, config_hash, status, attempts,
                 settings_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)
                """,
                (
                    run_id,
                    asset_id,
                    source_sha256,
                    config_hash,
                    AnalysisStatus.RUNNING.value,
                    json.dumps(settings, ensure_ascii=False, sort_keys=True),
                    now,
                    now,
                ),
            )
        return run_id, True

    def mark_failed(self, run_id: str, error: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE media_analysis_runs
                SET status=?, error=?, updated_at=?
                WHERE run_id=?
                """,
                (AnalysisStatus.FAILED.value, error, _now(), run_id),
            )

    def save_results(
        self,
        run_id: str,
        *,
        status: AnalysisStatus,
        duration_seconds: float | None,
        artifacts: list[AnalysisArtifact],
        transcripts: list[TranscriptSegment],
        ocr_segments: list[OCRSegment],
        warnings: list[str],
        asr_adapter: ASRAdapter | None,
        ocr_adapter: OCRAdapter | None,
    ) -> None:
        if status not in {AnalysisStatus.PARTIAL, AnalysisStatus.COMPLETED}:
            raise ValueError("save_results requires PARTIAL or COMPLETED status")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM media_analysis_artifacts WHERE run_id=?", (run_id,)
            )
            connection.execute(
                "DELETE FROM media_transcript_segments WHERE run_id=?", (run_id,)
            )
            connection.execute(
                "DELETE FROM media_ocr_segments WHERE run_id=?", (run_id,)
            )
            connection.executemany(
                """
                INSERT INTO media_analysis_artifacts
                (run_id, artifact_key, kind, path, sha256, size_bytes, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        run_id,
                        item.artifact_key,
                        item.kind,
                        item.path,
                        item.sha256,
                        item.size_bytes,
                        json.dumps(item.metadata, ensure_ascii=False, sort_keys=True),
                    )
                    for item in artifacts
                ],
            )
            if asr_adapter is not None:
                connection.executemany(
                    """
                    INSERT INTO media_transcript_segments
                    (run_id, segment_index, start_ms, end_ms, text_content,
                     adapter_name, adapter_version)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            run_id,
                            index,
                            item.start_ms,
                            item.end_ms,
                            item.text,
                            asr_adapter.name,
                            asr_adapter.version,
                        )
                        for index, item in enumerate(transcripts)
                    ],
                )
            if ocr_adapter is not None:
                connection.executemany(
                    """
                    INSERT INTO media_ocr_segments
                    (run_id, segment_index, timestamp_ms, text_content,
                     bounding_box_json, adapter_name, adapter_version)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            run_id,
                            index,
                            item.timestamp_ms,
                            item.text,
                            json.dumps(item.bounding_box)
                            if item.bounding_box is not None
                            else None,
                            ocr_adapter.name,
                            ocr_adapter.version,
                        )
                        for index, item in enumerate(ocr_segments)
                    ],
                )
            connection.execute(
                """
                UPDATE media_analysis_runs
                SET status=?, duration_seconds=?, warnings_json=?, error=NULL,
                    updated_at=?
                WHERE run_id=?
                """,
                (
                    status.value,
                    duration_seconds,
                    json.dumps(warnings, ensure_ascii=False),
                    _now(),
                    run_id,
                ),
            )

    def get(self, run_id: str) -> MediaAnalysisResult:
        with self._connect() as connection:
            run = connection.execute(
                "SELECT * FROM media_analysis_runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if run is None:
                raise KeyError(f"media analysis run not found: {run_id}")
            artifact_rows = connection.execute(
                """
                SELECT * FROM media_analysis_artifacts
                WHERE run_id=? ORDER BY kind, artifact_key
                """,
                (run_id,),
            ).fetchall()
            transcript_rows = connection.execute(
                """
                SELECT * FROM media_transcript_segments
                WHERE run_id=? ORDER BY segment_index
                """,
                (run_id,),
            ).fetchall()
            ocr_rows = connection.execute(
                """
                SELECT * FROM media_ocr_segments
                WHERE run_id=? ORDER BY segment_index
                """,
                (run_id,),
            ).fetchall()

        artifacts = tuple(
            AnalysisArtifact(
                artifact_key=row["artifact_key"],
                kind=row["kind"],
                path=row["path"],
                sha256=row["sha256"],
                size_bytes=row["size_bytes"],
                metadata=json.loads(row["metadata_json"]),
            )
            for row in artifact_rows
        )
        transcripts = tuple(
            TranscriptSegment(
                start_ms=row["start_ms"],
                end_ms=row["end_ms"],
                text=row["text_content"],
            )
            for row in transcript_rows
        )
        ocr_segments = tuple(
            OCRSegment(
                timestamp_ms=row["timestamp_ms"],
                text=row["text_content"],
                bounding_box=json.loads(row["bounding_box_json"])
                if row["bounding_box_json"]
                else None,
            )
            for row in ocr_rows
        )
        return MediaAnalysisResult(
            run_id=run["run_id"],
            asset_id=run["asset_id"],
            source_sha256=run["source_sha256"],
            config_hash=run["config_hash"],
            status=AnalysisStatus(run["status"]),
            attempts=run["attempts"],
            duration_seconds=run["duration_seconds"],
            artifacts=artifacts,
            transcripts=transcripts,
            ocr_segments=ocr_segments,
            warnings=tuple(json.loads(run["warnings_json"])),
            error=run["error"],
        )


class MediaAnalysisPipeline:
    """Extract audio/frame evidence and optionally run configured ASR/OCR adapters."""

    def __init__(
        self,
        asset_repository: MediaAssetRepository,
        analysis_repository: MediaAnalysisRepository,
        output_root: str | Path,
        *,
        ffmpeg: FFmpegProcessor | None = None,
        asr_adapter: ASRAdapter | None = None,
        ocr_adapter: OCRAdapter | None = None,
        frame_interval_seconds: float = 5.0,
        max_frames: int = 240,
    ) -> None:
        if not math.isfinite(frame_interval_seconds) or frame_interval_seconds <= 0:
            raise ValueError("frame_interval_seconds must be finite and positive")
        if max_frames < 1:
            raise ValueError("max_frames must be at least 1")
        self.assets = asset_repository
        self.repository = analysis_repository
        self.output_root = Path(output_root).expanduser().resolve()
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.ffmpeg = ffmpeg or FFmpegProcessor()
        self.asr_adapter = asr_adapter
        self.ocr_adapter = ocr_adapter
        self.frame_interval_seconds = frame_interval_seconds
        self.max_frames = max_frames

    @staticmethod
    def _local_asset_path(storage_uri: str) -> Path:
        parsed = urlparse(storage_uri)
        if parsed.scheme != "file":
            raise ValueError(
                f"media analysis currently requires a local file asset: {storage_uri}"
            )
        if parsed.netloc not in ("", "localhost"):
            raise ValueError("network file URIs are not supported")
        return Path(url2pathname(unquote(parsed.path))).expanduser().resolve(strict=True)

    @staticmethod
    def _duration_seconds(probe: dict[str, Any]) -> float | None:
        raw = probe.get("format", {}).get("duration")
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None
        return value if math.isfinite(value) and value >= 0 else None

    @staticmethod
    def _validate_transcripts(
        segments: list[TranscriptSegment],
    ) -> list[TranscriptSegment]:
        validated: list[TranscriptSegment] = []
        previous_start = -1
        for item in segments:
            if (
                isinstance(item.start_ms, bool)
                or isinstance(item.end_ms, bool)
                or item.start_ms < 0
                or item.end_ms <= item.start_ms
                or item.start_ms < previous_start
                or not item.text.strip()
            ):
                raise ValueError("ASR adapter returned an invalid transcript segment")
            validated.append(item)
            previous_start = item.start_ms
        return validated

    @staticmethod
    def _validate_ocr(segments: list[OCRSegment]) -> list[OCRSegment]:
        validated: list[OCRSegment] = []
        for item in segments:
            if (
                isinstance(item.timestamp_ms, bool)
                or item.timestamp_ms < 0
                or not item.text.strip()
            ):
                raise ValueError("OCR adapter returned an invalid OCR segment")
            if item.bounding_box is not None and (
                len(item.bounding_box) != 4
                or any(not math.isfinite(value) for value in item.bounding_box)
            ):
                raise ValueError("OCR adapter returned an invalid bounding box")
            validated.append(item)
        return validated

    @staticmethod
    def _artifact(path: Path, kind: str, key: str, **metadata: Any) -> AnalysisArtifact:
        return AnalysisArtifact(
            artifact_key=key,
            kind=kind,
            path=str(path.resolve(strict=True)),
            sha256=sha256_file(path),
            size_bytes=path.stat().st_size,
            metadata=metadata,
        )

    def analyze(self, asset_id: str) -> MediaAnalysisResult:
        asset = self.assets.get(asset_id)
        source_path = self._local_asset_path(asset.storage_uri)
        if source_path.stat().st_size != asset.size_bytes:
            raise ValueError("media asset size changed since registration")
        source_hash = sha256_file(source_path)
        if source_hash != asset.sha256:
            raise ValueError("media asset SHA-256 changed since registration")

        settings = {
            "pipeline_version": 1,
            "frame_interval_seconds": self.frame_interval_seconds,
            "max_frames": self.max_frames,
            "ffmpeg_binary": self.ffmpeg.ffmpeg_binary,
            "ffprobe_binary": self.ffmpeg.ffprobe_binary,
            "asr": (
                {"name": self.asr_adapter.name, "version": self.asr_adapter.version}
                if self.asr_adapter is not None
                else None
            ),
            "ocr": (
                {"name": self.ocr_adapter.name, "version": self.ocr_adapter.version}
                if self.ocr_adapter is not None
                else None
            ),
        }
        config_hash = hashlib.sha256(
            json.dumps(settings, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        run_id, should_execute = self.repository.start_or_resume(
            asset_id=asset_id,
            source_sha256=source_hash,
            config_hash=config_hash,
            settings=settings,
        )
        if not should_execute:
            return self.repository.get(run_id)

        try:
            probe = self.ffmpeg.probe(source_path)
            duration = self._duration_seconds(probe)
            streams = probe.get("streams", [])
            has_audio = any(
                isinstance(stream, dict) and stream.get("codec_type") == "audio"
                for stream in streams
            )
            has_video = any(
                isinstance(stream, dict) and stream.get("codec_type") == "video"
                for stream in streams
            )
            run_dir = self.output_root / asset_id / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            artifacts: list[AnalysisArtifact] = []
            transcripts: list[TranscriptSegment] = []
            ocr_segments: list[OCRSegment] = []
            warnings: list[str] = []
            audio_path: Path | None = None
            frames: list[Path] = []
            effective_interval = self.frame_interval_seconds

            if has_audio:
                audio_path = self.ffmpeg.extract_audio(
                    source_path, run_dir / "audio.wav"
                )
                if audio_path.stat().st_size <= 0:
                    raise ValueError("FFmpeg produced an empty audio artifact")
                artifacts.append(self._artifact(audio_path, "AUDIO", "audio"))
            else:
                warnings.append("No audio stream; ASR was skipped")

            if has_video:
                if duration is not None and duration > 0:
                    effective_interval = max(
                        self.frame_interval_seconds,
                        duration / self.max_frames,
                    )
                frames = self.ffmpeg.extract_frames(
                    source_path,
                    run_dir / "frames",
                    interval_seconds=effective_interval,
                )
                for index, frame_path in enumerate(frames):
                    artifacts.append(
                        self._artifact(
                            frame_path,
                            "FRAME",
                            f"frame:{index:06d}",
                            timestamp_ms=round(index * effective_interval * 1000),
                            interval_seconds=effective_interval,
                        )
                    )
            else:
                warnings.append("No video stream; frame extraction was skipped")

            if self.asr_adapter is not None and audio_path is not None:
                transcripts = self._validate_transcripts(
                    self.asr_adapter.transcribe(audio_path)
                )
            elif self.asr_adapter is None:
                warnings.append("ASR adapter not configured")
            if self.ocr_adapter is not None and frames:
                for index, frame_path in enumerate(frames):
                    timestamp_ms = round(index * effective_interval * 1000)
                    ocr_segments.extend(
                        self._validate_ocr(
                            self.ocr_adapter.recognize(frame_path, timestamp_ms)
                        )
                    )
            elif self.ocr_adapter is None:
                warnings.append("OCR adapter not configured")

            status = (
                AnalysisStatus.COMPLETED
                if not warnings and self.asr_adapter is not None and self.ocr_adapter is not None
                else AnalysisStatus.PARTIAL
            )
            self.repository.save_results(
                run_id,
                status=status,
                duration_seconds=duration,
                artifacts=artifacts,
                transcripts=transcripts,
                ocr_segments=ocr_segments,
                warnings=warnings,
                asr_adapter=self.asr_adapter,
                ocr_adapter=self.ocr_adapter,
            )
            return self.repository.get(run_id)
        except Exception as exc:
            self.repository.mark_failed(
                run_id, f"{type(exc).__name__}: {exc}"
            )
            raise
