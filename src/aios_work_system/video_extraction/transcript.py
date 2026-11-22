"""Timestamped subtitle parsing and optional faster-whisper fallback."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_TIMESTAMP = re.compile(
    r"(?m)^\s*(\d{2}:\d{2}:\d{2}[,.]\d{3}|\d{2}:\d{2}[,.]\d{3})"
    r"\s+-->\s+"
    r"(\d{2}:\d{2}:\d{2}[,.]\d{3}|\d{2}:\d{2}[,.]\d{3})[^\n]*\n"
)
_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


def timestamp_to_ms(value: str) -> int:
    """Convert SRT/VTT timestamps to milliseconds."""
    normalized = value.replace(",", ".")
    parts = normalized.split(":")
    if len(parts) == 2:
        hours = 0
        minutes = int(parts[0])
        seconds = float(parts[1])
    elif len(parts) == 3:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
    else:
        raise ValueError(f"unsupported subtitle timestamp: {value}")
    return int(round((hours * 3600 + minutes * 60 + seconds) * 1000))


def parse_subtitle_file(path: str | Path) -> list[dict[str, Any]]:
    """Parse timestamped SRT or WebVTT cues, retaining source timing."""
    source = Path(path)
    content = source.read_text(encoding="utf-8-sig", errors="replace")
    matches = list(_TIMESTAMP.finditer(content))
    segments: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        end_of_cue = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        body = content[match.end() : end_of_cue]
        lines = []
        for line in body.splitlines():
            candidate = line.strip()
            if not candidate or candidate.isdigit() or candidate == "WEBVTT":
                continue
            candidate = _TAG.sub("", candidate)
            candidate = _SPACE.sub(" ", candidate).strip()
            if candidate and candidate not in lines:
                lines.append(candidate)
        text = " ".join(lines).strip()
        start_ms = timestamp_to_ms(match.group(1))
        end_ms = timestamp_to_ms(match.group(2))
        if text and end_ms >= start_ms:
            segments.append(
                {
                    "segment_id": f"subtitle-{len(segments) + 1:05d}",
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "text": text,
                    "transcript_method": "subtitle",
                    "source_file": source.name,
                    "speaker_role": "unknown",
                }
            )
    return segments


def transcribe_with_faster_whisper(
    video_path: str | Path,
    model_size: str = "tiny",
    language: str | None = None,
) -> list[dict[str, Any]]:
    """Run CPU/int8 Whisper when no usable timestamped subtitle file exists."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "No usable subtitles were found and faster-whisper is not installed."
        ) from exc

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(
        str(video_path),
        language=language,
        word_timestamps=True,
        vad_filter=True,
    )
    output = []
    for index, segment in enumerate(segments, start=1):
        text = (segment.text or "").strip()
        if not text:
            continue
        words = []
        for word in segment.words or []:
            words.append(
                {
                    "text": (word.word or "").strip(),
                    "start_ms": round(float(word.start) * 1000),
                    "end_ms": round(float(word.end) * 1000),
                }
            )
        output.append(
            {
                "segment_id": f"asr-{index:05d}",
                "start_ms": round(float(segment.start) * 1000),
                "end_ms": round(float(segment.end) * 1000),
                "text": text,
                "transcript_method": "asr",
                "speaker_role": "unknown",
                "words": words,
            }
        )
    if not output:
        raise RuntimeError("faster-whisper completed but returned no speech segments")
    return output


def load_transcript(
    video_path: str | Path,
    captions_path: str | Path | None = None,
    whisper_model: str = "tiny",
    language: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Prefer supplied/downloaded subtitles; use ASR only if no subtitle cues exist."""
    candidates: list[Path] = []
    if captions_path is not None:
        candidates.append(Path(captions_path))
    else:
        video = Path(video_path)
        candidates.extend(
            sorted(video.parent.glob(f"{video.stem}*.vtt"))
            + sorted(video.parent.glob(f"{video.stem}*.srt"))
        )

    failures: list[str] = []
    for candidate in candidates:
        if not candidate.is_file():
            failures.append(f"subtitle file not found: {candidate}")
            continue
        try:
            segments = parse_subtitle_file(candidate)
        except (OSError, UnicodeError, ValueError) as exc:
            failures.append(f"{candidate.name}: {type(exc).__name__}: {exc}")
            continue
        if segments:
            return segments, {
                "status": "completed",
                "method": "existing_subtitles",
                "source_file": str(candidate),
                "segments": len(segments),
                "fallback_attempted": False,
            }
        failures.append(f"{candidate.name}: no valid timestamped cues")

    try:
        segments = transcribe_with_faster_whisper(video_path, whisper_model, language)
        return segments, {
            "status": "completed",
            "method": "faster_whisper",
            "model": whisper_model,
            "segments": len(segments),
            "fallback_attempted": True,
            "subtitle_failures": failures,
        }
    except Exception as exc:
        return [], {
            "status": "failed",
            "method": "faster_whisper",
            "model": whisper_model,
            "segments": 0,
            "fallback_attempted": True,
            "subtitle_failures": failures,
            "error": f"{type(exc).__name__}: {exc}",
        }
