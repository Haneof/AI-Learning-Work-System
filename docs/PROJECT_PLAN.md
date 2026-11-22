# Product Charter and Project Plan

**Version:** 0.1 design update

## Product definition

Build a general-purpose AI learning and work system that turns professional tutorials into evidence-grounded workflow knowledge and trains domain-specific language-model experts with LoRA.

The core product is a trained **Brain**: a language model that understands a business objective, decomposes the work, selects a path under current conditions, explains its decision, delegates operations, verifies results, and recovers from errors. Existing GUI operation models are the **Hands**. They perceive the live page and perform concrete UI interactions; this project reuses them rather than building a replacement.

The product is not a subtitle archive, video summary, knowledge package, or fixed action script. The same base model can host different vertical LoRA adapters, with each expert supported by versioned workflow data and evidence.

## Target learning pipeline

### Step 1 — Acquire and archive

Search for tutorials in the target vertical and use a cloud downloader to store them directly in the 5TB Google Drive. Preserve creator and series/course grouping. Every video keeps an acquisition record with the original source link and platform, plus content hash, Drive location, source metadata, and license status when available.

### Step 2 — Process downloaded tutorial video files

The selected learning input is a downloaded video file processed offline by local programs. Prefer usable SRT/WebVTT subtitles; when absent, use local ASR and keep segment/word timestamps. FFmpeg decodes timestamped sampled stills, a pixel-difference detector selects screen-change frames, and Tesseract reads visible UI text. OpenCV cursor tracking and local GUI-grounding models produce possible action/target hypotheses on selected changed frames.

The pipeline does not play the tutorial in real time and does not require a live recorder. Cursor/click and target hypotheses must be labelled `inferred_from_video`; a video file contains no native rrweb, Windows UIA, mouse, keyboard, or DOM event telemetry. Align the timestamped narration with visible screen changes and keep instructor-explicit claims separate from behavioral inference.

### Step 3 — Build, validate, and verify workflow knowledge

Create DecisionEpisodes rather than plain step lists. Each episode records:
- the task goal and known state at the decision point;
- timestamped visual observations, OCR, and source video references;
- instructor-explicit narration and separately labelled behavioral inference;
- inferred operation hypotheses and explicit unknowns;
- the selected strategy, constraints, and applicable workflow;
- any independently supported result and next decision.

PR #38 builds the DecisionEpisode and validates it against the schema and semantic contract. PR #39 adds the local open-weight verifier, which separately checks extraction fidelity, decision validity, and outcome validity. All three must pass. Local PASS is not dataset approval: a separate evidence-linked PM review is required. A video-only time sequence is not proof of execution or causal business outcome.

Compose approved episodes into HTN workflows with compound/primitive tasks, methods, hard dependencies, soft preferences, explicit ordering constraints, conditional transitions, invariants, and recovery rules. Deduplicate by content hash and retain conflicts from different tutorials, software versions, or applicability conditions.

### Step 4 — Compile training samples (PR #40)

The compiler creates conversational Brain samples from DecisionEpisodes that pass local verification, independent PM verification, review approval, and quality/trainable checks. Each decision point is a separate sample. Keep evidence_tier and rationale_loss_weight in a separate metadata sidecar, use source/course-grouped train/test splits, and exclude future Hands outcomes from earlier decision targets.

### Step 5 — Prepare the Brain LoRA (PR #41)

The repository now contains metadata-aware dataset preparation and a T4 Axolotl configuration for `DreamFast/qwen3-4b-heretic`. The setup uses the original Transformers checkpoint in FP16 (not a GGUF or quantized model) with the documented LoRA profile. This is configuration and preparation support only: no real approved samples or real training run were available when PR #41 was merged, so no trained adapter is claimed.

### Step 6 — Brain-to-Hands closed-loop harness (PR #42)

The Brain protocol delegates business-level capabilities; Hands returns correlated execution results and evidence. The loop obtains fresh observations, independently verifies postconditions, and re-enters Brain for continuation or recovery. CI acceptance uses a deterministic WorkflowBrain stand-in with SimulatedHands. A BrowserAgentHandsAdapter bridge is provided, but the PR did not run a real Brain LoRA or real UI-TARS-class Hands model.

## Architecture and model status

- **Brain:** language model plus vertical LoRA; the primary training target.
- **Hands:** existing GUI operation model and adapter (for example, UI-TARS); reuse as the execution layer.
- **Tutorial learning input:** downloaded video files processed offline with subtitles/ASR, FFmpeg frame sampling, screen-change detection, OCR, cursor inference, and local UI grounding.
- **Evidence model:** `observed_from_video`, `inferred_from_video`, `instructor_words`, and unknowns remain distinct. Inferred cursor/click candidates are not direct telemetry.
- **Workflow representation:** HTN plus conditional-branch graph and registered operation capabilities.
- **Training:** compiler-generated conversational JSONL with separate training-metadata sidecars; no future execution-outcome leakage in assistant targets.
- **Runtime:** business-level Brain delegation to Hands with fresh-state and postcondition verification.

**Superseded design decision — 2026-11-21:** the proposed live rrweb/Windows UIA recorder/event-collector route was cancelled. It was superseded by video-file extraction because the selected process can work from downloaded tutorials without installing and synchronizing a recorder inside each live application/session. Keep that route as historical context only; it is neither primary nor a required fallback.

The earlier Qwen3-VL-4B/Mage-VL-4B Colab T4 comparison was stopped on 2026-11-21 at approximately 19:51 PST after Qwen3-VL-4B scored 4.0/25. No winner was selected. That incomplete model comparison did not reject frame extraction; frame-change-driven video-file extraction is the current route.

## Compute and storage assumptions

- Initial Brain base model: 4B.
- Planning assumption: 4B BF16 LoRA on T4 16GB; 9B needs a 24GB+ GPU. Confirm actual fit and performance with a fixed model revision and recorded run configuration.
- Local RTX 3070 8GB: development and light validation, not assumed as the BF16 LoRA training device.
- Google Drive: original tutorial archive.
- SQLite: source/event metadata, narration alignment, Decision Episodes, workflow versions, reviews, dataset snapshots, and training lineage.

## Project objectives

- Acquire downloadable tutorial video files with source, license, and course provenance.
- Extract timestamped transcript and frame-change-driven visual evidence locally.
- Create contract-valid DecisionEpisodes with explicit observed/inferred labels.
- Apply the local verifier and independent PM review before training admission.
- Compile approved decision points into source-grouped Brain samples.
- Execute the configured Brain LoRA training run once an eligible corpus and compute are available.
- Integrate a trained Brain with existing Hands and verify business postconditions, recovery, safe stop, and unseen-task transfer.
- Preserve provenance, conflicts, software versions, and review decisions.

## Non-goals

- Rebuilding a GUI page-recognition or low-level operation model.
- Requiring a live rrweb/Windows UIA tutorial recorder or real-time video playback.
- Treating an uncontextualized sparse/dense frame dump as a complete action log or teaching target.
- Treating ASR, OCR, video summaries, or click replay as learned workflow competence.
- Training a universal foundation model from scratch.
- Training on evidence that has not passed both review gates.
- Optimizing throughput before decision quality is measured.

## Core assets and metrics

The core assets are vertical Brain LoRA experts, their reviewed Decision Episode datasets, versioned HTN workflows, and measured Brain-to-Hands task results.

Quality metrics include decision correctness, task decomposition, dependency/order correctness, branch accuracy, rationale provenance, precondition/postcondition verification, capability selection, recovery/stop quality, held-out goal completion, evidence coverage, and safety. Operational metrics include training cost, runtime delegation reliability, time/cost per verified training example, queue throughput, and recovery from infrastructure failure.

Quality gates are frozen before held-out evaluation. A high completion rate on memorized tutorial paths is not evidence of generalization.
