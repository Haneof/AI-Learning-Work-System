# Core State Machines

**Version:** 0.1 design update  
**Status:** target logical definitions; implementation must enforce transitions in code and tests.

## 1. Acquisition and download

~~~text
DISCOVERED -> SELECTED -> DOWNLOADING -> DOWNLOADED -> ARCHIVED
                  |             |
                  |             +-> FAILED
                  +-> REJECTED
~~~

- DISCOVERED: tutorial candidate found with source URL and platform.
- SELECTED: selected for download.
- DOWNLOADING: cloud download to Google Drive is active.
- DOWNLOADED / ARCHIVED: file is present in the creator/series course folder and the per-video download record is persisted.
- REJECTED: not selected for acquisition.
- FAILED: download or archive operation failed; retry is bounded and logged.

Every video record retains its original URL and platform, including videos later rejected by the pre-filter.

## 2. Direct event capture

~~~text
SESSION_CREATED -> CAPTURE_READY -> CAPTURING_EVENTS -> EVENT_STREAM_CLOSED
                         |                  |
                         +-> CAPTURE_BLOCKED +-> PARTIAL / CAPTURE_FAILED
~~~

- SESSION_CREATED: source asset and recording session are registered.
- CAPTURE_READY: rrweb or Windows UI Automation is configured and the session clock is available.
- CAPTURING_EVENTS: semantic UI events are persisted with timestamps and source/session identity.
- EVENT_STREAM_CLOSED: recording ended and the event stream is finalized.
- PARTIAL: some event providers or controls were unsupported, or a capture gap occurred; the limitations are recorded.
- CAPTURE_FAILED: event capture did not produce a usable stream.

For legacy MP4 sources without event telemetry, a separate reconstruction path creates inferred_from_video event candidates. It must not enter the direct-capture state.

## 3. Narration transcription and alignment

~~~text
AUDIO_REGISTERED -> SUBTITLE_CHECK -> TRANSCRIPT_READY -> ALIGNING -> ALIGNED
                         |                |                 |
                         +-> ASR_FALLBACK +-> ALIGNMENT_FAILED
~~~

- AUDIO_REGISTERED: original instructor audio and synchronization metadata are stored.
- SUBTITLE_CHECK: inspect embedded and sidecar subtitles.
- TRANSCRIPT_READY: usable subtitles are selected, or ASR output is created only when no usable source subtitle exists.
- ALIGNING: word/segment timestamps are aligned to the audio and recording timeline.
- ALIGNED: text segments can be correlated with UI events.
- ALIGNMENT_FAILED: timing confidence is insufficient; keep uncertainty and do not invent event/rationale links.

## 4. Decision Episode extraction and workflow construction

~~~text
EVENTS_AND_NARRATION_READY -> EPISODE_EXTRACTION -> EPISODES_DRAFT
                                      |                  |
                                      +-> NEEDS_EVIDENCE +-> WORKFLOW_DRAFT
~~~

The extraction stage aligns event and narration records to produce Decision Episodes. It distinguishes instructor-explicit statements from behavioral inference and keeps unknown facts explicit.

Workflow construction groups episodes into HTN task/method structures and conditional branches. Hard dependencies, soft preferences, invariants, and recovery paths remain explicit. A tutorial's demonstrated order is not automatically the only valid workflow.

## 5. Deduplication and review

~~~text
WORKFLOW_DRAFT -> HASH_DEDUPED -> FIRST_REVIEW_PASSED -> PM_VERIFIED -> APPROVED
                       |                  |                 |
                       +-> DUPLICATE      +-> REJECTED      +-> REJECTED
                       +-> CONFLICTS_RETAINED
~~~

- Exact duplicate source content is linked by SHA-256 and not redundantly reprocessed.
- Conflicting workflows coexist with their source/software-version/applicability scope.
- First review checks event/narration evidence, decision logic, conditions, workflow consistency, and uncertainty.
- PM Sangou independently checks the source tutorial and relevant tests.
- Only items passing both review gates and the separate quality/trainable gate become APPROVED and enter SQLite verified storage/training snapshots.

## 6. Brain dataset and training

~~~text
APPROVED -> DATASET_SNAPSHOTTED -> TRAINING_QUEUED -> TRAINING -> BRAIN_ADAPTER_READY
                                                        |                |
                                                        +-> FAILED       +-> EVALUATING
~~~

A dataset snapshot is immutable, grouped by tutorial/course/source, and contains only eligible decision examples. The assistant target ends at the Brain's next decision; future execution outcomes are excluded. Record the base-model revision, dataset hash, training parameters, GPU, peak resource use, and adapter hash.

## 7. Brain-to-Hands operation and expert evaluation

~~~text
BRAIN_PLANNED -> DELEGATION_SENT -> HANDS_EXECUTING -> HANDS_RESULT_RECEIVED -> BRAIN_VERIFIES
                                                                                   |
                                        +------------------------------------------+
                                        |
             CONTINUE / BRANCH / RECOVER / REPLAN / ASK / APPROVAL / FINISH / STOP
~~~

The Brain supplies a high-level capability request. The Hands adapter calls the existing operation model and returns status, observed state, postcondition checks, error details, and evidence references. The Brain then makes the next decision.

A successful tool call or click alone does not establish a successful business result. Evaluation must cover changed initial states, alternative methods, partial failures, and unseen tasks.

## 8. State transition requirements

- All state changes use a controlled transition function/domain service.
- Each transition records source state, target state, actor/model, guard, input hashes, output references, and failure reason.
- Illegal transitions are rejected and audited.
- Retries are bounded and idempotent; source hash and operation configuration form part of task identity.
- Review decisions and dataset membership are immutable once snapshotted.
- Pending, rejected, or quality-excluded items cannot enter an approved Brain training dataset.
- Expert release requires both Brain decision evaluation and Brain-to-Hands sandbox/GUI validation.

## Historical experiment status

The Qwen3-VL-4B vs Mage-VL-4B Colab T4 blind test was stopped on 2026-11-21 at approximately 19:51 PST after Qwen3-VL-4B scored 4.0/25. No winner was selected. The frame-based extraction route was rejected as the primary tutorial-learning method.
