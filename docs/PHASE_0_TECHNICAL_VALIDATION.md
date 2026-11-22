# Phase 0: Technical Validation Plan

**Version:** 0.2, aligned with merged PRs #38–#42  
**Status:** extraction, verifier, compiler, LoRA setup, and simulated Brain/Hands harnesses are implemented; a real approved-corpus training run and real Hands evaluation remain outstanding.  
**Priority:** prove that downloaded tutorials can yield evidence-grounded decision supervision and that a Brain can generalize workflow decisions before optimizing throughput.

## 1. Phase objective

Validate the following auditable pipeline:

1. Acquire a downloadable tutorial video file and available timed subtitles.
2. Process the file offline with local programs: subtitle/ASR, FFmpeg frame sampling, screen-change detection, OCR, cursor/possible-click inference, and local UI grounding.
3. Align transcript timestamps with visual changes; build a structured DecisionEpisode and validate it against the contract.
4. Run the local open-weight verifier for extraction fidelity, decision validity, and outcome validity.
5. Require an independent evidence-linked PM PASS before training admission.
6. Compile approved decision points into source-grouped conversational Brain samples and separate metadata sidecars.
7. Prepare and execute the configured Brain LoRA training run.
8. Connect the trained Brain to existing Hands infrastructure and verify business outcomes through the Brain/Hands loop.

The tutorial is processed as a **downloaded video file**. The system does not play it in real time and does not require a live event recorder. A transcript, video summary, OCR output, candidate click, or schema-valid record alone is not a successful learning result.

## 2. Scope and architecture boundaries

### Tutorial evidence input

The current primary route uses downloaded video files and local extraction. Prefer usable SRT/WebVTT subtitles; use local faster-whisper only when usable subtitle cues are unavailable. FFmpeg creates timestamped samples; pixel-difference detection selects screen changes; Tesseract reads visible text; OpenCV and local GUI-grounding models produce possible cursor/click/target hypotheses for selected frames.

Evidence must stay correctly labelled:
- `observed_from_video`: decoded visible state, screen changes, and OCR text.
- `inferred_from_video`: cursor/click and UI-target hypotheses inferred from pixels/model grounding.
- `instructor_words`: timed subtitles or ASR transcript.
- `unknown`: hidden or ambiguous actions and states that the file cannot establish.

A video file does not contain native rrweb, Windows UIA, mouse, keyboard, or DOM event telemetry. Do not claim such direct telemetry or infer business success from a screen change alone.

### Brain — the learning target

The Brain is the language model plus a vertical LoRA. It must learn:
- decomposition of a business goal into subgoals;
- task ordering and dependencies;
- conditional branch selection;
- the purpose and constraints behind business actions;
- selection of an available operation capability;
- verification of postconditions from Hands feedback;
- diagnosing failures, recovering, replanning, asking the user, requesting approval, or stopping;
- applying workflow principles to different starting states and alternative valid paths.

### Hands — reused execution infrastructure

Hands is an existing open-source GUI operation model (for example, UI-TARS) and its adapter. It handles live page perception, UI element localization, and low-level operation. The Brain delegates high-level capability requests; Hands returns structured results.

## 3. Implemented work packages

### WP0 — Downloaded video-file acquisition (PR #38 support)

- Download the tutorial video and available subtitle files.
- Preserve source URL/platform, source hash, creator/course information, and attribution/license metadata.
- Keep the downloaded file locally available to the extraction command.

**Boundary:** the downloader exists; a fully managed production downloader-to-Google-Drive archive workflow is not implied by the extractor.

### WP1 — Local extraction and DecisionEpisode validation (PR #38)

- Prefer existing timestamped subtitles; run local ASR only when usable subtitles are absent.
- Decode timestamped sampled frames with FFmpeg.
- Detect screen changes through grayscale pixel differences and select initial/changed frames.
- Run OCR on visible text, infer cursor/click candidates, and ground UI targets using local open-weight models.
- Align timestamped narration to visual events.
- Build a DecisionEpisode with source evidence and explicit unknown/inferred labels.
- Validate with `contracts.validate.validate_episode`.

**Exit:** episode claims match the source records or are explicitly marked inferred/unknown; schema validity is not mistaken for correctness or approval.

### WP2 — Local verifier and PM gate (PR #39)

- Run local open-weight verification for extraction fidelity, decision validity, and outcome validity.
- Preserve separate pass/fail/unknown statuses, reasons, evidence references, and unknowns.
- Require all three local levels to pass; no majority vote.
- Independently inspect the original video and proposed DecisionEpisode, and record the PM PASS with evidence references.

**Exit:** only records with all three local passes and a separate independent PM PASS may proceed toward training admission. A video-only temporal sequence is UNKNOWN for causal outcome validity.

### WP3 — Training-sample compiler (PR #40)

- Compile one conversational sample per decision point.
- Require local verification, PM verification, approved review, eligible annotation status, quality/trainable approval, and no exclusion reasons.
- Keep evidence-tier and rationale-loss-weight metadata in a separate sidecar.
- Group train/test splits by source/course; keep future Hands execution outcomes out of earlier decision targets.

**Exit:** held/rejected/incomplete records fail closed; compiler output and its sidecars are aligned and auditable.

### WP4 — Brain LoRA dataset preparation and training configuration (PR #41)

- Validate aligned training-metadata sidecars and reject excluded samples.
- Calculate bounded evidence-aware weighting for training rows; keep held-out test rows unchanged.
- Use the documented `DreamFast/qwen3-4b-heretic` Transformers checkpoint with the T4 FP16 Axolotl LoRA configuration.
- Record base revision, dataset hash, training parameters, compute, logs, metrics, and adapter hash for an actual run.

**Exit:** an eligible multi-source corpus exists, an actual training job completes, and the adapter is evaluated on held-out decision points. PR #41 only delivered preparation/configuration; it did not execute training or produce an adapter.

### WP5 — Brain-to-Hands closed loop (PR #42)

- Use typed business-level delegation and correlated Hands result messages.
- Refresh business state before decisions and after execution.
- Independently verify expected postconditions against fresh state and evidence.
- Return failed/partial/uncertain results to Brain for recovery/replanning; do not blindly continue.
- Evaluate business-goal completion, safe recovery, and alternate paths.

**Exit:** first prove the loop with a deterministic Brain and simulated Hands, then attach the actual trained Brain adapter and evaluate the real Hands operation model on a controlled local application. The merged CI path uses WorkflowBrain + SimulatedHands; it is not a real-model execution.

## 4. Historical route decision

The previously proposed live tutorial recorder/event collector (rrweb for web sessions and Windows UI Automation for desktop sessions) was cancelled on **2026-11-21**. It was superseded by downloadable-video-file extraction because the selected workflow operates on tutorial files without installing and synchronizing a recorder within each live application/session. This route is kept as historical context only, not an active alternative or required fallback.

The earlier Qwen3-VL-4B vs Mage-VL-4B Colab T4 comparison was stopped on 2026-11-21 at approximately 19:51 PST after Qwen3-VL-4B scored 4.0/25. The comparison did not produce a validated model winner. It did not reject the current frame-change-driven video-file extraction route.

## 5. Quality gates

Freeze thresholds before held-out evaluation. At minimum measure:
- episode evidence coverage and unsupported-claim rate;
- subtitle/ASR timestamp validity and transcript-to-visual alignment;
- screen-change and OCR grounding accuracy;
- target-box localization accuracy, explicitly distinguished from click-event accuracy;
- observation/inference/unknown label accuracy;
- extraction-fidelity, decision-validity, and outcome-validity verdicts;
- PM agreement and evidence traceability;
- task decomposition, dependency/order reasoning, branch selection, and capability choice;
- precondition/postcondition verification and Hands-result interpretation;
- recovery/replan/stop quality and held-out business-goal completion;
- transfer to alternative valid workflows and unseen conditions;
- safety violations (must be zero).

Do not substitute text fluency, generic video-QA scores, button detection, click count, or raw throughput for Brain workflow competence.

## 6. Compute and operations

- Local RTX 3070 8GB: development and video-file processing; not assumed to be the primary T4-profile training device.
- Cloud GPU: execute the configured 4B LoRA run when the approved dataset is ready.
- Record actual base revision, context length, batch, optimizer, peak VRAM, run time, dataset hash, and adapter hash.
- Keep original tutorial assets in the archive and store extraction artifacts, review decisions, samples, sidecars, and lineage separately.
- Use only local open-weight inference in the extraction/verifier path; do not send video, frames, OCR, transcript, or episodes to hosted model APIs.

## 7. Implementation snapshot

- **PR #38:** video-file extraction, DecisionEpisode construction, contract validation.
- **PR #39:** local verifier gate.
- **PR #40:** fail-closed training-sample compiler.
- **PR #41:** metadata-aware LoRA dataset preparation and T4 training configuration; no actual training run.
- **PR #42:** Brain/Hands closed-loop harness; CI uses deterministic WorkflowBrain and SimulatedHands, not real model execution.
