"""Docker command builder for a constrained, network-disabled skill test run."""

from __future__ import annotations

import re
import subprocess
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from aios_work_system.skills.validator import validate_skill_package


class SandboxUnavailableError(RuntimeError):
    """Raised when the configured sandbox runtime is unavailable."""


@dataclass(frozen=True)
class SandboxResult:
    package_hash: str
    image_digest: str
    exit_code: int | None
    timed_out: bool
    stdout: str
    stderr: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class DockerSandboxRunner:
    def __init__(self, docker_binary: str = "docker") -> None:
        self.docker_binary = docker_binary

    def build_command(
        self,
        package_path: str | Path,
        script_path: str,
        image_digest: str,
        memory_limit: str = "256m",
        cpu_limit: str = "1",
        timeout_seconds: int = 60,
        container_name: str | None = None,
    ) -> list[str]:
        root = Path(package_path).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise ValueError("Skill package path must be a directory")
        if not (
            re.fullmatch(r".+@sha256:[0-9a-f]{64}", image_digest)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", image_digest)
        ):
            raise ValueError(
                "Sandbox image must be pinned by an immutable sha256 digest or local image ID"
            )
        if not re.fullmatch(r"[1-9][0-9]{0,3}[mMgG]", memory_limit):
            raise ValueError("memory_limit must be a positive Docker memory value such as 256m")
        memory_number = int(memory_limit[:-1])
        memory_unit = memory_limit[-1].lower()
        memory_mb = memory_number * (1024 if memory_unit == "g" else 1)
        if memory_mb > 2048:
            raise ValueError("memory_limit must not exceed 2048m or 2g")
        if not re.fullmatch(r"(?:0?\.[0-9]+|[1-2](?:\.[0-9]+)?)", cpu_limit):
            raise ValueError("cpu_limit must be greater than 0 and no more than 2")
        if not 0 < float(cpu_limit) <= 2:
            raise ValueError("cpu_limit must be greater than 0 and no more than 2")
        relative_script = Path(script_path)
        if relative_script.is_absolute() or ".." in relative_script.parts:
            raise ValueError("Script path must stay inside the skill package")
        script = (root / relative_script).resolve(strict=True)
        try:
            script.relative_to(root)
        except ValueError as exc:
            raise ValueError("Script path escapes skill package") from exc
        if not script.is_file() or script.suffix != ".py":
            raise ValueError("Sandbox entrypoint must be an existing Python script")
        if timeout_seconds < 1 or timeout_seconds > 600:
            raise ValueError("timeout_seconds must be between 1 and 600")
        if container_name and not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}", container_name):
            raise ValueError("container_name contains unsupported characters")

        mount = f"type=bind,src={root},dst=/workspace,readonly"
        command = [
            self.docker_binary,
            "run",
            "--pull=never",
            "--rm",
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--pids-limit=64",
            f"--memory={memory_limit}",
            f"--cpus={cpu_limit}",
            "--user=65534:65534",
            f"--mount={mount}",
            "--tmpfs=/tmp:rw,noexec,nosuid,size=64m",
            "--tmpfs=/workspace/output:rw,noexec,nosuid,size=64m",
            "--workdir=/workspace",
        ]
        if container_name:
            command.append(f"--name={container_name}")
        command.extend([image_digest, "python", str(relative_script.as_posix())])
        return command

    def _ensure_runtime_available(self) -> None:
        """Fail explicitly when the Docker CLI or its daemon is unavailable."""
        try:
            completed = subprocess.run(
                [self.docker_binary, "info", "--format", "{{.ServerVersion}}"],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
        except FileNotFoundError as exc:
            raise SandboxUnavailableError(
                "Docker is not available. Install Docker Desktop or configure a sandbox runtime."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise SandboxUnavailableError(
                "Docker daemon did not respond to docker info within 10 seconds"
            ) from exc
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "unknown Docker daemon error").strip()
            raise SandboxUnavailableError(f"Docker daemon is unavailable: {detail[-1000:]}")

    def run(
        self,
        package_path: str | Path,
        script_path: str,
        image_digest: str,
        package_hash: str,
        timeout_seconds: int = 60,
    ) -> SandboxResult:
        report = validate_skill_package(package_path)
        if not report.passed:
            raise ValueError("Skill package failed static validation: " + "; ".join(report.errors))
        if report.package_hash != package_hash:
            raise ValueError("Skill package changed after validation; package hash mismatch")

        container_name = f"aios-skill-{uuid.uuid4().hex[:12]}"
        command = self.build_command(
            package_path=package_path,
            script_path=script_path,
            image_digest=image_digest,
            timeout_seconds=timeout_seconds,
            container_name=container_name,
        )
        self._ensure_runtime_available()
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise SandboxUnavailableError(
                "Docker is not available. Install Docker Desktop or configure a sandbox runtime."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            cleanup_error = ""
            try:
                cleanup = subprocess.run(
                    [self.docker_binary, "rm", "--force", container_name],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=10,
                )
                if cleanup.returncode != 0:
                    detail = cleanup.stderr.strip()
                    if "no such container" not in detail.lower():
                        cleanup_error = detail
            except (FileNotFoundError, subprocess.TimeoutExpired) as cleanup_exc:
                cleanup_error = str(cleanup_exc)
            stderr = str(exc.stderr or "")[-4000:]
            if cleanup_error:
                stderr = f"{stderr}\nContainer cleanup warning: {cleanup_error}"[-4000:]
            return SandboxResult(
                package_hash=package_hash,
                image_digest=image_digest,
                exit_code=None,
                timed_out=True,
                stdout=str(exc.stdout or "")[-4000:],
                stderr=stderr,
            )
        return SandboxResult(
            package_hash=package_hash,
            image_digest=image_digest,
            exit_code=completed.returncode,
            timed_out=False,
            stdout=completed.stdout[-4000:],
            stderr=completed.stderr[-4000:],
        )
