# Core State Machines

**Version:** 0.2, aligned with merged PRs #38–#42  
These logical state machines describe the current downloaded-video workflow and the required admission/runtime gates. Implementation state and artifact status must remain auditable.

## 1. Acquisition and download

~~~text
DISCOVERED -> SELECTED -> DOWNLOADING -> DOWNLOADED -> ARCHIVED
                  |             |
                  |             +-> FAILED
                  +-> REJECTED
~~~

- DISCOVERED: tutorial candidate found with source URL and platform.
- SELECTED: selected for download.
- DOWNLOADING: video and available timed subtitle files are being retrieved.
- DOWNLOADED / ARCHIVED: source file is available for local processing and its per-video record is persisted.
- REJECTED: not selected for acquisition.
- FAILED: download or archive operation failed; retry is bounded and logged.

Every selected file retains its original URL and platform, source hash, attribution/license metadata, and creator/course grouping when available.

## 2. Downloaded video-file extraction (PR #38)

~~~text
DOWNLOADED
    -> MEDIA_PROBED
    -> TRANSCRIPT_READY
    -> FRAMES_SAMPLED
    -> SCREEN_CHANGES_SELECTED
    -> VISUAL_EVIDENCE_EXTRACTED
    -> NARRATION_ALIGNED
    -> EPISODE_ASSEMBLED
    -> CONTRACT_VALIDATED
~~~

Failure/hold branches may occur at each stage:
- MEDIA_PROBE_FAILED
- TRANSCRIPT_MISSING / TRANSCRIPT_INVALID
- FRAME_DECODE_FAILED
- OCR_FAILED / GROUNDING_UNAVAILABLE
- ALIGNMENT_INCOMPLETE
- EPISODE_NEEDS_EVIDENCE
- CONTRACT_INVALID

Stage semantics:
- MEDIA_PROBED: local video metadata/duration are available.
- TRANSCRIPT_READY: usable SRT/WebVTT was loaded, or local ASR produced time-bounded segments because usable subtitles were absent.
- FRAMES_SAMPLED: FFmpeg decoded timestamped stills from the downloaded file.
- SCREEN_CHANGES_SELECTED: pixel-difference detection selected the initial state and screen-change frames.
- VISUAL_EVIDENCE_EXTRACTED: OCR, cursor candidate, possible-click, and local UI-target grounding artifacts are recorded with source timestamps and method.
- NARRATION_ALIGNED: timestamped transcript segments are aligned with visual changes.
- EPISODE_ASSEMBLED: DecisionEpisode content and evidence references are generated; inferred and unknown claims remain explicit.
- CONTRACT_VALIDATED: JSON Schema and semantic validation pass. This does not mean the content is true or approved for training.

This process is file-based and offline. It does not play the video in real time or depend on a live tutorial recorder. Cursor/click/target hypotheses derived from pixels are inferred_from_video; they are not native DOM, UIA, mouse, or keyboard events.

## 3. Local verifier and independent PM gate (PR #39)

~~~text
CONTRACT_VALIDATED -> LOCAL_VERIFYING
                         |
                         +-> LOCAL_PASS (all 3 levels)
                         +-> LOCAL_FAIL
                         +-> LOCAL_UNKNOWN / HELD
LOCAL_PASS -> PM_REVIEW_PENDING -> PM_PASS -> TRAINING_ADMISSION_CANDIDATE
                                  |-> PM_REJECT
                                  |-> PM_NEEDS_EVIDENCE
~~~

- LOCAL_PASS requires extraction_fidelity, decision_validity, and outcome_validity all to pass. No majority vote is permitted.
- LOCAL_FAIL remains excluded from training admission.
- LOCAL_UNKNOWN / HELD covers missing evidence, invalid references, unavailable/malformed model output, or unresolved claims.
- PM_REVIEW_PENDING means local PASS is not yet approval; the PM must independently inspect the source video and proposed episode.
- PM_PASS requires evidence references to source material and reviewed episode claims.
- PM_REJECT and PM_NEEDS_EVIDENCE remain traceable but are not trainable.

A video-only time sequence is not causal proof that an operation executed or achieved a business result; outcome validity must remain unknown unless supported by independent operation/business evidence.

## 4. Training-sample compilation (PR #40)

~~~text
TRAINING_ADMISSION_CANDIDATE
    + EPISODE_REVIEW_APPROVED
    + QUALITY_TRAINABLE
    -> COMPILATION_ELIGIBLE
    -> SAMPLES_COMPILED
    -> SOURCE_GROUPED_SPLIT
    -> DATASET_PREPARED
~~~

Any missing/failed gate or quality check transitions to HELD / EXCLUDED.

- SAMPLES_COMPILED: one decision-time conversational sample is emitted per decision point.
- SOURCE_GROUPED_SPLIT: all samples from the same source/course group remain in one partition; separate sidecars contain evidence metadata and are not model inputs.
- Future Hands results are not included in earlier assistant targets.
- Held, rejected, duplicate-invalid, malformed, or ineligible rows cannot be silently filtered into an approved dataset.

## 5. Brain LoRA preparation and training (PR #41)

~~~text
DATASET_PREPARED -> CONFIG_VALIDATED -> TRAINING_READY -> TRAINING
                                                     |       |
                                                     |       +-> TRAINING_FAILED
                                                     +-> WAITING_FOR_APPROVED_CORPUS
TRAINING -> ADAPTER_PRODUCED -> ADAPTER_EVALUATING -> ADAPTER_ACCEPTED / ADAPTER_REJECTED
~~~

- CONFIG_VALIDATED: the metadata-aware train/test data and T4 Axolotl LoRA configuration pass structural checks.
- WAITING_FOR_APPROVED_CORPUS: the training setup exists, but a real eligible corpus or sufficient source groups are not available.
- TRAINING: an actual configured training job is executing on provisioned compute.
- ADAPTER_PRODUCED: weights and their run metadata/hash exist after a successful real training run.

PR #41 delivered dataset preparation and configuration validation only. It did not run Axolotl training or produce adapter weights. Do not transition to ADAPTER_PRODUCED merely because config validation passes.

## 6. Brain-to-Hands operation and expert evaluation (PR #42)

~~~text
GOAL_RECEIVED -> STATE_OBSERVED -> BRAIN_DECIDES
                                      |
                  +-------------------+---------------------+
                  |                   |                     |
               ASK_USER          REQUEST_APPROVAL         DELEGATE
                                                            |
                                                    HANDS_EXECUTING
                                                            |
                                                    HANDS_RESULT_RECEIVED
                                                            |
                                                    FRESH_STATE_OBSERVED
                                                            |
                                                   POSTCONDITIONS_CHECKED
                                                            |
                              +-----------------------------+------------------+
                              |                             |                  |
                          CONTINUE/BRANCH                RECOVER/REPLAN     SAFE_STOP
                              |
                         GOAL_VERIFIED
~~~

The Brain sends a high-level business capability request. Hands returns a correlated operation result with status, observed state, postcondition checks, error details, and evidence references. The loop observes fresh state and independently checks expected postconditions before allowing progress. Failed, partial, timed-out, or uncertain results are returned to Brain for recovery; non-idempotent actions are not blindly retried.

The merged PR #42 CI acceptance uses a deterministic WorkflowBrain stand-in and SimulatedHands. BrowserAgentHandsAdapter reuses the existing GUI execution machinery but requires a domain-specific fresh business-state observer. No real trained Brain adapter or real UI-TARS-class model was run for that PR.

## 7. Superseded tutorial event-collector route

The proposed live rrweb web recorder and Windows UI Automation desktop recorder/event collector was cancelled on **2026-11-21** and superseded by downloaded-video-file extraction. The selected route works from tutorial files without installing and synchronizing a recorder in each live application/session. Keep the cancelled route as historical context only; do not model it as an active ingestion state machine or required fallback.

This cancellation does not remove the separate live GUI observations and trace artifacts used by the Hands execution layer at runtime.

## 8. State transition requirements

- Every extraction, verification, review, compilation, training, and runtime transition records source ID, state, actor/model/tool version, input hashes, output refs, and failure/hold reason.
- Missing evidence never silently advances an episode to approved.
- Local verifier PASS and PM PASS are separate gates.
- Illegal transitions are rejected and audited.
- Dataset membership and train/test assignment are immutable once snapshotted.
- Retries are bounded and idempotent; source hash and operation configuration form part of task identity.
- Pending, rejected, or quality-excluded items cannot enter an approved Brain training dataset.
- Expert release requires actual Brain evaluation and Brain-to-Hands validation, not only passing schema/configuration checks.

## Historical model experiment

The Qwen3-VL-4B vs Mage-VL-4B Colab T4 blind test was stopped on 2026-11-21 at approximately 19:51 PST after Qwen3-VL-4B scored 4.0/25. No winner was selected. This incomplete comparison did not reject frame extraction; frame-change-driven processing of downloaded video files is the current route.