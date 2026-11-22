"""Measured small-first model routing for local video grounding and episode synthesis."""

from __future__ import annotations

import copy
import json
import math
import time
from pathlib import Path
from typing import Any

from aios_work_system.video_extraction.local_models import (
    EPISODE_FALLBACK_GGUF_NAME,
    EPISODE_FALLBACK_MODEL_ID,
    EPISODE_SMALL_GGUF_NAME,
    EPISODE_SMALL_GGUF_REPO,
    EPISODE_SMALL_MODEL_ID,
    SHOWUI_MODEL_ID,
    UI_TARS_FALLBACK_MODEL_ID,
    UI_TARS_SMALL_MODEL_ID,
    LocalGGUFDecisionModel,
    LocalModelUnavailable,
    ShowUI2BGrounder,
    UITARS2BGrounder,
    UITARS7BGrounder,
    ensure_hf_file,
    ensure_hf_snapshot,
)


def _nearest_ocr_record(
    ocr_records: list[dict[str, Any]],
    timestamp_ms: int,
) -> dict[str, Any] | None:
    if not ocr_records:
        return None
    selected = min(
        ocr_records,
        key=lambda record: abs(int(record.get("timestamp_ms", 0)) - timestamp_ms),
    )
    if abs(int(selected.get("timestamp_ms", 0)) - timestamp_ms) > 1800:
        return None
    return selected


def _narration_context(
    transcript: list[dict[str, Any]],
    timestamp_ms: int,
    window_ms: int = 3500,
) -> str:
    return " ".join(
        str(segment.get("text", ""))
        for segment in transcript
        if int(segment.get("start_ms", 0)) - window_ms
        <= timestamp_ms
        <= int(segment.get("end_ms", 0)) + window_ms
    )


def _normalized_bbox_contains(
    point: list[float] | None,
    bbox: list[float],
) -> bool:
    if not point or len(bbox) != 4:
        return False
    x, y = point
    x1, y1, x2, y2 = bbox
    return x1 <= x <= x2 and y1 <= y <= y2


def _center_error(point: list[float] | None, bbox: list[float]) -> float | None:
    if not point or len(bbox) != 4:
        return None
    center_x = (bbox[0] + bbox[2]) / 2
    center_y = (bbox[1] + bbox[3]) / 2
    return math.dist(point, [center_x, center_y])


def evaluate_grounder(
    grounder: Any,
    frames: list[dict[str, Any]],
    annotations: list[dict[str, Any]],
    ocr_records: list[dict[str, Any]],
    transcript: list[dict[str, Any]],
) -> dict[str, Any]:
    """Measure point-in-target-box hit rate on manually annotated changed frames."""
    frame_by_timestamp = {int(frame["timestamp_ms"]): frame for frame in frames}
    predictions = []
    hits = 0
    valid = 0
    errors = []
    for annotation in annotations:
        timestamp_ms = int(annotation["timestamp_ms"])
        frame = frame_by_timestamp.get(timestamp_ms)
        if frame is None or not frame.get("is_change"):
            predictions.append(
                {
                    "timestamp_ms": timestamp_ms,
                    "status": "annotation_frame_not_found_or_not_changed",
                    "hit": False,
                }
            )
            continue
        ocr_record = _nearest_ocr_record(ocr_records, timestamp_ms)
        ocr_text = str(ocr_record.get("text", "")) if ocr_record else ""
        narration = _narration_context(transcript, timestamp_ms)
        try:
            result = grounder.ground(
                frame["path"],
                timestamp_ms,
                str(annotation["query"]),
                ocr_text,
                narration,
            )
        except Exception as exc:
            result = {
                "status": "failed",
                "timestamp_ms": timestamp_ms,
                "error": f"{type(exc).__name__}: {exc}",
            }
        point = result.get("point_norm")
        bbox = [float(value) for value in annotation["target_bbox_norm"]]
        hit = _normalized_bbox_contains(point, bbox)
        error = _center_error(point, bbox)
        valid += int(point is not None)
        hits += int(hit)
        if error is not None:
            errors.append(error)
        predictions.append(
            {
                **result,
                "timestamp_ms": timestamp_ms,
                "expected_label": annotation["target_label"],
                "expected_bbox_norm": bbox,
                "hit": hit,
                "normalized_center_error": round(error, 5) if error is not None else None,
            }
        )
    samples = len(annotations)
    hit_rate = hits / samples if samples else 0.0
    coordinate_rate = valid / samples if samples else 0.0
    return {
        "status": "completed" if samples else "no_annotations",
        "model_id": grounder.model_id,
        "parameter_class": grounder.parameter_class,
        "license": grounder.license,
        "samples": samples,
        "valid_coordinate_predictions": valid,
        "coordinate_parse_rate": round(coordinate_rate, 4),
        "target_box_hits": hits,
        "target_box_hit_rate": round(hit_rate, 4),
        "mean_normalized_center_error": (round(sum(errors) / len(errors), 5) if errors else None),
        "pass_threshold": 0.75,
        "passed": bool(samples and hit_rate >= 0.75 and coordinate_rate >= 0.95),
        "metric_definition": (
            "A prediction is a hit when its normalized point falls inside the manually "
            "annotated target element bounding box. This is target-localization accuracy, "
            "not click-event accuracy."
        ),
        "predictions": predictions,
    }


def _map_point_to_ocr_label(
    result: dict[str, Any],
    ocr_record: dict[str, Any] | None,
    frame_width: int,
    frame_height: int,
) -> dict[str, Any]:
    point = result.get("point_norm")
    if not point or not ocr_record:
        return result
    px, py = point[0] * frame_width, point[1] * frame_height
    best: tuple[float, dict[str, Any]] | None = None
    for region in ocr_record.get("regions", []):
        bbox = region.get("bbox", {})
        x1 = float(bbox.get("x", 0))
        y1 = float(bbox.get("y", 0))
        x2 = x1 + float(bbox.get("width", 0))
        y2 = y1 + float(bbox.get("height", 0))
        distance_x = max(x1 - px, 0.0, px - x2)
        distance_y = max(y1 - py, 0.0, py - y2)
        distance = math.hypot(distance_x, distance_y)
        if best is None or distance < best[0]:
            best = (distance, region)
    if best and best[0] <= 140:
        result["matched_ocr_text"] = best[1].get("text")
        result["matched_ocr_distance_px"] = round(best[0], 1)
    else:
        result["matched_ocr_text"] = None
        result["matched_ocr_distance_px"] = round(best[0], 1) if best else None
    result["visible_ui_element"] = (
        f"UI element near OCR text '{result['matched_ocr_text']}'"
        if result.get("matched_ocr_text")
        else "unlabeled UI region"
    )
    result["certainty"] = "inferred_from_video"
    return result


def route_ui_grounder(
    *,
    primary_model_path: str | Path | None,
    secondary_small_model_path: str | Path | None,
    fallback_model_path: str | Path | None,
    allow_download: bool,
    benchmark_path: str | Path | None,
    frames: list[dict[str, Any]],
    ocr_records: list[dict[str, Any]],
    transcript: list[dict[str, Any]],
    minimum_accuracy: float = 0.75,
) -> tuple[Any | None, dict[str, Any], dict[int, dict[str, Any]]]:
    """Test ShowUI-2B, then UI-TARS-2B; load UI-TARS-7B only after measured small-model failure."""
    annotations: list[dict[str, Any]] = []
    benchmark_meta: dict[str, Any] = {}
    if benchmark_path and Path(benchmark_path).is_file():
        payload = json.loads(Path(benchmark_path).read_text(encoding="utf-8"))
        benchmark_meta = {
            "benchmark_id": payload.get("benchmark_id"),
            "annotation_source": payload.get("annotation_source"),
            "video_id": payload.get("video_id"),
        }
        annotations = list(payload.get("annotations", []))

    stage: dict[str, Any] = {
        "status": "not_run",
        "small_models_first": True,
        "primary_model_id": SHOWUI_MODEL_ID,
        "primary_license": "MIT",
        "secondary_small_model_id": UI_TARS_SMALL_MODEL_ID,
        "secondary_small_license": "Apache-2.0",
        "large_fallback_model_id": UI_TARS_FALLBACK_MODEL_ID,
        "large_fallback_license": "Apache-2.0",
        "local_only_inference": True,
        "external_inference_provider_calls": 0,
        "benchmark": benchmark_meta,
        "metric": "point_in_manually_annotated_target_bbox",
        "pass_threshold": minimum_accuracy,
        "large_fallback_trigger": (
            "at least one 2B model was actually measured and both available 2B models "
            "scored below the target_box_hit_rate threshold"
        ),
        "primary_evaluation": None,
        "secondary_small_evaluation": None,
        "large_fallback_evaluation": None,
        "selected_model_id": None,
        "selection_reason": None,
    }
    cached: dict[int, dict[str, Any]] = {}
    if not annotations:
        stage.update(
            {
                "status": "benchmark_required",
                "error": (
                    "No human-annotated target-box benchmark was supplied; "
                    "model inference is not run without a scoreable evaluation set."
                ),
            }
        )
        return None, stage, cached

    candidate_models: list[tuple[Any, dict[str, Any]]] = []
    primary = None
    primary_eval = None
    try:
        if not primary_model_path:
            raise LocalModelUnavailable("ShowUI-2B local model path was not configured")
        path = ensure_hf_snapshot(
            SHOWUI_MODEL_ID,
            primary_model_path,
            allow_download=allow_download,
        )
        primary = ShowUI2BGrounder(path, local_files_only=True)
        primary_eval = evaluate_grounder(
            primary,
            frames,
            annotations,
            ocr_records,
            transcript,
        )
        primary_eval["pass_threshold"] = minimum_accuracy
        primary_eval["passed"] = bool(
            primary_eval["samples"]
            and primary_eval["target_box_hit_rate"] >= minimum_accuracy
            and primary_eval["coordinate_parse_rate"] >= 0.95
        )
        stage["primary_evaluation"] = primary_eval
        candidate_models.append((primary, primary_eval))
    except Exception as exc:
        stage["primary_evaluation"] = {
            "status": "load_or_evaluation_failed",
            "model_id": SHOWUI_MODEL_ID,
            "parameter_class": "2B",
            "license": "MIT",
            "error": f"{type(exc).__name__}: {exc}",
            "measured_samples": 0,
        }

    selected = primary if primary_eval and primary_eval.get("passed") else None
    selected_eval = primary_eval if selected else None
    if selected is None:
        secondary = None
        secondary_eval = None
        try:
            if not secondary_small_model_path:
                raise LocalModelUnavailable("UI-TARS-2B local model path was not configured")
            path = ensure_hf_snapshot(
                UI_TARS_SMALL_MODEL_ID,
                secondary_small_model_path,
                allow_download=allow_download,
            )
            secondary = UITARS2BGrounder(path, local_files_only=True)
            secondary_eval = evaluate_grounder(
                secondary,
                frames,
                annotations,
                ocr_records,
                transcript,
            )
            secondary_eval["pass_threshold"] = minimum_accuracy
            secondary_eval["passed"] = bool(
                secondary_eval["samples"]
                and secondary_eval["target_box_hit_rate"] >= minimum_accuracy
                and secondary_eval["coordinate_parse_rate"] >= 0.95
            )
            stage["secondary_small_evaluation"] = secondary_eval
            candidate_models.append((secondary, secondary_eval))
        except Exception as exc:
            stage["secondary_small_evaluation"] = {
                "status": "load_or_evaluation_failed",
                "model_id": UI_TARS_SMALL_MODEL_ID,
                "parameter_class": "2B",
                "license": "Apache-2.0",
                "error": f"{type(exc).__name__}: {exc}",
                "measured_samples": 0,
            }
        if secondary_eval and secondary_eval.get("passed"):
            selected = secondary
            selected_eval = secondary_eval

    measured_small_models = [
        (model, evaluation)
        for model, evaluation in candidate_models
        if int(evaluation.get("samples", 0)) > 0
    ]
    if selected is None and measured_small_models:
        # A 7B model is not loaded because a small model failed to import;
        # it is loaded only after real small-model scores miss the threshold.
        large = None
        large_eval = None
        try:
            if not fallback_model_path:
                raise LocalModelUnavailable("UI-TARS-7B fallback path was not configured")
            path = ensure_hf_snapshot(
                UI_TARS_FALLBACK_MODEL_ID,
                fallback_model_path,
                allow_download=allow_download,
            )
            large = UITARS7BGrounder(path, local_files_only=True)
            large_eval = evaluate_grounder(
                large,
                frames,
                annotations,
                ocr_records,
                transcript,
            )
            large_eval["pass_threshold"] = minimum_accuracy
            large_eval["passed"] = bool(
                large_eval["samples"]
                and large_eval["target_box_hit_rate"] >= minimum_accuracy
                and large_eval["coordinate_parse_rate"] >= 0.95
            )
            stage["large_fallback_evaluation"] = large_eval
            if large_eval.get("passed"):
                selected = large
                selected_eval = large_eval
            else:
                stage["large_fallback_selection"] = "below_threshold"
        except Exception as exc:
            stage["large_fallback_evaluation"] = {
                "status": "load_or_evaluation_failed",
                "model_id": UI_TARS_FALLBACK_MODEL_ID,
                "parameter_class": "7B",
                "license": "Apache-2.0",
                "error": f"{type(exc).__name__}: {exc}",
                "measured_samples": 0,
            }

    if selected is None and candidate_models:
        selected, selected_eval = max(
            candidate_models,
            key=lambda pair: float(pair[1].get("target_box_hit_rate", 0.0)),
        )
        stage["selection_reason"] = (
            "All measured small models and any measured large fallback missed the target "
            "threshold; the highest-scoring measured model is retained but flagged."
        )
    elif selected is None:
        stage["selection_reason"] = (
            "No small model could be measured. A larger model was deliberately not loaded "
            "because there was no small-model accuracy result to justify escalation."
        )
    elif selected.model_id == SHOWUI_MODEL_ID:
        stage["selection_reason"] = (
            "ShowUI-2B met the localization threshold; no larger model was loaded."
        )
    elif selected.model_id == UI_TARS_SMALL_MODEL_ID:
        stage["selection_reason"] = (
            "ShowUI-2B did not meet the threshold; UI-TARS-2B passed, so no 7B model was loaded."
        )
    else:
        stage["selection_reason"] = (
            "Both measured 2B models missed the threshold; UI-TARS-7B was evaluated as fallback."
        )

    if selected_eval:
        stage["status"] = "completed" if selected_eval.get("passed") else "below_threshold"
        stage["selected_model_id"] = selected.model_id
        stage["selected_model_evaluation"] = selected_eval
        for prediction in selected_eval.get("predictions", []):
            if prediction.get("point_norm") and prediction.get("timestamp_ms") is not None:
                cached[int(prediction["timestamp_ms"])] = prediction
    else:
        stage["status"] = "small_models_not_measured"
    return selected, stage, cached


def run_ui_grounding(
    *,
    primary_model_path: str | Path | None,
    secondary_small_model_path: str | Path | None,
    fallback_model_path: str | Path | None,
    benchmark_path: str | Path | None,
    allow_download: bool,
    frames: list[dict[str, Any]],
    ocr_records: list[dict[str, Any]],
    transcript: list[dict[str, Any]],
    maximum_frames: int,
    frame_dimensions: tuple[int, int],
    minimum_accuracy: float = 0.75,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Evaluate 2B models first, then localize only selected changed frames."""
    grounder, stage, cached = route_ui_grounder(
        primary_model_path=primary_model_path,
        secondary_small_model_path=secondary_small_model_path,
        fallback_model_path=fallback_model_path,
        allow_download=allow_download,
        benchmark_path=benchmark_path,
        frames=frames,
        ocr_records=ocr_records,
        transcript=transcript,
        minimum_accuracy=minimum_accuracy,
    )
    changed_frames = [frame for frame in frames if frame.get("is_change")]
    selected_by_timestamp = {
        int(frame["timestamp_ms"]): frame for frame in changed_frames[:maximum_frames]
    }
    # Keep manually scored benchmark frames in the episode even when outside the first-N window.
    for timestamp_ms in cached:
        frame = next(
            (item for item in changed_frames if int(item["timestamp_ms"]) == int(timestamp_ms)),
            None,
        )
        if frame is not None:
            selected_by_timestamp[int(timestamp_ms)] = frame
    selected_frames = [selected_by_timestamp[key] for key in sorted(selected_by_timestamp)]
    results: list[dict[str, Any]] = []
    if grounder is None:
        stage["frames_submitted"] = 0
        stage["candidate_changed_frames"] = len(changed_frames)
        stage["selected_changed_frame_timestamps_ms"] = []
        return results, stage

    width, height = frame_dimensions
    fresh_inference_count = 0
    reused_benchmark_count = 0
    try:
        for index, frame in enumerate(selected_frames, start=1):
            timestamp_ms = int(frame["timestamp_ms"])
            if timestamp_ms in cached:
                result = dict(cached[timestamp_ms])
                result["reused_benchmark_prediction"] = True
                reused_benchmark_count += 1
            else:
                ocr_record = _nearest_ocr_record(ocr_records, timestamp_ms)
                ocr_text = str(ocr_record.get("text", "")) if ocr_record else ""
                narration = _narration_context(transcript, timestamp_ms)
                query = (
                    "Identify the clickable UI control or text-entry region most directly "
                    "associated with the visible screen change at this timestamp. Use nearby "
                    "narration and OCR only as context; do not claim that a click was observed. "
                    f"Narration: {narration[:1400]}. OCR: {ocr_text[:1400]}."
                )
                fresh_inference_count += 1
                try:
                    result = grounder.ground(
                        frame["path"],
                        timestamp_ms,
                        query,
                        ocr_text,
                        narration,
                    )
                except Exception as exc:
                    result = {
                        "status": "failed",
                        "timestamp_ms": timestamp_ms,
                        "frame_path": frame["path"],
                        "error": f"{type(exc).__name__}: {exc}",
                    }
            result["grounding_index"] = index
            result["event_id"] = f"ui-grounding-{index:04d}"
            result["certainty"] = "inferred_from_video"
            result["source"] = "local_open_weight_ui_grounding"
            result = _map_point_to_ocr_label(
                result,
                _nearest_ocr_record(ocr_records, timestamp_ms),
                width,
                height,
            )
            results.append(result)
    finally:
        # Do not keep the 2B/7B vision model resident while loading the 4B text model.
        del grounder
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    completed = sum(item.get("point_norm") is not None for item in results)
    stage["frames_submitted"] = fresh_inference_count
    stage["benchmark_predictions_reused"] = reused_benchmark_count
    stage["unique_changed_frames_reported"] = len(selected_frames)
    stage["candidate_changed_frames"] = len(changed_frames)
    stage["frames_omitted_by_configured_cap"] = max(
        0, len(changed_frames) - len(changed_frames[:maximum_frames])
    )
    stage["completed"] = completed
    stage["failed"] = len(results) - completed
    stage["selected_changed_frame_timestamps_ms"] = [
        int(frame["timestamp_ms"]) for frame in selected_frames
    ]
    stage["selection_rule"] = "only frame_change.is_change == true"
    stage["runtime_model_id"] = stage.get("selected_model_id")
    stage["runtime_inference_backend"] = "transformers_local"
    stage["local_only"] = True
    stage["runtime_status"] = "completed" if completed else "failed"
    return results, stage


def local_model_file(
    model_path: str | Path | None,
    *,
    allow_download: bool,
    fallback: bool = False,
) -> Path:
    """Resolve local primary or fallback GGUF weights."""
    if fallback:
        target = (
            Path(model_path) if model_path else Path("artifacts/models/deepseek-v4-pro-9b-q4.gguf")
        )
        return ensure_hf_file(
            EPISODE_FALLBACK_MODEL_ID,
            EPISODE_FALLBACK_GGUF_NAME,
            target,
            allow_download=allow_download,
        )
    target = Path(model_path) if model_path else Path("artifacts/models/aurum-4b-q4.gguf")
    return ensure_hf_file(
        EPISODE_SMALL_GGUF_REPO,
        EPISODE_SMALL_GGUF_NAME,
        target,
        allow_download=allow_download,
    )


def _decision_quality_check(
    episode: dict[str, Any],
    decision: Any,
    allowed_evidence_ids: set[str],
) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not isinstance(decision, dict):
        return False, ["decision output is not a JSON object"]
    required = {
        "decision_type",
        "selected_strategy",
        "rationale_summary",
        "decision_basis",
        "applicable_conditions",
        "selected_next_step",
        "alternatives_considered",
        "uncertainties",
        "evidence_refs",
    }
    missing = sorted(required - set(decision))
    if missing:
        errors.append(f"missing decision keys: {missing}")
    refs = decision.get("evidence_refs", [])
    if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
        errors.append("evidence_refs must be an array of strings")
    elif not set(refs).issubset(allowed_evidence_ids):
        errors.append("decision contains evidence references not present in this episode")
    if decision.get("applicable_conditions") != []:
        errors.append("video-only automatic synthesis may not invent applicable conditions")
    basis = decision.get("decision_basis", [])
    if (
        not isinstance(basis, list)
        or not basis
        or any(item not in {"behavioral_inference", "unknown"} for item in basis)
    ):
        errors.append("decision_basis must be behavioral_inference or unknown")
    next_step = decision.get("selected_next_step")
    if (
        not isinstance(next_step, dict)
        or next_step.get("action") != "ask_user"
        or not str(next_step.get("objective", "")).strip()
    ):
        errors.append("video-only synthesis must leave the next step for human review")
    if episode.get("task", {}).get("business_constraints") != []:
        errors.append("synthesized decision must not add business constraints")

    candidate = copy.deepcopy(episode)
    if not errors:
        candidate["decision"] = decision
        try:
            from contracts.validate import validate_episode

            schema_errors = validate_episode(candidate)
        except Exception as exc:
            schema_errors = [f"{type(exc).__name__}: {exc}"]
        if schema_errors:
            errors.extend(schema_errors)
    return not errors, errors


def _compact_synthesis_text(value: Any, maximum_chars: int) -> str:
    return " ".join(str(value or "").split())[:maximum_chars]


def _build_episode_synthesis_context(
    *,
    episode: dict[str, Any],
    transcript: list[dict[str, Any]],
    frames: list[dict[str, Any]],
    ocr_records: list[dict[str, Any]],
    cursor_events: list[dict[str, Any]],
    grounding_results: list[dict[str, Any]],
    allowed_ids: set[str],
) -> dict[str, Any]:
    """Build a bounded, evidence-linked context instead of dumping every OCR frame."""
    changed_frames = [frame for frame in frames if frame.get("is_change")]
    observed_frame_changes = [
        {
            "event_id": f"frame-change-{int(frame['frame_index']):06d}"
            if frame.get("frame_index") is not None
            else f"frame-change-{int(frame['timestamp_ms']):09d}",
            "timestamp_ms": int(frame["timestamp_ms"]),
        }
        for frame in changed_frames[:64]
    ]

    grounding_timestamps = [
        int(item["timestamp_ms"])
        for item in grounding_results
        if item.get("timestamp_ms") is not None
    ]
    if not grounding_timestamps:
        grounding_timestamps = [int(frame["timestamp_ms"]) for frame in changed_frames[:12]]

    ocr_observations: list[dict[str, Any]] = []
    seen_ocr_timestamps: set[int] = set()
    for frame_timestamp in grounding_timestamps[:16]:
        record = _nearest_ocr_record(ocr_records, frame_timestamp)
        if record is None:
            continue
        record_timestamp = int(record["timestamp_ms"])
        if record_timestamp in seen_ocr_timestamps:
            continue
        visible_text = _compact_synthesis_text(record.get("text", ""), 320)
        if not visible_text:
            continue
        seen_ocr_timestamps.add(record_timestamp)
        ocr_observations.append(
            {
                "timestamp_ms": record_timestamp,
                "observed_for_frame_ms": frame_timestamp,
                "visible_text": visible_text,
            }
        )

    return {
        "source_id": episode.get("source", {}).get("source_id"),
        "duration_ms": episode.get("source", {}).get("source_duration_ms"),
        "observed_frame_changes": observed_frame_changes,
        "ocr_observations": ocr_observations,
        "inferred_cursor_actions": [
            {
                "event_id": item.get("event_id"),
                "timestamp_ms": item.get("timestamp_ms"),
                "certainty": "inferred_from_video",
                "confidence": item.get("confidence"),
            }
            for item in cursor_events[:24]
        ],
        "ui_target_hypotheses": [
            {
                "event_id": item.get("event_id"),
                "timestamp_ms": item.get("timestamp_ms"),
                "point_norm": item.get("point_norm"),
                "visible_ui_element": _compact_synthesis_text(item.get("visible_ui_element"), 120),
                "matched_ocr_text": _compact_synthesis_text(item.get("matched_ocr_text"), 160),
                "model_id": item.get("model_id"),
                "certainty": "inferred_from_video",
            }
            for item in grounding_results[:24]
        ],
        "instructor_words": [
            {
                "segment_id": item.get("segment_id"),
                "start_ms": item.get("start_ms"),
                "end_ms": item.get("end_ms"),
                "text": _compact_synthesis_text(item.get("text"), 220),
            }
            for item in transcript[:48]
        ],
        "evidence_ids": sorted(allowed_ids),
        "default_decision": episode.get("decision"),
        "business_constraints": [],
        "outcome_status": "not_verified",
        "operation_execution_status": "not_observed",
    }


def synthesize_episode_decision(
    *,
    episode: dict[str, Any],
    transcript: list[dict[str, Any]],
    frames: list[dict[str, Any]],
    ocr_records: list[dict[str, Any]],
    cursor_events: list[dict[str, Any]],
    grounding_results: list[dict[str, Any]],
    small_model_path: str | Path | None,
    fallback_model_path: str | Path | None,
    allow_download: bool,
    n_gpu_layers: int = -1,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Measure local Aurum-4B first; 9B fallback requires a generated, invalid 4B response."""
    allowed_ids = {item["evidence_id"] for item in episode.get("evidence", [])}
    structured_context = _build_episode_synthesis_context(
        episode=episode,
        transcript=transcript,
        frames=frames,
        ocr_records=ocr_records,
        cursor_events=cursor_events,
        grounding_results=grounding_results,
        allowed_ids=allowed_ids,
    )
    structured_context_chars = len(
        json.dumps(structured_context, ensure_ascii=False, separators=(",", ":"))
    )
    report: dict[str, Any] = {
        "small_model_first": True,
        "primary_model_id": EPISODE_SMALL_MODEL_ID,
        "primary_parameter_class": "4B",
        "primary_license": "Apache-2.0",
        "fallback_model_id": EPISODE_FALLBACK_MODEL_ID,
        "fallback_parameter_class": "9B",
        "fallback_license": "Apache-2.0",
        "inference_backend": "llama.cpp local GGUF",
        "local_only": True,
        "external_inference_provider_calls": 0,
        "input_context_chars": structured_context_chars,
        "input_context_policy": (
            "OCR is selected only near grounded changed frames; transcript, cursor, and "
            "grounding context are bounded before local 4B synthesis."
        ),
        "primary_attempt": None,
        "fallback_attempt": None,
        "selected_model_id": None,
        "fallback_trigger": (
            "only after Aurum-4B has loaded and generated a response that fails JSON, "
            "semantic or DecisionEpisode validation"
        ),
    }

    def attempt(
        model_path: str | Path | None,
        *,
        model_id: str,
        license_name: str,
        fallback: bool,
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        started = time.perf_counter()
        model_loaded = False
        generation_attempted = False
        try:
            resolved = local_model_file(
                model_path,
                allow_download=allow_download,
                fallback=fallback,
            )
            model = LocalGGUFDecisionModel(
                resolved,
                model_id=model_id,
                license=license_name,
                n_gpu_layers=n_gpu_layers,
            )
            model_loaded = True
            generation_attempted = True
            generated = model.synthesize_decision(
                episode_context=structured_context,
                allowed_evidence_ids=sorted(allowed_ids),
            )
            generation_output_received = bool(generated.get("generation_output_received"))
            json_parse_valid = generated.get("json_parse_valid") is True
            decision = generated.get("decision")
            if not json_parse_valid or not isinstance(decision, dict):
                return None, {
                    **{key: value for key, value in generated.items() if key != "decision"},
                    "status": "rejected",
                    "model_loaded": True,
                    "generation_attempted": True,
                    "generation_output_received": generation_output_received,
                    "json_parse_valid": False,
                    "decision_quality_valid": False,
                    "decision_episode_contract_valid": False,
                    "quality_errors": [
                        "small model did not return a parseable decision JSON object"
                    ],
                    "latency_ms_total": round((time.perf_counter() - started) * 1000, 2),
                }
            valid, errors = _decision_quality_check(episode, decision, allowed_ids)
            result = {
                **{key: value for key, value in generated.items() if key != "decision"},
                "status": "passed" if valid else "rejected",
                "model_loaded": True,
                "generation_attempted": True,
                "generation_output_received": generation_output_received,
                "json_parse_valid": True,
                "decision_quality_valid": valid,
                "decision_episode_contract_valid": valid,
                "quality_errors": errors,
                "latency_ms_total": round((time.perf_counter() - started) * 1000, 2),
                "business_constraints_preserved_empty": (
                    episode.get("task", {}).get("business_constraints") == []
                ),
                "evidence_reference_precision": (
                    1.0
                    if isinstance(decision.get("evidence_refs"), list)
                    and set(decision["evidence_refs"]).issubset(allowed_ids)
                    else 0.0
                ),
            }
            return decision if valid else None, result
        except Exception as exc:
            return None, {
                "status": "failed",
                "model_id": model_id,
                "model_license": license_name,
                "model_loaded": model_loaded,
                "generation_attempted": generation_attempted,
                "generation_output_received": False,
                "json_parse_valid": None,
                "decision_quality_valid": False,
                "decision_episode_contract_valid": False,
                "error": f"{type(exc).__name__}: {exc}",
                "latency_ms_total": round((time.perf_counter() - started) * 1000, 2),
            }

    small_decision, small_report = attempt(
        small_model_path,
        model_id=EPISODE_SMALL_MODEL_ID,
        license_name="Apache-2.0",
        fallback=False,
    )
    report["primary_attempt"] = small_report
    if small_decision is not None:
        episode["decision"] = small_decision
        report["selected_model_id"] = EPISODE_SMALL_MODEL_ID
        report["status"] = "completed"
        report["fallback_reason"] = None
        return episode, report

    measured_primary_failure = bool(
        small_report.get("model_loaded")
        and small_report.get("generation_attempted")
        and small_report.get("generation_output_received")
    )
    if not measured_primary_failure:
        report["fallback_attempt"] = {
            "status": "not_triggered",
            "model_id": EPISODE_FALLBACK_MODEL_ID,
            "reason": (
                "Aurum-4B could not be loaded or did not complete a generation. "
                "No measured small-model quality failure exists to justify escalation."
            ),
        }
        report["status"] = "primary_model_not_measured"
        report["selected_model_id"] = "deterministic_code_fallback"
        return episode, report

    fallback_decision, fallback_report = attempt(
        fallback_model_path,
        model_id=EPISODE_FALLBACK_MODEL_ID,
        license_name="Apache-2.0",
        fallback=True,
    )
    report["fallback_attempt"] = fallback_report
    report["fallback_reason"] = small_report.get("quality_errors") or small_report.get("error")
    if fallback_decision is not None:
        episode["decision"] = fallback_decision
        report["selected_model_id"] = EPISODE_FALLBACK_MODEL_ID
        report["status"] = "completed_with_fallback"
    else:
        report["selected_model_id"] = "deterministic_code_fallback"
        report["status"] = "small_and_large_models_unavailable_or_invalid"
        report["deterministic_fallback_used"] = True
    return episode, report
