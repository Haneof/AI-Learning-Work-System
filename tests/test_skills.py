"""Tests for skill package static validation and sandbox command policy."""

import json
import subprocess
from types import SimpleNamespace

import pytest

from aios_work_system.skills.registry import SkillVersionRecord, SkillVersionRegistry
from aios_work_system.skills.sandbox import DockerSandboxRunner, SandboxUnavailableError
from aios_work_system.skills.validator import validate_skill_package


def _knowledge_manifest():
    return {
        "id": "demo.skill",
        "version": "1.0.0",
        "purpose": "Parse local text while preserving source context.",
        "conditions": {
            "applicable_when": ["The input is a local text file."],
            "not_applicable_when": ["The file is remote or untrusted code."],
        },
        "judgement_criteria": ["The extracted text matches the source content."],
        "experience": {
            "success": ["Preserve the original source reference."],
            "failure": ["A missing source reference invalidates the result."],
        },
        "counterexamples": ["A plausible summary without source evidence is not verified."],
        "recovery": ["Stop and request a source file when the input is missing."],
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


def _write_knowledge_sections(root):
    (root / "SKILL.md").write_text(
        "# Demo knowledge package\n\n"
        "## Purpose\nParse local text while preserving source context.\n\n"
        "## Conditions\nApplicable to local text files; not for remote or untrusted code.\n\n"
        "## Judgement criteria\nThe extracted text matches the source.\n\n"
        "## Experience\nSuccess and failure examples are recorded.\n\n"
        "## Counterexamples\nA plausible summary without evidence is not verified.\n\n"
        "## Recovery\nStop and request a source file when missing.\n",
        encoding="utf-8",
    )


def write_valid_package(root):
    (root / "scripts").mkdir(parents=True)
    (root / "tests").mkdir()
    _write_knowledge_sections(root)
    manifest = _knowledge_manifest()
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root / "procedure.json").write_text(
        json.dumps(
            {
                "schema_version": "2.0",
                "knowledge_ids": ["demo.knowledge"],
                "annotation_status": "unreviewed",
                "evidence_refs": [],
                "suggested_steps": [],
            }
        ),
        encoding="utf-8",
    )
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


def test_validator_rejects_incomplete_knowledge_content(tmp_path):
    package = tmp_path / "incomplete"
    package.mkdir()
    write_valid_package(package)
    manifest_path = package / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["experience"].pop("failure")
    manifest["counterexamples"] = []
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = validate_skill_package(package)

    assert not report.passed
    assert any("experience.failure" in error for error in report.errors)
    assert any("counterexamples" in error for error in report.errors)


def test_validator_accepts_empty_or_partial_suggested_steps(tmp_path):
    package = tmp_path / "optional-flow"
    package.mkdir()
    write_valid_package(package)
    procedure_path = package / "procedure.json"
    procedure = json.loads(procedure_path.read_text(encoding="utf-8"))
    procedure["suggested_steps"] = [{"note": "Optional hint only."}]
    procedure_path.write_text(json.dumps(procedure), encoding="utf-8")

    report = validate_skill_package(package)

    assert report.passed, report.errors


def test_validator_rejects_legacy_mandatory_steps_key(tmp_path):
    package = tmp_path / "legacy-procedure"
    package.mkdir()
    write_valid_package(package)
    procedure_path = package / "procedure.json"
    procedure = json.loads(procedure_path.read_text(encoding="utf-8"))
    procedure["steps"] = [{"action": "must execute"}]
    procedure_path.write_text(json.dumps(procedure), encoding="utf-8")

    report = validate_skill_package(package)

    assert not report.passed
    assert any("suggested_steps instead of steps" in error for error in report.errors)


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


@pytest.mark.parametrize(
    "script",
    [
        "import os as operating_system\noperating_system.system('echo blocked')\n",
        "import os\ngetattr(os, 'system')('echo blocked')\n",
        "from os import system as run_command\nrun_command('echo blocked')\n",
        "__builtins__['eval']('1 + 1')\n",
    ],
)
def test_validator_rejects_ast_blacklist_alias_and_dynamic_lookup_bypasses(tmp_path, script):
    package = tmp_path / "unsafe-alias"
    package.mkdir()
    write_valid_package(package)
    (package / "scripts" / "run.py").write_text(script, encoding="utf-8")

    report = validate_skill_package(package)

    assert not report.passed
    assert any("blocked" in error for error in report.errors)


def test_validator_rejects_empty_manifest_evidence(tmp_path):
    package = tmp_path / "empty-evidence"
    package.mkdir()
    write_valid_package(package)
    manifest_path = package / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["evidence"] = []
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = validate_skill_package(package)

    assert not report.passed
    assert any("manifest evidence" in error and "non-empty" in error for error in report.errors)


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
    from aios_work_system.skills.registry import get_clean_git_commit

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
    from aios_work_system.skills.registry import get_clean_git_commit

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
    assert (
        "--tmpfs=/workspace/output:rw,noexec,nosuid,size=64m,"
        "uid=65534,gid=65534,mode=0700"
    ) in command
    assert (package / "output").is_dir()
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

    def fake_run(command, **_kwargs):
        if command[1] == "info":
            return SimpleNamespace(returncode=0, stdout="Docker", stderr="")
        return SimpleNamespace(returncode=0, stdout="test passed", stderr="")

    monkeypatch.setattr("aios_work_system.skills.sandbox.subprocess.run", fake_run)

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
        if command[1] == "info":
            return SimpleNamespace(returncode=0, stdout="Docker", stderr="")
        if command[1] == "run":
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
    cleanup_commands = [command for command in commands if command[1:3] == ["rm", "--force"]]
    assert len(cleanup_commands) == 1


def test_sandbox_reports_unavailable_when_docker_cli_is_missing(tmp_path, monkeypatch):
    package = tmp_path / "valid"
    package.mkdir()
    write_valid_package(package)
    report = validate_skill_package(package)

    def missing_docker(*_args, **_kwargs):
        raise FileNotFoundError("docker")

    monkeypatch.setattr("aios_work_system.skills.sandbox.subprocess.run", missing_docker)

    with pytest.raises(SandboxUnavailableError, match="Docker is not available"):
        DockerSandboxRunner().run(
            package,
            "scripts/run.py",
            "python@sha256:" + "a" * 64,
            package_hash=report.package_hash,
        )
