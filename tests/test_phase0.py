"""End-to-end contract integration tests for the Phase 0 fixture pipeline."""

import json

from aios_work_system.phase0 import run_phase0_demo


def test_phase0_demo_connects_source_knowledge_skill_and_safety_gates(tmp_path):
    report = run_phase0_demo(tmp_path / "phase0")

    assert report["overall_status"] == "PASS"
    assert all(report["checks"].values())
    assert report["source"]["sha256"]
    assert report["evidence"]["segment_id"]
    assert report["knowledge"]["state"] == "APPROVED"
    assert report["skill"]["package_hash"]
    assert len(report["skill"]["git_commit"]) == 40
    assert report["skill"]["sandbox_execution"] == "NOT_EXECUTED"

    json_report = json.loads(
        (tmp_path / "phase0" / "phase0-report.json").read_text(encoding="utf-8")
    )
    markdown_report = (tmp_path / "phase0" / "phase0-report.md").read_text(encoding="utf-8")
    assert json_report["source"]["sha256"] == report["source"]["sha256"]
    assert "NOT EXECUTED" in markdown_report
    assert "approved knowledge without evidence is rejected" in markdown_report


def test_phase0_demo_refuses_to_overwrite_nonempty_output(tmp_path):
    output = tmp_path / "not-empty"
    output.mkdir()
    (output / "user-file.txt").write_text("keep", encoding="utf-8")

    try:
        run_phase0_demo(output)
    except ValueError as exc:
        assert "must be empty" in str(exc)
    else:
        raise AssertionError("Expected non-empty output directory to be rejected")
    assert (output / "user-file.txt").read_text(encoding="utf-8") == "keep"


def test_phase0_demo_reports_invalid_output_paths_clearly(tmp_path):
    output_file = tmp_path / "not-a-directory"
    output_file.write_text("keep", encoding="utf-8")

    try:
        run_phase0_demo(output_file)
    except ValueError as exc:
        assert "Output path must be a directory" in str(exc)
    else:
        raise AssertionError("Expected a file output path to be rejected")

    try:
        run_phase0_demo(output_file / "child")
    except ValueError as exc:
        assert "Cannot create Phase 0 output directory" in str(exc)
    else:
        raise AssertionError("Expected a non-directory parent to be rejected")
    assert output_file.read_text(encoding="utf-8") == "keep"
