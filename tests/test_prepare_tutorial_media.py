import hashlib

import pytest

from scripts import prepare_tutorial_media


def test_verify_pinned_media_accepts_matching_file(tmp_path, monkeypatch):
    media = tmp_path / "tutorial.webm"
    media.write_bytes(b"verified test bytes")
    digest = hashlib.sha1(media.read_bytes()).hexdigest()
    monkeypatch.setattr(prepare_tutorial_media, "EXPECTED_SIZE", media.stat().st_size)
    monkeypatch.setattr(prepare_tutorial_media, "EXPECTED_SHA1", digest)

    result = prepare_tutorial_media.verify_pinned_media(media)

    assert result["bytes"] == len(b"verified test bytes")
    assert result["sha1"] == digest
    assert result["sha256"] == hashlib.sha256(b"verified test bytes").hexdigest()


def test_verify_pinned_media_rejects_wrong_size(tmp_path, monkeypatch):
    media = tmp_path / "tutorial.webm"
    media.write_bytes(b"wrong")
    monkeypatch.setattr(prepare_tutorial_media, "EXPECTED_SIZE", 99)

    with pytest.raises(ValueError, match="Unexpected media size"):
        prepare_tutorial_media.verify_pinned_media(media)


def test_verify_pinned_media_rejects_wrong_hash(tmp_path, monkeypatch):
    media = tmp_path / "tutorial.webm"
    media.write_bytes(b"same size")
    monkeypatch.setattr(prepare_tutorial_media, "EXPECTED_SIZE", media.stat().st_size)
    monkeypatch.setattr(prepare_tutorial_media, "EXPECTED_SHA1", "0" * 40)

    with pytest.raises(ValueError, match="SHA-1"):
        prepare_tutorial_media.verify_pinned_media(media)
