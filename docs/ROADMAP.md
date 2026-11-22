# Engineering Roadmap

**Version:** 0.1 design update  
Stage order is governed by evidence and quality gates. Do not scale tutorial volume to compensate for a weak learning signal.

## Stage 0 — Source and recording baseline

**Deliverables**
- Tutorial discovery and cloud download into the 5TB Google Drive.
- Creator/series/course archive layout and one source-link/platform record per video.
- Recording profile for new tutorials with rrweb web-event capture or Windows UI Automation event capture.
- Synchronized instructor audio and source/session metadata.

**Exit criteria**
- Directly captured event records have stable timestamps, source/session references, and enough context to reconstruct UI state changes.
- Capture gaps, unsupported controls, and provider limitations are recorded rather than silently ignored.

## Stage 1 — Narration alignment and Decision Episode extraction

**Deliverables**
- Existing-subtitle-first workflow; ASR fallback only when usable subtitles are absent.
- Word- or segment-level narration alignment to the recording timeline.
- Decision Episodes joining goal, state, instructor explanation, behavioral inference, selected operation, result, and next decision.
- Evidence labels separating direct capture, legacy-video inference, instructor-explicit rationale, behavioral inference, user-provided rules, and unknown information.

**Exit criteria**
- Independent reviewers can trace each important claim to a source event or narration segment.
- The dataset does not invent spoken reasons or upgrade reconstructed video events to directly captured telemetry.
- Decision Episodes represent decision points, not just a replayable click list.

## Stage 2 — HTN workflow construction and review

**Deliverables**
- Hierarchical tasks, methods, conditional branches, hard dependencies, soft preferences, and explicit ordering constraints.
- Preconditions, postconditions, invariants, operation capabilities, transitions, and recovery rules.
- Source/tutorial/software-version/applicability scope for each workflow.
- Duplicate handling and conflict coexistence.
- Dual review and quality/trainable gates.

**Exit criteria**
- Workflow semantics survive changes in starting state and alternative valid paths.
- No conflicting tutorial or software-version workflow is silently overwritten.
- Only examples passing both gates enter the approved training snapshot.

## Stage 3 — Brain LoRA training

**Deliverables**
- Versioned Brain training dataset in conversational JSONL.
- Separate training_meta sidecar for evidence_tier and rationale_loss_weight.
- Normal-decision and error-recovery samples.
- Tutorial/course/source-level train/test split.
- Cloud LoRA training, adapter lineage, and reproducible loading.

**Exit criteria**
- Training targets contain only the Brain's next decision, not future Hands execution outcomes.
- The Brain can decompose tasks, check workflow preconditions, choose branches, select capabilities, ask for missing information, and recover from simulated Hands errors.
- Volatile workflow rules are supplied in the runtime HTN slice rather than memorized as immutable weights.

## Stage 4 — Brain-to-Hands integration and expert validation

**Deliverables**
- Versioned delegation and execution-result JSON contracts.
- Hands adapter to the existing GUI operation model (do not build a replacement operation model).
- Simulated executor for Brain-only decision testing.
- Docker sandbox and live GUI operation loop for end-to-end tests.

**Exit criteria**
- Business postconditions are verified; low-level action success alone is insufficient.
- The Brain handles success, failure, partial success, blocked, and ambiguous Hands results.
- Tests cover unseen tasks, alternative valid paths, changed UI/business states, recovery, safe stop, and unauthorized side-effect prevention.

## Stage 5 — Multiple vertical experts

**Deliverables**
- Shared base model with separate vertical LoRA adapters.
- Versioned local workflow libraries and capability registries.
- Independent held-out evaluation and controlled expert coordination.

**Exit criteria**
- Each vertical expert can be independently evaluated, upgraded, rolled back, and scoped.
- Cross-expert workflow sharing is explicit and provenance-preserving.

## Historical model experiment

The earlier Colab T4 blind comparison of Qwen3-VL-4B and Mage-VL-4B was stopped on 2026-11-21 at approximately 19:51 PST after Qwen3-VL-4B scored 4.0/25. It did not produce a validated model winner. The frame-based extraction route was rejected; the semantic event-stream plus narration route is the current design.

## Engineering management

Every implementation task must state objective, scope, model role, input/output contract, quality metrics, evidence source, tests, resource measurement, risk, and rollback plan. A merged commit or high throughput is not a quality acceptance result.
