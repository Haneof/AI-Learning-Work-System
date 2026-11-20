# Procedural learning benchmark (initial harness)

## Purpose

This benchmark separates four capabilities that must not be conflated:

1. **Media processing** — decode video, extract audio/frames, run ASR/OCR.
2. **Procedure extraction** — infer ordered actions, targets, preconditions and expected states.
3. **Evidence grounding** — attach each claimed step to a timestamped UI observation.
4. **Task execution** — carry out the procedure in a controlled application and recover from faults.

The current implementation covers the data contract and a conservative step-extraction evaluator only. It does **not** implement a browser simulator, connect a real model, or demonstrate learning or execution.

## Step contract

See `schemas/procedural_skill.schema.json`. Each step requires:

- goal, preconditions, action and target;
- expected post-action state;
- one or more evidence references with a non-negative timestamp;
- a recovery strategy.

Evidence kinds distinguish video frames/UI snapshots from subtitles and ASR segments. A subtitle is narration evidence, not proof that a UI action occurred.

## Evaluator

Run:

```bash
python scripts/evaluate_procedural_steps.py \
  --reference tests/fixtures/procedural_steps_ground_truth.json \
  --prediction tests/fixtures/procedural_steps_ground_truth.json \
  --output artifacts/procedural-evaluation.json
```

The evaluator uses exact normalized action+target matching with one-to-one matching. It reports precision, recall, F1, order accuracy, expected-state accuracy on matched steps and evidence completeness.

This initial matching method is intentionally simple and conservative. It does not claim semantic equivalence. A prediction without evidence can still match an action/target for extraction scoring, but is separately penalized in evidence completeness.

## Fixture status

The checked-in fixture is explicitly marked `synthetic`. It exists only to test evaluator mechanics. It is **not** a human annotation of the Content Translation screencast and must not be used to report model quality.

Before using the screencast as ground truth:
1. pin the source media and subtitle versions and record SHA-256 hashes;
2. sample UI frames around state transitions;
3. annotate at least eight actions with timestamps, targets, preconditions, expected states and frame evidence;
4. have a second reviewer verify labels, or explicitly mark them unreviewed;
5. keep narration-only claims separate from observed UI facts.

## Execution benchmark — next milestone

Build a local mock application with states for feature enablement, dashboard, language/article selection, editor, draft save/resume and a mocked publish confirmation. The publish operation must remain local and must never submit to the real Wikimedia site.

The execution runner must log pre/post state, action, screenshot/evidence ID, failure, retry/recovery and final task outcome. Report normal-path success, disturbed-layout success, interruption recovery and end-to-end completion separately.

No model-learning or autonomous-work claim is permitted until a real model is evaluated against reviewed annotations and completes the isolated tasks.
