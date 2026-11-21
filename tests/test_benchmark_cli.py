"""CLI argument contract tests."""

from aios_work_system.cli import build_parser


def test_benchmark_cli_records_comparison_parameters():
    args = build_parser().parse_args(
        [
            "benchmark",
            "--dataset",
            "tests/fixtures/benchmark_smoke.jsonl",
            "--model-id",
            "local/qwen-candidate",
            "--revision",
            "abc123",
            "--quantization",
            "q4",
            "--context-length",
            "4096",
            "--temperature",
            "0.1",
            "--top-p",
            "0.9",
            "--max-tokens",
            "256",
            "--gpu",
            "NVIDIA GPU",
            "--vram-gb",
            "8",
            "--ram-gb",
            "16",
        ]
    )

    assert args.command == "benchmark"
    assert args.model_id == "local/qwen-candidate"
    assert args.revision == "abc123"
    assert args.context_length == 4096
    assert args.temperature == 0.1
    assert args.top_p == 0.9
    assert args.max_tokens == 256
    assert args.vram_gb == "8"


def test_cli_keeps_mock_as_the_default_backend():
    args = build_parser().parse_args(
        ["benchmark", "--dataset", "tests/fixtures/benchmark_smoke.jsonl"]
    )

    assert args.backend == "mock"


def test_cli_selects_llama_server_and_records_model_metadata(monkeypatch, tmp_path):
    import json
    import sys

    from aios_work_system import cli
    from aios_work_system.benchmark import MockBackend

    constructor_args = {}

    def backend_factory(**kwargs):
        constructor_args.update(kwargs)
        return MockBackend()

    monkeypatch.setattr(cli, "LlamaServerBackend", backend_factory)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "aios",
            "benchmark",
            "--dataset",
            "tests/fixtures/benchmark_smoke.jsonl",
            "--backend",
            "llama-server",
            "--model-size",
            "9B",
            "--context-length",
            "4096",
            "--max-tokens",
            "64",
            "--output-jsonl",
            str(tmp_path / "results.jsonl"),
            "--output-report",
            str(tmp_path / "report.md"),
        ],
    )

    cli.main()

    assert constructor_args["base_url"] == "http://127.0.0.1:8080/v1"
    assert constructor_args["model_id"] == "Qwen3.5-9B"
    assert constructor_args["timeout"] == 300.0
    assert constructor_args["generation_parameters"] == {
        "temperature": 0.0,
        "top_p": 1.0,
        "max_tokens": 64,
    }

    records = [
        json.loads(line)
        for line in (tmp_path / "results.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(records) == 5
    assert records[0]["model"]["backend"] == "llama-server"
    assert records[0]["model"]["model_id"] == "Qwen3.5-9B"
    assert records[0]["model"]["context_length"] == 4096
