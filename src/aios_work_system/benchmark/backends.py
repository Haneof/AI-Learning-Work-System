"""Inference backend interface and deterministic mock backend."""

from __future__ import annotations

from typing import Protocol

from aios_work_system.benchmark.types import BenchmarkCase, GenerationOutput


class GenerationBackend(Protocol):
    name: str

    def generate(self, case: BenchmarkCase) -> GenerationOutput:
        """Generate one response for a benchmark case."""


class MockBackend:
    """Return deterministic fixture text; this backend does not evaluate a real model."""

    name = "mock"

    def generate(self, case: BenchmarkCase) -> GenerationOutput:
        response = case.checks.get("mock_response", "Mock response for benchmark plumbing.")
        return GenerationOutput(
            text=str(response),
            input_tokens=len(case.prompt.split()),
            output_tokens=len(str(response).split()),
            metadata={"backend_mode": "mock"},
        )
