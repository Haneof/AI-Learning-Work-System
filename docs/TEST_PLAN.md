# Test Plan and Quality Gates

**Version:** 0.1 design update  
Applies to tutorial acquisition, event capture, narration alignment, Decision Episode extraction, workflow learning, Brain LoRA training, and Brain-to-Hands validation.

## 1. Test layers

- Unit/contract tests: schemas, references, timestamp ranges, provenance labels, semantic conditions, state transitions, and adapter boundaries.
- Acquisition integration: cloud download to Drive, creator/series grouping, source record completeness, content hashing, and resume behavior.
- Event-capture integration: rrweb web events, Windows UI Automation events, capture gaps, timestamps, target identity, and before/after state changes.
- Narration tests: subtitle extraction, ASR fallback only when subtitles are absent, transcript provenance, word/segment alignment, language support, and uncertain timing.
- Decision Episode tests: event/narration correlation, decision-time state, instructor-explicit rationale, behavioral inference, selected next decision, outcome evidence, and no future-information leakage.
- Workflow tests: HTN decomposition, method applicability, hard dependencies, soft preferences, ordering constraints, invariants, conditional branches, and recovery paths.
- Brain training-data tests: conversational JSONL, separate training_meta sidecar, normal-decision and error-recovery cases, review/quality gates, and source-grouped train/test split.
- Brain-only evaluation: task decomposition, sequence selection, guard checks, strategy choice, capability selection, ask/approval/stop decisions, and interpretation of simulated Hands responses.
- Brain-to-Hands integration: delegation schema, registered capability IDs, execution-result schema, postcondition verification, retry/idempotency, and error/recovery handling.
- Expert evaluation: sandbox execution, live GUI operation loop, unseen tasks, alternative workflows, changed initial states, and safe stop behavior.
- Performance/resource tests: event capture overhead, alignment cost, extraction/review latency, LoRA GPU/VRAM, queue utilization, and runtime delegation reliability after quality passes.

## 2. Labeled evaluation corpus

Build representative tutorials with PM-verified labels for:
- business goal and success criteria;
- UI event sequence and page/control state changes;
- narration segments and explicitly spoken reasons;
- task ordering, preconditions, branches, and constraints;
- selected operation capability and expected postconditions;
- Hands execution feedback, failure category, and recovery choice;
- direct-capture versus inferred-from-video observation channel;
- instructor-explicit versus behavioral-inference rationale source;
- applicable software version and task conditions.

Include duplicate downloads, conflicting tutorials, outdated application versions, missing subtitles, subtitle timing errors, missing/partial event streams, unsupported Windows UIA providers, non-tutorial content, and tutorials outside the selected vertical.

Keep source links, platform, license/attribution, SHA-256, course/tutorial grouping, recorder version, and software version with every sample.

For legacy MP4 material, any reconstructed interaction is labelled inferred_from_video. It must not be used as a direct-capture event ground truth.

## 3. Separate model evaluations

### Brain decision model

Evaluate the Brain with a simulated Hands executor first. Measure:
- task decomposition and subgoal coverage;
- hard dependency and ordering correctness;
- method/branch selection under changed state;
- rationale fidelity and provenance attribution;
- precondition/invariant enforcement;
- capability choice and delegation scope;
- postcondition verification decisions;
- handling of success, failure, partial success, blocked, and ambiguous Hands results;
- ask_user, request_approval, replan, finish, and stop decisions;
- transfer to alternative valid workflows and unseen conditions.

### Existing Hands operation model

Evaluate the existing Hands model separately for:
- page observation and control interaction;
- completion of the delegated capability;
- returned status and observed state accuracy;
- evidence-backed postcondition checks;
- safe handling of permission, validation, timeout, and ambiguous-state errors.

This project reuses the Hands operation model. It does not train a new button detector or low-level mouse-control model as the Brain learning target.

## 4. Historical Qwen/Mage experiment status

The earlier Qwen3-VL-4B vs Mage-VL-4B blind test on Colab T4 was stopped on 2026-11-21 at approximately 19:51 PST after Qwen3-VL-4B scored 4.0/25. It was not completed as a validated winner-selection benchmark. No winner is declared. Frame-based extraction is not the selected workflow-learning route.

## 5. Review quality

The first review checks evidence resolution, event/narration alignment, decision-time information, conditions, workflow consistency, uncertainty, and provenance labels.

PM Sangou independently verifies against the original tutorial/event evidence and relevant tests. No additional external manual-reviewer role or queue is required. Record both decisions and reasons. Only double-pass examples with quality/trainable approval are eligible for SQLite approved storage and Brain LoRA dataset snapshots.

## 6. Brain LoRA and behavior tests

- Training snapshot contains only approved Decision Episodes and eligible training examples; it is immutable.
- Base model revision, workflow versions, dataset hash, training parameters, GPU, and adapter hash are recorded.
- Test adapter loading on the designated Brain base.
- Supply the local HTN workflow slice at runtime and test that a workflow rule can be updated without changing LoRA weights.
- Use normal-decision examples and error-recovery examples. A prior Hands result appears in the user input for recovery; it must not leak into an earlier decision target.
- Test changed initial states, alternative menus/routes, missing information, unexpected results, partial failures, and recovery.
- Include unseen tasks that require applying learned workflow principles rather than repeating a memorized path.
- Confirm unsafe or unsupported actions are rejected, escalated, or safely stopped.

## 7. Quality-before-throughput metrics

Freeze acceptance thresholds before held-out evaluation. Record:
- decision correctness by decision type;
- task decomposition and dependency/order correctness;
- branch and method selection accuracy;
- instructor-rationale fidelity and evidence attribution;
- precondition/postcondition verification accuracy;
- capability delegation correctness;
- Hands result interpretation;
- recovery and replan quality;
- held-out business-goal completion and transfer to new conditions;
- evidence coverage and unsupported-claim rate;
- direct-capture/inferred-from-video and instructor-explicit/behavioral-inference label accuracy;
- safety violations (must be zero).

After quality gates pass, record processing time, event volume, ASR/alignment cost, GPU-hours, peak VRAM/RAM, per-tutorial cost, queue wait, retries, and failure rate. Do not claim throughput without the hardware, model revision, input duration, capture source, and quality level used.

## 8. Reports

Every test report records commit SHA, branch, test date, OS/hardware, model/adapter revision, workflow versions, dataset snapshot, tool versions, configuration, commands, total/pass/fail/skip, duration, measured resource use, artifacts, failure examples, and gate decision.
