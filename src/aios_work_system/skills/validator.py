"""Static skill package validation; this module never executes skill code."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

REQUIRED_FIELDS = {
    "id",
    "version",
    "goal",
    "scope",
    "inputs",
    "outputs",
    "tools",
    "permissions",
    "risk",
    "evidence",
    "tests",
}
ALLOWED_TOOLS = {"workspace.read", "workspace.write", "json.parse", "text.extract"}
ALLOWED_PERMISSIONS = {"workspace.read", "workspace.write"}
BLOCKED_IMPORTS = {
    "socket",
    "requests",
    "urllib",
    "http",
    "subprocess",
    "multiprocessing",
    "ctypes",
    "winreg",
    "importlib",
}
BLOCKED_CALLS = {"eval", "exec", "compile", "__import__", "system", "popen"}


@dataclass
class SkillValidationReport:
    package_path: str
    skill_id: str | None
    version: str | None
    package_hash: str | None
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _package_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if path.is_symlink():
            raise ValueError(f"Symlinks are not allowed in skill packages: {path}")
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _check_python_script(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as exc:
        return [f"{path.name}: invalid Python source: {exc}"]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_name = alias.name.split(".", maxsplit=1)[0]
                if root_name in BLOCKED_IMPORTS:
                    errors.append(f"{path.name}: blocked import '{root_name}'")
        elif isinstance(node, ast.ImportFrom):
            root_name = (node.module or "").split(".", maxsplit=1)[0]
            if root_name in BLOCKED_IMPORTS:
                errors.append(f"{path.name}: blocked import '{root_name}'")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in BLOCKED_CALLS:
                errors.append(f"{path.name}: blocked call '{node.func.id}'")
            if isinstance(node.func, ast.Attribute):
                if (
                    isinstance(node.func.value, ast.Name)
                    and node.func.value.id in {"os", "subprocess"}
                    and node.func.attr in BLOCKED_CALLS | {"execv", "spawn", "fork"}
                ):
                    errors.append(
                        f"{path.name}: blocked call '{node.func.value.id}.{node.func.attr}'"
                    )
    return errors


def validate_skill_package(
    package_path: str | Path,
    dependency_allowlist: frozenset[str] = frozenset(),
) -> SkillValidationReport:
    root = Path(package_path).expanduser().resolve(strict=True)
    errors: list[str] = []
    if not root.is_dir():
        raise ValueError("Skill package path must be a directory")

    for path in root.rglob("*"):
        if path.is_symlink():
            errors.append(f"Symlinks are not allowed: {path.relative_to(root)}")
        try:
            path.resolve(strict=False).relative_to(root)
        except ValueError:
            errors.append(f"Path escapes package root: {path}")

    manifest_path = root / "manifest.json"
    manifest: dict[str, object] = {}
    if not manifest_path.is_file():
        errors.append("manifest.json is required")
    else:
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("manifest root must be an object")
            manifest = payload
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            errors.append(f"manifest.json is invalid: {exc}")

    missing = sorted(REQUIRED_FIELDS - manifest.keys())
    if missing:
        errors.append(f"manifest missing required fields: {', '.join(missing)}")

    skill_id = manifest.get("id")
    version = manifest.get("version")
    if skill_id is not None and (
        not isinstance(skill_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,63}", skill_id)
    ):
        errors.append("manifest id must be a 2-64 character lowercase slug")
    if version is not None and (
        not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version)
    ):
        errors.append("manifest version must use MAJOR.MINOR.PATCH")

    for field_name in ("goal", "scope"):
        if field_name in manifest and (
            not isinstance(manifest[field_name], str) or not manifest[field_name].strip()
        ):
            errors.append(f"manifest {field_name} must be a non-empty string")
    for field_name in ("inputs", "outputs"):
        if field_name in manifest and not isinstance(manifest[field_name], dict):
            errors.append(f"manifest {field_name} must be an object")
    for field_name in ("tools", "permissions", "evidence", "tests"):
        if field_name in manifest and not isinstance(manifest[field_name], list):
            errors.append(f"manifest {field_name} must be an array")

    tools = manifest.get("tools", [])
    if isinstance(tools, list):
        for tool in tools:
            if tool not in ALLOWED_TOOLS:
                errors.append(f"tool is not allowlisted: {tool}")

    permissions = manifest.get("permissions", [])
    if isinstance(permissions, list):
        for permission in permissions:
            if permission not in ALLOWED_PERMISSIONS:
                errors.append(f"permission is not allowlisted: {permission}")

    risk = manifest.get("risk")
    if risk not in {"LOW", "MEDIUM", "HIGH", "L3"}:
        errors.append("manifest risk must be LOW, MEDIUM, HIGH, or L3")
    elif risk == "L3":
        errors.append("L3 external side effects are not executable in this PoC")

    dependencies = manifest.get("dependencies", [])
    if not isinstance(dependencies, list):
        errors.append("manifest dependencies must be an array when provided")
    else:
        for dependency in dependencies:
            if dependency not in dependency_allowlist:
                errors.append(f"dependency is not allowlisted: {dependency}")

    if not (root / "SKILL.md").is_file():
        errors.append("SKILL.md is required")

    scripts_dir = root / "scripts"
    if scripts_dir.exists():
        if not scripts_dir.is_dir():
            errors.append("scripts must be a directory")
        else:
            for script in scripts_dir.rglob("*.py"):
                errors.extend(_check_python_script(script))

    try:
        package_hash = _package_hash(root)
    except (OSError, ValueError) as exc:
        package_hash = None
        errors.append(f"could not hash skill package: {exc}")

    return SkillValidationReport(
        package_path=str(root),
        skill_id=skill_id if isinstance(skill_id, str) else None,
        version=version if isinstance(version, str) else None,
        package_hash=package_hash,
        passed=not errors,
        errors=errors,
    )
