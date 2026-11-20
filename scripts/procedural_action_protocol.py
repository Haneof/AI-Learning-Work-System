"""Strict boundary between model-proposed actions and simulator execution.

The model may propose a small JSON-like action object. This adapter validates its
shape and vocabulary before delegating to the deterministic simulator state machine.
"""
from __future__ import annotations

from typing import Any

from scripts.procedural_simulator import MockTranslationApp

ALLOWED_ACTIONS = {
    "enable",
    "open",
    "select_source",
    "select_target",
    "select_article",
    "add_paragraph",
    "inspect_alignment",
    "verify_links_and_formatting",
    "wait_for_autosave",
    "navigate",
    "resume",
    "publish_mock",
}
ALLOWED_TARGETS = {
    "beta_toggle",
    "beta_feature_switch",
    "translation_dashboard",
    "dashboard",
    "source_language_dropdown",
    "source_language",
    "target_language_dropdown",
    "target_language",
    "article_picker",
    "article",
    "editor",
    "central_translation_pane",
    "translation_pane",
    "sentence_highlights",
    "sentence_alignment",
    "links_and_formatting",
    "paragraph_content",
    "autosave_indicator",
    "draft_status",
    "draft_button",
    "draft",
    "mock_publish_button",
    "publish",
    "settings_beta_control",
}
REQUIRED_KEYS = {"action", "target"}
OPTIONAL_KEYS = {"value"}


class ActionProposalError(ValueError):
    """Raised when a model-proposed action violates the execution contract."""


def execute_proposal(
    app: MockTranslationApp, proposal: dict[str, Any]
) -> dict[str, Any]:
    """Validate a proposal and execute exactly one permitted simulator action."""
    if not isinstance(proposal, dict):
        raise ActionProposalError("Proposal must be a JSON object")
    keys = set(proposal)
    missing = REQUIRED_KEYS - keys
    unknown = keys - REQUIRED_KEYS - OPTIONAL_KEYS
    if missing:
        raise ActionProposalError(f"Missing required fields: {sorted(missing)}")
    if unknown:
        raise ActionProposalError(f"Unknown fields: {sorted(unknown)}")

    action = proposal["action"]
    target = proposal["target"]
    value = proposal.get("value")
    if not isinstance(action, str) or action not in ALLOWED_ACTIONS:
        raise ActionProposalError("Action is not in the execution allowlist")
    if not isinstance(target, str) or target not in ALLOWED_TARGETS:
        raise ActionProposalError("Target is not in the execution allowlist")
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise ActionProposalError("Value must be a non-empty string when supplied")

    try:
        return app.perform(action, target, value)
    except ValueError as exc:
        raise ActionProposalError(str(exc)) from exc
