# Downloaded Video-File Extraction Pipeline v0.1

## Scope

This route processes a downloaded tutorial video file with offline media programs. It does not control a live browser, read rrweb events, or infer actions from a live application session. Historical video evidence stays explicitly video-derived.

## Stages and evidence

1. **Subtitle / ASR:** existing SRT or WebVTT is preferred. If no usable cue file exists, faster-whisper transcribes the local video with timestamps and optional word timings.
2. **Frame sampling and change detection:** FFmpeg decodes a low-rate sequence of still frames. A cheap grayscale pixel-difference detector selects actual screen-change frames; the initial frame is retained as a state baseline.
3. **OCR:** Tesseract reads visible text and word boxes on the initial frame and selected changed frames. OCR is reported as observed screen content, not proof of an action.
4. **Cursor and click candidates:** OpenCV template tracking searches sampled frames for a visible pointer. A possible click is emitted only when a pointer candidate settles near a screen-change region. These results are always inferred_from_video; downloaded files contain no native click events.
5. **VLM grounding:** Qwen3-VL receives only frames selected by the change detector. Each request includes timestamp-matched OCR and nearby narration. Model results are hypotheses and retain confidence, uncertainty, and raw response. Unchanged frames are never sent to the VLM.
6. **Timeline alignment and DecisionEpisode:** subtitle/ASR segments are aligned to frame-change timestamps. The episode is validated with contracts.validate.validate_episode.

## Evidence labels

- observed_from_video: visible text, OCR regions, and frame changes read from decoded video frames.
- inferred_from_video: cursor/click hypotheses and VLM guesses about likely UI targets or actions.
- instructor_words: timestamped subtitle/ASR narration. Narration is contextual evidence; it is not automatically promoted into a business rule.

The generated episode keeps business_constraints empty, marks the operation not_observed, and leaves the outcome not_verified: a tutorial file cannot prove that a live target system accepted an action.

## Run locally

Install system tools ffmpeg and tesseract-ocr, then:

    python -m pip install -e ".[video,video-vlm,dev]"
    python scripts/download_tutorial_video.py --output-dir artifacts/tutorial-source
    python scripts/run_video_file_pipeline.py --input <downloaded-video-file> --captions <subtitle-file> --output-dir artifacts/video-extraction

Pass --vlm-model none to exercise the deterministic extraction stages without downloading Qwen3-VL weights. The real-media GitHub Actions workflow attempts Qwen3-VL on changed frames and records model-load or per-frame inference failures in part-breakdown.json.

## Per-part report

part-breakdown.json records stage status, counts, frame timestamps, OCR results, cursor candidates, click hypotheses, VLM submissions/results/failures, narration alignment coverage, and final contract validation.


## Demo source fallback

The downloader tries the three user-supplied YouTube IDs first. If YouTube denies the runner access, it records each failure and downloads the openly licensed Wikimedia Commons Content Translation Screencast (English) plus its timed SRT captions. The fallback attribution and CC BY-SA 4.0 license are written to `source-manifest.json`. This remains a real downloaded software screencast video file; it is not a synthetic fixture.
