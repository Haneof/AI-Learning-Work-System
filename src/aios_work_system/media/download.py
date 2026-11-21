"""Download adapters that delegate media protocols to yt-dlp and aria2."""

from __future__ import annotations

import json
import secrets
import socket
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
from typing import Any, Protocol
from urllib.error import URLError
from urllib.parse import unquote, urlparse
from urllib.request import Request as UrlRequest, urlopen

from aios_work_system.media.download_progress import (
    DownloadProgress,
    YTDLP_PROGRESS_PREFIX,
    parse_aria2_status,
    parse_ytdlp_progress_line,
)
from aios_work_system.media.ffmpeg import FFmpegProcessor
from aios_work_system.media.source import sha256_file


ProgressCallback = Callable[[DownloadProgress], None]


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


def _start_output_reader(process: Any) -> tuple[Queue[str | None], threading.Thread]:
    """Drain a child process pipe on a reader thread to avoid pipe deadlocks."""
    if process.stdout is None:
        raise DownloadError("download process did not expose stdout")
    output: Queue[str | None] = Queue()

    def read_lines() -> None:
        try:
            for raw_line in process.stdout:
                output.put(raw_line.rstrip("\r\n"))
        finally:
            output.put(None)

    reader = threading.Thread(target=read_lines, name="aios-download-output", daemon=True)
    reader.start()
    return output, reader


def _terminate_process(process: Any) -> None:
    if process.poll() is None:
        process.kill()
    process.wait()


def _reserve_loopback_port() -> int:
    """Reserve an ephemeral loopback port for a private per-job aria2 RPC server."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


class YtDlpAdapter:
    """Delegate site extraction and HLS/DASH downloads to yt-dlp."""

    name = "yt-dlp"
    _OUTPUT_PATH_PREFIX = "__AIOS_OUTPUT__"
    _PROGRESS_TEMPLATE = (
        f"download:{YTDLP_PROGRESS_PREFIX}"
        "%(progress.{downloaded_bytes,total_bytes,total_bytes_estimate,speed,eta})#j"
    )

    def __init__(
        self,
        *,
        executable: str = "yt-dlp",
        runner: CommandRunner = _default_runner,
        process_factory: Callable[..., Any] = subprocess.Popen,
        timeout_seconds: int = 3600,
    ) -> None:
        self.executable = executable
        self.runner = runner
        self.process_factory = process_factory
        self.timeout_seconds = timeout_seconds

    def _command(self, request: DownloadRequest, *, with_progress: bool) -> list[str]:
        destination = request.destination_dir.expanduser().resolve()
        output_template = request.filename or "%(title).180B [%(id)s].%(ext)s"
        command = [
            self.executable,
            "--newline",
            "--no-playlist",
            "--paths",
            str(destination),
            "--output",
            output_template,
            "--concurrent-fragments",
            str(request.concurrent_fragments),
            "--print",
            (
                f"after_move:{self._OUTPUT_PATH_PREFIX}%(filepath)s"
                if with_progress
                else "after_move:filepath"
            ),
            "--merge-output-format",
            "mp4",
        ]
        if with_progress:
            command.extend(
                [
                    "--progress",
                    "--progress-delta",
                    "0.5",
                    "--progress-template",
                    self._PROGRESS_TEMPLATE,
                ]
            )
        else:
            command.append("--no-progress")
        command.append(request.url)
        return command

    @staticmethod
    def _resolve_output_path(output_lines: list[str], destination: Path) -> Path:
        if not output_lines:
            raise DownloadError("yt-dlp completed without reporting the final file path")
        path = Path(output_lines[-1]).expanduser()
        if not path.is_absolute():
            path = destination / path
        return path.resolve()

    def download(
        self,
        request: DownloadRequest,
        *,
        progress_callback: ProgressCallback | None = None,
    ) -> Path:
        destination = request.destination_dir.expanduser().resolve()
        destination.mkdir(parents=True, exist_ok=True)
        command = self._command(request, with_progress=progress_callback is not None)

        if progress_callback is None:
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
                detail = (completed.stderr or "").strip() or (
                    f"exit code {completed.returncode}"
                )
                raise DownloadError(f"yt-dlp failed: {detail}")
            output_lines = [
                line.strip()
                for line in (completed.stdout or "").splitlines()
                if line.strip()
            ]
            return self._resolve_output_path(output_lines, destination)

        try:
            process = self.process_factory(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except FileNotFoundError as exc:
            raise DownloadError(
                "yt-dlp executable not found; install yt-dlp and add it to PATH"
            ) from exc

        output_queue, reader = _start_output_reader(process)
        output_lines: list[str] = []
        reported_paths: list[str] = []
        deadline = time.monotonic() + self.timeout_seconds
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, self.timeout_seconds)
                try:
                    line = output_queue.get(timeout=min(0.1, remaining))
                except Empty:
                    continue
                if line is None:
                    break
                if line.startswith(self._OUTPUT_PATH_PREFIX):
                    reported_paths.append(
                        line[len(self._OUTPUT_PATH_PREFIX) :].strip()
                    )
                    continue
                progress = parse_ytdlp_progress_line(line)
                if progress is not None:
                    progress_callback(progress)
                elif line.strip():
                    output_lines.append(line.strip())
            return_code = process.wait(
                timeout=max(0.1, deadline - time.monotonic())
            )
        except subprocess.TimeoutExpired as exc:
            _terminate_process(process)
            raise DownloadError("yt-dlp download timed out") from exc
        except BaseException:
            _terminate_process(process)
            raise
        finally:
            reader.join(timeout=1)

        if return_code != 0:
            detail = "\n".join(output_lines[-20:]).strip() or f"exit code {return_code}"
            raise DownloadError(f"yt-dlp failed: {detail}")
        return self._resolve_output_path(reported_paths, destination)


class Aria2Adapter:
    """Delegate ordinary HTTP(S) large-file downloads to aria2."""

    name = "aria2"

    def __init__(
        self,
        *,
        executable: str = "aria2c",
        runner: CommandRunner = _default_runner,
        process_factory: Callable[..., Any] = subprocess.Popen,
        rpc_opener: Callable[..., Any] = urlopen,
        timeout_seconds: int = 3600,
        progress_poll_interval: float = 0.5,
    ) -> None:
        if progress_poll_interval <= 0:
            raise ValueError("progress_poll_interval must be greater than zero")
        self.executable = executable
        self.runner = runner
        self.process_factory = process_factory
        self.rpc_opener = rpc_opener
        self.timeout_seconds = timeout_seconds
        self.progress_poll_interval = progress_poll_interval

    @staticmethod
    def _rpc_active(
        port: int,
        secret: str,
        opener: Callable[..., Any],
    ) -> list[dict[str, Any]]:
        body = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": "aios-progress",
                "method": "aria2.tellActive",
                "params": [
                    f"token:{secret}",
                    [
                        "gid",
                        "status",
                        "completedLength",
                        "totalLength",
                        "downloadSpeed",
                    ],
                ],
            }
        ).encode("utf-8")
        request = UrlRequest(
            f"http://127.0.0.1:{port}/jsonrpc",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with opener(request, timeout=1.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
        rows = payload.get("result", [])
        return rows if isinstance(rows, list) else []

    def _command(
        self,
        request: DownloadRequest,
        *,
        rpc_port: int | None = None,
        rpc_secret: str | None = None,
    ) -> tuple[list[str], Path]:
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
        ]
        if rpc_port is not None and rpc_secret is not None:
            command.extend(
                [
                    "--enable-rpc=true",
                    "--rpc-listen-all=false",
                    f"--rpc-listen-port={rpc_port}",
                    f"--rpc-secret={rpc_secret}",
                    "--console-readout=false",
                    "--summary-interval=0",
                ]
            )
        command.append(request.url)
        return command, output.resolve()

    def download(
        self,
        request: DownloadRequest,
        *,
        progress_callback: ProgressCallback | None = None,
    ) -> Path:
        if progress_callback is None:
            command, output = self._command(request)
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
                detail = (completed.stderr or "").strip() or (
                    f"exit code {completed.returncode}"
                )
                raise DownloadError(f"aria2 failed: {detail}")
            return output

        port = _reserve_loopback_port()
        secret = secrets.token_urlsafe(32)
        command, output = self._command(
            request, rpc_port=port, rpc_secret=secret
        )
        try:
            process = self.process_factory(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except FileNotFoundError as exc:
            raise DownloadError(
                "aria2c executable not found; install aria2 and add it to PATH"
            ) from exc

        output_queue, reader = _start_output_reader(process)
        output_lines: list[str] = []
        deadline = time.monotonic() + self.timeout_seconds
        next_poll = 0.0
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, self.timeout_seconds)
                try:
                    line = output_queue.get(
                        timeout=min(self.progress_poll_interval, remaining)
                    )
                except Empty:
                    line = ""
                if line is None:
                    break
                if line:
                    output_lines.append(line)
                now = time.monotonic()
                if now >= next_poll and process.poll() is None:
                    try:
                        statuses = self._rpc_active(port, secret, self.rpc_opener)
                    except (URLError, OSError, TimeoutError, ValueError):
                        statuses = []
                    for status in statuses:
                        progress = parse_aria2_status(status)
                        if progress is not None:
                            progress_callback(progress)
                    next_poll = now + self.progress_poll_interval
            return_code = process.wait(
                timeout=max(0.1, deadline - time.monotonic())
            )
        except subprocess.TimeoutExpired as exc:
            _terminate_process(process)
            raise DownloadError("aria2 download timed out") from exc
        except BaseException:
            _terminate_process(process)
            raise
        finally:
            reader.join(timeout=1)

        if return_code != 0:
            detail = "\n".join(output_lines[-20:]).strip() or f"exit code {return_code}"
            raise DownloadError(f"aria2 failed: {detail}")
        return output


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
