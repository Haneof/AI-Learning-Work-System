"""Compile dual-approved DecisionEpisodes into source-grouped conversational samples.

The compiler is intentionally conservative: review holds, missing evidence, invalid actions,
unsafe forced-execution labels, and decision-time leakage are excluded rather than repaired.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DECISION_ACTIONS = frozenset(
    {"delegate", "ask_user", "request_approval", "replan", "finish", "stop"}
)
LOCAL_GATE_LEVELS = ("extraction_fidelity", "decision_validity", "outcome_validity")
HAND_RESULT_STATUSES = frozenset({"success", "partial_success", "failure"})
APPROVED_ANNOTATION_STATES = frozenset({"human_reviewed", "gold"})
FUTURE_ONLY_KEYS = frozenset(
    {
        "future_result",
        "future_execution_result",
        "outcome",
        "state_after",
        "postcondition_checks",
        "result_after_decision",
        "operation_result",
        "next_execution_result",
    }
)
EXPLICIT_FUTURE_RESULT_KEYS = frozenset(
    {"future_result", "future_execution_result", "result_after_decision", "next_execution_result"}
)
EVIDENCE_METADATA_KEYS = frozenset(
    {
        "evidence_tier",
        "observation_channel",
        "rationale_source",
        "user_provided",
        "evidence_labels",
        "evidence_confidence",
    }
)
INPUT_FIELDS = (
    "goal",
    "current_state",
    "available_capabilities",
    "last_execution_result",
)
SYSTEM_PROMPT = (
    "You are the Brain in a Brain-to-Hands system. Choose exactly one next decision action: "
    "delegate, ask_user, request_approval, replan, finish, or stop. Use only information in "
    "the user message. Never invent missing state, permissions, capabilities, or results. "
    "When required information is missing or ambiguous, ask_user; never force execution. "
    "For delegation, select only a listed available capability. Return one JSON object with "
    "an action field and the decision details needed for that action. Do not claim an operation "
    "has succeeded unless the user-provided last_execution_result supports that conclusion."
)


@dataclass(frozen=True)
class CompilationResult:
    """Dataset records and their non-model metadata, kept in separate collections."""

    train_samples: list[dict[str, Any]] = field(default_factory=list)
    test_samples: list[dict[str, Any]] = field(default_factory=list)
    train_meta: list[dict[str, Any]] = field(default_factory=list)
    test_meta: list[dict[str, Any]] = field(default_factory=list)
    exclusions: list[dict[str, str]] = field(default_factory=list)
    split_manifest: dict[str, Any] = field(default_factory=dict)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_mapping(value: Any) -> bool:
    return isinstance(value, Mapping)


def _walk_forbidden(
    value: Any,
    path: str = "user",
    forbidden_keys: frozenset[str] = FUTURE_ONLY_KEYS,
) -> str | None:
    """Return the first forbidden key path found in a would-be model message."""
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if str(key).lower() in forbidden_keys:
                return f"{path}.{key}"
            found = _walk_forbidden(nested, f"{path}.{key}", forbidden_keys)
            if found:
                return found
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            found = _walk_forbidden(nested, f"{path}[{index}]", forbidden_keys)
            if found:
                return found
    return None


def _input_leak_path(user_payload: Mapping[str, Any]) -> str | None:
    """Check decision-time context but allow a genuinely prior Hands return object."""
    prior_result = user_payload.get("last_execution_result")
    decision_context = {
        key: value for key, value in user_payload.items() if key != "last_execution_result"
    }
    context_leak = _walk_forbidden(decision_context)
    if context_leak:
        return context_leak
    if prior_result is not None:
        return _walk_forbidden(
            prior_result,
            "user.last_execution_result",
            EXPLICIT_FUTURE_RESULT_KEYS,
        )
    return None


def _passes_local_gate(episode: Mapping[str, Any], report: Any) -> tuple[bool, str]:
    if not _is_mapping(report):
        return False, "local_verification_missing"
    if report.get("episode_id") != episode.get("episode_id"):
        return False, "local_verification_episode_id_mismatch"
    levels = report.get("levels")
    if report.get("overall_status") != "pass" or not _is_mapping(levels):
        return False, "local_verification_not_pass"
    if any(
        not _is_mapping(levels.get(name)) or levels[name].get("status") != "pass"
        for name in LOCAL_GATE_LEVELS
    ):
        return False, "local_verification_level_not_pass"
    return True, ""


def _passes_pm_gate(review: Any) -> tuple[bool, str]:
    if not _is_mapping(review):
        return False, "pm_independent_review_missing"
    source_refs = review.get("source_evidence_refs")
    record_refs = review.get("proposed_record_evidence_refs")
    refs_valid = (
        isinstance(source_refs, list)
        and bool(source_refs)
        and all(_is_nonempty_string(ref) for ref in source_refs)
        and isinstance(record_refs, list)
        and bool(record_refs)
        and all(_is_nonempty_string(ref) for ref in record_refs)
    )
    if review.get("status") != "pass" or not refs_valid:
        return False, "pm_independent_review_not_pass_or_missing_citations"
    return True, ""


def _passes_quality_gate(episode: Mapping[str, Any]) -> tuple[bool, str]:
    review = episode.get("review")
    quality = episode.get("quality")
    if (
        not _is_mapping(review)
        or review.get("status") != "approved"
        or review.get("approved_for_training") is not True
    ):
        return False, "episode_review_not_approved_for_training"
    if not _is_mapping(quality):
        return False, "episode_quality_missing"
    if (
        quality.get("annotation_status") not in APPROVED_ANNOTATION_STATES
        or quality.get("trainable") is not True
    ):
        return False, "episode_quality_not_trainable"
    if quality.get("exclusion_reasons") != []:
        return False, "episode_quality_exclusion_reasons_missing_or_nonempty"
    return True, ""


def _source_group(episode: Mapping[str, Any]) -> str:
    source = episode.get("source")
    if not _is_mapping(source):
        return ""
    for key in (
        "split_group_id",
        "course_id",
        "series_or_course",
        "sha256",
        "content_sha256",
        "source_id",
    ):
        value = source.get(key)
        if _is_nonempty_string(value):
            return f"{key}:{value.strip()}"
    return ""


def _decision_points(episode: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    points = episode.get("decision_points")
    if points is None:
        return [episode]
    if (
        not isinstance(points, list)
        or not points
        or not all(_is_mapping(point) for point in points)
    ):
        raise ValueError("decision_points must be a non-empty list of objects")
    return points


def _decision_for(episode: Mapping[str, Any], point: Mapping[str, Any]) -> Mapping[str, Any]:
    decision = point.get("decision", episode.get("decision"))
    if not _is_mapping(decision):
        raise ValueError("decision is missing")
    return decision


def _selected_next_step(decision: Mapping[str, Any], point: Mapping[str, Any]) -> Mapping[str, Any]:
    selected = point.get("selected_next_step", decision.get("selected_next_step"))
    if not _is_mapping(selected):
        raise ValueError("selected_next_step is missing")
    return selected


def _decision_input(
    episode: Mapping[str, Any], point: Mapping[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    task = point.get("task", episode.get("task", {}))
    goal = point.get("goal")
    if goal is None and _is_mapping(task):
        goal = task.get("goal")

    state = point.get("current_state")
    if state is None:
        state = point.get("state_before", episode.get("state_before"))

    capabilities = point.get("available_capabilities")
    if capabilities is None:
        capabilities = episode.get("available_capabilities")
    if capabilities is None and _is_mapping(episode.get("context")):
        capabilities = episode["context"].get("available_capabilities")

    last_result = point.get("last_execution_result")
    if last_result is None:
        hands = point.get("hands", episode.get("hands"))
        if _is_mapping(hands):
            last_result = hands.get("last_execution_result")

    missing: list[str] = []
    if not _is_nonempty_string(goal):
        missing.append("goal")
    if not _is_mapping(state) or not state:
        missing.append("current_state")
    if capabilities is None:
        capabilities = []
        missing.append("available_capabilities")
    elif not isinstance(capabilities, list):
        raise ValueError("available_capabilities must be a list")

    declared_missing = point.get("missing_information", point.get("unresolved_information", []))
    if declared_missing:
        if not isinstance(declared_missing, list) or not all(
            _is_nonempty_string(item) for item in declared_missing
        ):
            raise ValueError("missing_information must be a list of non-empty strings")
        missing.extend(item for item in declared_missing if item not in missing)

    if last_result is not None:
        if not _is_mapping(last_result):
            raise ValueError("last_execution_result must be an object or null")
        if last_result.get("status") not in HAND_RESULT_STATUSES:
            raise ValueError(
                "last_execution_result.status must be success, partial_success, or failure"
            )

    user_input = {
        "goal": goal if _is_nonempty_string(goal) else None,
        "current_state": dict(state) if _is_mapping(state) else None,
        "available_capabilities": list(capabilities),
        "last_execution_result": dict(last_result) if _is_mapping(last_result) else None,
    }
    return user_input, missing


def _target(
    decision: Mapping[str, Any],
    selected: Mapping[str, Any],
    missing: list[str],
    capabilities: list[Any],
) -> dict[str, Any]:
    action = selected.get("action")
    if action not in DECISION_ACTIONS:
        raise ValueError(f"decision action must be one of {sorted(DECISION_ACTIONS)}")
    if missing and action != "ask_user":
        raise ValueError(
            f"missing information {missing} must be handled with ask_user, not {action}"
        )

    target: dict[str, Any] = {"action": action}
    for key in (
        "objective",
        "question",
        "capability_id",
        "arguments",
        "approval_request",
        "reason",
    ):
        if key in selected:
            target[key] = selected[key]

    rationale = decision.get("rationale_summary")
    if _is_nonempty_string(rationale):
        target["rationale"] = rationale

    if action == "ask_user" and not _is_nonempty_string(target.get("question")):
        raise ValueError("ask_user target must include a non-empty question")
    if action == "delegate":
        capability_id = target.get("capability_id")
        if not _is_nonempty_string(capability_id):
            raise ValueError("delegate target must name a capability_id")
        available_ids = {
            item if isinstance(item, str) else item.get("capability_id")
            for item in capabilities
            if isinstance(item, str) or _is_mapping(item)
        }
        if capability_id not in available_ids:
            raise ValueError("delegate target capability_id is not in available_capabilities")
    return target


def _evidence_tier(
    episode: Mapping[str, Any],
    point: Mapping[str, Any],
    decision: Mapping[str, Any],
) -> tuple[dict[str, Any], float]:
    evidence_items = episode.get("evidence", [])
    if not isinstance(evidence_items, list):
        raise ValueError("episode.evidence must be a list")
    by_id = {
        item.get("evidence_id"): item
        for item in evidence_items
        if _is_mapping(item) and _is_nonempty_string(item.get("evidence_id"))
    }
    refs = point.get("evidence_refs", decision.get("evidence_refs", []))
    if not isinstance(refs, list) or not refs:
        raise ValueError("decision point must cite evidence_refs")
    missing_refs = [ref for ref in refs if ref not in by_id]
    if missing_refs:
        raise ValueError(f"decision evidence references do not resolve: {missing_refs}")
    selected_evidence = [by_id[ref] for ref in refs]

    observation_channels = sorted(
        {str(item.get("observation_channel", "unknown")) for item in selected_evidence}
    )
    rationale_sources = sorted(
        {str(item.get("rationale_source", "unknown")) for item in selected_evidence}
    )
    confidence: dict[str, float | None] = {}
    rationale_confidences: list[float] = []
    user_provided_ids: list[str] = []
    for evidence_id, item in zip(refs, selected_evidence, strict=True):
        score = item.get("confidence")
        if (
            isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not math.isfinite(score)
            or not 0 <= score <= 1
        ):
            score = None
        else:
            score = float(score)
        confidence[str(evidence_id)] = score
        if (
            item.get("rationale_source")
            in {"instructor_explicit", "behavioral_inference", "hybrid"}
            and score is not None
        ):
            rationale_confidences.append(score)
        labels = item.get("labels", [])
        is_user_provided = item.get("user_provided") is True or (
            isinstance(labels, list) and "user_provided" in labels
        )
        if is_user_provided:
            user_provided_ids.append(str(evidence_id))

    evidence_tier = {
        "observation_channel": observation_channels,
        "rationale_source": rationale_sources,
        "confidence": confidence,
        "user_provided": bool(user_provided_ids),
        "user_provided_evidence_ids": sorted(user_provided_ids),
    }
    rationale_loss_weight = (
        sum(rationale_confidences) / len(rationale_confidences) if rationale_confidences else 0.0
    )
    return evidence_tier, round(rationale_loss_weight, 6)


def _stable_sample_id(episode_id: str, point_id: str, group_id: str) -> str:
    identity = f"{episode_id}\0{point_id}\0{group_id}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return f"sample-{digest}"


def _split_groups(group_ids: list[str], seed: int, train_fraction: float) -> dict[str, str]:
    unique = sorted(set(group_ids))
    if len(unique) <= 1:
        return {group_id: "train" for group_id in unique}
    ranked = sorted(
        unique,
        key=lambda group_id: hashlib.sha256(f"{seed}\0{group_id}".encode("utf-8")).hexdigest(),
    )
    test_count = min(len(ranked) - 1, max(1, round(len(ranked) * (1.0 - train_fraction))))
    test_groups = set(ranked[:test_count])
    return {group_id: ("test" if group_id in test_groups else "train") for group_id in unique}


def validate_training_sample(sample: Mapping[str, Any]) -> None:
    """Validate message roles and reject any decision-time future-result leakage."""
    messages = sample.get("messages")
    if not isinstance(messages, list) or len(messages) != 3:
        raise ValueError("training sample must have exactly system, user, assistant messages")
    expected_roles = ["system", "user", "assistant"]
    if [message.get("role") for message in messages if _is_mapping(message)] != expected_roles:
        raise ValueError("training sample message roles must be system, user, assistant")
    if not all(
        _is_mapping(message) and isinstance(message.get("content"), str)
        for message in messages
    ):
        raise ValueError("each message must have a string content")

    user_payload = json.loads(messages[1]["content"])
    if not _is_mapping(user_payload) or set(user_payload) != set(INPUT_FIELDS):
        raise ValueError(f"user input must contain exactly these keys: {', '.join(INPUT_FIELDS)}")
    leaked_path = _input_leak_path(user_payload)
    if leaked_path:
        raise ValueError(f"future result leaked into model input at {leaked_path}")
    label_path = _walk_forbidden(user_payload, forbidden_keys=EVIDENCE_METADATA_KEYS)
    if label_path:
        raise ValueError(f"evidence labels/metadata leaked into model input at {label_path}")

    target = json.loads(messages[2]["content"])
    if not _is_mapping(target) or target.get("action") not in DECISION_ACTIONS:
        raise ValueError("assistant target must be a JSON object with one allowed decision action")
    leaked_target_path = _walk_forbidden(target, "assistant")
    if leaked_target_path:
        raise ValueError(f"future result leaked into assistant target at {leaked_target_path}")
    target_label_path = _walk_forbidden(target, "assistant", EVIDENCE_METADATA_KEYS)
    if target_label_path:
        raise ValueError(
            f"evidence labels/metadata leaked into assistant target at {target_label_path}"
        )
    if user_payload.get("last_execution_result") is not None:
        result = user_payload["last_execution_result"]
        if not _is_mapping(result) or result.get("status") not in HAND_RESULT_STATUSES:
            raise ValueError("last_execution_result must preserve a valid Hands return status")


def compile_episodes(
    episodes: Iterable[Mapping[str, Any]],
    *,
    seed: int = 42,
    train_fraction: float = 0.8,
) -> CompilationResult:
    """Compile review bundles; any held gate or quality check is excluded fail-closed.

    Input bundles have episode, local_verification, and pm_verification records.
    The PM record must be an independent PASS citing source evidence and reviewed episode claims.
    """
    if not 0.0 < train_fraction < 1.0:
        raise ValueError("train_fraction must be between 0 and 1")

    candidates: list[tuple[dict[str, Any], dict[str, Any], str]] = []
    exclusions: list[dict[str, str]] = []
    seen_sample_ids: set[str] = set()

    for bundle in episodes:
        episode = bundle.get("episode") if _is_mapping(bundle) else None
        if not _is_mapping(episode):
            exclusions.append({"episode_id": "unknown", "reason": "episode_missing"})
            continue
        episode_id = episode.get("episode_id")
        display_id = episode_id if _is_nonempty_string(episode_id) else "unknown"

        local_ok, local_reason = _passes_local_gate(episode, bundle.get("local_verification"))
        if not local_ok:
            exclusions.append({"episode_id": str(display_id), "reason": local_reason})
            continue
        pm_ok, pm_reason = _passes_pm_gate(bundle.get("pm_verification"))
        if not pm_ok:
            exclusions.append({"episode_id": str(display_id), "reason": pm_reason})
            continue
        quality_ok, quality_reason = _passes_quality_gate(episode)
        if not quality_ok:
            exclusions.append({"episode_id": str(display_id), "reason": quality_reason})
            continue
        admission = bundle.get("training_admission")
        if admission is not None and (
            not _is_mapping(admission)
            or (
                admission.get("eligible_for_dataset") is not True
                and admission.get("status") != "held_pending_pm_independent_verification"
            )
        ):
            exclusions.append(
                {"episode_id": str(display_id), "reason": "training_admission_not_eligible"}
            )
            continue
        if not _is_nonempty_string(episode_id):
            exclusions.append({"episode_id": "unknown", "reason": "episode_id_missing"})
            continue

        group_id = _source_group(episode)
        if not group_id:
            exclusions.append(
                {"episode_id": str(display_id), "reason": "source_split_group_missing"}
            )
            continue
        try:
            points = _decision_points(episode)
        except ValueError as exc:
            exclusions.append({"episode_id": str(display_id), "reason": str(exc)})
            continue

        for index, point in enumerate(points):
            point_id = point.get("decision_point_id", f"{episode_id}:decision:{index + 1}")
            if not _is_nonempty_string(point_id):
                exclusions.append(
                    {"episode_id": str(display_id), "reason": "decision_point_id_missing"}
                )
                continue
            try:
                decision = _decision_for(episode, point)
                selected = _selected_next_step(decision, point)
                model_input, missing = _decision_input(episode, point)
                leaked_path = _input_leak_path(model_input)
                if leaked_path:
                    raise ValueError(f"future result leaked into model input at {leaked_path}")
                target = _target(decision, selected, missing, model_input["available_capabilities"])
                evidence_tier, rationale_weight = _evidence_tier(episode, point, decision)
                sample = {
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": _json(model_input)},
                        {"role": "assistant", "content": _json(target)},
                    ]
                }
                validate_training_sample(sample)
                sample_id = _stable_sample_id(str(episode_id), str(point_id), group_id)
                if sample_id in seen_sample_ids:
                    raise ValueError(
                        "duplicate episode/decision-point sample ID; refusing overwrite"
                    )
                seen_sample_ids.add(sample_id)
                meta = {
                    "sample_id": sample_id,
                    "episode_id": str(episode_id),
                    "decision_point_id": str(point_id),
                    "sample_type": (
                        "ERROR_RECOVERY"
                        if model_input["last_execution_result"] is not None
                        else "NORMAL_DECISION"
                    ),
                    "evidence_tier": evidence_tier,
                    "rationale_loss_weight": rationale_weight,
                    "split_group_id": group_id,
                }
                candidates.append((sample, meta, group_id))
            except (TypeError, ValueError, KeyError) as exc:
                exclusions.append(
                    {
                        "episode_id": str(display_id),
                        "reason": f"decision_point_{index + 1}_rejected: {exc}",
                    }
                )

    partitions = _split_groups([group_id for _, _, group_id in candidates], seed, train_fraction)
    train_samples: list[dict[str, Any]] = []
    test_samples: list[dict[str, Any]] = []
    train_meta: list[dict[str, Any]] = []
    test_meta: list[dict[str, Any]] = []
    group_sources: dict[str, list[str]] = {}
    for sample, meta, group_id in candidates:
        partition = partitions[group_id]
        group_sources.setdefault(group_id, []).append(meta["episode_id"])
        if partition == "test":
            test_samples.append(sample)
            test_meta.append({**meta, "partition": partition})
        else:
            train_samples.append(sample)
            train_meta.append({**meta, "partition": partition})

    split_manifest = {
        "seed": seed,
        "train_fraction_target": train_fraction,
        "grouped_by": (
            "source tutorial/course/source identity; never split decision fragments within a group"
        ),
        "group_partitions": partitions,
        "group_episode_ids": group_sources,
        "single_source_group_warning": (
            "Only one eligible source group exists; all samples remain in train and no held-out "
            "test split is possible."
            if len(partitions) == 1
            else None
        ),
        "conflicts_policy": (
            "Keep each approved episode as a separate sample; do not deduplicate conflicting "
            "decisions."
        ),
    }
    return CompilationResult(
        train_samples=train_samples,
        test_samples=test_samples,
        train_meta=train_meta,
        test_meta=test_meta,
        exclusions=exclusions,
        split_manifest=split_manifest,
    )


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text("".join(f"{_json(record)}\n" for record in records), encoding="utf-8")


def write_compilation(result: CompilationResult, output_dir: str | Path) -> dict[str, str]:
    """Write model-facing JSONL and separate non-model metadata JSONL sidecars."""
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    paths = {
        "train": directory / "train.jsonl",
        "test": directory / "test.jsonl",
        "train_meta": directory / "train.training_meta.jsonl",
        "test_meta": directory / "test.training_meta.jsonl",
        "manifest": directory / "dataset_manifest.json",
    }
    _write_jsonl(paths["train"], result.train_samples)
    _write_jsonl(paths["test"], result.test_samples)
    _write_jsonl(paths["train_meta"], result.train_meta)
    _write_jsonl(paths["test_meta"], result.test_meta)
    manifest = {
        "schema_version": "1.0",
        "format": (
            "messages-jsonl; compatible with TRL conversational, Axolotl chat_template, and "
            "LLaMA-Factory sharegpt/messages-style adapters"
        ),
        "train_sample_count": len(result.train_samples),
        "test_sample_count": len(result.test_samples),
        "excluded_episode_or_decision_point_count": len(result.exclusions),
        "exclusions": result.exclusions,
        "split": result.split_manifest,
        "metadata_is_separate": True,
        "training_meta_files_are_not_model_inputs": True,
    }
    paths["manifest"].write_text(_json(manifest) + "\n", encoding="utf-8")
    return {key: str(path) for key, path in paths.items()}
