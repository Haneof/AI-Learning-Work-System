# Test Plan and Quality Gates

**Version:** 0.2, aligned with merged PRs #38–#42  
Applies to downloaded tutorial video acquisition/extraction, DecisionEpisode validation and verification, training-sample compilation, Brain LoRA preparation, and Brain-to-Hands validation.

## 1. Test layers

- **Acquisition integration:** video-file download, subtitle retrieval, source/license metadata, source hashing, archive grouping, resume behavior, and corrupt/unsupported file handling.
- **Video-file extraction:** SRT/WebVTT preference, local ASR fallback only when subtitles are unavailable, segment timestamps, FFmpeg frame sampling, pixel-difference change detection, initial/changed-frame selection, OCR output, and per-stage artifacts.
- **Visual inference:** cursor candidate tracking, click-hypothesis generation, local GUI target grounding, target-box accuracy, fallback model gates, and confidence/provenance. Do not score these as native click-event accuracy.
- **Narration alignment:** subtitle/ASR time validity, transcript provenance, language handling, and alignment of narration segments with timestamped screen changes.
- **DecisionEpisode tests:** episode construction, source evidence links, decision-time state, instructor-explicit rationale, behavioral inference, selected next decision, outcome evidence, unknown preservation, and no future-information leakage.
- **Contract and local-verifier tests:** schema/semantic validation, evidence-reference resolution, extraction-fidelity/decision-validity/outcome-validity verdicts, pass/fail/unknown handling, and fail-closed behavior.
- **Independent PM gate:** original-source review, proposed-episode inspection, cited source and record refs, and explicit PASS/REJECT/NEEDS_EVIDENCE.
- **Training-sample compiler:** local gate and PM gate enforcement, annotation/quality flags, one sample per decision point, source-grouped train/test partitioning, sidecar alignment, and exclusion manifest.
- **Brain LoRA preparation:** unique sample IDs, aligned sidecars, partition validation, bounded evidence-aware weighting, unchanged test split, Axolotl config validation, and chat-template tokenization.
- **Brain-only evaluation:** task decomposition, sequence selection, guard checks, branch choice, strategy/capability selection, ask/approval/stop decisions, and interpretation of simulated Hands responses.
- **Brain-to-Hands integration:** delegation schema, registered capability IDs, result correlation, fresh state observation, postcondition verification, retry/idempotency, and failure/partial/uncertain recovery.
- **Runtime GUI/Hands tests:** live page observations, operation model actions, state observer correctness, trace integrity, controlled app restrictions, and safe side-effect handling. These are execution-time Hands tests, not tutorial-ingestion event capture.
- **Performance/resource tests:** download reliability, subtitle/ASR cost, frame sampling and change detection, OCR/grounding latency, local verifier cost, compiler runtime, LoRA GPU/VRAM, and runtime delegation reliability after quality gates pass.

## 2. Video-file evaluation corpus

Build representative downloaded tutorials with PM-verified labels for:
- task goal and success criteria;
- video source ID/hash, duration, attribution/license, and subtitle provenance;
- transcript segments and time ranges;
- initial and changed screen states, OCR text/boxes, and screen-change timestamps;
- cursor candidates and inferred target/action hypotheses;
- instructor-explicit reasons and separately labelled behavioral inference;
- decision-time state, chosen strategy, next decision, and uncertainty;
- independent operation/outcome evidence when available;
- applicable software version and task conditions.

Include duplicate downloads, conflicting tutorials, outdated software versions, missing/invalid subtitles, ASR timing errors, silent or corrupted video, static/no-change scenes, high-motion scenes, low-quality OCR, cursor false positives, UI-grounding misses, non-tutorial content, and tutorials outside the selected vertical.

Any inferred click/interaction is labelled `inferred_from_video`. It must not be used as a direct-capture ground truth label. Keep any runtime Hands GUI traces in a separate corpus with clear source and role metadata.

## 3. Separate model evaluations

### Video extraction and local verifier

Evaluate:
- transcript extraction validity and time alignment;
- screen-change precision/recall against annotated visual changes;
- OCR text/box usefulness and error rate;
- cursor/click candidate precision and recall as hypotheses;
- UI target-box hit rate, explicitly not click-event accuracy;
- DecisionEpisode evidence coverage and unsupported-claim rate;
- local extraction-fidelity, decision-validity, and outcome-validity verdicts;
- correct handling of unknown/missing evidence and invalid references.

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

The project reuses the Hands operation model. It does not train a new button detector or low-level mouse-control model as the Brain learning target.

## 4. Historical route and model experiment status

The proposed live tutorial recorder/event collector (rrweb for web sessions and Windows UI Automation for desktop sessions) was cancelled on **2026-11-21** and superseded by downloaded-video-file extraction. It is retained as historical context only, not as a primary or required fallback ingestion path.

The earlier Qwen3-VL-4B vs Mage-VL-4B blind test on Colab T4 was stopped on 2026-11-21 at approximately 19:51 PST after Qwen3-VL-4B scored 4.0/25. It was not completed as a validated winner-selection benchmark; no winner is declared. This experiment did not reject frame extraction. The selected route uses frame-change-driven extraction with subtitle/ASR, OCR, cursor/UI-target inference, and verification.

## 5. Review quality and training admission

The local verifier independently scores extraction fidelity, decision validity, and outcome validity. All three levels must pass. Missing evidence, invalid references, malformed output, or unresolved claims remain held/unknown.

The PM independently checks the original tutorial file and proposed DecisionEpisode, and records a PASS with references to the source evidence and reviewed episode claims. Local PASS alone does not admit an episode.

Only bundles that pass both verification gates and the compiler's episode review/quality/trainable checks may produce model-facing training samples. Keep the training metadata sidecar separate from the model messages. No future Hands result may leak into an earlier Brain decision target.

## 6. Brain LoRA preparation and behavior tests

- Validate train/test JSONL against matching 'training_meta' sidecars; reject missing/misaligned/duplicate metadata and explicitly excluded rows.
- Ensure source-grouped train/test split integrity and preserve the held-out test records without training-row weighting.
- Validate the T4 Axolotl LoRA config before downloading model weights.
- For a real training run, record base revision, dataset snapshot hash, context length, batch, gradient accumulation, optimizer, precision, checkpointing, GPU model/VRAM, peak memory, wall time, metrics, and adapter hash.
- Use normal-decision examples and error-recovery examples. A prior Hands result appears in user input for recovery; it must not leak into an earlier decision target.
- Test changed initial states, alternative menus/routes, missing information, unexpected results, partial failures, and recovery.
- Include unseen tasks that require applying workflow principles rather than repeating a memorized path.
- Confirm unsafe or unsupported actions are rejected, escalated, or safely stopped.

PR #41 delivered data preparation/config validation and synthetic smoke tests, not an actual training run or adapter. Do not treat configuration validation as model-training acceptance.

## 7. Quality-before-throughput metrics

Freeze acceptance thresholds before held-out evaluation. Record:
- transcript accuracy/time alignment;
- screen-change detection and visual-evidence coverage;
- OCR usefulness and target-box localization;
- cursor/click hypothesis precision/recall (not native event accuracy);
- DecisionEpisode evidence coverage and unsupported-claim rate;
- extraction-fidelity, decision-validity, and outcome-validity verdicts;
- PM review agreement and traceability;
- decision correctness by type;
- task decomposition and dependency/order correctness;
- branch and method selection accuracy;
- instructor-rationale fidelity and evidence attribution;
- precondition/postcondition verification accuracy;
- capability delegation correctness;
- Hands result interpretation;
- recovery and replan quality;
- held-out business-goal completion and transfer to new conditions;
- observed/inferred/unknown classification correctness;
- safety violations (must be zero).

After quality gates pass, record processing time, video duration, ASR/alignment cost, GPU-hours, peak VRAM/RAM, per-tutorial cost, queue wait, retries, and failure rate. Do not claim throughput without the hardware, model revision, input duration, source-file details, and quality level used.

## 8. Reports

Every test report records commit SHA, branch, test date, OS/hardware, model/adapter revision, workflow versions, dataset snapshot, tool versions, configuration, commands, total/pass/fail/skip, duration, measured resource use, artifacts, failure examples, and gate decision.

## 9. Current implementation boundary

- **PR #38:** downloaded video-file extraction, DecisionEpisode construction, and contract validation.
- **PR #39:** local open-weight verifier gate.
- **PR #40:** fail-closed training-sample compiler.
- **PR #41:** metadata-aware dataset preparation and T4 Axolotl configuration; no real training run.
- **PR #42:** Brain/Hands loop; CI uses deterministic WorkflowBrain and SimulatedHands, not real model execution.

The full production chain still requires a PM-approved real corpus, actual LoRA training, a trained Brain serving adapter, and real Hands evaluation.
