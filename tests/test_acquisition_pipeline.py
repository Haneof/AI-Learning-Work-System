"""End-to-end tests for selected candidate -> download -> asset registration."""

import pytest

from aios_work_system.media.download_progress import DownloadProgress

from aios_work_system.acquisition import (
    CandidateRepository,
    CandidateStatus,
    ResourceCandidate,
)
from aios_work_system.acquisition.pipeline import AcquisitionDownloadPipeline
from aios_work_system.media.assets import MediaAssetRepository
from aios_work_system.media.download_jobs import (
    DownloadJobRepository,
    DownloadJobStatus,
)


class FakeYtDlp:
    name = "yt-dlp"

    def __init__(self, *, fail_downloads: int = 0):
        self.fail_downloads = fail_downloads
        self.calls = 0

    def download(self, request, *, progress_callback=None):
        self.calls += 1
        if self.calls <= self.fail_downloads:
            raise RuntimeError("temporary platform error")
        request.destination_dir.mkdir(parents=True, exist_ok=True)
        output = request.destination_dir / "lesson.mp4"
        payload = b"verified tutorial media from fake yt-dlp"
        output.write_bytes(payload)
        if progress_callback is not None:
            progress_callback(
                DownloadProgress(
                    bytes_downloaded=len(payload),
                    total_bytes=len(payload),
                    speed_bytes_per_second=128.0,
                    eta_seconds=0.0,
                )
            )
        return output


def _selected_candidate(repository, candidate_id="candidate-1"):
    candidate = ResourceCandidate(
        platform="bilibili",
        url=f"https://www.bilibili.com/video/{candidate_id}",
        title="A tutorial",
        candidate_id=candidate_id,
    )
    repository.save_candidates("batch-1", [candidate])
    repository.transition(candidate_id, CandidateStatus.SELECTED)
    return candidate


def _pipeline(tmp_path, candidate_repository, *, fail_downloads=0, max_retries=1):
    return AcquisitionDownloadPipeline(
        candidate_repository,
        DownloadJobRepository(tmp_path / "jobs.sqlite3"),
        MediaAssetRepository(
            tmp_path / "assets.sqlite3",
            tmp_path / "manifests",
        ),
        tmp_path / "downloads",
        yt_dlp=FakeYtDlp(fail_downloads=fail_downloads),
        max_retries=max_retries,
    )


def test_only_selected_candidates_can_enter_download_queue(tmp_path):
    candidates = CandidateRepository(tmp_path / "candidates.sqlite3")
    candidate = ResourceCandidate(
        platform="bilibili",
        url="https://www.bilibili.com/video/BV1notselected",
        title="Not selected",
        candidate_id="candidate-not-selected",
    )
    candidates.save_candidates("batch", [candidate])
    pipeline = _pipeline(tmp_path, candidates)
    try:
        with pytest.raises(ValueError, match="must be SELECTED"):
            pipeline.enqueue_selected(candidate.candidate_id)
    finally:
        pipeline.shutdown()


def test_enqueue_is_idempotent_and_creates_one_active_job(tmp_path):
    candidates = CandidateRepository(tmp_path / "candidates.sqlite3")
    candidate = _selected_candidate(candidates)
    pipeline = _pipeline(tmp_path, candidates)
    try:
        first = pipeline.enqueue_selected(candidate.candidate_id)
        second = pipeline.enqueue_selected(candidate.candidate_id)
        queued_candidate, status, _reason = candidates.get(candidate.candidate_id)

        assert first.job_id == second.job_id
        assert status == CandidateStatus.QUEUED
        assert queued_candidate.candidate_id == candidate.candidate_id
        assert len(pipeline.jobs.list()) == 1
    finally:
        pipeline.shutdown()


def test_selected_candidate_runs_through_asset_registration(tmp_path):
    candidates = CandidateRepository(tmp_path / "candidates.sqlite3")
    candidate = _selected_candidate(candidates)
    pipeline = _pipeline(tmp_path, candidates)
    try:
        result = pipeline.run_selected(candidate.candidate_id)
        _stored_candidate, status, _reason = candidates.get(candidate.candidate_id)
        asset = pipeline.assets.get(result.asset_id or "")
        source_rows = pipeline.assets.list_sources(result.asset_id or "")
    finally:
        pipeline.shutdown()

    assert result.status == DownloadJobStatus.COMPLETED
    assert result.asset_id == asset.asset_id
    assert result.sha256 == asset.sha256
    assert status == CandidateStatus.DOWNLOADED
    assert source_rows[0]["candidate_id"] == candidate.candidate_id
    assert source_rows[0]["job_id"] == result.job_id


def test_terminal_download_failure_can_be_retried_by_requeueing_candidate(tmp_path):
    candidates = CandidateRepository(tmp_path / "candidates.sqlite3")
    candidate = _selected_candidate(candidates)
    pipeline = _pipeline(
        tmp_path,
        candidates,
        fail_downloads=1,
        max_retries=0,
    )
    try:
        with pytest.raises(RuntimeError, match="temporary platform error"):
            pipeline.run_selected(candidate.candidate_id)
        _failed_candidate, failed_status, _reason = candidates.get(
            candidate.candidate_id
        )
        assert failed_status == CandidateStatus.DOWNLOAD_FAILED

        result = pipeline.run_selected(candidate.candidate_id)
        _stored_candidate, final_status, _reason = candidates.get(
            candidate.candidate_id
        )
    finally:
        pipeline.shutdown()

    assert result.status == DownloadJobStatus.COMPLETED
    assert final_status == CandidateStatus.DOWNLOADED
    assert len(pipeline.jobs.list()) == 2
