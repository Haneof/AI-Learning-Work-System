"""Run benchmark cases and emit machine-readable JSONL results."""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from pathlib import Path

from aios_work_system.benchmark.backends import GenerationBackend
from aios_work_system.benchmark.scoring import score_output
from aios_work_system.benchmark.types import (
    BenchmarkCase,
    BenchmarkResult,
    ModelDescriptor,
)


class BenchmarkRunner:
    def __init__(self, backend: GenerationBackend, model: ModelDescriptor) -> None:
        self.backend = backend
        self.model = model

    def run_case(self, case: BenchmarkCase) -> BenchmarkResult:
        started = time.perf_counter()
        try:
            generated = self.backend.generate(case)
            elapsed = time.perf_counter() - started
            checks = score_output(generated.text, case.checks)
            output_tokens = generated.output_tokens
            tokens_per_second = (
                output_tokens / elapsed if output_tokens is not None and elapsed > 0 else None
            )
            resource_metrics = {
                "ram_peak_bytes": None,
                "vram_peak_bytes": None,
                **generated.resource_metrics,
            }
            return BenchmarkResult(
                case_id=case.case_id,
                category=case.category,
                model=self.model,
                output=generated.text,
                latency_ms=elapsed * 1000,
                time_to_first_token_ms=generated.time_to_first_token_ms,
                input_tokens=generated.input_tokens,
                output_tokens=output_tokens,
                tokens_per_second=tokens_per_second,
                passed=all(checks.values()) if checks else False,
                checks=checks,
                resource_metrics=resource_metrics,
            )
        except Exception as exc:
            elapsed = time.perf_counter() - started
            return BenchmarkResult(
                case_id=case.case_id,
                category=case.category,
                model=self.model,
                output="",
                latency_ms=elapsed * 1000,
                time_to_first_token_ms=None,
                input_tokens=None,
                output_tokens=None,
                tokens_per_second=None,
                passed=False,
                checks={},
                error=f"{type(exc).__name__}: {exc}",
            )

    def run(self, cases: Iterable[BenchmarkCase]) -> list[BenchmarkResult]:
        return [self.run_case(case) for case in cases]


def load_jsonl(path: str | Path) -> list[BenchmarkCase]:
    cases: list[BenchmarkCase] = []
    with Path(path).open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                if not isinstance(payload, dict):
                    raise ValueError("Each JSONL line must be an object")
                cases.append(BenchmarkCase.from_dict(payload))
            except (json.JSONDecodeError, ValueError) as exc:
                raise ValueError(f"Invalid benchmark dataset at line {line_number}: {exc}") from exc
    return cases


def write_jsonl(results: Iterable[BenchmarkResult], path: str | Path) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as stream:
        for result in results:
            stream.write(json.dumps(result.to_dict(), ensure_ascii=False) + "\n")


def write_markdown_report(results: list[BenchmarkResult], path: str | Path) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    total = len(results)
    passed = sum(result.passed for result in results)
    lines = [
        "# Model Benchmark Report",
        "",
        f"- Cases: {total}",
        f"- Passed: {passed}",
        f"- Failed: {total - passed}",
        "",
        "| Case | Category | Model | Latency (ms) | Output tokens | tok/s | Checks |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for result in results:
        checks = (
            ", ".join(
                f"{name}={'PASS' if passed_check else 'FAIL'}"
                for name, passed_check in result.checks.items()
            )
            or "no automated checks"
        )
        lines.append(
            f"| {result.case_id} | {result.category} | {result.model.model_id} | "
            f"{result.latency_ms:.2f} | {result.output_tokens or ''} | "
            f"{result.tokens_per_second or ''} | {checks} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation limits",
            "",
            "- Mock backend results validate harness plumbing only, not model quality.",
            "- Time-to-first-token and peak RAM/VRAM are unknown unless a backend measures them.",
            "- Automated checks are explicit and deterministic; no subjective score is inferred.",
            "- Vision capability is unknown until a vision-capable adapter is tested.",
            "",
        ]
    )
    destination.write_text("\n".join(lines), encoding="utf-8")
