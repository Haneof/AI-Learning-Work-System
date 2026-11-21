"""Evidence-gated compiler for structured procedural skills.

The compiler writes declarative procedures only. It never generates Python
action code and never marks unreviewed narration as verified UI behavior.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from aios_work_system.knowledge.repository import KnowledgeRepository
from aios_work_system.knowledge.types import (
    EvidenceRelation,
    KnowledgeState,
    KnowledgeType,
)
from aios_work_system.skills.registry import SkillVersionRecord
from aios_work_system.skills.repository import SkillVersionRepository
from aios_work_system.skills.validator import validate_skill_package

_ALLOWED_EVIDENCE_KINDS = {
    "video_frame",
    "subtitle",
    "asr_segment",
    "ui_snapshot",
}
_VISUAL_KINDS = {"video_frame", "ui_snapshot"}
_MODALITY_FOR_KIND = {
    "video_frame": {"video_frame"},
    "ui_snapshot": {"ui_snapshot", "video_frame"},
    "subtitle": {"subtitle"},
    "asr_segment": {"asr"},
}


@dataclass(frozen=True)
class ProcedureSkillSpec:
    expert_id: str
    skill_id: str
    version: str
    title: str
    goal: str
    scope: str
    source_id: str
    knowledge_ids: tuple[str, ...]
    steps: tuple[dict[str, Any], ...]
    annotation_status: str = "unreviewed"
    annotator_id: str | None = None
    review_id: str | None = None
    reviewer_id: str | None = None
    reviewed_at: str | None = None
    risk: str = "LOW"


@dataclass(frozen=True)
class SkillCompilationResult:
    package_path: str
    skill_id: str
    version: str
    expert_id: str
    package_hash: str
    annotation_status: str
    lifecycle_status: str
    registered: bool
    execution_status: str
    validation_errors: tuple[str, ...] = field(default_factory=tuple)


class ProceduralSkillCompiler:
    """Compile approved knowledge plus timestamp-grounded steps into a package."""

    def __init__(
        self,
        knowledge_repository: KnowledgeRepository,
        version_repository: SkillVersionRepository,
    ) -> None:
        self.knowledge = knowledge_repository
        self.versions = version_repository

    @staticmethod
    def spec_fingerprint(spec: ProcedureSkillSpec) -> str:
        """Hash the exact reviewable procedure content, excluding review metadata."""
        payload = {
            "expert_id": spec.expert_id,
            "skill_id": spec.skill_id,
            "version": spec.version,
            "title": spec.title,
            "goal": spec.goal,
            "scope": spec.scope,
            "source_id": spec.source_id,
            "knowledge_ids": list(spec.knowledge_ids),
            "steps": list(spec.steps),
            "risk": spec.risk,
        }
        canonical = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def review_spec(
        self,
        spec: ProcedureSkillSpec,
        *,
        reviewer_id: str,
        decision: str,
        note: str,
    ):
        """Record an explicit review against the exact reviewed procedure hash."""
        if spec.annotation_status != "reviewed":
            raise ValueError("skill review requires annotation_status='reviewed'")
        if spec.review_id is not None:
            raise ValueError("review_id is assigned by the review repository")
        if spec.reviewer_id is not None or spec.reviewed_at is not None:
            raise ValueError("review metadata is assigned by the review repository")
        expert_id = self._non_empty_string(spec.expert_id, "expert_id")
        skill_id = self._non_empty_string(spec.skill_id, "skill_id")
        version = self._non_empty_string(spec.version, "version")
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,63}", skill_id):
            raise ValueError("skill_id must be a 2-64 character lowercase slug")
        if not re.fullmatch(r"\\d+\\.\\d+\\.\\d+", version):
            raise ValueError("version must use MAJOR.MINOR.PATCH")
        self._approved_procedure_knowledge(spec)
        self._normalize_steps(spec, {
            knowledge_id: self.knowledge.get(knowledge_id, expert_id)
            for knowledge_id in spec.knowledge_ids
        })
        return self.versions.record_review(
            expert_id=expert_id,
            skill_id=skill_id,
            version=version,
            spec_hash=self.spec_fingerprint(spec),
            reviewer_id=reviewer_id,
            annotator_id=spec.annotator_id,
            decision=decision,
            note=note,
        )

    @staticmethod
    def _non_empty_string(value: object, label: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label} must be a non-empty string")
        return value.strip()

    @staticmethod
    def _validate_review(spec: ProcedureSkillSpec) -> None:
        if spec.annotation_status not in {"unreviewed", "reviewed", "synthetic"}:
            raise ValueError("annotation_status must be unreviewed, reviewed, or synthetic")
        if spec.annotation_status != "reviewed":
            if spec.reviewer_id is not None or spec.reviewed_at is not None:
                raise ValueError(
                    "review metadata cannot be supplied unless annotation_status is reviewed"
                )
            return
        if spec.review_id is None or not spec.review_id.strip():
            raise ValueError("reviewed skill requires a persisted review_id")
        if spec.reviewer_id is not None or spec.reviewed_at is not None:
            raise ValueError(
                "reviewer_id and reviewed_at are loaded from the persisted review record"
            )

    def _approved_procedure_knowledge(
        self, spec: ProcedureSkillSpec
    ) -> dict[str, Any]:
        if not spec.knowledge_ids:
            raise ValueError("at least one approved PROCEDURE knowledge item is required")
        items: dict[str, Any] = {}
        for knowledge_id in spec.knowledge_ids:
            item = self.knowledge.get(knowledge_id, spec.expert_id)
            if item.knowledge_type != KnowledgeType.PROCEDURE:
                raise ValueError(f"knowledge item {knowledge_id} is not PROCEDURE")
            if item.state != KnowledgeState.APPROVED:
                raise ValueError(f"knowledge item {knowledge_id} is not APPROVED")
            if not any(
                evidence.relation == EvidenceRelation.SUPPORTS
                and evidence.source_id == spec.source_id
                for evidence in item.evidence
            ):
                raise ValueError(
                    f"knowledge item {knowledge_id} has no SUPPORTS evidence "
                    f"for source {spec.source_id}"
                )
            history = self.knowledge.review_history(knowledge_id, spec.expert_id)
            if not any(row["decision"] == KnowledgeState.APPROVED.value for row in history):
                raise ValueError(
                    f"knowledge item {knowledge_id} has no human approval audit record"
                )
            items[knowledge_id] = item
        return items

    def _validate_evidence_ref(
        self,
        *,
        expert_id: str,
        source_id: str,
        evidence_ref: object,
    ) -> dict[str, Any]:
        if not isinstance(evidence_ref, dict):
            raise ValueError("each evidence_refs entry must be an object")
        kind = self._non_empty_string(evidence_ref.get("kind"), "evidence kind")
        if kind not in _ALLOWED_EVIDENCE_KINDS:
            raise ValueError(f"unsupported evidence kind: {kind}")
        ref = self._non_empty_string(evidence_ref.get("ref"), "evidence ref")
        timestamp = evidence_ref.get("timestamp_seconds")
        if (
            isinstance(timestamp, bool)
            or not isinstance(timestamp, (int, float))
            or not math.isfinite(timestamp)
            or timestamp < 0
        ):
            raise ValueError("timestamp_seconds must be a non-negative number")

        segment = self.knowledge.get_segment(ref, expert_id)
        if segment.source_id != source_id:
            raise ValueError(f"evidence {ref} belongs to another source")
        if segment.modality not in _MODALITY_FOR_KIND[kind]:
            raise ValueError(
                f"evidence kind {kind} does not match source modality {segment.modality}"
            )

        timestamp_ms = round(float(timestamp) * 1000)
        locator = segment.locator
        if "timestamp_ms" in locator:
            if abs(timestamp_ms - locator["timestamp_ms"]) > 1:
                raise ValueError(
                    f"evidence timestamp does not match source segment {ref}"
                )
        elif "start_ms" in locator and "end_ms" in locator:
            if not locator["start_ms"] <= timestamp_ms <= locator["end_ms"]:
                raise ValueError(
                    f"evidence timestamp is outside source segment {ref}"
                )
        else:
            raise ValueError(f"evidence source segment {ref} has no time locator")

        return {
            "kind": kind,
            "ref": ref,
            "timestamp_seconds": round(float(timestamp), 3),
        }

    def _normalize_steps(
        self,
        spec: ProcedureSkillSpec,
        knowledge_items: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if not spec.steps:
            raise ValueError("procedure must include at least one step")
        normalized: list[dict[str, Any]] = []
        seen_step_ids: set[str] = set()
        for index, raw in enumerate(spec.steps):
            if not isinstance(raw, dict):
                raise ValueError(f"steps[{index}] must be an object")
            step_id = self._non_empty_string(raw.get("step_id"), f"steps[{index}].step_id")
            if step_id in seen_step_ids:
                raise ValueError(f"duplicate step_id: {step_id}")
            seen_step_ids.add(step_id)

            knowledge_id = self._non_empty_string(
                raw.get("knowledge_id"), f"steps[{index}].knowledge_id"
            )
            if knowledge_id not in knowledge_items:
                raise ValueError(
                    f"step {step_id} must reference one of the approved knowledge_ids"
                )

            evidence_refs = raw.get("evidence_refs")
            if not isinstance(evidence_refs, list) or not evidence_refs:
                raise ValueError(f"step {step_id} requires at least one evidence reference")
            validated_refs = [
                self._validate_evidence_ref(
                    expert_id=spec.expert_id,
                    source_id=spec.source_id,
                    evidence_ref=evidence_ref,
                )
                for evidence_ref in evidence_refs
            ]
            supporting_segment_ids = {
                evidence.segment_id
                for evidence in knowledge_items[knowledge_id].evidence
                if evidence.relation == EvidenceRelation.SUPPORTS
            }
            if any(ref["ref"] not in supporting_segment_ids for ref in validated_refs):
                raise ValueError(
                    f"step {step_id} evidence must be explicitly linked as SUPPORTS "
                    f"evidence by knowledge item {knowledge_id}"
                )
            if spec.annotation_status == "reviewed":
                if raw.get("ui_verification_status") != "frame_verified":
                    raise ValueError(
                        f"reviewed step {step_id} must be marked frame_verified"
                    )
                if not any(ref["kind"] in _VISUAL_KINDS for ref in validated_refs):
                    raise ValueError(
                        f"reviewed step {step_id} requires visual frame/UI evidence"
                    )
                ui_status = "frame_verified"
            else:
                # A caller cannot promote a draft merely by setting a field.
                ui_status = "pending_frame_review"

            preconditions = raw.get("preconditions", [])
            if not isinstance(preconditions, list) or any(
                not isinstance(value, str) or not value.strip()
                for value in preconditions
            ):
                raise ValueError(f"step {step_id} preconditions must be a string array")

            normalized.append(
                {
                    "step_id": step_id,
                    "knowledge_id": knowledge_id,
                    "goal": self._non_empty_string(raw.get("goal"), f"{step_id}.goal"),
                    "preconditions": [value.strip() for value in preconditions],
                    "action": self._non_empty_string(
                        raw.get("action"), f"{step_id}.action"
                    ),
                    "target": self._non_empty_string(
                        raw.get("target"), f"{step_id}.target"
                    ),
                    "expected_state": self._non_empty_string(
                        raw.get("expected_state"), f"{step_id}.expected_state"
                    ),
                    "evidence_refs": validated_refs,
                    "recovery_strategy": self._non_empty_string(
                        raw.get("recovery_strategy"), f"{step_id}.recovery_strategy"
                    ),
                    "ui_verification_status": ui_status,
                }
            )
        if spec.annotation_status == "reviewed" and len(normalized) < 8:
            raise ValueError(
                "reviewed procedural skills require at least eight "
                "visually verified steps"
            )
        return normalized

    @staticmethod
    def _safe_output_path(path: str | Path) -> Path:
        target = Path(path).expanduser().resolve(strict=False)
        if target.exists() or target.is_symlink():
            raise FileExistsError(f"skill package output already exists: {target}")
        if target.name in {"", ".", ".."}:
            raise ValueError("package output must name a new directory")
        return target

    def compile(
        self,
        spec: ProcedureSkillSpec,
        output_path: str | Path,
    ) -> SkillCompilationResult:
        expert_id = self._non_empty_string(spec.expert_id, "expert_id")
        skill_id = self._non_empty_string(spec.skill_id, "skill_id")
        version = self._non_empty_string(spec.version, "version")
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,63}", skill_id):
            raise ValueError("skill_id must be a 2-64 character lowercase slug")
        if not re.fullmatch(r"\d+\.\d+\.\d+", version):
            raise ValueError("version must use MAJOR.MINOR.PATCH")
        title = self._non_empty_string(spec.title, "title")
        goal = self._non_empty_string(spec.goal, "goal")
        scope = self._non_empty_string(spec.scope, "scope")
        source_id = self._non_empty_string(spec.source_id, "source_id")
        if spec.risk not in {"LOW", "MEDIUM"}:
            raise ValueError("compiled procedural skill risk must be LOW or MEDIUM")
        self._validate_review(spec)
        knowledge_items = self._approved_procedure_knowledge(spec)
        steps = self._normalize_steps(spec, knowledge_items)

        reviewed = spec.annotation_status == "reviewed"
        review_record = None
        if reviewed:
            assert spec.review_id is not None
            review_record = self.versions.get_review(spec.review_id, expert_id)
            if review_record.decision != "APPROVED":
                raise ValueError("skill compilation requires an APPROVED review record")
            if (
                review_record.skill_id != skill_id
                or review_record.version != version
                or review_record.spec_hash != self.spec_fingerprint(spec)
            ):
                raise ValueError(
                    "skill procedure content differs from the reviewed spec hash"
                )
            if review_record.annotator_id != spec.annotator_id:
                raise ValueError("skill annotator differs from the reviewed record")
        lifecycle_status = "REVIEWED" if reviewed else "DRAFT"
        target = self._safe_output_path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(
            tempfile.mkdtemp(prefix=f".{target.name}.compile-", dir=target.parent)
        )
        try:
            procedure: dict[str, Any] = {
                "schema_version": "1.0",
                "source_id": source_id,
                "expert_id": expert_id,
                "knowledge_ids": list(spec.knowledge_ids),
                "annotation_status": spec.annotation_status,
                "steps": steps,
            }
            if reviewed:
                assert review_record is not None
                procedure["review"] = {
                    "review_id": review_record.review_id,
                    "reviewer_id": review_record.reviewer_id,
                    "reviewed_at": review_record.reviewed_at,
                    "annotator_id": review_record.annotator_id,
                    "decision": review_record.decision,
                    "note": review_record.note,
                    "spec_hash": review_record.spec_hash,
                }

            (stage / "tests").mkdir()
            (stage / "references").mkdir()
            (stage / "procedure.json").write_text(
                json.dumps(procedure, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            manifest = {
                "id": skill_id,
                "version": version,
                "goal": goal,
                "scope": f"{scope} (expert scope: {expert_id})",
                "inputs": {"task_context": "object"},
                "outputs": {"procedure_result": "object"},
                "tools": [],
                "permissions": [],
                "risk": spec.risk,
                "evidence": list(spec.knowledge_ids),
                "tests": ["tests/test_procedure_contract.py"],
                "dependencies": [],
                "lifecycle_status": lifecycle_status,
                "execution_status": "SPEC_ONLY",
                "expert_id": expert_id,
            }
            (stage / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (stage / "SKILL.md").write_text(
                (
                    f"# {title}\n\n"
                    f"Goal: {goal}\n\n"
                    f"Scope: {scope}\n\n"
                    f"Expert scope: {expert_id}\n\n"
                    "This package contains a declarative procedure specification. "
                    "It is not an autonomous executor. Each step must be checked "
                    "against its evidence and expected state by a compatible "
                    "approved execution adapter. External side effects require "
                    "separate authorization.\n\n"
                    f"Evidence review status: {spec.annotation_status}.\n"
                    f"Lifecycle status: {lifecycle_status}.\n"
                ),
                encoding="utf-8",
            )
            package_test = (
                "import json\n"
                "from pathlib import Path\n\n"
                "def test_procedure_contract_is_non_empty_and_evidence_grounded():\n"
                "    root = Path(__file__).resolve().parents[1]\n"
                "    procedure_path = root / 'procedure.json'\n"
                "    procedure = json.loads(procedure_path.read_text(encoding='utf-8'))\n"
                "    assert procedure['schema_version'] == '1.0'\n"
                "    assert procedure['steps']\n"
                "    assert all(step['evidence_refs'] for step in procedure['steps'])\n"
                "    assert all(step['ui_verification_status'] == 'pending_frame_review' "
                "for step in procedure['steps']) or procedure['annotation_status'] == 'reviewed'\n"
            )
            (stage / "tests" / "test_procedure_contract.py").write_text(
                package_test, encoding="utf-8"
            )
            evidence_manifest = {
                "source_id": source_id,
                "expert_id": expert_id,
                "knowledge_ids": list(spec.knowledge_ids),
                "step_evidence": [
                    {
                        "step_id": step["step_id"],
                        "evidence_refs": step["evidence_refs"],
                    }
                    for step in steps
                ],
            }
            (stage / "references" / "evidence_manifest.json").write_text(
                json.dumps(evidence_manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            report = validate_skill_package(stage)
            if not report.passed or report.package_hash is None:
                raise ValueError(
                    "generated skill package failed static validation: "
                    + "; ".join(report.errors)
                )
            stage.replace(target)

            registered = False
            if reviewed:
                self.versions.register(
                    SkillVersionRecord(skill_id, version, report.package_hash),
                    expert_id=expert_id,
                    package_path=target,
                    review_id=review_record.review_id if review_record else "",
                    spec_hash=self.spec_fingerprint(spec),
                    lifecycle_status="REVIEWED",
                )
                registered = True

            return SkillCompilationResult(
                package_path=str(target),
                skill_id=skill_id,
                version=version,
                expert_id=expert_id,
                package_hash=report.package_hash,
                annotation_status=spec.annotation_status,
                lifecycle_status=lifecycle_status,
                registered=registered,
                execution_status="SPEC_ONLY",
            )
        except Exception:
            if stage.exists():
                shutil.rmtree(stage, ignore_errors=True)
            if target.exists() and reviewed:
                shutil.rmtree(target, ignore_errors=True)
            raise
