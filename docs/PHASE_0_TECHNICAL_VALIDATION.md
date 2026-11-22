# Phase 0: Technical Validation Plan

**Version:** 0.1 design update  
**Status:** validation baseline; a real-tutorial end-to-end audit is still required  
**Priority:** prove that tutorials teach transferable workflow decisions to the Brain before optimizing throughput.

## 1. Phase objective

Validate a minimal vertical slice that converts a tutorial's semantic UI event stream and instructor narration into workflow decision supervision, trains or evaluates a Brain model, and verifies that the Brain can direct an existing Hands operation model.

The target slice is:

1. Acquire licensed tutorials and preserve their source/course metadata.
2. For new recordings, capture timestamped semantic UI events directly: rrweb for web applications and Windows UI Automation for Windows desktop applications.
3. Preserve the original instructor audio. Prefer supplied subtitles; use ASR only when usable subtitles are unavailable, then align the transcript to the audio with word- or segment-level timestamps.
4. Align UI events and narration into Decision Episodes: goal, current business state, reason, chosen strategy, delegated operation, verified result, and next decision.
5. Build HTN workflows with conditional branches, hard dependencies, soft preferences, preconditions, postconditions, and recovery paths.
6. Review evidence and annotations, create Brain LoRA training examples without leaking future execution outcomes, and preserve a separate training-metadata sidecar.
7. Train/evaluate the Brain and connect it to the existing Hands model through a versioned delegation/result protocol.
8. Test changed initial states, alternative paths, Hands failures, and unseen tasks in a sandbox.

A transcript, UI event dump, video summary, button recognition result, or replay of one fixed click sequence does not constitute successful learning.

## 2. Scope and architecture boundaries

### Brain — the learning target

The Brain is the language model plus a vertical LoRA. It must learn:
- decomposition of a business goal into subgoals;
- task ordering and dependencies;
- condition and branch selection;
- the purpose and constraints behind business actions;
- selecting an available operation capability;
- verifying postconditions from Hands feedback;
- diagnosing failures, recovering, replanning, asking the user, requesting approval, or stopping;
- applying the learned workflow principles to different starting states and valid alternative paths.

### Hands — reused execution infrastructure

The Hands model is an existing open-source GUI operation model (for example, UI-TARS) and its adapter. It handles live page perception, UI element localization, and low-level operation. Building a replacement page-recognition or mouse-control model is outside this phase. The Brain delegates high-level capability requests; the Hands adapter maps them to the operation model and returns structured results.

### Tutorial evidence input

The primary input for new tutorials is the semantic UI event stream plus the instructor's voice narration. No sparse- or dense-frame extraction pipeline is planned as the primary learning path.

Legacy MP4 tutorials may be reconstructed when direct recording telemetry does not exist. Any reconstructed mouse/UI event must be labelled as inferred from video and must not be upgraded to directly captured evidence.

## 3. Work packages and sequence

### WP0 — Recording and source baseline

- Define a recording profile that starts event capture before the tutorial begins.
- Capture rrweb events for web tutorials, including DOM changes, interaction events, focus, scrolling, input state changes, and timestamps.
- Capture Windows UI Automation events and element state changes for desktop tutorials.
- Keep stable source/session IDs, application/software version, event timestamps, and source hashes.
- Record instructor audio on the same session clock or preserve synchronization metadata.
- Retain the original tutorial and all source metadata in the creator/course archive.

**Exit:** a new tutorial recording has a complete, timestamped event stream, original audio, source/session metadata, and a reproducible synchronization reference. Event gaps and unsupported controls are explicit.

### WP1 — Narration transcription and alignment

- Extract existing subtitles first and preserve their language and timecodes.
- Run ASR only when usable subtitles are unavailable.
- Align the transcript to the original audio. Preserve word-level timestamps when reliable, otherwise retain segment-level timestamps and mark the granularity.
- Distinguish instructor-explicit reasons and rules from behavioral inference.
- Do not convert narration into an approved business rule solely because the instructor said it; keep provenance and review state.

**Exit:** the narration is time-aligned to the event stream, and every explanatory claim can be traced to an audio/transcript segment.

### WP2 — Decision Episode and HTN workflow extraction

- Align page/navigation changes, control state changes, mouse/input events, and narration on one timeline.
- Extract episodes that contain the task goal, state known at the decision point, relevant conditions, instructor rationale, chosen operation, resulting state, and next decision.
- Separate directly captured events, legacy-video inferences, instructor-explicit rationale, behavioral inference, project-owner-provided rules, and unknowns.
- Compile episodes into HTN workflows and conditional graphs. Preserve alternative methods, hard dependencies, soft preferences, workflow applicability, software version, and recovery rules.
- Never assume the instructor's demonstrated path is the only valid path.

**Exit:** representative episodes and workflows are independently reviewable and preserve their evidence, conditions, uncertainties, and source/tutorial grouping.

### WP3 — Review, quality gates, and training data

- Deduplicate exact source content by SHA-256 while retaining every acquisition record.
- Preserve conflicts from different tutorials, application versions, and applicability conditions; do not overwrite.
- Require the agreed review approval switch and quality/trainable gate before formal training.
- Generate conversational JSONL examples with system/user/assistant messages. Keep evidence tier and rationale loss-weight metadata in a separate sidecar, never in the model input.
- Produce normal-decision and error-recovery examples. For recovery, place the prior Hands result in the user input; the assistant target must stop before the future execution outcome.
- Split by tutorial/course/source group so near-duplicate fragments cannot cross train and test partitions.

**Exit:** an auditable dataset snapshot contains only eligible examples, with provenance and leakage checks.

### WP4 — Brain LoRA training and standalone decision evaluation

- Use a fixed base-model revision and a versioned workflow-training dataset.
- Train the first vertical Brain LoRA on cloud GPU. Current capacity planning assumes 4B BF16 LoRA on a T4 16GB; 9B planning requires 24GB+ GPU. These are assumptions until verified with actual training logs.
- Provide the relevant local HTN workflow slice in the runtime prompt so volatile business rules can be updated in workflow data without retraining the LoRA.
- Evaluate the Brain with a simulated Hands executor before connecting a live operation model.
- Test task decomposition, branch selection, precondition checks, capability selection, asking for missing inputs, safe stop, and recovery from success/failure/partial-success/blocked/ambiguous Hands results.

**Exit:** the Brain chooses correct next decisions under controlled state variations, without needing to perform button recognition itself.

### WP5 — Brain-to-Hands integration and expert validation

- Connect the Brain to the existing Hands model through the versioned delegation/result contract.
- Require each delegation to include objective, capability, arguments, constraints, expected postconditions, and observation requirements.
- Require Hands to return a structured status, observed state, postcondition checks, error category, and evidence references.
- Verify business postconditions rather than accepting a successful click or tool call as proof.
- Use the Docker sandbox and GUI operation loop to test realistic tasks, alternative paths, failures, recovery, and safe stop behavior.

**Exit:** the end-to-end Brain + existing Hands pair completes or safely stops unseen variations and records why.

## 4. Quality gates

Freeze thresholds before a held-out evaluation. At minimum measure:

- decision accuracy at each decision point;
- task decomposition and dependency/order correctness;
- conditional branch selection under changed initial states;
- business-rationale fidelity and provenance correctness;
- precondition and postcondition verification accuracy;
- capability selection and safe delegation;
- Hands result interpretation;
- error diagnosis, recovery, replan, and stop decisions;
- successful completion of held-out business goals;
- transfer to alternative valid workflows and unseen conditions;
- evidence coverage, unsupported-claim rate, and direct/inferred label accuracy;
- safety violations (must be zero).

Do not substitute text fluency, video QA scores, button detection accuracy, or raw throughput for Brain workflow competence.

## 5. Historical tutorial handling

For legacy MP4 files without direct UI telemetry:
- retain the original video and narration;
- reconstruct only events supported by the recording;
- mark reconstructed event observations as inferred_from_video;
- mark instructor words separately from behavior-based rationale inference;
- leave hidden clicks, keyboard events, and ambiguous state changes unknown;
- use frame inspection only as a fallback for human/model reconstruction, not as the primary training input route.

## 6. Compute and operations

- Local RTX 3070 8GB: development and lightweight processing; not assumed to be the primary 4B BF16 LoRA trainer.
- Cloud GPU: LoRA training and heavier validation.
- T4 16GB for 4B BF16 LoRA and 24GB+ for 9B are planning assumptions. Record actual model revision, context length, batch, optimizer, peak VRAM, and run time.
- Keep original tutorial assets in Google Drive; store event/narration metadata, decisions, workflows, reviews, and dataset lineage in SQLite or the versioned structured store.
- Measure cost and throughput only after the quality thresholds are met.

## 7. Historical model experiment status

The earlier Qwen3-VL-4B vs Mage-VL-4B blind test on Colab T4 was stopped on 2026-11-21 at approximately 19:51 PST after Qwen3-VL-4B scored 4.0/25. The comparison was not completed as a validated winner-selection benchmark. The frame-based extraction route was rejected as the primary tutorial-learning method; the event-stream plus narration route is the current design.
