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

1. **Acquire and archive tutorial video files.** Discover tutorials, download the actual video files, and preserve them in the archive with source URL, platform, creator/course metadata, hash, and license information. The learning input is the downloaded file, not an actively recorded browser/desktop session.

2. **Extract evidence from the downloaded video file (primary route).** Programs process the file offline; the system does not play the tutorial in real time or depend on a live recorder. Prefer an existing SRT/WebVTT subtitle track. When usable subtitles are absent, run local ASR and retain segment/word timestamps. FFmpeg decodes sampled stills; a pixel-difference detector selects screen-change frames. OCR reads visible text; cursor/click candidates and UI targets are inferred from the video and are labelled `inferred_from_video`, never as native click telemetry. Local GUI-grounding models are run on selected changed frames, not on every unchanged frame. Align the timestamped narration to those visual events.

3. **Build and validate DecisionEpisodes.** Combine the task goal, decision-time visual state, timestamped narration, visible screen changes, inferred operation hypotheses, uncertainty, and evidence references. Produce a structured DecisionEpisode and validate it against the versioned contract. A video cannot prove hidden clicks, actual operation execution, or a business postcondition that is not visible and independently supported.

4. **Apply the local verifier gate, then the independent PM gate.** The local open-weight verifier separately scores extraction fidelity, decision validity, and outcome validity; every level must pass. A video-only sequence is not causal proof of a successful operation. Local PASS is not training approval: the episode remains held until the PM independently reviews the source and proposed episode and supplies the required evidence-linked PASS.

5. **Compile approved episodes into Brain training samples.** The #40 compiler accepts only episodes that pass local verification, PM verification, annotation/review approval, and quality/trainable checks. It emits decision-point conversational samples, source-grouped train/test splits, and separate metadata sidecars. Held, rejected, or incomplete items fail closed.

6. **Prepare and train the Brain LoRA.** PR #41 adds the Qwen3 4B Brain LoRA training configuration and metadata-aware dataset preparation/validation. It is a training setup, not evidence that an adapter has already been trained. Training still requires a non-empty eligible dataset and an actual recorded training run.

7. **Run the Brain-to-Hands loop.** PR #42 adds the business-level delegation/result contract and the observe → decide → delegate → execute → independently verify → replan/recover loop. The current CI acceptance uses a deterministic WorkflowBrain stand-in with SimulatedHands; BrowserAgentHandsAdapter reuses existing GUI execution infrastructure. This does not claim that a trained Brain LoRA or a real UI-TARS-class Hands model has been run.

**Superseded design decision — 2026-11-21:** The previously proposed live-recorder/event-collector route (rrweb for web sessions and Windows UI Automation event capture for desktop sessions) was cancelled and superseded by downloaded-video-file extraction. The reason for the change is architectural: the selected pipeline works from tutorial files already available for download and does not require instrumentation to be installed in, or synchronized with, each live tutorial session. Keep the old event-stream proposal as project history only; it is not the active primary route or a required fallback.

The distinction matters: frame extraction is part of the selected route, but frame-change-driven extraction is paired with transcript/narration, OCR, cursor inference, local UI grounding, evidence labels, and verification. The cancelled live recorder is not being replaced by a claim that sparse screenshots alone teach the workflow.

## Evidence and learning principles

1. **Quality first, efficiency second.** A decision unsupported by timestamped video observations, narration, or explicitly labelled inference must not become a training fact.
2. **Teach why and when.** Align the instructor's words with the demonstrated screen changes; keep explicit explanation separate from behavioral inference.
3. **Separate evidence channels.** Keep visible observations decoded from the video (`observed_from_video`), inferred cursor/click/target hypotheses (`inferred_from_video`), timestamped instructor words, reviewer conclusions, and unknown information distinct. A downloaded video does not contain native DOM/UIA/click telemetry.
4. **Verify outcomes.** A visually plausible next screen or inferred click is not by itself proof that an operation executed or that a business postcondition passed.
5. **Preserve conflicts.** Keep competing workflows with their sources, software versions, and applicability conditions. They do not overwrite one another.
6. **Generalize, do not replay.** Test different starting states, alternative valid paths, missing information, failures, and recovery. The Brain must adapt rather than repeat a tutorial verbatim.
7. **Reuse the Hands.** Do not spend the learning project rebuilding page perception or button-clicking capabilities already provided by an operation model.

## Model and experiment status

The earlier Colab T4 blind comparison of Qwen3-VL-4B and Mage-VL-4B was **stopped on 2026-11-21 at approximately 19:51 PST**, after Qwen3-VL-4B scored **4.0/25**. The comparison was not completed as a valid winner-selection benchmark; no model winner is claimed. That experiment does not mean frame extraction was rejected: frame-change-driven extraction from downloaded video files is now the selected learning route.

The Brain language model remains the primary training target; the existing Hands operation model remains a separate execution component. The selected extraction pipeline uses existing subtitles first and local ASR as fallback, with FFmpeg frame sampling, screen-change detection, OCR, cursor/possible-click inference, and local UI-target grounding.

## Compute and storage planning assumptions

- Initial Brain base-model target: 4B, with one LoRA adapter per vertical expert.
- T4 planning profile: 4B LoRA uses FP16 compute (BF16 is disabled for the T4 profile); 9B LoRA planning requires 24GB or more. Actual fit and performance must be measured with a fixed model revision, sequence length, batch size, optimizer, and checkpointing configuration.
- Existing local GPU: RTX 3070 8GB; useful for development, event/data processing, and lightweight validation, not assumed to be the primary BF16 LoRA trainer.
- Tutorial archive target: 5TB Google Drive.
- SQLite stores structured source, event, narration, workflow, review, and training lineage metadata.

## Current implementation boundary

The repository now contains the implemented milestones in this sequence:

- **PR #38 — video-file extraction:** download a tutorial video file, process subtitles/ASR and frame changes, build a structured DecisionEpisode, and run contract validation.
- **PR #39 — local verifier gate:** verify extraction fidelity, decision validity, and outcome validity with a local open-weight model; a separate PM PASS is still required for dataset admission.
- **PR #40 — training-sample compiler:** compile dual-approved, quality-approved DecisionEpisodes into decision-time Brain samples with source-grouped splits and separate sidecars.
- **PR #41 — LoRA training setup:** prepare metadata-aware datasets and validate the Brain LoRA configuration; no trained adapter is implied.
- **PR #42 — Brain+Hands closed loop:** add typed delegation/results, a deterministic WorkflowBrain test stand-in, SimulatedHands, independent postcondition checks, and a BrowserAgent adapter path.

These milestones are real code, but they are not yet a single production-trained system. The Brain used by the current closed-loop CI acceptance is a deterministic workflow stub, not a trained LoRA. No real Brain adapter or real UI-TARS-class Hands operation model has been run, and the extractor/compiler/training/runtime pieces are not represented as a fully deployed end-to-end service. Consult [Downloaded Video-File Extraction Pipeline](docs/VIDEO_FILE_EXTRACTION_PIPELINE.md), [Training-Sample Compiler](docs/TRAINING_SAMPLE_COMPILER.md), and [Brain/Hands Closed Loop](docs/BRAIN_HANDS_CLOSED_LOOP.md) for exact boundaries.

## Project documentation

| Document | Purpose |
|---|---|
| [Project plan](docs/PROJECT_PLAN.md) | Product definition, brain/hands split, and learning pipeline |
| [System architecture](docs/ARCHITECTURE.md) | Layers, data flow, workflow learning, and runtime delegation |
| [Technology stack](docs/TECH_STACK.md) | Video-file extraction, local models, Brain LoRA, and Hands reuse |
| [Roadmap](docs/ROADMAP.md) | Stages, deliverables, and exit criteria |
| [Acquisition pipeline](docs/ACQUISITION_PIPELINE.md) | Tutorial archive, video-file extraction, narration, review, and training |
| [Downloaded video-file extraction](docs/VIDEO_FILE_EXTRACTION_PIPELINE.md) | Executable extraction, local verification, evidence artifacts, and downstream gates |
| [Media ingestion](docs/MEDIA_INGEST.md) | Downloaded video-file extraction and evidence generation |
| [Knowledge and evidence](docs/KNOWLEDGE_EVIDENCE.md) | Provenance, observation channels, rationale sources, and uncertainty |
| [Core data model](docs/DATA_MODEL.md) | Video sources, extracted evidence, narration, DecisionEpisodes, workflows, and experts |
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

**Current implemented path:** downloaded tutorial file → subtitle/ASR + frame-change-driven extraction → DecisionEpisode + contract validation (#38) → local verifier gate (#39) → PM evidence review → training-sample compiler (#40) → Brain LoRA training setup (#41) → Brain+Hands closed-loop harness (#42).

The PR milestones establish code and test harnesses, not a completed trained expert. A real approved dataset and training run are still required to produce a real Brain LoRA; the #42 CI path uses a deterministic Brain stand-in and simulated Hands. The historical rrweb/Windows UIA live-recorder route was cancelled on 2026-11-21 and remains documented only as a superseded alternative.

All work requires explicit scope, evidence, interfaces, quality gates, and reproducible tests. Do not merge pull requests without authorization. Do not describe unimplemented or unvalidated capabilities as complete.

