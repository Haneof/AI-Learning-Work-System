"""Model benchmark harness with pluggable inference backends."""

from aios_work_system.benchmark.backends import GenerationBackend, MockBackend
from aios_work_system.benchmark.runner import BenchmarkRunner
from aios_work_system.benchmark.types import BenchmarkCase, ModelDescriptor

__all__ = [
    "BenchmarkCase",
    "BenchmarkRunner",
    "GenerationBackend",
    "MockBackend",
    "ModelDescriptor",
]
