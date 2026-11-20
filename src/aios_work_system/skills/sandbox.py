"""Docker command builder for a constrained, network-disabled skill test run."""

from __future__ import annotations

import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


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
    ) -> list[str]:
        root = Path(package_path).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise ValueError("Skill package path must be a directory")
        if not re.fullmatch(r".+@sha256:[0-9a-f]{64}", image_digest):
            raise ValueError("Sandbox image must be pinned by an immutable sha256 digest")
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

        mount = f"type=bind,src={root},dst=/workspace,readonly"
        return [
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
            "--workdir=/workspace",
            image_digest,
            "python",
            str(relative_script.as_posix()),
        ]

    def run(
        self,
        package_path: str | Path,
        script_path: str,
        image_digest: str,
        package_hash: str,
        timeout_seconds: int = 60,
    ) -> SandboxResult:
        command = self.build_command(
            package_path=package_path,
            script_path=script_path,
            image_digest=image_digest,
            timeout_seconds=timeout_seconds,
        )
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
            return SandboxResult(
                package_hash=package_hash,
                image_digest=image_digest,
                exit_code=None,
                timed_out=True,
                stdout=str(exc.stdout or "")[-4000:],
                stderr=str(exc.stderr or "")[-4000:],
            )
        return SandboxResult(
            package_hash=package_hash,
            image_digest=image_digest,
            exit_code=completed.returncode,
            timed_out=False,
            stdout=completed.stdout[-4000:],
            stderr=completed.stderr[-4000:],
        )
