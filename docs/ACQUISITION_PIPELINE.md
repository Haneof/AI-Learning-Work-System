# Tutorial Acquisition and Brain Learning Pipeline

## Purpose and priority

This document defines the target pipeline for converting professional tutorials into source-grounded workflow knowledge that trains a language-model Brain to direct an existing GUI operation model (the Hands).

**Quality ranks first; efficiency ranks second.** The primary learning input is a semantic UI event stream aligned with the instructor's narration. The project does not use sparse or dense frame extraction as the primary way to teach the Brain how a page or business workflow operates.

The current repository contains acquisition, media, knowledge, and GUI components, not the complete production pipeline described here. This design does not claim that direct event recording, complete narration alignment, Decision Episode extraction, Brain LoRA training, or the Brain-to-Hands runtime loop are already implemented end-to-end.

## Roles: Brain and Hands

- **Brain:** the language model plus a vertical LoRA. It learns the business goal, workflow structure, reasons, preconditions, conditional branches, operation capability selection, result verification, and recovery decisions.
- **Hands:** an existing open-source GUI operation model and adapter (for example, UI-TARS). It handles live page perception, control localization, clicking, typing, scrolling, and other low-level UI operations. Reuse this layer; do not build a replacement perception/action model as part of Brain training.
- **Event recorder:** captures what changed in the tutorial environment and when. It provides the behavioral evidence used to teach the Brain.
- **Narration processor:** aligns the instructor's words to the same timeline. It provides stated goals, reasons, constraints, and business context.

The Brain chooses what should happen and why. The Hands execute the delegated capability and return a structured result. The Brain then decides what happens next.

## Step 1 — Download and course archive

1. Search the web for tutorials in the selected target vertical.
2. Download with a cloud downloader directly into the user's 5TB Google Drive. Do not use scattered single-video folders or make the local workstation the bulk-download staging destination.
3. Organize the archive hierarchically by creator and series/course. A platform grouping may sit above the creator level, but the course structure must remain intact:

   ~~~text
   AI-Learning/
     <platform>/
       <creator>/
         <series-or-course>/
           <video-file>
   ~~~

4. Keep one download record for every video. At minimum, record the canonical source link and platform. Also retain creator, series/course, title, discovery/download time, Drive file ID/link/path, byte size, content SHA-256, and download status when available.
5. Preserve source metadata and attribution/license information where available. Unknown license metadata stays unknown; it must not be guessed.

The downloader's final archive target is Drive. The repository's current Google Drive API OAuth helper is an integration component, not proof that a cloud downloader-to-Drive production flow already exists.

## Step 2 — Capture semantic UI events and narration

### 2a. New tutorials: direct event capture is the primary path

Start event capture before the instructor begins the tutorial. Capture a semantic operation event stream rather than trying to infer every action from sampled screenshots.

For web tutorials, use an event recorder such as rrweb to retain:
- initial DOM snapshot and incremental DOM mutations;
- mouse movement/click/press/release and other interaction events supported by the recorder;
- focus and blur changes;
- scroll events;
- input and form-state changes;
- page navigation and relevant element/property changes;
- event timestamps, page/session identity, and stable node references where available.

For Windows desktop tutorials, use Windows UI Automation to retain:
- automation element identity and hierarchy;
- control type and accessible name;
- focus, structure, property, and supported control events;
- relevant enabled/disabled, expanded/collapsed, selected, value, and other state changes;
- event timestamps, application/window identity, and provider limitations.

Capture the instructor's original audio on the same session clock or preserve synchronization metadata. The recorder must report missing events and unsupported UI providers rather than silently pretending the event stream is complete.

### 2b. Existing subtitles and narration alignment

1. Inspect embedded subtitle tracks and associated subtitle files.
2. Prefer existing subtitles and preserve their source, language, and timecodes.
3. Only when usable subtitles are unavailable, run ASR on the original audio.
4. Align the transcript to the audio. Prefer word-level timestamps when the aligner supports the language and the result is reliable; otherwise retain segment-level timestamps and mark the time granularity.
5. Keep instructor-explicit statements separate from behavioral inference. A transcript records what the instructor said; it does not automatically prove that the statement is a universally correct business rule.

The narration provides the goal, motivation, explanation, conditions, constraints, and domain knowledge. UI events provide the observed behavior and state changes. Neither channel is sufficient alone; they must be aligned.

### 2c. Legacy MP4 tutorials: fallback reconstruction only

A prerecorded MP4 normally does not contain its original DOM tree, Accessibility tree, Windows UI Automation stream, or actual mouse/keyboard events. For legacy recordings only, reconstruct the limited UI events that can be supported by reviewing the recording and aligning those observations with narration.

- Mark reconstructed events as inferred_from_video.
- Never represent a reconstructed click, key press, or hidden state change as directly captured telemetry.
- Leave actions that cannot be established from the recording as unknown.
- Keep the recording time range and the basis for each inference.
- Do not promote frame-derived guesses into observed events.

This is a compatibility path for historical material, not the default collection architecture. Sparse or dense frame extraction is not the primary learning method.

## Step 3 — Build Decision Episodes and workflows

The minimal learning unit is a **Decision Episode**, not a simple chronological list of clicks. It represents:

**goal at the time → known business/UI situation → stated or inferred reason → selected strategy → delegated operation → observed result → next decision.**

Each episode should preserve:
- the task goal and success criteria;
- the current business state and facts available at that decision point;
- relevant conditions, constraints, and known unknowns;
- instructor narration segments and their time ranges;
- the instructor's explicit reason, separately from behavioral/model inference;
- the selected next decision and the operation capability to delegate;
- operation status and evidence-backed postcondition checks;
- the next step, branch, recovery, question, approval request, or stop decision;
- evidence provenance, observation channel, rationale source, and confidence.

Compose episodes into versioned HTN workflows with compound/primitive tasks, methods, conditional branches, hard dependencies, soft preferences, explicit ordering constraints, invariants, postconditions, operation capability IDs, and recovery rules.

Do not assume that the instructor's demonstrated path is the only valid path. A tutorial may show only one successful route. Preserve alternative methods, scope, software version, applicability conditions, and conflicting sources.

## Step 4 — Deduplicate, review, and store

1. Deduplicate exact source content by SHA-256 while retaining every acquisition record.
2. Keep conflicting workflow claims from different tutorials, software versions, and conditions side by side. Never overwrite a conflicting statement, workflow, or evidence trail.
3. The first review checks:
   - every business fact and decision rationale has traceable evidence;
   - instructor words, directly captured events, and behavioral inference are not conflated;
   - event order and narration alignment are consistent;
   - preconditions and postconditions match the evidence;
   - no hidden click, key press, or business result is fabricated;
   - uncertainty and conflicts are retained.
4. PM Sangou independently verifies the candidate against its source tutorial and relevant tests. There is no separate outside manual-review queue; the two required project gates are the first review and PM verification.
5. Only items that pass both the review approval switch and the quality/trainable gate enter the approved SQLite store and formal Brain training dataset.

Rejected or unresolved items remain traceable with their review status and reasons but are excluded from the approved training snapshot.

## Step 5 — Build training samples and train the Brain

1. Generate conversational JSONL samples with system/user/assistant messages. The input contains the goal, current state, relevant local HTN workflow slice, available capabilities, and any prior Hands result known at that decision point.
2. Generate normal-decision and error-recovery examples. For recovery, put the prior Hands response in the user input. The assistant target predicts the Brain's next decision and must stop before the future execution outcome.
3. Keep evidence_tier and rationale_loss_weight in a separate training_meta sidecar; these fields are metadata and are never fed to the model.
4. Split by tutorial/course/source group so fragments and near-duplicates from one tutorial never cross train/test partitions.
5. Train the vertical Brain LoRA on a cloud GPU. Current capacity-planning assumption: 4B BF16 LoRA on a 16GB T4; 9B planning requires a 24GB-or-larger GPU. Confirm the exact base revision, context, batch, optimizer, checkpointing, and peak VRAM in the actual training run.
6. At runtime, pass the relevant local HTN workflow slice to the Brain. Updating volatile workflow rules in that data should not require retraining the LoRA.

## Step 6 — Brain-to-Hands integration and expert validation

The Brain sends a high-level delegation JSON with an objective, capability ID, arguments, preconditions, constraints, expected postconditions, and observation requirements. A Hands adapter maps the capability to the existing GUI operation model. Hands returns a structured status, observed state, postcondition results, error category, and evidence references.

The Brain must reason over the return and select the next action. A successful tool call or click is not proof of business success. Test:
- goal decomposition and workflow planning;
- correct method and branch selection under changed state;
- prerequisite and invariant enforcement;
- interpretation of successful, failed, partial, blocked, and ambiguous Hands results;
- asking for missing information and requesting approval;
- recovery, replan, and safe stop;
- alternative valid paths and unseen business conditions.

The skill-package compiler and Docker sandbox are validation harnesses. They are not the final product and do not replace the trained Brain or the existing Hands model.

## Historical model experiment status

The earlier Colab T4 blind comparison of Qwen3-VL-4B and Mage-VL-4B was stopped on 2026-11-21 at approximately 19:51 PST after Qwen3-VL-4B scored 4.0/25. The comparison was not completed as a valid winner-selection benchmark. No winner is claimed. The frame-based extraction route was rejected as the primary tutorial-learning method; the semantic UI event stream plus instructor narration is the current design.

## Storage and provenance

- Original tutorial videos and course groupings live in Google Drive.
- Download records link each item to source URL, platform, creator, series, Drive location, and content hash.
- Event records retain the source/session ID, event type, target/element reference, timestamps, before/after values where available, and capture method.
- Narration records retain transcript text, language, alignment method, word/segment times, and source audio references.
- Decision Episodes and workflow versions reference the event and narration evidence they use.
- SQLite stores structured source metadata, event records, narration segments, decisions, workflows, conflicts, reviews, and training-dataset membership.
- Legacy MP4 reconstruction retains its source time range and inferred_from_video provenance.
- Failed, rejected, and superseded records remain traceable but are excluded from approved training snapshots.

## Current implementation boundary

The repository contains an acquisition prototype, Google Drive API storage code, FFmpeg media utilities, ASR/OCR Protocol interfaces and static adapters, knowledge/evidence components, skill compilation/validation, and GUI operation infrastructure. Static ASR/OCR adapters are test fixtures; they do not perform real transcription or recognition. Existing FFmpeg frame extraction is a media utility and a legacy compatibility aid, not the selected tutorial-learning path. The direct rrweb/Windows UIA event recorder, aligned narration pipeline, Decision Episode extractor, workflow learner, and Brain LoRA training/runtime integration remain implementation gaps.
