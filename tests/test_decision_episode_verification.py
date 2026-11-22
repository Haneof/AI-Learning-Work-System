"""Unit tests for fail-closed local DecisionEpisode verification."""

from __future__ import annotations

from copy import deepcopy

import pytest

from aios_work_system.video_extraction.verification import (
    LocalDecisionEpisodeVerifier,
    LocalOpenModelClient,
    training_dataset_admission_status,
)


class FakeLocalModel:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def complete_json(self, system_prompt, user_payload):
        self.calls += 1
        assert "Do not invent missing facts" in system_prompt
        assert user_payload["episode"]["episode_id"] == "ep-001"
        return deepcopy(self.response)


def _episode(direct=False):
    return {
        "episode_id": "ep-001",
        "source": {"source_id": "video-001"},
        "task": {
            "goal": "Create a folder",
            "business_constraints": ["Do not overwrite existing folders"],
        },
        "state_before": {
            "facts": [{"fact_id": "f1", "value": "A folder with that name already exists"}]
        },
        "narration": [
            {
                "segment_id": "n1",
                "start_ms": 1000,
                "end_ms": 2000,
                "text": "I create a new folder",
            }
        ],
        "decision": {
            "selected_strategy": "Create another folder with the same name",
            "decision_basis": ["instructor_explicit"],
            "evidence_refs": ["ev-words"],
        },
        "operation": {"execution_status": "observed" if direct else "not_observed"},
        "outcome": {
            "status": "success" if direct else "not_verified",
            "postcondition_checks": [
                {
                    "condition": "The requested folder exists",
                    "result": "passed" if direct else "unknown",
                    "evidence_refs": ["ev-result"],
                }
            ],
        },
        "evidence": [
            {
                "evidence_id": "ev-words",
                "evidence_type": "narration",
                "observation_channel": "not_applicable",
                "rationale_source": "instructor_explicit",
                "claim": "I create a new folder",
            },
            {
                "evidence_id": "ev-action",
                "evidence_type": "ui_event",
                "observation_channel": "direct_capture" if direct else "inferred_from_video",
                "rationale_source": "not_applicable",
                "claim": "The create-folder action",
            },
            {
                "evidence_id": "ev-result",
                "evidence_type": "business_result",
                "observation_channel": "direct_capture" if direct else "observed_from_video",
                "rationale_source": "not_applicable",
                "claim": "The resulting folder state",
            },
        ],
    }


def _source_evidence():
    return {
        "source_metadata": {"duration_ms": 5000},
        "transcript": [
            {
                "segment_id": "n1",
                "start_ms": 1000,
                "end_ms": 2000,
                "text": "I create a new folder",
            }
        ],
        "frames": [
            {"frame_index": 0, "timestamp_ms": 0, "is_initial": True},
            {"frame_index": 1, "timestamp_ms": 2000, "is_change": True},
        ],
        "ocr_records": [{"timestamp_ms": 2000, "text": "New Folder"}],
        "cursor_events": [],
        "grounding_results": [],
        "alignment": {
            "alignment": [{"segment_id": "n1", "matched_event_ids": ["frame-change-000001"]}]
        },
    }


def _response(decision_status="pass", outcome_status="unknown", causal_basis="unknown"):
    return {
        "episode_id": "ep-001",
        "levels": {
            "extraction_fidelity": {
                "status": "pass",
                "reasons": ["Narration and OCR claims match the source packet."],
                "evidence_refs": ["ev-words", "ev-result"],
                "unknowns": [],
            },
            "decision_validity": {
                "status": decision_status,
                "reasons": [
                    "The proposed action violates the no-overwrite constraint."
                    if decision_status == "fail"
                    else "The selected action is reasonable."
                ],
                "evidence_refs": ["ev-words"],
                "unknowns": [],
            },
            "outcome_validity": {
                "status": outcome_status,
                "reasons": [
                    "The result is supported."
                    if outcome_status == "pass"
                    else "Causal proof is missing."
                ],
                "evidence_refs": ["ev-action", "ev-result"],
                "unknowns": [],
                "causal_basis": causal_basis,
                "confounders_addressed": (
                    ["The state was unchanged except for the tested operation."]
                    if causal_basis in {"controlled_comparison", "system_audit_trail"}
                    else []
                ),
            },
        },
    }


def test_faithfully_extracted_but_wrong_decision_fails_decision_validity():
    model = FakeLocalModel(_response(decision_status="fail"))
    report = LocalDecisionEpisodeVerifier(completion_client=model).verify(
        _episode(), _source_evidence()
    )

    assert report["levels"]["extraction_fidelity"]["status"] == "pass"
    assert report["levels"]["decision_validity"]["status"] == "fail"
    assert "no-overwrite constraint" in report["levels"]["decision_validity"]["reasons"][0]
    assert report["overall_status"] == "fail"
    assert report["training_admission"]["eligible_for_dataset"] is False
    assert model.calls == 1


def test_unknown_is_preserved_and_never_treated_as_pass():
    response = _response(decision_status="unknown", outcome_status="unknown")
    report = LocalDecisionEpisodeVerifier(completion_client=FakeLocalModel(response)).verify(
        _episode(), _source_evidence()
    )

    assert report["levels"]["decision_validity"]["status"] == "unknown"
    assert report["levels"]["outcome_validity"]["status"] == "unknown"
    assert report["overall_status"] == "unknown"


def test_model_cannot_pass_a_level_while_reporting_unresolved_unknowns():
    response = _response(decision_status="pass")
    response["levels"]["decision_validity"]["unknowns"] = [
        "The relevant application state is not fully visible."
    ]
    report = LocalDecisionEpisodeVerifier(
        completion_client=FakeLocalModel(response)
    ).verify(_episode(), _source_evidence())

    assert report["levels"]["decision_validity"]["status"] == "unknown"
    assert report["overall_status"] == "unknown"


def test_positive_result_after_action_without_causal_evidence_is_unknown():
    episode = _episode()
    episode["operation"]["execution_status"] = "observed"
    episode["outcome"]["status"] = "success"
    episode["outcome"]["postcondition_checks"][0] = {
        "condition": "The requested folder exists",
        "result": "passed",
        "evidence_refs": ["ev-result"],
    }
    model = FakeLocalModel(
        _response(outcome_status="pass", causal_basis="temporal_correlation_only")
    )
    report = LocalDecisionEpisodeVerifier(completion_client=model).verify(
        episode, _source_evidence()
    )

    level = report["levels"]["outcome_validity"]
    assert level["status"] == "unknown"
    assert any("correlation, not causal evidence" in item for item in level["reasons"])


def test_outcome_pass_requires_direct_execution_result_and_causal_audit():
    report = LocalDecisionEpisodeVerifier(
        completion_client=FakeLocalModel(
            _response(outcome_status="pass", causal_basis="controlled_comparison")
        )
    ).verify(_episode(direct=True), _source_evidence())

    assert report["levels"]["outcome_validity"]["status"] == "pass"


def test_fabricated_evidence_reference_fails_that_verification_level():
    response = _response()
    response["levels"]["extraction_fidelity"]["evidence_refs"] = ["invented-evidence"]
    report = LocalDecisionEpisodeVerifier(completion_client=FakeLocalModel(response)).verify(
        _episode(), _source_evidence()
    )

    assert report["levels"]["extraction_fidelity"]["status"] == "fail"
    assert report["overall_status"] == "fail"


def test_missing_source_evidence_returns_unknown_without_model_call():
    model = FakeLocalModel(_response())
    report = LocalDecisionEpisodeVerifier(completion_client=model).verify(_episode(), None)

    assert report["overall_status"] == "unknown"
    assert all(
        report["levels"][name]["status"] == "unknown"
        for name in ("extraction_fidelity", "decision_validity", "outcome_validity")
    )
    assert model.calls == 0


def test_unconfigured_local_model_holds_episode():
    report = LocalDecisionEpisodeVerifier().verify(_episode(), _source_evidence())

    assert report["overall_status"] == "unknown"
    assert report["training_admission"]["eligible_for_dataset"] is False


def test_loopback_client_rejects_remote_model_urls():
    with pytest.raises(ValueError, match="remote verifier endpoints are forbidden"):
        LocalOpenModelClient("https://api.example.com/v1/chat/completions")


def test_dataset_requires_local_pass_and_separate_pm_pass():
    local = {
        "overall_status": "pass",
        "levels": {
            name: {"status": "pass"}
            for name in ("extraction_fidelity", "decision_validity", "outcome_validity")
        },
    }
    assert training_dataset_admission_status(local, None)["eligible_for_dataset"] is False
    assert (
        training_dataset_admission_status(local, {"status": "fail"})["eligible_for_dataset"]
        is False
    )
    # A bare PASS cannot attest that the PM actually inspected both artifacts.
    assert (
        training_dataset_admission_status(local, {"status": "pass"})["eligible_for_dataset"]
        is False
    )
    pm_review = {
        "status": "pass",
        "source_evidence_refs": ["video:timestamp:2000"],
        "proposed_record_evidence_refs": ["episode:decision.selected_strategy"],
    }
    assert training_dataset_admission_status(local, pm_review)["eligible_for_dataset"] is True
    pm_review["source_evidence_refs"] = "not-a-list"
    assert training_dataset_admission_status(local, pm_review)["eligible_for_dataset"] is False
