"""Acquisition orchestration: search, select, archive, retrieve, evidence, cleanup."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aios_work_system.acquisition.drive import DriveStorage
from aios_work_system.acquisition.evidence import (
    EvidenceExtractionContext,
    EvidenceExtractor,
)
from aios_work_system.acquisition.models import (
    AcquisitionRecord,
    SelectionCriteria,
    VideoCandidate,
)
from aios_work_system.acquisition.platforms import PlatformAdapter
from aios_work_system.acquisition.records import JsonlRecordStore
from aios_work_system.acquisition.selector import VideoSelector
from aios_work_system.media.source import sha256_file


class AcquisitionError(RuntimeError):
    """Raised for acquisition workflow errors that prevent a valid archive."""


class AcquisitionPipeline:
    """Execute one logical course item at a time and persist every state transition."""

    def __init__(
        self,
        platform: PlatformAdapter,
        selector: VideoSelector,
        drive: DriveStorage,
        evidence_extractor: EvidenceExtractor,
        *,
        record_store: JsonlRecordStore | None = None,
        staging_dir: str | Path = "artifacts/acquisition/downloads",
        work_dir: str | Path = "artifacts/acquisition/drive-work",
        evidence_dir: str | Path = "artifacts/acquisition/evidence",
    ) -> None:
        self.platform = platform
        self.selector = selector
        self.drive = drive
        self.evidence_extractor = evidence_extractor
        self.record_store = record_store or JsonlRecordStore()
        self.staging_dir = Path(staging_dir).expanduser().resolve()
        self.work_dir = Path(work_dir).expanduser().resolve()
        self.evidence_dir = Path(evidence_dir).expanduser().resolve()

    def search(self, query: str, max_results: int = 20) -> list[VideoCandidate]:
        return self.platform.search(query, max_results=max_results)

    def run_search(
        self,
        query: str,
        criteria: SelectionCriteria,
        *,
        max_results: int = 20,
    ) -> tuple[list[VideoCandidate], list[AcquisitionRecord]]:
        candidates = self.search(query, max_results=max_results)
        selected = self.selector.select(candidates, criteria)
        records = [self.process_one(candidate) for candidate in selected]
        return candidates, records

    @staticmethod
    def _safe_id(video_id: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", video_id).strip(" ._")
        return safe or "video"

    @staticmethod
    def _remove_and_verify(path: Path) -> bool:
        try:
            if path.exists():
                path.unlink()
            return not path.exists()
        except OSError:
            return False

    @staticmethod
    def _add_acquisition_provenance(
        payload: dict[str, Any],
        candidate: VideoCandidate,
        record: AcquisitionRecord,
    ) -> dict[str, Any]:
        provenance = {
            "video_url": candidate.video_url,
            "platform": candidate.platform,
            "uploader": candidate.uploader,
            "series": candidate.series or "unknown",
            "license": candidate.license_info or "unknown",
            "source_sha256": record.source_sha256,
            "drive_file_id": record.drive_file_id,
            "drive_link": record.drive_link,
            "drive_path": record.drive_path,
        }
        payload.setdefault("acquisition_provenance", {}).update(provenance)
        for evidence in payload.get("records") or []:
            evidence.setdefault("provenance", {}).update(provenance)
        return payload

    def process_one(self, candidate: VideoCandidate) -> AcquisitionRecord:
        record = AcquisitionRecord.from_candidate(candidate)
        self.record_store.upsert(record)
        staged_file: Path | None = None
        work_copy: Path | None = None
        staged_file_created = False
        work_copy_created = False

        self.staging_dir.mkdir(parents=True, exist_ok=True)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

        try:
            staged_file = Path(
                self.platform.download(candidate, self.staging_dir)
            ).expanduser().resolve(strict=True)
            if not staged_file.is_file() or not staged_file.is_relative_to(self.staging_dir):
                raise AcquisitionError(
                    "Downloader returned a file outside the configured staging directory"
                )
            staged_file_created = True
            record.download_time = datetime.now(UTC).isoformat()
            record.source_sha256 = sha256_file(staged_file)
            self.record_store.upsert(record)

            uploaded = self.drive.upload_video(staged_file, candidate)
            record.drive_file_id = uploaded.file.file_id
            record.drive_link = uploaded.file.web_view_link
            record.drive_path = uploaded.drive_path
            record.upload_status = "uploaded"
            self.record_store.upsert(record)

            # The extractor must receive a fresh Drive copy, never the original
            # yt-dlp staging file.
            if not self._remove_and_verify(staged_file):
                record.download_cache_deletion_status = "delete_failed"
                raise AcquisitionError("Could not remove the original downloaded staging file")
            record.download_cache_deletion_status = "deleted"
            self.record_store.upsert(record)

            work_copy = (
                self.work_dir
                / record.record_id
                / f"{self._safe_id(candidate.video_id)}{staged_file.suffix}"
            )
            self.drive.download_file(record.drive_file_id, work_copy)
            work_copy_created = work_copy.is_file()
            if not work_copy_created:
                raise AcquisitionError("Drive returned without creating the working copy")
            downloaded_hash = sha256_file(work_copy)
            if downloaded_hash != record.source_sha256:
                raise AcquisitionError(
                    "Drive round-trip SHA-256 mismatch; refusing to extract altered content"
                )

            context = EvidenceExtractionContext(
                candidate=candidate,
                source_sha256=record.source_sha256 or "",
                drive=uploaded,
            )
            evidence_payload = self.evidence_extractor.extract(work_copy, context)
            evidence_payload = self._add_acquisition_provenance(
                evidence_payload, candidate, record
            )
            evidence_path = self.evidence_dir / f"{record.record_id}.json"
            temporary = evidence_path.with_name(evidence_path.name + ".tmp")
            temporary.write_text(
                json.dumps(evidence_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary.replace(evidence_path)
            record.evidence_path = str(evidence_path)
            record.extraction_status = "completed"
        except Exception as exc:
            if record.upload_status == "pending":
                record.upload_status = "failed"
            record.extraction_status = (
                "failed" if record.upload_status == "uploaded" else "not_started"
            )
            record.error = f"{type(exc).__name__}: {exc}"
        finally:
            if staged_file is not None and staged_file_created:
                if self._remove_and_verify(staged_file):
                    if record.download_cache_deletion_status != "deleted":
                        record.download_cache_deletion_status = "deleted"
                else:
                    record.download_cache_deletion_status = "delete_failed"
                    record.error = self._append_error(
                        record.error, "Could not verify deletion of downloader staging file"
                    )
            if work_copy is not None:
                work_copy_created = work_copy_created or work_copy.is_file()
                if work_copy_created:
                    if self._remove_and_verify(work_copy):
                        record.deletion_status = "deleted"
                    else:
                        record.deletion_status = "delete_failed"
                        record.error = self._append_error(
                            record.error, "Could not verify deletion of Drive working copy"
                        )
                else:
                    record.deletion_status = "not_created"
                self._remove_empty_parent(work_copy.parent)
            self.record_store.upsert(record)
        return record

    @staticmethod
    def _append_error(current: str | None, message: str) -> str:
        return f"{current}; {message}" if current else message

    @staticmethod
    def _remove_empty_parent(path: Path) -> None:
        try:
            path.rmdir()
        except OSError:
            pass
