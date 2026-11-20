"""Tests for benchmark dataset loading, scoring, and JSONL output."""

import json

from aios_work_system.benchmark import BenchmarkRunner, MockBackend, ModelDescriptor
from aios_work_system.benchmark.runner import load_jsonl, write_jsonl, write_markdown_report
from aios_work_system.benchmark.scoring import score_output


def test_smoke_dataset_runs_and_writes_reports(tmp_path):
    dataset = load_jsonl("tests/fixtures/benchmark_smoke.jsonl")
    runner = BenchmarkRunner(
        backend=MockBackend(),
        model=ModelDescriptor(
            model_id="mock/qwen35-candidate",
            revision="not-configured",
            backend="mock",
            quantization="unknown",
            hardware={"gpu": "unknown", "vram_gb": "unknown", "ram_gb": "unknown"},
        ),
    )

    results = runner.run(dataset)

    assert len(results) == 5
    assert all(result.passed for result in results)
    assert all(result.time_to_first_token_ms is None for result in results)
    assert all(result.resource_metrics["vram_peak_bytes"] is None for result in results)

    jsonl_path = tmp_path / "results.jsonl"
    report_path = tmp_path / "report.md"
    write_jsonl(results, jsonl_path)
    write_markdown_report(results, report_path)

    records = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 5
    assert records[0]["model"]["model_id"] == "mock/qwen35-candidate"
    assert "Interpretation limits" in report_path.read_text(encoding="utf-8")


def test_invalid_json_is_scored_as_failure():
    assert score_output("not json", {"valid_json_object": True}) == {
        "valid_json_object": False
    }
