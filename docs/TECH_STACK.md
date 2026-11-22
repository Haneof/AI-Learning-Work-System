# Technology Stack and Validation Strategy

**Version:** 0.1 design update  
**Policy:** reuse existing operation models; focus new learning effort on Brain workflow competence. Quality first, efficiency second. This document describes the target design, not a claim that every adapter is already integrated.

## 1. System roles

| Layer | Candidate/tooling | Responsibility | Project status |
|---|---|---|---|
| Brain base model | A selected 4B language model | Business reasoning, task decomposition, conditional planning, capability delegation, verification, recovery | Primary LoRA training target; exact base revision is selected through separate model validation |
| Brain vertical adapter | LoRA | Learn reusable workflow decision behavior for a domain | Target training output |
| Video-file extraction | FFmpeg, pixel-difference detection, Tesseract, OpenCV, local GUI-grounding models | Process downloaded tutorial files offline; detect changed frames and derive visible UI evidence and explicitly inferred action hypotheses | Implemented in PR #38 |

| Narration processing | Existing subtitles first; ASR fallback and timestamp alignment | Preserve instructor words, reasons, constraints, and timing | Real ASR/alignment integration and language validation required |
| Workflow representation | HTN plus conditional graph | Store task hierarchy, methods, preconditions, hard dependencies, soft preferences, postconditions, and recovery rules | Target data contract |
| Hands operation layer | Existing open-source GUI operation model, e.g. UI-TARS | Live page recognition and low-level execution | Reuse; do not rebuild as part of the Brain learning project |
| Hands adapter | Project-owned capability adapter | Translate Brain capability delegation into the existing Hands model's request format and normalize its execution result | Interface/integration work |
| Validation | Simulated Hands executor, Docker sandbox, live GUI loop | Isolate Brain decisions, then validate the complete Brain + Hands pair | Target evaluation harness |

The Brain is not trained to find buttons. It is trained to decide which business task should be done, why, under which conditions, and how to react to the Hands result.

## 2. Downloaded video-file input and narration alignment

The primary input is a downloaded tutorial video file. Programs process it offline; they do not play it in real time and do not require a live recorder/event collector.

1. Prefer an existing timestamped SRT/WebVTT subtitle file. If usable subtitle cues are unavailable, run local faster-whisper ASR and retain the transcript method, language, and timestamps.
2. Use FFmpeg to decode timestamped sampled stills.
3. Use grayscale pixel-difference detection to select the initial state and actual screen-change frames.
4. Run Tesseract OCR on the initial/changed frames. OpenCV cursor tracking and the changed-region heuristic produce possible-click candidates; these are inferred from pixels, not recorded events.
5. Run local ShowUI/UI-TARS grounding on selected changed frames. The measured metric is point-in-annotated-target-box hit rate, not click-event accuracy; escalation follows measured quality thresholds.
6. Align transcript segments to visual change events. Preserve the instructor's words separately from behavioral inference.

**Superseded route — cancelled 2026-11-21:** the previous proposal to capture rrweb events from live web tutorials and Windows UI Automation events from live desktop tutorials was cancelled. The file-based route supersedes it because existing/downloadable tutorials can be processed without per-application recorder installation or synchronizing a live capture session. The old proposal remains historical context, not an active route or required fallback.

Evidence labels remain conservative:
- `observed_from_video`: decoded visual content, actual screen changes, and OCR text.
- `inferred_from_video`: cursor/click hypotheses and grounded target coordinates.
- `instructor_words`: timestamped subtitles or ASR.
- `unknown`: activity or state that the video cannot establish.

A video cannot provide native DOM/UIA/mouse/keyboard telemetry. Never relabel an inferred interaction as a directly captured event. A visible screen change does not prove which action caused it or that the business operation succeeded.

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

The Qwen3-VL-4B vs Mage-VL-4B blind test on Colab T4 was stopped on 2026-11-21 at approximately 19:51 PST after Qwen3-VL-4B scored 4.0/25. This was not a completed winner-selection benchmark; no winner is declared. The test did not reject frame extraction. The selected route is the downloaded-video, frame-change-driven pipeline, which combines visual evidence with subtitles/ASR, OCR, cursor inference, local UI grounding, and verification.

## 6. Training resources

- First Brain LoRA base: 4B.
- T4 16GB profile: 4B FP16 LoRA; 24GB+ planning capacity for 9B LoRA. The merged PR #41 configuration disables BF16 on T4.
- Local RTX 3070 8GB: development, video-file processing, and lightweight validation; not the default 4B BF16 training environment.
- For every run, record base revision, dataset snapshot hash, context length, batch, gradient accumulation, optimizer, precision, checkpointing, GPU model/VRAM, peak memory, wall time, and adapter hash.
- Planning estimates must not be reported as measured capacity.

## 7. Existing components: retain but do not overstate

| Component | Keep for | Do not claim it does |
|---|---|---|
| FFmpeg | Probe downloaded media, extract audio, and decode timestamped stills | Capture DOM/UIA events or infer business workflow |
| ASR/OCR protocols and local tools | Protocols remain deterministic fixtures in legacy tests; the video-file pipeline invokes faster-whisper and Tesseract for actual local extraction | Prove semantic correctness from raw text or OCR alone |
| StaticASRAdapter/StaticOCRAdapter | Deterministic tests | Transcribe or read real tutorial content |
| GUI Agent and operation adapter | Hands execution and live expert validation | Train the Brain's workflow decision policy |
| Skill package compiler | Compile/validate supporting knowledge and test material | Replace HTN workflow decision training |
| Docker sandbox | Isolate execution and validate behavior | Prove business competence without workflow tests |
| SQLite | Structured source, extraction-evidence, episode, workflow, review, and training-lineage metadata | Store bulk source video objects |

## 8. Quality gates

Evaluate the Brain independently with a simulated Hands executor, then evaluate Brain + real Hands end-to-end.

**Brain-only:** task decomposition, order/dependency reasoning, guard checks, branch choice, business rationale provenance, capability selection, missing-information handling, Hands-result interpretation, recovery, replan, and stop decisions.

**Brain + Hands:** achieved business postconditions, safe operation, no unauthorized side effects, resilience to state variations, alternative paths, partial successes, and unseen tasks.

A correct button click is not a successful workflow decision unless the business postcondition is verified. Do not use generic video-QA scores or GUI perception scores as a proxy for Brain competence.


## Implemented milestones and limits

- **PR #38:** downloaded-video extraction, DecisionEpisode assembly, and contract validation.
- **PR #39:** local open-weight verifier for extraction fidelity, decision validity, and outcome validity; PM independent review remains a separate admission gate.
- **PR #40:** fail-closed compilation of dual-approved episodes into decision-time Brain samples and metadata sidecars.
- **PR #41:** metadata-aware dataset preparation and Qwen3 4B Brain LoRA configuration; no completed training run or adapter is implied.
- **PR #42:** Brain/Hands closed loop. CI uses a deterministic WorkflowBrain stand-in and SimulatedHands; the real Hands model path is documented but was not run.

The earlier live rrweb/Windows UIA tutorial recorder was cancelled on 2026-11-21. This is separate from runtime BrowserAgent observations and JSONL traces, which belong to Hands execution rather than tutorial ingestion.
