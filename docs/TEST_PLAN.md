# Test Plan and Quality Gates

Version: V1.1  
Applies to acquisition, tutorial understanding, action grounding, LoRA training, and expert validation.

## 1. Test layers

- Unit/contract tests: schemas, state transitions, hashing, adapter boundaries, timestamp alignment, and epistemic labels.
- Acquisition integration: cloud download to Drive, creator/series grouping, record completeness, and resume behavior.
- Prefilter tests: embedded/sidecar subtitle extraction, ASR fallback only when subtitles are absent, and tutorial/vertical classification.
- Video-understanding tests: event segmentation, action sequence, intent, UI before/after state, outcome, evidence alignment, and hallucination detection.
- Action-grounding tests: click point/target area accuracy, trajectory order, temporal alignment, and uncertainty on ambiguous actions.
- Review/storage tests: GPT first review, PM independent verification, SHA-256 deduplication, conflicts coexist, and SQLite persistence.
- LoRA training tests: immutable dataset snapshot, base revision lineage, adapter artifact checks, and reproducible loading.
- Expert evaluation: sandbox execution, GUI operation loop, unseen tasks, UI variants, recovery, and safe stop behavior.
- Performance/resource tests: source-hour processing time, GPU/VRAM/RAM, queue utilization, failure recovery, and cost after quality passes.

## 2. Labeled evaluation corpus

Build representative tutorials with PM-verified labels for:
- action steps and time intervals;
- the visible target/control and candidate coordinates;
- pre/post UI state;
- whether the click/key input is directly visible, inferred, or unknown;
- stated intent versus inferred intent;
- expected and observed result;
- important preconditions, branches, exceptions, and recovery behavior.

Include duplicate files with different names, conflicting instructions, outdated UI versions, missing subtitles, subtitle timing errors, non-tutorial clips, and tutorials outside the selected vertical.

Keep source links, platform, license/attribution, SHA-256, and model revision with every sample.

## 3. Separate model evaluations

### Video-understanding candidates: Qwen3-VL and Mage-VL

Use the same blind set and compare:
- step/action correctness and completeness;
- intent and reason accuracy;
- UI-state transition accuracy;
- outcome judgement;
- temporal localization;
- evidence support and unsupported details;
- observed/inferred classification;
- long-context consistency and robustness.

The Colab T4 16GB blind test is currently running. Do not predeclare a winner. A fluent answer or high throughput does not establish understanding quality.

### Action-grounding model: Magma

Evaluate separately:
- click point error and target-region hit rate;
- trajectory/action ordering;
- alignment to the relevant frames;
- coordinate stability under scale, scrolling, and UI movement;
- ability to express uncertainty when the historical click is not visible.

Do not combine Magma coordinate scores with Qwen3-VL/Mage-VL semantic scores in one blended score that hides task-specific failure.

## 4. Review quality

GPT first-pass checks evidence match, time/causal consistency, UI-state transition, uncertainty, and observed/inferred separation.

PM Sangou independently verifies against the original video evidence and relevant tests. No additional manual-reviewer role or queue is required. Record both decisions and reasons. Only double-pass entries are eligible for SQLite approved storage and LoRA training snapshots.

## 5. LoRA and expert behavior tests

- Training data snapshot contains only approved packages and is immutable.
- Base model revision, training parameters, GPU and adapter hash are recorded.
- 4B BF16 LoRA planning target is T4 16GB; 9B requires 24GB+.
- Test adapter loading on the 4B base and verify the expected expert identity.
- Validate the expert in Docker sandbox and GUI operation loop.
- Test multiple initial UI states, alternative menus/routes, missing controls, unexpected dialogs, partial failures, and recovery.
- Include unseen tasks that require applying learned principles rather than repeating a memorized action list.
- Confirm unsafe or unsupported actions are rejected or safely stopped.

## 6. Quality-before-throughput metrics

Freeze acceptance thresholds before blind evaluation. Record:
- operation precision/recall/order;
- intent accuracy;
- UI-state and outcome accuracy;
- action target/coordinate error;
- timestamp error;
- observed/inferred classification accuracy;
- evidence coverage and unsupported-claim rate;
- unseen-task completion and recovery success;
- safety violations (must be zero).

After quality gates pass, record videos/hour, source-hours/hour, GPU-hours, peak VRAM/RAM, per-video cost, queue wait, retries, and failure rate. Do not claim throughput without the hardware, model revision, input duration, sample policy, and quality level used.

## 7. Reports

Every test report records commit SHA, branch, test date, OS/hardware, model and adapter revision, dataset snapshot, tool versions, configuration, commands, total/pass/fail/skip, duration, measured resource use, artifacts, failure examples, and gate decision.
