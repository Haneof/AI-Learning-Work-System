"""Durable media analysis tests: extraction, time-coded segments, and restart."""

import hashlib

import pytest

from aios_work_system.media.adapters import OCRSegment, TranscriptSegment
from aios_work_system.media.analysis import (
    AnalysisStatus,
    MediaAnalysisPipeline,
    MediaAnalysisRepository,
)
from aios_work_system.media.assets import MediaAssetRepository
from aios_work_system.media.download_jobs import DownloadJobRepository


class FakeFFmpeg:
    ffmpeg_binary = "fake-ffmpeg"
    ffprobe_binary = "fake-ffprobe"

    def __init__(self, *, duration=600.0):
        self.duration = duration
        self.probe_calls = 0
        self.audio_calls = 0
        self.frame_calls = 0
        self.last_interval = None

    def probe(self, source):
        self.probe_calls += 1
        return {
            "format": {"duration": str(self.duration)},
            "streams": [
                {"codec_type": "video", "width": 1280, "height": 720},
                {"codec_type": "audio", "sample_rate": "44100"},
            ],
        }

    def extract_audio(self, source, destination):
        self.audio_calls += 1
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"fake 16 kHz mono audio")
        return destination

    def extract_frames(self, source, output_dir, interval_seconds=5.0):
        self.frame_calls += 1
        self.last_interval = interval_seconds
        output_dir.mkdir(parents=True, exist_ok=True)
        frames = []
        for index in range(2):
            frame = output_dir / f"frame_{index + 1:06d}.jpg"
            frame.write_bytes(f"fake frame {index}".encode())
            frames.append(frame)
        return frames


class FakeASR:
    name = "fake-asr"
    version = "1"

    def __init__(self, *, fail_once=False):
        self.calls = 0
        self.fail_once = fail_once

    def transcribe(self, audio_path):
        self.calls += 1
        if self.fail_once and self.calls == 1:
            raise RuntimeError("temporary ASR service error")
        return [
            TranscriptSegment(0, 1200, "Open the settings menu."),
            TranscriptSegment(1200, 2500, "Choose the account tab."),
        ]


class FakeOCR:
    name = "fake-ocr"
    version = "1"

    def recognize(self, image_path, timestamp_ms):
        return [
            OCRSegment(
                timestamp_ms=timestamp_ms,
                text=f"Screen label at {timestamp_ms}ms",
                bounding_box=[0.1, 0.2, 0.8, 0.9],
            )
        ]


def _registered_video(tmp_path):
    jobs = DownloadJobRepository(tmp_path / "jobs.sqlite3")
    job = jobs.create(
        candidate_id="candidate-1",
        source_url="https://example.com/tutorial.mp4",
        engine="yt-dlp",
        destination=str(tmp_path / "downloads"),
    )
    source = tmp_path / "downloads" / "tutorial.mp4"
    source.parent.mkdir(parents=True, exist_ok=True)
    payload = b"fake tutorial video bytes"
    source.write_bytes(payload)
    assets = MediaAssetRepository(
        tmp_path / "assets.sqlite3",
        tmp_path / "manifests",
    )
    digest = hashlib.sha256(payload).hexdigest()
    asset_id = assets.register_download(job, source, digest, len(payload))
    return assets, asset_id, source


def test_pipeline_extracts_audio_frames_and_persists_timestamped_asr_ocr(tmp_path):
    assets, asset_id, _source = _registered_video(tmp_path)
    repository = MediaAnalysisRepository(tmp_path / "analysis.sqlite3")
    ffmpeg = FakeFFmpeg(duration=600.0)
    asr = FakeASR()
    ocr = FakeOCR()
    pipeline = MediaAnalysisPipeline(
        assets,
        repository,
        tmp_path / "derived",
        ffmpeg=ffmpeg,
        asr_adapter=asr,
        ocr_adapter=ocr,
        frame_interval_seconds=5.0,
        max_frames=100,
    )

    result = pipeline.analyze(asset_id)
    stored = repository.get(result.run_id)

    assert result.status == AnalysisStatus.COMPLETED
    assert result.duration_seconds == 600.0
    assert result.audio_path is not None
    assert result.audio_path.is_file()
    assert len(result.frame_paths) == 2
    assert len(result.transcripts) == 2
    assert result.transcripts[0].start_ms == 0
    assert result.transcripts[1].text == "Choose the account tab."
    assert len(result.ocr_segments) == 2
    assert result.ocr_segments[1].timestamp_ms == 6000
    assert stored.asset_id == asset_id
    assert len(stored.artifacts) == 3
    assert ffmpeg.last_interval == 6.0


def test_identical_completed_analysis_run_is_reused(tmp_path):
    assets, asset_id, _source = _registered_video(tmp_path)
    repository = MediaAnalysisRepository(tmp_path / "analysis.sqlite3")
    ffmpeg = FakeFFmpeg()
    pipeline = MediaAnalysisPipeline(
        assets,
        repository,
        tmp_path / "derived",
        ffmpeg=ffmpeg,
        asr_adapter=FakeASR(),
        ocr_adapter=FakeOCR(),
    )

    first = pipeline.analyze(asset_id)
    second = pipeline.analyze(asset_id)

    assert second.run_id == first.run_id
    assert second.attempts == 1
    assert ffmpeg.probe_calls == 1
    assert ffmpeg.audio_calls == 1
    assert ffmpeg.frame_calls == 1


def test_missing_asr_and_ocr_adapters_produce_explicit_partial_result(tmp_path):
    assets, asset_id, _source = _registered_video(tmp_path)
    repository = MediaAnalysisRepository(tmp_path / "analysis.sqlite3")
    pipeline = MediaAnalysisPipeline(
        assets,
        repository,
        tmp_path / "derived",
        ffmpeg=FakeFFmpeg(),
    )

    result = pipeline.analyze(asset_id)

    assert result.status == AnalysisStatus.PARTIAL
    assert "ASR adapter not configured" in result.warnings
    assert "OCR adapter not configured" in result.warnings
    assert result.audio_path is not None
    assert len(result.frame_paths) == 2
    assert result.transcripts == ()
    assert result.ocr_segments == ()


def test_failed_asr_run_is_persisted_and_resumes_with_attempt_count(tmp_path):
    assets, asset_id, _source = _registered_video(tmp_path)
    repository = MediaAnalysisRepository(tmp_path / "analysis.sqlite3")
    asr = FakeASR(fail_once=True)
    pipeline = MediaAnalysisPipeline(
        assets,
        repository,
        tmp_path / "derived",
        ffmpeg=FakeFFmpeg(),
        asr_adapter=asr,
        ocr_adapter=FakeOCR(),
    )

    with pytest.raises(RuntimeError, match="temporary ASR service error"):
        pipeline.analyze(asset_id)

    failed = repository.list_for_asset(asset_id)[0]
    assert failed.status == AnalysisStatus.FAILED
    assert failed.attempts == 1

    recovered = pipeline.analyze(asset_id)

    assert recovered.run_id == failed.run_id
    assert recovered.status == AnalysisStatus.COMPLETED
    assert recovered.attempts == 2


def test_pipeline_rejects_asset_modified_after_registration(tmp_path):
    assets, asset_id, source = _registered_video(tmp_path)
    repository = MediaAnalysisRepository(tmp_path / "analysis.sqlite3")
    source.write_bytes(b"x" * source.stat().st_size)
    pipeline = MediaAnalysisPipeline(
        assets,
        repository,
        tmp_path / "derived",
        ffmpeg=FakeFFmpeg(),
        asr_adapter=FakeASR(),
        ocr_adapter=FakeOCR(),
    )

    with pytest.raises(ValueError, match="SHA-256 changed"):
        pipeline.analyze(asset_id)


@pytest.mark.parametrize(
    "segment",
    [
        TranscriptSegment(0, 0, "empty duration"),
        TranscriptSegment(-1, 10, "negative"),
        TranscriptSegment(0, 10, "   "),
        TranscriptSegment(0.5, 10, "fractional timestamp"),
    ],
)
def test_pipeline_rejects_invalid_asr_segments(tmp_path, segment):
    assets, asset_id, _source = _registered_video(tmp_path)
    repository = MediaAnalysisRepository(tmp_path / "analysis.sqlite3")

    class InvalidASR:
        name = "invalid-asr"
        version = "1"

        def transcribe(self, audio_path):
            return [segment]

    pipeline = MediaAnalysisPipeline(
        assets,
        repository,
        tmp_path / "derived",
        ffmpeg=FakeFFmpeg(),
        asr_adapter=InvalidASR(),
        ocr_adapter=FakeOCR(),
    )

    with pytest.raises(ValueError, match="invalid transcript segment"):
        pipeline.analyze(asset_id)
