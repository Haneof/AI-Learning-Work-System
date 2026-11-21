# Video Acquisition Pipeline MVP

## Scope

The acquisition package provides the first YouTube path:

1. Search with the yt-dlp expression \`ytsearchN:<keyword>\`.
2. Normalize results into \`VideoCandidate\` records (URL, platform, uploader, title,
   duration, series/playlist, license metadata).
3. Select videos through the \`VideoSelector\` contract. The MVP ships a deterministic
   title/series/duration/license selector; a model-backed selector can implement the
   same interface later without changing the pipeline.
4. Download a selected item with yt-dlp, preferring MP4 video/audio up to 720p.
5. Upload it through the real Google Drive v3 API to
   \`AI-Learning/<platform>/<uploader>/<series-or-未分组>/<filename>\`.
6. Delete the downloader staging copy, download a fresh working copy from Drive,
   verify SHA-256, call the evidence-extractor interface, and delete the Drive working
   copy in a \`finally\` block. File absence is checked after deletion.
7. Persist one current record per video in \`artifacts/acquisition/records.jsonl\`.

Bilibili has a platform adapter extension point but no search implementation in this
MVP. Do not treat a placeholder as a working \`bilisearch\` endpoint. Implement a
Bilibili API-backed search adapter that returns the common \`VideoCandidate\` shape.

## Install

~~~powershell
python -m pip install -e ".[acquisition,dev]"
yt-dlp --version
ffmpeg -version
ffprobe -version
~~~

The \`acquisition\` extra declares yt-dlp and the official Google Drive API/OAuth client
libraries. They are optional so importing the base package does not fail on machines
that have not enabled acquisition. The first actual YouTube search or download raises
an actionable install error if yt-dlp is missing.

## Search and selection

~~~python
from aios_work_system.acquisition import (
    RuleBasedVideoSelector,
    SelectionCriteria,
    YouTubePlatformAdapter,
)

platform = YouTubePlatformAdapter()
videos = platform.search("Blender beginner workflow", max_results=20)
selected = RuleBasedVideoSelector().select(
    videos,
    SelectionCriteria(
        title_keywords=("blender", "beginner"),
        max_duration_seconds=20 * 60,
        allowed_license_terms=("creative commons", "cc by"),
        allow_unknown_license=False,
        limit=1,
    ),
)
~~~

The selector is a deterministic stub, not a language model. A future LLM selector must
implement the same \`VideoSelector.select(candidates, criteria)\` interface and return
the selected candidates; it must not rewrite source metadata or infer missing license
information.

A search result is not proof of reuse permission. If the platform metadata does not
include a license, the record stores \`unknown\`. License metadata is not promoted to
\`verified\` without an authoritative source. The sample below has a separately
documented Wikimedia Commons CC BY 3.0 listing.

A quick search command is also available:

~~~powershell
python scripts/search_youtube.py "Blender 3.4 tutorial" --max-results 20
~~~

It prints normalized candidate metadata as JSON and does not download anything.

## End-to-end orchestration API

The full \`AcquisitionPipeline\` accepts four replaceable components: platform,
selector, Drive storage, and evidence extractor. The production storage path is
\`GoogleDriveStorage.from_environment()\`, which uses the official Drive API client.
Tests inject a fake transport at the HTTP boundary; they do not replace the production
Google Drive implementation.

The reusable extractor adapter is \`PR26VideoLearningAdapter\`. It lazily imports
\`aios_work_system.video_learning.VideoLearningPipeline\`; it does not copy the
media-processing implementation. PR #26 must be merged to main before this adapter
can run. The adapter also requires concrete ASR/OCR adapters implementing the existing
media Protocols. If PR #26 is not yet present, extraction fails clearly after the
Drive archive is safely retained and the local working copy is cleaned up.

~~~python
from aios_work_system.acquisition import (
    AcquisitionPipeline,
    GoogleDriveStorage,
    JsonlRecordStore,
    PR26VideoLearningAdapter,
    RuleBasedVideoSelector,
    SelectionCriteria,
    YouTubePlatformAdapter,
)

# Supply ASR/OCR adapter instances that implement the existing media Protocols.
evidence_extractor = PR26VideoLearningAdapter(
    asr_adapter=your_asr_adapter,
    ocr_adapter=your_ocr_adapter,
)
pipeline = AcquisitionPipeline(
    platform=YouTubePlatformAdapter(),
    selector=RuleBasedVideoSelector(),
    drive=GoogleDriveStorage.from_environment(),
    evidence_extractor=evidence_extractor,
    record_store=JsonlRecordStore("artifacts/acquisition/records.jsonl"),
)
candidates, records = pipeline.run_search(
    "Blender 3.4 tutorial",
    SelectionCriteria(
        title_keywords=("blender",),
        max_duration_seconds=20 * 60,
        limit=1,
    ),
)
~~~

The Drive round-trip is deliberate: the extractor receives only the file freshly
downloaded from Drive, not the original yt-dlp staging file. A SHA-256 mismatch stops
extraction. The Drive archive is not deleted. Both local copies are removed and checked
for absence; extracted evidence JSON and JSONL metadata are kept locally.

## Record and course grouping

Each JSONL row contains the video URL, platform, uploader, title, duration, series,
license/source/verification state, discovery/download times, SHA-256, Drive file ID,
Drive link, Drive path, upload status, extraction status, local deletion status, and
evidence path. Updates replace the current row by \`record_id\`; this MVP is not a
transactional database.

Videos are grouped by uploader and series. If no series or playlist metadata is
provided, the folder component is exactly \`未分组\`. The evidence provenance carries
both uploader and series, so a set of videos from one creator/course can later be
treated as a course-level learning unit.

## Reference sample

- YouTube URL: https://www.youtube.com/watch?v=0zaG13Do12Q
- Title: Blender 3.4 New Features in LESS than 5 minutes
- YouTube channel: Blender (@blenderofficial)
- Attribution: Blender Foundation and SouthernShotty (Commons attribution record)
- Duration: 3 minutes 29 seconds
- Series: unknown; store under \`未分组\`
- License: Creative Commons Attribution 3.0 Unported (CC BY 3.0), as listed by
  Wikimedia Commons. Retain attribution and the license link; identify any changes.
- Commons source page:
  https://commons.wikimedia.org/wiki/File:Blender_3.4_New_Features_in_LESS_than_5_minutes.webm

For an actual acquisition, the YouTube metadata returned by yt-dlp is saved as
observed. The Commons reference above is independent license evidence, not a reason to
hard-code a license string for other videos. If the live result cannot confirm a
license, its record remains \`unknown\`.

## CI and limits

- Unit tests fake the yt-dlp boundary and inject an in-memory Drive transport.
- CI has no Google OAuth credentials and does not attempt a real Drive upload.
- The production Google Drive implementation uses the official API and OAuth flow;
  see [GOOGLE_DRIVE_SETUP.md](GOOGLE_DRIVE_SETUP.md) for one-time authorization.
- PR #26 is intentionally not vendored into this branch. Once it is merged, wire
  concrete ASR/OCR adapters into \`PR26VideoLearningAdapter\`.
- Current chunking, transcription/OCR quality, semantic course organization, and
  persistent database storage remain separate acceptance items.
