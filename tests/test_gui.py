"""Real Chromium tests for local GUI trace recording, replay, and agent control."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Awaitable, Callable
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from playwright.async_api import async_playwright

from aios_work_system.gui.agent import AgentConfig, BrowserAgent
from aios_work_system.gui.browser import (
    LocalBrowserOnlyError,
    observe_page,
    verify_expectation,
)
from aios_work_system.gui.contracts import GuiAction
from aios_work_system.gui.trace import (
    BrowserEventCapture,
    JsonlTraceRecorder,
    ReplayVerificationError,
    TraceReplayer,
    load_trace,
)


def run_in_local_browser(
    scenario: Callable[[Any, str], Awaitable[None]],
) -> None:
    async def run() -> None:
        fixture_dir = Path(__file__).parent / "fixtures" / "gui"
        handler = partial(SimpleHTTPRequestHandler, directory=str(fixture_dir))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        origin = f"http://127.0.0.1:{server.server_port}"
        try:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                try:
                    page = await browser.new_page()
                    await page.goto(f"{origin}/index.html")
                    await scenario(page, origin)
                finally:
                    await browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    asyncio.run(run())


def text_action(
    action: str,
    target: str,
    selector: str,
    value: str,
    expectation_kind: str,
    expectation_selector: str,
    expectation_value: str,
) -> dict[str, Any]:
    return {
        "action": action,
        "target": target,
        "selector": selector,
        "value": value,
        "expected_result": {
            "kind": expectation_kind,
            "selector": expectation_selector,
            "value": expectation_value,
        },
    }


class FakeModel:
    def __init__(self, decisions: list[dict[str, Any]]) -> None:
        self.decisions = list(decisions)
        self.requests: list[dict[str, Any]] = []

    async def decide(self, request: Any) -> dict[str, Any]:
        self.requests.append(dict(request))
        if not self.decisions:
            raise AssertionError("fake model has no remaining decisions")
        return self.decisions.pop(0)


def test_trace_captures_visual_semantic_and_input_events_and_replays(
    tmp_path: Path,
) -> None:
    async def scenario(page: Any, origin: str) -> None:
        path = tmp_path / "recording.jsonl"
        capture = BrowserEventCapture()
        await capture.attach(page)
        recorder = JsonlTraceRecorder(path, "save the name Ada", origin)

        before = await observe_page(page)
        cursor = capture.cursor()
        await page.locator("#name").click()
        await page.keyboard.type("Ada")
        after = await observe_page(page)
        type_action = GuiAction.from_mapping(
            text_action(
                "type",
                "the Name input",
                "#name",
                "Ada",
                "value_equals",
                "#name",
                "Ada",
            )
        )
        type_verification = await verify_expectation(page, type_action.expected_result)
        assert type_verification["passed"] is True
        recorder.record_step(
            before=before,
            after=after,
            action=type_action,
            events=capture.since(cursor),
            verification=type_verification,
        )

        before = after
        cursor = capture.cursor()
        await page.locator("#save").click()
        after = await observe_page(page)
        click_action = GuiAction.from_mapping(
            {
                "action": "click",
                "target": "the Save button",
                "selector": "#save",
                "expected_result": {
                    "kind": "text_contains",
                    "selector": "#status",
                    "value": "Saved: Ada",
                },
            }
        )
        click_verification = await verify_expectation(page, click_action.expected_result)
        assert click_verification["passed"] is True
        recorder.record_step(
            before=before,
            after=after,
            action=click_action,
            events=capture.since(cursor),
            verification=click_verification,
        )

        header, rows = load_trace(path)
        assert header["schema_version"] == "gui-trace-v1"
        assert len(rows) == 2
        assert rows[0]["before"]["screenshot_b64"]
        assert rows[0]["after"]["screenshot_b64"]
        assert "input" in rows[0]["before"]["dom_snapshot"]
        assert "Name" in rows[0]["before"]["accessibility_snapshot"]
        recorded_events = [event["event_type"] for row in rows for event in row["events"]]
        assert "keydown" in recorded_events
        assert "click" in recorded_events
        assert rows[0]["training_example"]["output"]["action"] == "type"

        await page.goto(f"{origin}/index.html")
        report = await TraceReplayer(path).replay(page)
        assert report.verified is True
        assert report.steps_replayed == 2
        assert await page.locator("#status").inner_text() == "Saved: Ada"

    run_in_local_browser(scenario)


def test_replay_stops_at_first_verification_mismatch(tmp_path: Path) -> None:
    async def scenario(page: Any, origin: str) -> None:
        path = tmp_path / "mismatch.jsonl"
        recorder = JsonlTraceRecorder(path, "enter Ada then save", origin)
        before = await observe_page(page)
        await page.locator("#name").fill("Ada")
        after = await observe_page(page)
        first = GuiAction.from_mapping(
            text_action(
                "type",
                "the Name input",
                "#name",
                "Ada",
                "text_contains",
                "#status",
                "not present",
            )
        )
        recorder.record_step(
            before=before,
            after=after,
            action=first,
            events=[],
            verification={"passed": False, "observed": "Idle"},
        )
        second = GuiAction.from_mapping(
            {
                "action": "click",
                "target": "the Save button",
                "selector": "#save",
                "expected_result": {
                    "kind": "text_contains",
                    "selector": "#status",
                    "value": "Saved: Ada",
                },
            }
        )
        recorder.record_step(
            before=after,
            after=after,
            action=second,
            events=[],
            verification={"passed": True},
        )

        await page.goto(f"{origin}/index.html")
        with pytest.raises(ReplayVerificationError) as raised:
            await TraceReplayer(path).replay(page)
        assert raised.value.step_number == 1
        assert await page.locator("#status").inner_text() == "Idle"

    run_in_local_browser(scenario)


def test_agent_runs_type_click_done_with_fake_model(tmp_path: Path) -> None:
    async def scenario(page: Any, _origin: str) -> None:
        model = FakeModel(
            [
                text_action(
                    "type",
                    "the Name input",
                    "#name",
                    "Ada",
                    "value_equals",
                    "#name",
                    "Ada",
                ),
                {
                    "action": "click",
                    "target": "the Save button",
                    "selector": "#save",
                    "expected_result": {
                        "kind": "text_contains",
                        "selector": "#status",
                        "value": "Saved: Ada",
                    },
                },
                {"action": "done", "target": "the requested name was saved"},
            ]
        )
        report = await BrowserAgent(page, model, str(tmp_path / "agent.jsonl")).run(
            "save the name Ada"
        )
        assert report.status == "done"
        assert report.steps == 2
        assert report.corrections == 0
        assert await page.locator("#status").inner_text() == "Saved: Ada"
        _header, rows = load_trace(tmp_path / "agent.jsonl")
        assert len(rows) == 3

    run_in_local_browser(scenario)


def test_agent_requests_exactly_one_correction_after_failed_verification(
    tmp_path: Path,
) -> None:
    async def scenario(page: Any, _origin: str) -> None:
        model = FakeModel(
            [
                {
                    "action": "click",
                    "target": "the Save button",
                    "selector": "#save",
                    "expected_result": {
                        "kind": "text_contains",
                        "selector": "#status",
                        "value": "this will not appear",
                    },
                },
                {
                    "action": "wait",
                    "target": "the status update",
                    "timeout_ms": 10,
                    "expected_result": {
                        "kind": "text_contains",
                        "selector": "#status",
                        "value": "Missing name",
                    },
                },
                {"action": "done", "target": "the missing-name state was observed"},
            ]
        )
        report = await BrowserAgent(page, model, str(tmp_path / "correction.jsonl")).run(
            "press Save and verify the empty-name state"
        )
        assert report.status == "done"
        assert report.corrections == 1
        assert len(model.requests) == 3
        assert model.requests[1]["correction"] is True
        assert model.requests[1]["last_failure"]["passed"] is False

    run_in_local_browser(scenario)


def test_agent_stops_when_the_single_correction_also_fails(tmp_path: Path) -> None:
    async def scenario(page: Any, _origin: str) -> None:
        model = FakeModel(
            [
                {
                    "action": "click",
                    "target": "the Save button",
                    "selector": "#save",
                    "expected_result": {
                        "kind": "text_contains",
                        "selector": "#status",
                        "value": "wrong first expectation",
                    },
                },
                {
                    "action": "wait",
                    "target": "the status update",
                    "timeout_ms": 10,
                    "expected_result": {
                        "kind": "text_contains",
                        "selector": "#status",
                        "value": "wrong second expectation",
                    },
                },
            ]
        )
        report = await BrowserAgent(page, model, str(tmp_path / "failed.jsonl")).run("press Save")
        assert report.status == "failed"
        assert report.steps == 2
        assert report.corrections == 1
        assert len(model.requests) == 2

    run_in_local_browser(scenario)


def test_agent_stops_on_model_timeout(tmp_path: Path) -> None:
    class SlowModel:
        async def decide(self, _request: Any) -> dict[str, Any]:
            await asyncio.sleep(0.1)
            return {"action": "done", "target": "too late"}

    async def scenario(page: Any, _origin: str) -> None:
        report = await BrowserAgent(
            page,
            SlowModel(),
            str(tmp_path / "timeout.jsonl"),
            AgentConfig(model_timeout_s=0.01),
        ).run("finish")
        assert report.status == "timed_out"
        assert report.error == "model decision timed out"

    run_in_local_browser(scenario)


def test_non_local_origins_are_rejected() -> None:
    with pytest.raises(LocalBrowserOnlyError):
        from aios_work_system.gui.browser import local_origin

        local_origin("https://example.com")
