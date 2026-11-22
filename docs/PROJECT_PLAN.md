# Product Charter and Project Plan

**Version:** 0.1 design update

## Product definition

Build a general-purpose AI learning and work system that turns professional tutorials into evidence-grounded workflow knowledge and trains domain-specific language-model experts with LoRA.

The core product is a trained **Brain**: a language model that understands a business objective, decomposes the work, selects a path under current conditions, explains its decision, delegates operations, verifies results, and recovers from errors. Existing GUI operation models are the **Hands**. They perceive the live page and perform concrete UI interactions; this project reuses them rather than building a replacement.

The product is not a subtitle archive, video summary, knowledge package, or fixed action script. The same base model can host different vertical LoRA adapters, with each expert supported by versioned workflow data and evidence.

## Target learning pipeline

### Step 1 — Acquire and archive

Search for tutorials in the target vertical and use a cloud downloader to store them directly in the 5TB Google Drive. Preserve creator and series/course grouping. Every video keeps an acquisition record with the original source link and platform, plus content hash, Drive location, source metadata, and license status when available.

### Step 2 — Capture semantic operation events and narration

For newly recorded tutorials, collect the semantic UI event stream at recording time:
- Web applications: rrweb events for DOM mutations, interaction events, focus, scroll, input changes, and timestamps.
- Windows desktop applications: Windows UI Automation events, element identities, property/state changes, and timestamps.
- Voice: original instructor audio plus subtitles where available; when subtitles are unavailable, use ASR and time alignment.

The event stream describes what changed and when. The instructor's narration describes the goal, reason, constraint, and business context. Neither channel is sufficient alone; they must be aligned to produce decision demonstrations.

Legacy MP4 tutorials may be used when no event telemetry exists. Reconstruct events only when supported by the recording and label them as inferred from video. Frame extraction is not the primary extraction or training route.

### Step 3 — Build and review workflow knowledge

Create Decision Episodes rather than plain step lists. Each episode records:
- the task goal and known state at the decision point;
- conditions and business constraints;
- instructor-explicit rationale and separately labelled behavioral inference;
- the selected strategy and delegated capability;
- operation result and verified postconditions;
- the next step, branch, recovery, question, approval request, or stop decision;
- source references, timestamps, evidence channel, and confidence.

Compose episodes into HTN workflows with compound/primitive tasks, methods, hard dependencies, soft preferences, explicit ordering constraints, conditional transitions, invariants, and recovery rules.

Deduplicate by content hash. Conflicting workflows from different tutorials, software versions, or applicability conditions coexist and retain their sources. Only examples passing both the review approval gate and the quality/trainable gate enter the formal Brain training set.

### Step 4 — Train the Brain and validate Brain-to-Hands

Generate conversational training samples for the Brain. The LoRA learns task decomposition, sequencing, branch decisions, business constraints, capability selection, postcondition checks, error interpretation, recovery, and safe stopping.

Keep volatile rules in versioned workflow data. At runtime, give the Brain the relevant local HTN slice so workflow rules can change without retraining the LoRA. The Brain emits a high-level delegation request; the existing Hands model performs page operations and returns observed results; the Brain then chooses the next decision.

Validate first with a simulated Hands executor, then with the real existing operation model in a sandbox and GUI loop. Passing requires success on changed states and unseen variations—not replay of one tutorial.

## Architecture and model status

- **Brain:** language model plus vertical LoRA; the primary training target.
- **Hands:** existing GUI operation model and adapter (for example, UI-TARS); reuse as the execution layer.
- **Event capture:** rrweb for web tutorials; Windows UI Automation for Windows desktop tutorials.
- **Narration:** supplied subtitles first; ASR fallback and timestamp alignment when needed.
- **Workflow representation:** HTN plus conditional-branch graph and registered operation capabilities.
- **Training:** conversational JSONL with a separate training-metadata sidecar; no future execution-outcome leakage in assistant targets.

The earlier Qwen3-VL-4B/Mage-VL-4B Colab T4 blind test was stopped on 2026-11-21 at approximately 19:51 PST after Qwen3-VL-4B scored 4.0/25. No winner was selected. The frame-based extraction route was rejected as the primary learning method; event streams plus instructor narration are the current input design.

## Compute and storage assumptions

- Initial Brain base model: 4B.
- Planning assumption: 4B BF16 LoRA on T4 16GB; 9B needs a 24GB+ GPU. Confirm actual fit and performance with a fixed model revision and recorded run configuration.
- Local RTX 3070 8GB: development and light validation, not assumed as the BF16 LoRA training device.
- Google Drive: original tutorial archive.
- SQLite: source/event metadata, narration alignment, Decision Episodes, workflow versions, reviews, dataset snapshots, and training lineage.

## Project objectives

- Build repeatable direct event capture for new tutorials.
- Align semantic UI event streams with instructor narration.
- Create source-grounded Decision Episodes and conditional HTN workflows.
- Train a Brain LoRA that can adapt to different states and valid workflow paths.
- Integrate with existing Hands through a clear delegation/result interface.
- Verify business postconditions, failure recovery, safe stop, and unseen-task transfer.
- Preserve provenance, conflicts, software versions, and review decisions.

## Non-goals

- Rebuilding a GUI page-recognition or low-level operation model.
- Using sparse or dense frame extraction as the primary tutorial learning input.
- Treating ASR, OCR, video summaries, or click replay as learned workflow competence.
- Training a universal foundation model from scratch.
- Training on evidence that has not passed both review gates.
- Optimizing throughput before decision quality is measured.

## Core assets and metrics

The core assets are vertical Brain LoRA experts, their reviewed Decision Episode datasets, versioned HTN workflows, and measured Brain-to-Hands task results.

Quality metrics include decision correctness, task decomposition, dependency/order correctness, branch accuracy, rationale provenance, precondition/postcondition verification, capability selection, recovery/stop quality, held-out goal completion, evidence coverage, and safety. Operational metrics include training cost, runtime delegation reliability, time/cost per verified training example, queue throughput, and recovery from infrastructure failure.

Quality gates are frozen before held-out evaluation. A high completion rate on memorized tutorial paths is not evidence of generalization.
