# Real Media, ASR, and OCR Component Smoke Tests

This document records existing component-level integration tests on an openly licensed tutorial recording. These jobs exercise FFmpeg, faster-whisper, and Tesseract. The sampled-frame extraction and OCR steps are retained only as legacy media-component tests. They are **not** the selected tutorial-learning route and must not be treated as the primary operational event stream or Brain training input. New tutorials should capture semantic rrweb or Windows UI Automation events directly and align them with the instructor's voice narration.

## Sample and attribution

- Work: LibreOffice Writer – The Basics
- Original file: [Wikimedia Commons file page](https://commons.wikimedia.org/wiki/File:LibreOffice_Writer_%E2%80%93_The_Basics.webm)
- Download: [Original WebM](https://upload.wikimedia.org/wikipedia/commons/1/18/LibreOffice_Writer_%E2%80%93_The_Basics.webm)
- Attribution: Free I.T. Athens
- License: Creative Commons Attribution 3.0 (CC BY 3.0); retain attribution and license when redistributing the sample.

## Existing automated component jobs

The `Real Media Sample Integration` workflow currently runs:

1. **Real video / FFmpeg**
   - Downloads the original WebM and checks it with `ffprobe`.
   - Extracts mono 16 kHz audio, creates an H.264 proxy, and extracts one frame every 60 seconds.
   - Registers original file SHA-256 and timestamp-located audio/frame segments.
   - Uploads artifacts and a JSON report.

2. **Real ASR / faster-whisper**
   - Runs the open-source `tiny.en` model on CPU with INT8 compute.
   - Writes segment text with start/end timestamps and checks for a non-empty transcript and valid intervals.

3. **Real keyframe OCR / Tesseract**
   - Extracts one frame every 60 seconds.
   - Runs Tesseract English OCR on sampled frames after resizing.
   - Writes recognized text, frame timestamps, per-frame character counts, and elapsed time.

Each job uploads reports and generated artifacts. The workflow is a component smoke test; it does not invoke a multimodal workflow-understanding model or a GUI operation model.

## Existing recorded smoke-test evidence

The following results were recorded on the 21-minute, 1280×720 sample in GitHub-hosted Ubuntu runners:

| Test | Observed result |
|---|---|
| FFmpeg probe | VP9 video + Opus audio detected |
| Audio extraction | Mono, 16 kHz WAV produced |
| Proxy transcode | H.264, 1280×720 MP4 produced |
| Keyframe extraction | 21 frames |
| Source manifest | 1 audio segment + 21 timestamped frame segments |
| Source integrity | Original SHA-256 matched the manifest and report |
| faster-whisper `tiny.en` | 341 timestamped segments; 16,794 transcript characters; CPU INT8 |
| Tesseract 5.5.0 | 21/21 sampled frames returned text; 11,365 characters |

These are execution results, not accuracy benchmarks. ASR was not scored against a PM-verified transcript. OCR character count is not character-level accuracy or semantic correctness.

## Relation to the target pipeline

In the target design, subtitles are a **cheap pre-filter**:
- use existing subtitles when available;
- otherwise use ASR to produce timestamped subtitles;
- reject non-tutorial or wrong-vertical videos before full GPU extraction.

For newly recorded tutorials, the target path is direct semantic UI event capture (rrweb for web applications, Windows UI Automation for Windows desktop applications) plus aligned instructor narration. These become Decision Episodes describing goal, current state, instructor-explicit rationale, selected operation, outcome, and next decision. Legacy MP4 files may be reconstructed only as a fallback; reconstructed interactions must be labelled inferred_from_video. The earlier Qwen3-VL-4B vs Mage-VL-4B Colab T4 blind test was stopped on 2026-11-21 at approximately 19:51 PST after Qwen3-VL-4B scored 4.0/25. No winner was selected, and the frame-based route was rejected as the primary learning method.

Therefore this existing smoke test does not establish:
- correct operation-step or intent extraction;
- UI-state transition understanding;
- mouse-click history or coordinate accuracy;
- observed/inferred classification;
- verified knowledge-package quality;
- LoRA training readiness or expert generalization.

## Local component checks

Install FFmpeg and add `ffmpeg.exe` and `ffprobe.exe` to PATH, then:

```powershell
python -m pip install -e .
New-Item -ItemType Directory -Force artifacts/real-media | Out-Null
Invoke-WebRequest -Uri "https://upload.wikimedia.org/wikipedia/commons/1/18/LibreOffice_Writer_%E2%80%93_The_Basics.webm" -OutFile "artifacts/real-media/LibreOffice_Writer_Basics.webm"
python scripts/validate_real_media_sample.py --input artifacts/real-media/LibreOffice_Writer_Basics.webm --output-dir artifacts/real-media/output
```

Optional component-level ASR:

```powershell
python -m pip install "faster-whisper>=1.1,<2"
ffmpeg -y -i artifacts/real-media/LibreOffice_Writer_Basics.webm -vn -ac 1 -ar 16000 artifacts/real-media/audio.wav
python scripts/validate_asr_sample.py --input artifacts/real-media/audio.wav --output artifacts/real-media/asr-report.json --model tiny.en
```

Optional component-level OCR requires Tesseract and its language data:

```powershell
python -m pip install pillow pytesseract
python scripts/validate_ocr_sample.py --input artifacts/real-media/LibreOffice_Writer_Basics.webm --output-dir artifacts/real-media/ocr --interval-seconds 60
```

## Acceptance still required

The target pipeline still requires direct event-capture validation, narration synchronization and alignment, Decision Episode and HTN workflow quality checks, evidence labels, GPT + PM dual review, SQLite verified storage, Brain LoRA training, simulated-Hands decision evaluation, and Brain-to-Hands validation in the sandbox and live GUI operation loop. Throughput or media-smoke-test PASS status cannot substitute for those gates.
