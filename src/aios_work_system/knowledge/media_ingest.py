"""Index timestamped ASR, OCR, and frame evidence into an expert scope."""

from __future__ import annotations

import hashlib

from aios_work_system.knowledge.repository import KnowledgeRepository
from aios_work_system.knowledge.types import SourceSegment
from aios_work_system.media.analysis import MediaAnalysisResult


def index_media_analysis(
    repository: KnowledgeRepository,
    result: MediaAnalysisResult,
    *,
    expert_id: str,
) -> list[SourceSegment]:
    """Persist stable source-segment references for one media analysis result.

    Frame entries intentionally contain no generated visual description. Their
    artifact path and timestamp are available for human review, while the
    placeholder text explicitly says that visual semantics are not yet verified.
    """
    if not expert_id.strip():
        raise ValueError("expert_id is required")
    indexed: list[SourceSegment] = []

    def add(
        modality: str,
        ordinal: int,
        text_content: str,
        locator: dict[str, int],
        artifact_ref: str | None,
    ) -> None:
        identity = (
            f"{result.asset_id}|{result.run_id}|{modality}|{ordinal}|"
            f"{text_content}|{locator}"
        )
        suffix = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
        segment = SourceSegment(
            segment_id=f"media:{result.asset_id}:{modality}:{suffix}",
            source_id=result.asset_id,
            expert_id=expert_id,
            locator=locator,
            text_content=text_content,
            modality=modality,
            artifact_ref=artifact_ref,
        )
        repository.add_segment(segment)
        indexed.append(segment)

    for index, segment in enumerate(result.transcripts):
        add(
            "asr",
            index,
            segment.text,
            {"start_ms": segment.start_ms, "end_ms": segment.end_ms},
            str(result.audio_path) if result.audio_path else None,
        )

    for index, segment in enumerate(result.ocr_segments):
        add(
            "ocr",
            index,
            segment.text,
            {"timestamp_ms": segment.timestamp_ms},
            None,
        )

    frame_index = 0
    for artifact in result.artifacts:
        if artifact.kind != "FRAME":
            continue
        timestamp_ms = artifact.metadata.get("timestamp_ms")
        if isinstance(timestamp_ms, bool) or not isinstance(timestamp_ms, int):
            continue
        add(
            "video_frame",
            frame_index,
            (
                "Visual frame evidence. Its UI meaning and demonstrated action "
                "require human review."
            ),
            {"timestamp_ms": timestamp_ms},
            artifact.path,
        )
        frame_index += 1

    return indexed
