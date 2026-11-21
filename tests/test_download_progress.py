"""Tests for normalized media download progress events."""

import pytest

from aios_work_system.media.download_progress import (
    YTDLP_PROGRESS_PREFIX,
    DownloadProgress,
    parse_aria2_status,
    parse_ytdlp_progress_line,
)


def test_ytdlp_progress_template_is_normalized_with_estimated_total():
    event = parse_ytdlp_progress_line(
        YTDLP_PROGRESS_PREFIX
        + '{"downloaded_bytes": 1024, "total_bytes": null, '
        + '"total_bytes_estimate": 4096, "speed": 512.5, "eta": 6}'
    )

    assert event == DownloadProgress(
        bytes_downloaded=1024,
        total_bytes=4096,
        speed_bytes_per_second=512.5,
        eta_seconds=6.0,
    )


def test_ytdlp_progress_ignores_unrelated_or_malformed_output():
    assert parse_ytdlp_progress_line("ordinary log line") is None
    assert parse_ytdlp_progress_line(YTDLP_PROGRESS_PREFIX + "{bad json") is None


def test_aria2_rpc_status_is_normalized_and_eta_is_derived():
    event = parse_aria2_status(
        {
            "completedLength": "2048",
            "totalLength": "8192",
            "downloadSpeed": "1024",
            "status": "active",
        }
    )

    assert event == DownloadProgress(
        bytes_downloaded=2048,
        total_bytes=8192,
        speed_bytes_per_second=1024.0,
        eta_seconds=6.0,
    )


def test_aria2_status_without_size_keeps_total_and_eta_unknown():
    event = parse_aria2_status(
        {"completedLength": "128", "totalLength": "0", "downloadSpeed": "0"}
    )

    assert event == DownloadProgress(
        bytes_downloaded=128,
        total_bytes=None,
        speed_bytes_per_second=0.0,
        eta_seconds=None,
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"bytes_downloaded": -1},
        {"bytes_downloaded": 0, "total_bytes": -1},
        {"bytes_downloaded": 0, "speed_bytes_per_second": float("nan")},
        {"bytes_downloaded": 0, "eta_seconds": float("inf")},
    ],
)
def test_download_progress_rejects_invalid_numeric_values(kwargs):
    with pytest.raises(ValueError):
        DownloadProgress(**kwargs)
