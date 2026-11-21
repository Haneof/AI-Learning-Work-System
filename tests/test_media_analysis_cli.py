"""CLI tests for running durable media preprocessing."""

import argparse
import hashlib
import json

from aios_work_system.cli import _run_media_analyze, build_parser
from aios_work_system.media.assets import MediaAssetRepository
from aios_work_system.media.download_jobs import DownloadJobRepository


class FakeFFmpeg:
    def __init__(
        self,
        ffmpeg_binary="fake-ffmpeg",
        ffprobe_binary="fake-ffprobe",
        timeout_seconds=1800,
    ):
        self.ffmpeg_binary = ffmpeg_binary
        self.ffprobe_binary = ffprobe_binary
        self.timeout_seconds = timeout_seconds

    def probe(self, source):
        return {
            "format": {"duration": "30"},
            "streams": [{"codec_type": "video"}, {"codec_type": "audio"}],
        }

    def extract_audio(self, source, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"fake audio")
        return destination

    def extract_frames(
        self, source, output_dir, interval_seconds=5.0, max_frames=None
    ):
        output_dir.mkdir(parents=True, exist_ok=True)
        frame = output_dir / "frame_000001.jpg"
        frame.write_bytes(b"fake frame")
        return [frame]


def test_media_analyze_cli_parses_resource_and_frame_limits():
    parser = build_parser()
    args = parser.parse_args(
        [
            "media-analyze",
            "--asset-id",
            "asset-123",
            "--frame-interval-seconds",
            "7.5",
            "--max-frames",
            "12",
            "--ffmpeg",
            "C:/tools/ffmpeg.exe",
        ]
    )

    assert args.command == "media-analyze"
    assert args.asset_id == "asset-123"
    assert args.frame_interval_seconds == 7.5
    assert args.max_frames == 12
    assert args.ffmpeg == "C:/tools/ffmpeg.exe"


def test_media_analyze_cli_returns_partial_when_asr_ocr_are_not_configured(
    tmp_path, monkeypatch, capsys
):
    from aios_work_system import media

    jobs = DownloadJobRepository(tmp_path / "jobs.sqlite3")
    job = jobs.create(
        candidate_id="candidate-cli",
        source_url="https://example.com/lesson.mp4",
        engine="yt-dlp",
        destination=str(tmp_path / "downloads"),
    )
    source = tmp_path / "downloads" / "lesson.mp4"
    source.parent.mkdir(parents=True, exist_ok=True)
    payload = b"fake source media bytes"
    source.write_bytes(payload)
    assets_db = tmp_path / "assets.sqlite3"
    manifest_dir = tmp_path / "asset_manifests"
    asset_id = MediaAssetRepository(assets_db, manifest_dir).register_download(
        job,
        source,
        hashlib.sha256(payload).hexdigest(),
        len(payload),
    )
    monkeypatch.setattr(media, "FFmpegProcessor", FakeFFmpeg)

    args = argparse.Namespace(
        asset_id=asset_id,
        assets_database=str(assets_db),
        manifest_dir=str(manifest_dir),
        analysis_database=str(tmp_path / "analysis.sqlite3"),
        derived_dir=str(tmp_path / "derived"),
        ffmpeg="fake-ffmpeg",
        ffprobe="fake-ffprobe",
        timeout_seconds=60,
        frame_interval_seconds=5.0,
        max_frames=20,
        asr_model_size=None,
        asr_device="cpu",
        asr_compute_type="int8",
        asr_language="zh",
        asr_download_root=str(tmp_path / "models"),
        enable_ocr=False,
        ocr_model_tier="small",
        ocr_device="cpu",
        ocr_min_confidence=0.0,
    )

    _run_media_analyze(args)
    result = json.loads(capsys.readouterr().out)

    assert result["asset_id"] == asset_id
    assert result["status"] == "PARTIAL"
    assert result["artifact_count"] == 2
    assert result["transcript_count"] == 0
    assert result["ocr_segment_count"] == 0
    assert "ASR adapter not configured" in result["warnings"]
    assert "OCR adapter not configured" in result["warnings"]
