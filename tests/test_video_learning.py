"""End-to-end tests for timestamped video knowledge evidence with stub adapters."""

import json

import pytest

from aios_work_system.media.adapters import OCRSegment, TranscriptSegment
from aios_work_system.video_learning import (
    StaticASRAdapter,
    StaticOCRAdapter,
    VideoLearningPipeline,
)


class FakeFFmpeg:
    def probe(self, _source):
        return {
            "format": {"duration": "65.0"},
            "streams": [{"codec_type": "video"}, {"codec_type": "audio"}],
        }

    def extract_audio(self, _source, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"fake wav")
        return destination.resolve()

    def extract_frames(self, _source, output_dir, interval_seconds):
        assert interval_seconds == 30
        output_dir.mkdir(parents=True, exist_ok=True)
        frames = []
        for index in range(3):
            frame = output_dir / f"frame_{index + 1:06d}.jpg"
            frame.write_bytes(b"fake frame")
            frames.append(frame.resolve())
        return frames


class TimestampOCR:
    name = "ocr-test-stub"
    version = "test"

    def recognize(self, _image_path, timestamp_ms):
        return [OCRSegment(timestamp_ms=timestamp_ms, text=f"UI text at {timestamp_ms}ms")]


def test_video_to_evidence_pipeline_preserves_file_time_version_and_scope(tmp_path):
    video = tmp_path / "lesson.webm"
    video.write_bytes(b"video-placeholder")
    asr = StaticASRAdapter(
        name="asr-test-stub",
        version="test",
        segments=[
            TranscriptSegment(1_000, 5_000, "Open the settings menu."),
            TranscriptSegment(31_000, 38_000, "Select the translation dashboard."),
        ],
    )
    pipeline = VideoLearningPipeline(
        asr=asr,
        ocr=TimestampOCR(),
        ffmpeg=FakeFFmpeg(),
    )

    result = pipeline.ingest(
        video,
        tmp_path / "artifacts",
        expert_id="expert-software",
        applicability_scope="Content Translation workflow; verify current UI before reuse",
        source_version="commons-2015-01-13",
        knowledge_version=3,
        frame_interval_seconds=30,
        chunk_duration_seconds=30,
    )

    assert len(result.temporal_segments) == 3
    assert result.temporal_segments[0].locator == {"start_ms": 0, "end_ms": 30_000}
    assert result.temporal_segments[-1].locator == {"start_ms": 60_000, "end_ms": 65_000}
    assert result.source.sha256
    assert result.audio_path.is_file()
    assert len(result.frame_paths) == 3
    assert len(result.knowledge_items) == 3

    first = result.evidence_records[0]
    provenance = first["provenance"]
    assert provenance["source_file"] == "lesson.webm"
    assert provenance["source_sha256"] == result.source.sha256
    assert provenance["source_version"] == "commons-2015-01-13"
    assert provenance["timestamp"] == {"start_ms": 0, "end_ms": 30_000}
    assert provenance["expert_id"] == "expert-software"
    assert provenance["applicability_scope"].startswith("Content Translation")
    assert first["knowledge_version"] == 3
    assert first["epistemic_type"] == "DIRECT_QUOTE"
    assert "[ASR_STUB" in first["statement"]
    assert "[OCR_STUB" in first["statement"]
    assert first["evidence"][0]["excerpt"] == first["statement"]

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    evidence = json.loads(result.evidence_path.read_text(encoding="utf-8"))
    assert manifest["sha256"] == result.source.sha256
    assert any(segment["segment_type"] == "AUDIO_TRACK" for segment in manifest["segments"])
    assert len(evidence["records"]) == 3
    assert evidence["records"][0]["provenance"]["timestamp"]["start_ms"] == 0


def test_pipeline_rejects_invalid_asr_timestamps(tmp_path):
    video = tmp_path / "broken.mp4"
    video.write_bytes(b"video-placeholder")
    pipeline = VideoLearningPipeline(
        asr=StaticASRAdapter(
            name="bad-asr",
            version="test",
            segments=[TranscriptSegment(10, 5, "invalid interval")],
        ),
        ocr=StaticOCRAdapter(name="ocr", version="test", text_by_timestamp={}),
        ffmpeg=FakeFFmpeg(),
    )

    with pytest.raises(ValueError, match="invalid timestamp interval"):
        pipeline.ingest(
            video,
            tmp_path / "artifacts",
            expert_id="expert-a",
            applicability_scope="test-only",
            frame_interval_seconds=30,
        )


def test_pipeline_requires_explicit_applicability_scope(tmp_path):
    video = tmp_path / "lesson.mp4"
    video.write_bytes(b"video-placeholder")
    pipeline = VideoLearningPipeline(
        asr=StaticASRAdapter(name="asr", version="test", segments=[]),
        ocr=StaticOCRAdapter(name="ocr", version="test", text_by_timestamp={}),
        ffmpeg=FakeFFmpeg(),
    )

    with pytest.raises(ValueError, match="applicability_scope is required"):
        pipeline.ingest(
            video,
            tmp_path / "artifacts",
            expert_id="expert-a",
            applicability_scope=" ",
        )
