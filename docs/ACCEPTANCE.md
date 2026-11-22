# Acceptance Criteria

**Version:** 0.1 design update  
The pipeline is accepted on evidence quality, Brain workflow competence, and verified business outcomes—not transcript volume, screenshot count, or raw throughput.

## Step 1 — Download and archive

- Every selected tutorial has a download record with source link and platform.
- Creator/series/course grouping is preserved in the 5TB Google Drive archive.
- Original metadata and license uncertainty are not fabricated.
- SHA-256 is recorded to identify exact duplicate content.

## Step 2 — Capture semantic UI events and narration

- New web tutorials capture rrweb events directly from recording start.
- New Windows desktop tutorials capture supported Windows UI Automation events and record provider limitations.
- Event timestamps, application/page/window identity, target references, and before/after state changes are retained where available.
- Instructor audio is preserved and synchronized with the event stream.
- Existing subtitles are used first; ASR runs only when usable subtitles are unavailable.
- Narration is aligned at word or segment granularity, with method and uncertainty recorded.
- Legacy MP4 reconstruction is explicitly labelled inferred_from_video; it is not treated as direct telemetry.
- Sparse/dense frame extraction is not used as the primary tutorial-learning input.

## Step 3 — Decision Episodes and workflows

- Each Decision Episode records goal, decision-time state, rationale source, chosen strategy, operation, result, and next decision.
- Instructor-explicit statements are separated from behavioral inference and project-owner-provided rules.
- Every decision-driving fact and rationale has evidence or is explicitly unknown.
- HTN workflows include compound/primitive tasks, methods, conditions, dependencies, preferences, ordering constraints, invariants, transitions, and recovery rules.
- Conflicting workflows from different tutorials, application versions, or applicability conditions coexist; no overwrite.
- A single tutorial's path is not assumed to be the only valid path.

## Step 4 — Review and training data

- Exact duplicate source content is identified by SHA-256.
- The first review checks evidence resolution, event/narration alignment, workflow consistency, and uncertainty.
- PM Sangou independently verifies source evidence and relevant tests.
- Both review.status=approved/approved_for_training and quality.trainable gates must pass.
- Conversational JSONL examples and the separate training_meta sidecar are consistent.
- Normal-decision and error-recovery examples use only information available at that decision point.
- Future Hands execution outcomes do not leak into the assistant target.
- Train/test split is grouped by tutorial/course/source.
- Only eligible examples enter the immutable training dataset snapshot.

## Step 5 — Brain LoRA and Brain-to-Hands validation

- Every dataset snapshot and training run records example/source hashes, base revision, configuration, compute/GPU, and adapter hash.
- The 4B BF16 LoRA path is planned for a T4 16GB cloud GPU; the 9B path requires 24GB+ planning capacity. Actual usage must be measured.
- Runtime prompts include the applicable local HTN workflow slice.
- Brain decisions are first evaluated with a simulated Hands executor.
- The real existing Hands model is connected through a capability adapter; no new button-recognition or low-level operation model is required.
- Hands returns structured status, observed state, postcondition results, errors, and evidence references.
- Passing requires business postcondition verification, branch handling, and safe recovery—not a successful click alone.
- The Brain handles success, failure, partial success, blocked, and ambiguous operation results.
- Evaluation includes unseen tasks, changed initial states, alternative valid routes, missing information, and error recovery.

## Quality metrics

Freeze thresholds before held-out evaluation. At minimum measure:
- decision accuracy at each decision point;
- task decomposition and dependency/order correctness;
- conditional branch selection;
- business rationale and evidence provenance correctness;
- precondition and postcondition verification;
- capability selection and safe delegation;
- Hands result interpretation;
- recovery/replan/stop decision quality;
- held-out business-goal completion and transfer to alternative routes;
- evidence coverage and unsupported-claim rate;
- direct-capture versus inferred-from-video classification accuracy;
- safety violations (must be zero).

Throughput and cost are optimized only after the quality gates pass.

## Release blocking

Any fabricated instructor reason, unsupported business rule, false direct-capture claim, unresolved critical evidence, material workflow inconsistency, future-outcome leakage, unreviewed training example, unregistered capability call, or critical sandbox/Hands safety failure blocks release.
