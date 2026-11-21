# Offline Media Ingestion PoC

## Scope

This package provides source hashing, page-aware PDF text extraction, FFmpeg wrappers, ASR/OCR adapter contracts, durable timestamped media analysis, and retry/recovery metadata. The analysis pipeline verifies registered source integrity, extracts normalized audio and bounded keyframes, and persists optional ASR/OCR evidence. Concrete ASR/OCR engines, production worker orchestration, model downloads, and full resource telemetry are still out of scope.

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

## Durable asset analysis

A downloaded asset must already exist in `MediaAssetRepository`. The pipeline verifies the registered file size and SHA-256 again before processing. A run is keyed by asset ID, source hash, and a hash of the analysis settings/adapters, so a completed result with the same inputs is reused.

```python
from aios_work_system.media import (
    FFmpegProcessor,
    MediaAnalysisPipeline,
    MediaAnalysisRepository,
    MediaAssetRepository,
)

pipeline = MediaAnalysisPipeline(
    asset_repository=MediaAssetRepository(
        "artifacts/acquisition/assets.sqlite3",
        "artifacts/acquisition/asset_manifests",
    ),
    analysis_repository=MediaAnalysisRepository(
        "artifacts/acquisition/analysis.sqlite3"
    ),
    output_root="artifacts/media/derived",
    ffmpeg=FFmpegProcessor(),
    frame_interval_seconds=5.0,
    max_frames=240,
)
result = pipeline.analyze("asset-id-from-discover-download")
print(result.status, result.audio_path, result.frame_paths)
print(result.warnings)
```

The CLI exposes the same preprocessing path:

```powershell
aios media-analyze --asset-id <asset-id>
```

Optional storage/runtime settings include `--assets-database`, `--manifest-dir`, `--analysis-database`, `--derived-dir`, `--ffmpeg`, `--ffprobe`, `--timeout-seconds`, `--frame-interval-seconds`, and `--max-frames`.

When no ASR/OCR adapter is configured, the pipeline still extracts available audio and video evidence but correctly returns `PARTIAL` with explicit warnings. It does not fabricate transcript or OCR text. `ASRAdapter` and `OCRAdapter` are extension contracts only; this branch does not yet install or ship concrete model adapters.

Analysis metadata, artifact file hashes/sizes, transcript offsets, and OCR timestamps are stored in SQLite. If an ASR/OCR or FFmpeg step fails, the run is persisted as `FAILED`. A later retry reuses the same run ID, increments the attempt count, clears only that run's previous derived output directory, and regenerates results. A completed or partial run with identical source/config is reused without rerunning.

A duplicate call that encounters an already `RUNNING` run will not start another copy. After confirming the previous worker process is gone, the worker startup path may call `MediaAnalysisRepository.recover_interrupted()` to mark abandoned runs failed so they can be retried. Do not call it while another worker is actively processing.

Frame extraction has both a calculated interval and a hard `max_frames` FFmpeg limit. The hard limit applies even if ffprobe cannot determine duration. Stale `frame_*.jpg` outputs are removed before extraction.

## Optional ASR and OCR engines

The stable adapter interfaces have optional concrete implementations:

- `FasterWhisperASRAdapter`: lazy-loads faster-whisper and turns each speech segment's start/end into millisecond offsets. The conservative default is CPU + int8; the model is downloaded on first use unless it is already cached or a local model path is supplied. For a CUDA deployment, verify the installed CTranslate2/CUDA/cuDNN combination before selecting `device="cuda"`.
- `PaddleOCRAdapter`: lazy-loads PaddleOCR 3.x and returns recognized text, bounding boxes, confidence scores, and the timestamp of the source frame. PP-OCRv6 supports tiny/small/medium tiers; tiny is the smallest footprint, while small is the default CLI balance. PaddleOCR itself is an API package; install the platform-compatible PaddlePaddle inference engine separately.

Install only the engine needed:

```powershell
# ASR only
python -m pip install -e ".[asr]"

# OCR Python package
python -m pip install -e ".[ocr]"
# Then install the CPU or GPU PaddlePaddle inference package matching
# your OS, Python version, and CUDA environment from Paddle's install guide.
```

The CLI enables model work explicitly, so a default `media-analyze` call does not download model weights:

```powershell
# Small Whisper model, CPU int8; language code zh
aios media-analyze --asset-id <asset-id> --asr-model-size small

# PP-OCRv6 small models
aios media-analyze --asset-id <asset-id> --enable-ocr --ocr-model-tier small

# Lowest-footprint PP-OCRv6 option
aios media-analyze --asset-id <asset-id> --enable-ocr --ocr-model-tier tiny

# Enable both engines in one run
aios media-analyze --asset-id <asset-id> --asr-model-size small --enable-ocr --ocr-model-tier small
```

Other ASR options are `--asr-device`, `--asr-compute-type`, `--asr-language`, and `--asr-download-root`. OCR options are `--ocr-device` and `--ocr-min-confidence`. The CLI uses the multilingual PP-OCRv6 model names directly; when explicit model names are supplied, PaddleOCR's `lang` selector is intentionally omitted. The Python API can instead use `lang` with PaddleOCR's default models, or provide an explicit detection/recognition model pair and an inference engine.

A run's identity includes adapter name, package version and adapter configuration, so changing Whisper model size, compute type, OCR model tier, language, device, or confidence threshold creates a distinct analysis configuration rather than silently reusing incompatible evidence.

The current automated tests inject fake model factories. They verify parameter mapping, timestamp conversion, result normalization, confidence filtering and lazy loading, but do not download model weights or establish real inference accuracy, throughput, GPU compatibility, or memory use. Those require representative tutorial recordings and the target machine.

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
- ASR/OCR are interfaces only. faster-whisper and PaddleOCR adapters remain separate follow-up work; a PARTIAL result is expected until they are configured.
- Elapsed task time is recorded. RAM/VRAM peaks are not measured by this PoC and must remain unknown, not estimated.
- The smoke tests mock FFmpeg and PDF reader boundaries. Actual Windows FFmpeg installation and representative media samples remain required for final acceptance.
