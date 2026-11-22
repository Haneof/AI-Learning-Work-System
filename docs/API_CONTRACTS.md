# API Contracts for Workflow Learning (Logical MVP)

**Version:** 0.1 design target  
These logical contracts do not imply that every service is implemented.

## 1. General conventions

- JSON UTF-8; timestamps use ISO 8601 UTC or integer milliseconds relative to the source video timeline, as declared by the schema.
- IDs use UUID or stable source-scoped identifiers.
- Long-running download, extraction, alignment, review, and training operations return job/task IDs.
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

### Register a tutorial video file

- POST /v1/source-assets/{source_asset_id}/video
- Input: downloadable/local video-file reference, source URL, platform, source hash, duration metadata when available, and optional subtitle-file references.
- Output: video_asset_id, media probe status, file metadata, and source references.
- Preserve the original file and any supplied SRT/WebVTT file. Record extraction provenance against the source file and its time range.
- This contract does not register a live rrweb or Windows UI Automation event stream. The live event-collector proposal was cancelled on 2026-11-21 and remains historical only.

### Register narration and align transcript

- POST /v1/source-assets/{source_asset_id}/narration
- Input: original audio reference, supplied subtitles if available, language, transcript method, and optional word/segment timestamps.
- Output: narration_record_id, alignment status, transcript segments and provenance.
- Use existing subtitles first. ASR is a fallback only when usable subtitles are unavailable.
- Word-level alignment is preferred when supported and reliable; otherwise return segment-level timing with its granularity and uncertainty.

### Start video-file extraction

- POST /v1/source-assets/{source_asset_id}/decision-extraction-jobs
- Input: downloaded video-file reference, optional subtitle-file reference, extraction profile, and local extraction-model revisions/configuration.
- Output: job_id, state, stage reports, and artifact references.
- The extractor prefers usable timed subtitles and otherwise runs local ASR. It decodes sampled frames from the file, detects screen changes, runs OCR and local cursor/UI-target inference on selected frames, aligns narration to visual events, builds DecisionEpisodes, and performs contract validation.
- All inferred cursor/click/target information must remain labelled inferred_from_video. Video-derived observations must not be presented as native DOM/UIA/mouse/keyboard telemetry.
- The selected process operates on downloaded files; it does not play the video in real time or require a live event collector.

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
