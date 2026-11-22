# Phase 0 Synthetic Contract Harness

## Run

From the repository root:

```powershell
python -m pip install -e ".[dev]"
python -m aios_work_system phase0-demo --output-dir artifacts/phase0-demo
pytest -q
```

The command refuses to overwrite a non-empty output directory. It creates a small synthetic text source, source manifest, evidence-linked approved knowledge item, validated skill package, and machine-readable plus Markdown reports.

## What this proves

- A source file can be hashed and registered.
- A segment keeps a stable source ID and timestamp locator.
- Knowledge approval requires a valid supporting evidence link.
- A direct quote is checked against source segment text.
- An ungrounded approved knowledge item is rejected.
- A skill package is statically validated and its immutable package hash is registered.
- A skill containing a blocked network import is rejected.
- A Docker command can be built with network, filesystem, capability, process and identity restrictions.

## What this does not prove

This is a deterministic contract fixture, not an AI learning demonstration or the downloaded-video pipeline. It does not:
- discover/download tutorial video files or archive them in Google Drive;
- run the video-file extractor on a real tutorial (subtitle/ASR, FFmpeg frame sampling, screen-change detection, OCR, cursor inference, or UI grounding);
- build or validate real source-grounded DecisionEpisodes from tutorial files;
- run the local DecisionEpisode verifier or supply independent PM review evidence;
- compile a real approved corpus, prepare a production dataset, or train/load a Brain LoRA;
- run a real Hands operation model, perform Brain-to-Hands delegation against a live application, or demonstrate expert generalization;
- perform the full review/admission process or create an approved training dataset;
- parse real PDF/video, run OCR/ASR/FFmpeg in this Phase 0 command, or start a Docker container.

The sandbox status in the report is explicitly NOT_EXECUTED. The image digest is a placeholder used only to validate command construction; it is not a real trusted image.

This harness remains useful for deterministic contract and safety regression. It is not evidence that a vertical expert has learned or generalized.

## Required end-to-end acceptance

The current repository milestone chain is:

1. **PR #38 — downloaded video-file extraction:** subtitles/ASR, FFmpeg frame sampling, screen-change-driven visual extraction, OCR/cursor/UI grounding, narration alignment, DecisionEpisode assembly, and contract validation.
2. **PR #39 — local verifier gate:** local open-weight checks for extraction fidelity, decision validity, and outcome validity. All three must pass; local PASS alone remains held pending independent PM review.
3. **PR #40 — training-sample compiler:** compile only dual-approved, quality-approved decision points into conversational Brain samples with source-grouped splits and separate sidecars.
4. **PR #41 — Brain LoRA setup:** metadata-aware dataset preparation and T4 configuration. A real approved corpus and actual training run are still required to produce an adapter.
5. **PR #42 — Brain+Hands closed-loop harness:** verify business postconditions and recovery. Current CI uses a deterministic WorkflowBrain stand-in and SimulatedHands; it does not run a trained Brain adapter or a real UI-TARS-class Hands model.

The legacy live rrweb/Windows UIA tutorial recorder/event-collector proposal was cancelled on **2026-11-21** and superseded by downloaded-video-file extraction. It is historical context only, not an active ingestion route or required fallback.

Full acceptance still requires an eligible real tutorial corpus, the local verifier plus independent PM PASS, actual LoRA training and held-out evaluation, and real Hands evaluation in a controlled environment. Video-derived interactions that cannot be established from the source remain labelled inferred_from_video or unknown; never present them as native click/UIA telemetry.
