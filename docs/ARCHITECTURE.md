# System Architecture

## Product architecture

The system's primary product is a set of domain experts: one shared 4B base model with different vertical LoRA adapters. Verified tutorial knowledge is the training data used to produce those adapters. A transcript, summary, compiled skill package, or sandbox report is not the final product.

## Four-step data flow

1. **Download**: web-search target-vertical tutorials; use a cloud downloader to place them directly in the 5TB Google Drive; group by creator and series/course; retain one download record per video with source link and platform.
2. **Clean and extract**:
   - extract existing subtitles first, or use ASR to create timestamped subtitles only when none are available;
   - pre-filter by text to retain only tutorials relevant to the selected vertical;
   - run full multimodal extraction only on matches. Qwen3-VL/Mage-VL understand video and audio and produce evidence-linked text; Magma grounds candidate click points and action trajectories;
   - represent each action, intent, UI state transition, and result with time-linked evidence, separating observed facts from inference.
3. **Deduplicate, review, store**: deduplicate by content hash; preserve conflicts without overwrite; GPT reviews evidence match, trajectory consistency, and epistemic labels; PM Sangou independently verifies against video evidence and tests; only candidates passing both gates enter SQLite.
4. **Train and validate LoRA**: verified knowledge packages become LoRA training data. Train on cloud GPU, bring the adapter back, and mount it on the 4B base. One base plus different vertical adapters yields different experts. Validate trained experts in the Docker sandbox and GUI operation loop.

## Model boundaries

| Model family | Architectural responsibility | Output contract |
|---|---|---|
| Qwen3-VL | Video understanding | Time-grounded text: what happened, why, visible state changes, outcome, evidence |
| Mage-VL | Alternative video understanding candidate | Same semantic/text task, independently benchmarked against Qwen3-VL |
| Magma | Action grounding | Coordinate/action-oriented candidates: click points, regions, trajectories |

These responsibilities are separate. The understanding candidates must be tested for semantic correctness, action/intent interpretation, and state-transition understanding. Magma must be tested for coordinate/action grounding. No single aggregate score may conceal a failure in either role. Qwen3-VL vs Mage-VL blind evaluation on Colab T4 is ongoing; the architecture records no result or winner.

## Evidence and epistemic boundary

For each extracted step, preserve source video identity/hash, time interval, frame references, transcript references, model/version, and review state. Use `observed` only for information directly visible in the video or captured by synchronized input-event logs. Use `inferred` for model-interpreted actions, hidden clicks, intent, or causality. A predicted Magma coordinate is a candidate inference, not proof of an actual click. Uncertainty and conflicts remain explicit.

## Layered services

- **Acquisition service**: web search, platform adapters, cloud download, course grouping, download records, Drive archive.
- **Pre-filter service**: subtitle discovery/extraction, ASR fallback, tutorial/vertical text classification.
- **Multimodal understanding service**: video/audio context, temporal event segmentation, semantic action/intent/UI-state extraction.
- **Action-grounding service**: candidate target regions, click coordinates, and trajectories.
- **Review and knowledge service**: content-hash deduplication, conflicts, evidence validation, GPT review, PM verification, SQLite persistence.
- **Training service**: verified dataset snapshot, LoRA training jobs, adapter/model lineage, evaluation reports.
- **Validation harness**: skill-package compiler, static checks, Docker sandbox, and GUI operation loop for testing trained experts.
- **Orchestrator and audit**: task state, resource scheduling, authorization, retries, logs, and provenance.

MVP may remain a modular monolith with separate worker processes; do not turn every logical boundary into a microservice prematurely.

## Storage

- Google Drive: original tutorial videos, organized by platform/creator/series, plus large derived media when needed.
- SQLite: download metadata, hashes, subtitle/pre-filter decisions, trajectory steps, evidence links, conflicts, GPT/PM review decisions, verified knowledge packages, and training-dataset membership.
- Training artifacts: versioned cloud output, base-model revision, adapter weights, run configuration, and benchmark report.
- Git: documentation, schemas, validation rules, and code; never commit source videos, secrets, or model weights.

SQLite is the selected structured store for this pipeline. The previous generic suggestion of PostgreSQL for future multi-user production does not change this project decision.

## Compute strategy and assumptions

- Video understanding candidate selection is currently a blind Colab T4 (16GB) comparison between Qwen3-VL and Mage-VL.
- Cloud GPU is the primary execution environment for LoRA training.
- Planning assumption: 4B BF16 LoRA fits a 16GB T4; 9B needs a 24GB+ GPU. Validate exact revision, sequence length, batch, optimizer, and peak VRAM before treating the estimate as measured.
- The existing RTX 3070 8GB local GPU is useful for development, FFmpeg preprocessing, and lightweight checks, not as the primary 4B BF16 LoRA trainer.

## Existing implementation boundary

The repository has real FFmpeg media operations, ASR/OCR Protocols with static test adapters, a basic video-learning provenance path, SQLite-backed components in the skill/knowledge area, a GUI Agent, and an OpenAI-compatible GUI decision adapter. It does not yet contain the complete cloud-download/pre-filter/model-understanding/action-grounding/review/LoRA-training pipeline. Do not describe interface stubs or supplied-caption integration tests as real model extraction.
