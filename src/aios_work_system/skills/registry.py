"""In-memory immutable skill version registry."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SkillVersionRecord:
    skill_id: str
    version: str
    package_hash: str


class SkillVersionRegistry:
    def __init__(self) -> None:
        self._versions: dict[tuple[str, str], SkillVersionRecord] = {}

    def register(self, record: SkillVersionRecord) -> None:
        key = (record.skill_id, record.version)
        existing = self._versions.get(key)
        if existing and existing.package_hash != record.package_hash:
            raise ValueError(
                "Skill content changed without a version increment; create a new version"
            )
        self._versions[key] = record

    def get(self, skill_id: str, version: str) -> SkillVersionRecord:
        return self._versions[(skill_id, version)]
