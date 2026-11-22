# Engineering Roadmap

**Version:** updated after PRs #38–#42  
Stage order is governed by evidence and quality gates. Do not scale tutorial volume to compensate for a weak learning signal.

## Selected route and superseded decision

The primary learning route is **downloaded tutorial video files processed offline**. The pipeline prefers existing timestamped subtitles, uses local ASR only when needed, decodes sampled frames with FFmpeg, detects actual screen changes, runs OCR and cursor/UI-target inference on selected frames, aligns narration, and creates DecisionEpisodes.

**Superseded — cancelled 2026-11-21:** the previously proposed rrweb web-recorder / Windows UI Automation desktop-recorder event-collector route was cancelled. It was replaced by file-based extraction because tutorials can be processed from downloaded files without installing and synchronizing a recorder in every live application/session. Retain the old proposal as history only, not an active ingestion route or required fallback.

Frames are not rejected. Uncontextualized screenshot dumps are insufficient, but frame-change-driven extraction combined with transcript/ASR, OCR, cursor inference, target grounding, provenance, and verification is the selected method.

## Stage 0 — Acquire and preserve video files

**Status:** downloader implementation exists; full production cloud archive integration remains a separate integration task.

**Deliverables**
- Tutorial video file and available subtitle files.
- Source URL/platform, creator/course grouping, source hash, and attribution/license metadata.
- One acquisition record for each selected file.

**Exit criteria**
- Source file is reproducibly available to the local extraction pipeline.
- Attribution, licensing, source identity, and hash are retained.
- Unknown metadata remains unknown rather than guessed.

## Stage 1 — Video-file extraction and DecisionEpisode validation (PR #38)

**Status:** implemented and merged.

**Deliverables**
- Existing-subtitle-first parsing and local faster-whisper fallback.
- FFmpeg timestamped frame sampling and pixel-difference screen-change detection.
- Tesseract OCR on initial/changed frames.
- OpenCV cursor and possible-click inference.
- Local ShowUI/UI-TARS grounding on selected changed frames with measured escalation gates.
- Timestamp alignment between narration and visual change events.
- Structured DecisionEpisode assembly and contract/schema validation.
- Per-stage reports and evidence artifacts.

**Exit criteria**
- Every episode claim references timestamped source evidence or is explicitly unknown/inferred.
- Video-derived hypotheses are never labelled as native DOM, UIA, mouse, or keyboard telemetry.
- Contract validity is kept separate from truth, independent review, and training approval.

## Stage 2 — Local verifier and independent PM gate (PR #39)

**Status:** local verifier implemented and merged; real approved corpus still required.

**Deliverables**
- Local open-weight verifier for extraction fidelity, decision validity, and outcome validity.
- Separate pass/fail/unknown verdicts, reasons, evidence references, and unknowns.
- Fail-closed preliminary training admission.
- Independent PM verification using the original source and proposed episode.

**Exit criteria**
- All three local levels pass; there is no majority-vote override.
- PM review separately passes and cites source evidence and reviewed episode claims.
- Video-only temporal ordering is not accepted as causal proof of an operation outcome.

## Stage 3 — Training-sample compiler (PR #40)

**Status:** implemented and merged.

**Deliverables**
- One conversational Brain sample per decision point.
- Compiler checks for local verification, PM evidence review, annotation status, quality/trainable flags, and exclusion reasons.
- Source/course-grouped train/test splits, manifest, and separate training metadata sidecars.
- Decision-time input only; future Hands outcomes do not leak into earlier assistant targets.

**Exit criteria**
- Held, rejected, incomplete, or misaligned examples are excluded fail-closed.
- Sidecar metadata is not inserted into model-facing messages.
- At least two distinct eligible source groups exist before claiming a meaningful train/test evaluation split.

## Stage 4 — Brain LoRA preparation and training (PR #41)

**Status:** preparation and T4 Axolotl configuration implemented and merged; actual training not run.

**Deliverables**
- Metadata-aware train/test sidecar alignment and exclusion checks.
- Bounded evidence-weighted train-row repetition; test split remains unchanged.
- `DreamFast/qwen3-4b-heretic` Transformers checkpoint configuration.
- T4-compatible FP16 LoRA configuration and tokenization/config validation.

**Remaining exit criteria**
- Obtain enough real dual-approved examples and source groups.
- Run the actual configured training job on provisioned compute.
- Record base revision, dataset hash, run configuration, resource usage, metrics, and adapter hash.
- Evaluate the trained adapter on held-out decision points and unseen workflow variations.

The merged configuration is not a trained adapter. PR #41 explicitly did not download the checkpoint, run Axolotl optimization, or produce weights.

## Stage 5 — Brain-to-Hands closed loop (PR #42)

**Status:** protocol, loop, simulator, and adapter bridge implemented and merged.

**Deliverables**
- Typed business-level Brain delegation and Hands execution-result contracts.
- WorkflowDefinition-driven deterministic Brain test stand-in.
- SimulatedHands business-state executor.
- Fresh observation and independent postcondition verification after every Hands result.
- Failure/partial/uncertain-result recovery and safe stop behavior.
- BrowserAgentHandsAdapter reusing the existing GUI execution machinery.

**Remaining exit criteria**
- Add a serving adapter for the actual trained Brain LoRA.
- Run and evaluate the real Hands operation model manually against a controlled local app.
- Test business-goal completion, alternate paths, partial failures, safe recovery, and postcondition evidence—not click count.
- Integrate and test the full extraction → approved dataset → trained Brain → Hands path as one usable workflow.

The PR #42 CI acceptance used only the deterministic Brain stand-in and SimulatedHands. No real Brain adapter or real UI-TARS-class Hands model was run.

## Historical model experiment

The earlier Qwen3-VL-4B vs Mage-VL-4B blind comparison on Colab T4 was stopped on 2026-11-21 at approximately 19:51 PST after Qwen3-VL-4B scored 4.0/25. It was not a completed winner-selection benchmark; no model winner is claimed. That experiment did **not** reject frame extraction and is not the reason the tutorial-ingestion route changed.

## Engineering management

Every implementation task must state objective, scope, model role, input/output contract, quality metrics, evidence source, tests, resource measurement, risk, and rollback plan. A merged commit or high throughput is not a quality acceptance result.
