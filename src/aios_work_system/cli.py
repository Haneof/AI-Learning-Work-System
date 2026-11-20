"""Command-line entry point."""

from __future__ import annotations

import argparse

from aios_work_system.health import serve


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aios", description="AI Learning & Work System")
    subparsers = parser.add_subparsers(dest="command", required=True)
    serve_parser = subparsers.add_parser("serve", help="start the local health endpoint")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "serve":
        serve(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
