"""Tests for bounded download job execution."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from aios_work_system.media.download_jobs import (
    DownloadJobRepository,
    DownloadJobStatus,
)
from aios_work_system.media.download_progress import DownloadProgress
from aios_work_system.media.download_runner import DownloadJobExecutor


class FakeAdapter:
    name = "fake-engine"

    def __init__(self, output: Path, fail_downloads: int = 0):
        self.output = output
        self.fail_downloads = fail_downloads
        self.calls = 0

    def download(self, request, *, progress_callback=None):
        self.calls += 1
        if self.calls <= self.fail_downloads:
            raise RuntimeError("temporary network error")
        request.destination_dir.mkdir(parents=True, exist_ok=True)
        self.output.write_bytes(b"valid media bytes")
        if progress_callback is not None:
            progress_callback(
                DownloadProgress(
                    bytes_downloaded=5,
                    total_bytes=17,
                    speed_bytes_per_second=2.0,
                    eta_seconds=6.0,
                )
            )
        return self.output


class FakeVerifier:
    def verify(self, engine, path):
        return SimpleNamespace(
            engine=engine,
            path=Path(path),
            sha256="a" * 64,
            size_bytes=17,
        )


def make_executor(
    tmp_path, *, fail_register=False, fail_downloads=0, max_retries=2
):
    repository = DownloadJobRepository(tmp_path / "jobs.sqlite3")
    job = repository.create(
        candidate_id="candidate-1",
        source_url="https://example.com/lesson.mp4",
        engine="yt-dlp",
        destination=tmp_path / "downloads",
    )
    output = tmp_path / "downloads" / "lesson.mp4"
    adapter = FakeAdapter(output, fail_downloads=fail_downloads)

    def register(_job, _path, _sha256, _size):
        if fail_register:
            raise RuntimeError("asset store unavailable")
        return "asset-123"

    executor = DownloadJobExecutor(
        repository,
        yt_dlp=adapter,
        verifier=FakeVerifier(),
        asset_registrar=register,
        max_retries=max_retries,
    )
    return repository, job, adapter, executor


def test_executor_runs_and_registers_verified_asset(tmp_path):
    repository, job, adapter, executor = make_executor(tmp_path)
    try:
        result = executor.run(job.job_id)
    finally:
        executor.shutdown()

    assert adapter.calls == 1
    assert result.status == DownloadJobStatus.COMPLETED
    assert result.asset_id == "asset-123"
    assert result.sha256 == "a" * 64
    assert result.bytes_downloaded == 5
    assert result.total_bytes == 17
    assert result.speed_bytes_per_second == 2.0
    assert result.eta_seconds == 6.0


def test_executor_does_not_mark_job_complete_if_asset_registration_fails(tmp_path):
    repository, job, _adapter, executor = make_executor(
        tmp_path, fail_register=True
    )
    try:
        with pytest.raises(RuntimeError, match="asset store unavailable"):
            executor.run(job.job_id)
    finally:
        executor.shutdown()

    failed_attempt = repository.get(job.job_id)
    assert failed_attempt.status == DownloadJobStatus.RETRY_WAIT
    assert failed_attempt.asset_id is None
    assert failed_attempt.sha256 is None


def test_executor_exhausts_retry_budget_as_failed(tmp_path):
    repository, job, _adapter, executor = make_executor(
        tmp_path, fail_register=True, max_retries=0
    )
    try:
        with pytest.raises(RuntimeError, match="asset store unavailable"):
            executor.run(job.job_id)
    finally:
        executor.shutdown()

    assert repository.get(job.job_id).status == DownloadJobStatus.FAILED


def test_submit_rejects_duplicate_active_future(tmp_path):
    repository, job, _adapter, executor = make_executor(tmp_path)
    # A queued job is scheduled once; a second submission while it is running
    # is guarded by the executor's in-flight registry.
    try:
        future = executor.submit(job.job_id)
        with pytest.raises(ValueError, match="already scheduled"):
            executor.submit(job.job_id)
        future.result(timeout=5)
    finally:
        executor.shutdown()



def test_executor_requeues_retry_wait_job_before_second_attempt(tmp_path):
    repository, job, adapter, executor = make_executor(
        tmp_path,
        fail_downloads=1,
        max_retries=1,
    )
    try:
        with pytest.raises(RuntimeError, match="temporary network error"):
            executor.run(job.job_id)
        retry_wait = repository.get(job.job_id)
        assert retry_wait.status == DownloadJobStatus.RETRY_WAIT

        result = executor.run(job.job_id)
    finally:
        executor.shutdown()

    assert adapter.calls == 2
    assert result.status == DownloadJobStatus.COMPLETED
    assert result.retry_count == 1
