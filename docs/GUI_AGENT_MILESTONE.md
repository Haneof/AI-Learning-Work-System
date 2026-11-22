# GUI Agent: Expert Validation Operation Loop

## Role in the learning system

The GUI Agent provides runtime validation/execution infrastructure for Brain/Hands workflows. It is not the tutorial source-understanding pipeline: tutorial evidence is extracted from downloaded video files and timed subtitles/ASR. Pixel-derived cursor/click hypotheses remain inferred_from_video.

The target product is a 4B base model with a vertical LoRA adapter trained on double-verified knowledge packages. After adapter loading, the GUI loop tests whether the expert can use the learned principles to complete a goal in a live controlled interface, observe the resulting state, recover from unexpected changes, and generalize beyond the tutorial's exact route.

This loop can capture actual pointer, mouse, keyboard, and input events while the existing Hands model is operating in the controlled environment. These are runtime Hands execution observations, not tutorial-ingestion evidence. They may be used to audit a live operation, but they must remain distinct from observations and inferences extracted from downloaded tutorial video files. The previously proposed rrweb/Windows UIA live tutorial recorder/event collector was cancelled on 2026-11-21 and is not part of the current ingestion architecture.

## Scope

This milestone provides a local-browser-only observe/decide/act/verify loop and a timestamped JSONL trace format. The decision model is injected through the async `DecisionModel.decide(request)` protocol.

The current implementation is a GUI agent foundation. It does not automatically load or train a LoRA adapter; a compatible serving endpoint/model wrapper must be configured and validated for the trained expert.

Install the optional browser extra and Chromium:

```bash
python -m pip install -e ".[dev,gui]"
playwright install chromium
pytest
```

## Action contract

A model returns one JSON object with an `action` from `click`, `type`, `scroll`, `wait`, or `done`, plus a natural-language `target` description. Click and type also require a CSS `selector`. Every non-terminal action must include an explicit `expected_result` assertion. Supported assertions are `text_contains`, `text_equals`, `value_equals`, `visible`, `hidden`, `attribute_equals`, `url_contains`, and `title_contains`.

The runner supplies the model with the objective, screenshot (base64 PNG), full DOM snapshot, accessibility snapshot, recent action history, and correction feedback. Only the five declared actions are executable; arbitrary JavaScript and navigation actions are not part of the protocol.

## Safety boundary

The initial page must use loopback HTTP(S) (`localhost`, `127.0.0.1`, or `::1`). The browser context blocks requests outside the exact initial origin, and every action checks that the page remains on that origin. Tests serve `tests/fixtures/gui/index.html` from a temporary local HTTP server. No test uses a real model or API credential.

## Trace format and replay

Each JSONL trace starts with a `gui-trace-v1` header. Every step records before and after PNG frames, DOM and accessibility snapshots, captured pointer/mouse/keyboard/input events, the structured action, expected and observed result, and a `training_example` pair (`observation -> action`). Text and event metadata for password/secret/token inputs are redacted by the event collector.

`TraceReplayer` requires the exact recorded local origin and executes steps in order. A malformed step, recorded error, action failure, or verification mismatch raises `ReplayVerificationError` and stops replay immediately.

## Expert acceptance use

Run sandbox and GUI loop evaluations against frozen test suites. Include alternate starting states, changed control labels/layouts, dialogs, scroll positions, partial failures, and unseen tasks. A passing result requires goal/result verification and safe recovery—not merely that the expert emitted a plausible click or replayed a reference sequence.
