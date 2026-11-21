# Offline Media Ingestion PoC

## Scope

This package provides source hashing, page-aware PDF text extraction, FFmpeg wrappers,
ASR/OCR adapter contracts, timestamped video chunking, and a JSON task journal with
bounded retry and resume. It does not include production queues, model downloads,
model inference adapters, or full resource telemetry.

## Install

1. Install FFmpeg and ensure both ffmpeg and ffprobe are available on PATH.
2. Install the optional PDF dependency:

~~~powershell
python -m pip install -e ".[media,dev]"
ffmpeg -version
ffprobe -version
pytest
~~~

The base package does not require FFmpeg or pypdf. PDF text extraction raises a clear
optional-dependency error when pypdf is missing. Image-only/scanned PDF pages are
preserved as empty page segments and require a later OCR pass.

## Video to knowledge evidence

**VideoLearningPipeline** is the smallest end-to-end video path. It probes the source,
extracts mono 16 kHz audio and sampled frames with FFmpeg, invokes injected ASR/OCR
adapters, groups timestamped text into fixed windows, and writes a source manifest plus
candidate knowledge-evidence JSON.

~~~python
from aios_work_system.media.adapters import TranscriptSegment
from aios_work_system.video_learning import (
    StaticASRAdapter,
    StaticOCRAdapter,
    VideoLearningPipeline,
)

pipeline = VideoLearningPipeline(
    asr=StaticASRAdapter(
        name="asr-fixture",
        version="1",
        segments=[TranscriptSegment(1000, 5000, "Open the settings menu.")],
    ),
    ocr=StaticOCRAdapter(
        name="ocr-fixture",
        version="1",
        text_by_timestamp={0: "Settings"},
    ),
)
result = pipeline.ingest(
    "samples/lesson.webm",
    "artifacts/lesson",
    expert_id="software-learning",
    applicability_scope="Application/version and workflow where this instruction applies",
    source_version="source-release-or-capture-date",
)
~~~

The static adapters are deterministic fixtures, not speech recognition or image
recognition. They test orchestration and provenance before adding optional real
inference engines. The default verbatim extractor only creates CANDIDATE direct quotes;
it does not claim that the tutorial procedure is correct, current, or independently
learned. A reviewer must approve extracted facts or procedural knowledge separately.

The evidence record retains source filename/URI/SHA-256, source version, segment ID,
start/end milliseconds, expert scope, applicability scope, knowledge version, and
adapter/parser identities/versions. Manifest segments also retain the extracted audio
and frame artifact URIs. The original video is never overwritten.

## Licensed screencast smoke run (CI)

The repository reuses Wikimedia's **Content Translation Screencast (English)** by Pau
Giner (2015-01-13), licensed CC BY-SA 4.0. Source and attribution are documented in
[SOFTWARE_TUTORIAL_BENCHMARK.md](SOFTWARE_TUTORIAL_BENCHMARK.md). The integration job
downloads that sample, runs real FFmpeg audio/frame extraction, uses published English
timed text as a deterministic ASR stand-in, and curated procedural landmarks as an OCR
stand-in. The generated report labels both adapters as stubs. This is a plumbing and
provenance test, not ASR/OCR accuracy evidence or a live software replay.

Run locally after downloading the video and its English SRT captions:

~~~powershell
python -m pip install -e .
python scripts/run_video_learning_sample.py --input artifacts/content-translation/tutorial.webm --captions artifacts/content-translation/tutorial.en.srt --output-dir artifacts/content-translation/output
~~~

## Existing Python API: source and PDF

~~~python
from aios_work_system.media import FFmpegProcessor, register_source
from aios_work_system.media.pdf import extract_pdf_pages

processor = FFmpegProcessor()
source = register_source("samples/lesson.mp4", "VIDEO")
metadata = processor.probe("samples/lesson.mp4")
audio = processor.extract_audio("samples/lesson.mp4", "artifacts/lesson.wav")
proxy = processor.create_proxy("samples/lesson.mp4", "artifacts/lesson-proxy.mp4")
frames = processor.extract_frames("samples/lesson.mp4", "artifacts/frames", 5)

pdf_source = register_source("samples/tables.pdf", "PDF")
pdf_segments = extract_pdf_pages("samples/tables.pdf", pdf_source.source_id)
for segment in pdf_segments:
    pdf_source.add_segment(segment)
pdf_source.save("artifacts/tables.manifest.json")
~~~

The source manifest records original filename, file URI, SHA-256, MIME type, size,
parser identity, and page/time/frame locator segments. Derived artifacts never
overwrite the source.

## Retry and resume

~~~python
from aios_work_system.media.tasks import TaskJournal

journal = TaskJournal("artifacts/task-journal.json")
journal.run(
    task_id="sha256-of-source-plus-operation-config",
    operation="extract_audio",
    action=lambda: processor.extract_audio("samples/lesson.mp4", "artifacts/lesson.wav"),
    max_attempts=2,
)
~~~

A successful task ID is skipped on later runs. Failed tasks retry within the remaining
attempt budget. A task found in RUNNING state after a process interruption retries the
interrupted attempt. Keep task IDs stable and include source hash plus operation
parameters to avoid incorrectly reusing an old result.

## Evidence and known limits

- PDF segments use 1-based page numbers; blank text is retained so scanned pages are not silently discarded.
- FFmpeg probe, audio, proxy, and frame outputs are derived artifacts; the original is read-only.
- Frame extraction uses a fixed interval and returns files in filename order; callers record timestamps as interval multiples.
- ASR/OCR are injectable interfaces; this change includes only deterministic stubs, not inference engines.
- Video chunks are fixed-duration windows, not semantic chapter boundaries.
- Knowledge output is CANDIDATE evidence and requires review; source version and applicability scope must be supplied by the caller.
- Elapsed task time is recorded. RAM/VRAM peaks are not measured and must remain unknown, not estimated.
- Unit tests mock FFmpeg boundaries; the licensed screencast CI job exercises actual FFmpeg while keeping ASR/OCR inference stubbed.
