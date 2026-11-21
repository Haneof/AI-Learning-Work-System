"""Tests for skill package static validation and sandbox command policy."""

import json
import subprocess
from types import SimpleNamespace

import pytest

from aios_work_system.skills.registry import (
    SkillVersionRecord,
    SkillVersionRegistry,
    get_clean_git_commit,
)
from aios_work_system.skills.sandbox import DockerSandboxRunner
from aios_work_system.skills.validator import validate_skill_package


def write_valid_package(root):
    (root / "scripts").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "SKILL.md").write_text("# Demo skill", encoding="utf-8")
    manifest = {
        "id": "demo.skill",
        "version": "1.0.0",
        "goal": "Parse a local text file",
        "scope": "workspace",
        "inputs": {"text": "string"},
        "outputs": {"summary": "string"},
        "tools": ["text.extract"],
        "permissions": ["workspace.read"],
        "risk": "LOW",
        "evidence": ["source:example.txt"],
        "tests": ["tests/test_demo.py"],
        "dependencies": [],
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root / "scripts" / "run.py").write_text("print('ok')\n", encoding="utf-8")
    (root / "tests" / "test_demo.py").write_text(
        "def test_demo():\n    assert True\n",
        encoding="utf-8",
    )


def test_valid_skill_package_has_stable_hash(tmp_path):
    package = tmp_path / "demo"
    package.mkdir()
    write_valid_package(package)

    first = validate_skill_package(package)
    second = validate_skill_package(package)

    assert first.passed
    assert first.package_hash == second.package_hash


def test_validator_rejects_missing_fields_and_network_permission(tmp_path):
    package = tmp_path / "bad"
    package.mkdir()
    (package / "SKILL.md").write_text("# Bad", encoding="utf-8")
    (package / "manifest.json").write_text(
        json.dumps({"id": "bad", "permissions": ["network.access"]}),
        encoding="utf-8",
    )

    report = validate_skill_package(package)

    assert not report.passed
    assert any("manifest missing required fields" in error for error in report.errors)
    assert any("permission is not allowlisted" in error for error in report.errors)


def test_validator_rejects_dynamic_execution_and_network_imports(tmp_path):
    package = tmp_path / "unsafe"
    package.mkdir()
    write_valid_package(package)
    (package / "scripts" / "run.py").write_text(
        "import socket\neval('1 + 1')\n",
        encoding="utf-8",
    )

    report = validate_skill_package(package)

    assert not report.passed
    assert any("blocked import 'socket'" in error for error in report.errors)
    assert any("blocked call 'eval'" in error for error in report.errors)


def test_validator_rejects_test_path_traversal(tmp_path):
    package = tmp_path / "traversal"
    package.mkdir()
    write_valid_package(package)
    manifest_path = package / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["tests"] = ["../outside.py"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = validate_skill_package(package)

    assert not report.passed
    assert any("path traversal is not allowed" in error for error in report.errors)


def _init_git_package(tmp_path):
    repository = tmp_path / "git-repository"
    repository.mkdir()
    package = repository / "skills" / "demo"
    package.mkdir(parents=True)
    write_valid_package(package)
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    subprocess.run(
        ["git", "-C", str(repository), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repository), "config", "user.name", "Test User"],
        check=True,
    )
    subprocess.run(["git", "-C", str(repository), "add", "--all"], check=True)
    subprocess.run(
        ["git", "-C", str(repository), "commit", "-m", "Initial skill package"],
        check=True,
        capture_output=True,
        text=True,
    )
    return repository, package


def test_version_registry_records_commit_for_clean_skill_package(tmp_path):
    _repository, package = _init_git_package(tmp_path)
    expected_commit = get_clean_git_commit(package)
    registry = SkillVersionRegistry()

    registry.register(
        SkillVersionRecord("demo.skill", "1.0.0", "hash-a"),
        package_path=package,
    )

    stored = registry.get("demo.skill", "1.0.0")
    assert stored.git_commit == expected_commit
    assert len(stored.git_commit) == 40


def test_version_registry_rejects_mutating_an_existing_version(tmp_path):
    _repository, package = _init_git_package(tmp_path)
    registry = SkillVersionRegistry()
    registry.register(
        SkillVersionRecord("demo.skill", "1.0.0", "hash-a"),
        package_path=package,
    )

    with pytest.raises(ValueError, match="version increment"):
        registry.register(
            SkillVersionRecord("demo.skill", "1.0.0", "hash-b"),
            package_path=package,
        )

    registry.register(
        SkillVersionRecord("demo.skill", "1.0.1", "hash-b"),
        package_path=package,
    )
    assert registry.get("demo.skill", "1.0.1").package_hash == "hash-b"


def test_version_registry_rejects_dirty_skill_package_worktree(tmp_path):
    _repository, package = _init_git_package(tmp_path)
    (package / "SKILL.md").write_text("# Modified after commit", encoding="utf-8")
    registry = SkillVersionRegistry()

    with pytest.raises(ValueError, match="worktree is dirty"):
        get_clean_git_commit(package)
    with pytest.raises(ValueError, match="worktree is dirty"):
        registry.register(
            SkillVersionRecord("demo.skill", "1.0.0", "hash-a"),
            package_path=package,
        )
    with pytest.raises(KeyError):
        registry.get("demo.skill", "1.0.0")


def test_docker_sandbox_disables_network_and_requires_digest(tmp_path):
    package = tmp_path / "demo"
    package.mkdir()
    script = package / "scripts" / "run.py"
    script.parent.mkdir()
    script.write_text("print('safe')", encoding="utf-8")
    runner = DockerSandboxRunner()
    image = "python@sha256:" + "a" * 64

    command = runner.build_command(package, "scripts/run.py", image)

    assert "--network=none" in command
    assert "--read-only" in command
    assert "--cap-drop=ALL" in command
    assert any(argument.startswith("--memory=") for argument in command)
    with pytest.raises(ValueError):
        runner.build_command(package, "scripts/run.py", "python:latest")
    with pytest.raises(ValueError):
        runner.build_command(package, "../outside.py", image)
    with pytest.raises(ValueError):
        runner.build_command(package, "scripts/run.py", image, memory_limit="8g")


def test_sandbox_refuses_failed_static_validation(tmp_path, monkeypatch):
    package = tmp_path / "unsafe"
    package.mkdir()
    write_valid_package(package)
    (package / "scripts" / "run.py").write_text("import socket\n", encoding="utf-8")
    runner = DockerSandboxRunner()
    monkeypatch.setattr(
        "aios_work_system.skills.sandbox.subprocess.run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not execute")),
    )

    with pytest.raises(ValueError, match="failed static validation"):
        runner.run(
            package,
            "scripts/run.py",
            "python@sha256:" + "a" * 64,
            package_hash="not-a-real-hash",
        )


def test_sandbox_run_records_result_after_validation(tmp_path, monkeypatch):
    package = tmp_path / "valid"
    package.mkdir()
    write_valid_package(package)
    report = validate_skill_package(package)
    runner = DockerSandboxRunner()
    monkeypatch.setattr(
        "aios_work_system.skills.sandbox.subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout="test passed",
            stderr="",
        ),
    )

    result = runner.run(
        package,
        "scripts/run.py",
        "python@sha256:" + "a" * 64,
        package_hash=report.package_hash,
    )

    assert result.exit_code == 0
    assert not result.timed_out
    assert result.package_hash == report.package_hash


def test_sandbox_timeout_removes_container(tmp_path, monkeypatch):
    package = tmp_path / "valid"
    package.mkdir()
    write_valid_package(package)
    report = validate_skill_package(package)
    runner = DockerSandboxRunner()
    commands = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        if len(commands) == 1:
            raise subprocess.TimeoutExpired(command, timeout=1, output="partial")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("aios_work_system.skills.sandbox.subprocess.run", fake_run)
    result = runner.run(
        package,
        "scripts/run.py",
        "python@sha256:" + "a" * 64,
        package_hash=report.package_hash,
        timeout_seconds=1,
    )

    assert result.timed_out
    assert commands[1][1:3] == ["rm", "--force"]
