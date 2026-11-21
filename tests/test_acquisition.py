"""Tests for YouTube acquisition, Drive archive, JSONL records and local cleanup."""

import importlib
import json
from pathlib import Path

import pytest

from aios_work_system.acquisition.drive import (
    DriveConfigurationError,
    DriveFileInfo,
    GoogleDriveStorage,
)
from aios_work_system.acquisition.evidence import EvidenceExtractionContext
from aios_work_system.acquisition.models import SelectionCriteria, VideoCandidate
from aios_work_system.acquisition.pipeline import AcquisitionPipeline
from aios_work_system.acquisition.platforms import (
    AcquisitionDependencyError,
    YouTubePlatformAdapter,
)
from aios_work_system.acquisition.records import JsonlRecordStore
from aios_work_system.acquisition.selector import RuleBasedVideoSelector


class FakeDriveTransport:
    def __init__(self):
        self.folders = {}
        self.files = {}
        self.next_id = 0

    def _id(self, prefix):
        self.next_id += 1
        return f"{prefix}-{self.next_id}"

    def find_folder(self, name, parent_id):
        return self.folders.get((parent_id, name))

    def create_folder(self, name, parent_id):
        folder_id = self._id("folder")
        self.folders[(parent_id, name)] = folder_id
        return folder_id

    def upload_file(self, path: Path, parent_id: str):
        file_id = self._id("file")
        self.files[file_id] = {
            "content": path.read_bytes(),
            "name": path.name,
            "parent_id": parent_id,
            "web_view_link": f"https://drive.google.com/file/d/{file_id}/view",
            "size_bytes": path.stat().st_size,
        }
        return DriveFileInfo(
            file_id=file_id,
            name=path.name,
            web_view_link=self.files[file_id]["web_view_link"],
            size_bytes=path.stat().st_size,
        )

    def download_file(self, file_id, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.files[file_id]["content"])


class FakePlatform:
    platform = "youtube"

    def __init__(self, candidate):
        self.candidate = candidate

    def search(self, query, max_results=20):
        assert query == "Blender tutorial"
        return [self.candidate]

    def download(self, candidate, output_dir):
        path = Path(output_dir) / f"{candidate.video_id}.mp4"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"licensed tutorial bytes")
        return path


class FakeEvidenceExtractor:
    def __init__(self, fail=False):
        self.fail = fail
        self.seen_path = None
        self.seen_context = None

    def extract(self, video_path, context: EvidenceExtractionContext):
        self.seen_path = video_path
        self.seen_context = context
        assert video_path.is_file()
        if self.fail:
            raise RuntimeError("extractor test failure")
        return {"records": [{"knowledge_id": "k-1", "provenance": {}}]}


def make_candidate(series=None):
    return VideoCandidate(
        video_id="0zaG13Do12Q",
        video_url="https://www.youtube.com/watch?v=0zaG13Do12Q",
        platform="youtube",
        uploader="Blender",
        title="Blender 3.4 New Features in LESS than 5 minutes",
        duration_seconds=209,
        series=series,
        license_info="CC BY 3.0",
        license_source="Wikimedia Commons",
        license_verification="listed_on_commons",
    )


def test_youtube_search_uses_ytsearch_prefix_and_normalizes_metadata():
    calls = {}

    class FakeYtDlp:
        def __init__(self, options):
            calls["options"] = options

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, query, download):
            calls["query"] = query
            calls["download"] = download
            return {
                "entries": [
                    {
                        "id": "abc123",
                        "title": "Blender tutorial",
                        "uploader": "Blender",
                        "duration": 180,
                        "playlist_title": "Blender Fundamentals",
                        "license": "Creative Commons Attribution license (reuse allowed)",
                    },
                    {
                        "id": "xyz987",
                        "title": "Another tutorial",
                        "channel": "Creator",
                    },
                ]
            }

    adapter = YouTubePlatformAdapter(ydl_factory=FakeYtDlp)
    results = adapter.search("Blender tutorial", max_results=7)

    assert calls["query"] == "ytsearch7:Blender tutorial"
    assert calls["download"] is False
    assert len(results) == 2
    assert results[0].video_url.endswith("v=abc123")
    assert results[0].uploader == "Blender"
    assert results[0].series == "Blender Fundamentals"
    assert "Creative Commons" in results[0].license_info
    assert results[1].license_info == "unknown"
    assert results[1].series is None


def test_missing_ytdlp_dependency_has_actionable_error(monkeypatch):
    def missing_module(_name):
        raise ImportError("not installed")

    monkeypatch.setattr(importlib, "import_module", missing_module)
    adapter = YouTubePlatformAdapter()

    with pytest.raises(AcquisitionDependencyError, match="yt-dlp.*Install it"):
        adapter.search("Blender")


def test_drive_auth_fails_clearly_without_oauth_client_file(monkeypatch):
    monkeypatch.delenv("GOOGLE_DRIVE_CREDENTIALS", raising=False)

    with pytest.raises(DriveConfigurationError, match="GOOGLE_DRIVE_CREDENTIALS"):
        GoogleDriveStorage.from_environment()


def test_rule_selector_filters_by_title_duration_and_series():
    candidates = [
        make_candidate(series="Blender Fundamentals"),
        VideoCandidate(
            video_id="long",
            video_url="https://www.youtube.com/watch?v=long",
            platform="youtube",
            uploader="Creator",
            title="Blender tutorial advanced",
            duration_seconds=1800,
            series="Blender Fundamentals",
        ),
        VideoCandidate(
            video_id="other",
            video_url="https://www.youtube.com/watch?v=other",
            platform="youtube",
            uploader="Creator",
            title="Blender tutorial basics",
            duration_seconds=100,
            series="Other course",
        ),
    ]
    result = RuleBasedVideoSelector().select(
        candidates,
        SelectionCriteria(
            title_keywords=("blender", "features"),
            series_keywords=("fundamentals",),
            max_duration_seconds=1200,
            limit=1,
        ),
    )
    assert result == [candidates[0]]


def test_selector_can_exclude_unlicensed_unknown_results():
    unknown = make_candidate(series=None)
    unknown = VideoCandidate(
        video_id=unknown.video_id,
        video_url=unknown.video_url,
        platform=unknown.platform,
        uploader=unknown.uploader,
        title=unknown.title,
        duration_seconds=unknown.duration_seconds,
        series=unknown.series,
        license_info="unknown",
    )
    assert (
        RuleBasedVideoSelector().select(
            [unknown],
            SelectionCriteria(title_keywords=("blender",), allow_unknown_license=False),
        )
        == []
    )


def test_drive_storage_uses_creator_and_series_folder_hierarchy(tmp_path):
    transport = FakeDriveTransport()
    storage = GoogleDriveStorage(transport)
    source = tmp_path / "video.mp4"
    source.write_bytes(b"video bytes")

    upload = storage.upload_video(source, make_candidate(series="Blender 3.4"))

    assert upload.drive_path.startswith("AI-Learning/youtube/Blender/Blender 3.4/")
    assert upload.drive_path.endswith("video.mp4")
    assert upload.file.file_id.startswith("file-")
    assert upload.file.web_view_link.endswith("/view")
    assert len(transport.folders) == 4


def test_drive_storage_uses_un_grouped_folder_when_series_missing(tmp_path):
    transport = FakeDriveTransport()
    storage = GoogleDriveStorage(transport)
    source = tmp_path / "video.mp4"
    source.write_bytes(b"video bytes")

    upload = storage.upload_video(source, make_candidate(series=None))

    assert upload.drive_path.startswith("AI-Learning/youtube/Blender/未分组/")


def test_end_to_end_archive_roundtrip_evidence_and_verified_local_deletion(tmp_path):
    candidate = make_candidate(series=None)
    transport = FakeDriveTransport()
    storage = GoogleDriveStorage(transport)
    extractor = FakeEvidenceExtractor()
    records_path = tmp_path / "artifacts" / "acquisition" / "records.jsonl"
    pipeline = AcquisitionPipeline(
        platform=FakePlatform(candidate),
        selector=RuleBasedVideoSelector(),
        drive=storage,
        evidence_extractor=extractor,
        record_store=JsonlRecordStore(records_path),
        staging_dir=tmp_path / "staging",
        work_dir=tmp_path / "work",
        evidence_dir=tmp_path / "evidence",
    )

    discovered, processed = pipeline.run_search(
        "Blender tutorial",
        SelectionCriteria(title_keywords=("blender",), max_duration_seconds=1200),
        max_results=10,
    )

    assert discovered == [candidate]
    assert len(processed) == 1
    record = processed[0]
    assert record.upload_status == "uploaded"
    assert record.extraction_status == "completed"
    assert record.deletion_status == "deleted"
    assert record.download_cache_deletion_status == "deleted"
    assert record.source_sha256
    assert record.drive_file_id in transport.files
    assert record.drive_link == transport.files[record.drive_file_id]["web_view_link"]
    assert record.drive_path.endswith("/未分组/0zaG13Do12Q.mp4")
    assert record.download_time is not None
    assert record.license_info == "CC BY 3.0"

    assert extractor.seen_path is not None
    assert not extractor.seen_path.exists()
    assert not list((tmp_path / "staging").glob("*.mp4"))
    assert not list((tmp_path / "work").rglob("*.mp4"))

    evidence = json.loads(Path(record.evidence_path).read_text(encoding="utf-8"))
    provenance = evidence["records"][0]["provenance"]
    assert provenance["uploader"] == "Blender"
    assert provenance["series"] == "unknown"
    assert provenance["drive_file_id"] == record.drive_file_id

    rows = JsonlRecordStore(records_path).list_records()
    assert len(rows) == 1
    assert rows[0]["video_url"] == candidate.video_url
    assert rows[0]["drive_file_id"] == record.drive_file_id


def test_working_copy_is_deleted_when_evidence_extraction_fails(tmp_path):
    candidate = make_candidate(series="Blender 3.4")
    transport = FakeDriveTransport()
    extractor = FakeEvidenceExtractor(fail=True)
    pipeline = AcquisitionPipeline(
        platform=FakePlatform(candidate),
        selector=RuleBasedVideoSelector(),
        drive=GoogleDriveStorage(transport),
        evidence_extractor=extractor,
        record_store=JsonlRecordStore(tmp_path / "records.jsonl"),
        staging_dir=tmp_path / "staging",
        work_dir=tmp_path / "work",
        evidence_dir=tmp_path / "evidence",
    )

    record = pipeline.process_one(candidate)

    assert record.upload_status == "uploaded"
    assert record.extraction_status == "failed"
    assert record.deletion_status == "deleted"
    assert record.download_cache_deletion_status == "deleted"
    assert "extractor test failure" in record.error
    assert not extractor.seen_path.exists()


def test_bilibili_search_is_an_explicit_extension_point():
    from aios_work_system.acquisition.platforms import BilibiliPlatformAdapter

    with pytest.raises(NotImplementedError, match="Bilibili search is not implemented"):
        BilibiliPlatformAdapter().search("Blender")
