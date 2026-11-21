"""Real Docker security regression tests.

Run explicitly in the Docker-enabled CI job with AIOS_SANDBOX_IMAGE_DIGEST set
to the immutable local image ID produced by that job.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from aios_work_system.skills import sandbox, validator


CONTRACT_SCRIPT = "tests/test_procedure_contract.py"


def _pinned_image_id() -> str:
    image_id = os.environ.get("AIOS_SANDBOX_IMAGE_DIGEST", "")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise AssertionError(
            "AIOS_SANDBOX_IMAGE_DIGEST must be the immutable sha256 image ID "
            "created by the Docker CI job"
        )
    return image_id


def _assert_no_sandbox_containers() -> None:
    result = subprocess.run(
        ["docker", "ps", "-aq", "--filter", "name=aios-skill-"],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    assert not result.stdout.strip(), f"Sandbox container remains: {result.stdout}"


def _run_package(
    package: Path,
    script: str,
    *,
    timeout_seconds: int = 30,
) -> SandboxResult:
    contract_path = package / CONTRACT_SCRIPT
    contract_path.write_text(script, encoding="utf-8")
    report = validator.validate_skill_package(package)
    assert report.passed, report.errors
    assert report.package_hash is not None

    result = sandbox.DockerSandboxRunner().run(
        package_path=package,
        script_path=CONTRACT_SCRIPT,
        image_digest=_pinned_image_id(),
        package_hash=report.package_hash,
        timeout_seconds=timeout_seconds,
    )
    assert isinstance(result, sandbox.SandboxResult)
    assert result.package_hash == report.package_hash
    assert result.image_digest == _pinned_image_id()
    assert not result.stderr or result.exit_code != 0 or result.timed_out
    return result


def test_compiled_pvd_contract_really_executes_inside_docker(
    compiled_pvd_skill_factory,
):
    package = compiled_pvd_skill_factory()
    report = validator.validate_skill_package(package)
    assert report.passed, report.errors
    assert report.package_hash

    result = sandbox.DockerSandboxRunner().run(
        package_path=package,
        script_path=CONTRACT_SCRIPT,
        image_digest=_pinned_image_id(),
        package_hash=report.package_hash,
        timeout_seconds=30,
    )

    assert result.exit_code == 0
    assert not result.timed_out
    assert result.package_hash == report.package_hash
    assert result.image_digest == _pinned_image_id()
    assert "PVD_PROCEDURE_CONTRACT_OK" in result.stdout
    _assert_no_sandbox_containers()


def test_network_access_is_blocked_inside_container(compiled_pvd_skill_factory):
    package = compiled_pvd_skill_factory()
    script = """\
import socket

connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
connection.settimeout(2)
try:
    connection.connect(("1.1.1.1", 53))
except OSError:
    print("NETWORK_BLOCKED")
else:
    raise AssertionError("network connection unexpectedly succeeded")
finally:
    connection.close()
"""
    result = _run_package(package, script)
    assert result.exit_code == 0
    assert "NETWORK_BLOCKED" in result.stdout
    _assert_no_sandbox_containers()


def test_package_mount_and_container_rootfs_are_read_only_but_tmpfs_is_writable(
    compiled_pvd_skill_factory,
):
    package = compiled_pvd_skill_factory()
    script = """\
from pathlib import Path

denied_paths = (
    Path("/workspace/pvd-write-must-fail.txt"),
    Path("/pvd-rootfs-write-must-fail.txt"),
)
for target in denied_paths:
    try:
        target.write_text("forbidden", encoding="utf-8")
    except OSError:
        print(f"WRITE_BLOCKED:{target}")
    else:
        raise AssertionError(f"write unexpectedly succeeded: {target}")

Path("/tmp/pvd-sandbox-positive-control.txt").write_text("ok", encoding="utf-8")
print("TMPFS_WRITE_ALLOWED")
"""
    result = _run_package(package, script)
    assert result.exit_code == 0
    assert "WRITE_BLOCKED:/workspace/" in result.stdout
    assert "WRITE_BLOCKED:/pvd-rootfs-" in result.stdout
    assert "TMPFS_WRITE_ALLOWED" in result.stdout
    _assert_no_sandbox_containers()


def test_container_runs_unprivileged_with_no_new_privileges_and_no_capabilities(
    compiled_pvd_skill_factory,
):
    package = compiled_pvd_skill_factory()
    script = """\
import os

assert os.geteuid() == 65534, f"unexpected euid: {os.geteuid()}"
status = {}
for line in open("/proc/self/status", encoding="utf-8"):
    if ":" in line:
        key, value = line.split(":", 1)
        status[key] = value.strip()
assert status.get("NoNewPrivs") == "1", status.get("NoNewPrivs")
assert status.get("CapEff") == "0000000000000000", status.get("CapEff")
try:
    os.setuid(0)
except PermissionError:
    print("PRIVILEGE_ESCALATION_BLOCKED")
else:
    raise AssertionError("process unexpectedly changed to uid 0")
print("UNPRIVILEGED_IDENTITY_CONFIRMED")
"""
    result = _run_package(package, script)
    assert result.exit_code == 0
    assert "PRIVILEGE_ESCALATION_BLOCKED" in result.stdout
    assert "UNPRIVILEGED_IDENTITY_CONFIRMED" in result.stdout
    _assert_no_sandbox_containers()


def test_timeout_kills_container_and_runner_leaves_no_residual_container(
    compiled_pvd_skill_factory,
):
    package = compiled_pvd_skill_factory()
    script = "import time\ntime.sleep(30)\n"
    result = _run_package(package, script, timeout_seconds=2)

    assert result.timed_out
    assert result.exit_code is None
    _assert_no_sandbox_containers()


def test_unpinned_image_tag_is_rejected_before_docker_execution(
    compiled_pvd_skill_factory,
):
    package = compiled_pvd_skill_factory()
    report = validator.validate_skill_package(package)
    assert report.passed and report.package_hash

    runner = sandbox.DockerSandboxRunner()
    try:
        runner.run(
            package_path=package,
            script_path=CONTRACT_SCRIPT,
            image_digest="python:latest",
            package_hash=report.package_hash,
        )
    except ValueError as exc:
        assert "pinned" in str(exc)
    else:
        raise AssertionError("unpinned image reference was accepted")
