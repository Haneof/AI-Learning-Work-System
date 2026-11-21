"""Tests for media asset persistence, integrity checks, and source provenance."""

import hashlib
import json

import pytest

from aios_work_system.media.assets import MediaAssetRepository
from aios_work_system.media.download_jobs import DownloadJobRepository


def _job(repository, candidate_id):
    return repository.create(
        candidate_id=candidate_id,
        source_url=f"https://example.com/{candidate_id}/lesson.mp4",
        engine="yt-dlp",
        destination="/tmp/downloads",
    )


def test_asset_registry_persists_manifest_and_download_provenance(tmp_path):
    jobs = DownloadJobRepository(tmp_path / "jobs.sqlite3")
    job = _job(jobs, "candidate-a")
    payload = b"verified tutorial video bytes"
    output = tmp_path / "lesson.mp4"
    output.write_bytes(payload)

    assets = MediaAssetRepository(
        tmp_path / "assets.sqlite3",
        tmp_path / "manifests",
    )
    digest = hashlib.sha256(payload).hexdigest()
    asset_id = assets.register_download(job, output, digest, len(payload))

    asset = assets.get(asset_id)
    manifest = json.loads(
        (tmp_path / "manifests" / f"{asset_id}.json").read_text(encoding="utf-8")
    )
    sources = assets.list_sources(asset_id)

    assert asset.asset_id == asset_id
    assert asset.sha256 == digest
    assert asset.size_bytes == len(payload)
    assert asset.storage_uri == output.resolve().as_uri()
    assert manifest["sha256"] == digest
    assert manifest["acquisition"]["candidate_id"] == "candidate-a"
    assert manifest["acquisition"]["job_id"] == job.job_id
    assert sources[0]["source_url"] == job.source_url


def test_duplicate_content_reuses_asset_but_retains_each_source(tmp_path):
    jobs = DownloadJobRepository(tmp_path / "jobs.sqlite3")
    first_job = _job(jobs, "candidate-a")
    second_job = _job(jobs, "candidate-b")
    payload = b"the same bytes from two source pages"
    output = tmp_path / "same.mp4"
    output.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    assets = MediaAssetRepository(
        tmp_path / "assets.sqlite3",
        tmp_path / "manifests",
    )

    first_id = assets.register_download(first_job, output, digest, len(payload))
    second_id = assets.register_download(second_job, output, digest, len(payload))

    assert second_id == first_id
    assert len(assets.list()) == 1
    assert {source["candidate_id"] for source in assets.list_sources(first_id)} == {
        "candidate-a",
        "candidate-b",
    }


@pytest.mark.parametrize(
    ("expected_sha256", "expected_size_bytes", "message"),
    [
        ("0" * 64, 4, "SHA-256"),
        ("a" * 64, 5, "size"),
        ("not-a-hash", 4, "64-character"),
    ],
)
def test_asset_registry_rejects_unverified_file_metadata(
    tmp_path, expected_sha256, expected_size_bytes, message
):
    jobs = DownloadJobRepository(tmp_path / "jobs.sqlite3")
    job = _job(jobs, "candidate-a")
    output = tmp_path / "lesson.mp4"
    output.write_bytes(b"data")
    assets = MediaAssetRepository(
        tmp_path / "assets.sqlite3",
        tmp_path / "manifests",
    )

    with pytest.raises(ValueError, match=message):
        assets.register_download(job, output, expected_sha256, expected_size_bytes)

    assert assets.list() == []
