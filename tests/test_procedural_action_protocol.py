import pytest

from scripts.procedural_action_protocol import (
    ActionProposalError,
    execute_proposal,
)
from scripts.procedural_simulator import MockTranslationApp


def test_valid_proposal_executes_one_action_and_records_audit():
    app = MockTranslationApp()
    result = execute_proposal(app, {"action": "enable", "target": "beta_toggle"})
    assert result["beta_enabled"] is True
    assert len(app.audit_log) == 1


@pytest.mark.parametrize(
    "proposal",
    [
        None,
        [],
        {"target": "beta_toggle"},
        {"action": "enable"},
        {"action": "delete_all", "target": "beta_toggle"},
        {"action": "enable", "target": "shell"},
        {"action": "enable", "target": "beta_toggle", "extra": True},
        {"action": "enable", "target": "beta_toggle", "value": 7},
        {"action": "enable", "target": "beta_toggle", "value": ""},
    ],
)
def test_malformed_or_unapproved_proposals_are_rejected(proposal):
    app = MockTranslationApp()
    with pytest.raises(ActionProposalError):
        execute_proposal(app, proposal)
    assert app.audit_log == []
    assert app.beta_enabled is False


def test_valid_vocabulary_does_not_bypass_state_machine():
    app = MockTranslationApp()
    with pytest.raises(ActionProposalError, match="current state"):
        execute_proposal(app, {"action": "publish_mock", "target": "publish"})
    assert app.audit_log == []
    assert app.published is False


def test_proposal_cannot_mutate_internal_state_fields():
    app = MockTranslationApp()
    with pytest.raises(ActionProposalError, match="Unknown fields"):
        execute_proposal(
            app,
            {
                "action": "enable",
                "target": "beta_toggle",
                "state": "published_mock",
            },
        )
    assert app.state == "settings"
