"""Run the real Wikimedia tutorial video through the FFmpeg media pipeline."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from aios_work_system.media import FFmpegProcessor, SegmentRecord, register_source


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    source_path = args.input.expanduser().resolve(strict=True)
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    processor = FFmpegProcessor(timeout_seconds=2400)
    metadata = processor.probe(source_path)
    streams = metadata["streams"]
    video_streams = [item for item in streams if item.get("codec_type") == "video"]
    audio_streams = [item for item in streams if item.get("codec_type") == "audio"]
    if not video_streams:
        raise SystemExit("FAIL: sample has no video stream")
    if not audio_streams:
        raise SystemExit("FAIL: sample has no audio stream")

    audio_path = processor.extract_audio(source_path, output_dir / "sample-audio.wav")
    proxy_path = processor.create_proxy(source_path, output_dir / "sample-proxy.mp4")
    frame_dir = output_dir / "frames"
    frames = processor.extract_frames(source_path, frame_dir, interval_seconds=60)

    source = register_source(
        source_path,
        "VIDEO",
        parser_name="ffmpeg-real-sample",
        parser_version="ffmpeg-system",
    )
    duration = float(metadata.get("format", {}).get("duration", 0) or 0)
    source.add_segment(
        SegmentRecord.create(
            source_id=source.source_id,
            segment_type="AUDIO_TRACK",
            locator={"start_ms": 0, "end_ms": round(duration * 1000)},
            parser_name="ffmpeg",
            parser_version="system",
            media_uri=audio_path.as_uri(),
        )
    )
    for index, frame_path in enumerate(frames):
        timestamp = index * 60
        source.add_segment(
            SegmentRecord.create(
                source_id=source.source_id,
                segment_type="FRAME",
                locator={"timestamp_ms": timestamp * 1000},
                parser_name="ffmpeg",
                parser_version="system",
                media_uri=frame_path.as_uri(),
            )
        )
    manifest_path = output_dir / "sample.manifest.json"
    source.save(manifest_path)

    ffmpeg_version = subprocess.run(
        ["ffmpeg", "-version"], capture_output=True, text=True, check=True
    ).stdout.splitlines()[0]
    report = {
        "status": "PASS",
        "test_kind": "REAL_VIDEO_FFMPEG_INTEGRATION",
        "sample": {
            "filename": source_path.name,
            "size_bytes": source.size_bytes,
            "sha256": source.sha256,
            "duration_seconds": duration,
            "source_url": "https://commons.wikimedia.org/wiki/File:LibreOffice_Writer_%E2%80%93_The_Basics.webm",
            "license": "CC BY 3.0",
            "attribution": "Free I.T. Athens",
        },
        "ffmpeg_version": ffmpeg_version,
        "streams": [
            {
                "codec_type": item.get("codec_type"),
                "codec_name": item.get("codec_name"),
                "width": item.get("width"),
                "height": item.get("height"),
                "sample_rate": item.get("sample_rate"),
            }
            for item in streams
        ],
        "outputs": {
            "audio": {"path": str(audio_path), "size_bytes": audio_path.stat().st_size},
            "proxy": {"path": str(proxy_path), "size_bytes": proxy_path.stat().st_size},
            "frames": len(frames),
            "manifest": str(manifest_path),
            "manifest_segments": len(source.segments),
        },
    }
    (output_dir / "real-media-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
