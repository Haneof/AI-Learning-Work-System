"""Testable orchestration helpers for the Brain/Hands CLI entry point."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


class RunLoopConfigurationError(ValueError):
    """Raised when run-loop inputs or runtime configuration are invalid."""


@dataclass(frozen=True, slots=True)
class RunLoopResult:
    """CLI-facing result returned after a workflow run has been persisted."""

    exit_code: int
    report_path: Path
    report: Any
