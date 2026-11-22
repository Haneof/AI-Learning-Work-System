# Core Data Model for Tutorial Learning and LoRA Experts

Version: V1.1  
Status: target logical model; implementation and migrations must be versioned separately.

## 1. Design rules

- Every acquired video has a download record with original source link and platform.
- Video assets are grouped by creator and series/course in Google Drive.
- SHA-256 identifies exact duplicate video content. A duplicate links to the existing asset; it does not erase its acquisition record.
- Conflicting knowledge and different applicability/version claims coexist; never overwrite one with another.
- Every trajectory step links to source video identity, time range, and supporting frames/audio/text.
- Direct observations and model inferences are stored separately.
- Only knowledge packages passing both GPT review and PM Sangou's independent verification enter the approved SQLite training corpus.
- LoRA training runs, base-model revisions, training-data snapshots, and adapter artifacts are immutable/versioned lineage.

## 2. Core entities

### download_record
- id (UUID, PK)
- source_url, platform (required)
- creator, series_or_course, title
- discovered_at, downloaded_at
- drive_file_id, drive_web_link, drive_path
- sha256, size_bytes, duration_ms
- license_value, license_source, license_status
- download_status, failure_reason
- duplicate_of_download_id (nullable FK)
- metadata_json

Every video gets a record even when later rejected by the clean/pre-filter stage.

### source_video
- id (UUID, PK)
- download_record_id (FK)
- content_sha256 (unique per exact content)
- storage_uri (Google Drive)
- creator, series_or_course, platform
- source_version, applicability_scope
- lifecycle_state (DOWNLOADED / PREFILTERED / REJECTED / READY_FOR_EXTRACTION / EXTRACTED)

### subtitle_transcript
- id (UUID, PK)
- source_video_id (FK)
- origin (EMBEDDED_SUBTITLE / SIDECAR_SUBTITLE / ASR)
- language, text, start_ms, end_ms
- model_name, model_version, configuration_json
- selected_for_prefilter (bool), quality_status

Prefer existing subtitles. ASR-generated subtitles are a fallback only when no usable subtitle source exists.

### source_segment
- id (UUID, PK)
- source_video_id (FK)
- segment_type (TIME_RANGE / FRAME / AUDIO_RANGE / SUBTITLE_RANGE)
- locator_json (start_ms/end_ms/frame_timestamp_ms/frame_index)
- media_uri, text_content, content_hash
- parser_or_model_name, version, created_at

### trajectory_step
- id (UUID, PK)
- source_video_id (FK)
- sequence_no, start_ms, end_ms
- action_description, target_element, candidate_coordinates_json
- intent_description, expected_outcome, observed_outcome
- pre_ui_state_json, post_ui_state_json
- observed_evidence_json (directly visible video or synchronized event telemetry)
- inferred_claims_json (predicted action/intent/causality, confidence, alternatives)
- evidence_segment_ids_json, model_name, model_version
- epistemic_status (OBSERVED / INFERRED / MIXED / UNKNOWN)
- review_state, created_at

A coordinate predicted by an action-grounding model is inference unless the actual click is visibly evidenced or captured by synchronized input-event telemetry.

### knowledge_package
- id (UUID, PK)
- expert_id, vertical_id
- package_version, package_hash
- purpose, conditions_json, judgement_criteria_json
- success_failure_experience_json, counterexamples_json, recovery_json
- trajectory_step_ids_json, evidence_refs_json
- lifecycle_state (CANDIDATE / GPT_PASSED / PM_VERIFIED / APPROVED / REJECTED / SUPERSEDED)
- applicability_scope, created_at

### review_event
- id (UUID, PK)
- knowledge_package_id (FK)
- gate (GPT_FIRST_PASS / PM_INDEPENDENT_VERIFICATION)
- decision (PASS / REJECT / NEEDS_EVIDENCE)
- reviewer_identity (GPT model/version or PM identity)
- checks_json (evidence_match, trajectory_consistency, UI_state_match, epistemic_separation, test_results)
- comments, created_at

No separate manual-reviewer role is part of this workflow. The required sequence is GPT check first, then PM Sangou independently verifies the original video evidence and relevant tests.

### training_dataset_snapshot
- id (UUID, PK)
- vertical_id
- dataset_version, dataset_hash
- approved_knowledge_package_ids_json
- included_source_hashes_json
- exclusions_json
- created_at, created_by

Only knowledge packages with both required PASS review events may be included.

### lora_training_run
- id (UUID, PK)
- vertical_id, training_dataset_snapshot_id (FK)
- base_model_id, base_model_revision
- adapter_id, adapter_revision
- training_config_json
- compute_provider, GPU_model, VRAM_GB
- status, started_at, finished_at
- peak_vram_gb, metrics_json, artifact_uri, adapter_sha256

### expert
- id (UUID, PK)
- name, vertical_id, description
- base_model_id, base_model_revision
- active_adapter_id, adapter_revision
- lifecycle_state (DATASET_READY / TRAINING / EVALUATING / READY / SUSPENDED)
- created_at, updated_at

The expert is the trained base-plus-LoRA model; the knowledge package is its provenance-backed training material.

## 3. Relationships

- download_record 1:1 source_video; duplicate download records may refer to a canonical source_video.
- source_video 1:N subtitle_transcript / source_segment / trajectory_step.
- trajectory_step N:M source_segment through evidence_segment_ids/evidence links.
- knowledge_package 1:N trajectory_step (or references steps from multiple source videos when explicitly designed).
- knowledge_package 1:N review_event.
- training_dataset_snapshot N:M approved knowledge_package.
- training_dataset_snapshot 1:N lora_training_run.
- lora_training_run produces a versioned adapter mounted on a base-model revision.
- expert references one base model and one active vertical adapter.

## 4. Required constraints

1. An approved knowledge package has evidence references and both required review events.
2. Observed claims have direct video or synchronized telemetry evidence; inferred claims carry confidence and supporting observations.
3. Hash-equal content is not redundantly re-extracted; conflicting knowledge is never silently overwritten.
4. Dataset snapshot membership is immutable and excludes rejected, pending, or superseded content.
5. Every adapter is traceable to a base revision, training dataset hash, and configuration.
6. Changing the base, adapter, or dataset creates a new version, not an in-place mutation.
7. SQLite is the selected store for structured pipeline records and review/training metadata. Large video objects remain in Google Drive.
8. Secrets, personal credentials, and private tokens are not included in records or logs.

## 5. Deferred

- Distributed multi-region storage.
- Advanced graph database and cross-expert automatic knowledge sharing.
- Automated compliance retention policy engine.
- Large-scale vector-index sharding.

These are not prerequisites for the first vertical LoRA expert.
