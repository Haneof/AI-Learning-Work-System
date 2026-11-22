# Acceptance Criteria

Version: V1.1  
The pipeline is accepted on quality and verified expert behavior, not on transcript volume or raw throughput.

## Step 1 — Download and archive

- Every selected video has a download record with source link and platform.
- Creator/series grouping is preserved in the 5TB Google Drive archive.
- Original metadata and license uncertainty are not fabricated.
- SHA-256 is recorded to identify exact duplicate content.

## Step 2 — Clean and extract

- Existing subtitles are used first; ASR runs only when usable subtitles are unavailable.
- The transcript/text pre-filter identifies both tutorial content and relevance to the target vertical.
- Rejected videos retain their source/download record and rejection reason; they do not enter full extraction.
- Full extraction watches relevant frames/clips and listens to audio.
- Output explains actions, intent, target controls/coordinates, pre/post UI states, visible changes, expected outcomes, preconditions, exceptions, and recovery evidence.
- Transcription-only, OCR-only, or a fluent generic summary does not pass.
- Every step has source/time evidence and separate observed/inferred fields.
- No predicted action is mislabeled as a directly recorded historical click.

## Step 3 — Deduplicate, review, and store

- Exact duplicate video content is identified by SHA-256.
- Conflicting claims and different applicability/version records coexist; no overwrite.
- GPT first checks evidence match, trajectory consistency, state changes, and epistemic labels.
- PM Sangou independently verifies the candidate against source video evidence and relevant tests.
- No separate human-review queue is introduced.
- Only candidates passing both gates enter the approved SQLite store and training dataset snapshot.
- Failed or uncertain candidates retain traceable rejection/hold reasons and cannot enter the training snapshot.

## Step 4 — LoRA and expert validation

- Training dataset contains only double-approved knowledge packages.
- Every dataset snapshot and training run records sample hashes, base revision, configuration, compute/GPU, and output adapter hash.
- The 4B BF16 LoRA path is planned for a T4 16GB cloud GPU; the 9B path requires 24GB+.
- The adapter is loaded on the designated 4B base model.
- The trained expert is tested in Docker sandbox and the GUI operation loop.
- Passing requires flexible task completion under changed UI states and unseen variations, not only replaying memorized tutorial steps.
- Unsafe actions, unsupported claims, or unverified outcomes block acceptance.

## Quality metrics

Freeze thresholds before the final blind test. At minimum, measure:

- action-step precision/recall, order, and temporal localization;
- intent and causal explanation correctness;
- UI element and before/after state correctness;
- action outcome correctness;
- coordinate/target grounding accuracy;
- evidence-match rate and unsupported-claim rate;
- observed/inferred classification accuracy;
- generalization to unseen initial states, interface changes, and alternative valid routes;
- sandbox safety and GUI operation success.

Throughput, GPU utilization, cost per source hour, and GB/video hours are optimized only after the quality gates pass.

## Release blocking

Any missing critical evidence, false observed-action claim, material trajectory inconsistency, unreviewed training sample, model/version provenance gap, or critical sandbox/GUI safety failure blocks release.
