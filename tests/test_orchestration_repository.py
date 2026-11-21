"""SQLite durability and expert-isolation tests."""

import sqlite3

import pytest

from aios_work_system.orchestration.repository import OrchestrationRepository


def _seed_expert(repository, expert_id):
    task = repository.create_task_run(
        f"task-{expert_id}",
        expert_id,
        expert_scope=(expert_id,),
    )
    audit = repository.append_audit_log(
        expert_id,
        actor=f"operator-{expert_id}",
        action="task.started",
        target=task.task_id,
        result="accepted",
    )
    experience = repository.add_experience(
        expert_id,
        task.task_id,
        result="Completed a safe practice run.",
        lesson="Verify the result before marking the task complete.",
        related_skill_version="demo.skill@1.0.0",
    )
    return task, audit, experience


def test_task_audit_and_experience_rows_are_expert_isolated(tmp_path):
    repository = OrchestrationRepository(tmp_path / "orchestration.sqlite3")
    task_a, audit_a, experience_a = _seed_expert(repository, "expert-a")
    task_b, audit_b, experience_b = _seed_expert(repository, "expert-b")

    assert [row.task_id for row in repository.list_task_runs("expert-a")] == [task_a.task_id]
    assert [row.audit_id for row in repository.list_audit_logs("expert-a")] == [audit_a.audit_id]
    assert [row.experience_id for row in repository.list_experiences("expert-a")] == [
        experience_a.experience_id
    ]

    with pytest.raises(PermissionError, match="another expert"):
        repository.get_task_run(task_b.task_id, "expert-a")
    with pytest.raises(PermissionError, match="another expert"):
        repository.get_audit_log(audit_b.audit_id, "expert-a")
    with pytest.raises(PermissionError, match="another expert"):
        repository.get_experience(experience_b.experience_id, "expert-a")


def test_explicit_sharing_is_required_to_read_another_experts_rows(tmp_path):
    repository = OrchestrationRepository(tmp_path / "orchestration.sqlite3")
    task = repository.create_task_run(
        "shared-task",
        "expert-b",
        expert_scope=("expert-b", "expert-a"),
        shared_with_experts=("expert-a",),
    )
    audit = repository.append_audit_log(
        "expert-b",
        "operator-b",
        "task.completed",
        "shared-task",
        "success",
        shared_with_experts=("expert-a",),
    )
    experience = repository.add_experience(
        "expert-b",
        "shared-task",
        "The task passed.",
        "Keep the verification step.",
        shared_with_experts=("expert-a",),
    )

    assert repository.get_task_run("shared-task", "expert-a") == task
    assert repository.get_audit_log(audit.audit_id, "expert-a") == audit
    assert repository.get_experience(experience.experience_id, "expert-a") == experience
    assert repository.list_task_runs("expert-a") == [task]
    assert repository.list_audit_logs("expert-a") == [audit]
    assert repository.list_experiences("expert-a") == [experience]


def test_audit_log_is_time_ordered_and_sqlite_enforces_append_only(tmp_path):
    database = tmp_path / "orchestration.sqlite3"
    repository = OrchestrationRepository(database)
    later = repository.append_audit_log(
        "expert-a",
        "operator",
        "later",
        "target",
        "done",
        occurred_at="2026-11-21T12:00:00+00:00",
    )
    earlier = repository.append_audit_log(
        "expert-a",
        "operator",
        "earlier",
        "target",
        "started",
        occurred_at="2026-11-21T13:00:00+02:00",
    )

    assert [row.audit_id for row in repository.list_audit_logs("expert-a")] == [
        earlier.audit_id,
        later.audit_id,
    ]
    assert earlier.occurred_at == "2026-11-21T11:00:00+00:00"
    with sqlite3.connect(database) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "UPDATE audit_logs SET result='tampered' WHERE audit_id=?",
                (later.audit_id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "DELETE FROM audit_logs WHERE audit_id=?",
                (later.audit_id,),
            )


def test_task_status_transitions_record_start_end_and_result_reference(tmp_path):
    repository = OrchestrationRepository(tmp_path / "orchestration.sqlite3")
    queued = repository.create_task_run("task-1", "expert-a", status="QUEUED")
    assert queued.started_at is None

    running = repository.update_task_run_status("task-1", "expert-a", "RUNNING")
    assert running.started_at is not None
    assert running.ended_at is None

    done = repository.update_task_run_status(
        "task-1",
        "expert-a",
        "SUCCEEDED",
        result_ref="artifact://results/task-1.json",
    )
    assert done.ended_at is not None
    assert done.result_ref == "artifact://results/task-1.json"

    with pytest.raises(ValueError, match="invalid task transition"):
        repository.update_task_run_status("task-1", "expert-a", "RUNNING")


def test_experience_must_reference_a_task_owned_by_the_same_expert(tmp_path):
    repository = OrchestrationRepository(tmp_path / "orchestration.sqlite3")
    repository.create_task_run("task-b", "expert-b")

    with pytest.raises(KeyError, match="same expert"):
        repository.add_experience(
            "expert-a",
            "task-b",
            "result",
            "lesson",
        )
