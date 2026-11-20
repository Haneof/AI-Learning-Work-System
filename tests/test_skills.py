"""Tests for skill package static validation and sandbox command policy."""

import json

import pytest

from aios_work_system.skills.registry import SkillVersionRecord, SkillVersionRegistry
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


def test_version_registry_rejects_mutating_an_existing_version():
    registry = SkillVersionRegistry()
    registry.register(SkillVersionRecord("demo.skill", "1.0.0", "hash-a"))

    with pytest.raises(ValueError):
        registry.register(SkillVersionRecord("demo.skill", "1.0.0", "hash-b"))

    registry.register(SkillVersionRecord("demo.skill", "1.0.1", "hash-b"))
    assert registry.get("demo.skill", "1.0.1").package_hash == "hash-b"


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
