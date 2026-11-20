# Software Tutorial Benchmark: Content Translation Screencast

## Why this sample

This is a real software-operation screencast, not a language-learning clip or a static product demo. It shows a user enabling Wikipedia's Content Translation beta feature, opening the translation dashboard, selecting source/target languages and an article, editing paragraph translations, reviewing links and formatting, saving a draft, resuming work, and publishing.

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

## Expected procedural outline (reference labels)

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

## CI processing

The `content-translation-tutorial` job downloads the original WebM and Chinese subtitles, probes streams, extracts audio and sampled frames, runs CPU faster-whisper on the English narration, and runs Tesseract OCR on UI frames. Artifacts are retained for 14 days.

## What this does and does not prove

A passing job proves that the media can be downloaded and processed and that ASR/OCR return outputs. It does **not** prove that a model has reconstructed the procedure, learned a reusable skill, or completed the task. Those require a separate evidence-linked step extraction evaluation and a controlled task replay against a live or locally reproducible target application.

This sample is short and dates from 2015. It is a first procedural-learning benchmark, not a representative long-course or modern enterprise-software benchmark. The spoken audio is English; the Chinese subtitle file is a separate aligned reference, not Chinese speech.
