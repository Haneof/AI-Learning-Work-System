"""Versioned skill package validation and isolated execution interfaces.

Compiler/repository exports are resolved lazily so the package stays
importable where those modules are not present; the names below are
still part of the public package API.
"""

from aios_work_system.skills.registry import SkillVersionRecord, SkillVersionRegistry
from aios_work_system.skills.validator import SkillValidationReport, validate_skill_package

__all__ = [
    "ProcedureSkillSpec",
    "ProceduralSkillCompiler",
    "SkillCompilationResult",
    "SkillValidationReport",
    "SkillVersionRecord",
    "SkillVersionRegistry",
    "SkillVersionRepository",
    "StoredSkillReview",
    "StoredSkillVersion",
    "get_clean_git_commit",
    "validate_skill_package",
]

_LAZY_EXPORTS = {
    "ProcedureSkillSpec": (".compiler", "ProcedureSkillSpec"),
    "ProceduralSkillCompiler": (".compiler", "ProceduralSkillCompiler"),
    "SkillCompilationResult": (".compiler", "SkillCompilationResult"),
    "SkillVersionRepository": (".repository", "SkillVersionRepository"),
    "StoredSkillReview": (".repository", "StoredSkillReview"),
    "StoredSkillVersion": (".repository", "StoredSkillVersion"),
    "get_clean_git_commit": (".registry", "get_clean_git_commit"),
}


def __getattr__(name):
    """Lazily resolve compiler/repository exports (PEP 562)."""
    if name in _LAZY_EXPORTS:
        import importlib

        module_name, attribute = _LAZY_EXPORTS[name]
        module = importlib.import_module(module_name, __package__)
        value = getattr(module, attribute)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
