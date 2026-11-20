"""Typed records used by the model benchmark harness."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ModelDescriptor:
    model_id: str
    revision: str = "unknown"
    backend: str = "unknown"
    quantization: str = "unknown"
    context_length: int | None = None
    hardware: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    category: str
    prompt: str
    checks: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> BenchmarkCase:
        required = ("case_id", "category", "prompt")
        missing = [key for key in required if not payload.get(key)]
        if missing:
            raise ValueError(f"Benchmark case missing required fields: {', '.join(missing)}")
        checks = payload.get("checks", {})
        if not isinstance(checks, dict):
            raise ValueError("Benchmark case 'checks' must be an object")
        return cls(
            case_id=str(payload["case_id"]),
            category=str(payload["category"]),
            prompt=str(payload["prompt"]),
            checks=checks,
        )


@dataclass(frozen=True)
class GenerationOutput:
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BenchmarkResult:
    case_id: str
    category: str
    model: ModelDescriptor
    output: str
    latency_ms: float
    time_to_first_token_ms: float | None
    input_tokens: int | None
    output_tokens: int | None
    tokens_per_second: float | None
    passed: bool
    checks: dict[str, bool]
    error: str | None = None
    resource_metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
