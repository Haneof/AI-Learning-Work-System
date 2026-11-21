# Download Job Lifecycle

Status: implemented persistence and lifecycle contract; process scheduler and engine event adapters remain pending.

## Scope

The acquisition stack uses existing engines rather than reimplementing media protocols:

- `yt-dlp`: platform pages and HLS/DASH media extraction, fragment concurrency and merge.
- `aria2c`: ordinary HTTP(S) files, multi-connection transfers and continuation when supported by the server.
- `ffprobe`: optional media-stream validation after download.

`DownloadJobRepository` persists job metadata and enforces the state machine. `DownloadJobExecutor` now runs persisted jobs through the existing yt-dlp/aria2 adapters with a bounded worker pool, records lifecycle transitions, verifies output, and calls an explicit asset-registration callback. It does not yet expose live engine progress, pause/resume/cancel a running OS process, or implement a local HTTP Range integration harness.

## State machine

```text
QUEUED -> PREPARING -> DOWNLOADING -> VERIFYING -> COMPLETED
              |             |              |
              +-> RETRY_WAIT <-------------+
              |             |
              +-> FAILED    +-> PAUSED -> QUEUED
                            |
                            +-> CANCELLED
```

Additional rules:

- `RETRY_WAIT` requires an error reason and increments `retry_count`.
- `FAILED` and `CANCELLED` are terminal for that job; a new job may be created for the candidate.
- `FAILED` can be explicitly re-queued for a controlled retry.
- `COMPLETED` requires both an `asset_id` and a SHA-256 digest.
- Progress updates are accepted only while the job is `DOWNLOADING`.
- At most one non-terminal job may exist for a candidate.
- `recover_interrupted()` moves in-flight jobs to `RETRY_WAIT` after an unclean shutdown. It does not claim that the underlying partial file is valid; the scheduler must inspect the engine's resume metadata before continuing.

## Minimal API

```python
from aios_work_system.media.download_jobs import (
    DownloadJobRepository,
    DownloadJobStatus,
)

jobs = DownloadJobRepository("data/download_jobs.sqlite3")
job = jobs.create(
    candidate_id="candidate-id",
    source_url="https://example.com/lesson.mp4",
    engine="yt-dlp",
    destination="data/media",
)
jobs.transition(job.job_id, DownloadJobStatus.PREPARING)
jobs.transition(job.job_id, DownloadJobStatus.DOWNLOADING)
jobs.update_progress(
    job.job_id,
    bytes_downloaded=1024,
    total_bytes=4096,
    speed_bytes_per_second=512.0,
    eta_seconds=6.0,
)
```

After the engine exits successfully, the future scheduler must move the job to `VERIFYING`, run file and media checks, register the resulting asset, then transition to `COMPLETED` with the asset ID and SHA-256. A successful process exit alone is not completion evidence.

## Verification boundaries

| Test layer | What it proves | What it does not prove |
|---|---|---|
| Repository unit tests | Persistence, state guards, duplicate-active protection, progress validation and restart recovery metadata | Real file download or process recovery |
| Fake-runner adapter tests | Correct command construction and error handling | yt-dlp/aria2 interoperability |
| Local HTTP Range integration | Segmented transfer and resume against a controlled server | Every external host supports Range |
| External smoke test | A pinned public sample can be fetched at test time | Long-term platform availability |
| Windows acceptance | Actual local environment setup and user workflow | Other machines or networks |

## Next implementation increment

1. Add a bounded scheduler with per-host concurrency and process lifecycle management.
2. Parse stable progress events from yt-dlp and aria2 without exposing raw log text as the public API.
3. Implement pause/resume/cancel and graceful process termination.
4. Reconcile partial files and engine resume metadata after restart.
5. Add a local HTTP Range test server and real binary integration jobs.
6. Connect candidate selection to queue creation and asset registration.

Do not claim a job is completed until integrity and media validation have passed.
