"""Stable interfaces for optional ASR and OCR engines."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class TranscriptSegment:
    start_ms: int
    end_ms: int
    text: str


@dataclass(frozen=True)
class OCRSegment:
    timestamp_ms: int
    text: str
    bounding_box: list[float] | None = None
    confidence: float | None = None


class ASRAdapter(Protocol):
    name: str
    version: str

    def transcribe(self, audio_path: Path) -> list[TranscriptSegment]:
        """Return transcript chunks with millisecond offsets."""


class OCRAdapter(Protocol):
    name: str
    version: str

    def recognize(self, image_path: Path, timestamp_ms: int) -> list[OCRSegment]:
        """Return OCR text with its source frame timestamp and optional box."""
