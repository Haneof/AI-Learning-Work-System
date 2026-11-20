"""Page-aware PDF text extraction with an optional pypdf dependency."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from aios_work_system.media.source import SegmentRecord


def extract_pdf_pages(
    path: str | Path,
    source_id: str,
    parser_version: str = "pypdf-adapter-0.1.0",
    reader_factory: Callable[[str], Any] | None = None,
) -> list[SegmentRecord]:
    pdf_path = Path(path).expanduser().resolve(strict=True)
    if reader_factory is None:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError(
                "PDF text extraction requires the optional dependency. "
                "Install with: python -m pip install -e '.[media]'"
            ) from exc
        reader_factory = PdfReader

    reader = reader_factory(str(pdf_path))
    segments: list[SegmentRecord] = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        segments.append(
            SegmentRecord.create(
                source_id=source_id,
                segment_type="PAGE",
                locator={"page": page_number},
                parser_name="pypdf",
                parser_version=parser_version,
                text_content=text,
            )
        )
    return segments
