"""Business-level Brain/Hands orchestration over the existing GUI execution layer."""

from aios_work_system.brain_hands.browser_adapter import BrowserAgentHandsAdapter
from aios_work_system.brain_hands.engine import (
    BrainHandsLoop,
    LoopConfig,
    LoopReport,
    WorkflowBrain,
    condition_matches,
    workflow_goal_satisfied,
)
from aios_work_system.brain_hands.interfaces import (
    Brain,
    BrainContext,
    BrainDecision,
    BrainDecisionAction,
    ExecutionResult,
    ExecutionStatus,
    Hands,
    OperationDelegation,
    ProtocolError,
)
from aios_work_system.brain_hands.simulated import (
    SimulatedHands,
    SimulatedOutcome,
    shop_listing_handlers,
)

__all__ = [
    "Brain",
    "BrainContext",
    "BrainDecision",
    "BrainDecisionAction",
    "BrainHandsLoop",
    "BrowserAgentHandsAdapter",
    "ExecutionResult",
    "ExecutionStatus",
    "Hands",
    "LoopConfig",
    "LoopReport",
    "OperationDelegation",
    "ProtocolError",
    "SimulatedHands",
    "SimulatedOutcome",
    "WorkflowBrain",
    "condition_matches",
    "shop_listing_handlers",
    "workflow_goal_satisfied",
]
