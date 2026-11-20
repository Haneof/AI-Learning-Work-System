import pytest

from scripts.evaluate_procedural_execution import evaluate


def _episode(
    episode_id,
    attempted,
    successful,
    completed,
    opportunity=False,
    recovery_attempted=False,
    recovery_succeeded=None,
):
    return {
        "episode_id": episode_id,
        "attempted_actions": attempted,
        "successful_actions": successful,
        "task_completed": completed,
        "recovery_opportunity": opportunity,
        "recovery_attempted": recovery_attempted,
        "recovery_succeeded": recovery_succeeded,
    }


def test_metrics_keep_step_task_and_recovery_denominators_separate():
    payload = {
        "benchmark_id": "synthetic-metrics-test",
        "episodes": [
            _episode("a", 4, 3, True, True, True, True),
            _episode("b", 2, 1, False, True, True, False),
            _episode("c", 3, 3, True),
            _episode("d", 1, 0, False, True, False),
        ],
    }
    report = evaluate(payload)
    assert report["step_success_rate"] == 0.7
    assert report["task_completion_rate"] == 0.5
    assert report["recovery_success_rate"] == 0.5
    assert report["counts"]["recovery_opportunities"] == 3
    assert report["counts"]["recovery_attempted_episodes"] == 2
    assert report["counts"]["recovery_not_attempted_episodes"] == 1


def test_no_recovery_attempts_produces_null_not_zero_rate():
    report = evaluate({"episodes": [_episode("a", 1, 1, True)]})
    assert report["recovery_success_rate"] is None


def test_zero_action_denominator_produces_null_step_rate():
    report = evaluate({"episodes": [_episode("a", 0, 0, False)]})
    assert report["step_success_rate"] is None


@pytest.mark.parametrize(
    "episode",
    [
        _episode("bad", 1, 2, True),
        _episode("bad", True, 0, False),
        _episode("bad", 1, 0, False, False, True, True),
        _episode("bad", 1, 0, False, True, True, None),
        {**_episode("bad", 1, 0, False), "unexpected": 1},
    ],
)
def test_inconsistent_episode_records_are_rejected(episode):
    with pytest.raises(ValueError):
        evaluate({"episodes": [episode]})


def test_duplicate_episode_ids_are_rejected():
    with pytest.raises(ValueError, match="unique"):
        evaluate({"episodes": [_episode("same", 1, 1, True), _episode("same", 1, 0, False)]})
