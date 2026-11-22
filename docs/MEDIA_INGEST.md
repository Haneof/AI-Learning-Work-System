# Media Ingestion and Tutorial Event Learning

## Current implementation boundary

The repository currently provides:
- source registration and SHA-256 hashing;
- FFmpeg probing, audio extraction, proxy transcoding, and utility frame extraction;
- ASRAdapter and OCRAdapter Protocol interfaces;
- StaticASRAdapter and StaticOCRAdapter deterministic fixtures;
- a basic VideoLearningPipeline that invokes injected adapters and writes timestamped evidence artifacts.

The static adapters are supplied-text stand-ins, not real ASR or OCR inference. The current knowledge extractor interface is too narrow to represent business decisions and conditional workflows. A prior end-to-end test used an externally supplied SRT file; it proved orchestration and provenance, not real transcription or workflow understanding.

## Selected target ingestion path

The primary input to tutorial learning is a **semantic UI operation event stream plus instructor narration**.

### New recordings

- Web applications: capture rrweb snapshots and incremental events from the start of the tutorial. Keep DOM changes, interaction events, focus, scroll, input changes, event timestamps, page/session identity, and available element references.
- Windows desktop applications: capture supported Windows UI Automation events and relevant AutomationElement properties/state changes with timestamps and window/application identity.
- Audio: preserve the instructor's original voice recording and synchronization metadata.
- Text: extract usable subtitles first. Use ASR only when subtitles are unavailable, then align the transcript to the audio with word- or segment-level timestamps.

### Legacy MP4 recordings

An old MP4 does not contain the original DOM or UI Automation event log. If these recordings are retained, reconstruct only what can be supported by reviewing the recording and narration. Mark reconstructed UI actions and state changes as inferred_from_video. Hidden clicks and uncertain actions remain unknown.

Frame extraction is not the primary event-generation or Brain-training approach. Existing FFmpeg frame utilities may support legacy inspection or component tests, but a sampled frame sequence is not a substitute for direct event capture.

## From event stream and voice to workflow knowledge

Normalize the recorded events into page changes, control changes, mouse/input interactions, focus, navigation, and state transitions. Align them with transcript segments and, where reliable, word timestamps.

A Decision Episode must explain:
- the task goal and current situation;
- what the instructor said and why, if explicitly stated;
- what behavior was directly captured or reconstructed;
- the strategy or decision demonstrated;
- the resulting UI/business state and whether it was verified;
- what should happen next, including conditional branches and recovery.

The output is a source-linked Decision Episode and workflow knowledge, not a screenshot sequence or transcript-only summary.

## Brain and Hands separation

The language-model Brain learns workflow planning, preconditions, conditions, business reasoning, capability choice, verification, and recovery. Existing Hands models handle page perception and concrete UI actions. The Brain delegates high-level capability tasks; Hands returns execution status and observed state; the Brain chooses the next decision.

Do not train the Brain to reproduce mouse coordinates or button-recognition behavior that belongs to the Hands layer.

## Existing FFmpeg API and legacy utilities

The current processor remains useful for metadata probing, audio extraction, proxy generation, and legacy video inspection:

~~~python
from aios_work_system.media import FFmpegProcessor, register_source

processor = FFmpegProcessor()
source = register_source("samples/lesson.mp4", "VIDEO")
metadata = processor.probe("samples/lesson.mp4")
audio = processor.extract_audio("samples/lesson.mp4", "artifacts/lesson.wav")
proxy = processor.create_proxy("samples/lesson.mp4", "artifacts/lesson-proxy.mp4")
source.save("artifacts/lesson.manifest.json")
~~~

The existing extract_frames helper remains available for legacy MP4 inspection and component-level experiments. Its output must not be treated as the primary operational trajectory input or direct event telemetry.

The FFmpeg layer is a media preparation utility. It does not capture rrweb/Windows UIA events, infer business intent, or recover hidden input logs from an MP4.

TaskJournal remains useful for bounded retry/resume. Task IDs should include source content hash and operation configuration so retries cannot reuse stale outputs.

## Acceptance boundary

A component-level media smoke test proves only that media can be read and artifacts can be produced. It does not prove that the workflow has been understood. Acceptance requires:
- timestamped semantic event records for direct recordings, or explicitly inferred historical-video reconstructions;
- narration aligned to the event timeline;
- Decision Episodes with goals, states, reasons, decisions, outcomes, and next steps;
- HTN workflow definitions with conditional branches and recovery paths;
- provenance and uncertainty labels;
- Brain decision tests and Brain-to-Hands execution tests.

The full direct event recorder, narration alignment, Decision Episode extraction, workflow learning, Brain LoRA training, and runtime delegation pipeline are not yet implied by the existing media interfaces.
