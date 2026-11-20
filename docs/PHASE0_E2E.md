# Phase 0 End-to-End Fixture Harness

## Run

From the repository root:

```powershell
python -m pip install -e ".[dev]"
python -m aios_work_system phase0-demo --output-dir artifacts/phase0-demo
pytest -q
```

The command refuses to overwrite a non-empty output directory. It creates a small synthetic text source, source manifest, evidence-linked approved knowledge item, validated skill package, and machine-readable plus Markdown reports.

## What this proves

- A source file is hashed and registered.
- A segment keeps a stable source ID and timestamp locator.
- Knowledge approval requires a valid supporting evidence link.
- A direct quote is checked against the source segment text.
- An ungrounded approved knowledge item is rejected.
- A skill package is statically validated and its immutable package hash is registered.
- A skill containing a blocked network import is rejected.
- A Docker command can be built with network, filesystem, capability, process and identity restrictions.

## What this does not prove

This is a deterministic contract-integration fixture, not an AI learning demonstration. It does not call the selected Qwen model, extract knowledge from an actual lesson, parse real PDF/video, run OCR/ASR/FFmpeg, or start a Docker container. The sandbox status in the report is explicitly `NOT_EXECUTED`. The image digest is a placeholder used only to validate command construction; it is not a real trusted image.

For final Issue #6 acceptance, add licensed representative samples (narrated screen recording, text-heavy video, table PDF), real parser and model adapters, a real preloaded sandbox image, malicious prompt-injection samples, and measured runtime/resource data. Never mark this issue complete from the synthetic fixture alone.
