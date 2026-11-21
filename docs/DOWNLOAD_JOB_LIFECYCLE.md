# Download Job Lifecycle

Status: implemented persistent jobs, bounded execution, normalized live engine progress, candidate hand-off, and hash-deduplicated asset registration; process pause/resume/cancel and real HTTP Range integration remain pending.

## Scope

The acquisition stack uses existing engines rather than reimplementing media protocols:

- `yt-dlp`: platform pages and HLS/DASH media extraction, fragment concurrency and merge.
- `aria2c`: ordinary HTTP(S) files, multi-connection transfers and continuation when supported by the server.
- `ffprobe`: optional media-stream validation after download.

`DownloadJobRepository` persists job metadata and enforces the state machine. `DownloadJobExecutor` runs persisted jobs through the existing yt-dlp/aria2 adapters with a bounded worker pool, records lifecycle transitions, verifies output, and calls an explicit asset-registration callback. `AcquisitionDownloadPipeline` bridges selected candidates to the job queue. `MediaAssetRepository` re-checks file size and SHA-256, persists the source manifest and provenance, and reuses the same asset ID for identical content. Both adapters can emit normalized `DownloadProgress` events: yt-dlp uses its structured JSON progress template; aria2 is queried through a per-job JSON-RPC endpoint bound to loopback and protected by a random token. The executor persists byte count, known/estimated total, speed and ETA in SQLite. Unknown totals remain unknown and do not erase an earlier known total. Running process pause/resume/cancel, per-host limits, and a local HTTP Range integration harness remain out of scope.

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

After the engine exits successfully, the executor moves the job to `VERIFYING`, runs file checks, registers the resulting asset, then transitions to `COMPLETED` with the asset ID and SHA-256. The acquisition pipeline updates the candidate to `DOWNLOADED` only after this succeeds. A successful process exit alone is not completion evidence.

## Candidate-to-asset integration

The current Python integration path is:

```python
from aios_work_system.acquisition import (
    AcquisitionDownloadPipeline,
    CandidateRepository,
)
from aios_work_system.media import (
    DownloadJobRepository,
    MediaAssetRepository,
)

pipeline = AcquisitionDownloadPipeline(
    candidate_repository=CandidateRepository("data/candidates.sqlite3"),
    job_repository=DownloadJobRepository("data/download_jobs.sqlite3"),
    asset_repository=MediaAssetRepository(
        "data/assets.sqlite3", "data/asset_manifests"
    ),
    destination_root="data/downloads",
)
try:
    # The candidate must already have status SELECTED.
    job = pipeline.run_selected("candidate-id", engine="yt-dlp")
finally:
    pipeline.shutdown()
```

The pipeline is available as a Python API; the current CLI still exposes search only. Candidate and download metadata use separate SQLite repositories, so queue hand-off is idempotent and recovery-aware rather than relying on a cross-database transaction. Candidate IDs are hashed before use in filesystem paths.

## Verification boundaries

| Test layer | What it proves | What it does not prove |
|---|---|---|
| Repository unit tests | Persistence, state guards, duplicate-active protection, progress validation and restart recovery metadata | Real file download or process recovery |
| Fake-runner adapter tests | Correct command construction and error handling | yt-dlp/aria2 interoperability |
| Local HTTP Range integration | Segmented transfer and resume against a controlled server | Every external host supports Range |
| External smoke test | A pinned public sample can be fetched at test time | Long-term platform availability |
| Windows acceptance | Actual local environment setup and user workflow | Other machines or networks |

## Progress event contract

`DownloadProgress` contains `bytes_downloaded`, optional `total_bytes`, optional `speed_bytes_per_second`, and optional `eta_seconds`. Parsers reject malformed/negative/non-finite values. yt-dlp's estimated total is used only when an exact total is unavailable. aria2's ETA is derived only when both total and positive speed are known. Event persistence is accepted only while the job is `DOWNLOADING`; an omitted total does not overwrite a previously known total.

Progress reporting is best-effort telemetry and is not completion evidence. A successful engine exit still requires file integrity verification and asset registration before `COMPLETED`.

## Next implementation increment

1. Add process supervision with pause/resume/cancel and graceful termination semantics.
2. Reconcile partial files and engine resume metadata after restart.
3. Add a local HTTP Range test server and real binary integration jobs.
4. Add per-host concurrency/rate controls without weakening job-level limits.
5. Add downstream ASR/OCR/keyframe analysis and persist timestamp/page evidence segments against the registered asset.

Do not claim a job is completed until integrity and media validation have passed.
