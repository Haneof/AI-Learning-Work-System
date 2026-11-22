# Downloaded Video-File Extraction Pipeline v0.2

## Scope and non-negotiable inference policy

This pipeline processes downloaded tutorial **video files** with local programs. It does not record live browser sessions, use rrweb, or reconstruct native click telemetry from screenshots.

All model inference in the learning/extraction path must use locally loaded open-weight models. GPT, Gemini, hosted moderation services, and hosted inference endpoints are not permitted. Hugging Face access in the downloader is used only to fetch model weight files. The processing command loads models from local paths; the demo workflow sets \`HF_HUB_OFFLINE=1\` and \`TRANSFORMERS_OFFLINE=1\` for the inference stage.

The code reports \`external_inference_provider_calls: 0\`. No video, image, OCR, transcript, or episode content is sent to a model API.

## Processing stages

1. **Subtitle / ASR:** use a local SRT/WebVTT track when available. Otherwise faster-whisper transcribes the downloaded file locally and keeps segment/word timestamps.
2. **Frame sampling and cheap screen-change detection:** FFmpeg decodes sampled stills. A grayscale pixel-difference detector chooses frames where the screen actually changed; unchanged frames are not sent to a vision model.
3. **OCR:** Tesseract reads visible UI text and text-region boxes on the initial state and selected changed frames. OCR is evidence of visible pixels, not proof of a click.
4. **Cursor / possible-click inference:** OpenCV searches for visible pointer candidates and compares them with changed regions. Every click candidate is labelled \`inferred_from_video\`; a video file contains no native click event telemetry.
5. **UI element grounding — small model first:**
   - ShowUI-2B (MIT) is tested first on a human-annotated target-box benchmark.
   - If its measured target-box hit rate is below 0.75, or coordinate parse rate below 0.95, UI-TARS-2B-SFT (Apache-2.0) is measured next.
   - UI-TARS-7B-SFT (Apache-2.0) is considered only when at least one 2B model was actually evaluated and both available 2B models miss the measured gate. A missing/unloadable 2B is not treated as poor accuracy and does not by itself trigger a larger model.
   - The metric is point-in-manually-annotated-target-box hit rate. This is UI-target localization accuracy, **not click-event accuracy**.
6. **Narration alignment:** timestamped subtitle/ASR segments are joined to nearby screen-change events. Narration is preserved as the instructor's words; it is not turned into policy by itself.
7. **DecisionEpisode synthesis — 4B model first:**
   - Aurum-4B-Uncensored Q4_K_M (Apache-2.0) runs locally through llama.cpp and generates only the structured \`decision\` JSON object from already structured events, OCR and narration.
   - The code measures JSON parse validity, required fields, allowed evidence references, empty business constraints, ask-user review action, and the full DecisionEpisode contract.
   - DeepSeek-V4-Pro-Qwen3.5-9B-UNCENSORED-heretic Q4_K_M (Apache-2.0) is considered only after Aurum has actually generated a response that fails JSON/semantic/schema checks. Failure to install/load Aurum or failure before a generated response is **not** counted as measured poor model quality and does not trigger the 9B model.
   - If neither model can be measured, the deterministic code-built baseline is retained and the report says the model was not measured. It is not labelled as a model-generated result.
8. **Contract validation:** every episode is validated by \`contracts.validate.validate_episode\`.

The model-card refusal figures for uncensored variants are publisher-reported measurements, not a guarantee that every prompt will be answered. The pipeline does not rely on those claims as a quality test; it logs the actual local model result for each run.

## Evidence labels and limits

- \`observed_from_video\`: decoded frames, screen changes, and text visibly read by OCR.
- \`inferred_from_video\`: cursor/click hypotheses and UI target coordinates returned by a grounding model.
- \`instructor_words\`: timestamped subtitles or ASR transcript. This is what the speaker said, not proof of an action or business rule.

The generated episode keeps \`business_constraints\` empty, marks operation execution as \`not_observed\`, and outcome as \`not_verified\`. A tutorial video cannot prove that a live target system accepted an operation.

## Local installation

Install system tools FFmpeg and Tesseract, then install the project and local-model runtime:

    python -m pip install -e ".[dev,video,video-open-models]"
    python -m pip install torch torchvision

Install the PyTorch build matching the local GPU/driver from the official PyTorch selector. For CUDA devices that can use 4-bit BitsAndBytes quantization for the 7B fallback:

    python -m pip install -e ".[video-open-models-cuda]"

The primary weights (two small GUI models and the 4B structured-output model) are fetched into the local model directory:

    python scripts/download_video_models.py --model-dir artifacts/models

Large fallbacks are optional and can be downloaded only when the operator has enough disk/memory:

    python scripts/download_video_models.py --model-dir artifacts/models --include-large-fallbacks

The weight downloader writes \`artifacts/models/model-manifest.json\`. It downloads weight files only and performs no inference.

## Run an offline local video-file demo

Download one tutorial file and timestamped subtitles:

    python scripts/download_tutorial_video.py --output-dir artifacts/tutorial-source

Then run local inference with already downloaded weights. No \`--allow-model-download\` flag is needed when all selected weights are present:

    python scripts/run_video_file_pipeline.py --input artifacts/tutorial-source/<video-file> --captions artifacts/tutorial-source/<subtitle-file> --output-dir artifacts/video-extraction --ui-model-path artifacts/models/showui-2b --ui-secondary-small-model-path artifacts/models/ui-tars-2b --ui-fallback-model-path artifacts/models/ui-tars-7b --grounding-benchmark tests/fixtures/video_grounding_benchmark.wikimedia.json --episode-model-path artifacts/models/aurum-4b-q4.gguf --episode-fallback-model-path artifacts/models/deepseek-v4-pro-9b-q4.gguf --maximum-changed-frames 24

To explicitly permit downloading a fallback model's **weights** after its escalation gate fires, add \`--allow-model-download\`. This still performs all inference locally.

## Demo benchmark

\`tests/fixtures/video_grounding_benchmark.wikimedia.json\` contains four manually annotated target bounding boxes from the downloaded Wikimedia Content Translation tutorial. These boxes assess whether a model's normalized point is inside the intended UI element. They are not native click labels and cannot establish a click event.

## Per-part report files

The output directory contains:

- \`part-breakdown.json\`: per-stage status and counts, model IDs, model licences, measured scores, fallback decisions, timings, and inference backend.
- \`ui-grounding-model-evaluation.json\`: primary/secondary/fallback target-box scores and per-frame predictions.
- \`decision-synthesis.json\`: Aurum-4B parse/quality/schema result, fallback trigger/result, selected model, latency and token counts.
- \`transcript.json\`, \`ocr.json\`, \`cursor-and-click-inferences.json\`, \`ui-grounding.json\`, \`narration-alignment.json\`.
- \`decision-episode.json\` and \`validation.json\`.

## Real tutorial source used by the CI demo

The downloader tries the three user-supplied YouTube IDs first. If YouTube denies runner access, it records each failure and downloads the real Wikipedia Content Translation Tool Tutorial (2 min 8 s) from Wikimedia Commons with its published English SRT captions. The video is by AlexandraShagzhina and is licensed CC BY-SA 4.0. The fallback attribution and licence are written to \`source-manifest.json\`. This is a real browser-tool tutorial file, not a synthetic fixture.
