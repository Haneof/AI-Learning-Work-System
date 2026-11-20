import json

import pytest

from scripts.procedural_agent_runner import parse_proposal, run_agent
from scripts.procedural_simulator import MockTranslationApp


def test_parse_proposal_requires_strict_json_object():
    assert parse_proposal('{"action":"open","target":"dashboard"}') == {
        "action": "open",
        "target": "dashboard",
    }
    assert parse_proposal('{"action":"stop","target":"task"}') is None
    for invalid in ("not json", "```json\n{}\n```", "[]", "null"):
        with pytest.raises(ValueError):
            parse_proposal(invalid)


def test_runner_executes_bounded_actions_and_stops_on_completion():
    proposals = [
        {"action": "enable", "target": "beta_toggle"},
        {"action": "open", "target": "dashboard"},
        {"action": "select_source", "target": "source_language_dropdown", "value": "es"},
        {"action": "select_target", "target": "target_language_dropdown", "value": "ca"},
        {"action": "select_article", "target": "article_picker", "value": "Garam masala"},
        {"action": "open", "target": "editor"},
        {"action": "add_paragraph", "target": "central_translation_pane"},
        {"action": "inspect_alignment", "target": "sentence_highlights"},
        {"action": "verify_links_and_formatting", "target": "links_and_formatting"},
        {"action": "wait_for_autosave", "target": "autosave_indicator"},
        {"action": "navigate", "target": "translation_dashboard"},
        {"action": "resume", "target": "draft_button"},
        {"action": "publish_mock", "target": "mock_publish_button"},
    ]
    iterator = iter(proposals)

    def model_call(prompt):
        assert "Current state:" in prompt
        return json.dumps(next(iterator))

    report = run_agent(MockTranslationApp(), model_call, max_steps=15)
    assert report["task_completed"] is True
    assert report["successful_actions"] == 13
    assert report["attempted_actions"] == 13
    assert report["stop_reason"] == "task_completed"


def test_runner_rejects_bad_output_and_respects_step_limit():
    outputs = iter(["{bad json", '{"action":"open","target":"dashboard"}'])

    report = run_agent(
        MockTranslationApp(),
        lambda _prompt: next(outputs),
        max_steps=2,
    )
    assert report["attempted_actions"] == 2
    assert report["successful_actions"] == 0
    assert report["task_completed"] is False
    assert report["stop_reason"] == "max_steps_reached"
    assert [event["status"] for event in report["events"]] == ["rejected", "rejected"]


def test_runner_records_provider_failure_without_crashing():
    def broken(_prompt):
        raise RuntimeError("provider unavailable")

    report = run_agent(MockTranslationApp(), broken, max_steps=3)
    assert report["attempted_actions"] == 0
    assert report["stop_reason"] == "model_call_error"
    assert report["events"][0]["status"] == "model_error"


def test_runner_requires_positive_bounded_step_count():
    with pytest.raises(ValueError):
        run_agent(MockTranslationApp(), lambda _prompt: "{}", max_steps=0)
