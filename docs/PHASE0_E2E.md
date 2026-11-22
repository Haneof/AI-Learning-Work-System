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
- inspect embedded subtitles or run real ASR pre-filtering;
- call Qwen3-VL, Mage-VL, or Magma;
- understand video actions, intentions, UI state transitions, or click coordinates;
- perform the GPT + PM double-review workflow;
- train or load a LoRA expert;
- parse real PDF/video, run real OCR/ASR/FFmpeg in this command, or start a Docker container.

The sandbox status in the report is explicitly NOT_EXECUTED. The image digest is a placeholder used only to validate command construction; it is not a real trusted image.

This harness remains useful for deterministic contract and safety regression. It is not the final product and must not be used as evidence that a vertical expert has learned or generalized.

## Required end-to-end acceptance

The full target pipeline is documented in [ACQUISITION_PIPELINE.md](ACQUISITION_PIPELINE.md). Final acceptance requires a licensed tutorial corpus, subtitle-first filtering, real video understanding and action grounding, evidence-linked observed/inferred trajectories, GPT review plus PM verification, SQLite approved knowledge storage, a verified LoRA training snapshot, and trained-expert evaluation in Docker sandbox and the GUI operation loop.
