import json
from pathlib import Path

from scripts.evaluate_procedural_steps import evaluate  # noqa: I001


FIXTURE = Path(__file__).parent / "fixtures" / "procedural_steps_ground_truth.json"


def test_exact_match_scores_perfectly():
    reference = json.loads(FIXTURE.read_text(encoding="utf-8"))
    prediction = json.loads(json.dumps(reference))
    report = evaluate(reference, prediction)
    assert report["extraction"]["f1"] == 1.0
    assert report["order_accuracy"] == 1.0
    assert report["evidence_completeness"] == 1.0
    assert report["expected_state_accuracy_on_matched_steps"] == 1.0


def test_missing_evidence_does_not_count_as_complete():
    reference = json.loads(FIXTURE.read_text(encoding="utf-8"))
    prediction = json.loads(json.dumps(reference))
    prediction["steps"][0]["evidence_refs"] = []
    report = evaluate(reference, prediction)
    assert report["extraction"]["f1"] == 1.0
    assert report["evidence_completeness"] == round(2 / 3, 4)


def test_wrong_action_and_target_are_not_matched():
    reference = json.loads(FIXTURE.read_text(encoding="utf-8"))
    prediction = json.loads(json.dumps(reference))
    prediction["steps"][1]["target"] = "wrong_control"
    report = evaluate(reference, prediction)
    assert report["counts"]["matched_steps"] == 2
    assert report["extraction"]["recall"] == round(2 / 3, 4)
