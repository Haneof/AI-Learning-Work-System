# Local procedural replay simulator

This is a deterministic state-machine fixture for exercising procedural plans without
opening a real website. All state is in memory. The only publish-like action is
`publish_mock`, which changes local state to `published_mock`; there is no network
client and no connection to Wikimedia.

## Covered workflow

Settings -> dashboard -> source/target/article selection -> editor -> paragraph
insertion -> sentence-alignment review -> links/formatting review -> autosave ->
dashboard -> draft resume -> mocked publish confirmation.

The simulator records before/after snapshots for each accepted action. It rejects
out-of-order edits, autosave before content review, dashboard navigation without a
saved draft, and mock publication without the required review gates.

## Fault cases

- shifted control naming: a target alias simulates a layout/control-name change;
- interruption: after autosave, the app returns to dashboard and resumes the draft;
- invalid transition: illegal state/action combinations are rejected.

## Run

```bash
pytest tests/test_procedural_simulator.py -q
```

This validates the deterministic simulator and replay rules, not model competence,
translation quality, real UI automation, or real task success. `publish_mock` is a
local-only terminal state; no real publishing is implemented or permitted by this
harness. The tutorial annotation remains unreviewed until a human inspects actual
video frames.
