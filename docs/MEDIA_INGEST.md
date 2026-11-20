# Offline Media Ingestion PoC

## Scope

This package provides source hashing, page-aware PDF text extraction, FFmpeg wrappers, ASR/OCR adapter contracts, and a JSON task journal with bounded retry and resume. It does not yet include production-scale queues, model downloads, ASR/OCR engine implementations, or full resource telemetry.

## Install

1. Install FFmpeg and ensure both ffmpeg and ffprobe are available on PATH.
2. Install the optional PDF dependency:

```powershell
python -m pip install -e ".[media,dev]"
ffmpeg -version
ffprobe -version
pytest
```

The base package does not require FFmpeg or pypdf. PDF text extraction raises a clear optional-dependency error when pypdf is missing. Image-only/scanned PDF pages are preserved as empty page segments and require a later OCR pass.

## Python API

```python
from aios_work_system.media import FFmpegProcessor, register_source
from aios_work_system.media.pdf import extract_pdf_pages
from aios_work_system.media.source import SegmentRecord

processor = FFmpegProcessor()
source = register_source("samples/lesson.mp4", "VIDEO")
metadata = processor.probe("samples/lesson.mp4")
audio = processor.extract_audio("samples/lesson.mp4", "artifacts/lesson.wav")
proxy = processor.create_proxy("samples/lesson.mp4", "artifacts/lesson-proxy.mp4")
frames = processor.extract_frames("samples/lesson.mp4", "artifacts/frames", 5)

source.add_segment(
    SegmentRecord.create(
        source_id=source.source_id,
        segment_type="TIME_RANGE",
        locator={"start_ms": 0, "end_ms": 5000},
        parser_name="ffmpeg",
        parser_version="system",
        media_uri=audio.resolve().as_uri(),
    )
)
source.save("artifacts/lesson.manifest.json")

pdf_source = register_source("samples/tables.pdf", "PDF")
pdf_segments = extract_pdf_pages("samples/tables.pdf", pdf_source.source_id)
for segment in pdf_segments:
    pdf_source.add_segment(segment)
pdf_source.save("artifacts/tables.manifest.json")
```

The source manifest records original filename, file URI, SHA-256, MIME type, size, parser identity, and page/time/frame locator segments. Derived artifacts never overwrite the source.

## Retry and resume

```python
from aios_work_system.media.tasks import TaskJournal

journal = TaskJournal("artifacts/task-journal.json")
journal.run(
    task_id="sha256-of-source-plus-operation-config",
    operation="extract_audio",
    action=lambda: processor.extract_audio("samples/lesson.mp4", "artifacts/lesson.wav"),
    max_attempts=2,
)
```

A successful task ID is skipped on later runs. Failed tasks retry within the remaining attempt budget. A task found in RUNNING state after a process interruption retries the interrupted attempt. Keep task IDs stable and include source hash plus operation parameters to avoid incorrectly reusing an old result.

## Evidence and known limits

- PDF segments use 1-based page numbers; blank text is retained so scanned pages are not silently discarded.
- FFmpeg probe, audio, proxy, and frame outputs are derived artifacts; the original is read-only.
- Frame extraction uses a fixed interval and returns files in filename order; callers should record timestamps as interval multiples.
- ASR/OCR are interfaces only. faster-whisper and PaddleOCR adapters are separate follow-up work.
- Elapsed task time is recorded. RAM/VRAM peaks are not measured by this PoC and must remain unknown, not estimated.
- The smoke tests mock FFmpeg and PDF reader boundaries. Actual Windows FFmpeg installation and representative media samples remain required for final acceptance.
