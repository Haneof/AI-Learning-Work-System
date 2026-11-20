# Local procedural replay simulator

This is a deterministic state-machine fixture for exercising procedural plans without
opening a real website. All state is in memory. The only publish-like action is
`publish_mock`, which changes local state to `published_mock`; there is no network
client and no connection to Wikimedia.

## Covered states

Settings -> dashboard -> language/article selection -> editor -> saved draft ->
resumed draft -> mocked publish confirmation.

## Fault cases

- shifted control naming: a target alias simulates a layout/control-name change;
- interruption: the app state is reset to dashboard after saving, then the draft is resumed;
- invalid transition: publishing outside the editor is rejected.

## Run

```bash
pytest tests/test_procedural_simulator.py -q
```

This validates the deterministic simulator and replay rules, not model competence.
The next increment is a model adapter that proposes actions from observed snapshots,
plus trajectory logging and reviewed video-frame annotations. No real publishing is
implemented or permitted by this harness.
