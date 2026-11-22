# Legacy Software Tutorial Benchmark: Content Translation Screencast

## Purpose

This openly licensed tutorial is retained as a **legacy MP4 reconstruction sample**. It has no synchronized rrweb or Windows UI Automation event log. It can therefore help evaluate whether a limited set of historical UI events and decision context can be reconstructed from a recording and narration, but it cannot provide direct-capture event ground truth.

This sample is not the primary training-input design and is not a Qwen3-VL/Mage-VL model-selection benchmark. Any reconstructed interaction from the recording must be labelled inferred_from_video. Instructor words must be aligned to the audio/subtitle source and kept separate from behavioral inference.

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

1. Preserve the original WebM, source hash, attribution, and subtitle files.
2. Use the existing subtitle text first; align it to the audio where the source timing is uncertain.
3. Inspect the recording only as needed to reconstruct page/navigation/control state changes.
4. Create inferred_from_video event candidates with start/end time and the visual state that supports the reconstruction.
5. Link instructor-explicit narration to the corresponding Decision Episode. Keep any purpose inferred from the behavior separately labelled behavioral_inference.
6. Leave hidden clicks, key presses, and ambiguous outcomes unknown.
7. Have PM verify the reconstructed episodes against the licensed original source before considering them for a legacy-data training sample.

## Existing CI processing is only a component smoke test

The current content-translation-tutorial job downloads the original WebM and Chinese subtitles, probes streams, extracts audio and sampled frames, runs CPU faster-whisper on English narration, and runs Tesseract OCR on UI frames. Artifacts are retained for 14 days.

This demonstrates that media and subtitle/OCR components execute. It does not prove semantic workflow reconstruction, direct UI event capture, Brain decision learning, or Brain-to-Hands competence. Its sampled-frame/OCR processing is a legacy media component test; it is not the selected primary tutorial-learning route.

## Historical Qwen/Mage experiment

The Qwen3-VL-4B vs Mage-VL-4B blind test on Colab T4 was stopped on 2026-11-21 at approximately 19:51 PST after Qwen3-VL-4B scored 4.0/25. The test was not completed as a validated winner-selection benchmark. No winner is recorded. The primary learning design is semantic UI event streams aligned with instructor narration.

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

This sample is short and dates from 2015. It is a legacy reconstruction fixture, not a representative modern enterprise tutorial corpus. The spoken audio is English; the Chinese subtitle file is a separately aligned reference, not Chinese speech. Direct event capture cannot be retroactively recovered from this MP4. Expand validation with new tutorials recorded with rrweb/Windows UIA and synchronized narration before claiming direct event-capture quality or large-scale generalization.
