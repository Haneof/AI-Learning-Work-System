"""Two-layer validators for the workflow decision contracts.

Layer one validates JSON Schema Draft 2020-12. Layer two checks references and
cross-record semantics that JSON Schema cannot express by itself.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

CONTRACTS_DIR = Path(__file__).resolve().parent
SCHEMA_FILES = {
    "episode": "decision-episode.schema.json",
    "workflow": "workflow.schema.json",
    "protocol": "brain-hands-protocol.schema.json",
}
DECISION_ACTIONS = {
    "delegate",
    "ask_user",
    "request_approval",
    "replan",
    "finish",
    "stop",
}
FORBIDDEN_ASSISTANT_KEYS = {
    "execution_outcome",
    "last_execution_result",
    "postcondition_results",
    "observed_state",
    "actual_result",
    "execution_status",
}
EVIDENCE_TIERS = {
    "direct_explicit",
    "direct_behavioral_or_hybrid",
    "video_reconstructed",
    "user_provided_rule",
    "mixed",
    "unknown",
}


def _load_schema(kind: str) -> dict[str, Any]:
    """Load the schema associated with a supported contract kind."""
    try:
        filename = SCHEMA_FILES[kind]
    except KeyError as exc:
        raise ValueError(f"Unsupported schema kind: {kind}") from exc
    with (CONTRACTS_DIR / filename).open(encoding="utf-8") as handle:
        return json.load(handle)


def _schema_errors(kind: str, data: Any) -> list[str]:
    schema = _load_schema(kind)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = []
    for error in validator.iter_errors(data):
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        errors.append(f"schema {location}: {error.message}")
    return errors


def _unique_values(values: Iterable[str], label: str) -> list[str]:
    seen: set[str] = set()
    errors: list[str] = []
    for value in values:
        if value in seen:
            errors.append(f"duplicate {label}: {value}")
        seen.add(value)
    return errors


def _collect_evidence_refs(value: Any) -> list[str]:
    refs: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "evidence_refs" and isinstance(child, list):
                refs.extend(item for item in child if isinstance(item, str))
            else:
                refs.extend(_collect_evidence_refs(child))
    elif isinstance(value, list):
        for child in value:
            refs.extend(_collect_evidence_refs(child))
    return refs


def _check_time_ranges(value: Any, path: str = "$") -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        start = value.get("start_ms")
        end = value.get("end_ms")
        if isinstance(start, int) and isinstance(end, int) and end < start:
            errors.append(f"{path}: end_ms must be greater than or equal to start_ms")
        for key, child in value.items():
            errors.extend(_check_time_ranges(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(_check_time_ranges(child, f"{path}[{index}]"))
    return errors


def validate_episode(data: dict[str, Any]) -> list[str]:
    """Validate a DecisionEpisode structurally and semantically."""
    errors = _schema_errors("episode", data)
    if errors:
        return errors

    evidence = data["evidence"]
    evidence_ids = [item["evidence_id"] for item in evidence]
    errors.extend(_unique_values(evidence_ids, "evidence_id"))
    known_evidence = set(evidence_ids)

    for ref in _collect_evidence_refs(data):
        if ref not in known_evidence:
            errors.append(f"unresolved evidence reference: {ref}")

    errors.extend(_check_time_ranges(data))
    duration = data["source"].get("source_duration_ms")
    if isinstance(duration, int):
        for item in evidence:
            locator = item["source_locator"]
            if locator.get("end_ms", 0) > duration:
                errors.append(
                    f"evidence {item['evidence_id']}: source locator exceeds source_duration_ms"
                )
        for segment in data["narration"]:
            if segment["end_ms"] > duration:
                errors.append(
                    f"narration {segment['segment_id']}: segment exceeds source_duration_ms"
                )
            for word in segment.get("words", []):
                if word["start_ms"] < segment["start_ms"] or word["end_ms"] > segment["end_ms"]:
                    errors.append(
                        f"narration {segment['segment_id']}: word timestamp falls outside "
                        "its segment"
                    )

    decision = data["decision"]
    if not decision["evidence_refs"] and "unknown" not in decision["decision_basis"]:
        errors.append(
            "decision must reference evidence or explicitly include 'unknown' in decision_basis"
        )

    for item in evidence:
        if (
            "user_provided" in item.get("labels", [])
            and item["rationale_source"] == "instructor_explicit"
        ):
            errors.append(
                f"evidence {item['evidence_id']}: user_provided must not be mislabeled as "
                "instructor_explicit; store those as separate evidence items"
            )

    outcome = data["outcome"]
    if outcome["status"] == "success":
        passed = [
            check
            for check in outcome["postcondition_checks"]
            if check["result"] == "passed" and check["evidence_refs"]
        ]
        if not passed:
            errors.append(
                "successful outcome requires at least one passed postcondition with evidence"
            )
        else:
            verification_refs = {
                ref for check in passed for ref in check["evidence_refs"]
            }
            verified_directly = any(
                item["evidence_id"] in verification_refs
                and item["observation_channel"] == "direct_capture"
                and item["evidence_type"] in {"ui_event", "business_result"}
                for item in evidence
            )
            if not verified_directly:
                errors.append(
                    "successful outcome requires direct-capture UI/business-result evidence "
                    "for a passed postcondition"
                )

    review = data["review"]
    quality = data["quality"]
    if quality["trainable"]:
        if review["status"] != "approved" or not review["approved_for_training"]:
            errors.append(
                "quality.trainable requires review.status=approved and "
                "review.approved_for_training=true"
            )
        if quality["annotation_status"] not in {"human_reviewed", "gold"}:
            errors.append(
                "quality.trainable requires annotation_status=human_reviewed or gold"
            )
        if quality["exclusion_reasons"]:
            errors.append("quality.trainable cannot be true when exclusion_reasons is non-empty")
    if review["approved_for_training"] and not quality["trainable"]:
        errors.append(
            "review.approved_for_training cannot be true while quality.trainable is false"
        )
    if quality["annotation_status"] == "rejected" and quality["trainable"]:
        errors.append("rejected annotations cannot be trainable")

    return errors


def _has_cycle(adjacency: dict[str, set[str]]) -> bool:
    """Return whether a directed graph has a cycle."""
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        for neighbor in adjacency.get(node, set()):
            if visit(neighbor):
                return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in adjacency if node not in visited)


def validate_workflow(
    data: dict[str, Any], available_evidence_refs: Iterable[str] | None = None
) -> list[str]:
    """Validate WorkflowDefinition structure and its HTN/graph invariants."""
    errors = _schema_errors("workflow", data)
    if errors:
        return errors

    tasks = data["tasks"]
    task_ids = [task["task_id"] for task in tasks]
    errors.extend(_unique_values(task_ids, "task_id"))
    task_by_id = {task["task_id"]: task for task in tasks}
    task_id_set = set(task_ids)

    capability_ids = [item["capability_id"] for item in data["capabilities"]]
    errors.extend(_unique_values(capability_ids, "capability_id"))
    registered_capabilities = set(capability_ids)

    method_ids = [method["method_id"] for method in data["methods"]]
    errors.extend(_unique_values(method_ids, "method_id"))
    methods_by_compound: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for task in tasks:
        parent_id = task.get("parent_task_id")
        if parent_id is not None:
            if parent_id not in task_id_set:
                errors.append(f"task {task['task_id']}: unknown parent_task_id {parent_id}")
            elif task_by_id[parent_id]["kind"] != "compound":
                errors.append(f"task {task['task_id']}: parent task must be compound")

        if task["kind"] == "primitive" and task["capability_id"] not in registered_capabilities:
            errors.append(
                f"primitive task {task['task_id']} maps to unregistered capability "
                f"{task['capability_id']}"
            )

    for method in data["methods"]:
        compound_id = method["compound_task_id"]
        if compound_id not in task_id_set:
            errors.append(f"method {method['method_id']}: unknown compound task {compound_id}")
        elif task_by_id[compound_id]["kind"] != "compound":
            errors.append(f"method {method['method_id']}: compound_task_id is not compound")
        methods_by_compound[compound_id].append(method)

        for subtask in method["subtasks"]:
            if subtask not in task_id_set:
                errors.append(f"method {method['method_id']}: unknown subtask {subtask}")

        for constraint in method.get("ordering_constraints", []):
            before = constraint["before_task_id"]
            after = constraint["after_task_id"]
            if before not in task_id_set or after not in task_id_set:
                errors.append(f"method {method['method_id']}: ordering constraint has unknown task")
            if before == after:
                errors.append(f"method {method['method_id']}: task cannot precede itself")

    for task in tasks:
        if task["kind"] == "compound" and not methods_by_compound.get(task["task_id"]):
            errors.append(f"compound task {task['task_id']} has no decomposition method")

    adjacency: dict[str, set[str]] = {task_id: set() for task_id in task_id_set}
    for edge in data["edges"]:
        source = edge["from_task_id"]
        target = edge["to_task_id"]
        if source not in task_id_set or target not in task_id_set:
            errors.append(f"workflow edge references unknown task: {source} -> {target}")
        elif source == target:
            errors.append(f"workflow edge cannot reference the same task: {source}")
        elif edge["relation"] == "hard_dependency":
            adjacency[source].add(target)

    for constraint in data["ordering_constraints"]:
        before = constraint["before_task_id"]
        after = constraint["after_task_id"]
        if before not in task_id_set or after not in task_id_set:
            errors.append(f"ordering constraint references unknown task: {before} -> {after}")
        elif before == after:
            errors.append(f"ordering constraint cannot order a task before itself: {before}")
        else:
            adjacency[before].add(after)

    for method in data["methods"]:
        for constraint in method.get("ordering_constraints", []):
            before = constraint["before_task_id"]
            after = constraint["after_task_id"]
            if before in task_id_set and after in task_id_set:
                adjacency[before].add(after)

    if _has_cycle(adjacency):
        errors.append("workflow hard dependencies / ordering constraints contain a cycle")

    for invariant in data["invariants"]:
        condition = invariant["condition"]
        for task_id in invariant["must_hold_before_task_ids"]:
            if task_id not in task_id_set:
                errors.append(
                    f"invariant {invariant['invariant_id']}: unknown guarded task {task_id}"
                )
                continue
            task_conditions = task_by_id[task_id]["preconditions"]
            if condition not in task_conditions:
                errors.append(
                    f"invariant {invariant['invariant_id']}: condition is not present in "
                    f"preconditions of guarded task {task_id}; invariant could be bypassed"
                )

    for transition in data["transitions"]:
        for field in ("from_task_id", "to_task_id"):
            if transition[field] not in task_id_set:
                errors.append(
                    f"transition references unknown {field}: {transition[field]}"
                )

    for recovery in data["recovery_rules"]:
        next_task = recovery.get("next_task_id")
        if next_task is not None and next_task not in task_id_set:
            errors.append(f"recovery rule {recovery['rule_id']}: unknown next_task_id {next_task}")

    workflow_evidence_refs = set(_collect_evidence_refs(data))
    if workflow_evidence_refs:
        if available_evidence_refs is None:
            errors.append("an evidence registry is required to validate WorkflowDefinition references")
        else:
            unresolved = workflow_evidence_refs - set(available_evidence_refs)
            errors.extend(f"workflow has unresolved evidence reference: {ref}" for ref in sorted(unresolved))

    return errors


def validate_protocol(
    data: dict[str, Any], registered_capabilities: Iterable[str] | None = None
) -> list[str]:
    """Validate a BrainHands message and resolve delegated capability IDs."""
    errors = _schema_errors("protocol", data)
    if errors:
        return errors

    if data["message_type"] == "operation_delegation":
        if registered_capabilities is None:
            return ["capability registry is required to validate an operation_delegation"]
        capability_id = data["objective"]["capability_id"]
        if capability_id not in set(registered_capabilities):
            errors.append(f"Brain called unregistered capability_id: {capability_id}")

    if data["message_type"] == "operation_result" and data["status"] == "succeeded":
        passed = [
            item
            for item in data["postcondition_results"]
            if item["result"] == "passed" and item["evidence_refs"]
        ]
        if not passed:
            errors.append(
                "succeeded Hands result requires a passed postcondition with evidence_refs"
            )
        else:
            top_level_refs = set(data["evidence_refs"])
            if not any(
                set(item["evidence_refs"]).issubset(top_level_refs) for item in passed
            ):
                errors.append(
                    "passed postcondition evidence must also appear in top-level evidence_refs"
                )

    return errors


def _contains_forbidden_key(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN_ASSISTANT_KEYS:
                return key
            found = _contains_forbidden_key(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _contains_forbidden_key(child)
            if found:
                return found
    return None


def validate_training_jsonl(
    training_path: Path, sidecar_path: Path | None = None
) -> list[str]:
    """Validate conversational JSONL and its separate training_meta sidecar."""
    errors: list[str] = []
    examples: dict[str, dict[str, Any]] = {}

    with training_path.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                continue
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                errors.append(f"training line {line_number}: invalid JSON: {exc.msg}")
                continue
            example_id = record.get("training_example_id")
            if not isinstance(example_id, str) or not example_id:
                errors.append(f"training line {line_number}: missing training_example_id")
                continue
            if example_id in examples:
                errors.append(
                    f"training line {line_number}: duplicate training_example_id "
                    f"{example_id}"
                )
                continue
            examples[example_id] = record

            messages = record.get("messages")
            if not isinstance(messages, list) or len(messages) != 3:
                errors.append(
                    f"training line {line_number}: messages must contain system, user, assistant"
                )
                continue
            roles = [item.get("role") for item in messages if isinstance(item, dict)]
            if roles != ["system", "user", "assistant"]:
                errors.append(
                    f"training line {line_number}: message roles must be system, user, assistant"
                )
                continue
            if any(not isinstance(item.get("content"), str) for item in messages):
                errors.append(f"training line {line_number}: message content must be strings")
                continue
            if "training_meta" in record:
                errors.append(
                    f"training line {line_number}: training_meta must be stored in sidecar, "
                    "not in the model record"
                )

            try:
                user_payload = json.loads(messages[1]["content"])
                assistant_payload = json.loads(messages[2]["content"])
            except json.JSONDecodeError:
                errors.append(
                    f"training line {line_number}: user and assistant content must be JSON objects"
                )
                continue
            if not isinstance(user_payload, dict) or not isinstance(assistant_payload, dict):
                errors.append(
                    f"training line {line_number}: user and assistant content must decode "
                    "to objects"
                )
                continue

            action = assistant_payload.get("decision_action")
            if action not in DECISION_ACTIONS:
                errors.append(
                    f"training line {line_number}: invalid assistant decision_action {action!r}"
                )
            forbidden = _contains_forbidden_key(assistant_payload)
            if forbidden:
                errors.append(
                    f"training line {line_number}: assistant target leaks execution result "
                    f"through key {forbidden}"
                )

    if sidecar_path is None:
        return errors

    sidecar_records: dict[str, dict[str, Any]] = {}
    with sidecar_path.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                continue
            try:
                metadata = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                errors.append(f"sidecar line {line_number}: invalid JSON: {exc.msg}")
                continue
            required = {
                "training_example_id",
                "sample_type",
                "episode_refs",
                "evidence_tier",
                "rationale_loss_weight",
            }
            missing = required - set(metadata)
            if missing:
                errors.append(
                    f"sidecar line {line_number}: missing fields {sorted(missing)}"
                )
                continue
            example_id = metadata["training_example_id"]
            if example_id in sidecar_records:
                errors.append(f"sidecar line {line_number}: duplicate metadata for {example_id}")
            sidecar_records[example_id] = metadata
            if metadata["sample_type"] not in {"normal_decision", "error_recovery"}:
                errors.append(f"sidecar line {line_number}: unsupported sample_type")
            if metadata["evidence_tier"] not in EVIDENCE_TIERS:
                errors.append(f"sidecar line {line_number}: unsupported evidence_tier")
            weight = metadata["rationale_loss_weight"]
            if weight is not None and (
                isinstance(weight, bool) or not isinstance(weight, (int, float)) or weight < 0
            ):
                errors.append(
                    f"sidecar line {line_number}: rationale_loss_weight must be null "
                    "or non-negative"
                )

    for example_id, record in examples.items():
        metadata = sidecar_records.get(example_id)
        if metadata is None:
            errors.append(f"missing training_meta sidecar record for {example_id}")
            continue
        messages = record.get("messages", [])
        if len(messages) != 3 or not isinstance(messages[1].get("content"), str):
            continue
        try:
            user_payload = json.loads(messages[1]["content"])
        except json.JSONDecodeError:
            continue
        last_result = user_payload.get("last_execution_result")
        if metadata["sample_type"] == "error_recovery" and last_result is None:
            errors.append(
                f"{example_id}: error_recovery sample requires user.last_execution_result"
            )
        if metadata["sample_type"] == "normal_decision" and last_result is not None:
            errors.append(
                f"{example_id}: normal_decision sample must not include a prior Hands result"
            )

    extra_sidecar_ids = set(sidecar_records) - set(examples)
    for example_id in sorted(extra_sidecar_ids):
        errors.append(f"sidecar metadata has no matching training example: {example_id}")

    return errors


def _read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--kind",
        required=True,
        choices=["episode", "workflow", "protocol", "training-jsonl"],
    )
    parser.add_argument("path", type=Path)
    parser.add_argument("--capability-registry", type=Path)
    parser.add_argument("--evidence-registry", type=Path)
    parser.add_argument("--sidecar", type=Path)
    args = parser.parse_args(argv)

    try:
        if args.kind == "training-jsonl":
            errors = validate_training_jsonl(args.path, args.sidecar)
        else:
            data = _read_json(args.path)
            if args.kind == "episode":
                errors = validate_episode(data)
            elif args.kind == "workflow":
                evidence_ids = None
                if args.evidence_registry is not None:
                    registry = _read_json(args.evidence_registry)
                    if "evidence" in registry:
                        evidence_ids = [
                            item["evidence_id"] for item in registry["evidence"]
                        ]
                    else:
                        evidence_ids = registry.get("evidence_ids", [])
                errors = validate_workflow(data, evidence_ids)
            else:
                capabilities = None
                if args.capability_registry is not None:
                    registry = _read_json(args.capability_registry)
                    capabilities = [
                        item["capability_id"] for item in registry.get("capabilities", [])
                    ]
                errors = validate_protocol(data, capabilities)
    except (OSError, json.JSONDecodeError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(f"VALID: {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
