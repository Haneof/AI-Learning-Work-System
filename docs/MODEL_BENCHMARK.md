# Model Benchmark Harness

## Purpose

This harness provides a repeatable comparison contract for the selected Qwen 3.5 4B and 9B candidates. It deliberately separates the benchmark runner from the inference backend so the final runtime can be selected after the exact model artifacts and hardware-compatible quantization are confirmed.

## Current implementation boundary

- A backend protocol defines the inference adapter boundary.
- The included mock backend validates dataset loading, scoring, JSONL serialization, and report generation only.
- The smoke dataset covers structured output, knowledge extraction, evidence citation, multi-step reasoning, and skill drafting.
- Deterministic checks are explicit: required substrings, valid JSON object, and non-empty output.
- No real Qwen weights are downloaded or loaded.
- Time-to-first-token, peak RAM, and peak VRAM are null until a real backend measures them.
- Vision capability remains unknown until a vision-capable adapter is tested.

## Run the smoke benchmark

From the repository root:

```powershell
python -m pip install -e ".[dev]"
aios benchmark --dataset tests/fixtures/benchmark_smoke.jsonl --model-id mock/smoke
```

Or:

```powershell
python -m aios_work_system benchmark --dataset tests/fixtures/benchmark_smoke.jsonl
```

The default outputs are:

- `artifacts/benchmark/results.jsonl`
- `artifacts/benchmark/report.md`

## Dataset format

Each JSONL line is one independent case:

```json
{
  "case_id": "json-shape-001",
  "category": "structured_output",
  "prompt": "Return a JSON object with key status.",
  "checks": {
    "valid_json_object": true,
    "contains_all": ["status"]
  }
}
```

The `mock_response` field is only a fixture hook for the mock backend. A real backend must ignore it.

## Required metadata before real-model evaluation

For each candidate, record:

- Exact model repository or local path
- Immutable revision / commit or model file checksum
- Quantization format and exact artifact filename
- Inference backend and version
- Context length and generation parameters (temperature, top-p, max tokens, seed)
- GPU model, VRAM, system RAM, operating system, and driver/runtime versions

Both candidates must use the same dataset version, prompts, decoding settings, and hardware conditions. Report measured facts separately from subjective human review.

## Planned real-backend contract

A real adapter must implement `GenerationBackend.generate(case)` and return the generated text, token counts, time-to-first-token, and any backend-measured resource metrics where available. The generic runner does not invent or estimate unavailable measurements.
