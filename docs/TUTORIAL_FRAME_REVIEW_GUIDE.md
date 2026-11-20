# Tutorial frame review guide

## Goal

Convert the narration-aligned draft in
`tests/fixtures/content_translation_timeline_unreviewed.json` into reviewed UI-grounded
annotations. The subtitle timestamps are search anchors only. They are not guaranteed
to coincide with the click or the resulting UI state.

## Prepare the media

Run from the repository root:

```bash
python scripts/prepare_tutorial_media.py --output-dir artifacts/tutorial-media
```

The helper verifies the pinned Commons file size and SHA-1, computes SHA-256, extracts
one candidate frame per draft step, and writes `frame_manifest.json`. Keep the source
attribution and CC BY-SA 4.0 terms when redistributing media or derived frames.

## Review each step

For every step:

1. Open the candidate frame and inspect the actual visible UI, not the subtitle text.
2. If the action or resulting state is not visible, seek nearby frames in the source
   video and record a better timestamp. Do not force a label to fit the narration.
3. Record the observed page/state, target control label and location, action, visible
   preconditions, and resulting state.
4. Add a `video_frame` evidence reference to the exact frame file and timestamp.
5. Change `ui_verification_status` to `frame_verified` only after the frame supports
   the claim. Keep `pending_frame_review` when evidence is absent or ambiguous.
6. Keep the subtitle reference as supplementary narration evidence; never substitute
   it for the UI frame.

## Review status

- `unreviewed`: draft labels have not been independently checked.
- `frame_verified`: an individual step's UI evidence has been inspected.
- `reviewed`: use only after a second reviewer checks the complete annotation set.
  Record the reviewer and review date in the annotation metadata/change history.

Do not report the annotation as accepted ground truth until at least eight key steps
have timestamped UI evidence, all key transitions have frame evidence, and the
review state is accurately recorded.
