"""FFmpeg wrappers for probing and creating derived media artifacts."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

MAX_EXTRACTED_FRAMES = 1000


class MediaProcessingError(RuntimeError):
    """Raised when a media command fails or returns invalid output."""


class NoAudioStreamError(MediaProcessingError):
    """Raised when audio extraction is requested for a video without audio."""


class FFmpegProcessor:
    def __init__(
        self,
        ffmpeg_binary: str = "ffmpeg",
        ffprobe_binary: str = "ffprobe",
        timeout_seconds: int = 1800,
    ) -> None:
        self.ffmpeg_binary = ffmpeg_binary
        self.ffprobe_binary = ffprobe_binary
        self.timeout_seconds = timeout_seconds

    def _run(self, command: list[str]) -> str:
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=self.timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise MediaProcessingError(
                f"Executable not found: {command[0]}. Install FFmpeg and add it to PATH."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise MediaProcessingError(
                f"Media command timed out after {self.timeout_seconds} seconds"
            ) from exc
        if completed.returncode != 0:
            detail = completed.stderr.strip() or f"exit code {completed.returncode}"
            raise MediaProcessingError(detail)
        return completed.stdout

    def probe(self, source: str | Path) -> dict[str, Any]:
        try:
            source_path = Path(source).expanduser().resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise MediaProcessingError(f"Could not resolve media source: {source}") from exc
        if not source_path.is_file():
            raise MediaProcessingError(f"Media source is not a file: {source_path}")
        output = self._run(
            [
                self.ffprobe_binary,
                "-v",
                "error",
                "-show_format",
                "-show_streams",
                "-of",
                "json",
                str(source_path),
            ]
        )
        try:
            payload = json.loads(output)
        except json.JSONDecodeError as exc:
            raise MediaProcessingError("ffprobe returned invalid JSON") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("streams"), list):
            raise MediaProcessingError("ffprobe output is missing the streams array")
        return payload

    def extract_audio(self, source: str | Path, destination: str | Path) -> Path:
        source_path = Path(source).resolve(strict=True)
        streams = self.probe(source_path).get("streams", [])
        if not any(stream.get("codec_type") == "audio" for stream in streams):
            raise NoAudioStreamError(f"No audio stream found: {source_path}")
        output_path = Path(destination).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path == source_path:
            raise ValueError("Output path must not overwrite the source file")
        self._run(
            [
                self.ffmpeg_binary,
                "-y",
                "-i",
                str(source_path),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                str(output_path),
            ]
        )
        return output_path

    def create_proxy(self, source: str | Path, destination: str | Path) -> Path:
        source_path = Path(source).resolve(strict=True)
        output_path = Path(destination).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path == source_path:
            raise ValueError("Output path must not overwrite the source file")
        self._run(
            [
                self.ffmpeg_binary,
                "-y",
                "-i",
                str(source_path),
                "-vf",
                "scale='min(1280,iw)':-2",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "28",
                "-an",
                str(output_path),
            ]
        )
        return output_path

    def extract_frames(
        self,
        source: str | Path,
        output_dir: str | Path,
        interval_seconds: float = 5.0,
        max_frames: int = MAX_EXTRACTED_FRAMES,
    ) -> list[Path]:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be greater than zero")
        if (
            isinstance(max_frames, bool)
            or not isinstance(max_frames, int)
            or not 1 <= max_frames <= MAX_EXTRACTED_FRAMES
        ):
            raise ValueError(f"max_frames must be between 1 and {MAX_EXTRACTED_FRAMES}")
        source_path = Path(source).resolve(strict=True)
        frame_dir = Path(output_dir).resolve()
        frame_dir.mkdir(parents=True, exist_ok=True)
        pattern = frame_dir / "frame_%06d.jpg"
        self._run(
            [
                self.ffmpeg_binary,
                "-y",
                "-i",
                str(source_path),
                "-vf",
                f"fps=1/{interval_seconds:.6g}",
                "-q:v",
                "2",
                "-frames:v",
                str(max_frames),
                str(pattern),
            ]
        )
        frames = sorted(frame_dir.glob("frame_*.jpg"))[:max_frames]
        if not frames:
            raise MediaProcessingError("FFmpeg completed but produced no frames")
        return frames
