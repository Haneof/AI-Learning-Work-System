# Tutorial Acquisition and Brain Learning Pipeline

## Purpose and priority

This document describes the selected, implemented learning route for turning professional tutorials into source-grounded workflow knowledge for a language-model Brain that directs an existing GUI operation model (the Hands).

**Quality ranks first; efficiency ranks second.** The primary input is a downloaded tutorial video file. Programs process that file offline. The system does not play tutorials as a live session, and tutorial learning does not depend on rrweb, Windows UI Automation event capture, or a live event collector.

The current implementation milestones are PRs #38–#42. They provide extraction, structured episode generation and validation, a local verifier, an approved-sample compiler, LoRA preparation/configuration, and a Brain/Hands closed-loop harness. They do not yet constitute a deployed production service or a trained domain expert.

## Superseded design decision — 2026-11-21

The previously proposed live-recorder/event-collector route was cancelled on **2026-11-21** and superseded by downloaded-video-file extraction. The architectural reason is that the selected route works from tutorial files that can be downloaded and processed locally, without requiring a recorder to be installed in or synchronized with each live web/desktop tutorial session. The old rrweb-for-web / Windows-UIA-for-desktop proposal is retained here as historical design context only; it is not an active primary route or a required fallback.

The selected route does use frames. It does **not** treat a sparse/dense frame dump as a complete action log: it samples the file, detects actual screen changes, and grounds visual/cursor hypotheses against timestamped narration and OCR. A video does not contain native click telemetry, so inferred clicks remain explicitly inferred.

## Roles: Brain and Hands

- **Brain:** the language model plus a vertical LoRA. It learns the business goal, workflow structure, reasons, preconditions, conditional branches, operation capability selection, result verification, and recovery decisions.
- **Hands:** an existing GUI operation model and adapter (for example, UI-TARS). It handles live page perception, control localization, clicking, typing, scrolling, and other low-level UI operations. Reuse this layer; do not build a replacement perception/action model as part of Brain training.
- **Video-file extractor:** processes a downloaded file and produces timestamped transcript, visual, OCR, cursor, and UI-grounding evidence from which DecisionEpisodes can be proposed.
- **Narration processor:** prefers supplied subtitles and uses local ASR only when usable subtitle tracks are unavailable; it preserves the instructor's words and timestamps.

The Brain chooses what should happen and why. The Hands execute the delegated capability and return a structured result. The Brain then decides what happens next.

## Step 1 — Download and archive

1. Search for tutorials in the selected target vertical.
2. Download the tutorial video file and any available timed subtitle file. The repository includes a downloader implementation; the long-term archive target remains Google Drive.
3. Organize the archive hierarchically by creator and series/course. A platform grouping may sit above the creator level, but the course structure must remain intact:

   ~~~text
   AI-Learning/
     <platform>/
       <creator>/
         <series-or-course>/
           <video-file>
           <subtitle-file>
   ~~~

4. Keep one download record for every video. At minimum, record the canonical source link and platform. Also retain creator, series/course, title, discovery/download time, Drive file ID/link/path, byte size, content SHA-256, and download status when available.
5. Preserve source metadata and attribution/license information where available. Unknown license metadata stays unknown; it must not be guessed.

The downloader's final archive target is Drive. The repository's Google Drive API OAuth helper is an integration component, not proof that the complete cloud-downloader-to-Drive archive service is deployed.

## Step 2 — Process the downloaded video file

The executable entry point is `scripts/run_video_file_pipeline.py`; the main implementation is `aios_work_system.video_extraction.pipeline.VideoExtractionPipeline`.

### 2a. Subtitle / ASR

1. Prefer a supplied local SRT/WebVTT subtitle file when it contains usable timestamped cues.
2. If no usable subtitle cues exist, transcribe the downloaded video's audio locally with faster-whisper.
3. Preserve source, language, transcript method, and segment/word timestamps. Cues outside the media duration are not treated as valid transcript evidence.

The narration provides goals, motivation, explanations, conditions, constraints, and domain context. A transcript records what the instructor said; it does not automatically prove the statement is a universally correct business rule.

### 2b. Frame-change-driven visual extraction

1. FFmpeg decodes timestamped sampled stills from the local video file.
2. A grayscale pixel-difference detector compares adjacent samples and selects initial/changed frames. Unchanged frames are not treated as separate workflow actions and are not sent through the expensive grounding path.
3. Tesseract OCR reads visible text and text-region boxes on the initial state and selected changed frames.
4. OpenCV cursor tracking and the changed-region heuristic generate possible cursor/click candidates. These are hypotheses inferred from pixels, not native mouse/click events.
5. Local GUI-grounding models (ShowUI/UI-TARS) can localize a target in selected changed frames. Their benchmark measures point-in-annotated-target-box hit rate, not click-event accuracy. Model escalation is controlled by measured quality gates.

### 2c. Evidence classification and narration alignment

- `observed_from_video`: decoded frames, screen changes, and text visibly read by OCR.
- `inferred_from_video`: cursor/click hypotheses and UI target coordinates returned by a grounding model.
- `instructor_words`: timestamped subtitle or ASR transcript; this is what the speaker said, not proof that an operation executed.
- Unknown or hidden activity stays unknown. Do not invent DOM mutations, keyboard events, or click telemetry that the video cannot show.

Timestamped transcript segments are aligned to visual screen-change events. The evidence model preserves the source time range and the distinction between observation, inference, and instructor narration.

## Step 3 — Build and validate DecisionEpisodes (PR #38)

The minimal learning unit is a **DecisionEpisode**, not a chronological list of clicks. It represents:

**goal at the time → visible/known state → stated or inferred reason → selected decision → operation hypothesis → supported result evidence → next decision.**

The extractor builds a structured episode from transcript segments, changed-frame observations, OCR, cursor/target hypotheses, and source metadata. The current video-derived episode is deliberately conservative: it keeps business constraints empty when unsupported, marks operation execution as not observed, marks outcome as not verified, and uses an ask-user review action where human confirmation is required.

Every episode is checked by `contracts.validate.validate_episode` against the versioned DecisionEpisode schema and semantic rules. A valid schema does not mean that the episode is true, independently reviewed, or approved for training.

## Step 4 — Local verification and PM admission gate (PR #39)

The local open-weight verifier evaluates three independent dimensions:

1. **Extraction fidelity:** episode claims must match timestamped transcript, OCR, frame-change, cursor, and GUI-grounding source records.
2. **Decision validity:** the selected decision must be reasonable using only information available at that decision point.
3. **Outcome validity:** there must be evidence for actual execution and a passed business postcondition, with confounders addressed. A video-only sequence is UNKNOWN, not causal proof.

All three levels must pass; there is no majority vote. Missing evidence or malformed output is held as unknown. The local verifier receives structured timestamped extraction evidence rather than raw pixels, so the PM must still inspect the original source and proposed episode independently.

**Local PASS is not training approval.** The preliminary admission state remains held pending the independent PM verification. Dataset admission requires both local verification and an evidence-linked PM PASS.

## Step 5 — Compile approved DecisionEpisodes into samples (PR #40)

The training-sample compiler consumes review bundles containing the episode, local-verification report, and PM-verification record. It fails closed unless:
- all three local verification levels pass;
- the independent PM gate passes and cites source evidence and reviewed episode claims;
- episode review approval and approved-for-training flags are set;
- annotation quality is `human_reviewed` or `gold`, `trainable=true`, and exclusion reasons are empty.

The compiler produces one Brain decision sample per decision point, source/course-grouped train/test splits, a manifest, and separate `training_meta` sidecars. Sidecar data is not part of model messages. The assistant target predicts the Brain's next decision only; future Hands results are not leaked into earlier decisions.

## Step 6 — Prepare the Brain LoRA training setup (PR #41)

The repository includes metadata-aware dataset preparation, train/test validation, tokenization checks, and an Axolotl configuration for the Qwen3 4B Brain LoRA profile. This is a reproducible setup and configuration gate, not a claim that a training run has completed or that a trained adapter exists. A non-empty dataset that passes the admission gates and an actual logged training run are still required.

## Step 7 — Brain-to-Hands closed loop (PR #42)

The Brain sends a high-level capability delegation with business arguments, preconditions, constraints, expected postconditions, and risk/approval metadata. Hands returns a correlated execution result with observed state, per-postcondition results, errors, and evidence references. The loop performs fresh observation and independent postcondition verification before it accepts progress; failed, partial, or uncertain results return to Brain for re-planning/recovery.

The current CI path uses a deterministic `WorkflowBrain` stand-in driven by a WorkflowDefinition and `SimulatedHands`. `BrowserAgentHandsAdapter` bridges the protocol to the existing BrowserAgent and requires a domain-specific fresh business-state observer. No real Brain LoRA adapter or real UI-TARS-class Hands operation model was provisioned or run for PR #42. The closed-loop harness is not proof of a trained expert or a production end-to-end integration.

## Storage and provenance

- Original tutorial video files and course groupings live in the archive; source URL, platform, attribution/license, and content hash remain attached.
- Transcript records retain subtitle/ASR source, language, time ranges, and method.
- Visual records retain frame timestamps, screen-change status, OCR text/boxes, and source frame references.
- Cursor/click and UI-target hypotheses retain their inference method and must remain labelled `inferred_from_video`.
- DecisionEpisodes link the evidence they use, retain unknowns, and preserve separate rationale/provenance labels.
- Local verification, PM review, compiler manifests, sidecars, training configuration, adapter lineage, and Brain/Hands execution traces remain separately auditable.
- Failed, rejected, held, and superseded records remain traceable but are excluded from approved training snapshots.

## Historical model experiment status

The earlier Colab T4 blind comparison of Qwen3-VL-4B and Mage-VL-4B was stopped on 2026-11-21 at approximately 19:51 PST after Qwen3-VL-4B scored 4.0/25. The comparison was not completed as a valid winner-selection benchmark; no model winner is claimed. This result did not reject frame extraction. The selected path is the file-based, frame-change-driven pipeline described above.

## Current implementation boundary

The repository contains the video-file extractor, DecisionEpisode builder and contract validator (#38), local decision verifier (#39), fail-closed training-sample compiler (#40), metadata-aware Brain LoRA preparation/configuration (#41), and Brain/Hands loop with simulated acceptance (#42). The extraction path uses local open-weight inference; it does not send video, image, OCR, transcript, or episode content to hosted model APIs.

The pipeline stages are implemented as repository components and harnesses, not yet as a deployed single service. The compiler requires separately supplied PM review evidence. No real Brain adapter has been trained, and the current Brain/Hands CI acceptance uses a deterministic stub and simulated Hands.