"""In-memory immutable skill version registry with Git provenance checks."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path


@dataclass(frozen=True)
class SkillVersionRecord:
    skill_id: str
    version: str
    package_hash: str
    git_commit: str | None = None


def get_clean_git_commit(
    package_path: str | Path,
    *,
    repository_root: str | Path | None = None,
) -> str:
    """Return HEAD only when the skill package path is clean in its Git worktree.

    Tracked, staged, untracked, and ignored files under the package path all make
    the package dirty. This prevents recording a commit that does not identify
    the exact directory content being registered.
    """
    package = Path(package_path).expanduser().resolve(strict=True)
    if not package.is_dir():
        raise ValueError("Skill package path must be a directory")

    try:
        if repository_root is None:
            root_text = subprocess.run(
                ["git", "-C", str(package), "rev-parse", "--show-toplevel"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            root = Path(root_text).resolve(strict=True)
        else:
            root = Path(repository_root).expanduser().resolve(strict=True)
            detected_root = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            if Path(detected_root).resolve(strict=True) != root:
                raise ValueError("repository_root must be the Git worktree root")

        relative_package = package.relative_to(root)
        commit = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", commit):
            raise ValueError("Git returned an invalid commit object ID")

        relative_path = relative_package.as_posix() or "."
        status = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
                "--ignored=matching",
                "--",
                relative_path,
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except ValueError:
        raise
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError(f"Could not verify skill package Git state: {exc}") from exc

    if status:
        raise ValueError(
            "Skill package worktree is dirty; commit or remove package changes before registration"
        )
    return commit


class SkillVersionRegistry:
    def __init__(self) -> None:
        self._versions: dict[tuple[str, str], SkillVersionRecord] = {}

    def register(
        self,
        record: SkillVersionRecord,
        *,
        package_path: str | Path,
        repository_root: str | Path | None = None,
    ) -> None:
        detected_commit = get_clean_git_commit(
            package_path,
            repository_root=repository_root,
        )
        if record.git_commit is not None and record.git_commit != detected_commit:
            raise ValueError("SkillVersionRecord git_commit does not match clean worktree HEAD")

        stored_record = replace(record, git_commit=detected_commit)
        key = (stored_record.skill_id, stored_record.version)
        existing = self._versions.get(key)
        if existing and existing.package_hash != stored_record.package_hash:
            raise ValueError(
                "Skill content changed without a version increment; create a new version"
            )
        if existing and existing.git_commit != stored_record.git_commit:
            raise ValueError("Skill version is already bound to another Git commit")
        self._versions[key] = stored_record

    def get(self, skill_id: str, version: str) -> SkillVersionRecord:
        return self._versions[(skill_id, version)]
