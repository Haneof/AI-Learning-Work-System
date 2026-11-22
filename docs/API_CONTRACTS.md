# API Contracts for Tutorial Learning (Logical MVP)

Version: V1.1  
Status: target logical contracts; these definitions do not imply every service is implemented.

## 1. General conventions

- JSON UTF-8; timestamps use ISO 8601 UTC.
- IDs use UUID; list pagination uses cursor/limit.
- Long-running download, prefilter, extraction, review, and training operations return job/task IDs.
- Writes support idempotency keys; retries must not duplicate side effects.
- Every response includes request_id; background jobs also include trace_id.
- Secrets, credentials, private source URLs, and tokens must not appear in ordinary logs.

## 2. Pipeline contracts

### Register a tutorial download

- POST /v1/experts/{expert_id}/downloads
- Input: source_url, platform, creator, series_or_course, title, discovered_at, license_metadata.
- Output: download_record_id, state.
- A record is required for every downloaded video and must preserve source_url and platform.
- The archive destination is Google Drive under platform/creator/series-or-course. The cloud downloader writes directly to Drive.

### Start clean and pre-filter

- POST /v1/downloads/{download_record_id}/prefilter-jobs
- Input: target_vertical, subtitle_preferences, prefilter_profile.
- Output: job_id, state.
- Extract embedded/sidecar subtitles when usable. Run ASR only when source subtitles are unavailable.
- Classify whether the item is a tutorial in the target vertical.
- Rejected videos retain the download record and rejection reason and must not enter full extraction.

### Start full multimodal extraction

- POST /v1/source-videos/{source_video_id}/trajectory-extraction-jobs
- Input: understanding_model_id/revision, grounding_model_id/revision, extraction_profile.
- Output: job_id, state.
- The understanding model (Qwen3-VL or Mage-VL candidate) receives video frame/clip evidence and audio/subtitle context and returns time-grounded text understanding.
- The action-grounding model (Magma) returns candidate coordinates/target regions/action trajectories.
- These outputs must remain separate and must include source/time/frame references.
- Every action claim distinguishes observed evidence from inference.

### Query pipeline job

- GET /v1/pipeline-jobs/{job_id}
- Return stage, state, progress, warnings, error_code, output references, model/tool versions, timestamps, and measured resource metrics when available.

### Review a knowledge package

- POST /v1/knowledge-packages/{package_id}/reviews
- Input: gate (GPT_FIRST_PASS / PM_INDEPENDENT_VERIFICATION), decision (PASS / REJECT / NEEDS_EVIDENCE), comments, evidence/test references.
- Output: review_event_id, new_state.
- GPT checks first; PM Sangou independently verifies the original video evidence and relevant tests.
- No separate manual-review queue. A package cannot become approved unless both required gates pass.

### Freeze a LoRA training dataset

- POST /v1/verticals/{vertical_id}/training-datasets
- Input: approved_package_ids, dataset_version, base_model_id.
- Output: dataset_snapshot_id, dataset_hash.
- The server must reject any package without both review PASS events. Dataset snapshots are immutable.

### Start LoRA training

- POST /v1/training-datasets/{dataset_snapshot_id}/lora-training-jobs
- Input: base_model_id/revision, adapter_config, compute_profile.
- Output: training_job_id, state.
- Training targets 4B BF16 LoRA on a cloud T4 16GB planning profile; 9B requires a 24GB+ profile. Actual capacity is verified from run metadata.

### Evaluate a trained expert

- POST /v1/experts/{expert_id}/evaluation-runs
- Input: adapter_revision, sandbox_profile, gui_test_suite, unseen_task_suite.
- Output: evaluation_run_id, state.
- Validation includes Docker sandbox execution and the GUI operation loop. A replay-only pass is insufficient.

## 3. Existing generic interfaces

### Register source

- POST /v1/experts/{expert_id}/sources
- Input: source_type, original_name, storage_uri/upload_ref, sha256, mime_type, size_bytes, metadata.
- Output: source_id, ingest_state, duplicate_of (when exact content already exists).

### Query parsing result

- GET /v1/ingestion-jobs/{job_id}
- Return state, progress, warnings, error_code, segment_count, and measured resource metrics.

## 4. Access control and integrity

- Every resource access validates expert/vertical scope.
- Hash-identical video content is deduplicated; conflicting knowledge is retained as separate records, never overwritten.
- The store derives reviewer identity from trusted runtime context; caller-provided identity strings are not authorization.
- Approval requires both review gates; training dataset membership is server-enforced.
- Model/tool outputs are untrusted until evidence checks pass.
- High-risk external effects remain subject to the separate authorization policy.

## 5. Version policy

- API uses /v1; breaking contract changes require a major version.
- Schema changes require compatibility tests and migration notes.
- This document is a target contract, not a claim that the API endpoints already exist.
