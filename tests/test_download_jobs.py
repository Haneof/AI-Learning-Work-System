"""Tests for persistent download-job lifecycle and recovery."""

import pytest

from aios_work_system.media.download_jobs import (
    DownloadJobRepository,
    DownloadJobStatus,
)


def make_job(repository, candidate_id="candidate-1"):
    return repository.create(
        candidate_id=candidate_id,
        source_url="https://example.com/lesson.mp4",
        engine="yt-dlp",
        destination="/tmp/downloads",
    )


def test_job_is_persisted_and_can_be_reopened(tmp_path):
    database = tmp_path / "jobs.sqlite3"
    job = make_job(DownloadJobRepository(database))

    reopened = DownloadJobRepository(database).get(job.job_id)

    assert reopened == job
    assert reopened.status == DownloadJobStatus.QUEUED
    assert reopened.progress_percent is None


def test_duplicate_active_candidate_is_rejected_but_terminal_job_allows_retry(tmp_path):
    repository = DownloadJobRepository(tmp_path / "jobs.sqlite3")
    first = make_job(repository)

    with pytest.raises(ValueError, match="active download job"):
        make_job(repository)

    repository.transition(first.job_id, DownloadJobStatus.CANCELLED)
    second = make_job(repository)

    assert second.job_id != first.job_id


def test_state_machine_requires_valid_order_and_completion_evidence(tmp_path):
    repository = DownloadJobRepository(tmp_path / "jobs.sqlite3")
    job = make_job(repository)

    with pytest.raises(ValueError, match="invalid download job transition"):
        repository.transition(job.job_id, DownloadJobStatus.COMPLETED)

    repository.transition(job.job_id, DownloadJobStatus.PREPARING)
    repository.transition(job.job_id, DownloadJobStatus.DOWNLOADING)

    repository.transition(job.job_id, DownloadJobStatus.VERIFYING)

    with pytest.raises(ValueError, match="asset_id and sha256"):
        repository.transition(job.job_id, DownloadJobStatus.COMPLETED)
    completed = repository.transition(
        job.job_id,
        DownloadJobStatus.COMPLETED,
        asset_id="asset-123",
        sha256="a" * 64,
    )

    assert completed.asset_id == "asset-123"
    assert completed.sha256 == "a" * 64


def test_progress_is_only_accepted_while_downloading(tmp_path):
    repository = DownloadJobRepository(tmp_path / "jobs.sqlite3")
    job = make_job(repository)

    with pytest.raises(ValueError, match="only be updated while DOWNLOADING"):
        repository.update_progress(job.job_id, bytes_downloaded=10)

    repository.transition(job.job_id, DownloadJobStatus.PREPARING)
    repository.transition(job.job_id, DownloadJobStatus.DOWNLOADING)
    updated = repository.update_progress(
        job.job_id,
        bytes_downloaded=25,
        total_bytes=100,
        speed_bytes_per_second=5.0,
        eta_seconds=15.0,
    )

    assert updated.progress_percent == 25.0
    assert updated.speed_bytes_per_second == 5.0
    assert updated.eta_seconds == 15.0

    partial = repository.update_progress(
        job.job_id,
        bytes_downloaded=30,
        total_bytes=None,
        speed_bytes_per_second=6.0,
    )
    assert partial.bytes_downloaded == 30
    assert partial.total_bytes == 100


def test_retry_wait_requires_error_and_increments_retry_count(tmp_path):
    repository = DownloadJobRepository(tmp_path / "jobs.sqlite3")
    job = make_job(repository)
    repository.transition(job.job_id, DownloadJobStatus.PREPARING)

    with pytest.raises(ValueError, match="require a non-empty error"):
        repository.transition(job.job_id, DownloadJobStatus.RETRY_WAIT)

    retry = repository.transition(
        job.job_id,
        DownloadJobStatus.RETRY_WAIT,
        error="temporary network error",
    )

    assert retry.retry_count == 1
    assert retry.error == "temporary network error"


def test_recovery_marks_only_inflight_jobs_for_resume(tmp_path):
    repository = DownloadJobRepository(tmp_path / "jobs.sqlite3")
    queued = make_job(repository, "queued")
    active = make_job(repository, "active")
    paused = make_job(repository, "paused")

    repository.transition(active.job_id, DownloadJobStatus.PREPARING)
    repository.transition(active.job_id, DownloadJobStatus.DOWNLOADING)
    repository.transition(paused.job_id, DownloadJobStatus.PREPARING)
    repository.transition(paused.job_id, DownloadJobStatus.DOWNLOADING)
    repository.transition(paused.job_id, DownloadJobStatus.PAUSED)

    recovered = repository.recover_interrupted()

    assert recovered == 1
    assert repository.get(queued.job_id).status == DownloadJobStatus.QUEUED
    assert repository.get(active.job_id).status == DownloadJobStatus.RETRY_WAIT
    assert repository.get(paused.job_id).status == DownloadJobStatus.PAUSED


def test_expected_status_prevents_stale_worker_updates(tmp_path):
    repository = DownloadJobRepository(tmp_path / "jobs.sqlite3")
    job = make_job(repository)
    repository.transition(job.job_id, DownloadJobStatus.PREPARING)

    with pytest.raises(ValueError, match="status conflict"):
        repository.transition(
            job.job_id,
            DownloadJobStatus.DOWNLOADING,
            expected_status=DownloadJobStatus.QUEUED,
        )


def test_input_validation_and_list_filtering(tmp_path):
    repository = DownloadJobRepository(tmp_path / "jobs.sqlite3")

    with pytest.raises(ValueError, match="HTTP or HTTPS"):
        repository.create(
            candidate_id="bad",
            source_url="file:///etc/passwd",
            engine="aria2",
            destination="/tmp",
        )
    with pytest.raises(ValueError, match="engine"):
        repository.create(
            candidate_id="bad-engine",
            source_url="https://example.com/file",
            engine="curl",
            destination="/tmp",
        )

    job = make_job(repository)
    assert repository.list(status=DownloadJobStatus.QUEUED) == [job]
    with pytest.raises(ValueError, match="limit"):
        repository.list(limit=0)
