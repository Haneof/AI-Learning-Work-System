"""Command-line entry point."""

from __future__ import annotations

import argparse

from aios_work_system.benchmark import BenchmarkRunner, MockBackend, ModelDescriptor
from aios_work_system.benchmark.runner import load_jsonl, write_jsonl, write_markdown_report
from aios_work_system.health import serve


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aios", description="AI Learning & Work System")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser("serve", help="start the local health endpoint")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)

    benchmark_parser = subparsers.add_parser(
        "benchmark", help="run the model benchmark dataset"
    )
    benchmark_parser.add_argument("--dataset", required=True)
    benchmark_parser.add_argument("--output-jsonl", default="artifacts/benchmark/results.jsonl")
    benchmark_parser.add_argument("--output-report", default="artifacts/benchmark/report.md")
    benchmark_parser.add_argument("--model-id", default="mock/local")
    benchmark_parser.add_argument("--revision", default="unknown")
    benchmark_parser.add_argument("--quantization", default="unknown")
    benchmark_parser.add_argument("--context-length", type=int)
    benchmark_parser.add_argument("--temperature", type=float, default=0.0)
    benchmark_parser.add_argument("--top-p", type=float, default=1.0)
    benchmark_parser.add_argument("--max-tokens", type=int, default=512)
    benchmark_parser.add_argument("--gpu", default="unknown")
    benchmark_parser.add_argument("--vram-gb", default="unknown")
    benchmark_parser.add_argument("--ram-gb", default="unknown")

    demo_parser = subparsers.add_parser(
        "phase0-demo",
        help="run the deterministic Phase 0 source-to-skill integration fixture",
    )
    demo_parser.add_argument("--output-dir", default="artifacts/phase0-demo")
    return parser


def _run_benchmark(args: argparse.Namespace) -> None:
    cases = load_jsonl(args.dataset)
    model = ModelDescriptor(
        model_id=args.model_id,
        revision=args.revision,
        backend="mock",
        quantization=args.quantization,
        context_length=args.context_length,
        generation_parameters={
            "temperature": args.temperature,
            "top_p": args.top_p,
            "max_tokens": args.max_tokens,
        },
        hardware={
            "gpu": args.gpu,
            "vram_gb": args.vram_gb,
            "ram_gb": args.ram_gb,
        },
    )
    results = BenchmarkRunner(MockBackend(), model).run(cases)
    write_jsonl(results, args.output_jsonl)
    write_markdown_report(results, args.output_report)
    passed = sum(result.passed for result in results)
    print(f"Benchmark complete: {passed}/{len(results)} passed")
    print(f"JSONL: {args.output_jsonl}")
    print(f"Report: {args.output_report}")


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "serve":
        serve(host=args.host, port=args.port)
    elif args.command == "benchmark":
        _run_benchmark(args)
    elif args.command == "phase0-demo":
        from aios_work_system.phase0 import run_phase0_demo

        report = run_phase0_demo(args.output_dir)
        print(f"Phase 0 demo: {report['overall_status']}")
        print(f"Report: {args.output_dir}/phase0-report.md")
        if report["overall_status"] != "PASS":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
