# Legacy Software Tutorial Benchmark: Content Translation Screencast

## Purpose

This openly licensed tutorial is a **downloaded video-file extraction sample**. It has no synchronized native DOM, rrweb, Windows UI Automation, mouse, or keyboard event log. It can therefore be processed by the selected file-based pipeline to recover timestamped visible state changes and narration, but any cursor/click/target hypotheses inferred from the pixels must remain labelled inferred_from_video.

This sample is compatible with the primary training-input design: downloaded tutorial files are processed offline by programs rather than captured through a live recorder. It is not a Qwen3-VL/Mage-VL model-selection benchmark. Visible screen-change/OCR observations must be linked to source timestamps; inferred interactions must be labelled inferred_from_video. Instructor words must be aligned to the audio/subtitle source and kept separate from behavioral inference.

A successful reconstruction should identify the business task, decision points, likely operation sequence, visible before/after UI state, narration-based reasons, result evidence, and uncertainty. It must not invent hidden clicks or keyboard events.

## Source and license

- Title: Content Translation Screencast (English)
- Creator: Pau Giner (Wikimedia Foundation)
- Date: 2015-01-13
- Duration: 4 min 16 sec
- Resolution: 1280x720
- Video: https://commons.wikimedia.org/wiki/File:Content_Translation_Screencast_(English).webm
- License: CC BY-SA 4.0
- Attribution: Pau Giner; identify any changes; adaptations must comply with CC BY-SA 4.0.
- Simplified Chinese timed text: https://commons.wikimedia.org/wiki/TimedText:Content_Translation_Screencast_(English).webm.zh-cn.srt
- English timed text: https://commons.wikimedia.org/wiki/TimedText:Content_Translation_Screencast_(English).webm.en.srt

## Expected procedural outline (PM reference labels)

| Approx. time | Expected operation | Evidence to inspect |
|---|---|---|
| 00:11-00:31 | Open Beta settings; enable Content Translation; save | narration and visible settings state |
| 00:46-01:01 | Open Contributions; choose Translation; reach dashboard | narration and navigation change |
| 01:03-01:13 | Choose source/target languages and source article | narration and selected values |
| 01:15-01:28 | Identify the three-column editor and each column's purpose | narration and editor state |
| 01:30-01:54 | Add paragraphs; review initial machine translation | narration and visible content changes |
| 01:57-02:14 | Compare corresponding source sentence and links | narration and highlighted source content |
| 02:28-02:45 | Review, revise, discard, or use source paragraph as a template | narration and editing changes |
| 02:46-03:01 | Create links; defer advanced styling | narration and visible result |
| 03:02-03:23 | Review categories and autosaved draft; resume from dashboard | narration and dashboard state |
| 03:24-03:31 | Publish translation | narration and visible publish result |

These are PM reference landmarks, not verified event records. During reconstruction, cite the relevant recording time and narration. If the input event cannot be established, preserve the operation as inferred or unknown rather than calling it an observed click.

## Reconstruction protocol for this legacy sample

1. Preserve the original WebM, source hash, attribution, and timed subtitle files.
2. Run the downloaded-file extractor: use timed subtitles first, local ASR only if usable subtitle cues are unavailable, and align narration to the detected visual changes.
3. Decode sampled frames, select initial/changed frames by screen-change detection, OCR the visible UI, and run local cursor/UI-target inference on the selected frames.
4. Link every visual claim and possible action to source timestamps and extracted evidence. Use inferred_from_video for cursor/click/target hypotheses; do not invent native event telemetry.
5. Link instructor-explicit narration to the corresponding DecisionEpisode and keep any purpose inferred from behavior separately labelled behavioral_inference.
6. Leave hidden clicks, key presses, and ambiguous outcomes unknown. Do not claim actual execution or a verified business outcome without independent evidence.
7. Validate the episode contract, run the local verifier, then require independent PM review before training admission.

## Existing CI processing is only a component smoke test

The current content-translation-tutorial job downloads the original WebM and Chinese subtitles, probes streams, extracts audio and sampled frames, runs CPU faster-whisper on English narration, and runs Tesseract OCR on UI frames. Artifacts are retained for 14 days.

This demonstrates that media and subtitle/OCR components execute on a downloaded video file. It does not exercise the complete PR #38 frame-change-driven pipeline, cursor/click inference, local UI grounding, DecisionEpisode synthesis/validation, local verifier, compiler, LoRA training, or Brain-to-Hands competence. Its sampled-frame/OCR processing is a simplified component smoke test; the dedicated video-file pipeline is the selected primary route.

## Historical Qwen/Mage experiment

The Qwen3-VL-4B vs Mage-VL-4B blind test on Colab T4 was stopped on 2026-11-21 at approximately 19:51 PST after Qwen3-VL-4B scored 4.0/25. The test was not completed as a validated winner-selection benchmark. No winner is recorded. This model experiment did not reject frame extraction; the primary learning design is downloaded-video-file processing with frame-change-driven visual extraction aligned to instructor narration.

## Evidence and quality requirements

A benchmark/reconstruction report should preserve:
- source URL, platform, SHA-256, license/attribution, and source version;
- subtitle/audio and alignment method;
- time-linked reconstructed event candidates and visible pre/post state;
- relevant narration segments and whether each reason was instructor-explicit or inferred;
- direct/inferred/unknown observation labels;
- unsupported, missing, or conflicting claims;
- review decisions and exclusion reasons.

Passing requires a coherent, evidence-grounded Decision Episode and workflow representation. Subtitle generation, OCR output, or a fluent generic summary alone is never a pass.

## Limitations

This sample is short and dates from 2015. It is a legacy reconstruction fixture, not a representative modern enterprise tutorial corpus. The spoken audio is English; the Chinese subtitle file is a separately aligned reference, not Chinese speech. Native DOM/UIA/mouse/keyboard event telemetry cannot be retroactively recovered from this MP4. Expand validation across more downloaded tutorial files, software versions, visual conditions, languages, and tasks before claiming extraction quality or large-scale generalization.
