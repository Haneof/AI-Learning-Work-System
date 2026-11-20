"""Tests for yt-dlp and aria2 delegation and output verification."""

import hashlib
from types import SimpleNamespace

import pytest

from aios_work_system.media.download import (
    Aria2Adapter,
    DownloadError,
    DownloadRequest,
    DownloadService,
    DownloadVerifier,
    YtDlpAdapter,
)


def test_ytdlp_adapter_delegates_to_existing_binary_and_reports_final_path(tmp_path):
    created = tmp_path / "lesson.mp4"

    def runner(command, **kwargs):
        assert command[0] == "yt-dlp"
        assert "--concurrent-fragments" in command
        assert "--no-playlist" in command
        created.write_bytes(b"video-data")
        return SimpleNamespace(returncode=0, stdout=str(created) + "\n", stderr="")

    path = YtDlpAdapter(runner=runner).download(
        DownloadRequest(
            url="https://www.bilibili.com/video/BV1xx",
            destination_dir=tmp_path,
            concurrent_fragments=6,
        )
    )

    assert path == created.resolve()
    assert created.read_bytes() == b"video-data"


def test_aria2_adapter_uses_multiconnection_resume_and_expected_output(tmp_path):
    created = tmp_path / "archive.bin"

    def runner(command, **kwargs):
        assert command[0] == "aria2c"
        assert "--continue=true" in command
        assert "--split=12" in command
        created.write_bytes(b"large-file")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    path = Aria2Adapter(runner=runner).download(
        DownloadRequest(
            url="https://example.com/archive.bin",
            destination_dir=tmp_path,
            filename="archive.bin",
            max_connections=12,
        )
    )

    assert path == created.resolve()


def test_download_service_hashes_and_verifies_video_output(tmp_path):
    created = tmp_path / "video.mp4"
    payload = b"verified-media"

    def runner(command, **kwargs):
        created.write_bytes(payload)
        return SimpleNamespace(returncode=0, stdout=str(created), stderr="")

    result = DownloadService(
        yt_dlp=YtDlpAdapter(runner=runner),
        verifier=DownloadVerifier(),
    ).download_video_page(
        DownloadRequest(
            url="https://www.bilibili.com/video/BV1xx",
            destination_dir=tmp_path,
        )
    )

    assert result.engine == "yt-dlp"
    assert result.size_bytes == len(payload)
    assert result.sha256 == hashlib.sha256(payload).hexdigest()


def test_download_verifier_rejects_empty_file(tmp_path):
    empty = tmp_path / "empty.mp4"
    empty.touch()

    with pytest.raises(DownloadError, match="empty"):
        DownloadVerifier().verify("test", empty)


def test_download_verifier_requires_media_streams_when_ffprobe_enabled(tmp_path):
    media = tmp_path / "not-media.bin"
    media.write_bytes(b"not really media")

    class FakeFFmpeg:
        def probe(self, _path):
            return {"streams": []}

    with pytest.raises(DownloadError, match="no media streams"):
        DownloadVerifier(ffmpeg=FakeFFmpeg()).verify("test", media)


def test_download_request_rejects_unsafe_or_invalid_options(tmp_path):
    with pytest.raises(ValueError, match="HTTP"):
        DownloadRequest("file:///tmp/a", tmp_path)
    with pytest.raises(ValueError, match="directory"):
        DownloadRequest("https://example.com/a", tmp_path, filename="../escape")
    with pytest.raises(ValueError, match="at least 1"):
        DownloadRequest("https://example.com/a", tmp_path, max_connections=0)


def test_ytdlp_adapter_surfaces_missing_executable(tmp_path):
    def runner(_command, **kwargs):
        raise FileNotFoundError("missing")

    with pytest.raises(DownloadError, match="yt-dlp executable not found"):
        YtDlpAdapter(runner=runner).download(
            DownloadRequest("https://example.com/video", tmp_path)
        )


def test_aria2_adapter_surfaces_nonzero_exit(tmp_path):
    def runner(_command, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="server rejected range")

    with pytest.raises(DownloadError, match="server rejected range"):
        Aria2Adapter(runner=runner).download(
            DownloadRequest(
                "https://example.com/file.zip",
                tmp_path,
                filename="file.zip",
            )
        )
