"""Validated acquisition metadata and durable record shape."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class VideoCandidate:
    video_id: str
    video_url: str
    platform: str
    uploader: str
    title: str
    duration_seconds: float | None
    series: str | None = None
    license_info: str = "unknown"
    license_source: str = "unknown"
    license_verification: str = "unknown"
    description: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @property
    def series_folder(self) -> str:
        return self.series.strip() if self.series and self.series.strip() else "未分组"


@dataclass(frozen=True)
class SelectionCriteria:
    title_keywords: tuple[str, ...] = ()
    series_keywords: tuple[str, ...] = ()
    min_duration_seconds: float = 0
    max_duration_seconds: float = 1200
    allowed_license_terms: tuple[str, ...] = ()
    allow_unknown_license: bool = True
    limit: int = 1


@dataclass
class AcquisitionRecord:
    record_id: str
    video_url: str
    platform: str
    uploader: str
    title: str
    duration_seconds: float | None
    series: str | None
    license_info: str
    license_source: str
    license_verification: str
    discovered_at: str
    download_time: str | None = None
    source_sha256: str | None = None
    drive_file_id: str | None = None
    drive_link: str | None = None
    drive_path: str | None = None
    upload_status: str = "pending"
    extraction_status: str = "not_started"
    deletion_status: str = "not_created"
    download_cache_deletion_status: str = "not_created"
    evidence_path: str | None = None
    error: str | None = None

    @classmethod
    def from_candidate(cls, candidate: VideoCandidate) -> AcquisitionRecord:
        return cls(
            record_id=str(uuid4()),
            video_url=candidate.video_url,
            platform=candidate.platform,
            uploader=candidate.uploader,
            title=candidate.title,
            duration_seconds=candidate.duration_seconds,
            series=candidate.series,
            license_info=candidate.license_info or "unknown",
            license_source=candidate.license_source or "unknown",
            license_verification=candidate.license_verification or "unknown",
            discovered_at=datetime.now(UTC).isoformat(),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
