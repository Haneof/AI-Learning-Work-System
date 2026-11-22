# Software Tutorial Benchmark: Content Translation Screencast

## Purpose

This openly licensed tutorial is a reference sample for testing whether a video-understanding model can reconstruct a software workflow from visual and audio evidence. It is not simply a subtitle/OCR benchmark, and the reference outline below is not a pre-approved generated trajectory.

A successful understanding result must identify actions, intent, UI state before/after each action, visible result, time range, and supporting frames/audio. It must separate directly visible or logged events from inferred actions and explanations.

## Source and license

- Title: Content Translation Screencast (English)
- Creator: Pau Giner (Wikimedia Foundation)
- Date: 2015-01-13
- Duration: 4 min 16 sec
- Resolution: 1280x720
- Video: https://commons.wikimedia.org/wiki/File:Content_Translation_Screencast_(English).webm
- License: CC BY-SA 4.0
- Attribution: Pau Giner; changes, if any, must be identified; adaptations must comply with CC BY-SA 4.0.
- Simplified Chinese timed text: https://commons.wikimedia.org/wiki/TimedText:Content_Translation_Screencast_(English).webm.zh-cn.srt
- English timed text: https://commons.wikimedia.org/wiki/TimedText:Content_Translation_Screencast_(English).webm.en.srt

## Expected procedural outline (PM reference labels)

| Approx. time | Expected operation | Evidence |
|---|---|---|
| 00:11-00:31 | Open Beta settings; enable Content Translation; save | narration + settings UI |
| 00:46-01:01 | Open Contributions; choose Translation; reach dashboard | narration + navigation UI |
| 01:03-01:13 | Choose source/target languages and source article | narration + language/article selection |
| 01:15-01:28 | Identify three-column editor and its roles | narration + editor layout |
| 01:30-01:54 | Add paragraphs; review initial machine translation | narration + editor interaction |
| 01:57-02:14 | Compare corresponding source sentence and links | narration + highlighted source |
| 02:28-02:45 | Review, revise, discard or use source paragraph as template | narration + editing UI |
| 02:46-03:01 | Create links; defer advanced styling | narration + editor UI |
| 03:02-03:23 | Categories, autosaved draft, resume from dashboard | narration + dashboard |
| 03:24-03:31 | Publish translation | narration + publish action |

These labels provide expected task landmarks only. During evaluation, the model must cite the actual frame/audio evidence and may identify an action as uncertain or inferred when the screencast does not show the input event unambiguously.

## Model-role evaluation

### Video understanding: Qwen3-VL and Mage-VL

Give each candidate the same video intervals and context. Score whether it accurately explains:
- what action occurred and the purpose of the step;
- which UI elements and states were visible;
- what changed after the action;
- whether the expected result occurred;
- what the narration explicitly said versus what the model inferred;
- the time interval and evidence supporting each claim.

These candidates produce text understanding and are tested against the same blind rubric. The current Colab T4 comparison is ongoing; this sample alone does not identify a winner.

### Action grounding: Magma

Evaluate target-region and click-point predictions independently. A predicted point is not automatically a recorded historical click. Score target hit, coordinate error, timing, and uncertainty separately from semantic understanding.

## Existing CI processing is only a component smoke test

The current `content-translation-tutorial` job downloads the original WebM and Chinese subtitles, probes streams, extracts audio and sampled frames, runs CPU faster-whisper on English narration, and runs Tesseract OCR on UI frames. Artifacts are retained for 14 days.

This demonstrates that media and subtitle/OCR components execute. It does not prove semantic operation reconstruction, intent understanding, action grounding, or knowledge validation. The presence of a subtitle file is a pre-filter input/benchmark reference, not the final extracted knowledge.

## Quality and evidence requirements

A benchmark report should preserve:
- source URL, platform, SHA-256, license/attribution, and video version;
- model/revision and generation settings;
- per-step start/end time and supporting frame/audio references;
- action, target, pre/post UI state, and outcome;
- explicit observed/inferred/unknown labels;
- incorrect, missing, or unsupported claims;
- independent GPT review and PM Sangou verification decisions.

Passing requires a correct, evidence-grounded trajectory and explanation. Subtitle generation or OCR output alone is never a pass.

## Limitations

This sample is short and dates from 2015. It is a first procedural-understanding benchmark, not a representative long-course or modern enterprise-software benchmark. The spoken audio is English; the Chinese subtitle file is a separately aligned reference, not Chinese speech. Expand the evaluation corpus with multiple creators, software versions, layouts, languages, and tutorial lengths before selecting a model or asserting large-scale quality.
