"""Run the real multimodal GUI agent against the repository's local fixture."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIRECTORY = REPOSITORY_ROOT / "tests" / "fixtures" / "gui"
DEFAULT_TRACE_PATH = REPOSITORY_ROOT / "artifacts" / "gui-real-model-demo.jsonl"
OBJECTIVE = (
    "On this local test page only, enter Ada in the Name field, click Save, "
    "and stop after the status shows Saved: Ada."
)


class _QuietFixtureHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return


async def _run_demo(model: OpenAICompatibleDecisionModel, trace_path: Path):
    from aios_work_system.gui.agent import BrowserAgent
    from aios_work_system.gui.real_model import (
        OpenAICompatibleDecisionModel,
    )

    try:
        from playwright.async_api import async_playwright
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Playwright is not installed. Install the GUI extra and its Chromium browser."
        ) from exc
    if not FIXTURE_DIRECTORY.is_dir():
        raise RuntimeError("the repository GUI fixture directory is missing")

    handler = partial(_QuietFixtureHandler, directory=str(FIXTURE_DIRECTORY))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"

    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            try:
                page = await browser.new_page()
                await page.goto(origin + "/index.html", wait_until="domcontentloaded")
                report = await BrowserAgent(
                    page,
                    model,
                    str(trace_path),
                ).run(OBJECTIVE)
                return report
            finally:
                await browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--trace",
        type=Path,
        default=DEFAULT_TRACE_PATH,
        help="output path for the gui-trace-v1 JSONL trace",
    )
    args = parser.parse_args()

    try:
        from aios_work_system.gui.real_model import (
            ModelConfigurationError,
            OpenAICompatibleDecisionModel,
        )

        model = OpenAICompatibleDecisionModel.from_env()
    except ModelConfigurationError as exc:
        print(f"Model configuration error: {exc}", file=sys.stderr)
        print("No fake-model fallback was used; no model request was sent.", file=sys.stderr)
        return 2

    try:
        report = asyncio.run(_run_demo(model, args.trace))
    except Exception as exc:
        print(f"GUI demo failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    print("Trace schema: gui-trace-v1")
    print(f"Trace file: {report.trace_path}")
    return 0 if report.status == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
