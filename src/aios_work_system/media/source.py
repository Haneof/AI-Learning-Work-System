"""Source registration and traceable segment manifest records."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class SegmentRecord:
    segment_id: str
    source_id: str
    segment_type: str
    locator: dict[str, Any]
    parser_name: str
    parser_version: str
    text_content: str | None = None
    media_uri: str | None = None
    content_hash: str | None = None

    @classmethod
    def create(
        cls,
        source_id: str,
        segment_type: str,
        locator: dict[str, Any],
        parser_name: str,
        parser_version: str,
        text_content: str | None = None,
        media_uri: str | None = None,
    ) -> SegmentRecord:
        content_hash = (
            hashlib.sha256(text_content.encode("utf-8")).hexdigest()
            if text_content is not None
            else None
        )
        return cls(
            segment_id=str(uuid.uuid4()),
            source_id=source_id,
            segment_type=segment_type,
            locator=locator,
            parser_name=parser_name,
            parser_version=parser_version,
            text_content=text_content,
            media_uri=media_uri,
            content_hash=content_hash,
        )


@dataclass
class SourceManifest:
    source_id: str
    source_type: str
    original_name: str
    storage_uri: str
    sha256: str
    mime_type: str
    size_bytes: int
    parser_name: str
    parser_version: str
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    segments: list[SegmentRecord] = field(default_factory=list)

    def add_segment(self, segment: SegmentRecord) -> None:
        if segment.source_id != self.source_id:
            raise ValueError("Segment source_id does not match manifest source_id")
        self.segments.append(segment)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def save(self, path: str | Path) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + ".tmp")
        temporary.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(destination)


def register_source(
    path: str | Path,
    source_type: str,
    parser_name: str = "aios-media",
    parser_version: str = "0.1.0",
) -> SourceManifest:
    source_path = Path(path).expanduser().resolve(strict=True)
    if not source_path.is_file():
        raise ValueError(f"Source path is not a file: {source_path}")
    mime_type = mimetypes.guess_type(source_path.name)[0] or "application/octet-stream"
    return SourceManifest(
        source_id=str(uuid.uuid4()),
        source_type=source_type.upper(),
        original_name=source_path.name,
        storage_uri=source_path.as_uri(),
        sha256=sha256_file(source_path),
        mime_type=mime_type,
        size_bytes=source_path.stat().st_size,
        parser_name=parser_name,
        parser_version=parser_version,
    )
