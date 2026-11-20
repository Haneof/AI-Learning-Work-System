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
