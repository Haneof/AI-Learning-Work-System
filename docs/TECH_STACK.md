# Technology Stack and Validation Strategy

**Version:** 0.1 design update  
**Policy:** reuse existing operation models; focus new learning effort on Brain workflow competence. Quality first, efficiency second. This document describes the target design, not a claim that every adapter is already integrated.

## 1. System roles

| Layer | Candidate/tooling | Responsibility | Project status |
|---|---|---|---|
| Brain base model | A selected 4B language model | Business reasoning, task decomposition, conditional planning, capability delegation, verification, recovery | Primary LoRA training target; exact base revision is selected through separate model validation |
| Brain vertical adapter | LoRA | Learn reusable workflow decision behavior for a domain | Target training output |
| Web event capture | rrweb | Directly capture timestamped DOM changes, interactions, focus, scrolling, and input changes while recording a new tutorial | Target capture integration |
| Windows desktop event capture | Windows UI Automation | Capture control identities, property/state changes, focus and UIA events with timestamps | Target capture integration |
| Narration processing | Existing subtitles first; ASR fallback and timestamp alignment | Preserve instructor words, reasons, constraints, and timing | Real ASR/alignment integration and language validation required |
| Workflow representation | HTN plus conditional graph | Store task hierarchy, methods, preconditions, hard dependencies, soft preferences, postconditions, and recovery rules | Target data contract |
| Hands operation layer | Existing open-source GUI operation model, e.g. UI-TARS | Live page recognition and low-level execution | Reuse; do not rebuild as part of the Brain learning project |
| Hands adapter | Project-owned capability adapter | Translate Brain capability delegation into the existing Hands model's request format and normalize its execution result | Interface/integration work |
| Validation | Simulated Hands executor, Docker sandbox, live GUI loop | Isolate Brain decisions, then validate the complete Brain + Hands pair | Target evaluation harness |

The Brain is not trained to find buttons. It is trained to decide which business task should be done, why, under which conditions, and how to react to the Hands result.

## 2. Tutorial input and narration alignment

### New recordings — primary path

- Web tutorials: record semantic event streams with rrweb from the start of the session. Retain event type, stable target/node references where available, event timestamp, relevant DOM mutation, focus/scroll/input changes, and page/session identity.
- Windows desktop tutorials: subscribe to supported Windows UI Automation events and preserve element identity, control type/name, property changes, focus, structure changes, and timestamps. Record provider limitations; not every app exposes every event.
- Voice: preserve original audio. Extract supplied subtitles first. When unavailable, run ASR and align words or utterance segments to the audio. Preserve language, time range, ASR/alignment method, and uncertainty.
- Clock alignment: record enough session timing metadata to place UI events and narration segments on one timeline. Do not guess alignment when clocks cannot be reconciled.

### Legacy MP4 — fallback path only

A prerecorded MP4 normally has no original DOM, UI Automation, mouse, or keyboard event log. Where needed, reconstruct a limited event stream from the recording and narration. Mark all reconstructed UI actions as inferred_from_video; hidden clicks, key presses, or unobservable state changes remain unknown. This is a legacy-data compatibility path, not the default learning method.

Sparse and dense frame extraction were rejected as the primary route. FFmpeg may still be used for file probing and audio extraction; it is not a substitute for direct semantic event capture.

## 3. Decision Episode and Workflow data

The smallest learning unit is a Decision Episode, not a plain UI step list. It joins:
- business goal and success criteria at the time;
- current state and relevant facts;
- instructor-explicit narration and behavioral inference as separate sources;
- selected strategy, conditions, and alternatives;
- delegated operation capability and arguments;
- returned operation status and verified postconditions;
- next decision, recovery, question, approval request, or stop;
- evidence references, timestamps, observation channel, rationale source, and confidence.

Workflow data uses HTN tasks and methods plus a conditional graph:
- compound and primitive tasks;
- applicable conditions and method selection;
- hard_dependency and soft_preference edges;
- explicit ordering constraints and invariants;
- capability registry mappings;
- postconditions, transitions, and recovery rules;
- source/tutorial, software version, and applicability scope.

Conflicting source workflows must coexist rather than overwrite one another.

## 4. Brain LoRA training data

- Conversational JSONL uses system/user/assistant messages, compatible with the data adapters used by TRL, Axolotl, and LLaMA-Factory after their chat-template mapping is configured.
- Normal-decision examples train selection of the next decision from goal, state, local workflow slice, and available capabilities.
- Error-recovery examples put the previous Hands return in the user input as last_execution_result; the assistant target predicts the Brain's next action.
- Training targets stop before the future execution outcome. Do not leak the Hands response that follows the action being predicted.
- Keep evidence_tier and rationale_loss_weight in a separate training_meta sidecar; never feed these fields to the model.
- Split train/test by tutorial/course/source group to prevent near-duplicate fragments from crossing partitions.

## 5. Historical Qwen/Mage experiment status

The Qwen3-VL-4B vs Mage-VL-4B blind test on Colab T4 was stopped on 2026-11-21 at approximately 19:51 PST after Qwen3-VL-4B scored 4.0/25. This was not a completed winner-selection benchmark. No winner is declared, and neither video model is the primary event-stream workflow extractor in the current architecture.

## 6. Training resources

- First Brain LoRA base: 4B.
- Planning assumption: T4 16GB for 4B BF16 LoRA; 24GB+ for 9B LoRA.
- Local RTX 3070 8GB: development, event processing, and lightweight validation; not the default 4B BF16 training environment.
- For every run, record base revision, dataset snapshot hash, context length, batch, gradient accumulation, optimizer, precision, checkpointing, GPU model/VRAM, peak memory, wall time, and adapter hash.
- Planning estimates must not be reported as measured capacity.

## 7. Existing components: retain but do not overstate

| Component | Keep for | Do not claim it does |
|---|---|---|
| FFmpeg | Probe media and extract audio where necessary | Capture DOM/UIA events or infer business workflow |
| ASR/OCR protocols | Adapter boundaries and selected legacy compatibility | Provide real inference when only static fixtures are installed |
| StaticASRAdapter/StaticOCRAdapter | Deterministic tests | Transcribe or read real tutorial content |
| GUI Agent and operation adapter | Hands execution and live expert validation | Train the Brain's workflow decision policy |
| Skill package compiler | Compile/validate supporting knowledge and test material | Replace HTN workflow decision training |
| Docker sandbox | Isolate execution and validate behavior | Prove business competence without workflow tests |
| SQLite | Structured event, episode, workflow, review, and training lineage metadata | Store bulk source video objects |

## 8. Quality gates

Evaluate the Brain independently with a simulated Hands executor, then evaluate Brain + real Hands end-to-end.

**Brain-only:** task decomposition, order/dependency reasoning, guard checks, branch choice, business rationale provenance, capability selection, missing-information handling, Hands-result interpretation, recovery, replan, and stop decisions.

**Brain + Hands:** achieved business postconditions, safe operation, no unauthorized side effects, resilience to state variations, alternative paths, partial successes, and unseen tasks.

A correct button click is not a successful workflow decision unless the business postcondition is verified. Do not use generic video-QA scores or GUI perception scores as a proxy for Brain competence.
