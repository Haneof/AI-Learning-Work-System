# System Architecture

## Product architecture: Brain and Hands

The system's primary product is a set of domain experts: a shared language-model base with different vertical LoRA adapters. Each adapter trains the **Brain** to reason about a business workflow. The **Hands** are an existing GUI operation model that performs live page perception and low-level interaction.

- **Brain:** understands the business goal, current state, rules and constraints; decomposes tasks; chooses methods and branches; delegates high-level capabilities; verifies results; and recovers from errors.
- **Hands:** identifies live page controls and performs concrete UI operations such as click, type, scroll, and navigation. Reuse a ready-made operation model (for example, UI-TARS) through an adapter. Do not build a new page-recognition or low-level action model as the Brain training project.
- **Tutorial event recorder:** supplies the behavior evidence from which the Brain learns.
- **Narration aligner:** provides the instructor's explicit goals, reasons, and constraints on the same timeline as the UI events.

A transcript, summary, or fixed click sequence is not the product. The target is a Brain that can select a suitable workflow path and direct the Hands to accomplish the business objective.

## Four-step data flow

1. **Acquire:** web-search target-vertical tutorials; use a cloud downloader to store them directly in the 5TB Google Drive; group by creator and series/course; retain a source-link/platform record per video.
2. **Capture and align:**
   - for new web tutorials, record semantic rrweb events from session start: DOM mutations, interactions, focus, scrolling, input changes, navigation and timestamps;
   - for new Windows desktop tutorials, record supported Windows UI Automation events, element identities, property/state changes and timestamps;
   - preserve the instructor's voice and align supplied subtitles or ASR fallback to word/segment timestamps;
   - for legacy MP4 files without event telemetry, reconstruct only supportable events from the recording and mark them inferred_from_video.
3. **Build and review workflow knowledge:** align events and narration into Decision Episodes; construct HTN workflows with methods, conditions, hard dependencies, soft preferences, explicit ordering constraints, invariants, transitions and recovery rules; preserve source conflicts and require both review gates.
4. **Train and operate:** train the Brain LoRA from approved conversational decision samples. At runtime, supply the applicable local HTN workflow slice, let the Brain delegate a high-level capability to the existing Hands adapter, receive a structured execution result, and decide the next action.

Frame extraction is not the primary tutorial-learning route. A legacy MP4 reconstruction may use recording inspection as a fallback, but reconstructed interactions remain inferred rather than direct telemetry.

## Runtime Brain-to-Hands loop

1. The user or calling system supplies a business goal and current known state.
2. The Brain loads the relevant local HTN workflow slice and available operation capabilities.
3. The Brain checks preconditions and selects the next business subtask or asks for missing information/approval.
4. For an executable operation, the Brain emits a high-level delegation containing objective, capability ID, arguments, constraints, expected postconditions and observation requirements.
5. The Hands adapter maps the capability to the existing operation model and performs page interaction.
6. Hands returns status, observed state, postcondition results, error category and evidence references.
7. The Brain verifies the result and chooses continue, branch, recover, replan, ask, request approval, finish, or stop.

A successful low-level tool call is not proof that the business task succeeded. The Brain advances only when the relevant postconditions are supported.

## Workflow representation

Use a hierarchical task network (HTN) for compound/primitive task decomposition and a conditional graph for branches and transitions. Distinguish hard dependencies from soft preferences. Explicit ordering constraints and invariants represent non-bypassable requirements. Primitive tasks map to registered capability IDs. Recovery rules describe diagnosis, retry conditions, replan, approval, and safe stop.

Volatile business rules remain in versioned workflow data and are supplied locally at runtime. The LoRA learns how to reason over workflow data; it should not have to memorize every changing business rule in its weights.

## Evidence and provenance

For every decision-driving fact, retain:
- source tutorial/session identity and content hash;
- event ID/type, timestamp, target/element reference, and captured before/after state where available;
- narration segment and word/utterance timestamps;
- observation channel (direct capture or inferred from legacy video);
- rationale source (instructor explicit, behavioral inference, hybrid, not applicable, or unknown);
- confidence and explicit unknowns;
- workflow source, software version, and applicability.

Do not label a reconstructed MP4 interaction as a direct rrweb/Windows UIA event. An instructor quote records what was said, not an automatically verified universal business rule. Preserve conflicting workflows rather than silently normalizing them.

## Layered services

- **Acquisition:** web discovery, platform adapters, cloud download, course grouping, download records, Drive archive.
- **Event capture:** rrweb for web tutorials; Windows UI Automation for Windows desktop tutorials.
- **Narration:** subtitle discovery, ASR fallback, audio alignment, transcript provenance.
- **Decision extraction:** event/narration alignment, Decision Episodes, conditions, reasons, operation choices, results, and next decisions.
- **Workflow service:** HTN tasks/methods, conditional transitions, invariants, capabilities, recovery rules, and versions.
- **Review and knowledge:** source verification, deduplication, conflicts, evidence validation, GPT/PM review, SQLite persistence.
- **Brain training/runtime:** conversational JSONL dataset, LoRA jobs, runtime HTN context, decision generation.
- **Hands adapter:** maps high-level capability delegations to the existing GUI operation model and normalizes return messages.
- **Validation harness:** simulated Hands executor, skill package compiler, static checks, Docker sandbox, and live GUI operation loop.
- **Orchestrator/audit:** task state, resource scheduling, authorization, retries, logs, and provenance.

MVP may remain a modular monolith with separate worker processes; do not turn every logical boundary into a microservice prematurely.

## Storage

- Google Drive: original tutorials organized by platform/creator/series, plus large media assets.
- SQLite: download metadata, semantic UI events, narration segments, Decision Episodes, workflow versions, evidence links, conflicts, reviews, training-dataset membership, and lineage.
- Training artifacts: versioned cloud outputs, base-model revision, adapter weights, run configuration, and benchmark reports.
- Git: documentation, contracts, validation rules, and code; never commit source videos, secrets, or model weights.

## Compute and experiment status

- Initial Brain LoRA planning target: 4B. Planning assumption: 4B BF16 LoRA on T4 16GB; 9B requires 24GB+ GPU. Actual fit and peak VRAM must be measured.
- Existing local RTX 3070 8GB supports development and lightweight processing; it is not assumed to be the primary 4B BF16 trainer.
- The previous Qwen3-VL-4B vs Mage-VL-4B Colab T4 blind test was stopped on 2026-11-21 at approximately 19:51 PST after Qwen3-VL-4B scored 4.0/25. It was not a completed winner-selection benchmark. The frame-based route was rejected as the primary learning method; the current input design is semantic UI events plus instructor narration.

## Existing implementation boundary

The repository has real FFmpeg media operations, ASR/OCR Protocols with static test adapters, a basic video-learning provenance path, SQLite-backed knowledge/skill components, a GUI Agent, and an OpenAI-compatible GUI decision adapter. It does not yet contain the complete event-capture/narration-alignment/Decision Episode/HTN/Brain LoRA/Brain-to-Hands pipeline. Do not describe interface stubs or supplied-caption integration tests as completed direct event capture or Brain workflow learning.
