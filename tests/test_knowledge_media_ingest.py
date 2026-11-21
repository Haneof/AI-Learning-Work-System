"""Media analysis output is indexed as expert-scoped, typed source evidence."""

from aios_work_system.knowledge import KnowledgeRepository, index_media_analysis
from aios_work_system.media.adapters import OCRSegment, TranscriptSegment
from aios_work_system.media.analysis import (
    AnalysisArtifact,
    AnalysisStatus,
    MediaAnalysisResult,
)


def _result():
    return MediaAnalysisResult(
        run_id="analysis-run-1",
        asset_id="asset-ingest-1",
        source_sha256="a" * 64,
        config_hash="b" * 64,
        status=AnalysisStatus.COMPLETED,
        attempts=1,
        duration_seconds=12.0,
        artifacts=(
            AnalysisArtifact(
                artifact_key="audio",
                kind="AUDIO",
                path="/derived/audio.wav",
                sha256="c" * 64,
                size_bytes=1024,
                metadata={},
            ),
            AnalysisArtifact(
                artifact_key="frame:000000",
                kind="FRAME",
                path="/derived/frame_000000.jpg",
                sha256="d" * 64,
                size_bytes=256,
                metadata={"timestamp_ms": 0, "interval_seconds": 5.0},
            ),
            AnalysisArtifact(
                artifact_key="frame:000001",
                kind="FRAME",
                path="/derived/frame_000001.jpg",
                sha256="e" * 64,
                size_bytes=256,
                metadata={"timestamp_ms": 5000, "interval_seconds": 5.0},
            ),
        ),
        transcripts=(
            TranscriptSegment(1000, 2000, "Select the account tab."),
        ),
        ocr_segments=(
            OCRSegment(5000, "Account settings", [10, 20, 120, 60], 0.95),
        ),
        warnings=(),
        error=None,
    )


def test_media_analysis_is_indexed_by_modality_and_timestamp(tmp_path):
    repository = KnowledgeRepository(tmp_path / "knowledge.sqlite3")
    indexed = index_media_analysis(
        repository,
        _result(),
        expert_id="expert-office",
    )

    assert [item.modality for item in indexed] == [
        "asr",
        "ocr",
        "video_frame",
        "video_frame",
    ]
    asr = indexed[0]
    assert asr.locator == {"start_ms": 1000, "end_ms": 2000}
    assert asr.artifact_ref == "/derived/audio.wav"
    assert indexed[1].locator == {"timestamp_ms": 5000}
    assert indexed[2].artifact_ref == "/derived/frame_000000.jpg"
    assert "require human review" in indexed[2].text_content

    reopened = KnowledgeRepository(tmp_path / "knowledge.sqlite3")
    restored = reopened.get_segment(indexed[2].segment_id, "expert-office")
    assert restored.modality == "video_frame"
    assert restored.locator == {"timestamp_ms": 0}


def test_media_evidence_index_is_idempotent_for_same_analysis(tmp_path):
    repository = KnowledgeRepository(tmp_path / "knowledge.sqlite3")
    first = index_media_analysis(repository, _result(), expert_id="expert-office")
    second = index_media_analysis(repository, _result(), expert_id="expert-office")

    assert [segment.segment_id for segment in first] == [
        segment.segment_id for segment in second
    ]
    assert len(repository.list_segments("expert-office")) == 4


def test_same_asset_evidence_is_isolated_between_expert_workspaces(tmp_path):
    repository = KnowledgeRepository(tmp_path / "knowledge.sqlite3")
    indexed = index_media_analysis(repository, _result(), expert_id="expert-a")

    try:
        repository.get_segment(indexed[0].segment_id, "expert-b")
    except PermissionError:
        pass
    else:
        raise AssertionError("cross-expert source evidence access must be denied")
