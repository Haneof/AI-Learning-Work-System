"""Video media ingestion to traceable, candidate knowledge evidence."""

from __future__ import annotations

import json
import uuid
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from aios_work_system.knowledge import (
    ConfidenceLabel,
    EpistemicType,
    EvidenceLink,
    EvidenceRelation,
    KnowledgeItem,
    KnowledgeRegistry,
    KnowledgeState,
    KnowledgeType,
    SourceSegment,
)
from aios_work_system.media.adapters import (
    ASRAdapter,
    OCRAdapter,
    OCRSegment,
    TranscriptSegment,
)
from aios_work_system.media.ffmpeg import FFmpegProcessor, MediaProcessingError
from aios_work_system.media.source import SegmentRecord, SourceManifest, register_source


@dataclass(frozen=True)
class StaticASRAdapter:
    """Deterministic ASR stand-in; supplied text is not a model transcription."""

    name: str
    version: str
    segments: list[TranscriptSegment]

    def transcribe(self, audio_path: Path) -> list[TranscriptSegment]:
        if not audio_path.is_file():
            raise FileNotFoundError(audio_path)
        return list(self.segments)


@dataclass(frozen=True)
class StaticOCRAdapter:
    """Deterministic OCR stand-in keyed by frame timestamp in milliseconds."""

    name: str
    version: str
    text_by_timestamp: dict[int, str]

    def recognize(self, image_path: Path, timestamp_ms: int) -> list[OCRSegment]:
        if not image_path.is_file():
            raise FileNotFoundError(image_path)
        text = self.text_by_timestamp.get(timestamp_ms, "").strip()
        return [OCRSegment(timestamp_ms=timestamp_ms, text=text)] if text else []


class KnowledgeExtractor(Protocol):
    name: str
    version: str

    def extract_quote(self, segment_text: str) -> str | None:
        """Return a verbatim excerpt, or None when no evidence should be emitted."""


@dataclass(frozen=True)
class VerbatimQuoteExtractor:
    """No-model baseline: preserve each timed chunk as a candidate direct quote."""

    name: str = "verbatim-quote-stub"
    version: str = "1"

    def extract_quote(self, segment_text: str) -> str | None:
        return segment_text.strip() or None


@dataclass
class VideoLearningResult:
    source: SourceManifest
    audio_path: Path
    frame_paths: list[Path]
    temporal_segments: list[SegmentRecord]
    knowledge_items: list[KnowledgeItem]
    evidence_records: list[dict[str, Any]]
    manifest_path: Path
    evidence_path: Path


class VideoLearningPipeline:
    """Create time-addressable text segments and candidate knowledge evidence."""

    VERSION = "0.1.0"

    def __init__(
        self,
        asr: ASRAdapter,
        ocr: OCRAdapter,
        ffmpeg: FFmpegProcessor | None = None,
        extractor: KnowledgeExtractor | None = None,
    ) -> None:
        self.asr = asr
        self.ocr = ocr
        self.ffmpeg = ffmpeg or FFmpegProcessor()
        self.extractor = extractor or VerbatimQuoteExtractor()

    def ingest(
        self,
        video_path: str | Path,
        output_dir: str | Path,
        *,
        expert_id: str,
        applicability_scope: str,
        source_version: str = "1",
        knowledge_version: int = 1,
        frame_interval_seconds: float = 15.0,
        chunk_duration_seconds: int = 30,
    ) -> VideoLearningResult:
        if not expert_id.strip():
            raise ValueError("expert_id is required")
        if not applicability_scope.strip():
            raise ValueError("applicability_scope is required")
        if not source_version.strip():
            raise ValueError("source_version is required")
        if knowledge_version < 1:
            raise ValueError("knowledge_version must be at least 1")
        if frame_interval_seconds <= 0 or chunk_duration_seconds <= 0:
            raise ValueError("frame interval and chunk duration must be positive")

        original = Path(video_path).expanduser().resolve(strict=True)
        destination = Path(output_dir).expanduser().resolve()
        destination.mkdir(parents=True, exist_ok=True)
        source = register_source(
            original,
            "VIDEO",
            parser_name="video-learning-pipeline",
            parser_version=self.VERSION,
        )

        metadata = self.ffmpeg.probe(original)
        streams = metadata.get("streams", [])
        if not any(stream.get("codec_type") == "video" for stream in streams):
            raise MediaProcessingError("Input media has no video stream")
        if not any(stream.get("codec_type") == "audio" for stream in streams):
            raise MediaProcessingError("Input video has no audio stream")
        duration_seconds = float(metadata.get("format", {}).get("duration", 0) or 0)
        if duration_seconds <= 0:
            raise MediaProcessingError("Input video has no valid positive duration")
        duration_ms = round(duration_seconds * 1000)

        audio_path = self.ffmpeg.extract_audio(
            original, destination / f"{original.stem}.mono-16khz.wav"
        )
        frame_dir = destination / "frames"
        frames = self.ffmpeg.extract_frames(
            original, frame_dir, interval_seconds=frame_interval_seconds
        )

        source.add_segment(
            SegmentRecord.create(
                source_id=source.source_id,
                segment_type="AUDIO_TRACK",
                locator={"start_ms": 0, "end_ms": duration_ms},
                parser_name="ffmpeg",
                parser_version="system",
                media_uri=audio_path.as_uri(),
            )
        )
        for index, frame_path in enumerate(frames):
            timestamp_ms = round(index * frame_interval_seconds * 1000)
            if timestamp_ms >= duration_ms:
                continue
            source.add_segment(
                SegmentRecord.create(
                    source_id=source.source_id,
                    segment_type="FRAME",
                    locator={"timestamp_ms": timestamp_ms},
                    parser_name="ffmpeg",
                    parser_version="system",
                    media_uri=frame_path.as_uri(),
                )
            )

        # Events are assigned to fixed, deterministic time windows. Modality
        # labels remain in the text so readers can distinguish ASR from OCR.
        events: dict[int, list[tuple[int, str]]] = defaultdict(list)
        transcripts = self.asr.transcribe(audio_path)
        for item in transcripts:
            if item.start_ms < 0 or item.end_ms <= item.start_ms:
                raise ValueError("ASR returned an invalid timestamp interval")
            if item.end_ms > duration_ms:
                raise ValueError("ASR timestamp exceeds video duration")
            text = item.text.strip()
            if text:
                bucket = item.start_ms // (chunk_duration_seconds * 1000)
                events[bucket].append(
                    (
                        item.start_ms,
                        f"[ASR_STUB {item.start_ms}-{item.end_ms}ms] {text}",
                    )
                )

        for index, frame_path in enumerate(frames):
            timestamp_ms = round(index * frame_interval_seconds * 1000)
            if timestamp_ms >= duration_ms:
                continue
            for item in self.ocr.recognize(frame_path, timestamp_ms):
                if item.timestamp_ms < 0 or item.timestamp_ms >= duration_ms:
                    raise ValueError("OCR timestamp is outside video duration")
                text = item.text.strip()
                if text:
                    bucket = item.timestamp_ms // (chunk_duration_seconds * 1000)
                    events[bucket].append(
                        (
                            item.timestamp_ms,
                            f"[OCR_STUB @{item.timestamp_ms}ms] {text}",
                        )
                    )

        if not events:
            raise MediaProcessingError("ASR and OCR adapters returned no usable text")

        registry = KnowledgeRegistry()
        temporal_segments: list[SegmentRecord] = []
        knowledge_items: list[KnowledgeItem] = []
        evidence_records: list[dict[str, Any]] = []
        chunk_ms = chunk_duration_seconds * 1000

        for bucket in sorted(events):
            start_ms = bucket * chunk_ms
            end_ms = min((bucket + 1) * chunk_ms, duration_ms)
            if end_ms <= start_ms:
                continue
            ordered_lines = [line for _, line in sorted(events[bucket], key=lambda event: event[0])]
            text_content = "\n".join(ordered_lines)
            media_segment = SegmentRecord.create(
                source_id=source.source_id,
                segment_type="TIME_RANGE",
                locator={"start_ms": start_ms, "end_ms": end_ms},
                parser_name="video-learning-chunker",
                parser_version=self.VERSION,
                text_content=text_content,
            )
            source.add_segment(media_segment)
            temporal_segments.append(media_segment)

            source_segment = SourceSegment(
                segment_id=media_segment.segment_id,
                source_id=source.source_id,
                expert_id=expert_id,
                locator={"start_ms": start_ms, "end_ms": end_ms},
                text_content=text_content,
                source_file=source.original_name,
                source_sha256=source.sha256,
                source_version=source_version,
                media_uri=source.storage_uri,
            )
            registry.add_segment(source_segment)
            quote = self.extractor.extract_quote(text_content)
            if not quote:
                continue
            item = KnowledgeItem(
                knowledge_id=str(uuid.uuid4()),
                expert_id=expert_id,
                statement=quote,
                knowledge_type=KnowledgeType.PROCEDURE,
                epistemic_type=EpistemicType.DIRECT_QUOTE,
                state=KnowledgeState.CANDIDATE,
                confidence=ConfidenceLabel.LOW,
                version=knowledge_version,
                evidence=[
                    EvidenceLink(
                        source_id=source.source_id,
                        segment_id=media_segment.segment_id,
                        relation=EvidenceRelation.SUPPORTS,
                        excerpt=quote,
                    )
                ],
                applicability_scope=applicability_scope,
            )
            validation = registry.add_knowledge(item)
            if not validation.accepted:
                raise ValueError(f"Generated evidence failed validation: {validation.errors}")
            knowledge_items.append(item)
            evidence_records.append(
                {
                    "knowledge_id": item.knowledge_id,
                    "statement": item.statement,
                    "knowledge_type": item.knowledge_type.value,
                    "epistemic_type": item.epistemic_type.value,
                    "state": item.state.value,
                    "confidence": item.confidence.value,
                    "knowledge_version": item.version,
                    "applicability_scope": item.applicability_scope,
                    "evidence": [
                        {
                            "source_id": link.source_id,
                            "segment_id": link.segment_id,
                            "relation": link.relation.value,
                            "excerpt": link.excerpt,
                        }
                        for link in item.evidence
                    ],
                    "provenance": {
                        "source_id": source.source_id,
                        "source_file": source.original_name,
                        "source_uri": source.storage_uri,
                        "source_sha256": source.sha256,
                        "source_version": source_version,
                        "timestamp": {"start_ms": start_ms, "end_ms": end_ms},
                        "expert_id": expert_id,
                        "applicability_scope": applicability_scope,
                        "segment_parser": {
                            "name": "video-learning-chunker",
                            "version": self.VERSION,
                        },
                        "asr_adapter": {
                            "name": self.asr.name,
                            "version": self.asr.version,
                        },
                        "ocr_adapter": {
                            "name": self.ocr.name,
                            "version": self.ocr.version,
                        },
                        "knowledge_extractor": {
                            "name": self.extractor.name,
                            "version": self.extractor.version,
                        },
                    },
                }
            )

        manifest_path = destination / f"{original.stem}.manifest.json"
        evidence_path = destination / "knowledge-evidence.json"
        source.save(manifest_path)
        self._write_json(
            evidence_path,
            {
                "schema_version": "1",
                "source_id": source.source_id,
                "source_file": source.original_name,
                "source_sha256": source.sha256,
                "source_version": source_version,
                "expert_id": expert_id,
                "applicability_scope": applicability_scope,
                "records": evidence_records,
            },
        )
        return VideoLearningResult(
            source=source,
            audio_path=audio_path,
            frame_paths=frames,
            temporal_segments=temporal_segments,
            knowledge_items=knowledge_items,
            evidence_records=evidence_records,
            manifest_path=manifest_path,
            evidence_path=evidence_path,
        )

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(path)


__all__ = [
    "StaticASRAdapter",
    "StaticOCRAdapter",
    "TranscriptSegment",
    "VideoLearningPipeline",
    "VideoLearningResult",
    "VerbatimQuoteExtractor",
]
