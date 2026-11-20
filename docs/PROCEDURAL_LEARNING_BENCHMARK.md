# Procedural learning benchmark (initial harness)

## Purpose

This benchmark separates four capabilities that must not be conflated:

1. **Media processing** — decode video, extract audio/frames, run ASR/OCR.
2. **Procedure extraction** — infer ordered actions, targets, preconditions and expected states.
3. **Evidence grounding** — attach each claimed step to a timestamped UI observation.
4. **Task execution** — carry out the procedure in a controlled application and recover from faults.

The current implementation includes the data contract, a conservative step-extraction evaluator, and a deterministic local state-machine simulator. It does **not** implement browser automation, connect a real model, or demonstrate model learning or autonomous execution.

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

The checked-in evaluator fixture is explicitly marked `synthetic`. It exists only to test evaluator mechanics. It is **not** a human annotation of the Content Translation screencast and must not be used to report model quality.

## Local execution simulator

A deterministic local state-machine simulator covers feature enablement, dashboard, language/article selection, editor, draft save/resume and mocked publish confirmation. The publish operation remains local and never submits to the real Wikimedia site. Tests cover the normal path, shifted control aliases, interruption recovery, and invalid transitions.

This is still a hand-authored simulator, not an execution agent. A future runner must log pre/post state, action, screenshot/evidence ID, failure, retry/recovery and final task outcome. Report normal-path success, disturbed-layout success, interruption recovery and end-to-end completion separately.

## Real tutorial annotation draft

Source selected: [Content Translation Screencast (English).webm](https://commons.wikimedia.org/wiki/File:Content_Translation_Screencast_(English).webm), by Pau Giner, 13 January 2015, 255.983 seconds, 1280x720, CC BY-SA 4.0. An official YouTube mirror is also listed by Wikimedia: [Content Translation screencast](https://www.youtube.com/watch?v=nHTDeKW3hV0). Chinese timed text: [zh-cn subtitles](https://commons.wikimedia.org/wiki/TimedText:Content_Translation_Screencast_(English).webm.zh-cn.srt).

A ten-step narration-aligned draft is stored at `tests/fixtures/content_translation_timeline_unreviewed.json`. It records subtitle cue references and timestamps only. Every step is marked `pending_frame_review`; this is not accepted UI ground truth. Timestamp-specific frame captures and the pinned media SHA-256 have not yet been acquired. Do not use this draft to claim UI evidence completeness or model accuracy.

The media preparation helper is:

```bash
python scripts/prepare_tutorial_media.py --output-dir artifacts/tutorial-media
```

It downloads only the pinned Wikimedia Commons file, checks its published byte size and SHA-1 before accepting it, computes SHA-256, extracts one frame at each draft step timestamp with FFmpeg, and writes a manifest with creator/date/source attribution and the CC BY-SA 4.0 license URL. Extracted frames remain `pending_human_visual_review`; extraction does not automatically validate the UI action or target. The direct Wikimedia media endpoint was not retrievable in the current review environment; the source page and YouTube mirror are confirmed, but no frames are claimed as inspected.

Human visual review instructions: see [TUTORIAL_FRAME_REVIEW_GUIDE.md](TUTORIAL_FRAME_REVIEW_GUIDE.md). Subtitle timestamps are navigation anchors only; reviewers must select the actual frame where the UI state/action is visible.

## Acceptance gate for reviewed ground truth

Do not promote a draft to accepted ground truth by changing a status string alone. Run:

```bash
python scripts/validate_tutorial_annotation.py \
  tests/fixtures/content_translation_timeline_unreviewed.json
```

The validator rejects drafts unless the complete annotation is marked `reviewed`, review metadata includes a reviewer and ISO review date, the reviewer differs from the annotator when an annotator is recorded, every step is marked `frame_verified` with timestamped `video_frame` or `ui_snapshot` evidence, and at least eight steps have visual evidence. This gate validates annotation metadata and evidence references; it does not inspect image contents or prove that a frame genuinely supports its label. Human review remains mandatory.
