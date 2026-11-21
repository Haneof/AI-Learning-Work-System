"""CLI contract tests for the discovery command."""

import argparse
import json

from aios_work_system.acquisition import CandidateRepository, CandidateStatus, ResourceCandidate
from aios_work_system.cli import (
    _run_discovery_review,
    _run_discovery_select,
    build_parser,
)


def test_discover_search_cli_requires_keyword_and_accepts_platform_options():
    parser = build_parser()
    args = parser.parse_args(
        [
            "discover-search",
            "--platform",
            "bilibili",
            "--keyword",
            "python tutorial",
            "--page",
            "2",
            "--page-size",
            "10",
        ]
    )

    assert args.command == "discover-search"
    assert args.platform == "bilibili"
    assert args.keyword == "python tutorial"
    assert args.page == 2
    assert args.page_size == 10
    assert args.database.endswith("candidates.sqlite3")



def test_discovery_review_and_select_commands_parse_expected_options():
    parser = build_parser()
    review = parser.parse_args(
        [
            "discover-review",
            "--batch-id",
            "batch-123",
            "--status",
            "DISCOVERED",
            "--limit",
            "8",
        ]
    )
    select = parser.parse_args(
        ["discover-select", "--candidate-id", "candidate-123"]
    )

    assert review.command == "discover-review"
    assert review.batch_id == "batch-123"
    assert review.status == "DISCOVERED"
    assert review.limit == 8
    assert select.command == "discover-select"
    assert select.candidate_id == "candidate-123"


def test_discovery_download_cli_parses_engine_and_storage_paths():
    parser = build_parser()
    args = parser.parse_args(
        [
            "discover-download",
            "--candidate-id",
            "candidate-123",
            "--engine",
            "aria2",
            "--destination",
            "media/downloads",
        ]
    )

    assert args.command == "discover-download"
    assert args.candidate_id == "candidate-123"
    assert args.engine == "aria2"
    assert args.destination == "media/downloads"
    assert args.max_concurrent_jobs == 2


def test_select_command_updates_candidate_state_idempotently(tmp_path, capsys):
    repository = CandidateRepository(tmp_path / "candidates.sqlite3")
    candidate = ResourceCandidate(
        platform="bilibili",
        url="https://www.bilibili.com/video/BV1select",
        title="Selectable tutorial",
        candidate_id="candidate-select",
    )
    repository.save_candidates("batch-select", [candidate])
    args = argparse.Namespace(
        candidate_id=candidate.candidate_id,
        database=str(tmp_path / "candidates.sqlite3"),
    )

    _run_discovery_select(args)
    first_payload = json.loads(capsys.readouterr().out)
    _run_discovery_select(args)
    second_payload = json.loads(capsys.readouterr().out)

    assert first_payload["status"] == CandidateStatus.SELECTED.value
    assert second_payload["status"] == CandidateStatus.SELECTED.value
    assert repository.get(candidate.candidate_id)[1] == CandidateStatus.SELECTED


def test_review_command_lists_candidate_ids_and_status(tmp_path, capsys):
    repository = CandidateRepository(tmp_path / "candidates.sqlite3")
    candidate = ResourceCandidate(
        platform="bilibili",
        url="https://www.bilibili.com/video/BV1review",
        title="Review this tutorial",
        candidate_id="candidate-review",
    )
    repository.save_candidates("batch-review", [candidate])
    args = argparse.Namespace(
        database=str(tmp_path / "candidates.sqlite3"),
        batch_id="batch-review",
        status=None,
        limit=20,
    )

    _run_discovery_review(args)
    payload = json.loads(capsys.readouterr().out)

    assert payload["candidate_count"] == 1
    assert payload["candidates"][0]["candidate_id"] == candidate.candidate_id
    assert payload["candidates"][0]["status"] == CandidateStatus.DISCOVERED.value
