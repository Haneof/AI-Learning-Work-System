# Model Benchmark Harness

## Purpose

This harness provides a repeatable comparison contract for the selected Qwen 3.5 4B and 9B candidates. The benchmark runner is separated from the inference backend so the same dataset and scoring rules can be used with the deterministic mock or a real local model.

## Backend choices

- `mock` (default): deterministic fixture text. It validates dataset loading, scoring, JSONL serialization, and report generation only.
- `llama-server`: sends each prompt to a local llama.cpp server through the OpenAI-compatible Chat Completions API. The adapter uses Server-Sent Events (SSE) to measure time-to-first-token.

No Python runtime dependency is added for the real backend; it uses the standard library HTTP client.

## Start a local Qwen 3.5 model (Windows PowerShell)

From the repository root, start the 4B model:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\start-qwen35-llama-server.ps1 -ModelSize 4B
```

The script downloads the GGUF file into `models/qwen35/`, verifies its SHA-256 checksum, finds (or installs) `llama-server.exe`, and starts the server on `127.0.0.1:8080`. Stop the server with Ctrl+C before starting a different model.

Start the 9B candidate in the same way:

```powershell
.\scripts\start-qwen35-llama-server.ps1 -ModelSize 9B
```

You can override the server executable, port, context length, GPU offload setting, or model directory:

```powershell
.\scripts\start-qwen35-llama-server.ps1 -ModelSize 4B -ServerExe "C:\llama.cpp\llama-server.exe" -ContextLength 4096 -GpuLayers auto
```

The script binds only to loopback. The default WinGet installation is a convenience fallback; for best NVIDIA throughput, use a CUDA-enabled llama.cpp Windows build and pass its `llama-server.exe` path with `-ServerExe`. A Vulkan build can still use the NVIDIA GPU but may perform differently.

### Model artifacts and hardware notes

| Candidate | GGUF source | File | Approx. download size | SHA-256 |
|---|---|---|---:|---|
| 4B Q4_K_M | `ggml-org/Qwen3.5-4B-GGUF` | `Qwen3.5-4B-Q4_K_M.gguf` | 3.03 GB | `217002fa8008ef4fc6d548353a3aebef055a96e6ff8e0e2c0953ef8254a89c14` |
| 9B Q4_K_M | `SoAIHQ/Qwen3.5-9B-GGUF` | `Qwen3.5-9B-Q4_K_M.gguf` | 5.8 GB | `ef6f244d63abcba4f8d30b7cbd9369e9e798fc33cf21109889373f59af329c93` |

The 4B GGUF repository declares Apache-2.0. The 9B repackaging declares the original Qwen model's Apache-2.0 license and documents the source revision/conversion provenance; see its model card and published checksum manifest.\n\nThe 8 GB RTX 3070 Laptop cannot be assumed to hold the 9B weights plus KV cache entirely in VRAM. The launcher uses llama.cpp's automatic GPU-layer fit and a conservative 4K context by default; some layers may run on system RAM/CPU. Actual speed and peak resource use must be measured on the target machine. Change `-ContextLength` only as part of a recorded benchmark configuration.

The launcher downloads text GGUF weights only. It does not download a multimodal projection (`mmproj`) file, so this integration benchmarks text prompts; vision capability remains untested.

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

The mock backend remains the default to preserve offline tests and the existing workflow.

## Run against the real model

Keep the llama-server terminal running. In a second PowerShell terminal:

```powershell
python -m aios_work_system benchmark `
  --dataset tests/fixtures/benchmark_smoke.jsonl `
  --backend llama-server `
  --model-size 4B `
  --context-length 4096 `
  --revision main `
  --quantization Q4_K_M `
  --gpu "RTX 3070 Laptop GPU" `
  --vram-gb 8 `
  --ram-gb 16
```

For 9B, stop the 4B server, start the 9B server, then set `--model-size 9B`. You may override `--base-url` and `--request-timeout` when the server is not at the default `http://127.0.0.1:8080/v1` address.

## Output and measurement semantics

The default outputs are:

- `artifacts/benchmark/results.jsonl`
- `artifacts/benchmark/report.md`

For the real backend:

- Time-to-first-token is measured to the first non-empty streamed text delta.
- Input/output token counts are recorded only when the server sends a `usage` object. If usage is absent, token counts and tokens/second remain null; they are not estimated.
- Peak RAM and VRAM remain null unless a backend explicitly measures them. This adapter does not invent resource metrics.
- Backend metadata, including the returned server model name and whether usage was returned, is preserved in JSONL.
- HTTP errors, connection failures, malformed stream events, and empty responses become failed benchmark cases with an actionable error.

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

The `mock_response` field is only a fixture hook for the mock backend. A real backend ignores it and sends only the case prompt.

## Comparison requirements and interpretation limits

For each candidate, record:

- Exact model repository and local path
- Immutable revision / commit or model file SHA-256
- Quantization format and exact artifact filename
- Inference backend and version
- Context length and generation parameters (temperature, top-p, max tokens)
- GPU model, VRAM, system RAM, operating system, and driver/runtime versions

Both candidates must use the same dataset version, prompts, decoding settings, and hardware conditions. Report measured facts separately from subjective human review.

- Mock results validate harness plumbing only, not model quality.
- Real-backend output is generated by a real model, but deterministic substring/JSON checks are not a substitute for human review or task-level acceptance.
- Time-to-first-token is measured only when a real backend streams content. Peak RAM/VRAM remain unknown unless a backend measures them.
- Vision capability remains unknown until a vision-capable adapter and projection model are tested.
