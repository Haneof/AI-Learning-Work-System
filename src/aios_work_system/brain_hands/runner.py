"""Testable orchestration helpers for the Brain/Hands CLI entry point."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aios_work_system.brain_hands.engine import (
    BrainHandsLoop,
    LoopConfig,
    LoopReport,
    WorkflowBrain,
)
from aios_work_system.brain_hands.simulated import SimulatedHands, shop_listing_handlers


class RunLoopConfigurationError(ValueError):
    """Raised when run-loop inputs or runtime configuration are invalid."""

    def __init__(self, message: str, *, errors: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.errors = errors or (message,)


@dataclass(frozen=True, slots=True)
class RunLoopResult:
    """CLI-facing result returned after a workflow run has been persisted."""

    exit_code: int
    report_path: Path
    report: LoopReport


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RunLoopConfigurationError(f"{label} file does not exist: {path}") from exc
    except OSError as exc:
        raise RunLoopConfigurationError(f"cannot read {label} file {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RunLoopConfigurationError(
            f"{label} file contains invalid JSON at line {exc.lineno}, "
            f"column {exc.colno}: {exc.msg}"
        ) from exc
    if not isinstance(payload, dict):
        raise RunLoopConfigurationError(f"{label} JSON must contain a top-level object")
    return payload


def _workflow_validator():
    """Import the repository's validator without invoking its command-line wrapper."""
    try:
        from contracts.validate import validate_workflow
    except ModuleNotFoundError:
        validator_path = Path(__file__).resolve().parents[3] / "contracts" / "validate.py"
        if not validator_path.is_file():
            raise RunLoopConfigurationError(
                f"workflow contract validator is unavailable: {validator_path}"
            ) from None
        spec = importlib.util.spec_from_file_location(
            "_aios_workflow_contract_validator", validator_path
        )
        if spec is None or spec.loader is None:
            raise RunLoopConfigurationError(
                f"cannot load workflow contract validator: {validator_path}"
            )
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            raise RunLoopConfigurationError(
                f"cannot import workflow contract validator: {type(exc).__name__}: {exc}"
            ) from exc
        validate_workflow = module.validate_workflow
    return validate_workflow


def load_workflow(workflow_path: str | Path) -> dict[str, Any]:
    """Load a workflow JSON object and validate it with contracts/validate.py."""
    workflow = _read_json_object(Path(workflow_path), "workflow")
    validate_workflow = _workflow_validator()
    declared_evidence_refs = workflow.get("evidence_refs", [])
    if not isinstance(declared_evidence_refs, list):
        declared_evidence_refs = []
    errors = validate_workflow(workflow, declared_evidence_refs)
    if errors:
        raise RunLoopConfigurationError(
            "workflow validation failed",
            errors=tuple(str(error) for error in errors),
        )
    return workflow


def load_run_inputs(
    inputs_path: str | Path | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load the optional initial-state and Brain-input objects."""
    if inputs_path is None:
        return {}, {}
    payload = _read_json_object(Path(inputs_path), "inputs")
    initial_state = payload.get("initial_state", {})
    workflow_inputs = payload.get("workflow_inputs", {})
    if not isinstance(initial_state, dict):
        raise RunLoopConfigurationError("inputs.initial_state must be a JSON object")
    if not isinstance(workflow_inputs, dict):
        raise RunLoopConfigurationError("inputs.workflow_inputs must be a JSON object")
    return initial_state, workflow_inputs


async def _run_browser_loop(
    workflow: dict[str, Any],
    workflow_inputs: dict[str, Any],
    config: LoopConfig,
    url: str,
    trace_dir: Path,
) -> LoopReport:
    from aios_work_system.brain_hands.browser_adapter import BrowserAgentHandsAdapter
    from aios_work_system.brain_hands.woocommerce import woocommerce_product_state
    from aios_work_system.gui.browser import local_origin
    from aios_work_system.gui.real_model import (
        ModelConfigurationError,
        OpenAICompatibleDecisionModel,
    )

    try:
        local_origin(url)
    except ValueError as exc:
        raise RunLoopConfigurationError(
            f"browser --url must be a loopback HTTP(S) URL: {exc}"
        ) from exc

    try:
        model = OpenAICompatibleDecisionModel.from_env()
    except ModelConfigurationError as exc:
        raise RunLoopConfigurationError(f"Model configuration error: {exc}") from exc

    try:
        from playwright.async_api import async_playwright
    except ModuleNotFoundError as exc:
        raise RunLoopConfigurationError(
            "Playwright is not installed. Install the GUI extra and Chromium "
            '(python -m pip install -e ".[gui]"; playwright install chromium).'
        ) from exc

    async with async_playwright() as playwright:
        try:
            browser = await playwright.chromium.launch()
        except Exception as exc:
            raise RunLoopConfigurationError(
                f"Could not launch Playwright Chromium: {type(exc).__name__}: {exc}"
            ) from exc
        try:
            page = await browser.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded")
            except Exception as exc:
                raise RunLoopConfigurationError(
                    f"Could not open browser target {url}: {type(exc).__name__}: {exc}"
                ) from exc
            hands = BrowserAgentHandsAdapter(
                page,
                model,
                woocommerce_product_state,
                trace_dir,
            )
            return await BrainHandsLoop(workflow, WorkflowBrain(workflow), hands, config).run(
                workflow_inputs
            )
        finally:
            await browser.close()


def _write_report(output_dir: Path, report: LoopReport) -> Path:
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / "report.json"
        report_data = {
            "status": report.status,
            "goal_satisfied": report.goal_satisfied,
            "decisions": report.decisions,
            "operations": report.operations,
            "final_state": dict(report.final_state),
            "error": report.error,
        }
        report_path.write_text(
            json.dumps(report_data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        history_path = output_dir / "history.jsonl"
        with history_path.open("w", encoding="utf-8", newline="\n") as handle:
            for entry in report.history:
                handle.write(json.dumps(dict(entry), ensure_ascii=False) + "\n")
    except OSError as exc:
        raise RunLoopConfigurationError(
            f"cannot write run-loop reports to {output_dir}: {exc}"
        ) from exc
    return report_path


def run_loop(
    *,
    workflow_path: str | Path,
    inputs_path: str | Path | None = None,
    hands: str = "simulated",
    brain: str = "workflow",
    max_decisions: int = 30,
    output_dir: str | Path = "artifacts/brain-hands/run",
    url: str | None = None,
    trace_dir: str | Path | None = None,
) -> RunLoopResult:
    """Validate, construct, execute, and persist one Brain/Hands loop run."""
    if brain != "workflow":
        raise RunLoopConfigurationError("only --brain workflow is supported")
    if hands not in {"simulated", "browser"}:
        raise RunLoopConfigurationError("--hands must be simulated or browser")
    if hands == "browser" and not url:
        raise RunLoopConfigurationError("--url is required when --hands browser")
    try:
        config = LoopConfig(max_decisions=max_decisions)
    except ValueError as exc:
        raise RunLoopConfigurationError(str(exc)) from exc

    workflow = load_workflow(workflow_path)
    initial_state, workflow_inputs = load_run_inputs(inputs_path)
    if hands == "simulated":
        simulator = SimulatedHands(initial_state, shop_listing_handlers())
        report = asyncio.run(
            BrainHandsLoop(workflow, WorkflowBrain(workflow), simulator, config).run(
                workflow_inputs
            )
        )
    else:
        output_path = Path(output_dir)
        traces_path = Path(trace_dir) if trace_dir is not None else output_path / "traces"
        report = asyncio.run(
            _run_browser_loop(workflow, workflow_inputs, config, url or "", traces_path)
        )

    report_path = _write_report(Path(output_dir), report)
    exit_code = 0 if report.status == "succeeded" and report.goal_satisfied else 1
    return RunLoopResult(exit_code=exit_code, report_path=report_path, report=report)


def run_loop_command(
    *,
    workflow_path: str | Path,
    inputs_path: str | Path | None = None,
    hands: str = "simulated",
    brain: str = "workflow",
    max_decisions: int = 30,
    output_dir: str | Path = "artifacts/brain-hands/run",
    url: str | None = None,
    trace_dir: str | Path | None = None,
) -> int:
    """CLI presentation wrapper, separate from argparse and directly testable."""
    try:
        result = run_loop(
            workflow_path=workflow_path,
            inputs_path=inputs_path,
            hands=hands,
            brain=brain,
            max_decisions=max_decisions,
            output_dir=output_dir,
            url=url,
            trace_dir=trace_dir,
        )
    except RunLoopConfigurationError as exc:
        for error in exc.errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"run-loop failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    report = result.report
    print(
        f"run-loop: {report.status} goal_satisfied={str(report.goal_satisfied).lower()} "
        f"decisions={report.decisions} operations={report.operations}"
    )
    print(f"Report: {result.report_path}")
    return result.exit_code
