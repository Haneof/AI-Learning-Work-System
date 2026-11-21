"""Persistent immutable SkillVersionRepository tests."""

import pytest

from aios_work_system.skills.registry import SkillVersionRecord
from aios_work_system.skills.repository import SkillVersionRepository


def _record(package_hash="a" * 64):
    return SkillVersionRecord(
        skill_id="office.account-settings",
        version="1.0.0",
        package_hash=package_hash,
    )


def test_skill_version_survives_reopen_and_is_expert_scoped(tmp_path):
    database = tmp_path / "skills.sqlite3"
    repository = SkillVersionRepository(database)
    package_dir = tmp_path / "package"
    package_dir.mkdir()

    stored = repository.register(
        _record(),
        expert_id="expert-office",
        package_path=package_dir,
    )
    reopened = SkillVersionRepository(database).get(
        "expert-office", "office.account-settings", "1.0.0"
    )

    assert stored == reopened
    assert reopened.package_hash == "a" * 64
    assert SkillVersionRepository(database).list_for_expert("another-expert") == []


def test_same_skill_version_cannot_be_registered_with_different_hash(tmp_path):
    repository = SkillVersionRepository(tmp_path / "skills.sqlite3")
    package_dir = tmp_path / "package"
    package_dir.mkdir()
    repository.register(
        _record(),
        expert_id="expert-office",
        package_path=package_dir,
    )

    with pytest.raises(ValueError, match="version increment"):
        repository.register(
            _record("b" * 64),
            expert_id="expert-office",
            package_path=package_dir,
        )


def test_draft_or_unknown_lifecycle_cannot_enter_registered_version_catalog(tmp_path):
    repository = SkillVersionRepository(tmp_path / "skills.sqlite3")
    package_dir = tmp_path / "package"
    package_dir.mkdir()

    with pytest.raises(ValueError, match="only reviewed"):
        repository.register(
            _record(),
            expert_id="expert-office",
            package_path=package_dir,
            lifecycle_status="DRAFT",
        )

    with pytest.raises(ValueError, match="only reviewed"):
        repository.register(
            _record(),
            expert_id="expert-office",
            package_path=package_dir,
            lifecycle_status="EXECUTABLE",
        )


def test_same_reviewed_skill_version_registration_is_idempotent(tmp_path):
    repository = SkillVersionRepository(tmp_path / "skills.sqlite3")
    package_dir = tmp_path / "package"
    package_dir.mkdir()
    first = repository.register(
        _record(),
        expert_id="expert-office",
        package_path=package_dir,
    )
    second = repository.register(
        _record(),
        expert_id="expert-office",
        package_path=package_dir,
    )

    assert first == second
    assert len(repository.list_for_expert("expert-office")) == 1
