# Media Ingestion and Intelligent Video Extraction

## Current implementation boundary

The repository currently provides:

- Source registration and SHA-256 hashing.
- FFmpeg probing, audio extraction, proxy transcoding, and sampled-frame extraction.
- `ASRAdapter` and `OCRAdapter` Protocol interfaces.
- `StaticASRAdapter` and `StaticOCRAdapter` deterministic fixtures.
- A basic `VideoLearningPipeline` that invokes injected adapters and writes timestamped evidence artifacts.

The static adapters are supplied-text stand-ins, not real ASR or OCR inference. The current knowledge extractor interface is too narrow to represent a video-grounded sequence of actions, intent, and UI state transitions. A prior end-to-end test used an externally supplied SRT file; that proved orchestration and provenance, not model transcription or semantic video understanding.

## Target video pipeline

The target workflow is defined in [ACQUISITION_PIPELINE.md](ACQUISITION_PIPELINE.md):

1. Archive tutorial videos directly to Google Drive, organized by creator and course/series, with one source-link/platform download record per video.
2. **Clean before expensive extraction**: extract existing subtitle tracks/files first; when unavailable, transcribe audio using ASR. Use the resulting text to filter out videos that are not tutorials in the target vertical.
3. Only matching tutorials undergo full multimodal understanding. The understanding model watches frames/clips and listens to audio; it extracts actions, intent, interface elements, before/after UI state, outcomes, preconditions, and recovery knowledge. Magma separately grounds candidate action coordinates/trajectories.
4. Distinguish directly observed evidence from inferred actions or intent.
5. Deduplicate by content hash, pass GPT review and PM Sangou's independent video-evidence/test verification, then store approved knowledge in SQLite.
6. Use verified knowledge packages as LoRA training data, then validate the trained expert in a sandbox and GUI operation loop.

A transcript or OCR dump alone is not a valid extraction result. Quality takes priority over throughput.

## Model responsibilities

- **Qwen3-VL and Mage-VL** are video-understanding candidates. Their task is to watch/understand and produce text output: events, intent, UI state changes, result, and evidence-linked explanations. They are being compared in a blind Colab T4 test; no winner is recorded here.
- **Magma** is an action-grounding candidate. Its task is to produce coordinate/action-oriented output such as click points, target regions, and candidate trajectories. Evaluate it separately from the semantic understanding models.

The models' roles are complementary. A predicted coordinate is a model inference, not a historical click observation unless the original video visibly records it or synchronized input-event telemetry exists.

## Cheap text pre-filter details

For each downloaded video:

- Inspect embedded and sidecar subtitle availability.
- Prefer source-provided subtitles and preserve their language and timecodes.
- If subtitles are absent, call the configured ASR adapter to generate a timestamped transcript.
- Classify whether the content is a tutorial and belongs to the configured vertical.
- Retain rejected source/download metadata and a rejection reason; do not send rejected videos to expensive full extraction.

ASR is therefore a pre-filter dependency first. It is not the main learning objective and cannot by itself satisfy the video knowledge extraction requirement.

## Structured trajectory requirements

A full extraction result must contain ordered, time-aligned steps. Each step should record at least:

- action description and target element;
- source start/end time and supporting frame/transcript references;
- pre-action UI state and post-action UI state;
- observed action evidence and/or inferred action hypothesis;
- user's apparent intent and the evidence for that interpretation;
- expected outcome and whether it is visible;
- uncertainty/confidence and unresolved alternatives;
- relevant preconditions, exceptions, and recovery observations.

Store factual observations and inferences in separate typed fields. Do not collapse a predicted click coordinate into an observed click event.

## Existing FFmpeg API and retry

The existing processor can still be used for media metadata, audio extraction, proxy generation, and bounded frame extraction:

~~~python
from aios_work_system.media import FFmpegProcessor, register_source

processor = FFmpegProcessor()
source = register_source("samples/lesson.mp4", "VIDEO")
metadata = processor.probe("samples/lesson.mp4")
audio = processor.extract_audio("samples/lesson.mp4", "artifacts/lesson.wav")
proxy = processor.create_proxy("samples/lesson.mp4", "artifacts/lesson-proxy.mp4")
frames = processor.extract_frames("samples/lesson.mp4", "artifacts/frames", 5)
source.save("artifacts/lesson.manifest.json")
~~~

The FFmpeg layer is a media preparation utility, not a video-understanding model. It does not infer user intent or reconstruct missing input events.

TaskJournal remains useful for bounded retry/resume. Task IDs should include source content hash and operation configuration so retries cannot reuse stale outputs.

## Acceptance boundary

A component-level media smoke test proves only that media can be read and artifacts can be produced. It does not prove that the procedure is correctly understood. Acceptance requires labeled operation intervals, UI-state transitions, action targets, intent, observed/inferred classification, and expert-level GUI tests. See [TEST_PLAN.md](TEST_PLAN.md) and [SOFTWARE_TUTORIAL_BENCHMARK.md](SOFTWARE_TUTORIAL_BENCHMARK.md).

The full multimodal extraction engine, real video-understanding adapters, action-grounding adapter, trajectory schema, review workflow, and LoRA training pipeline are not yet implied by the existing media interfaces.
