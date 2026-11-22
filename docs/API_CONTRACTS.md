# API Contracts for Workflow Learning (Logical MVP)

**Version:** 0.1 design target  
These logical contracts do not imply that every service is implemented.

## 1. General conventions

- JSON UTF-8; timestamps use ISO 8601 UTC or integer milliseconds relative to a recording session, as declared by the schema.
- IDs use UUID or stable source-scoped identifiers.
- Long-running download, capture, alignment, extraction, review, and training operations return job/task IDs.
- Writes support idempotency keys; retries must not duplicate side effects.
- Every response includes request_id; background jobs also include trace_id.
- Secrets, credentials, private source URLs, and tokens must not appear in ordinary logs.

## 2. Pipeline contracts

### Register a tutorial download

- POST /v1/experts/{expert_id}/downloads
- Input: source_url, platform, creator, series_or_course, title, discovered_at, license_metadata.
- Output: download_record_id, state.
- A record is required for every downloaded video and must preserve source_url and platform.
- The archive destination is Google Drive under platform/creator/series-or-course.

### Register a direct event recording

- POST /v1/source-assets/{source_asset_id}/event-recordings
- Input: source/session ID, recorder type (rrweb or Windows UI Automation), recorder version, application/software version, session clock metadata, and the event stream or durable event-stream reference.
- Output: recording_id, accepted event count, capture status, warnings, and source references.
- Events contain timestamp, event type, page/window identity, target/element reference where available, and relevant before/after value or state.
- The service must preserve the original event payload and record capture gaps/provider limitations.

### Register narration and align transcript

- POST /v1/source-assets/{source_asset_id}/narration
- Input: original audio reference, supplied subtitles if available, language, transcript method, and optional word/segment timestamps.
- Output: narration_record_id, alignment status, transcript segments and provenance.
- Use existing subtitles first. ASR is a fallback only when usable subtitles are unavailable.
- Word-level alignment is preferred when supported and reliable; otherwise return segment-level timing with its granularity and uncertainty.

### Start decision extraction

- POST /v1/source-assets/{source_asset_id}/decision-extraction-jobs
- Input: event-recording reference, narration-record reference, extraction profile, and extraction-model revision.
- Output: job_id, state.
- The extraction service aligns semantic UI changes with instructor narration and produces Decision Episodes. It does not need a video-frame sequence as its primary input.
- For legacy MP4 sources without direct event telemetry, reconstructed events must be marked inferred_from_video and retain source time references.
- Every decision-driving fact and rationale must reference event, narration, project-owner, or other declared evidence.

### Register or update a workflow definition

- POST /v1/experts/{expert_id}/workflows
- Input: workflow_id, version, applicability, HTN tasks/methods, conditions, hard/soft edges, ordering constraints, invariants, transitions, capabilities, recovery rules, and evidence references.
- Output: workflow_version_id, validation status.
- Conflicting workflows and software-version variants coexist; they are not overwritten.
- Workflow updates create a new version.

### Query pipeline job

- GET /v1/pipeline-jobs/{job_id}
- Return stage, state, progress, warnings, error_code, output references, model/tool versions, timestamps, and measured resource metrics when available.

### Review a Decision Episode or workflow

- POST /v1/knowledge/{knowledge_id}/reviews
- Input: gate, decision (PASS / REJECT / NEEDS_EVIDENCE), comments, evidence/test references.
- Output: review_event_id, new_state.
- Both required review gates and the separate quality/trainable gate must pass before dataset admission.

### Freeze a Brain training dataset

- POST /v1/experts/{expert_id}/training-datasets
- Input: approved_episode_ids, workflow_versions, dataset_version, base_model_id.
- Output: dataset_snapshot_id, dataset_hash, grouped split manifest.
- The server rejects episodes that fail either review/quality gate.
- All fragments and near-duplicates from one tutorial/course/source must remain in one train/test partition.

### Start Brain LoRA training

- POST /v1/training-datasets/{dataset_snapshot_id}/brain-lora-training-jobs
- Input: base_model_id/revision, adapter_config, compute_profile.
- Output: training_job_id, state.
- Training metadata sidecars are not included in model input.
- The assistant target predicts the next Brain decision only; future Hands execution results are not target content.

### Evaluate a trained Brain with Hands

- POST /v1/experts/{expert_id}/evaluation-runs
- Input: adapter_revision, local_workflow_slice, simulated_or_live_hands_adapter, task_suite, unseen_task_suite.
- Output: evaluation_run_id, state.
- Evaluate Brain-only decisions with a simulated Hands executor before running end-to-end GUI tasks.
- End-to-end validation checks verified business postconditions and safe recovery, not click success alone.

## 3. Brain-to-Hands runtime contracts

### Brain delegation

The Brain sends a high-level operation_delegation containing:
- objective and registered capability_id;
- arguments, preconditions, constraints, and allowed scope;
- expected postconditions and observation requirements;
- risk and human-approval policy;
- call/task IDs and idempotency key.

The Brain does not send low-level mouse coordinates as its business plan.

### Hands execution result

Hands returns operation_result with:
- call/task IDs and execution status;
- observed state;
- postcondition results;
- action summary;
- error category/code/message;
- evidence/trace references.

A successful Hands status requires evidence-backed postcondition verification. The Brain decides the next step after inspecting the result.

## 4. Access control and integrity

- Every resource access validates expert/vertical scope.
- Hash-identical tutorial content is deduplicated; conflicting workflow knowledge is retained as separate versioned records.
- Reviewer identity comes from trusted runtime context; caller-provided identity strings are not authorization.
- Training dataset membership is server-enforced.
- Model/tool outputs remain untrusted until evidence and postcondition checks pass.
- High-risk external effects remain subject to separate authorization policy.

## 5. Version policy

- API uses /v1; breaking contract changes require a major version.
- Schema changes require compatibility tests and migration notes.
- This document is a target contract, not a claim that the API endpoints already exist.
