# Media Ingestion and Downloaded-Video Learning

## Selected learning input

The primary tutorial-learning input is a **downloaded video file**, processed offline by the repository's video-extraction programs. The system does not play the video in real time and does not require a live rrweb/Windows UI Automation event collector.

**Superseded route — cancelled 2026-11-21:** the former proposal to instrument live web tutorials with rrweb and live Windows desktop tutorials with UI Automation was cancelled and replaced by downloaded-video-file extraction. The reason is architectural: a video-file pipeline can work from downloaded tutorials without requiring per-application recorder installation or a synchronized live event-collection session. Keep that proposal as history only, not as the active route or a required fallback.

Frame extraction is now part of the primary route, but it is not treated as a standalone action log. FFmpeg samples the local file; a pixel-difference detector selects changed frames; OCR, cursor/click inference, and local UI grounding operate on selected visual states; subtitle/ASR timestamps provide the narration context.

## Current implementation

The main entry point is `scripts/run_video_file_pipeline.py`, which calls `VideoExtractionPipeline` in `aios_work_system.video_extraction.pipeline`. Its stages include:

1. Load existing timestamped SRT/WebVTT subtitles; use local faster-whisper ASR only when usable subtitle cues are unavailable.
2. Decode timestamped stills from the video with FFmpeg and detect actual screen changes using grayscale pixel differences.
3. OCR visible text with Tesseract on the initial state and selected changed frames.
4. Track visible cursor candidates and infer possible clicks from cursor movement plus screen changes. These remain `inferred_from_video`; the file contains no native click event stream.
5. Run local GUI-target grounding on selected changed frames, with measured model-quality gates and bounded fallbacks.
6. Align timestamped transcript segments with visual events and assemble an auditable DecisionEpisode.
7. Validate the episode using `contracts.validate.validate_episode`.
8. Run the local open-weight DecisionEpisode verifier added in PR #39; a local PASS still leaves admission held until PM independent review.

The extraction path is local-only for inference. It does not send video, frames, OCR, transcript, or episode content to GPT, Gemini, hosted moderation, or other hosted model APIs.

## Evidence semantics

- `observed_from_video`: visible pixels, decoded screen changes, and OCR text.
- `inferred_from_video`: cursor/click hypotheses and model-grounded UI target coordinates.
- `instructor_words`: timestamped subtitle/ASR transcript.
- `unknown`: hidden or ambiguous activity that the video cannot establish.

A cursor hypothesis is not a recorded mouse event. A screen change is not proof that a particular click caused it. A tutorial's narration is not, by itself, proof of a universal business rule. The generated video-derived episode therefore does not claim that the operation executed or that its business outcome was verified unless separate evidence supports those claims.

## DecisionEpisode, review, and training stages

- **PR #38:** extracts evidence from the downloaded file, builds DecisionEpisodes, and validates their structure/semantics.
- **PR #39:** applies a local verifier to extraction fidelity, decision validity, and outcome validity. All three levels must pass; the independent PM gate remains separate and evidence-linked.
- **PR #40:** compiles only dual-approved, quality-approved decision points into conversational Brain samples. It writes source-grouped train/test splits, a manifest, and separate training metadata sidecars.
- **PR #41:** prepares and validates the Qwen3 4B Brain LoRA training setup. It does not mean an adapter has been trained.
- **PR #42:** provides the Brain/Hands closed-loop harness. CI acceptance uses a deterministic WorkflowBrain stand-in and SimulatedHands, not a trained LoRA or real operation model.

These are separate components and artifacts, not a claim that every stage is wired into one production service.

## Existing FFmpeg API and general media utilities

The existing media layer remains useful for basic media operations such as probing, audio extraction, proxy generation, and utility frame inspection:

~~~python
from aios_work_system.media import FFmpegProcessor, register_source

processor = FFmpegProcessor()
source = register_source("samples/lesson.mp4", "VIDEO")
metadata = processor.probe("samples/lesson.mp4")
audio = processor.extract_audio("samples/lesson.mp4", "artifacts/lesson.wav")
proxy = processor.create_proxy("samples/lesson.mp4", "artifacts/lesson-proxy.mp4")
source.save("artifacts/lesson.manifest.json")
~~~

The older `extract_frames` helper remains a general media utility. The selected learning path uses the dedicated `video_extraction.frames.extract_sampled_frames` and `detect_frame_changes` stages; their changed-frame output is an input to OCR/grounding/episode extraction, not direct event telemetry.

TaskJournal remains useful for bounded retry/resume. Task IDs should include source content hash and operation configuration so retries cannot reuse stale outputs.

## Acceptance boundary

A media smoke test proves only that media can be read and basic artifacts can be produced. The learning path additionally requires:
- valid timed subtitles or local ASR output;
- timestamped frame samples and screen-change detection;
- OCR and explicitly labelled cursor/target inferences;
- narration-to-visual-event alignment;
- a structured DecisionEpisode and contract validation;
- local verifier output with explicit pass/fail/unknown states;
- independent PM verification before training admission;
- fail-closed sample compilation, followed by Brain LoRA preparation and Brain/Hands evaluation.

Do not equate frame count, OCR character count, subtitle volume, a successful click hypothesis, or schema validity with learned workflow competence.
