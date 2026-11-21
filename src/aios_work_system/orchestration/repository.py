"""SQLite persistence for expert-scoped task runs, audit logs, and experiences."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _required_text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required")
    return value.strip()


def _expert_ids(values: tuple[str, ...] | list[str] | None, owner: str) -> tuple[str, ...]:
    if values is None:
        return (owner,)
    cleaned: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("expert IDs must be non-empty strings")
        if value.strip() not in cleaned:
            cleaned.append(value.strip())
    if owner not in cleaned:
        cleaned.insert(0, owner)
    return tuple(cleaned)


def _shared_expert_ids(
    values: tuple[str, ...] | list[str] | None,
    owner: str,
) -> tuple[str, ...]:
    shared = _expert_ids(values, owner) if values is not None else ()
    return tuple(expert for expert in shared if expert != owner)


def _can_read(owner: str, shared_json: str, requester: str) -> bool:
    if owner == requester:
        return True
    return requester in json.loads(shared_json)


@dataclass(frozen=True)
class TaskRun:
    task_id: str
    expert_id: str
    expert_scope: tuple[str, ...]
    status: str
    started_at: str | None
    ended_at: str | None
    result_ref: str | None
    shared_with_experts: tuple[str, ...]


@dataclass(frozen=True)
class AuditLog:
    audit_id: int
    expert_id: str
    occurred_at: str
    actor: str
    action: str
    target: str
    result: str
    shared_with_experts: tuple[str, ...]


@dataclass(frozen=True)
class Experience:
    experience_id: str
    expert_id: str
    source_task_id: str
    result: str
    lesson: str
    related_skill_version: str | None
    expert_scope: tuple[str, ...]
    shared_with_experts: tuple[str, ...]
    created_at: str


class OrchestrationRepository:
    """Persist task history and learning experiences with explicit expert sharing.

    expert_scope describes specialists involved in a task but grants no read access.
    Cross-expert reads require the owning row's shared_with_experts list. This
    repository is not an authentication service: callers must derive expert_id
    from trusted application identity. Audit rows are append-only in SQLite.
    """

    _TASK_STATES = {
        "QUEUED",
        "RUNNING",
        "WAITING_APPROVAL",
        "SUCCEEDED",
        "FAILED",
        "CANCELLED",
    }
    _TRANSITIONS = {
        "QUEUED": {"RUNNING", "CANCELLED"},
        "RUNNING": {"WAITING_APPROVAL", "SUCCEEDED", "FAILED", "CANCELLED"},
        "WAITING_APPROVAL": {"RUNNING", "CANCELLED"},
    }
    _TERMINAL_STATES = {"SUCCEEDED", "FAILED", "CANCELLED"}

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        if self.database_path != ":memory:":
            Path(self.database_path).expanduser().resolve().parent.mkdir(
                parents=True, exist_ok=True
            )
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS task_runs (
                    task_id TEXT NOT NULL,
                    expert_id TEXT NOT NULL,
                    expert_scope_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT,
                    ended_at TEXT,
                    result_ref TEXT,
                    shared_with_experts_json TEXT NOT NULL,
                    PRIMARY KEY (expert_id, task_id)
                );
                CREATE INDEX IF NOT EXISTS idx_task_runs_expert_time
                    ON task_runs(expert_id, started_at, task_id);

                CREATE TABLE IF NOT EXISTS audit_logs (
                    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    expert_id TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    target TEXT NOT NULL,
                    result TEXT NOT NULL,
                    shared_with_experts_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_audit_logs_expert_time
                    ON audit_logs(expert_id, occurred_at, audit_id);
                CREATE TRIGGER IF NOT EXISTS trg_audit_logs_no_update
                    BEFORE UPDATE ON audit_logs
                    BEGIN
                        SELECT RAISE(ABORT, 'audit_logs are append-only');
                    END;
                CREATE TRIGGER IF NOT EXISTS trg_audit_logs_no_delete
                    BEFORE DELETE ON audit_logs
                    BEGIN
                        SELECT RAISE(ABORT, 'audit_logs are append-only');
                    END;

                CREATE TABLE IF NOT EXISTS experiences (
                    experience_id TEXT NOT NULL,
                    expert_id TEXT NOT NULL,
                    source_task_id TEXT NOT NULL,
                    result TEXT NOT NULL,
                    lesson TEXT NOT NULL,
                    related_skill_version TEXT,
                    expert_scope_json TEXT NOT NULL,
                    shared_with_experts_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (expert_id, experience_id),
                    FOREIGN KEY (expert_id, source_task_id)
                        REFERENCES task_runs(expert_id, task_id)
                );
                CREATE INDEX IF NOT EXISTS idx_experiences_expert_time
                    ON experiences(expert_id, created_at, experience_id);
                """
            )

    @staticmethod
    def _task_from_row(row: sqlite3.Row) -> TaskRun:
        return TaskRun(
            task_id=row["task_id"],
            expert_id=row["expert_id"],
            expert_scope=tuple(json.loads(row["expert_scope_json"])),
            status=row["status"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
            result_ref=row["result_ref"],
            shared_with_experts=tuple(json.loads(row["shared_with_experts_json"])),
        )

    @staticmethod
    def _audit_from_row(row: sqlite3.Row) -> AuditLog:
        return AuditLog(
            audit_id=int(row["audit_id"]),
            expert_id=row["expert_id"],
            occurred_at=row["occurred_at"],
            actor=row["actor"],
            action=row["action"],
            target=row["target"],
            result=row["result"],
            shared_with_experts=tuple(json.loads(row["shared_with_experts_json"])),
        )

    @staticmethod
    def _experience_from_row(row: sqlite3.Row) -> Experience:
        return Experience(
            experience_id=row["experience_id"],
            expert_id=row["expert_id"],
            source_task_id=row["source_task_id"],
            result=row["result"],
            lesson=row["lesson"],
            related_skill_version=row["related_skill_version"],
            expert_scope=tuple(json.loads(row["expert_scope_json"])),
            shared_with_experts=tuple(json.loads(row["shared_with_experts_json"])),
            created_at=row["created_at"],
        )

    @staticmethod
    def _shared_where() -> str:
        return (
            "expert_id=? OR EXISTS ("
            "SELECT 1 FROM json_each(shared_with_experts_json) WHERE value=?"
            ")"
        )

    def create_task_run(
        self,
        task_id: str,
        expert_id: str,
        *,
        expert_scope: tuple[str, ...] | list[str] | None = None,
        status: str = "RUNNING",
        started_at: str | None = None,
        shared_with_experts: tuple[str, ...] | list[str] | None = None,
    ) -> TaskRun:
        task_id = _required_text(task_id, "task_id")
        expert_id = _required_text(expert_id, "expert_id")
        if status not in {"QUEUED", "RUNNING"}:
            raise ValueError("new task runs must start in QUEUED or RUNNING")
        scope = _expert_ids(expert_scope, expert_id)
        shared = _shared_expert_ids(shared_with_experts, expert_id)
        start_time = started_at or (_now() if status == "RUNNING" else None)
        if start_time is not None:
            start_time = _required_text(start_time, "started_at")

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO task_runs
                (task_id, expert_id, expert_scope_json, status, started_at,
                 ended_at, result_ref, shared_with_experts_json)
                VALUES (?, ?, ?, ?, ?, NULL, NULL, ?)
                """,
                (
                    task_id,
                    expert_id,
                    json.dumps(scope, ensure_ascii=False),
                    status,
                    start_time,
                    json.dumps(shared, ensure_ascii=False),
                ),
            )
            row = connection.execute(
                "SELECT * FROM task_runs WHERE task_id=? AND expert_id=?",
                (task_id, expert_id),
            ).fetchone()
        return self._task_from_row(row)

    def get_task_run(self, task_id: str, expert_id: str) -> TaskRun:
        task_id = _required_text(task_id, "task_id")
        expert_id = _required_text(expert_id, "expert_id")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM task_runs WHERE task_id=? ORDER BY expert_id",
                (task_id,),
            ).fetchall()
        if not rows:
            raise KeyError(f"task run not found: {task_id}")
        for row in rows:
            if row["expert_id"] == expert_id:
                return self._task_from_row(row)
        for row in rows:
            if _can_read(row["expert_id"], row["shared_with_experts_json"], expert_id):
                return self._task_from_row(row)
        raise PermissionError("Task run belongs to another expert scope")

    def list_task_runs(
        self,
        expert_id: str,
        *,
        status: str | None = None,
        limit: int = 1000,
    ) -> list[TaskRun]:
        expert_id = _required_text(expert_id, "expert_id")
        if not 1 <= limit <= 10000:
            raise ValueError("limit must be between 1 and 10000")
        query = f"SELECT * FROM task_runs WHERE ({self._shared_where()})"
        params: list[Any] = [expert_id, expert_id]
        if status is not None:
            if status not in self._TASK_STATES:
                raise ValueError(f"unsupported task status: {status}")
            query += " AND status=?"
            params.append(status)
        query += " ORDER BY COALESCE(started_at, ''), task_id LIMIT ?"
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._task_from_row(row) for row in rows]

    def update_task_run_status(
        self,
        task_id: str,
        expert_id: str,
        status: str,
        *,
        result_ref: str | None = None,
        ended_at: str | None = None,
    ) -> TaskRun:
        task_id = _required_text(task_id, "task_id")
        expert_id = _required_text(expert_id, "expert_id")
        if status not in self._TASK_STATES:
            raise ValueError(f"unsupported task status: {status}")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM task_runs WHERE task_id=? AND expert_id=?",
                (task_id, expert_id),
            ).fetchone()
            if row is None:
                raise KeyError(f"task run not found for expert: {task_id}")
            allowed = self._TRANSITIONS.get(row["status"], set())
            if status not in allowed:
                raise ValueError(f"invalid task transition: {row['status']} -> {status}")
            start_time = row["started_at"]
            if status == "RUNNING" and start_time is None:
                start_time = _now()
            end_time = (
                _required_text(ended_at, "ended_at") if ended_at else _now()
            ) if status in self._TERMINAL_STATES else None
            saved_result_ref = (
                _required_text(result_ref, "result_ref")
                if result_ref is not None
                else row["result_ref"]
            )
            connection.execute(
                """
                UPDATE task_runs
                SET status=?, started_at=?, ended_at=?, result_ref=?
                WHERE task_id=? AND expert_id=?
                """,
                (status, start_time, end_time, saved_result_ref, task_id, expert_id),
            )
            updated = connection.execute(
                "SELECT * FROM task_runs WHERE task_id=? AND expert_id=?",
                (task_id, expert_id),
            ).fetchone()
        return self._task_from_row(updated)

    def append_audit_log(
        self,
        expert_id: str,
        actor: str,
        action: str,
        target: str,
        result: str,
        *,
        occurred_at: str | None = None,
        shared_with_experts: tuple[str, ...] | list[str] | None = None,
    ) -> AuditLog:
        expert_id = _required_text(expert_id, "expert_id")
        actor = _required_text(actor, "actor")
        action = _required_text(action, "action")
        target = _required_text(target, "target")
        result = _required_text(result, "result")
        timestamp = _required_text(occurred_at, "occurred_at") if occurred_at else _now()
        shared = _shared_expert_ids(shared_with_experts, expert_id)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO audit_logs
                (expert_id, occurred_at, actor, action, target, result,
                 shared_with_experts_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    expert_id,
                    timestamp,
                    actor,
                    action,
                    target,
                    result,
                    json.dumps(shared, ensure_ascii=False),
                ),
            )
            row = connection.execute(
                "SELECT * FROM audit_logs WHERE audit_id=?",
                (cursor.lastrowid,),
            ).fetchone()
        return self._audit_from_row(row)

    def get_audit_log(self, audit_id: int, expert_id: str) -> AuditLog:
        expert_id = _required_text(expert_id, "expert_id")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM audit_logs WHERE audit_id=?",
                (audit_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"audit log not found: {audit_id}")
        if not _can_read(row["expert_id"], row["shared_with_experts_json"], expert_id):
            raise PermissionError("Audit log belongs to another expert scope")
        return self._audit_from_row(row)

    def list_audit_logs(self, expert_id: str, *, limit: int = 1000) -> list[AuditLog]:
        expert_id = _required_text(expert_id, "expert_id")
        if not 1 <= limit <= 10000:
            raise ValueError("limit must be between 1 and 10000")
        query = (
            "SELECT * FROM audit_logs WHERE ("
            + self._shared_where()
            + ") ORDER BY occurred_at, audit_id LIMIT ?"
        )
        with self._connect() as connection:
            rows = connection.execute(query, (expert_id, expert_id, limit)).fetchall()
        return [self._audit_from_row(row) for row in rows]

    def add_experience(
        self,
        expert_id: str,
        source_task_id: str,
        result: str,
        lesson: str,
        *,
        related_skill_version: str | None = None,
        expert_scope: tuple[str, ...] | list[str] | None = None,
        shared_with_experts: tuple[str, ...] | list[str] | None = None,
        experience_id: str | None = None,
    ) -> Experience:
        expert_id = _required_text(expert_id, "expert_id")
        source_task_id = _required_text(source_task_id, "source_task_id")
        result = _required_text(result, "result")
        lesson = _required_text(lesson, "lesson")
        skill_version = (
            _required_text(related_skill_version, "related_skill_version")
            if related_skill_version is not None
            else None
        )
        experience_id = (
            _required_text(experience_id, "experience_id")
            if experience_id
            else str(uuid.uuid4())
        )
        shared = _shared_expert_ids(shared_with_experts, expert_id)
        with self._connect() as connection:
            task = connection.execute(
                """
                SELECT expert_scope_json FROM task_runs
                WHERE task_id=? AND expert_id=?
                """,
                (source_task_id, expert_id),
            ).fetchone()
            if task is None:
                raise KeyError("experience source task must belong to the same expert")
            inherited_scope = tuple(json.loads(task["expert_scope_json"]))
            scope = (
                _expert_ids(expert_scope, expert_id)
                if expert_scope is not None
                else inherited_scope
            )
            connection.execute(
                """
                INSERT INTO experiences
                (experience_id, expert_id, source_task_id, result, lesson,
                 related_skill_version, expert_scope_json, shared_with_experts_json,
                 created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    experience_id,
                    expert_id,
                    source_task_id,
                    result,
                    lesson,
                    skill_version,
                    json.dumps(scope, ensure_ascii=False),
                    json.dumps(shared, ensure_ascii=False),
                    _now(),
                ),
            )
            row = connection.execute(
                "SELECT * FROM experiences WHERE experience_id=? AND expert_id=?",
                (experience_id, expert_id),
            ).fetchone()
        return self._experience_from_row(row)

    def get_experience(self, experience_id: str, expert_id: str) -> Experience:
        experience_id = _required_text(experience_id, "experience_id")
        expert_id = _required_text(expert_id, "expert_id")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM experiences WHERE experience_id=? ORDER BY expert_id",
                (experience_id,),
            ).fetchall()
        if not rows:
            raise KeyError(f"experience not found: {experience_id}")
        for row in rows:
            if row["expert_id"] == expert_id:
                return self._experience_from_row(row)
        for row in rows:
            if _can_read(row["expert_id"], row["shared_with_experts_json"], expert_id):
                return self._experience_from_row(row)
        raise PermissionError("Experience belongs to another expert scope")

    def list_experiences(self, expert_id: str, *, limit: int = 1000) -> list[Experience]:
        expert_id = _required_text(expert_id, "expert_id")
        if not 1 <= limit <= 10000:
            raise ValueError("limit must be between 1 and 10000")
        query = (
            "SELECT * FROM experiences WHERE ("
            + self._shared_where()
            + ") ORDER BY created_at, experience_id LIMIT ?"
        )
        with self._connect() as connection:
            rows = connection.execute(query, (expert_id, expert_id, limit)).fetchall()
        return [self._experience_from_row(row) for row in rows]
