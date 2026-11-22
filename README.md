# AI Learning & Work System

**A general-purpose AI learning and work system:** turn professional tutorials and verified operational evidence into training data for domain experts, then use LoRA to teach a language model how to plan and direct work.

> The product is not a subtitle archive, video summary, button detector, or fixed click script. The product is a domain expert that understands a business goal, chooses an appropriate workflow, handles conditions and exceptions, and directs an existing operation model to execute page interactions.

## Product objective: train the brain, reuse the hands

The system has two deliberately separate roles:

| Role | Responsibility | Project scope |
|---|---|---|
| **Brain — language model + domain LoRA** | Understand business goals, plan workflow steps, check preconditions, choose branches, explain decisions, delegate capabilities, verify outcomes, recover from failures | This is the primary learning and training target |
| **Hands — existing GUI operation model** | Perceive the live page, find controls, click, type, scroll, and perform low-level UI interaction | Reuse an available open-source operation model, such as UI-TARS, through an adapter; do not build a replacement UI perception/action model |

The Brain decides **what should happen next and why**. The Hands execute the delegated task and return structured observations. The Brain checks the result and chooses the next step.

The system must teach the Brain a transferable workflow policy, not make it replay one instructor's mouse path.

## Learning pipeline

1. **Acquire and archive tutorials.** Search for tutorials in the target vertical. Use a cloud downloader to store them directly in the 5TB Google Drive, grouped by creator and series/course. Keep a per-video record containing at least the original source link and platform, plus available creator, course, hash, and license metadata.

2. **Capture or recover the operation event stream, and align narration.**
   - For newly recorded tutorials, capture semantic UI events directly during recording. For web applications, use an event recorder such as rrweb to record DOM changes, interactions, focus, scrolling, input changes, and timestamps. For Windows desktop applications, use Windows UI Automation events and element state information. Synchronize the event stream with the instructor's audio.
   - Prefer existing subtitles. If usable subtitles are absent, run ASR and obtain word-level or segment-level timestamps through alignment. The narration provides the instructor's goals, reasons, constraints, and explanations.
   - For legacy MP4 tutorials that have no event log, reconstruct only the events that can be supported by the recording. These records must be labelled as inferred from video; they must never be represented as directly captured DOM, Accessibility, mouse, or keyboard events.
   - Frame-based extraction is **not** the primary learning route. Do not feed sparse or dense frame collections to a video model as the main way to teach operational workflows.

3. **Build decision episodes and workflow knowledge.** Align the event stream with the narration. Extract decision episodes containing the goal at the time, known business state, instructor's explicit explanation, inferred rationale where appropriate, chosen operation, observed result, and next decision. Preserve source evidence and confidence. Compose these episodes into hierarchical task networks (HTN) with conditional branches, hard dependencies, soft preferences, preconditions, postconditions, and recovery paths. Conflicts from different tutorials, software versions, or conditions coexist; they do not overwrite one another.

4. **Train and validate the Brain.** Turn approved decision episodes into conversational supervised-training examples. The Brain learns task decomposition, sequence and branch selection, business constraints, capability choice, state verification, and error recovery. At runtime, provide the relevant local HTN workflow slice in the prompt so volatile business rules can be updated without retraining the LoRA. The Brain sends a high-level delegation JSON to the Hands adapter; Hands returns an execution-result JSON; the Brain verifies the postconditions and chooses what happens next.

Only approved, source-grounded training examples should enter a LoRA dataset. A fluent transcript, UI event dump, or click replay is not by itself a successful learning result.

## Evidence and learning principles

1. **Quality first, efficiency second.** A decision that cannot be supported by the event stream, narration, or clearly labelled inference must not become a training fact.
2. **Teach why and when.** The instructor's words and demonstrated behavior must be aligned so the Brain can learn goals, reasons, preconditions, conditions, and alternative paths.
3. **Separate evidence channels.** Directly captured UI events, reconstructed legacy-video events, instructor-explicit rationale, behavioral inference, project-owner-provided rules, and unknown information remain distinguishable.
4. **Verify outcomes.** A successful click or tool call is not proof of a successful business result. Record postcondition checks and their evidence.
5. **Preserve conflicts.** Keep competing workflows with their sources, application/software versions, and applicability conditions. Never silently overwrite a conflicting rule.
6. **Generalize, do not replay.** Test different starting states, alternative valid paths, missing information, failures, and recovery. The Brain must adapt its plan rather than repeat a tutorial verbatim.
7. **Reuse the Hands.** Do not spend the learning project rebuilding page perception or button-clicking capabilities already provided by an operation model.

## Model and experiment status

The earlier Colab T4 blind comparison of Qwen3-VL-4B and Mage-VL-4B was **stopped on 2026-11-21 at approximately 19:51 PST**, after Qwen3-VL-4B scored **4.0/25**. The comparison was not completed as a valid winner-selection benchmark. No winner is claimed, and the frame-based video-understanding route was rejected as the primary way to learn UI workflows.

The primary training target is now the Brain language model. The existing Hands operation model remains a separate execution component. ASR and word/segment alignment support the narration channel; rrweb and Windows UI Automation provide direct event capture for new tutorials.

## Compute and storage planning assumptions

- Initial Brain base-model target: 4B, with one LoRA adapter per vertical expert.
- Planning assumption: a 16GB T4 may accommodate 4B BF16 LoRA; 9B LoRA planning requires 24GB or more. These are capacity assumptions until measured with a fixed model revision, sequence length, batch size, optimizer, and checkpointing configuration.
- Existing local GPU: RTX 3070 8GB; useful for development, event/data processing, and lightweight validation, not assumed to be the primary BF16 LoRA trainer.
- Tutorial archive target: 5TB Google Drive.
- SQLite stores structured source, event, narration, workflow, review, and training lineage metadata.

## Current implementation boundary

The repository contains acquisition/storage components, FFmpeg media utilities, ASR/OCR interfaces and static fixtures, knowledge/evidence components, a skill compiler, a sandbox, and a GUI Agent with a model adapter. These components do not yet constitute the complete event-stream capture, narration alignment, decision-episode extraction, Brain LoRA training, or Brain-to-Hands production loop. The static ASR/OCR adapters are test fixtures, not real model inference. The GUI operation adapter is downstream Hands infrastructure, not the Brain's workflow-learning system.

## Project documentation

| Document | Purpose |
|---|---|
| [Project plan](docs/PROJECT_PLAN.md) | Product definition, brain/hands split, and learning pipeline |
| [System architecture](docs/ARCHITECTURE.md) | Layers, data flow, workflow learning, and runtime delegation |
| [Technology stack](docs/TECH_STACK.md) | Event capture, narration alignment, Brain LoRA, and Hands reuse |
| [Roadmap](docs/ROADMAP.md) | Stages, deliverables, and exit criteria |
| [Acquisition pipeline](docs/ACQUISITION_PIPELINE.md) | Tutorial archive, event stream, narration, review, and training |
| [Media ingestion](docs/MEDIA_INGEST.md) | Existing media utilities and target event-based ingestion |
| [Knowledge and evidence](docs/KNOWLEDGE_EVIDENCE.md) | Provenance, observation channels, rationale sources, and uncertainty |
| [Core data model](docs/DATA_MODEL.md) | Sources, UI events, narration, decision episodes, workflows, and experts |
| [Acceptance criteria](docs/ACCEPTANCE.md) | Evidence quality and Brain/Hands validation |
| [Model benchmark harness](docs/MODEL_BENCHMARK.md) | Existing benchmark interface and its limits |
| [Phase 0 technical validation](docs/PHASE_0_TECHNICAL_VALIDATION.md) | First end-to-end Brain learning validation |
| [Skill compilation](docs/SKILL_COMPILATION.md) | Structure/evidence validation and test-material compilation |
| [Skill security PoC](docs/SKILL_SECURITY.md) | Static checks and sandbox isolation |
| [Test plan](docs/TEST_PLAN.md) | Workflow decisions, recovery, transfer, and safe execution |

## Local development

Requires Python 3.11 or 3.12. Read the [development guide](DEVELOPMENT.md) before running the project.

~~~powershell
py -3.11 -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
ruff check .
pytest
python -m aios_work_system serve --host 127.0.0.1 --port 8000
~~~

## Current project status

**Current focus: define and validate the event-stream-to-decision-episode path and the Brain-to-Hands contract.** The prior Qwen3-VL-4B/Mage-VL-4B blind test was stopped as noted above. Direct event capture for new tutorials, legacy-video reconstruction, narration alignment, Brain LoRA training, and the full Brain-to-Hands loop are not yet claimed as implemented end-to-end.

All work requires explicit scope, evidence, interfaces, quality gates, and reproducible tests. Do not merge pull requests without authorization. Do not describe unimplemented or unvalidated capabilities as complete.
