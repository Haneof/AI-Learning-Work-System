# Real Video Integration Test

This test downloads and processes an actual, openly licensed tutorial recording on a GitHub-hosted Ubuntu runner. It exercises the current FFmpeg wrapper rather than mocked subprocesses.

## Sample and attribution

- Work: LibreOffice Writer – The Basics
- Original file: [Wikimedia Commons file page](https://commons.wikimedia.org/wiki/File:LibreOffice_Writer_%E2%80%93_The_Basics.webm)
- Download: [Original WebM](https://upload.wikimedia.org/wikipedia/commons/1/18/LibreOffice_Writer_%E2%80%93_The_Basics.webm)
- Attribution: Free I.T. Athens
- License: Creative Commons Attribution 3.0 (CC BY 3.0); retain attribution and license when redistributing the sample.

## What the automated test really runs

1. Downloads the real WebM file.
2. Runs `ffprobe` through `FFmpegProcessor.probe` and checks that video and audio streams exist.
3. Extracts the full audio track to mono 16 kHz WAV.
4. Transcodes a proxy MP4.
5. Extracts one frame every 60 seconds.
6. Registers the original file with SHA-256 and creates timestamp-located audio/frame segments in a source manifest.
7. Uploads the JSON report and derived artifacts as a workflow artifact.

The workflow is triggered for pull requests that change the media implementation and can also be started manually from GitHub Actions.

## Run locally on Windows

Install FFmpeg and add both `ffmpeg.exe` and `ffprobe.exe` to PATH. Then, from the repository root:

```powershell
python -m pip install -e .
New-Item -ItemType Directory -Force artifacts/real-media | Out-Null
Invoke-WebRequest -Uri "https://upload.wikimedia.org/wikipedia/commons/1/18/LibreOffice_Writer_%E2%80%93_The_Basics.webm" -OutFile "artifacts/real-media/LibreOffice_Writer_Basics.webm"
python scripts/validate_real_media_sample.py --input artifacts/real-media/LibreOffice_Writer_Basics.webm --output-dir artifacts/real-media/output
```

## Limits

This test validates real media probing, audio extraction, proxy transcoding, frame extraction, and source/segment manifest creation. It does not validate ASR, OCR, semantic step extraction, scanned PDFs, table PDFs, Windows-specific FFmpeg behavior, or RAM/VRAM peak telemetry. A passing Ubuntu workflow must not be represented as Windows acceptance.
