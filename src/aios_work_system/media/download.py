"""Download adapters that delegate media protocols to yt-dlp and aria2."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import unquote, urlparse

from aios_work_system.media.ffmpeg import FFmpegProcessor
from aios_work_system.media.source import sha256_file


class DownloadError(RuntimeError):
    """Raised when a download engine fails or its output cannot be verified."""


@dataclass(frozen=True)
class DownloadRequest:
    url: str
    destination_dir: Path
    filename: str | None = None
    concurrent_fragments: int = 4
    max_connections: int = 8

    def __post_init__(self) -> None:
        if not self.url.startswith(("http://", "https://")):
            raise ValueError("download URL must use HTTP or HTTPS")
        if self.concurrent_fragments < 1:
            raise ValueError("concurrent_fragments must be at least 1")
        if self.max_connections < 1:
            raise ValueError("max_connections must be at least 1")
        if self.filename and Path(self.filename).name != self.filename:
            raise ValueError("filename must not contain directory components")


@dataclass(frozen=True)
class DownloadResult:
    engine: str
    path: Path
    size_bytes: int
    sha256: str
    media_info: dict[str, Any] | None = None


class CommandRunner(Protocol):
    def __call__(
        self,
        command: list[str],
        *,
        capture_output: bool,
        text: bool,
        check: bool,
        timeout: int,
    ) -> Any:
        """Run a command without invoking a shell."""


def _default_runner(
    command: list[str],
    *,
    capture_output: bool = True,
    text: bool = True,
    check: bool = False,
    timeout: int = 3600,
):
    return subprocess.run(
        command,
        capture_output=capture_output,
        text=text,
        check=check,
        timeout=timeout,
    )


class YtDlpAdapter:
    """Delegate site extraction and HLS/DASH downloads to yt-dlp."""

    name = "yt-dlp"

    def __init__(
        self,
        *,
        executable: str = "yt-dlp",
        runner: CommandRunner = _default_runner,
        timeout_seconds: int = 3600,
    ) -> None:
        self.executable = executable
        self.runner = runner
        self.timeout_seconds = timeout_seconds

    def download(self, request: DownloadRequest) -> Path:
        destination = request.destination_dir.expanduser().resolve()
        destination.mkdir(parents=True, exist_ok=True)
        output_template = request.filename or "%(title).180B [%(id)s].%(ext)s"
        command = [
            self.executable,
            "--no-progress",
            "--newline",
            "--no-playlist",
            "--paths",
            str(destination),
            "--output",
            output_template,
            "--concurrent-fragments",
            str(request.concurrent_fragments),
            "--print",
            "after_move:filepath",
            "--merge-output-format",
            "mp4",
            request.url,
        ]
        try:
            completed = self.runner(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=self.timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise DownloadError(
                "yt-dlp executable not found; install yt-dlp and add it to PATH"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise DownloadError("yt-dlp download timed out") from exc
        if completed.returncode != 0:
            detail = (completed.stderr or "").strip() or f"exit code {completed.returncode}"
            raise DownloadError(f"yt-dlp failed: {detail}")
        output_lines = [
            line.strip()
            for line in (completed.stdout or "").splitlines()
            if line.strip()
        ]
        if not output_lines:
            raise DownloadError("yt-dlp completed without reporting the final file path")
        path = Path(output_lines[-1]).expanduser()
        if not path.is_absolute():
            path = destination / path
        return path.resolve()


class Aria2Adapter:
    """Delegate ordinary HTTP(S) large-file downloads to aria2."""

    name = "aria2"

    def __init__(
        self,
        *,
        executable: str = "aria2c",
        runner: CommandRunner = _default_runner,
        timeout_seconds: int = 3600,
    ) -> None:
        self.executable = executable
        self.runner = runner
        self.timeout_seconds = timeout_seconds

    def download(self, request: DownloadRequest) -> Path:
        destination = request.destination_dir.expanduser().resolve()
        destination.mkdir(parents=True, exist_ok=True)
        filename = (
            request.filename
            or Path(unquote(urlparse(request.url).path)).name
            or "download.bin"
        )
        output = destination / filename
        command = [
            self.executable,
            "--continue=true",
            "--allow-overwrite=true",
            "--auto-file-renaming=false",
            f"--max-connection-per-server={request.max_connections}",
            f"--split={request.max_connections}",
            "--min-split-size=1M",
            f"--dir={destination}",
            f"--out={filename}",
            request.url,
        ]
        try:
            completed = self.runner(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=self.timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise DownloadError(
                "aria2c executable not found; install aria2 and add it to PATH"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise DownloadError("aria2 download timed out") from exc
        if completed.returncode != 0:
            detail = (completed.stderr or "").strip() or f"exit code {completed.returncode}"
            raise DownloadError(f"aria2 failed: {detail}")
        return output.resolve()


class DownloadVerifier:
    """Verify a downloaded file and optionally inspect its media streams."""

    def __init__(self, ffmpeg: FFmpegProcessor | None = None) -> None:
        self.ffmpeg = ffmpeg

    def verify(self, engine: str, path: str | Path) -> DownloadResult:
        file_path = Path(path).expanduser().resolve(strict=True)
        if not file_path.is_file():
            raise DownloadError(f"download output is not a file: {file_path}")
        size = file_path.stat().st_size
        if size <= 0:
            raise DownloadError(f"download output is empty: {file_path}")
        digest = sha256_file(file_path)
        media_info = self.ffmpeg.probe(file_path) if self.ffmpeg else None
        if media_info is not None and not media_info.get("streams"):
            raise DownloadError("ffprobe found no media streams in downloaded file")
        return DownloadResult(
            engine=engine,
            path=file_path,
            size_bytes=size,
            sha256=digest,
            media_info=media_info,
        )


class DownloadService:
    """Route by resource type, execute an existing engine, then verify output."""

    def __init__(
        self,
        *,
        yt_dlp: YtDlpAdapter | None = None,
        aria2: Aria2Adapter | None = None,
        verifier: DownloadVerifier | None = None,
    ) -> None:
        self.yt_dlp = yt_dlp or YtDlpAdapter()
        self.aria2 = aria2 or Aria2Adapter()
        self.verifier = verifier or DownloadVerifier()

    def download_video_page(self, request: DownloadRequest) -> DownloadResult:
        path = self.yt_dlp.download(request)
        return self.verifier.verify(self.yt_dlp.name, path)

    def download_http_file(self, request: DownloadRequest) -> DownloadResult:
        path = self.aria2.download(request)
        return self.verifier.verify(self.aria2.name, path)
