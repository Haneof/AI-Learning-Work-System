"""Download one candidate tutorial video file and its timed subtitles with yt-dlp."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


CANDIDATES = [
    ("OyZ3qj44snA", "Windows 11 create a new folder"),
    ("tdYUsICTIdk", "Windows 11 change desktop wallpaper"),
    ("lVs37MPl9ik", "Excel pivot table"),
]


def download_first_available(output_dir: Path) -> dict[str, Any]:
    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:
        raise RuntimeError("Install yt-dlp with the video optional dependencies.") from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    attempts: list[dict[str, Any]] = []
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
                info = ydl.extract_info(url, download=False)
                if not isinstance(info, dict):
                    raise RuntimeError("yt-dlp returned no video metadata")
                duration = float(info.get("duration") or 0)
                if duration <= 0:
                    raise RuntimeError("video duration is missing")
                if duration > 20 * 60:
                    raise RuntimeError(f"candidate is longer than 20 minutes ({duration:.1f}s)")
                ydl.download([url])
                info = ydl.extract_info(url, download=False)
                requested = info.get("requested_downloads") or []
                video_path = requested[0].get("filepath") if requested else None
                if not video_path:
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
                caption = next((item for item in caption_candidates if item.stat().st_size), None)
                metadata = {
                    "video_id": video_id,
                    "title": info.get("title") or label,
                    "url": url,
                    "extractor": info.get("extractor_key") or "youtube",
                    "duration_seconds": duration,
                    "video_path": str(Path(video_path).resolve()),
                    "captions_path": str(caption.resolve()) if caption else None,
                    "caption_candidates": [str(item) for item in caption_candidates],
                    "subtitle_source": "youtube_subtitle" if caption else "asr_fallback_required",
                }
                (output_dir / "source-manifest.json").write_text(
                    json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                print(json.dumps({"selected": metadata, "attempts": attempts}, ensure_ascii=False))
                return metadata
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
    raise RuntimeError(f"All tutorial downloads failed: {json.dumps(attempts, ensure_ascii=False)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = download_first_available(args.output_dir)
    print(f"Downloaded video file: {result['video_path']}")
    print(f"Timed subtitle file: {result['captions_path'] or 'none; ASR fallback will run'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
