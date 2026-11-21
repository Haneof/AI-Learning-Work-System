"""Optional faster-whisper implementation of the stable ASR adapter contract."""

from __future__ import annotations

import math
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Callable

from aios_work_system.media.adapters import TranscriptSegment


def _package_version() -> str:
    try:
        return version("faster-whisper")
    except PackageNotFoundError:
        return "not-installed"


class FasterWhisperASRAdapter:
    """Lazy-load faster-whisper and normalize segment offsets into milliseconds.

    CPU/int8 is the conservative default. GPU users can explicitly select
    device="cuda" and an appropriate compute_type after configuring CUDA.
    """

    name = "faster-whisper"

    def __init__(
        self,
        *,
        model_size: str = "small",
        device: str = "cpu",
        compute_type: str = "int8",
        language: str | None = None,
        beam_size: int = 5,
        vad_filter: bool = True,
        cpu_threads: int = 4,
        num_workers: int = 1,
        download_root: str | Path | None = None,
        model_factory: Callable[..., Any] | None = None,
        package_version: str | None = None,
    ) -> None:
        if not model_size.strip():
            raise ValueError("model_size must not be empty")
        if not device.strip():
            raise ValueError("device must not be empty")
        if not compute_type.strip():
            raise ValueError("compute_type must not be empty")
        if not isinstance(beam_size, int) or isinstance(beam_size, bool) or beam_size < 1:
            raise ValueError("beam_size must be a positive integer")
        if not isinstance(cpu_threads, int) or isinstance(cpu_threads, bool) or cpu_threads < 1:
            raise ValueError("cpu_threads must be a positive integer")
        if not isinstance(num_workers, int) or isinstance(num_workers, bool) or num_workers < 1:
            raise ValueError("num_workers must be a positive integer")
        if language is not None and not language.strip():
            raise ValueError("language must be None or a non-empty language code")

        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.beam_size = beam_size
        self.vad_filter = vad_filter
        self.cpu_threads = cpu_threads
        self.num_workers = num_workers
        self.download_root = (
            Path(download_root).expanduser().resolve()
            if download_root is not None
            else None
        )
        self._model_factory = model_factory
        self._package_version = package_version or _package_version()
        self._model: Any | None = None

    @property
    def version(self) -> str:
        return self._package_version

    @property
    def config(self) -> dict[str, Any]:
        return {
            "model_size": self.model_size,
            "device": self.device,
            "compute_type": self.compute_type,
            "language": self.language,
            "beam_size": self.beam_size,
            "vad_filter": self.vad_filter,
            "cpu_threads": self.cpu_threads,
            "num_workers": self.num_workers,
            "download_root": (
                str(self.download_root) if self.download_root is not None else None
            ),
        }

    def _get_model(self) -> Any:
        if self._model is not None:
            return self._model
        factory = self._model_factory
        if factory is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise RuntimeError(
                    "faster-whisper is optional; install with "
                    "pip install 'aios-work-system[asr]'"
                ) from exc
            factory = WhisperModel

        kwargs: dict[str, Any] = {
            "device": self.device,
            "compute_type": self.compute_type,
            "cpu_threads": self.cpu_threads,
            "num_workers": self.num_workers,
        }
        if self.download_root is not None:
            self.download_root.mkdir(parents=True, exist_ok=True)
            kwargs["download_root"] = str(self.download_root)
        self._model = factory(self.model_size, **kwargs)
        return self._model

    def transcribe(self, audio_path: Path) -> list[TranscriptSegment]:
        source = Path(audio_path).expanduser().resolve(strict=True)
        if not source.is_file():
            raise ValueError(f"ASR input is not a file: {source}")

        model = self._get_model()
        segments, _info = model.transcribe(
            str(source),
            language=self.language,
            beam_size=self.beam_size,
            vad_filter=self.vad_filter,
            condition_on_previous_text=False,
        )
        normalized: list[TranscriptSegment] = []
        for segment in segments:
            start = float(segment.start)
            end = float(segment.end)
            text = str(segment.text).strip()
            if (
                not math.isfinite(start)
                or not math.isfinite(end)
                or start < 0
                or end <= start
            ):
                raise ValueError("faster-whisper returned invalid segment timestamps")
            if not text:
                continue
            start_ms = round(start * 1000)
            end_ms = round(end * 1000)
            if end_ms <= start_ms:
                end_ms = start_ms + 1
            normalized.append(
                TranscriptSegment(
                    start_ms=start_ms,
                    end_ms=end_ms,
                    text=text,
                )
            )
        return normalized
