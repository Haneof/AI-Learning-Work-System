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

This initial matching method is intentionally simple and conservative. It does not claim semantic equivalence. A prediction without evidence can still match an action/target for extraction scoring, but is separately penalized in evidence completeness. The report also exposes `ui_evidence_completeness`, which only accepts `video_frame` or `ui_snapshot`; subtitle/ASR references cannot satisfy this visual-evidence metric.

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

## Real tutorial annotation draft

Source selected: [Content Translation Screencast (English).webm](https://commons.wikimedia.org/wiki/File:Content_Translation_Screencast_(English).webm), by Pau Giner, 13 January 2015, 255.983 seconds, 1280x720, CC BY-SA 4.0. Chinese timed text: [zh-cn subtitles](https://commons.wikimedia.org/wiki/TimedText:Content_Translation_Screencast_(English).webm.zh-cn.srt).

A ten-step narration-aligned draft is stored at `tests/fixtures/content_translation_timeline_unreviewed.json`. It records subtitle cue references and timestamps only. Every step is marked `pending_frame_review`; this is not accepted UI ground truth. The Commons page exposes a poster image of the editor, but timestamp-specific frame captures and SHA-256 of the media have not yet been acquired. Do not use this draft to claim UI evidence completeness or model accuracy.

Next gate: obtain the media locally, extract timestamp-specific frames, verify each target/action/state against the frames, replace or supplement subtitle references with `video_frame` evidence, and have a second reviewer verify the labels (or keep the status unreviewed).

Media acquisition and frame extraction helper:

```bash
python scripts/prepare_tutorial_media.py --output-dir artifacts/tutorial-media
```

The helper downloads only the pinned Wikimedia Commons file, checks its published byte size and SHA-1 before accepting it, computes SHA-256, extracts one frame at each draft step timestamp with FFmpeg, and writes a manifest with creator/date/source attribution and the CC BY-SA 4.0 license URL. Extracted frames are adaptations of the source and must retain compatible attribution/share-alike terms when redistributed. The resulting frames remain `pending_human_visual_review`; extraction does not automatically validate the UI action or target.
