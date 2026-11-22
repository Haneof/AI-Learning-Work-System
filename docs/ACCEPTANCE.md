# Acceptance Criteria

**Version:** 0.2, aligned with PRs #38–#42  
The pipeline is accepted on evidence quality, Brain workflow competence, and verified business outcomes—not transcript volume, screenshot count, or raw throughput.

## Step 1 — Download and archive

- Each selected tutorial is acquired as a downloadable video file.
- Available timed subtitle files are preserved with the source video.
- Every file has a record with source link, platform, content hash, creator/course grouping, and attribution/license metadata where available.
- The source file is reproducibly available to the extraction command.
- The learning route does not require real-time video playback or a live rrweb/Windows UIA recorder.

## Step 2 — Extract evidence from the video file (PR #38)

- Existing timestamped SRT/WebVTT subtitles are preferred.
- Local ASR is used only when no usable subtitle cues are available.
- FFmpeg produces timestamped sampled stills and pixel-difference detection selects the initial/changed frames.
- OCR reads visible UI text from selected frames.
- Cursor/possible-click inference and local UI-target grounding are retained as hypotheses, not native event telemetry.
- Transcript segments are aligned to visual screen-change events.
- Evidence preserves source timestamps, extraction methods, provenance, and uncertainty.
- Video-visible observations are labelled `observed_from_video`; inferred cursor/click/target items are `inferred_from_video`; instructor words remain separate.
- Hidden clicks, keypresses, DOM changes, and unobservable business state remain unknown rather than fabricated.

## Step 3 — DecisionEpisode and contract validation (PR #38)

- Each DecisionEpisode records the goal, decision-time state, rationale source, selected decision, operation hypothesis/status, result evidence, next decision, and unresolved questions.
- Every important claim links to source evidence or is explicitly marked inferred/unknown.
- The episode passes JSON Schema and semantic validation.
- A schema-valid episode is not automatically true, independently reviewed, or approved for training.
- A video-derived record does not claim that an operation executed or a business postcondition passed unless separate evidence supports it.

## Step 4 — Local verification and PM review (PR #39)

- The local verifier returns separate pass/fail/unknown verdicts for extraction fidelity, decision validity, and outcome validity.
- All three local levels must pass; no majority vote can override a failed or unknown level.
- Invalid evidence references, missing source/model evidence, and malformed output remain held.
- A video-only temporal sequence is UNKNOWN for causal outcome validity.
- The PM independently inspects the original source and proposed episode and records a separate PASS with source-evidence and proposed-record references.
- Local PASS alone never makes an episode eligible for training.

## Step 5 — Compile Brain training samples (PR #40)

- The compiler accepts only episodes with local verifier PASS, independent PM PASS, approved review, eligible annotation state, `trainable=true`, and no exclusion reasons.
- Every decision point becomes a separate conversational sample.
- Assistant targets contain the Brain's next decision only; future Hands results do not leak into earlier decisions.
- Evidence tier and rationale loss weight are kept in a separate training-metadata sidecar, not model messages.
- All episodes/near-duplicates from one source/course group stay in one train/test partition.
- The manifest records included/excluded counts and split assignments; held records fail closed.

## Step 6 — Brain LoRA training setup and execution (PR #41)

- Sidecars are required, aligned, uniquely identified, and partition-consistent.
- Excluded or not-eligible rows are rejected.
- Training-row weighting is deterministic and bounded; test rows remain unchanged.
- The T4 Axolotl config uses the original `DreamFast/qwen3-4b-heretic` Transformers checkpoint, FP16 compute, and the documented LoRA modules/settings.
- Dataset preparation and configuration validation pass before any model download or training.
- **A real training run is a separate acceptance step:** record dataset hash, base revision, run parameters, GPU/VRAM, metrics, and adapter hash. PR #41 did not run training or produce adapter weights.

## Step 7 — Brain-to-Hands loop (PR #42)

- Brain delegation is business-level and names a registered capability, arguments, preconditions, constraints, risk/approval policy, and expected postconditions.
- Hands results are correlated by call/task ID and include status, fresh state, postcondition checks, and evidence references.
- The loop independently verifies expected postconditions against a fresh observation before accepting progress.
- Failed, partial, or uncertain execution returns to Brain for recovery/replanning; non-idempotent actions are not blindly retried.
- Acceptance is scored by business-goal completion and safe recovery, not click count or model "done" text.
- **Current merged CI scope:** deterministic WorkflowBrain plus SimulatedHands. The BrowserAgentHandsAdapter is available as a bridge, but PR #42 did not run a trained Brain LoRA or a real UI-TARS-class Hands model.

## Quality metrics

Freeze thresholds before held-out evaluation. At minimum measure:
- extraction fidelity and timestamp alignment;
- OCR and changed-frame coverage;
- UI target-box localization (not click-event accuracy);
- observed/inferred/unknown label correctness;
- decision validity and provenance of rationale;
- outcome validity and postcondition evidence;
- task decomposition, dependency/order reasoning, and branch selection;
- capability selection, safe delegation, and Hands-result interpretation;
- recovery/replan/stop quality;
- held-out business-goal completion and transfer to alternative routes;
- evidence coverage, unsupported-claim rate, and safety violations (must be zero).

Throughput and cost are optimized only after the quality gates pass.

## Release blocking

Any fabricated instructor reason, unsupported business rule, false native-event claim, unsupported click/outcome assertion, unresolved critical evidence, invalid local or PM gate, unreviewed training sample, future-outcome leakage, unregistered capability call, or critical sandbox/Hands safety failure blocks release.
