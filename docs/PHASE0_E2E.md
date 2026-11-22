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

This is a deterministic contract fixture, not an AI learning demonstration or the target tutorial pipeline. It does not:
- search for or download tutorials into Google Drive;
- capture rrweb or Windows UI Automation event streams from a real tutorial;
- align real instructor narration or run real subtitle/ASR alignment;
- produce Decision Episodes or HTN workflow definitions;
- train or evaluate a Brain LoRA, call an existing Hands operation model, or run Brain-to-Hands delegation;
- perform the GPT + PM double-review workflow;
- train or load a LoRA expert;
- parse real PDF/video, run real OCR/ASR/FFmpeg in this command, or start a Docker container.

The sandbox status in the report is explicitly NOT_EXECUTED. The image digest is a placeholder used only to validate command construction; it is not a real trusted image.

This harness remains useful for deterministic contract and safety regression. It is not the final product and must not be used as evidence that a vertical expert has learned or generalized.

## Required end-to-end acceptance

The full target pipeline is documented in [ACQUISITION_PIPELINE.md](ACQUISITION_PIPELINE.md). Final acceptance requires licensed tutorials, direct semantic UI event capture for new recordings, aligned instructor narration, source-grounded Decision Episodes, HTN workflows with conditional branches and recovery, GPT review plus PM verification, SQLite approved knowledge storage, a Brain LoRA training snapshot, and Brain-to-Hands evaluation in Docker sandbox and the live GUI operation loop. Legacy MP4 reconstructions must remain labelled inferred_from_video.
