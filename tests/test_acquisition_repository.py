"""Tests for persistent candidate review and search-batch membership."""

import pytest

from aios_work_system.acquisition import (
    CandidateRepository,
    CandidateStatus,
    ResourceCandidate,
)


def test_repository_persists_candidates_deduplicates_and_links_batches(tmp_path):
    repository = CandidateRepository(tmp_path / "candidates.sqlite3")
    first = ResourceCandidate(
        platform="bilibili",
        url="https://www.bilibili.com/video/BV1xx?spm=tracking",
        title="First result",
    )
    duplicate = ResourceCandidate(
        platform="bilibili",
        url="https://www.bilibili.com/video/BV1xx",
        title="Duplicate title",
    )

    assert repository.save_candidates("batch-a", [first]) == 1
    assert repository.save_candidates("batch-b", [duplicate]) == 0
    rows_a = repository.list_candidates(batch_id="batch-a")
    rows_b = repository.list_candidates(batch_id="batch-b")

    assert len(rows_a) == len(rows_b) == 1
    assert rows_a[0][0].title == "First result"
    assert rows_b[0][0].candidate_id == first.candidate_id
    assert rows_a[0][1] == CandidateStatus.DISCOVERED


def test_repository_enforces_review_transitions_and_records_reason(tmp_path):
    repository = CandidateRepository(tmp_path / "candidates.sqlite3")
    candidate = ResourceCandidate(
        platform="bilibili",
        url="https://www.bilibili.com/video/BV1yy",
        title="Tutorial",
    )
    repository.save_candidates("batch", [candidate])

    with pytest.raises(ValueError, match="invalid"):
        repository.transition(candidate.candidate_id, CandidateStatus.QUEUED)

    repository.transition(candidate.candidate_id, CandidateStatus.REVIEW_PENDING)
    repository.transition(candidate.candidate_id, CandidateStatus.SELECTED)
    repository.transition(candidate.candidate_id, CandidateStatus.REJECTED, reason="not a tutorial")

    rows = repository.list_candidates(status=CandidateStatus.REJECTED)
    assert rows[0][1] == CandidateStatus.REJECTED
    assert rows[0][2] == "not a tutorial"


def test_repository_validates_batch_and_limit(tmp_path):
    repository = CandidateRepository(tmp_path / "candidates.sqlite3")
    with pytest.raises(ValueError, match="batch_id"):
        repository.save_candidates(" ", [])
    with pytest.raises(ValueError, match="limit"):
        repository.list_candidates(limit=0)
