# GUI Agent first milestone

## Scope

This milestone provides a local-browser-only observe/decide/act/verify loop and a
timestamped JSONL trace format. It does not connect a hosted model, access a real
website, perform authentication, or perform external side effects. The decision
model is injected through the async `DecisionModel.decide(request)` protocol.

Install the optional browser extra and the Chromium engine:

```bash
python -m pip install -e ".[dev,gui]"
playwright install chromium
pytest
```

## Action contract

A model returns one JSON object with an `action` from `click`, `type`, `scroll`,
`wait`, or `done`, plus a natural-language `target` description. Click and type
also require a CSS `selector`. Every non-terminal action must include an explicit
`expected_result` assertion. Supported assertions are `text_contains`,
`text_equals`, `value_equals`, `visible`, `hidden`, `attribute_equals`,
`url_contains`, and `title_contains`.

The runner supplies the model with the objective, screenshot (base64 PNG), full DOM
snapshot, accessibility snapshot, recent action history, and correction feedback.
Only the five declared actions are executable; arbitrary JavaScript and navigation
actions are not part of the protocol.

## Safety boundary

The initial page must use loopback HTTP(S) (`localhost`, `127.0.0.1`, or `::1`).
The browser context blocks requests outside the exact initial origin, and every
action checks that the page remains on that origin. Tests serve
`tests/fixtures/gui/index.html` from a temporary local HTTP server. No test uses a
real model or API credential.

## Trace format and replay

Each JSONL trace starts with a `gui-trace-v1` header. Every step records before and
after PNG frames, DOM and accessibility snapshots, captured pointer/mouse/keyboard/
input events, the structured action, expected and observed result, and a
`training_example` pair (`observation -> action`). Text and event metadata for
password/secret/token inputs are redacted by the event collector.

`TraceReplayer` requires the exact recorded local origin and executes steps in
order. A malformed step, recorded error, action failure, or verification mismatch
raises `ReplayVerificationError` and stops replay immediately.

## Recovery policy

After a failed result assertion, the agent may ask the model for one correction
action. If the correction fails, the model times out, an action times out, or the
step limit is reached, the agent stops and returns a `RunReport` with the trace
path and failure information.
