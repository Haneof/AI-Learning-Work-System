"""Regression tests for local-only small-first video model routing."""

from __future__ import annotations

import json
from pathlib import Path

from aios_work_system.video_extraction.episode import build_decision_episode
from aios_work_system.video_extraction.local_models import parse_normalized_point
from aios_work_system.video_extraction.model_router import (
    _decision_quality_check,
    evaluate_grounder,
    route_ui_grounder,
    synthesize_episode_decision,
)


def _benchmark(path: Path) -> Path:
    payload = {
        "benchmark_id": "unit-grounding",
        "annotation_source": "human-labelled target boxes",
        "video_id": "unit-video",
        "annotations": [
            {
                "timestamp_ms": 100,
                "query": "the Save button",
                "target_label": "Save button",
                "target_bbox_norm": [0.4, 0.4, 0.6, 0.6],
            },
            {
                "timestamp_ms": 200,
                "query": "the title field",
                "target_label": "title field",
                "target_bbox_norm": [0.4, 0.4, 0.6, 0.6],
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _frames() -> list[dict]:
    return [
        {"timestamp_ms": 100, "path": "frame-1.jpg", "is_change": True},
        {"timestamp_ms": 200, "path": "frame-2.jpg", "is_change": True},
    ]


def _episode(video_path: Path) -> dict:
    video_path.write_bytes(b"video bytes for test identity")
    return build_decision_episode(
        video_path=video_path,
        video_metadata={"video_id": "unit-video", "duration_ms": 1000},
        transcript=[],
        frames=[{"frame_index": 0, "timestamp_ms": 0, "is_initial": True, "is_change": False}],
        ocr_records=[],
        cursor_events=[],
        vlm_results=[],
        alignment={"alignment": []},
    )


def _decision() -> dict:
    return {
        "decision_type": "step_selection",
        "selected_strategy": "Leave this video interpretation for human confirmation.",
        "rationale_summary": (
            "The decoded video shows screen changes, but no native click event exists."
        ),
        "decision_basis": ["unknown"],
        "applicable_conditions": [],
        "selected_next_step": {
            "action": "ask_user",
            "objective": "Review the video-grounded interpretation before accepting it.",
            "question": "Does this interpretation match the demonstrated operation?",
        },
        "alternatives_considered": [],
        "uncertainties": ["A downloaded tutorial does not contain native click telemetry."],
        "evidence_refs": ["ev-observed-video"],
    }


def test_parse_normalized_point_accepts_normalized_coordinates_only():
    assert parse_normalized_point("[0.5, 0.25]") == (0.5, 0.25)
    assert parse_normalized_point("[0.75, 1.0]") == (0.75, 1.0)
    assert parse_normalized_point("[1024, 560]") is None
    assert parse_normalized_point("no visible target") is None


def test_grounding_metric_measures_point_inside_manual_target_box():
    class FakeGrounder:
        model_id = "fake-showui-2b"
        parameter_class = "2B"
        license = "MIT"

        def ground(self, *_args):
            return {"status": "completed", "point_norm": [0.5, 0.5]}

    report = evaluate_grounder(
        FakeGrounder(),
        _frames(),
        [
            {
                "timestamp_ms": 100,
                "query": "save button",
                "target_label": "Save",
                "target_bbox_norm": [0.4, 0.4, 0.6, 0.6],
            },
            {
                "timestamp_ms": 200,
                "query": "title field",
                "target_label": "Title",
                "target_bbox_norm": [0.4, 0.4, 0.6, 0.6],
            },
        ],
        [],
        [],
    )
    assert report["samples"] == 2
    assert report["valid_coordinate_predictions"] == 2
    assert report["target_box_hit_rate"] == 1.0
    assert report["passed"] is True


def test_showui_2b_passes_so_ui_tars_2b_and_7b_are_not_loaded(tmp_path, monkeypatch):
    import aios_work_system.video_extraction.model_router as router

    loaded = []

    class PassingGrounder:
        model_id = "showlab/ShowUI-2B"
        parameter_class = "2B"
        license = "MIT"

        def __init__(self, path, local_files_only=True):
            loaded.append(("showui", str(path), local_files_only))

        def ground(self, *_args):
            return {"status": "completed", "point_norm": [0.5, 0.5]}

    class ForbiddenGrounder:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("a larger/sibling model must not load after ShowUI passed")

    monkeypatch.setattr(router, "ensure_hf_snapshot", lambda repo, path, **_kw: Path(path))
    monkeypatch.setattr(router, "ShowUI2BGrounder", PassingGrounder)
    monkeypatch.setattr(router, "UITARS2BGrounder", ForbiddenGrounder)
    monkeypatch.setattr(router, "UITARS7BGrounder", ForbiddenGrounder)

    model, report, cached = route_ui_grounder(
        primary_model_path="showui",
        secondary_small_model_path="ui-tars-2b",
        fallback_model_path="ui-tars-7b",
        allow_download=False,
        benchmark_path=_benchmark(tmp_path / "benchmark.json"),
        frames=_frames(),
        ocr_records=[],
        transcript=[],
    )
    assert model.model_id == "showlab/ShowUI-2B"
    assert report["primary_evaluation"]["target_box_hit_rate"] == 1.0
    assert report["secondary_small_evaluation"] is None
    assert report["large_fallback_evaluation"] is None
    assert report["status"] == "completed"
    assert len(cached) == 2
    assert [item[0] for item in loaded] == ["showui"]


def test_ui_tars_2b_is_tested_before_the_7b_fallback(tmp_path, monkeypatch):
    import aios_work_system.video_extraction.model_router as router

    loaded = []

    class PoorShowUI:
        model_id = "showlab/ShowUI-2B"
        parameter_class = "2B"
        license = "MIT"

        def __init__(self, *_args, **_kwargs):
            loaded.append("showui-2b")

        def ground(self, *_args):
            return {"status": "completed", "point_norm": [0.95, 0.95]}

    class PassingUITARS2B:
        model_id = "ByteDance-Seed/UI-TARS-2B-SFT"
        parameter_class = "2B"
        license = "Apache-2.0"

        def __init__(self, *_args, **_kwargs):
            loaded.append("ui-tars-2b")

        def ground(self, *_args):
            return {"status": "completed", "point_norm": [0.5, 0.5]}

    class Forbidden7B:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("7B must not load when the second 2B passed")

    monkeypatch.setattr(router, "ensure_hf_snapshot", lambda repo, path, **_kw: Path(path))
    monkeypatch.setattr(router, "ShowUI2BGrounder", PoorShowUI)
    monkeypatch.setattr(router, "UITARS2BGrounder", PassingUITARS2B)
    monkeypatch.setattr(router, "UITARS7BGrounder", Forbidden7B)

    model, report, _cached = route_ui_grounder(
        primary_model_path="showui",
        secondary_small_model_path="ui-tars-2b",
        fallback_model_path="ui-tars-7b",
        allow_download=False,
        benchmark_path=_benchmark(tmp_path / "benchmark.json"),
        frames=_frames(),
        ocr_records=[],
        transcript=[],
    )
    assert loaded == ["showui-2b", "ui-tars-2b"]
    assert report["primary_evaluation"]["target_box_hit_rate"] == 0.0
    assert report["secondary_small_evaluation"]["target_box_hit_rate"] == 1.0
    assert report["large_fallback_evaluation"] is None
    assert model.model_id == "ByteDance-Seed/UI-TARS-2B-SFT"


def test_ui_tars_7b_is_loaded_only_after_both_2b_models_measure_below_threshold(
    tmp_path,
    monkeypatch,
):
    import aios_work_system.video_extraction.model_router as router

    loaded = []

    class PoorGrounder:
        parameter_class = "2B"
        license = "Apache-2.0"

        def __init__(self, *_args, **_kwargs):
            loaded.append(self.model_id)

        def ground(self, *_args):
            return {"status": "completed", "point_norm": [0.98, 0.98]}

    class LargeFallback:
        model_id = "ByteDance-Seed/UI-TARS-7B-SFT"
        parameter_class = "7B"
        license = "Apache-2.0"

        def __init__(self, *_args, **_kwargs):
            loaded.append("ui-tars-7b")

        def ground(self, *_args):
            return {"status": "completed", "point_norm": [0.5, 0.5]}

    class PoorShowUI(PoorGrounder):
        model_id = "showlab/ShowUI-2B"
        license = "MIT"

    class PoorUITARS2B(PoorGrounder):
        model_id = "ByteDance-Seed/UI-TARS-2B-SFT"

    monkeypatch.setattr(router, "ensure_hf_snapshot", lambda repo, path, **_kw: Path(path))
    monkeypatch.setattr(router, "ShowUI2BGrounder", PoorShowUI)
    monkeypatch.setattr(router, "UITARS2BGrounder", PoorUITARS2B)
    monkeypatch.setattr(router, "UITARS7BGrounder", LargeFallback)

    model, report, _cached = route_ui_grounder(
        primary_model_path="showui",
        secondary_small_model_path="ui-tars-2b",
        fallback_model_path="ui-tars-7b",
        allow_download=False,
        benchmark_path=_benchmark(tmp_path / "benchmark.json"),
        frames=_frames(),
        ocr_records=[],
        transcript=[],
    )
    assert loaded == [
        "showlab/ShowUI-2B",
        "ByteDance-Seed/UI-TARS-2B-SFT",
        "ui-tars-7b",
    ]
    assert report["primary_evaluation"]["passed"] is False
    assert report["secondary_small_evaluation"]["passed"] is False
    assert report["large_fallback_evaluation"]["passed"] is True
    assert model.model_id == "ByteDance-Seed/UI-TARS-7B-SFT"


def test_missing_small_models_do_not_trigger_unmeasured_large_fallback(tmp_path, monkeypatch):
    import aios_work_system.video_extraction.model_router as router

    def missing(_repo, path, **_kwargs):
        raise router.LocalModelUnavailable(f"missing {path}")

    class Forbidden7B:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("7B cannot load when no 2B result was measured")

    monkeypatch.setattr(router, "ensure_hf_snapshot", missing)
    monkeypatch.setattr(router, "UITARS7BGrounder", Forbidden7B)
    model, report, _cached = route_ui_grounder(
        primary_model_path="missing-showui",
        secondary_small_model_path="missing-ui-tars-2b",
        fallback_model_path="ui-tars-7b",
        allow_download=False,
        benchmark_path=_benchmark(tmp_path / "benchmark.json"),
        frames=_frames(),
        ocr_records=[],
        transcript=[],
    )
    assert model is None
    assert report["status"] == "small_models_not_measured"
    assert report["large_fallback_evaluation"] is None


def test_decision_quality_gate_rejects_unknown_evidence_refs(tmp_path):
    episode = _episode(tmp_path / "video.webm")
    decision = _decision()
    decision["evidence_refs"] = ["not-in-episode"]
    valid, errors = _decision_quality_check(
        episode,
        decision,
        {"ev-observed-video"},
    )
    assert not valid
    assert any("evidence references" in error for error in errors)


def test_aurum_4b_pass_prevents_deepseek_9b_escalation(tmp_path, monkeypatch):
    import aios_work_system.video_extraction.model_router as router

    episode = _episode(tmp_path / "video.webm")
    small_model_decision = _decision()
    loaded = []

    class FakeLocalGGUF:
        def __init__(self, model_path, *, model_id, license, **_kwargs):
            self.model_id = model_id
            loaded.append(model_id)

        def synthesize_decision(self, **_kwargs):
            return {
                "decision": small_model_decision,
                "json_parse_valid": True,
                "generation_attempted": True,
                "generation_output_received": True,
                "model_id": self.model_id,
                "model_license": "Apache-2.0",
                "local_only": True,
                "latency_ms": 5,
            }

    monkeypatch.setattr(router, "local_model_file", lambda path, **_kw: Path(str(path)))
    monkeypatch.setattr(router, "LocalGGUFDecisionModel", FakeLocalGGUF)
    result, report = synthesize_episode_decision(
        episode=episode,
        transcript=[],
        frames=[],
        ocr_records=[],
        cursor_events=[],
        grounding_results=[],
        small_model_path="aurum.gguf",
        fallback_model_path="deepseek.gguf",
        allow_download=False,
    )
    assert report["status"] == "completed"
    assert report["selected_model_id"] == router.EPISODE_SMALL_MODEL_ID
    assert report["fallback_attempt"] is None
    assert loaded == [router.EPISODE_SMALL_MODEL_ID]
    assert result["decision"] == small_model_decision


def test_invalid_aurum_json_response_triggers_deepseek_9b_fallback(tmp_path, monkeypatch):
    import aios_work_system.video_extraction.model_router as router

    episode = _episode(tmp_path / "video.webm")
    loaded = []

    class FakeLocalGGUF:
        def __init__(self, model_path, *, model_id, license, **_kwargs):
            self.model_id = model_id
            loaded.append(model_id)

        def synthesize_decision(self, **_kwargs):
            if self.model_id == router.EPISODE_SMALL_MODEL_ID:
                return {
                    "decision": None,
                    "json_parse_valid": False,
                    "generation_attempted": True,
                    "generation_output_received": True,
                    "raw_response": "not valid JSON",
                }
            return {
                "decision": _decision(),
                "json_parse_valid": True,
                "generation_attempted": True,
                "generation_output_received": True,
                "model_id": self.model_id,
                "model_license": "Apache-2.0",
                "local_only": True,
                "latency_ms": 8,
            }

    monkeypatch.setattr(router, "local_model_file", lambda path, **_kw: Path(str(path)))
    monkeypatch.setattr(router, "LocalGGUFDecisionModel", FakeLocalGGUF)
    result, report = synthesize_episode_decision(
        episode=episode,
        transcript=[],
        frames=[],
        ocr_records=[],
        cursor_events=[],
        grounding_results=[],
        small_model_path="aurum.gguf",
        fallback_model_path="deepseek.gguf",
        allow_download=False,
    )
    assert loaded == [
        router.EPISODE_SMALL_MODEL_ID,
        router.EPISODE_FALLBACK_MODEL_ID,
    ]
    assert report["status"] == "completed_with_fallback"
    assert report["primary_attempt"]["json_parse_valid"] is False
    assert result["decision"] == _decision()


def test_unloadable_aurum_does_not_trigger_large_model_without_measured_output(
    tmp_path,
    monkeypatch,
):
    import aios_work_system.video_extraction.model_router as router

    episode = _episode(tmp_path / "video.webm")

    def local_path(_model_path, *, allow_download, fallback):
        if not fallback:
            raise router.LocalModelUnavailable("Aurum model weights are not present")
        return Path("deepseek.gguf")

    monkeypatch.setattr(router, "local_model_file", local_path)

    class ForbiddenFallback:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("9B must not load without a measured 4B output")

    monkeypatch.setattr(router, "LocalGGUFDecisionModel", ForbiddenFallback)
    result, report = synthesize_episode_decision(
        episode=episode,
        transcript=[],
        frames=[],
        ocr_records=[],
        cursor_events=[],
        grounding_results=[],
        small_model_path="aurum.gguf",
        fallback_model_path="deepseek.gguf",
        allow_download=False,
    )
    assert report["status"] == "primary_model_not_measured"
    assert report["fallback_attempt"]["status"] == "not_triggered"
    assert result["task"]["business_constraints"] == []
