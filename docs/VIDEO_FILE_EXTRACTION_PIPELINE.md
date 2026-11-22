# Downloaded Video-File Extraction Pipeline v0.2

## Scope and non-negotiable inference policy

This pipeline processes downloaded tutorial **video files** with local programs. It does not record live browser sessions, use rrweb, or reconstruct native click telemetry from screenshots.

All model inference in the learning/extraction path uses local open-weight models. GPT, Gemini, hosted moderation services, and hosted inference endpoints are not permitted. The demo downloads the primary small models before processing. It permits Hugging Face access solely for fallback weight files if—and only if—the existing measured quality gates justify escalation: UI-TARS-7B after at least one 2B model was measured and both available 2B models miss the grounding threshold; the 9B synthesis model only after the 4B model generated an output that fails JSON, semantic, or contract checks. Downloaded weights are loaded from disk and inference remains local; no video, frame, OCR, transcript, or episode data is sent to a remote model service.

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

## Run a local video-file demo

Download one tutorial file and timestamped subtitles:

    python scripts/download_tutorial_video.py --output-dir artifacts/tutorial-source

Then run local inference with already downloaded weights. No \`--allow-model-download\` flag is needed when all selected weights are present:

    python scripts/run_video_file_pipeline.py --input artifacts/tutorial-source/<video-file> --captions artifacts/tutorial-source/<subtitle-file> --output-dir artifacts/video-extraction --ui-model-path artifacts/models/showui-2b --ui-secondary-small-model-path artifacts/models/ui-tars-2b --ui-fallback-model-path artifacts/models/ui-tars-7b --grounding-benchmark tests/fixtures/video_grounding_benchmark.wikimedia.json --episode-model-path artifacts/models/aurum-4b-q4.gguf --episode-fallback-model-path artifacts/models/deepseek-v4-pro-9b-q4.gguf --maximum-changed-frames 24

To explicitly permit downloading a fallback model's **weights** after its escalation gate fires, add \`--allow-model-download\`. This still performs all inference locally.

## Demo benchmark

\`tests/fixtures/video_grounding_benchmark.wikimedia.json\` contains four manually annotated target bounding boxes from the downloaded Wikimedia Content Translation tutorial. These boxes assess whether a model's normalized point is inside the intended UI element. They are not native click labels and cannot establish a click event.

## Per-part report files

The output directory contains:

- \`part-breakdown.json\`: per-stage status and counts, stage wall-clock timings, model IDs, model licences, measured scores, fallback decisions, and inference backend. Grounding predictions and synthesis attempts also record their own model latency separately.
- \`ui-grounding-model-evaluation.json\`: primary/secondary/fallback target-box scores and per-frame predictions.
- \`decision-synthesis.json\`: Aurum-4B parse/quality/schema result, fallback trigger/result, selected model, latency and token counts.
- \`transcript.json\`, \`ocr.json\`, \`cursor-and-click-inferences.json\`, \`ui-grounding.json\`, \`narration-alignment.json\`.
- \`decision-episode.json\` and \`validation.json\`.

## Local DecisionEpisode verification gate

After episode synthesis and contract validation, a separate local open-weight model performs the first-pass verification before the proposed episode is written to the output artifact. The three verdicts are reported independently:

1. **Extraction fidelity:** do the claims in the episode match the timestamped transcript, OCR, frame-change, cursor and GUI-grounding source records?
2. **Decision validity:** was the selected decision reasonable using only the state, information and constraints available at that decision point? An action can be extracted faithfully and still FAIL this level when it violates a constraint or is otherwise unsound.
3. **Outcome validity:** is there evidence that the operation achieved its intended result, rather than merely being followed by a positive-looking screen? The local gate requires direct operation evidence, direct business-result evidence tied to a passed postcondition, and a controlled comparison or system audit trail addressing confounders. A video-only temporal sequence is UNKNOWN, not causal proof.

Each level reports pass, fail or unknown, with reasons, evidence IDs and explicit unknowns. Invalid or unresolved evidence references fail that level. Missing source/model evidence or malformed model output is held as unknown. All three levels must pass; no majority vote is permitted.

### Local model configuration

The verifier uses only a local GGUF/open-weight model through llama-server's OpenAI-compatible chat-completions protocol. The default model path is the primary 4B episode model. Select another local file or an already-running loopback endpoint with:

    --decision-verifier-model-path artifacts/models/your-local-4b-heretic.gguf
    --decision-verifier-server-binary llama-server
    --decision-verifier-port 8089
    --decision-verifier-gpu-layers -1

Or point at a local server:

    --decision-verifier-endpoint http://127.0.0.1:8089/v1/chat/completions
    --decision-verifier-model-name local-open-model

The path option starts a local llama-server for the verification request and shuts it down afterward. The endpoint option connects only to localhost or an IP loopback address. Remote hosts, HTTP redirects and environment-configured proxies are blocked by the verifier. It uses Python standard-library HTTP/process support and makes no GPT, Gemini, moderation API or hosted inference calls. Model weights are not downloaded by the verifier; make the selected local model file available first.

### Dual gate and artifacts

The first local pass never substitutes for PM verification. Even when all three local levels pass, admission remains held pending the PM's independent inspection of the source material and proposed DecisionEpisode. The PM gate must explicitly return PASS before a record can be marked eligible for the training dataset. Failing or unknown verdicts remain held.

The run writes:

- decision-source-evidence.json: timestamped extraction inputs supplied to the verifier.
- decision-verification.json: three local verdicts, reasons, evidence references, unknowns and model/backend metadata.
- training-admission.json: fail-closed admission state; local PASS alone is still pending PM.
- decision-episode.json: proposed record for audit/review, not an automatically approved training example.

The verifier currently receives structured timestamped extraction evidence rather than raw image pixels. Therefore its extraction-fidelity check audits the episode against those extracted observations; it is not a substitute for the PM's independent inspection of the original video. The current video-file pipeline has no automatic training-dataset writer, and this stage does not create or approve a dataset entry.

## Real tutorial source used by the CI demo

The downloader tries the three user-supplied YouTube IDs first. If YouTube denies runner access, it records each failure and downloads the real Wikipedia Content Translation Tool Tutorial (2 min 8 s) from Wikimedia Commons with its published English SRT captions. The video is by AlexandraShagzhina and is licensed CC BY-SA 4.0. The fallback attribution and licence are written to \`source-manifest.json\`. This is a real browser-tool tutorial file, not a synthetic fixture.


## Downstream learning pipeline after extraction

This document describes PR #38's file-based extraction and PR #39's local verifier. The complete repository learning sequence continues through the separately implemented downstream milestones:

1. **PR #38 — extract and validate:** download the tutorial video file; process supplied subtitles or local ASR; decode and select changed frames; run OCR, cursor inference, and local GUI grounding; align narration; assemble a structured DecisionEpisode; validate it against the schema and semantic contract.
2. **PR #39 — local verifier gate:** evaluate extraction fidelity, decision validity, and outcome validity with a local open-weight verifier. Every level must pass. A video-only temporal sequence is UNKNOWN for causal outcome validity. The verifier consumes timestamped structured extraction evidence, not raw image pixels, so it does not replace independent PM inspection of the original video.
3. **Independent PM review — admission prerequisite:** local PASS leaves the episode held pending an evidence-linked PM PASS against the source and proposed episode. The extractor does not perform or bypass this independent review.
4. **PR #40 — training-sample compiler:** compile only episodes that have local verification PASS, independent PM PASS, approved review, eligible annotation state, and quality/trainable approval. It creates one decision-time conversational sample per decision point, source-grouped train/test partitions, a manifest, and separate training metadata sidecars. The assistant target excludes future Hands execution outcomes.
5. **PR #41 — Brain LoRA setup:** prepare metadata-aware training/held-out datasets and validate the Qwen3 4B Axolotl/T4 FP16 LoRA configuration. This is training setup only. PR #41 did not execute an actual training run or produce adapter weights; an eligible real corpus, provisioned compute, and recorded training run remain required.
6. **PR #42 — Brain+Hands closed loop:** provide typed business-level delegation and Hands result contracts, fresh observation and independent postcondition verification, recovery/replanning, a deterministic WorkflowBrain stand-in, SimulatedHands, and a BrowserAgentHandsAdapter bridge. The CI acceptance uses the deterministic Brain and simulated Hands. No trained Brain adapter or real UI-TARS-class operation model was run.

The intended conceptual chain is therefore:

`downloaded video file` → `subtitle/ASR + frame-change-driven evidence extraction` → `DecisionEpisode + contract validation (#38)` → `local verifier (#39)` → `independent PM evidence review` → `training-sample compiler (#40)` → `Brain LoRA dataset/configuration (#41)` → `Brain+Hands closed-loop harness (#42)`.

The milestones are separate components and harnesses, not yet one deployed end-to-end production service. In particular, PR #38's current pipeline invokes the local verifier after episode validation and writes a proposed episode/admission report; it does not automatically create or approve training samples. PR #40 is the separate compiler, PR #41 is a training setup rather than a completed training run, and PR #42's CI is a simulated Brain/Hands acceptance path rather than a real-model run.

## Superseded live tutorial recorder route

The earlier proposed live-recorder/event-collector route (rrweb for web tutorials and Windows UI Automation for desktop tutorials) was **cancelled on 2026-11-21** and superseded by downloaded-video-file extraction. It was cancelled because the chosen learning path operates on available tutorial files and does not require installing and synchronizing a recorder inside each live application/session. Preserve the proposal as historical design context only; it is not an active primary route or a required fallback.
