# Procedural execution metrics

## Purpose

The execution evaluator reports three separate rates. It consumes structured episode
records; it does not run a model or simulator and does not manufacture outcomes.

Run:

```bash
python scripts/evaluate_procedural_execution.py \
  --input tests/fixtures/procedural_execution_metrics_synthetic.json \
  --output artifacts/procedural-execution-report.json
```

## Metric definitions

- **Step success rate** = successful actions / attempted actions. An attempted action
  must be counted whether the action was accepted or rejected. The caller records an
  action as successful only when the execution adapter reports success.
- **Task completion rate** = completed episodes / all episodes. Completion is a
  terminal task outcome; it must not be inferred from a high step success rate.
- **Recovery success rate** = successful recovery attempts / episodes where recovery
  was attempted after a recorded recovery opportunity. Episodes with no recovery
  opportunity are excluded. An eligible episode where recovery was not attempted is
  reported separately and is not silently counted as a failed recovery.

A rate with a zero denominator is `null`, not 0. This distinguishes “not measured”
from “measured and failed”.

## Episode input contract

Each episode contains exactly:

- `episode_id`: unique non-empty identifier;
- `attempted_actions`, `successful_actions`: non-negative integers, with successes
  no greater than attempts;
- `task_completed`: boolean;
- `recovery_opportunity`: whether an interruption/fault made recovery applicable;
- `recovery_attempted`: whether the runner actually attempted recovery;
- `recovery_succeeded`: boolean when attempted, otherwise null.

The evaluator rejects inconsistent records, duplicate IDs, booleans masquerading as
integer action counts, and unknown fields.

## Evidence and interpretation

The current checked-in fixture is synthetic and validates arithmetic/denominator
behavior only. It is not a benchmark result and does not demonstrate a model's ability.

When a real model runner is added, it must record raw event logs and derive these
episode fields from the logs. Reports should identify model/version, prompt version,
simulator/app version, task set, random seed, and run timestamp in the surrounding
experiment manifest. Compare models only on the same task set and environment.

A deterministic simulator score measures performance in that simulator. It must not
be described as real browser competence until tested against a controlled real UI
environment with independently reviewed task outcomes.
