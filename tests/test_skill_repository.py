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


def _review(repository, *, decision="APPROVED"):
    return repository.record_review(
        expert_id="expert-office",
        skill_id="office.account-settings",
        version="1.0.0",
        spec_hash="b" * 64,
        reviewer_id="human-reviewer",
        annotator_id="content-author",
        decision=decision,
        note="Reviewed this exact procedure version.",
    )


def test_skill_version_survives_reopen_and_is_expert_scoped(tmp_path):
    database = tmp_path / "skills.sqlite3"
    repository = SkillVersionRepository(database)
    package_dir = tmp_path / "package"
    package_dir.mkdir()
    review = _review(repository)

    stored = repository.register(
        _record(),
        expert_id="expert-office",
        package_path=package_dir,
        review_id=review.review_id,
        spec_hash=review.spec_hash,
    )
    reopened = SkillVersionRepository(database).get(
        "expert-office", "office.account-settings", "1.0.0"
    )

    assert stored == reopened
    assert reopened.package_hash == "a" * 64
    assert reopened.review_id == review.review_id
    assert SkillVersionRepository(database).list_for_expert("another-expert") == []


def test_same_skill_version_cannot_be_registered_with_different_hash(tmp_path):
    repository = SkillVersionRepository(tmp_path / "skills.sqlite3")
    package_dir = tmp_path / "package"
    package_dir.mkdir()
    review = _review(repository)
    repository.register(
        _record(),
        expert_id="expert-office",
        package_path=package_dir,
        review_id=review.review_id,
        spec_hash=review.spec_hash,
    )

    with pytest.raises(ValueError, match="version increment"):
        repository.register(
            _record("c" * 64),
            expert_id="expert-office",
            package_path=package_dir,
            review_id=review.review_id,
            spec_hash=review.spec_hash,
        )


def test_draft_or_unknown_lifecycle_cannot_enter_registered_version_catalog(tmp_path):
    repository = SkillVersionRepository(tmp_path / "skills.sqlite3")
    package_dir = tmp_path / "package"
    package_dir.mkdir()
    review = _review(repository)

    with pytest.raises(ValueError, match="only reviewed"):
        repository.register(
            _record(),
            expert_id="expert-office",
            package_path=package_dir,
            review_id=review.review_id,
            spec_hash=review.spec_hash,
            lifecycle_status="DRAFT",
        )

    with pytest.raises(ValueError, match="only reviewed"):
        repository.register(
            _record(),
            expert_id="expert-office",
            package_path=package_dir,
            review_id=review.review_id,
            spec_hash=review.spec_hash,
            lifecycle_status="EXECUTABLE",
        )


def test_same_reviewed_skill_version_registration_is_idempotent(tmp_path):
    repository = SkillVersionRepository(tmp_path / "skills.sqlite3")
    package_dir = tmp_path / "package"
    package_dir.mkdir()
    review = _review(repository)
    first = repository.register(
        _record(),
        expert_id="expert-office",
        package_path=package_dir,
        review_id=review.review_id,
        spec_hash=review.spec_hash,
    )
    second = repository.register(
        _record(),
        expert_id="expert-office",
        package_path=package_dir,
        review_id=review.review_id,
        spec_hash=review.spec_hash,
    )

    assert first == second
    assert len(repository.list_for_expert("expert-office")) == 1


def test_version_registration_requires_matching_approved_review_record(tmp_path):
    repository = SkillVersionRepository(tmp_path / "skills.sqlite3")
    package_dir = tmp_path / "package"
    package_dir.mkdir()
    rejected = _review(repository, decision="REJECTED")

    with pytest.raises(ValueError, match="approved review"):
        repository.register(
            _record(),
            expert_id="expert-office",
            package_path=package_dir,
            review_id=rejected.review_id,
            spec_hash=rejected.spec_hash,
        )

    approved = _review(repository)
    with pytest.raises(ValueError, match="exact spec hash"):
        repository.register(
            _record(),
            expert_id="expert-office",
            package_path=package_dir,
            review_id=approved.review_id,
            spec_hash="c" * 64,
        )
