"""Platform search adapters and lazy yt-dlp download integration."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, Protocol

from aios_work_system.acquisition.models import VideoCandidate


class AcquisitionDependencyError(RuntimeError):
    """Raised when an optional acquisition dependency is missing."""


class AcquisitionPlatformError(RuntimeError):
    """Raised when platform search or download fails."""


class PlatformAdapter(Protocol):
    platform: str

    def search(self, query: str, max_results: int = 20) -> list[VideoCandidate]:
        """Search the platform and return normalized metadata."""

    def download(self, candidate: VideoCandidate, output_dir: str | Path) -> Path:
        """Download one selected video and return its final local path."""


class YtDlpDownloader:
    """Common yt-dlp downloader; import is deferred until a download is requested."""

    def __init__(self, ydl_factory: Any | None = None) -> None:
        self.ydl_factory = ydl_factory

    def _factory(self) -> Any:
        if self.ydl_factory is not None:
            return self.ydl_factory
        try:
            module = importlib.import_module("yt_dlp")
        except ImportError as exc:
            raise AcquisitionDependencyError(
                "yt-dlp is required for video downloads. Install it with: "
                'python -m pip install -e ".[acquisition]"'
            ) from exc
        return module.YoutubeDL

    def download(self, video_url: str, video_id: str, output_dir: str | Path) -> Path:
        destination = Path(output_dir).expanduser().resolve()
        destination.mkdir(parents=True, exist_ok=True)
        options = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "format": (
                "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720][ext=mp4]/b[height<=720]"
            ),
            "merge_output_format": "mp4",
            "outtmpl": str(destination / "%(id)s.%(ext)s"),
            "overwrites": False,
        }
        try:
            with self._factory()(options) as ydl:
                info = ydl.extract_info(video_url, download=True)
                returned_paths = [
                    info.get("filepath"),
                    info.get("_filename"),
                    (info.get("requested_downloads") or [{}])[0].get("filepath"),
                ]
            for raw_path in returned_paths:
                if raw_path and Path(raw_path).is_file():
                    return Path(raw_path).resolve()
            matches = sorted(path for path in destination.glob(f"{video_id}.*") if path.is_file())
            mp4_matches = [path for path in matches if path.suffix.casefold() == ".mp4"]
            if mp4_matches:
                return mp4_matches[0].resolve()
            if matches:
                return matches[0].resolve()
            raise AcquisitionPlatformError(
                f"yt-dlp finished but no output file was found for video {video_id}"
            )
        except (AcquisitionDependencyError, AcquisitionPlatformError):
            raise
        except Exception as exc:
            raise AcquisitionPlatformError(f"yt-dlp download failed: {exc}") from exc


class YouTubePlatformAdapter:
    platform = "youtube"

    def __init__(
        self,
        ydl_factory: Any | None = None,
        downloader: YtDlpDownloader | None = None,
    ) -> None:
        self.ydl_factory = ydl_factory
        self.downloader = downloader or YtDlpDownloader(ydl_factory=ydl_factory)

    def _factory(self) -> Any:
        if self.ydl_factory is not None:
            return self.ydl_factory
        try:
            module = importlib.import_module("yt_dlp")
        except ImportError as exc:
            raise AcquisitionDependencyError(
                "yt-dlp is required for YouTube search. Install it with: "
                'python -m pip install -e ".[acquisition]"'
            ) from exc
        return module.YoutubeDL

    def search(self, query: str, max_results: int = 20) -> list[VideoCandidate]:
        if not query.strip():
            raise ValueError("Search query must not be empty")
        if max_results < 1:
            raise ValueError("max_results must be at least 1")
        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": True,
        }
        try:
            with self._factory()(options) as ydl:
                result = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
        except AcquisitionDependencyError:
            raise
        except Exception as exc:
            raise AcquisitionPlatformError(f"YouTube search failed: {exc}") from exc

        candidates: list[VideoCandidate] = []
        for item in (result or {}).get("entries") or []:
            if not item:
                continue
            video_id = str(item.get("id") or item.get("url") or "").strip()
            if not video_id:
                continue
            video_url = item.get("webpage_url") or item.get("original_url")
            if not video_url or not str(video_url).startswith(("http://", "https://")):
                video_url = f"https://www.youtube.com/watch?v={video_id}"
            license_info = item.get("license") or "unknown"
            candidates.append(
                VideoCandidate(
                    video_id=video_id,
                    video_url=str(video_url),
                    platform="youtube",
                    uploader=str(item.get("uploader") or item.get("channel") or "unknown"),
                    title=str(item.get("title") or "untitled"),
                    duration_seconds=(
                        float(item["duration"]) if item.get("duration") is not None else None
                    ),
                    series=(
                        item.get("playlist_title") or item.get("playlist") or item.get("series")
                    ),
                    license_info=str(license_info),
                    license_source="yt-dlp metadata" if license_info != "unknown" else "unknown",
                    license_verification=(
                        "reported_by_platform" if license_info != "unknown" else "unknown"
                    ),
                    description=item.get("description"),
                    metadata={
                        key: item.get(key)
                        for key in ("channel_id", "playlist_id", "upload_date", "view_count")
                        if item.get(key) is not None
                    },
                )
            )
        return candidates

    def download(self, candidate: VideoCandidate, output_dir: str | Path) -> Path:
        if candidate.platform.casefold() != self.platform:
            raise ValueError("YouTube adapter cannot download a non-YouTube candidate")
        return self.downloader.download(candidate.video_url, candidate.video_id, output_dir)


class BilibiliPlatformAdapter:
    """Reserved extension point; search will be added with the Bilibili API adapter."""

    platform = "bilibili"

    def __init__(self, downloader: YtDlpDownloader | None = None) -> None:
        self.downloader = downloader or YtDlpDownloader()

    def search(self, query: str, max_results: int = 20) -> list[VideoCandidate]:
        raise NotImplementedError(
            "Bilibili search is not implemented in this MVP. Add a Bilibili API-backed "
            "search adapter that returns VideoCandidate records."
        )

    def download(self, candidate: VideoCandidate, output_dir: str | Path) -> Path:
        if candidate.platform.casefold() != self.platform:
            raise ValueError("Bilibili adapter cannot download a non-Bilibili candidate")
        return self.downloader.download(candidate.video_url, candidate.video_id, output_dir)
