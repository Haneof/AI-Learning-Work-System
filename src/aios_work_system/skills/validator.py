"""Static knowledge package validation; this module never executes package code."""

from __future__ import annotations

import ast
import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

REQUIRED_FIELDS = {
    "id",
    "version",
    "purpose",
    "conditions",
    "judgement_criteria",
    "experience",
    "counterexamples",
    "recovery",
    "scope",
    "inputs",
    "outputs",
    "tools",
    "permissions",
    "risk",
    "evidence",
    "tests",
}
REQUIRED_SKILL_SECTIONS = (
    "## purpose",
    "## conditions",
    "## judgement criteria",
    "## experience",
    "## counterexamples",
    "## recovery",
)
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
            raise ValueError(f"Symlinks are not allowed in knowledge packages: {path}")
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

    blocked_attributes = BLOCKED_CALLS | {"execv", "spawn", "fork"}
    module_aliases: dict[str, str] = {}
    call_aliases: dict[str, str] = {}
    dynamic_lookup_aliases: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_name = alias.name.split(".", maxsplit=1)[0]
                local_name = alias.asname or alias.name.split(".", maxsplit=1)[0]
                module_aliases[local_name] = alias.name
                if root_name in BLOCKED_IMPORTS:
                    errors.append(f"{path.name}: blocked import '{root_name}'")
        elif isinstance(node, ast.ImportFrom):
            imported_module = node.module or ""
            root_name = imported_module.split(".", maxsplit=1)[0]
            if root_name in BLOCKED_IMPORTS:
                errors.append(f"{path.name}: blocked import '{root_name}'")
            for alias in node.names:
                local_name = alias.asname or alias.name
                if root_name in {"os", "subprocess", "builtins"} and alias.name in blocked_attributes:
                    call_aliases[local_name] = f"{root_name}.{alias.name}"
                if root_name == "builtins" and alias.name in {"getattr", "__getattribute__"}:
                    dynamic_lookup_aliases.add(local_name)

    for node in ast.walk(tree):
        assignment = (
            node.value
            if isinstance(node, ast.Assign)
            else node.value
            if isinstance(node, ast.AnnAssign)
            else None
        )
        if isinstance(assignment, ast.Attribute) and isinstance(assignment.value, ast.Name):
            imported_module = module_aliases.get(assignment.value.id, assignment.value.id)
            root_name = imported_module.split(".", maxsplit=1)[0]
            if root_name in {"os", "subprocess", "builtins"} and assignment.attr in blocked_attributes:
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name):
                        call_aliases[target.id] = f"{root_name}.{assignment.attr}"

    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "__builtins__":
            errors.append(f"{path.name}: blocked builtins access '__builtins__'")
        elif isinstance(node, ast.Attribute):
            if node.attr == "__builtins__":
                errors.append(f"{path.name}: blocked builtins access '__builtins__'")
            elif node.attr == "__dict__" and isinstance(node.value, ast.Name):
                imported_module = module_aliases.get(node.value.id, node.value.id)
                if imported_module.split(".", maxsplit=1)[0] == "builtins":
                    errors.append(f"{path.name}: blocked builtins namespace access")
        elif isinstance(node, ast.Call):
            function = node.func
            if isinstance(function, ast.Name):
                if function.id in BLOCKED_CALLS:
                    errors.append(f"{path.name}: blocked call '{function.id}'")
                elif function.id in call_aliases:
                    errors.append(
                        f"{path.name}: blocked call '{call_aliases[function.id]}' via import alias"
                    )
                elif function.id in dynamic_lookup_aliases or function.id == "getattr":
                    errors.append(f"{path.name}: blocked dynamic attribute access '{function.id}'")
            elif isinstance(function, ast.Attribute):
                if function.attr in {"getattr", "__getattribute__"}:
                    errors.append(
                        f"{path.name}: blocked dynamic attribute access '{function.attr}'"
                    )
                elif isinstance(function.value, ast.Name):
                    imported_module = module_aliases.get(
                        function.value.id,
                        function.value.id,
                    )
                    root_name = imported_module.split(".", maxsplit=1)[0]
                    if root_name in {"os", "subprocess", "builtins"} and function.attr in blocked_attributes:
                        errors.append(
                            f"{path.name}: blocked call '{root_name}.{function.attr}'"
                        )
    return errors
def _validate_relative_file(root: Path, relative_value: object, label: str) -> list[str]:
    if not isinstance(relative_value, str) or not relative_value.strip():
        return [f"{label} must be a non-empty relative path"]
    relative = Path(relative_value)
    if relative.is_absolute() or ".." in relative.parts:
        return [f"{label} path traversal is not allowed: {relative_value}"]
    target = (root / relative).resolve(strict=False)
    try:
        target.relative_to(root)
    except ValueError:
        return [f"{label} path escapes package root: {relative_value}"]
    if not target.is_file():
        return [f"{label} file does not exist: {relative_value}"]
    return []


def _validate_non_empty_string(value: object, label: str) -> list[str]:
    if not isinstance(value, str) or not value.strip():
        return [f"manifest {label} must be a non-empty string"]
    return []


def _validate_string_array(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        return [f"manifest {label} must be a non-empty string array"]
    errors: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"manifest {label}[{index}] must be a non-empty string")
    return errors


def _validate_knowledge_sections(manifest: dict[str, object]) -> list[str]:
    errors = _validate_non_empty_string(manifest.get("purpose"), "purpose")

    conditions = manifest.get("conditions")
    if not isinstance(conditions, dict):
        errors.append("manifest conditions must be an object")
    else:
        errors.extend(
            _validate_string_array(
                conditions.get("applicable_when"),
                "conditions.applicable_when",
            )
        )
        errors.extend(
            _validate_string_array(
                conditions.get("not_applicable_when"),
                "conditions.not_applicable_when",
            )
        )

    errors.extend(_validate_string_array(manifest.get("judgement_criteria"), "judgement_criteria"))

    experience = manifest.get("experience")
    if not isinstance(experience, dict):
        errors.append("manifest experience must be an object")
    else:
        errors.extend(_validate_string_array(experience.get("success"), "experience.success"))
        errors.extend(_validate_string_array(experience.get("failure"), "experience.failure"))

    errors.extend(_validate_string_array(manifest.get("counterexamples"), "counterexamples"))
    errors.extend(_validate_string_array(manifest.get("recovery"), "recovery"))
    return errors


def _validate_procedure(root: Path) -> list[str]:
    path = root / "procedure.json"
    if not path.is_file():
        return ["procedure.json is required"]
    try:
        procedure = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return [f"procedure.json is invalid: {exc}"]
    if not isinstance(procedure, dict):
        return ["procedure.json root must be an object"]

    errors: list[str] = []
    if procedure.get("schema_version") != "2.0":
        errors.append("procedure.json schema_version must be '2.0'")
    if "steps" in procedure:
        errors.append("procedure.json must use suggested_steps instead of steps")
    suggested_steps = procedure.get("suggested_steps")
    if not isinstance(suggested_steps, list):
        errors.append("procedure.json suggested_steps must be an array")
    else:
        for index, step in enumerate(suggested_steps):
            if not isinstance(step, dict):
                errors.append(f"procedure.json suggested_steps[{index}] must be an object")

    evidence_refs = procedure.get("evidence_refs")
    if not isinstance(evidence_refs, list):
        errors.append("procedure.json evidence_refs must be an array")
    else:
        for index, evidence in enumerate(evidence_refs):
            if not isinstance(evidence, dict):
                errors.append(f"procedure.json evidence_refs[{index}] must be an object")
                continue
            for field_name in ("kind", "ref"):
                value = evidence.get(field_name)
                if not isinstance(value, str) or not value.strip():
                    errors.append(
                        f"procedure.json evidence_refs[{index}].{field_name} must be non-empty"
                    )
            timestamp = evidence.get("timestamp_seconds")
            if (
                isinstance(timestamp, bool)
                or not isinstance(timestamp, (int, float))
                or not math.isfinite(timestamp)
                or timestamp < 0
            ):
                errors.append(
                    f"procedure.json evidence_refs[{index}].timestamp_seconds must be non-negative"
                )
    return errors


def validate_skill_package(
    package_path: str | Path,
    dependency_allowlist: frozenset[str] = frozenset(),
) -> SkillValidationReport:
    root = Path(package_path).expanduser().resolve(strict=True)
    errors: list[str] = []
    if not root.is_dir():
        raise ValueError("Knowledge package path must be a directory")

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

    errors.extend(_validate_knowledge_sections(manifest))
    errors.extend(_validate_non_empty_string(manifest.get("scope"), "scope"))

    for field_name in ("inputs", "outputs"):
        if field_name in manifest and not isinstance(manifest[field_name], dict):
            errors.append(f"manifest {field_name} must be an object")

    for field_name in ("tools", "permissions", "evidence", "tests"):
        if field_name in manifest and not isinstance(manifest[field_name], list):
            errors.append(f"manifest {field_name} must be an array")

    tools = manifest.get("tools", [])
    if isinstance(tools, list):
        for tool in tools:
            if not isinstance(tool, str) or tool not in ALLOWED_TOOLS:
                errors.append(f"tool is not allowlisted: {tool}")

    evidence = manifest.get("evidence", [])
    if isinstance(evidence, list):
        errors.extend(_validate_string_array(evidence, "evidence"))

    permissions = manifest.get("permissions", [])
    if isinstance(permissions, list):
        for permission in permissions:
            if not isinstance(permission, str) or permission not in ALLOWED_PERMISSIONS:
                errors.append(f"permission is not allowlisted: {permission}")

    risk = manifest.get("risk")
    if not isinstance(risk, str) or risk not in {"LOW", "MEDIUM", "HIGH", "L3"}:
        errors.append("manifest risk must be LOW, MEDIUM, HIGH, or L3")
    elif risk == "L3":
        errors.append("L3 external side effects are not executable in this PoC")

    dependencies = manifest.get("dependencies", [])
    if not isinstance(dependencies, list):
        errors.append("manifest dependencies must be an array when provided")
    else:
        for dependency in dependencies:
            if not isinstance(dependency, str) or dependency not in dependency_allowlist:
                errors.append(f"dependency is not allowlisted: {dependency}")

    skill_path = root / "SKILL.md"
    if not skill_path.is_file():
        errors.append("SKILL.md is required")
    else:
        try:
            skill_text = skill_path.read_text(encoding="utf-8").lower()
            for heading in REQUIRED_SKILL_SECTIONS:
                if heading not in skill_text:
                    errors.append(f"SKILL.md is missing required knowledge section: {heading}")
        except UnicodeDecodeError as exc:
            errors.append(f"SKILL.md is not valid UTF-8: {exc}")

    errors.extend(_validate_procedure(root))

    tests = manifest.get("tests", [])
    if isinstance(tests, list):
        if not tests:
            errors.append("manifest tests must include at least one test file")
        for test_path in tests:
            errors.extend(_validate_relative_file(root, test_path, "test"))

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
        errors.append(f"could not hash knowledge package: {exc}")

    return SkillValidationReport(
        package_path=str(root),
        skill_id=skill_id if isinstance(skill_id, str) else None,
        version=version if isinstance(version, str) else None,
        package_hash=package_hash,
        passed=not errors,
        errors=errors,
    )
