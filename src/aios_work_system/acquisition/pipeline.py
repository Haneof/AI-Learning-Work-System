"""Bridge curated resource candidates to durable downloads and media assets."""

from __future__ import annotations

from concurrent.futures import Future
from pathlib import Path
from threading import RLock

from aios_work_system.acquisition.repository import CandidateRepository, CandidateStatus
from aios_work_system.media.assets import MediaAssetRepository
from aios_work_system.media.download import (
    Aria2Adapter,
    DownloadVerifier,
    YtDlpAdapter,
)
from aios_work_system.media.download_jobs import (
    DownloadJob,
    DownloadJobRepository,
    DownloadJobStatus,
)
from aios_work_system.media.download_runner import DownloadJobExecutor


class AcquisitionDownloadPipeline:
    """Enqueue selected candidates, execute downloads, and register verified assets.

    Candidate and download repositories may use separate SQLite files. The
    hand-off is therefore intentionally idempotent: a persisted active job is
    reused if candidate status repair or a caller retry is needed after a
    process interruption.
    """

    def __init__(
        self,
        candidate_repository: CandidateRepository,
        job_repository: DownloadJobRepository,
        asset_repository: MediaAssetRepository,
        destination_root: str | Path,
        *,
        yt_dlp: YtDlpAdapter | None = None,
        aria2: Aria2Adapter | None = None,
        verifier: DownloadVerifier | None = None,
        max_concurrent_jobs: int = 2,
        max_retries: int = 2,
    ) -> None:
        self.candidates = candidate_repository
        self.jobs = job_repository
        self.assets = asset_repository
        self.destination_root = Path(destination_root).expanduser().resolve()
        self.destination_root.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self.executor = DownloadJobExecutor(
            self.jobs,
            yt_dlp=yt_dlp,
            aria2=aria2,
            verifier=verifier,
            asset_registrar=self.assets.register_download,
            max_concurrent_jobs=max_concurrent_jobs,
            max_retries=max_retries,
        )

    def enqueue_selected(
        self,
        candidate_id: str,
        *,
        engine: str = "yt-dlp",
    ) -> DownloadJob:
        """Create or reuse a job for a SELECTED candidate.

        Calling this again for an already queued candidate returns its active
        job. A previous terminal download failure can be explicitly retried by
        calling this method again; completed candidates are never re-downloaded
        implicitly.
        """
        with self._lock:
            candidate, status, _reason = self.candidates.get(candidate_id)

            if status == CandidateStatus.DOWNLOADED:
                latest = self.jobs.get_latest_for_candidate(candidate_id)
                if latest is None or latest.status != DownloadJobStatus.COMPLETED:
                    raise RuntimeError(
                        "candidate is DOWNLOADED but has no completed download job"
                    )
                return latest

            if status == CandidateStatus.QUEUED:
                active = self.jobs.get_active_for_candidate(candidate_id)
                if active is not None:
                    return active
                latest = self.jobs.get_latest_for_candidate(candidate_id)
                if latest is None:
                    raise RuntimeError(
                        "candidate is QUEUED but has no corresponding download job"
                    )
                if latest.status == DownloadJobStatus.COMPLETED:
                    self.candidates.transition(
                        candidate_id, CandidateStatus.DOWNLOADED
                    )
                    return latest
                if latest.status in {
                    DownloadJobStatus.FAILED,
                    DownloadJobStatus.CANCELLED,
                }:
                    self.candidates.transition(
                        candidate_id,
                        CandidateStatus.DOWNLOAD_FAILED,
                        reason=latest.error or latest.status.value,
                    )
                    self.candidates.transition(
                        candidate_id, CandidateStatus.SELECTED
                    )
                    status = CandidateStatus.SELECTED
                else:
                    raise RuntimeError(
                        f"candidate has no active job but latest job is {latest.status}"
                    )

            if status == CandidateStatus.DOWNLOAD_FAILED:
                self.candidates.transition(
                    candidate_id, CandidateStatus.SELECTED
                )
                status = CandidateStatus.SELECTED
            if status != CandidateStatus.SELECTED:
                raise ValueError(
                    f"candidate must be SELECTED before download; found {status}"
                )

            try:
                job = self.jobs.create(
                    candidate_id=candidate.candidate_id,
                    source_url=candidate.url,
                    engine=engine,
                    destination=self.destination_root / candidate.candidate_id,
                )
            except ValueError:
                # Another caller may have created the active job between the
                # status read and INSERT. Reuse only a matching durable job.
                active = self.jobs.get_active_for_candidate(candidate_id)
                if active is None:
                    raise
                self.candidates.transition(candidate_id, CandidateStatus.QUEUED)
                return active

            try:
                self.candidates.transition(candidate_id, CandidateStatus.QUEUED)
            except Exception:
                current_candidate, current_status, _ = self.candidates.get(
                    candidate_id
                )
                if current_status == CandidateStatus.QUEUED:
                    return job
                self.jobs.transition(job.job_id, DownloadJobStatus.CANCELLED)
                raise
            return job

    def submit_selected(
        self,
        candidate_id: str,
        *,
        engine: str = "yt-dlp",
    ) -> Future[DownloadJob]:
        """Queue and asynchronously execute a selected candidate."""
        job = self.enqueue_selected(candidate_id, engine=engine)
        if job.status == DownloadJobStatus.COMPLETED:
            future: Future[DownloadJob] = Future()
            future.set_result(job)
            return future
        future = self.executor.submit(job.job_id)
        future.add_done_callback(
            lambda completed: self._finalize_candidate(candidate_id, job.job_id, completed)
        )
        return future

    def run_selected(
        self,
        candidate_id: str,
        *,
        engine: str = "yt-dlp",
    ) -> DownloadJob:
        """Queue and synchronously execute a selected candidate."""
        job = self.enqueue_selected(candidate_id, engine=engine)
        if job.status == DownloadJobStatus.COMPLETED:
            return job
        try:
            result = self.executor.run(job.job_id)
        except Exception:
            self._reconcile_terminal_candidate(candidate_id, job.job_id)
            raise
        self._mark_downloaded(candidate_id, result)
        return result

    def _finalize_candidate(
        self,
        candidate_id: str,
        job_id: str,
        future: Future[DownloadJob],
    ) -> None:
        try:
            result = future.result()
        except Exception:
            self._reconcile_terminal_candidate(candidate_id, job_id)
        else:
            self._mark_downloaded(candidate_id, result)

    def _mark_downloaded(self, candidate_id: str, job: DownloadJob) -> None:
        if job.status != DownloadJobStatus.COMPLETED:
            return
        _candidate, status, _reason = self.candidates.get(candidate_id)
        if status == CandidateStatus.QUEUED:
            self.candidates.transition(candidate_id, CandidateStatus.DOWNLOADED)

    def _reconcile_terminal_candidate(self, candidate_id: str, job_id: str) -> None:
        job = self.jobs.get(job_id)
        if job.status not in {
            DownloadJobStatus.FAILED,
            DownloadJobStatus.CANCELLED,
        }:
            return
        _candidate, status, _reason = self.candidates.get(candidate_id)
        if status == CandidateStatus.QUEUED:
            self.candidates.transition(
                candidate_id,
                CandidateStatus.DOWNLOAD_FAILED,
                reason=job.error or job.status.value,
            )

    def shutdown(self, *, wait: bool = True) -> None:
        """Stop accepting jobs and optionally wait for current downloads."""
        self.executor.shutdown(wait=wait)
