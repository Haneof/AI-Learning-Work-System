# Model action proposal protocol

The simulator accepts actions only through `scripts.procedural_action_protocol.execute_proposal`
when testing a model-facing integration. The adapter validates a single proposal object
against an allowlist, rejects extra fields, and delegates state/precondition checks to
`MockTranslationApp.perform`.

## Proposal shape

```json
{"action":"select_source","target":"source_language_dropdown","value":"es"}
```

- Required: `action`, `target`
- Optional: `value` (non-empty string)
- No additional properties are accepted.
- Action and target vocabularies are explicitly allowlisted in the adapter and mirrored
  in `schemas/procedural_action_proposal.schema.json`.
- A valid vocabulary does not imply a valid transition: the simulator still checks
  current state and required preconditions.
- The adapter executes at most one action per proposal and records the simulator audit
  entry only after successful execution.

## Safety boundary

This is a local mock execution boundary, not a browser or operating-system control API.
The model cannot set internal state, call arbitrary functions, submit shell commands,
access the network, or perform real publishing. `publish_mock` remains a local-only
terminal transition. Schema validation is mirrored in Python checks; the runtime adapter
is authoritative for execution.

## Run

```bash
pytest tests/test_procedural_action_protocol.py -q
```

Passing these tests validates protocol rejection and simulator integration only. It
does not measure model reasoning quality or real-world task success.
