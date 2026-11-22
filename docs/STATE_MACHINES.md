# Core State Machines

Version: V1.1  
Status: target logical definitions; implementation must enforce transitions in code and tests.

## 1. Acquisition and download

```text
DISCOVERED -> SELECTED -> DOWNLOADING -> DOWNLOADED -> ARCHIVED
                  |             |
                  |             +-> FAILED
                  +-> REJECTED
```

- DISCOVERED: tutorial candidate found with source URL and platform.
- SELECTED: selected for download.
- DOWNLOADING: cloud download to Google Drive is active.
- DOWNLOADED / ARCHIVED: file is present in the creator/series course folder and the per-video download record is persisted.
- REJECTED: not selected for acquisition.
- FAILED: download or archive operation failed; retry is bounded and logged.

Every video record retains its original URL and platform, including videos later rejected by the pre-filter.

## 2. Clean / pre-filter

```text
SUBTITLE_CHECK -> TEXT_READY -> PREFILTERING -> PREFILTER_PASSED
       |                         |
       +-> ASR_FALLBACK -> TEXT_READY
                                 +-> PREFILTER_REJECTED
```

- SUBTITLE_CHECK: inspect embedded and sidecar subtitles.
- TEXT_READY: usable existing subtitles extracted, or ASR transcript created only when no usable subtitle exists.
- ASR_FALLBACK: produce timestamped subtitles when source subtitles are absent.
- PREFILTERING: classify tutorial status and target-vertical relevance.
- PREFILTER_PASSED: eligible for full multimodal understanding.
- PREFILTER_REJECTED: retain record and reason; do not run expensive full extraction.

## 3. Full multimodal extraction

```text
PREFILTER_PASSED -> UNDERSTANDING -> GROUNDING -> TRAJECTORY_READY
                         |              |
                         +-> FAILED     +-> PARTIAL / NEEDS_EVIDENCE
```

The understanding stage uses Qwen3-VL or Mage-VL to interpret video/audio, operation, intent, UI state changes, and outcome. The grounding stage uses Magma to produce candidate target regions, click points, or trajectories. Their outputs have separate contracts and evaluation metrics.

Trajectory steps must retain time/frame/audio evidence and observed/inferred labels. Missing or ambiguous historical click evidence cannot be upgraded into an observed event.

## 4. Deduplication and review

```text
TRAJECTORY_READY -> HASH_DEDUPED -> GPT_REVIEW_PASSED -> PM_VERIFIED -> APPROVED
                          |                 |                 |
                          +-> DUPLICATE     +-> REJECTED      +-> REJECTED
                          +-> CONFLICTS_RETAINED
```

- Exact duplicate video content is linked by SHA-256 and is not redundantly extracted.
- Conflicting knowledge statements coexist and retain separate evidence; no overwrite.
- GPT checks evidence match, trajectory consistency, UI-state changes, and observed/inferred separation.
- PM Sangou independently checks the original video evidence and relevant tests.
- There is no separate external human-review queue.
- Only items passing both gates become APPROVED and enter SQLite verified storage/training snapshots.

## 5. LoRA dataset and training

```text
APPROVED -> DATASET_SNAPSHOTTED -> TRAINING_QUEUED -> TRAINING -> ADAPTER_READY
                                                        |              |
                                                        +-> FAILED     +-> EVALUATING
```

A dataset snapshot is immutable and contains only double-approved knowledge packages. Record the base-model revision, dataset hash, training parameters, GPU, peak resource use, and adapter hash.

Planning capacity: 4B BF16 LoRA on a 16GB T4; 9B on a 24GB+ GPU. Treat measured training logs as authoritative over this estimate.

## 6. Expert evaluation and lifecycle

```text
ADAPTER_READY -> SANDBOX_EVALUATION -> GUI_EVALUATION -> READY
                       |                    |
                       +-> FAILED           +-> FAILED / NEEDS_REVISION
```

Evaluation checks the expert's ability to understand goals, select actions based on current UI state, verify results, handle exceptions, and generalize to unseen variations. Passing a fixed replay alone is insufficient.

## 7. State transition requirements

- All state changes use a controlled transition function/domain service.
- Each transition records source state, target state, actor/model, guard, input hashes, output references, and failure reason.
- Illegal transitions are rejected and audited.
- Retries are bounded and idempotent; source hash and operation configuration form part of task identity.
- Review decisions and dataset membership are immutable once snapshotted.
- A failed or pending item cannot be included in an approved LoRA training dataset.
- Expert release requires passing sandbox and GUI operation loop evaluations.
