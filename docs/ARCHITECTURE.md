# System Architecture

## Product architecture: Brain and Hands

The system's product is a domain expert: a language-model base with a vertical LoRA that learns business workflow decisions. The **Brain** reasons about goals, state, constraints, task order, branches, capability choice, verification, and recovery. The **Hands** are an existing GUI operation model and adapter that perceive the live page and perform low-level interactions.

- **Brain:** interprets a business goal, uses a versioned workflow slice, chooses what should happen next and why, delegates a high-level capability, and reacts to the verified result.
- **Hands:** identifies live page controls and performs concrete UI operations such as click, type, scroll, and navigation. Reuse an operation model (for example, UI-TARS) rather than training a duplicate perception/action model as part of Brain learning.
- **Video-file extraction:** processes downloaded tutorial files offline and converts transcript, visible screen changes, OCR, and inferred cursor/target hypotheses into evidence for DecisionEpisodes.
- **Local verifier and PM gate:** checks the episode's evidence and decision quality before any training admission.
- **Training compiler and LoRA setup:** converts only approved decision points into model-facing samples and prepares the configured Brain LoRA training data.

A transcript, summary, or fixed click sequence is not the product. The target is a Brain that can select a suitable workflow path and direct the Hands to accomplish the business objective.

## Current learning and runtime data flow

1. **Acquire video files:** download source tutorials and available subtitle files; preserve source URL, platform, attribution/license, course grouping, and content hash.
2. **Extract from the local file (PR #38):**
   - prefer usable SRT/WebVTT captions; use local faster-whisper ASR only when no usable timed subtitles are available;
   - use FFmpeg to decode sampled frames from the downloaded file;
   - use pixel-difference screen-change detection to select initial/changed frames;
   - OCR selected visual states; infer cursor/possible-click candidates and ground UI targets on selected changed frames;
   - align timestamped transcript segments to visual events and produce a structured DecisionEpisode;
   - validate the episode with the versioned schema and semantic validator.
3. **Apply the local verifier gate (PR #39):** independently score extraction fidelity, decision validity, and outcome validity. All three must pass. A local pass is not enough for training admission; PM independent review and cited evidence are also required.
4. **Compile approved decision points (PR #40):** fail closed on missing/failed local verification, PM review, annotation approval, or quality/trainable flags. Emit conversational samples, source-grouped train/test splits, and separate training-metadata sidecars.
5. **Prepare the Brain LoRA (PR #41):** metadata-aware train/test preparation and configuration validation for the Qwen3 4B Brain LoRA profile. A training setup is present; a trained adapter is not thereby produced.
6. **Operate through Brain and Hands (PR #42):** the Brain emits a typed high-level delegation; Hands returns a correlated result; the loop observes fresh state, verifies postconditions, and replans/recoveries on failure or uncertainty.

The extractor, verifier, compiler, training setup, and Brain/Hands harness are separate repository components. Their presence does not mean there is a deployed end-to-end service, a trained Brain adapter, or a real Hands model run.

## Superseded live-recorder route — cancelled 2026-11-21

The earlier proposal to capture rrweb events from live web tutorials and Windows UI Automation events from live desktop tutorials was **cancelled on 2026-11-21**. It was superseded by the downloaded-video-file route because the selected workflow can process tutorial files already available for download without installing a recorder into each target application/session or synchronizing a live event-collection channel. This event-stream route remains historical design context, not an active ingestion path or required fallback.

Frame extraction is part of the selected route, but it is frame-change-driven and evidence-combined—not a blind screenshot-only action log. The video contains no native mouse/keyboard/DOM/UIA telemetry. Cursor/click and UI target candidates inferred from pixels remain labelled `inferred_from_video`.

## Runtime Brain-to-Hands loop

1. The user or calling system supplies a business goal and current known state.
2. The Brain loads the applicable local HTN workflow slice and registered operation capabilities.
3. The Brain checks preconditions and selects the next business subtask or asks for missing information/approval.
4. For an executable operation, the Brain emits a high-level delegation containing objective, capability ID, arguments, constraints, expected postconditions, and observation requirements.
5. The Hands adapter maps the capability to the existing operation model and performs page interaction.
6. Hands returns status, observed state, per-postcondition results, error category, and evidence references.
7. The loop obtains a fresh state observation and independently checks postconditions before allowing progress. Failed, partial, stale, or uncertain results return to Brain for re-planning/recovery; a successful click alone is not business success.

PR #42's current CI acceptance uses a deterministic `WorkflowBrain` stand-in and `SimulatedHands`. `BrowserAgentHandsAdapter` bridges the same protocol to the existing BrowserAgent, but requires a domain-specific fresh business-state observer. No real Brain LoRA adapter or real UI-TARS-class operation model was run for that PR.

## Workflow representation

Use a hierarchical task network (HTN) for compound/primitive task decomposition and a conditional graph for branches and transitions. Distinguish hard dependencies from soft preferences. Explicit ordering constraints and invariants represent non-bypassable requirements. Primitive tasks map to registered capability IDs. Recovery rules describe diagnosis, retry conditions, replan, approval, and safe stop.

Volatile business rules remain in versioned workflow data and are supplied locally at runtime. The LoRA learns how to reason over workflow data; it should not have to memorize every changing business rule in its weights.

## Evidence and provenance

For every decision-driving fact, retain:
- source tutorial/file identity, content hash, and timestamp range;
- decoded visual frame and screen-change references;
- visible OCR text and bounding boxes;
- timestamped subtitle/ASR segment IDs and transcript method;
- observation channel: `observed_from_video`, `inferred_from_video`, or unknown as applicable;
- rationale source: instructor-explicit, behavioral inference, hybrid, not applicable, or unknown;
- confidence, explicit unknowns, and conflicting interpretations;
- workflow source, software version, and applicability.

A downloaded video can directly support claims about visible pixels and recorded speech. It cannot establish hidden clicks, key presses, DOM mutations, or that an operation actually executed. Do not relabel an inferred action as direct event telemetry. An instructor quote records what was said, not an automatically verified universal business rule.

## Layered services and milestone mapping

- **Acquisition:** discovery, downloading tutorial files/subtitles, source/course records, archive metadata.
- **Video-file extraction (#38):** subtitle/ASR, FFmpeg sampling, screen-change detection, OCR, cursor/click hypotheses, local UI grounding, narration alignment, DecisionEpisode construction, contract validation.
- **Local verification (#39):** extraction-fidelity, decision-validity, and outcome-validity verdicts with evidence references and unknowns; PM review remains a separate gate.
- **Training-sample compiler (#40):** dual-gate and quality admission, decision-point sample creation, grouped splits, sidecar and manifest generation.
- **Brain LoRA setup (#41):** metadata-aware dataset preparation and a validated Axolotl configuration; not a completed training run.
- **Brain/Hands (#42):** typed protocols, workflow-driven test Brain, simulated Hands, state/postcondition checks, and BrowserAgent adapter.
- **Validation harness:** unit/contract tests, simulated business-state tests, local model harnesses, sandbox and GUI execution tests.

The implementation can remain a modular monolith with worker processes; do not turn every logical boundary into a microservice prematurely.

## Storage

- **Video archive:** original tutorial files, supplied subtitles, source URL, platform, creator/course, attribution/license, and content hash.
- **Extraction artifacts:** transcript, sampled frames, screen-change metadata, OCR, cursor/target hypotheses, narration alignment, source evidence, proposed DecisionEpisode, and validation/verifier reports.
- **Training artifacts:** approved review bundles, conversational JSONL, sidecar metadata, source-grouped split manifest, dataset snapshot, training configuration, run logs, and adapter lineage.
- **Runtime artifacts:** workflow definitions, capability registry, Brain decision history, Hands result, fresh state observations, postcondition evidence, and execution trace.
- **Git:** source, contracts, documentation, and tests; never commit tutorial videos, secrets, or model weights.

## Compute and experiment status

The extraction path uses local open-weight inference. It does not send video, frame, OCR, transcript, or episode content to GPT, Gemini, or hosted model APIs. Model-weight downloads, when permitted by the documented measured escalation gates, are separate from inference.

The earlier Qwen3-VL-4B vs Mage-VL-4B Colab T4 blind test was stopped on 2026-11-21 at approximately 19:51 PST after Qwen3-VL-4B scored 4.0/25. It was not a completed winner-selection benchmark; no winner was selected. That experiment did not reject frame extraction. The selected path is the downloaded-video, frame-change-driven extraction route.

## Implementation boundary

- PR #38 provides the video-file extraction, DecisionEpisode builder, and contract validation.
- PR #39 adds the local verifier gate. A separate PM evidence-linked PASS is still required.
- PR #40 adds the fail-closed DecisionEpisode-to-training-sample compiler.
- PR #41 adds the Brain LoRA dataset preparation and training configuration. No trained adapter is implied.
- PR #42 adds the Brain/Hands protocol and loop. Its passing CI uses a deterministic Brain stand-in and SimulatedHands; the real operation-model harness is documented, not executed.

The code milestones are merged and tested, but the real-world end-to-end expert still needs eligible PM-approved training data, an actual LoRA run, and real Hands evaluation.
