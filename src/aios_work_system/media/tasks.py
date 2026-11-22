"""Small JSON task journal for bounded retry and crash-safe resume."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

T = TypeVar("T")


class MediaTaskError(RuntimeError):
    """Raised when a journaled media task exhausts its retry budget."""


class TaskJournalError(RuntimeError):
    """Raised when a task journal cannot be read or decoded."""


@dataclass
class TaskRecord:
    task_id: str
    operation: str
    state: str
    attempts: int
    max_attempts: int
    elapsed_ms: float | None = None
    error: str | None = None
    updated_at: str = ""


class TaskJournal:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.records: dict[str, TaskRecord] = {}
        if self.path.exists():
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise TaskJournalError(
                    f"Task journal at {self.path} is unreadable or contains invalid JSON: {exc}"
                ) from exc
            if not isinstance(payload, dict):
                raise TaskJournalError(f"Task journal at {self.path} must contain a JSON object")
            try:
                self.records = {
                    task_id: TaskRecord(**record) for task_id, record in payload.items()
                }
            except (AttributeError, TypeError) as exc:
                raise TaskJournalError(
                    f"Task journal at {self.path} contains an invalid task record: {exc}"
                ) from exc

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        temporary.write_text(
            json.dumps(
                {key: asdict(value) for key, value in self.records.items()},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        temporary.replace(self.path)

    def run(
        self,
        task_id: str,
        operation: str,
        action: Callable[[], T],
        max_attempts: int = 2,
    ) -> T | None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        previous = self.records.get(task_id)
        if previous and previous.operation != operation:
            raise ValueError(f"Task ID {task_id} is already registered for {previous.operation}")
        if previous and previous.state == "SUCCEEDED":
            return None

        attempts = previous.attempts if previous else 0
        if previous and previous.state == "RUNNING":
            attempts -= 1
        if attempts >= max_attempts:
            raise MediaTaskError(f"Task {task_id} exhausted {max_attempts} attempts")

        while attempts < max_attempts:
            attempts += 1
            record = TaskRecord(
                task_id=task_id,
                operation=operation,
                state="RUNNING",
                attempts=attempts,
                max_attempts=max_attempts,
                updated_at=datetime.now(UTC).isoformat(),
            )
            self.records[task_id] = record
            self._save()
            started = time.perf_counter()
            try:
                result = action()
            except Exception as exc:
                record.state = "FAILED"
                record.error = f"{type(exc).__name__}: {exc}"
                record.elapsed_ms = (time.perf_counter() - started) * 1000
                record.updated_at = datetime.now(UTC).isoformat()
                self._save()
                if attempts >= max_attempts:
                    raise MediaTaskError(
                        f"Task {task_id} failed after {attempts} attempts: {record.error}"
                    ) from exc
            else:
                record.state = "SUCCEEDED"
                record.error = None
                record.elapsed_ms = (time.perf_counter() - started) * 1000
                record.updated_at = datetime.now(UTC).isoformat()
                self._save()
                return result
