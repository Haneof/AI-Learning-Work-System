"""Tests for source registration, PDF page mapping, FFmpeg, and task resume."""

import json

import pytest

from aios_work_system.media.ffmpeg import FFmpegProcessor, NoAudioStreamError
from aios_work_system.media.pdf import extract_pdf_pages
from aios_work_system.media.source import SegmentRecord, register_source
from aios_work_system.media.tasks import MediaTaskError, TaskJournal


class FakePage:
    def __init__(self, text):
        self.text = text

    def extract_text(self):
        return self.text


class FakeReader:
    def __init__(self, _path):
        self.pages = [FakePage("Page one"), FakePage(""), FakePage("Page three")]


def test_source_registration_hashes_original_and_manifest_is_traceable(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("original content", encoding="utf-8")

    manifest = register_source(source, "document")
    segment = SegmentRecord.create(
        source_id=manifest.source_id,
        segment_type="PARAGRAPH",
        locator={"page": 1, "paragraph": 1},
        parser_name="test",
        parser_version="1",
        text_content="original content",
    )
    manifest.add_segment(segment)
    output = tmp_path / "manifest.json"
    manifest.save(output)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["sha256"] == manifest.sha256
    assert payload["segments"][0]["locator"]["page"] == 1
    assert source.read_text(encoding="utf-8") == "original content"


def test_pdf_extraction_keeps_page_numbers_and_empty_pages(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-fake")

    segments = extract_pdf_pages(
        pdf_path,
        source_id="source-1",
        reader_factory=FakeReader,
    )

    assert [item.locator["page"] for item in segments] == [1, 2, 3]
    assert segments[1].text_content == ""


def test_ffmpeg_probe_parses_stream_metadata(tmp_path, monkeypatch):
    media_path = tmp_path / "sample.mp4"
    media_path.write_bytes(b"placeholder")
    processor = FFmpegProcessor()
    monkeypatch.setattr(
        processor,
        "_run",
        lambda _command: json.dumps({"streams": [{"codec_type": "video"}]}),
    )

    result = processor.probe(media_path)

    assert result["streams"][0]["codec_type"] == "video"


def test_audio_extraction_rejects_video_without_audio(tmp_path, monkeypatch):
    media_path = tmp_path / "silent.mp4"
    media_path.write_bytes(b"placeholder")
    processor = FFmpegProcessor()
    monkeypatch.setattr(
        processor,
        "probe",
        lambda _source: {"streams": [{"codec_type": "video"}]},
    )

    with pytest.raises(NoAudioStreamError):
        processor.extract_audio(media_path, tmp_path / "audio.wav")


def test_task_journal_retries_and_skips_completed_work(tmp_path):
    journal_path = tmp_path / "task-journal.json"
    journal = TaskJournal(journal_path)
    calls = 0

    def flaky_action():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ValueError("temporary failure")
        return "artifact-ready"

    result = journal.run("stable-task-id", "extract_audio", flaky_action, max_attempts=2)

    assert result == "artifact-ready"
    assert calls == 2
    assert journal.records["stable-task-id"].state == "SUCCEEDED"
    assert journal.records["stable-task-id"].attempts == 2

    resumed = TaskJournal(journal_path)
    assert resumed.run("stable-task-id", "extract_audio", flaky_action, max_attempts=2) is None
    assert calls == 2


def test_task_journal_resumes_an_interrupted_final_attempt(tmp_path):
    journal_path = tmp_path / "interrupted-task.json"
    journal_path.write_text(
        json.dumps(
            {
                "interrupted": {
                    "task_id": "interrupted",
                    "operation": "extract_frames",
                    "state": "RUNNING",
                    "attempts": 2,
                    "max_attempts": 2,
                }
            }
        ),
        encoding="utf-8",
    )
    journal = TaskJournal(journal_path)

    assert journal.run("interrupted", "extract_frames", lambda: "done", max_attempts=2) == "done"
    assert journal.records["interrupted"].attempts == 2
    assert journal.records["interrupted"].state == "SUCCEEDED"


def test_task_journal_persists_exhausted_failure(tmp_path):
    journal = TaskJournal(tmp_path / "failed-task.json")

    def fail():
        raise RuntimeError("broken media")

    with pytest.raises(MediaTaskError):
        journal.run("broken-source", "probe", fail, max_attempts=1)

    assert journal.records["broken-source"].state == "FAILED"
    assert journal.records["broken-source"].error == "RuntimeError: broken media"
