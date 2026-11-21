"""Platform search adapters and lazy yt-dlp download integration."""

from __future__ import annotations

import importlib
import json
import re
from html import unescape
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



def _strip_html_tags(value: str) -> str:
    """Remove Bilibili's HTML keyword-highlighting tags from a search title."""
    return unescape(re.sub(r"<[^>]*>", "", value)).strip()


def _duration_to_seconds(value: object) -> float | None:
    """Parse Bilibili's MM:SS or HH:MM:SS duration text without guessing."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if not isinstance(value, str):
        return None
    parts = value.strip().split(":")
    if not 1 <= len(parts) <= 3 or any(not part.isdigit() for part in parts):
        return None
    numbers = [int(part) for part in parts]
    if len(numbers) == 1:
        return float(numbers[0])
    if len(numbers) == 2:
        return float(numbers[0] * 60 + numbers[1])
    return float(numbers[0] * 3600 + numbers[1] * 60 + numbers[2])


def _series_title(item: dict[str, Any]) -> str | None:
    for key in ("season_title", "playlist_title", "ugc_season", "series"):
        value = item.get(key)
        if isinstance(value, dict):
            value = value.get("title") or value.get("name")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


class BilibiliPlatformAdapter:
    """Search public Bilibili video results without requiring a logged-in account.

    The public search endpoint may apply rate limits or anti-bot controls. Those
    responses are surfaced as AcquisitionPlatformError; this adapter does not
    manufacture cookies, sign in, or retry around access controls.
    """

    platform = "bilibili"
    API_URL = "https://api.bilibili.com/x/web-interface/search/type"
    PAGE_SIZE = 20
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )

    def __init__(
        self,
        downloader: YtDlpDownloader | None = None,
        *,
        http_open: Any | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.downloader = downloader or YtDlpDownloader()
        self.http_open = http_open
        self.timeout_seconds = timeout_seconds

    def _fetch_search_page(self, query: str, page: int) -> list[dict[str, Any]]:
        from urllib.error import HTTPError, URLError
        from urllib.parse import urlencode
        from urllib.request import Request, urlopen

        query_string = urlencode(
            {
                "search_type": "video",
                "keyword": query,
                "page": page,
                "order": "totalrank",
            }
        )
        request = Request(
            f"{self.API_URL}?{query_string}",
            headers={
                "User-Agent": self.USER_AGENT,
                "Referer": "https://www.bilibili.com/",
                "Accept": "application/json, text/plain, */*",
            },
        )
        open_request = self.http_open or urlopen
        try:
            with open_request(request, timeout=self.timeout_seconds) as response:
                status = getattr(response, "status", 200)
                if status != 200:
                    if status == 429:
                        detail = "rate limited"
                    elif status in {403, 412}:
                        detail = "blocked by Bilibili anti-bot/risk control"
                    else:
                        detail = f"HTTP {status}"
                    raise AcquisitionPlatformError(f"Bilibili search {detail} (HTTP {status})")
                raw_body = response.read()
        except HTTPError as exc:
            if exc.code == 429:
                detail = "rate limited"
            elif exc.code in {403, 412}:
                detail = "blocked by Bilibili anti-bot/risk control"
            else:
                detail = f"HTTP {exc.code}"
            raise AcquisitionPlatformError(f"Bilibili search {detail}") from exc
        except URLError as exc:
            raise AcquisitionPlatformError(f"Bilibili search request failed: {exc.reason}") from exc
        except OSError as exc:
            raise AcquisitionPlatformError(f"Bilibili search request failed: {exc}") from exc

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (AttributeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AcquisitionPlatformError("Bilibili search returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise AcquisitionPlatformError("Bilibili search returned an invalid response object")

        try:
            code = int(payload.get("code", 0))
        except (TypeError, ValueError) as exc:
            raise AcquisitionPlatformError("Bilibili search returned an invalid API status code") from exc
        if code != 0:
            message = str(payload.get("message") or "no error message")
            if code in {-412, -352}:
                detail = "blocked by Bilibili anti-bot/risk control"
            elif code in {-509, -429, 429}:
                detail = "rate limited"
            else:
                detail = "API error"
            raise AcquisitionPlatformError(
                f"Bilibili search {detail} (code {code}): {message}"
            )

        data = payload.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("result"), list):
            raise AcquisitionPlatformError("Bilibili search response is missing data.result")
        return [item for item in data["result"] if isinstance(item, dict)]

    def search(self, query: str, max_results: int = 20) -> list[VideoCandidate]:
        if not query.strip():
            raise ValueError("Search query must not be empty")
        if max_results < 1:
            raise ValueError("max_results must be at least 1")

        candidates: list[VideoCandidate] = []
        page = 1
        while len(candidates) < max_results:
            items = self._fetch_search_page(query, page)
            for item in items:
                bvid = item.get("bvid")
                if not isinstance(bvid, str) or not bvid.strip():
                    continue
                raw_title = item.get("title")
                title = _strip_html_tags(raw_title) if isinstance(raw_title, str) else ""
                if not title:
                    title = "untitled"
                author = item.get("author")
                if not isinstance(author, str) or not author.strip():
                    owner = item.get("owner")
                    author = owner.get("name") if isinstance(owner, dict) else None
                uploader = author.strip() if isinstance(author, str) and author.strip() else "unknown"
                license_info = "unknown"
                candidates.append(
                    VideoCandidate(
                        video_id=bvid.strip(),
                        video_url=f"https://www.bilibili.com/video/{bvid.strip()}",
                        platform=self.platform,
                        uploader=uploader,
                        title=title,
                        duration_seconds=_duration_to_seconds(item.get("duration")),
                        series=_series_title(item),
                        license_info=license_info,
                        license_source="unknown",
                        license_verification="unknown",
                        description=(
                            item.get("description")
                            if isinstance(item.get("description"), str)
                            else None
                        ),
                        metadata={
                            key: item[key]
                            for key in ("aid", "mid", "typename", "pubdate", "typeid")
                            if item.get(key) is not None
                        },
                    )
                )
                if len(candidates) >= max_results:
                    break
            if len(items) < self.PAGE_SIZE or len(candidates) >= max_results:
                break
            page += 1
        return candidates

    def download(self, candidate: VideoCandidate, output_dir: str | Path) -> Path:
        if candidate.platform.casefold() != self.platform:
            raise ValueError("Bilibili adapter cannot download a non-Bilibili candidate")
        return self.downloader.download(candidate.video_url, candidate.video_id, output_dir)
