# Real Media, ASR, and OCR Integration Test

This test suite downloads and processes an actual, openly licensed tutorial recording on GitHub-hosted Ubuntu runners. It exercises real FFmpeg, faster-whisper, and Tesseract execution; it does not mock the media tools.

## Sample and attribution

- Work: LibreOffice Writer – The Basics
- Original file: [Wikimedia Commons file page](https://commons.wikimedia.org/wiki/File:LibreOffice_Writer_%E2%80%93_The_Basics.webm)
- Download: [Original WebM](https://upload.wikimedia.org/wikipedia/commons/1/18/LibreOffice_Writer_%E2%80%93_The_Basics.webm)
- Attribution: Free I.T. Athens
- License: Creative Commons Attribution 3.0 (CC BY 3.0); retain attribution and license when redistributing the sample.

## Automated test jobs

The `Real Media Sample Integration` workflow runs three real integration jobs:

1. **Real video / FFmpeg**
   - Downloads the original WebM and checks it with `ffprobe`.
   - Extracts the full audio track to mono 16 kHz WAV.
   - Transcodes a 1280-wide H.264 proxy MP4.
   - Extracts one frame every 60 seconds.
   - Registers the original file with SHA-256 and creates timestamp-located audio/frame segments in a source manifest.
   - Uploads the source, derived media, manifest, and JSON report.

2. **Real ASR / faster-whisper**
   - Downloads the same recording and extracts mono 16 kHz audio.
   - Runs the open-source `tiny.en` model on CPU with INT8 compute.
   - Writes segment text with start/end timestamps and a JSON report.
   - Checks that a non-empty transcript and valid timestamp intervals were returned.

3. **Real keyframe OCR / Tesseract**
   - Downloads the same recording and extracts one frame per 60 seconds through the project FFmpeg wrapper.
   - Runs Tesseract English OCR on each frame after resizing to a maximum of 640×360.
   - Writes recognized text, frame timestamps, per-frame character counts, and elapsed time to JSON.

Each job uploads its report and generated artifacts. The workflow runs for relevant pull requests and can also be started manually from GitHub Actions.

## Recorded test evidence

The following results were observed on the 21-minute, 1280×720 sample in GitHub-hosted Ubuntu runners:

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

These are integration smoke-test results, not accuracy benchmarks. The ASR transcript has not been scored against a human-verified reference transcript. OCR character count does not measure character-level accuracy or semantic correctness.

## Run locally on Windows

Install FFmpeg and add both `ffmpeg.exe` and `ffprobe.exe` to PATH. Then, from the repository root:

```powershell
python -m pip install -e .
New-Item -ItemType Directory -Force artifacts/real-media | Out-Null
Invoke-WebRequest -Uri "https://upload.wikimedia.org/wikipedia/commons/1/18/LibreOffice_Writer_%E2%80%93_The_Basics.webm" -OutFile "artifacts/real-media/LibreOffice_Writer_Basics.webm"
python scripts/validate_real_media_sample.py --input artifacts/real-media/LibreOffice_Writer_Basics.webm --output-dir artifacts/real-media/output
```

For the optional ASR smoke test:

```powershell
python -m pip install "faster-whisper>=1.1,<2"
ffmpeg -y -i artifacts/real-media/LibreOffice_Writer_Basics.webm -vn -ac 1 -ar 16000 artifacts/real-media/audio.wav
python scripts/validate_asr_sample.py --input artifacts/real-media/audio.wav --output artifacts/real-media/asr-report.json --model tiny.en
```

For the optional OCR smoke test, install Tesseract OCR and its English language data, then:

```powershell
python -m pip install -e .
python -m pip install pillow pytesseract
python scripts/validate_ocr_sample.py --input artifacts/real-media/LibreOffice_Writer_Basics.webm --output-dir artifacts/real-media/ocr --interval-seconds 60
```

## Mandarin Chinese test extension

A second, openly licensed Mandarin learning video is used for multilingual coverage:

- Work: 25 Essential Chinese Phrases You NEED to Know Before Visiting China!
- Source: [Wikimedia Commons file page](https://commons.wikimedia.org/wiki/File:25_Essential_Chinese_Phrases_You_NEED_to_Know_Before_Visiting_China!.webm)
- Author: My Mandarin Journey
- License: CC BY 3.0 (attribution required)
- Automated jobs: faster-whisper multilingual `tiny` with `zh` language hint; Tesseract Simplified Chinese `chi_sim` on 30-second keyframes.

These jobs are designed to validate that the pipeline can execute on Chinese-language media. A PASS only proves non-empty outputs and valid execution; it does not prove transcription correctness, Simplified-vs-Traditional script fidelity, or OCR accuracy. The report artifacts must be manually reviewed and scored against reference text before acceptance.

## Limits and remaining acceptance work

This suite validates one real narrated English screen-recording sample. It does **not** establish:

- ASR word error rate or correctness against a human-verified transcript.
- Chinese speech recognition or Chinese UI OCR.
- Dense-screen OCR recall/precision, table extraction, or PDF parsing.
- Semantic step extraction, knowledge approval, skill generation, or task success.
- Windows-specific FFmpeg/ASR/OCR acceptance.
- Peak RAM/VRAM, throughput under concurrent ingestion, or behavior on hundreds of GB of material.

Issue #3 must remain open until representative narrated recordings, text-dense recordings, and table PDFs are tested; source-linked outputs and failure cases are checked; and Windows reproduction plus resource measurements are recorded. A passing Ubuntu smoke test must not be represented as full media-ingestion acceptance.


## Manual Mandarin OCR reference set

A first reference set was manually transcribed by visually inspecting 10 corresponding extracted keyframes from the CC BY 3.0 Mandarin sample. It labels only the principal Simplified Chinese phrase shown on screen; pinyin, English translations, category headings, and incidental/background text are outside this benchmark's scope.

- Labels: `tests/fixtures/mandarin_ocr_ground_truth.json`
- Scorer: `scripts/score_ocr_reference.py`
- Metric: Chinese-character CER = Levenshtein edit distance / number of reference Chinese characters.
- Normalization: whitespace and non-CJK characters are removed before scoring.
- Observed result on the saved Tesseract 5.5.0 `chi_sim` report: 13 edit operations / 56 reference characters = **23.21% CER** (76.79% simple character-accuracy proxy).
- Largest error clusters occur at the 240-second and 270-second frames, where extra or misread Chinese characters appear around the main phrase.

This is a diagnostic score on 10 selected keyframes, not a representative general OCR accuracy claim. The scorer is wired into the Chinese OCR CI job and emits `ocr-score.json`. Future coverage should add more layouts, small fonts, dense screens, tables, Traditional Chinese, and background-only frames. This score is not yet a release gate.
