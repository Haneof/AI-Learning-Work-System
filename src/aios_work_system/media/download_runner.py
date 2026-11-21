"""Bounded execution of persisted download jobs using existing media engines."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from threading import Lock

from aios_work_system.media.download import (
    Aria2Adapter,
    DownloadRequest,
    DownloadVerifier,
    YtDlpAdapter,
)
from aios_work_system.media.download_jobs import (
    DownloadJob,
    DownloadJobRepository,
    DownloadJobStatus,
)
from aios_work_system.media.download_progress import DownloadProgress

AssetRegistrar = Callable[[DownloadJob, Path, str, int], str]


class DownloadJobExecutor:
    """Run queued jobs with bounded parallelism and verified asset registration.

    Each worker owns one job at a time. yt-dlp/aria2 retain responsibility for
    protocol-level concurrency and resume; this executor bounds job-level
    concurrency and persists lifecycle transitions.
    """

    def __init__(
        self,
        repository: DownloadJobRepository,
        *,
        yt_dlp: YtDlpAdapter | None = None,
        aria2: Aria2Adapter | None = None,
        verifier: DownloadVerifier | None = None,
        asset_registrar: AssetRegistrar,
        max_concurrent_jobs: int = 2,
        max_retries: int = 2,
    ) -> None:
        if max_concurrent_jobs < 1:
            raise ValueError("max_concurrent_jobs must be at least 1")
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        self.repository = repository
        self.yt_dlp = yt_dlp or YtDlpAdapter()
        self.aria2 = aria2 or Aria2Adapter()
        self.verifier = verifier or DownloadVerifier()
        self.asset_registrar = asset_registrar
        self.max_retries = max_retries
        self._pool = ThreadPoolExecutor(
            max_workers=max_concurrent_jobs,
            thread_name_prefix="aios-download",
        )
        self._lock = Lock()
        self._futures: dict[str, Future[DownloadJob]] = {}

    def submit(self, job_id: str) -> Future[DownloadJob]:
        """Schedule a queued or retryable job; duplicate submissions are rejected."""
        with self._lock:
            existing = self._futures.get(job_id)
            job = self.repository.get(job_id)
            if existing is not None and (
                not existing.done()
                or job.status
                not in {
                    DownloadJobStatus.QUEUED,
                    DownloadJobStatus.RETRY_WAIT,
                }
            ):
                raise ValueError(
                    f"download job is already scheduled or finished: {job_id}"
                )
            if job.status not in {
                DownloadJobStatus.QUEUED,
                DownloadJobStatus.RETRY_WAIT,
            }:
                raise ValueError(f"job is not ready to run: {job.status}")
            future = self._pool.submit(self.run, job_id)
            self._futures[job_id] = future
            return future

    def run(self, job_id: str) -> DownloadJob:
        """Execute one job synchronously; useful for deterministic tests and workers."""
        job = self.repository.get(job_id)
        if job.status not in {
            DownloadJobStatus.QUEUED,
            DownloadJobStatus.RETRY_WAIT,
        }:
            raise ValueError(f"job is not ready to run: {job.status}")

        self.repository.transition(
            job_id, DownloadJobStatus.PREPARING, expected_status=job.status
        )
        try:
            request = DownloadRequest(
                url=job.source_url,
                destination_dir=Path(job.destination),
            )
            def report_progress(progress: DownloadProgress) -> None:
                self.repository.update_progress(
                    job_id,
                    bytes_downloaded=progress.bytes_downloaded,
                    total_bytes=progress.total_bytes,
                    speed_bytes_per_second=progress.speed_bytes_per_second,
                    eta_seconds=progress.eta_seconds,
                )

            if job.engine == "yt-dlp":
                self.repository.transition(job_id, DownloadJobStatus.DOWNLOADING)
                output_path = self.yt_dlp.download(
                    request, progress_callback=report_progress
                )
                engine_name = self.yt_dlp.name
            elif job.engine == "aria2":
                self.repository.transition(job_id, DownloadJobStatus.DOWNLOADING)
                output_path = self.aria2.download(
                    request, progress_callback=report_progress
                )
                engine_name = self.aria2.name
            else:
                raise ValueError(f"unsupported download engine: {job.engine}")

            self.repository.transition(job_id, DownloadJobStatus.VERIFYING)
            result = self.verifier.verify(engine_name, output_path)
            asset_id = self.asset_registrar(
                job, result.path, result.sha256, result.size_bytes
            )
            if not asset_id or not asset_id.strip():
                raise ValueError("asset registrar returned an empty asset_id")
            return self.repository.transition(
                job_id,
                DownloadJobStatus.COMPLETED,
                asset_id=asset_id,
                sha256=result.sha256,
            )
        except Exception as exc:
            current = self.repository.get(job_id)
            message = f"{type(exc).__name__}: {exc}"
            if current.status in {
                DownloadJobStatus.PREPARING,
                DownloadJobStatus.DOWNLOADING,
                DownloadJobStatus.VERIFYING,
            }:
                target = (
                    DownloadJobStatus.RETRY_WAIT
                    if current.retry_count < self.max_retries
                    else DownloadJobStatus.FAILED
                )
                self.repository.transition(job_id, target, error=message)
            raise

    def shutdown(self, *, wait: bool = True) -> None:
        """Stop accepting new jobs and optionally wait for active jobs to finish."""
        self._pool.shutdown(wait=wait, cancel_futures=not wait)
