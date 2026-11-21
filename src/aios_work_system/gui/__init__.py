"""Local-only browser GUI agent primitives."""

from aios_work_system.gui.agent import AgentConfig, BrowserAgent, DecisionModel, RunReport
from aios_work_system.gui.contracts import (
    BrowserObservation,
    ContractError,
    ExpectedResult,
    GuiAction,
)
from aios_work_system.gui.trace import (
    BrowserEventCapture,
    JsonlTraceRecorder,
    ReplayReport,
    ReplayVerificationError,
    TraceFormatError,
    TraceReplayer,
    load_trace,
)

__all__ = [
    "AgentConfig",
    "BrowserAgent",
    "BrowserEventCapture",
    "BrowserObservation",
    "ContractError",
    "DecisionModel",
    "ExpectedResult",
    "GuiAction",
    "JsonlTraceRecorder",
    "ReplayReport",
    "ReplayVerificationError",
    "RunReport",
    "TraceFormatError",
    "TraceReplayer",
    "load_trace",
]
