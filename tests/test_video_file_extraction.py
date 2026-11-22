"""Unit and local-file integration tests for downloaded-video extraction."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from contracts.validate import validate_episode
from aios_work_system.video_extraction.episode import (
    align_transcript_to_events,
    build_decision_episode,
)
from aios_work_system.video_extraction.transcript import (
    parse_subtitle_file,
    timestamp_to_ms,
)


def test_timestamp_parser_accepts_srt_and_vtt_clock_formats():
    assert timestamp_to_ms("00:01:02,345") == 62_345
    assert timestamp_to_ms("01:02.500") == 62_500


def test_parse_subtitles_keeps_timestamped_words_and_removes_vtt_markup(tmp_path: Path):
    subtitle = tmp_path / "tutorial.en.vtt"
    subtitle.write_text(
        "WEBVTT\n\n"
        "00:00:01.000 --> 00:00:02.500 align:start\n"
        "<c.colorE5E5E5>Click</c> the Start button\n\n"
        "00:00:03.000 --> 00:00:04.000\n"
        "Choose Settings\n",
        encoding="utf-8",
    )
    segments = parse_subtitle_file(subtitle)
    assert len(segments) == 2
    assert segments[0]["start_ms"] == 1000
    assert segments[0]["end_ms"] == 2500
    assert segments[0]["text"] == "Click the Start button"
    assert segments[1]["transcript_method"] == "subtitle"


def test_timeline_alignment_attaches_only_events_inside_the_time_window():
    segments = [
        {"segment_id": "n1", "start_ms": 1000, "end_ms": 1600, "text": "Click Start"},
        {"segment_id": "n2", "start_ms": 5000, "end_ms": 5500, "text": "Open Settings"},
    ]
    events = [
        {"event_id": "f1", "timestamp_ms": 1800},
        {"event_id": "f2", "timestamp_ms": 8500},
    ]
    aligned = align_transcript_to_events(segments, events, window_ms=500)
    assert aligned["alignment"][0]["matched_event_ids"] == ["f1"]
    assert aligned["alignment"][1]["matched_event_ids"] == []


def _episode_fixture(video_path: Path) -> dict:
    return build_decision_episode(
        video_path=video_path,
        video_metadata={
            "video_id": "unit-video",
            "duration_ms": 5000,
            "extractor": "unit-test",
        },
        transcript=[
            {
                "segment_id": "n1",
                "start_ms": 1000,
                "end_ms": 1800,
                "text": "I select the Start button.",
                "transcript_method": "subtitle",
                "speaker_role": "unknown",
            }
        ],
        frames=[
            {
                "frame_index": 0,
                "timestamp_ms": 0,
                "is_initial": True,
                "is_change": False,
            },
            {"frame_index": 4, "timestamp_ms": 2000, "is_change": True},
        ],
        ocr_records=[
            {
                "timestamp_ms": 2000,
                "text": "Start Settings",
                "regions": [{"text": "Start"}, {"text": "Settings"}],
            }
        ],
        cursor_events=[
            {
                "event_id": "click-0001",
                "timestamp_ms": 2000,
                "confidence": 0.3,
            }
        ],
        vlm_results=[
            {
                "status": "completed",
                "timestamp_ms": 2000,
                "likely_action": "click",
                "visible_ui_element": "Start button",
                "confidence": 0.42,
            }
        ],
        alignment={"alignment": []},
    )


def test_decision_episode_uses_distinct_observed_inferred_and_narration_labels(tmp_path: Path):
    video = tmp_path / "source.mp4"
    video.write_bytes(b"video placeholder")
    episode = _episode_fixture(video)
    assert validate_episode(episode) == []
    labels = {item["evidence_id"]: item.get("labels", []) for item in episode["evidence"]}
    channels = {
        item["evidence_id"]: item["observation_channel"]
        for item in episode["evidence"]
    }
    assert labels["ev-observed-video"] == ["observed_from_video"]
    assert labels["ev-inferred-actions"] == ["inferred_from_video"]
    assert labels["ev-instructor-words"] == ["instructor_words"]
    assert channels["ev-observed-video"] == "observed_from_video"
    assert channels["ev-inferred-actions"] == "inferred_from_video"
    assert episode["task"]["business_constraints"] == []
    assert episode["outcome"]["status"] == "not_verified"
    assert episode["operation"]["execution_status"] == "not_observed"


def test_decision_episode_without_grounding_leaves_action_unknown_and_still_valid(tmp_path: Path):
    video = tmp_path / "source.mp4"
    video.write_bytes(b"video placeholder")
    episode = build_decision_episode(
        video_path=video,
        video_metadata={"video_id": "unknown-case", "duration_ms": 1000},
        transcript=[],
        frames=[{"frame_index": 0, "timestamp_ms": 0, "is_initial": True, "is_change": False}],
        ocr_records=[],
        cursor_events=[],
        vlm_results=[],
        alignment={"alignment": []},
    )
    assert validate_episode(episode) == []
    assert episode["decision"]["decision_basis"] == ["unknown"]
    assert episode["operation"]["event_refs"] == []
    assert [item["evidence_id"] for item in episode["evidence"]] == ["ev-observed-video"]


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("tesseract"),
    reason="FFmpeg and Tesseract are required for the local video-file integration test",
)
def test_pipeline_runs_on_a_real_video_file_and_emits_contract_valid_episode(tmp_path: Path):
    from aios_work_system.video_extraction.pipeline import VideoExtractionPipeline

    video = tmp_path / "sample.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=white:s=640x360:d=2:r=4",
            "-vf",
            "drawbox=x=0:y=0:w=iw:h=ih/2:color=black:t=fill:enable='between(t,1,2)'",
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(video),
        ],
        check=True,
        capture_output=True,
    )
    captions = tmp_path / "sample.en.srt"
    captions.write_text(
        "1\n00:00:00,300 --> 00:00:01,700\nI open the Start menu.\n",
        encoding="utf-8",
    )
    pipeline = VideoExtractionPipeline(sample_fps=2.0, vlm_model=None)
    result = pipeline.run(video, tmp_path / "output", captions_path=captions)
    assert result["validation"]["valid"] is True
    assert validate_episode(result["episode"]) == []
    assert result["summary"]["counts"]["sampled_frames"] >= 2
    assert result["summary"]["part_breakdown"]["subtitle_asr"]["method"] == "existing_subtitles"
    assert result["summary"]["part_breakdown"]["frame_change"]["changed_frames"] >= 1
    assert result["summary"]["part_breakdown"]["ocr"]["frames_processed"] >= 1
