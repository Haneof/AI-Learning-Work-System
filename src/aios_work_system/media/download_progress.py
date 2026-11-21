"""Normalized progress events emitted by media download engines."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any


YTDLP_PROGRESS_PREFIX = "__AIOS_PROGRESS__"


@dataclass(frozen=True, slots=True)
class DownloadProgress:
    """Engine-independent download progress measured in bytes and seconds."""

    bytes_downloaded: int
    total_bytes: int | None = None
    speed_bytes_per_second: float | None = None
    eta_seconds: float | None = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.bytes_downloaded, bool)
            or not isinstance(self.bytes_downloaded, int)
            or self.bytes_downloaded < 0
        ):
            raise ValueError("bytes_downloaded must be a non-negative integer")
        if self.total_bytes is not None and (
            isinstance(self.total_bytes, bool)
            or not isinstance(self.total_bytes, int)
            or self.total_bytes < 0
        ):
            raise ValueError("total_bytes must be a non-negative integer")
        for name, value in (
            ("speed_bytes_per_second", self.speed_bytes_per_second),
            ("eta_seconds", self.eta_seconds),
        ):
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
            ):
                raise ValueError(f"{name} must be finite and non-negative")


def _optional_int(value: Any) -> int | None:
    if value in (None, "", "NA", "N/A", "None") or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(parsed) or not parsed.is_integer() or parsed < 0:
        return None
    return int(parsed)


def _optional_float(value: Any) -> float | None:
    if value in (None, "", "NA", "N/A", "None") or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if math.isfinite(parsed) and parsed >= 0 else None


def parse_ytdlp_progress_line(line: str) -> DownloadProgress | None:
    """Parse a yt-dlp JSON progress-template line; ignore unrelated output."""
    if not line.startswith(YTDLP_PROGRESS_PREFIX):
        return None
    try:
        payload = json.loads(line[len(YTDLP_PROGRESS_PREFIX) :])
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None

    downloaded = _optional_int(payload.get("downloaded_bytes"))
    if downloaded is None:
        return None
    total = _optional_int(payload.get("total_bytes"))
    if total is None:
        total = _optional_int(payload.get("total_bytes_estimate"))
    speed = _optional_float(payload.get("speed"))
    eta = _optional_float(payload.get("eta"))
    return DownloadProgress(
        bytes_downloaded=downloaded,
        total_bytes=total,
        speed_bytes_per_second=speed,
        eta_seconds=eta,
    )


def parse_aria2_status(status: dict[str, Any]) -> DownloadProgress | None:
    """Convert aria2.tellStatus fields (JSON-RPC strings) into a progress event."""
    downloaded = _optional_int(status.get("completedLength"))
    if downloaded is None:
        return None
    total = _optional_int(status.get("totalLength"))
    if total == 0:
        total = None
    speed = _optional_float(status.get("downloadSpeed"))
    eta = None
    if total is not None and speed is not None and speed > 0:
        eta = max(0.0, (total - downloaded) / speed)
    return DownloadProgress(
        bytes_downloaded=downloaded,
        total_bytes=total,
        speed_bytes_per_second=speed,
        eta_seconds=eta,
    )
