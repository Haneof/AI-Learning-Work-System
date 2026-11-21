"""Evidence extraction contract and lazy bridge to the video-learning PR #26 engine."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Protocol

from aios_work_system.acquisition.drive import DriveUploadResult
from aios_work_system.acquisition.models import VideoCandidate


@dataclass(frozen=True)
class EvidenceExtractionContext:
    candidate: VideoCandidate
    source_sha256: str
    drive: DriveUploadResult


class EvidenceExtractor(Protocol):
    def extract(
        self,
        video_path: Path,
        context: EvidenceExtractionContext,
    ) -> dict[str, Any]:
        """Extract evidence from a local Drive copy and return the evidence payload."""


class EvidenceEngineUnavailable(RuntimeError):
    """Raised when the reusable PR #26 extraction engine is not available."""


class PR26VideoLearningAdapter:
    """Adapter for PR #26; import only when extraction is requested.

    PR #26 is intentionally not copied into this branch. Merge it into main first,
    then pass concrete ASR/OCR implementations here.
    """

    def __init__(
        self,
        asr_adapter: object,
        ocr_adapter: object,
        *,
        ffmpeg_processor: object | None = None,
        frame_interval_seconds: float = 15.0,
        chunk_duration_seconds: int = 30,
    ) -> None:
        self.asr_adapter = asr_adapter
        self.ocr_adapter = ocr_adapter
        self.ffmpeg_processor = ffmpeg_processor
        self.frame_interval_seconds = frame_interval_seconds
        self.chunk_duration_seconds = chunk_duration_seconds

    def extract(
        self,
        video_path: Path,
        context: EvidenceExtractionContext,
    ) -> dict[str, Any]:
        try:
            from aios_work_system.video_learning import VideoLearningPipeline
        except ImportError as exc:
            raise EvidenceEngineUnavailable(
                "The reusable VideoLearningPipeline from PR #26 is not present on "
                "main yet. Merge PR #26 before enabling extraction; this acquisition "
                "branch deliberately does not duplicate its media-learning engine."
            ) from exc

        candidate = context.candidate
        series = candidate.series or "未分组"
        applicability_scope = (
            f"Platform: {candidate.platform}; creator: {candidate.uploader}; "
            f"series: {series}; tutorial: {candidate.title}. "
            "Verify the target software version and current UI before reuse."
        )
        pipeline = VideoLearningPipeline(
            asr=self.asr_adapter,
            ocr=self.ocr_adapter,
            ffmpeg=self.ffmpeg_processor,
        )
        with TemporaryDirectory(prefix="aios-video-evidence-") as temporary:
            result = pipeline.ingest(
                video_path,
                temporary,
                expert_id=f"{candidate.platform}:{candidate.uploader}",
                applicability_scope=applicability_scope,
                source_version=f"sha256:{context.source_sha256}",
                knowledge_version=1,
                frame_interval_seconds=self.frame_interval_seconds,
                chunk_duration_seconds=self.chunk_duration_seconds,
            )
            payload = json.loads(result.evidence_path.read_text(encoding="utf-8"))

        acquisition_provenance = {
            "video_url": candidate.video_url,
            "platform": candidate.platform,
            "uploader": candidate.uploader,
            "series": candidate.series or "unknown",
            "drive_file_id": context.drive.file.file_id,
            "drive_link": context.drive.file.web_view_link,
            "drive_path": context.drive.drive_path,
            "source_sha256": context.source_sha256,
        }
        payload["acquisition_provenance"] = acquisition_provenance
        for record in payload.get("records") or []:
            provenance = record.setdefault("provenance", {})
            provenance.update(acquisition_provenance)
        return payload
