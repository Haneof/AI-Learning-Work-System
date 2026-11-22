# Core Data Model for Tutorial Workflow Learning and LoRA Experts

**Version:** 0.1 design update  
**Status:** target logical model; implementation and migrations must be versioned separately.

## 1. Design rules

- Every acquired tutorial has a download record with original source link and platform.
- Original videos are grouped by creator and series/course in Google Drive.
- SHA-256 identifies exact duplicate source content. A duplicate links to the canonical source but does not erase its acquisition record.
- Tutorial learning starts from downloaded video files; visible observations and inferred interactions are separately labelled.
- Instructor narration is preserved and aligned to the same timeline as UI events.
- Each Decision Episode records the business decision point, not just a UI click.
- HTN workflows retain conditions, dependencies, branches, alternatives, and recovery paths.
- Conflicting workflows and different applicability/software versions coexist; never overwrite one another.
- Only records passing both review gates and the quality/trainable gate enter the approved Brain training corpus.
- Dataset snapshots, base revisions, LoRA runs, and adapter artifacts are immutable/versioned lineage.

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
- course_group_id (nullable)
- metadata_json

Every downloaded video gets a record, including items later rejected by the text pre-filter.

### source_asset

- id (UUID, PK)
- download_record_id (FK)
- content_sha256
- storage_uri (Google Drive or local processing reference)
- creator, series_or_course, platform
- source_kind (DOWNLOADED_VIDEO / LIVE_TASK_TRACE)
- software_name, software_version (when known from source)
- media_duration_ms, subtitle_asset_refs_json
- lifecycle_state (DOWNLOADED / PROBED / EVIDENCE_EXTRACTED / EPISODES_DRAFTED / LOCALLY_VERIFIED / PM_APPROVED / REJECTED)
- extraction_profile_json, extractor_version

The primary tutorial source is the downloaded file. A runtime Hands trace is a separate execution artifact and must not be confused with tutorial ingestion or a cancelled live tutorial recorder.

### video_observation

- id (UUID, PK)
- source_asset_id (FK)
- event_sequence_no
- timestamp_ms, end_timestamp_ms (when an interval is available)
- observation_type (INITIAL_FRAME / SCREEN_CHANGE / OCR_REGION / CURSOR_CANDIDATE / CLICK_HYPOTHESIS / UI_TARGET_GROUNDING / OTHER)
- observation_channel (OBSERVED_FROM_VIDEO / INFERRED_FROM_VIDEO / UNKNOWN)
- frame_index, frame_ref, source_time_range_json
- visible_text, target_box_json, cursor_candidate_json
- before_visual_state_json, after_visual_state_json
- extraction_tool, extraction_model, tool_or_model_version
- confidence, source_locator_json
- raw_record_ref

This replaces the old tutorial-ingestion assumption that each row is a directly captured DOM/click/UIA event. A decoded frame or OCR region is an observation from the video; a cursor/click or target interpretation is an inference. The video file does not supply native DOM, Windows UIA, mouse, or keyboard telemetry. Runtime GUI/Hands traces, when used, are stored separately.

### narration_segment

- id (UUID, PK)
- source_asset_id (FK)
- speaker_role
- text, language
- start_ms, end_ms
- transcript_origin (EMBEDDED_SUBTITLE / SIDECAR_SUBTITLE / ASR / HUMAN_TRANSCRIPT)
- alignment_method, alignment_model, alignment_version
- word_timestamps_json (nullable)
- alignment_confidence, quality_status
- raw_audio_ref, transcript_ref

Prefer usable existing subtitles; use ASR only when subtitle sources are unavailable. Preserve whether the timing is word-level or segment-level.

### decision_episode

- id (UUID, PK)
- expert_id, workflow_id, workflow_version
- source_asset_id (FK)
- task_goal, success_criteria_json
- state_before_json, state_after_json
- narration_segment_ids_json
- relevant_video_observation_ids_json
- decision_type
- selected_strategy, rationale_summary
- decision_basis_json, applicable_conditions_json
- selected_next_step_json
- operation_capability_id, operation_arguments_json
- operation_status
- postcondition_checks_json
- outcome_status, next_action, next_step_reason
- evidence_refs_json, uncertainties_json
- review_status, approved_for_training
- annotation_status, trainable, exclusion_reasons_json
- created_at, reviewed_at

A Decision Episode must describe the goal/state/reason/decision/operation/result/next-decision relationship. A plain click list is not a Decision Episode.

### workflow_definition

- id (UUID, PK)
- expert_id, workflow_id, version
- name, domain, goal
- applicability_json (software versions, business context, conditions)
- success_conditions_json
- tasks_json (compound and primitive HTN tasks)
- methods_json (applicability conditions and subtask decomposition)
- edges_json (HARD_DEPENDENCY / SOFT_PREFERENCE)
- ordering_constraints_json
- invariants_json
- transitions_json
- recovery_rules_json
- capability_registry_version
- evidence_refs_json
- lifecycle_status
- created_at

A workflow is scoped by source, software version, and applicability conditions. Conflicting variants coexist.

### operation_capability

- capability_id (PK)
- version
- description
- hands_adapter_id
- argument_schema_json
- preconditions_json
- expected_postconditions_json
- risk_level
- idempotent
- availability_status

Primitive HTN tasks map to registered capabilities. The capability registry is an integration contract with the existing Hands model, not a new low-level GUI agent.

### review_event

- id (UUID, PK)
- decision_episode_id or workflow_definition_id
- gate (FIRST_REVIEW / PM_INDEPENDENT_VERIFICATION)
- decision (PASS / REJECT / NEEDS_EVIDENCE)
- reviewer_identity and model/version where applicable
- checks_json (evidence resolution, event/narration alignment, decision/condition logic, uncertainty, test results)
- comments, created_at

There is no additional external manual-reviewer queue. Both required gates must pass.

### training_example

- id (UUID, PK)
- decision_episode_id (FK)
- sample_type (NORMAL_DECISION / ERROR_RECOVERY)
- messages_json (system/user/assistant)
- source_decision_point_ref
- split_group_id (tutorial/course/source grouping key)
- train_or_test_partition
- created_at

Assistant targets contain the Brain's next decision only. They must not contain future Hands execution outcomes.

### training_meta

- training_example_id (FK)
- evidence_tier
- rationale_loss_weight (nullable)
- sidecar_version

This sidecar is not fed to the model. It is stored separately from the conversational messages.

### training_dataset_snapshot

- id (UUID, PK)
- expert_id, dataset_version, dataset_hash
- approved_decision_episode_ids_json
- training_example_ids_json
- included_source_hashes_json
- split_manifest_json (grouped by tutorial/course/source)
- exclusions_json
- created_at, created_by

### lora_training_run

- id (UUID, PK)
- expert_id, training_dataset_snapshot_id (FK)
- base_model_id, base_model_revision
- adapter_id, adapter_revision
- training_config_json
- compute_provider, GPU_model, VRAM_GB
- status, started_at, finished_at
- peak_vram_gb, metrics_json, artifact_uri, adapter_sha256

### expert

- id (UUID, PK)
- name, vertical_id, description
- brain_base_model_id, base_model_revision
- active_lora_adapter_id, adapter_revision
- hands_adapter_id, capability_registry_version
- lifecycle_state (DATASET_READY / TRAINING / EVALUATING / READY / SUSPENDED)
- created_at, updated_at

An expert is the Brain base-plus-LoRA paired with a configured Hands integration. Decision Episodes and WorkflowDefinitions are training and runtime knowledge assets.

## 3. Relationships

- download_record 1:1 source_asset; duplicate acquisition records may refer to a canonical source_asset.
- source_asset 1:N video_observation and narration_segment.
- source_asset 1:N decision_episode.
- decision_episode N:M video_observation and narration_segment through evidence references.
- decision_episode N:1 workflow_definition version.
- workflow_definition N:M operation_capability through primitive task mappings.
- decision_episode/workflow_definition 1:N review_event.
- training_example N:1 decision_episode; training_meta 1:1 training_example.
- training_dataset_snapshot N:M approved training_example and decision_episode.
- training_dataset_snapshot 1:N lora_training_run.
- lora_training_run produces a versioned Brain adapter.
- expert references one Brain base, one active vertical adapter, and one Hands adapter/capability registry.

## 4. Required constraints

1. Every referenced evidence ID resolves to a source event, narration segment, or other declared evidence record.
2. Timestamps are ordered and remain within the source duration when known.
3. Directly captured UI events and legacy-video inferences remain distinguishable.
4. Instructor-explicit rationale, behavioral inference, project-owner-provided rules, and unknown information remain distinguishable.
5. A successful operation outcome requires evidence-backed postcondition verification.
6. Hard dependencies and hard ordering constraints must not contain cycles.
7. Every primitive workflow task maps to a registered operation capability.
8. Invariants must be present in the guarded tasks' preconditions and cannot be bypassed.
9. Training samples contain only information available at their decision point. Future execution outcomes are excluded from the assistant target.
10. Train/test splitting is grouped by tutorial/course/source so near-duplicate fragments cannot cross partitions.
11. Only examples passing both review gates and the quality/trainable gate may be included in an approved dataset snapshot.
12. A Hands capability call must resolve against the configured capability registry.
13. SQLite is the selected store for structured pipeline records and lineage metadata. Large original tutorial files remain in Google Drive.
14. Secrets, personal credentials, and private tokens are excluded from records and logs.

## 5. Deferred

- Distributed multi-region storage.
- Automated workflow conflict resolution across all software versions.
- Large-scale vector-index sharding.
- Automatic cross-expert workflow sharing.
- A replacement page-perception/action model.

These are not prerequisites for the first Brain LoRA expert.
