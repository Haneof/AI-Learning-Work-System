"""Download a candidate tutorial video file and timed subtitles."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CANDIDATES = [
    ("OyZ3qj44snA", "Windows 11 create a new folder"),
    ("tdYUsICTIdk", "Windows 11 change desktop wallpaper"),
    ("lVs37MPl9ik", "Excel pivot table"),
]
WIKIMEDIA_VIDEO_URL = (
    "https://commons.wikimedia.org/wiki/Special:Redirect/file/"
    "Content_Translation_Screencast_%28English%29.webm"
)
WIKIMEDIA_CAPTION_URL = "https://commons.wikimedia.org/w/index.php"


def _write_url(url: str, destination: Path, referer: str | None = None) -> None:
    """Download with bounded retry/backoff for transient CDN 429/5xx responses."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; AI-Learning-Work-System/0.1; "
            "+https://github.com/Haneof/AI-Learning-Work-System)"
        )
    }
    if referer:
        headers["Referer"] = referer
    for attempt in range(4):
        request = Request(url, headers=headers)
        try:
            with urlopen(request, timeout=120) as response, destination.open("wb") as handle:
                while chunk := response.read(1024 * 1024):
                    handle.write(chunk)
            break
        except HTTPError as exc:
            if exc.code not in {429, 500, 502, 503, 504} or attempt == 3:
                raise
            delay = 20 * (2**attempt)
            print(f"Download HTTP {exc.code}; retrying in {delay}s (attempt {attempt + 2}/4)")
            time.sleep(delay)
        except URLError:
            if attempt == 3:
                raise
            delay = 10 * (2**attempt)
            print(f"Download network error; retrying in {delay}s (attempt {attempt + 2}/4)")
            time.sleep(delay)
    if not destination.is_file() or destination.stat().st_size < 1024:
        raise RuntimeError(f"downloaded file is missing or unexpectedly small: {destination}")


def _save_manifest(
    output_dir: Path,
    metadata: dict[str, Any],
    attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    metadata["download_attempts"] = attempts
    (output_dir / "source-manifest.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"selected": metadata, "attempts": attempts}, ensure_ascii=False))
    return metadata


def _download_wikimedia_fallback(
    output_dir: Path,
    attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Download a real UI tutorial with its published, timestamped English subtitles."""
    video_id = "wikimedia-wikipedia-content-translation-tool-tutorial"
    video_path = output_dir / "wikipedia-content-translation-tool-tutorial.webm"
    caption_path = output_dir / "wikipedia-content-translation-tool-tutorial.en.srt"
    video_url = (
        "https://upload.wikimedia.org/wikipedia/commons/f/f2/"
        "Wikipedia_Content_Translation_Tool_Tutorial.webm"
    )
    source_page = "https://commons.wikimedia.org/wiki/File:Wikipedia_Content_Translation_Tool_Tutorial.webm"
    caption_query = urlencode(
        {
            "title": "TimedText:Wikipedia Content Translation Tool Tutorial.webm.en.srt",
            "action": "raw",
        }
    )
    caption_url = f"https://commons.wikimedia.org/w/index.php?{caption_query}"
    try:
        _write_url(video_url, video_path, referer=source_page)
        _write_url(caption_url, caption_path, referer=source_page)
        caption_text = caption_path.read_text(encoding="utf-8-sig", errors="replace")
        if "-->" not in caption_text or not any(char.isdigit() for char in caption_text):
            raise RuntimeError("published timed-text response has no timestamped subtitle cues")
        metadata = {
            "video_id": video_id,
            "title": "Wikipedia Content Translation Tool Tutorial",
            "url": video_url,
            "extractor": "wikimedia_commons",
            "duration_seconds": 128.128,
            "video_path": str(video_path.resolve()),
            "captions_path": str(caption_path.resolve()),
            "caption_candidates": [str(caption_path.resolve())],
            "subtitle_source": "published_wikimedia_timed_text",
            "license": "CC BY-SA 4.0",
            "attribution": ", ".join(
                [
                    "Wikipedia Content Translation Tool Tutorial",
                    "AlexandraShagzhina",
                    "Wikimedia Commons",
                ]
            ),
            "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
            "source_page": source_page,
            "media_direct_url": video_url,
        }
        attempts.append(
            {
                "source": "Wikimedia Commons",
                "status": "selected",
                "reason": "The three supplied YouTube IDs were unavailable from the CI runner.",
            }
        )
        return _save_manifest(output_dir, metadata, attempts)
    except (OSError, URLError, RuntimeError) as exc:
        for partial in (video_path, caption_path):
            if partial.is_file():
                partial.unlink()
        attempts.append(
            {
                "source": "Wikimedia Commons",
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
        raise RuntimeError(
            "All supplied YouTube candidates and the Wikimedia tutorial fallback failed: "
            + json.dumps(attempts, ensure_ascii=False)
        ) from exc


def download_first_available(output_dir: Path) -> dict[str, Any]:
    """Try the three supplied videos first, then the repository's licensed fallback."""
    output_dir.mkdir(parents=True, exist_ok=True)
    attempts: list[dict[str, Any]] = []
    try:
        from yt_dlp import YoutubeDL
    except ImportError:
        YoutubeDL = None

    if YoutubeDL is not None:
        for video_id, label in CANDIDATES:
            url = f"https://www.youtube.com/watch?v={video_id}"
            options = {
                "format": "best[height<=720]/best",
                "outtmpl": str(output_dir / "%(id)s.%(ext)s"),
                "noplaylist": True,
                "quiet": False,
                "no_warnings": False,
                "retries": 3,
                "fragment_retries": 3,
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitleslangs": ["en", "en-US", "en-GB"],
                "subtitlesformat": "vtt/best",
                "skip_download": False,
                "overwrites": True,
                "restrictfilenames": True,
            }
            try:
                with YoutubeDL(options) as ydl:
                    info = ydl.extract_info(url, download=True)
                    if not isinstance(info, dict):
                        raise RuntimeError("yt-dlp returned no video metadata")
                    duration = float(info.get("duration") or 0)
                    if duration <= 0:
                        raise RuntimeError("video duration is missing")
                    if duration > 20 * 60:
                        raise RuntimeError(f"candidate is longer than 20 minutes ({duration:.1f}s)")
                    requested = info.get("requested_downloads") or []
                    video_path = requested[0].get("filepath") if requested else None
                    if not video_path:
                        video_path = ydl.prepare_filename(info)
                    if not video_path or not Path(video_path).is_file():
                        matches = sorted(output_dir.glob(f"{video_id}.*"))
                        matches = [
                            item
                            for item in matches
                            if item.suffix.lower() not in {".vtt", ".srt", ".json"}
                        ]
                        video_path = str(matches[0]) if matches else None
                    if not video_path or not Path(video_path).is_file():
                        raise RuntimeError("download completed but no video file was found")
                    caption_candidates = sorted(output_dir.glob(f"{video_id}*.vtt")) + sorted(
                        output_dir.glob(f"{video_id}*.srt")
                    )
                    caption = next(
                        (item for item in caption_candidates if item.stat().st_size),
                        None,
                    )
                    metadata = {
                        "video_id": video_id,
                        "title": info.get("title") or label,
                        "url": url,
                        "extractor": info.get("extractor_key") or "youtube",
                        "duration_seconds": duration,
                        "video_path": str(Path(video_path).resolve()),
                        "captions_path": str(caption.resolve()) if caption else None,
                        "caption_candidates": [str(item.resolve()) for item in caption_candidates],
                        "subtitle_source": (
                            "youtube_subtitle" if caption else "asr_fallback_required"
                        ),
                    }
                    return _save_manifest(output_dir, metadata, attempts)
            except Exception as exc:
                attempt = {
                    "video_id": video_id,
                    "title": label,
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                }
                attempts.append(attempt)
                print(json.dumps(attempt, ensure_ascii=False))
                for partial in output_dir.glob(f"{video_id}*"):
                    if partial.is_file():
                        partial.unlink()
    else:
        attempts.append(
            {
                "source": "yt-dlp",
                "status": "unavailable",
                "error": "yt-dlp is not installed; proceeding to the Wikimedia fallback.",
            }
        )

    return _download_wikimedia_fallback(output_dir, attempts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = download_first_available(args.output_dir)
    print(f"Downloaded video file: {result['video_path']}")
    print(f"Timed subtitle file: {result['captions_path'] or 'none; ASR fallback will run'}")
    if result.get("license"):
        print(f"Video license: {result['license']} — {result['attribution']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
