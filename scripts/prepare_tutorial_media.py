#!/usr/bin/env python3
"""Download the pinned Commons screencast and extract reviewable evidence frames."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

MEDIA_URL = (
    "https://upload.wikimedia.org/wikipedia/commons/e/ee/"
    "Content_Translation_Screencast_%28English%29.webm"
)
EXPECTED_SHA1 = "8eb92107393e1896ddb2c03f0c6cfd96bd2cb41a"
EXPECTED_SIZE = 16_599_498
DEFAULT_ANNOTATION = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "content_translation_timeline_unreviewed.json"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_pinned_media(destination: Path) -> dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        MEDIA_URL,
        headers={"User-Agent": "AI-Learning-Work-System/0.1 (tutorial benchmark media prep)"},
    )
    sha1 = hashlib.sha1()
    total = 0
    temporary = destination.with_suffix(destination.suffix + ".part")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            with temporary.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > EXPECTED_SIZE:
                        raise ValueError("Downloaded media exceeds the pinned file size")
                    sha1.update(chunk)
                    output.write(chunk)
        if total != EXPECTED_SIZE:
            raise ValueError(f"Unexpected media size: {total} != {EXPECTED_SIZE}")
        if sha1.hexdigest() != EXPECTED_SHA1:
            raise ValueError("Downloaded media SHA-1 does not match the Commons source")
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return {
        "url": MEDIA_URL,
        "bytes": total,
        "sha1": sha1.hexdigest(),
        "sha256": sha256_file(destination),
    }


def extract_frames(
    media: Path, annotation: dict[str, Any], output_dir: Path
) -> list[dict[str, Any]]:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is required to extract tutorial frames")
    duration = float(annotation["source"]["duration_seconds"])
    output_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    for step in annotation["steps"]:
        timestamp = float(step["evidence_refs"][0]["timestamp_seconds"])
        if timestamp < 0 or timestamp >= duration:
            raise ValueError(f"Timestamp out of range for {step['step_id']}: {timestamp}")
        frame_path = output_dir / f"{step['step_id']}.jpg"
        subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(media),
                "-ss",
                f"{timestamp:.3f}",
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(frame_path),
            ],
            check=True,
        )
        frames.append(
            {
                "step_id": step["step_id"],
                "timestamp_seconds": timestamp,
                "frame_path": str(frame_path),
                "sha256": sha256_file(frame_path),
                "human_review_required": True,
            }
        )
    return frames


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/tutorial-media"))
    parser.add_argument("--annotation", type=Path, default=DEFAULT_ANNOTATION)
    args = parser.parse_args()

    annotation = json.loads(args.annotation.read_text(encoding="utf-8"))
    media_path = args.output_dir / "Content_Translation_Screencast_English.webm"
    media = download_pinned_media(media_path)
    frames = extract_frames(media_path, annotation, args.output_dir / "frames")
    manifest = {
        "source_id": annotation["source_id"],
        "license": annotation["source"]["license"],
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
        "attribution": {
            "creator": annotation["source"]["author"],
            "date": annotation["source"]["date"],
            "source_url": annotation["source"]["media_url"],
        },
        "media": media,
        "frames": frames,
        "review_status": "pending_human_visual_review",
    }
    manifest_path = args.output_dir / "frame_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
