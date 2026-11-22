"""CLI and browser-observer tests for the Brain/Hands end-to-end runner."""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Mapping
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any

import pytest

from aios_work_system.brain_hands.browser_adapter import BrowserAgentHandsAdapter
from aios_work_system.brain_hands.interfaces import OperationDelegation
from aios_work_system.brain_hands.woocommerce import woocommerce_product_state
from aios_work_system.cli import main

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPOSITORY_ROOT / "contracts" / "examples" / "shop-list-product.workflow.json"
GUI_FIXTURE_DIRECTORY = REPOSITORY_ROOT / "tests" / "fixtures" / "gui"
WOOCOMMERCE_FIXTURE = Path(__file__).parent / "fixtures" / "woocommerce-product-form.html"


def _write_inputs(path: Path) -> Path:
    payload = {
        "initial_state": {
            "photos.status": "complete",
            "title.status": "missing",
            "price.status": "not_set",
        },
        "workflow_inputs": {
            "product_title": "Portable Pet Water Fountain",
            "price": 39.99,
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _invoke_cli(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> int:
    monkeypatch.setattr(sys, "argv", ["aios", *argv])
    return main()


def test_simulated_run_loop_cli_writes_complete_report_and_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inputs_path = _write_inputs(tmp_path / "inputs.json")
    output_dir = tmp_path / "run"

    exit_code = _invoke_cli(
        monkeypatch,
        [
            "run-loop",
            "--workflow",
            str(WORKFLOW_PATH),
            "--inputs",
            str(inputs_path),
            "--hands",
            "simulated",
            "--output-dir",
            str(output_dir),
        ],
    )

    assert exit_code == 0
    report_path = output_dir / "report.json"
    history_path = output_dir / "history.jsonl"
    assert report_path.is_file()
    assert history_path.is_file()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "succeeded"
    assert report["goal_satisfied"] is True
    assert report["final_state"]["title.status"] == "verified"
    assert report["final_state"]["price.status"] == "set"
    assert report["decisions"] == 4
    assert report["operations"] == 3

    history_lines = history_path.read_text(encoding="utf-8").splitlines()
    # The loop history records delegated decisions; its terminal finish decision
    # increments decisions but intentionally does not create an operation-history entry.
    assert len(history_lines) == report["operations"]
    entries = [json.loads(line) for line in history_lines]
    assert all(isinstance(entry, dict) for entry in entries)
    assert [entry["delegation"]["task_id"] for entry in entries] == [
        "enter_title",
        "verify_title",
        "set_price",
    ]
    output = capsys.readouterr().out
    assert "run-loop: succeeded goal_satisfied=true decisions=4 operations=3" in output
    assert f"Report: {report_path}" in output


def test_invalid_workflow_capability_exits_two_without_writing_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workflow = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    next(task for task in workflow["tasks"] if task["task_id"] == "enter_title")[
        "capability_id"
    ] = "shop.listing.not_registered"
    workflow_path = tmp_path / "invalid.workflow.json"
    workflow_path.write_text(json.dumps(workflow), encoding="utf-8")
    output_dir = tmp_path / "invalid-run"

    exit_code = _invoke_cli(
        monkeypatch,
        [
            "run-loop",
            "--workflow",
            str(workflow_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert exit_code == 2
    error_output = capsys.readouterr().err
    assert "unregistered capability shop.listing.not_registered" in error_output
    assert not (output_dir / "report.json").exists()


def test_missing_workflow_is_an_argparse_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(SystemExit) as error:
        _invoke_cli(monkeypatch, ["run-loop"])
    assert error.value.code == 2


def test_max_decisions_returns_step_limit_and_exit_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inputs_path = _write_inputs(tmp_path / "inputs.json")
    output_dir = tmp_path / "limited-run"

    exit_code = _invoke_cli(
        monkeypatch,
        [
            "run-loop",
            "--workflow",
            str(WORKFLOW_PATH),
            "--inputs",
            str(inputs_path),
            "--max-decisions",
            "2",
            "--output-dir",
            str(output_dir),
        ],
    )

    assert exit_code == 1
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "step_limit"
    assert report["goal_satisfied"] is False
    assert report["decisions"] == 2
    assert report["operations"] == 2
    assert "run-loop: step_limit goal_satisfied=false decisions=2 operations=2" in (
        capsys.readouterr().out
    )


def test_unconfigured_browser_model_exits_two_without_fake_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for name in (
        "AIOS_GUI_MODEL_BASE_URL",
        "AIOS_GUI_MODEL_NAME",
        "AIOS_GUI_MODEL_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    output_dir = tmp_path / "browser-run"

    exit_code = _invoke_cli(
        monkeypatch,
        [
            "run-loop",
            "--workflow",
            str(WORKFLOW_PATH),
            "--hands",
            "browser",
            "--url",
            "http://localhost:8080/wp-admin/post-new.php?post_type=product",
            "--output-dir",
            str(output_dir),
        ],
    )

    assert exit_code == 2
    assert "Missing required model environment variables" in capsys.readouterr().err
    assert not (output_dir / "report.json").exists()


class _QuietFixtureHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return


class _DoneDecisionModel:
    def __init__(self) -> None:
        self.calls = 0

    async def decide(self, _request: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls += 1
        return {"action": "done", "target": "fixture is already in the expected state"}


def test_browser_hands_adapter_accepts_done_only_after_fresh_state_verification(
    tmp_path: Path,
) -> None:
    pytest.importorskip("playwright")
    from playwright.async_api import async_playwright

    handler = partial(_QuietFixtureHandler, directory=str(GUI_FIXTURE_DIRECTORY))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    model = _DoneDecisionModel()
    delegation = OperationDelegation(
        call_id="fixture:1:observe",
        task_id="observe_fixture",
        workflow_id="fixture.workflow",
        workflow_version="0.1",
        node_id="observe_fixture",
        description="Observe the local fixture and stop when its initial status is visible.",
        capability_id="fixture.observe",
        arguments={},
        preconditions=(),
        constraints={
            "must_not": ["Do not click or modify the page."],
            "allowed_scope": ["fixture.workflow", "observe_fixture", "fixture.observe"],
        },
        expected_postconditions=(
            {
                "condition_id": "status_is_idle",
                "path": "status",
                "operator": "equals",
                "value": "Idle",
            },
        ),
        observation_requirements=("Return a fresh status observation.",),
        risk_level="low",
        requires_human_approval=False,
        idempotency_key="fixture:observe:attempt-1",
    )

    async def exercise_adapter() -> None:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            try:
                page = await browser.new_page()
                await page.goto(
                    f"http://127.0.0.1:{server.server_port}/index.html",
                    wait_until="domcontentloaded",
                )

                async def observe_status(current_page: Any) -> dict[str, Any]:
                    return {"status": await current_page.locator("#status").inner_text()}

                adapter = BrowserAgentHandsAdapter(
                    page,
                    model,
                    observe_status,
                    tmp_path / "adapter-traces",
                )
                result = await adapter.execute(delegation)

                assert result.status == "succeeded"
                assert result.postcondition_results[0]["result"] == "passed"
                assert model.calls == 1
                assert await page.locator("#status").inner_text() == "Idle"
                assert await page.locator("#name").input_value() == ""
                assert Path(result.trace_ref).is_file()
            finally:
                await browser.close()

    try:
        asyncio.run(exercise_adapter())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_woocommerce_observer_reads_expected_state_without_page_mutation() -> None:
    pytest.importorskip("playwright")
    from playwright.async_api import async_playwright

    async def inspect_fixture() -> None:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            try:
                page = await browser.new_page()
                await page.goto(WOOCOMMERCE_FIXTURE.resolve().as_uri())
                snapshot_script = """() => ({
                    markup: document.documentElement.outerHTML,
                    values: Array.from(document.querySelectorAll("input, textarea, select"))
                        .map((element) => ({
                            id: element.id,
                            value: element.value,
                            selectedIndex: element.selectedIndex
                        }))
                })"""
                before = await page.evaluate(snapshot_script)
                state = await woocommerce_product_state(page)
                after = await page.evaluate(snapshot_script)

                assert state == {
                    "title": {"value": "Fixture Product", "status": "present"},
                    "product_type": {"value": "simple"},
                    "price": {"value": "19.95"},
                    "description": {"present": True},
                    "short_description": {"present": True},
                    "draft": {"status": "draft_updated"},
                    "publish": {"visible": True},
                }
                assert after == before
            finally:
                await browser.close()

    asyncio.run(inspect_fixture())
