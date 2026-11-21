"""Evidence-gated compiler for evidence-backed knowledge packages.

The compiler writes declarative knowledge only. Suggested steps are optional
reference material, never an execution checklist.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aios_work_system.knowledge.repository import KnowledgeRepository
from aios_work_system.knowledge.types import EvidenceRelation, KnowledgeState
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
    """Input contract for compiling approved evidence into a knowledge package."""

    expert_id: str
    skill_id: str
    version: str
    title: str
    purpose: str
    scope: str
    source_id: str
    knowledge_ids: tuple[str, ...]
    conditions: dict[str, Any]
    judgement_criteria: tuple[str, ...]
    experience: dict[str, Any]
    counterexamples: tuple[str, ...]
    recovery: tuple[str, ...]
    evidence_refs: tuple[dict[str, Any], ...] = ()
    suggested_steps: tuple[dict[str, Any], ...] = ()
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
    """Compile approved knowledge and evidence into a declarative knowledge package."""

    def __init__(
        self,
        knowledge_repository: KnowledgeRepository,
        version_repository: SkillVersionRepository,
    ) -> None:
        self.knowledge = knowledge_repository
        self.versions = version_repository

    @staticmethod
    def spec_fingerprint(spec: ProcedureSkillSpec) -> str:
        """Hash all reviewable knowledge content and evidence, excluding review metadata."""
        payload = {
            "expert_id": spec.expert_id,
            "skill_id": spec.skill_id,
            "version": spec.version,
            "title": spec.title,
            "purpose": spec.purpose,
            "scope": spec.scope,
            "source_id": spec.source_id,
            "knowledge_ids": list(spec.knowledge_ids),
            "conditions": spec.conditions,
            "judgement_criteria": list(spec.judgement_criteria),
            "experience": spec.experience,
            "counterexamples": list(spec.counterexamples),
            "recovery": list(spec.recovery),
            "evidence_refs": list(spec.evidence_refs),
            "suggested_steps": list(spec.suggested_steps),
            "risk": spec.risk,
        }
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def review_spec(
        self,
        spec: ProcedureSkillSpec,
        *,
        reviewer_id: str,
        decision: str,
        note: str,
    ):
        """Record an explicit review against the exact reviewed knowledge package hash."""
        if spec.annotation_status != "reviewed":
            raise ValueError("knowledge package review requires annotation_status='reviewed'")
        if spec.review_id is not None:
            raise ValueError("review_id is assigned by the review repository")
        if spec.reviewer_id is not None or spec.reviewed_at is not None:
            raise ValueError("review metadata is assigned by the review repository")
        expert_id = self._non_empty_string(spec.expert_id, "expert_id")
        skill_id = self._non_empty_string(spec.skill_id, "skill_id")
        version = self._non_empty_string(spec.version, "version")
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,63}", skill_id):
            raise ValueError("skill_id must be a 2-64 character lowercase slug")
        if not re.fullmatch(r"\d+\.\d+\.\d+", version):
            raise ValueError("version must use MAJOR.MINOR.PATCH")
        self._normalize_knowledge_content(spec)
        knowledge_items = self._approved_knowledge(spec)
        self._normalize_evidence_refs(spec, knowledge_items)
        self._normalize_suggested_steps(spec, knowledge_items)
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

    @classmethod
    def _string_list(cls, value: object, label: str) -> list[str]:
        if not isinstance(value, (list, tuple)) or not value:
            raise ValueError(f"{label} must be a non-empty string array")
        return [
            cls._non_empty_string(item, f"{label}[{index}]")
            for index, item in enumerate(value)
        ]

    @classmethod
    def _normalize_knowledge_content(cls, spec: ProcedureSkillSpec) -> dict[str, Any]:
        purpose = cls._non_empty_string(spec.purpose, "purpose")
        if not isinstance(spec.conditions, dict):
            raise ValueError("conditions must be an object")
        conditions = {
            "applicable_when": cls._string_list(
                spec.conditions.get("applicable_when"), "conditions.applicable_when"
            ),
            "not_applicable_when": cls._string_list(
                spec.conditions.get("not_applicable_when"),
                "conditions.not_applicable_when",
            ),
        }
        judgement_criteria = cls._string_list(
            spec.judgement_criteria, "judgement_criteria"
        )
        if not isinstance(spec.experience, dict):
            raise ValueError("experience must be an object")
        experience = {
            "success": cls._string_list(spec.experience.get("success"), "experience.success"),
            "failure": cls._string_list(spec.experience.get("failure"), "experience.failure"),
        }
        counterexamples = cls._string_list(spec.counterexamples, "counterexamples")
        recovery = cls._string_list(spec.recovery, "recovery")
        return {
            "purpose": purpose,
            "conditions": conditions,
            "judgement_criteria": judgement_criteria,
            "experience": experience,
            "counterexamples": counterexamples,
            "recovery": recovery,
        }

    @staticmethod
    def _validate_review(spec: ProcedureSkillSpec) -> None:
        if spec.annotation_status not in {"unreviewed", "reviewed", "synthetic"}:
            raise ValueError("annotation_status must be unreviewed, reviewed, or synthetic")
        if spec.annotation_status != "reviewed":
            if spec.review_id is not None:
                raise ValueError("draft knowledge package cannot carry a review_id")
            if spec.reviewer_id is not None or spec.reviewed_at is not None:
                raise ValueError(
                    "review metadata cannot be supplied unless annotation_status is reviewed"
                )
            return
        if (
            spec.review_id is None
            or not isinstance(spec.review_id, str)
            or not spec.review_id.strip()
        ):
            raise ValueError("reviewed knowledge package requires a persisted review_id")
        if spec.reviewer_id is not None or spec.reviewed_at is not None:
            raise ValueError(
                "reviewer_id and reviewed_at are loaded from the persisted review record"
            )

    def _approved_knowledge(self, spec: ProcedureSkillSpec) -> dict[str, Any]:
        """Load approved source-grounded knowledge; no specific knowledge type is privileged."""
        if not spec.knowledge_ids:
            raise ValueError("at least one approved knowledge item is required")
        items: dict[str, Any] = {}
        for knowledge_id in spec.knowledge_ids:
            item = self.knowledge.get(knowledge_id, spec.expert_id)
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
                raise ValueError(f"evidence timestamp does not match source segment {ref}")
        elif "start_ms" in locator and "end_ms" in locator:
            if not locator["start_ms"] <= timestamp_ms <= locator["end_ms"]:
                raise ValueError(f"evidence timestamp is outside source segment {ref}")
        else:
            raise ValueError(f"evidence source segment {ref} has no time locator")

        return {
            "kind": kind,
            "ref": ref,
            "timestamp_seconds": round(float(timestamp), 3),
        }

    @staticmethod
    def _supporting_segments(knowledge_items: dict[str, Any]) -> set[str]:
        return {
            evidence.segment_id
            for item in knowledge_items.values()
            for evidence in item.evidence
            if evidence.relation == EvidenceRelation.SUPPORTS
        }

    def _raw_evidence_refs(self, spec: ProcedureSkillSpec) -> list[dict[str, Any]]:
        if spec.evidence_refs:
            return list(spec.evidence_refs)
        collected: list[dict[str, Any]] = []
        for suggested_step in spec.suggested_steps:
            if isinstance(suggested_step, dict):
                references = suggested_step.get("evidence_refs", [])
                if isinstance(references, list):
                    collected.extend(references)
        return collected

    def _normalize_evidence_refs(
        self,
        spec: ProcedureSkillSpec,
        knowledge_items: dict[str, Any],
    ) -> list[dict[str, Any]]:
        raw_refs = self._raw_evidence_refs(spec)
        if not raw_refs:
            raise ValueError("knowledge package requires timestamped SUPPORTS evidence_refs")
        normalized = [
            self._validate_evidence_ref(
                expert_id=spec.expert_id,
                source_id=spec.source_id,
                evidence_ref=evidence_ref,
            )
            for evidence_ref in raw_refs
        ]
        supporting_segments = self._supporting_segments(knowledge_items)
        for evidence_ref in normalized:
            if evidence_ref["ref"] not in supporting_segments:
                raise ValueError(
                    f"evidence {evidence_ref['ref']} must be linked as SUPPORTS "
                    "evidence by an approved knowledge item"
                )
        if spec.annotation_status == "reviewed" and not any(
            reference["kind"] in _VISUAL_KINDS for reference in normalized
        ):
            raise ValueError("reviewed knowledge package requires visual frame/UI evidence")
        return normalized

    def _normalize_suggested_steps(
        self,
        spec: ProcedureSkillSpec,
        knowledge_items: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Normalize optional reference steps without requiring a complete procedure."""
        normalized: list[dict[str, Any]] = []
        seen_step_ids: set[str] = set()
        supporting_segments = self._supporting_segments(knowledge_items)
        for index, raw in enumerate(spec.suggested_steps):
            if not isinstance(raw, dict):
                raise ValueError(f"suggested_steps[{index}] must be an object")
            step = dict(raw)
            step_id = raw.get("step_id")
            if step_id is not None:
                step_id = self._non_empty_string(
                    step_id, f"suggested_steps[{index}].step_id"
                )
                if step_id in seen_step_ids:
                    raise ValueError(f"duplicate suggested step_id: {step_id}")
                seen_step_ids.add(step_id)
                step["step_id"] = step_id

            knowledge_id = raw.get("knowledge_id")
            if knowledge_id is not None:
                knowledge_id = self._non_empty_string(
                    knowledge_id, f"suggested_steps[{index}].knowledge_id"
                )
                if knowledge_id not in knowledge_items:
                    raise ValueError(
                        f"suggested step {step_id or index} must reference an approved knowledge_id"
                    )

            raw_refs = raw.get("evidence_refs", [])
            if not isinstance(raw_refs, list):
                raise ValueError(
                    f"suggested_steps[{index}].evidence_refs must be an array"
                )
            validated_refs = [
                self._validate_evidence_ref(
                    expert_id=spec.expert_id,
                    source_id=spec.source_id,
                    evidence_ref=evidence_ref,
                )
                for evidence_ref in raw_refs
            ]
            if any(ref["ref"] not in supporting_segments for ref in validated_refs):
                raise ValueError(
                    f"suggested step {step_id or index} evidence must be linked as "
                    "SUPPORTS evidence by an approved knowledge item"
                )
            if spec.annotation_status == "reviewed" and validated_refs:
                if not any(ref["kind"] in _VISUAL_KINDS for ref in validated_refs):
                    raise ValueError(
                        f"reviewed suggested step {step_id or index} requires visual evidence"
                    )
                if raw.get("ui_verification_status", "frame_verified") != "frame_verified":
                    raise ValueError(
                        f"reviewed suggested step {step_id or index} must be frame_verified"
                    )
                step["ui_verification_status"] = "frame_verified"
            elif raw_refs or "ui_verification_status" in raw:
                # A caller cannot promote a draft reference step by setting a field.
                step["ui_verification_status"] = "pending_frame_review"
            if raw_refs:
                step["evidence_refs"] = validated_refs
            normalized.append(step)
        return normalized

    @staticmethod
    def _safe_output_path(path: str | Path) -> Path:
        target = Path(path).expanduser().resolve(strict=False)
        if target.exists() or target.is_symlink():
            raise FileExistsError(f"knowledge package output already exists: {target}")
        if target.name in {"", ".", ".."}:
            raise ValueError("package output must name a new directory")
        return target

    @staticmethod
    def _markdown_list(values: list[str]) -> str:
        return "\n".join(f"- {value}" for value in values)

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
        scope = self._non_empty_string(spec.scope, "scope")
        source_id = self._non_empty_string(spec.source_id, "source_id")
        if spec.risk not in {"LOW", "MEDIUM"}:
            raise ValueError("compiled knowledge package risk must be LOW or MEDIUM")
        self._validate_review(spec)
        knowledge_content = self._normalize_knowledge_content(spec)
        knowledge_items = self._approved_knowledge(spec)
        evidence_refs = self._normalize_evidence_refs(spec, knowledge_items)
        suggested_steps = self._normalize_suggested_steps(spec, knowledge_items)

        reviewed = spec.annotation_status == "reviewed"
        review_record = None
        if reviewed:
            assert spec.review_id is not None
            review_record = self.versions.get_review(spec.review_id, expert_id)
            if review_record.decision != "APPROVED":
                raise ValueError("knowledge package compilation requires an APPROVED review record")
            if (
                review_record.skill_id != skill_id
                or review_record.version != version
                or review_record.spec_hash != self.spec_fingerprint(spec)
            ):
                raise ValueError("knowledge package content differs from the reviewed spec hash")
            if review_record.annotator_id != spec.annotator_id:
                raise ValueError("knowledge package annotator differs from the reviewed record")
        lifecycle_status = "REVIEWED" if reviewed else "DRAFT"
        target = self._safe_output_path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=f".{target.name}.compile-", dir=target.parent))
        try:
            procedure: dict[str, Any] = {
                "schema_version": "2.0",
                "source_id": source_id,
                "expert_id": expert_id,
                "knowledge_ids": list(spec.knowledge_ids),
                "annotation_status": spec.annotation_status,
                "evidence_refs": evidence_refs,
                "suggested_steps": suggested_steps,
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
                **knowledge_content,
                "scope": f"{scope} (expert scope: {expert_id})",
                "inputs": {"task_context": "object"},
                "outputs": {"knowledge_result": "object"},
                "tools": [],
                "permissions": [],
                "risk": spec.risk,
                "evidence": list(spec.knowledge_ids),
                "tests": ["tests/test_knowledge_contract.py"],
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
                    f"## Purpose\n\n{knowledge_content['purpose']}\n\n"
                    "## Conditions\n\n"
                    "### Applicable when\n\n"
                    f"{self._markdown_list(knowledge_content['conditions']['applicable_when'])}\n\n"
                    "### Not applicable when\n\n"
                    f"{self._markdown_list(knowledge_content['conditions']['not_applicable_when'])}\n\n"
                    "## Judgement criteria\n\n"
                    f"{self._markdown_list(knowledge_content['judgement_criteria'])}\n\n"
                    "## Experience\n\n### Success\n\n"
                    f"{self._markdown_list(knowledge_content['experience']['success'])}\n\n"
                    "### Failure\n\n"
                    f"{self._markdown_list(knowledge_content['experience']['failure'])}\n\n"
                    "## Counterexamples\n\n"
                    f"{self._markdown_list(knowledge_content['counterexamples'])}\n\n"
                    "## Recovery\n\n"
                    f"{self._markdown_list(knowledge_content['recovery'])}\n\n"
                    "## Suggested steps\n\n"
                    "The optional reference flow is in procedure.json. It is not a "
                    "mandatory or exhaustive execution checklist.\n\n"
                    f"Scope: {scope}\n\n"
                    f"Expert scope: {expert_id}\n\n"
                    f"Evidence review status: {spec.annotation_status}.\n"
                    f"Lifecycle status: {lifecycle_status}.\n"
                    "This package is declarative knowledge, not an autonomous executor. "
                    "External side effects require separate authorization.\n"
                ),
                encoding="utf-8",
            )
            package_test = (
                "import json\n"
                "from pathlib import Path\n\n"
                "def test_knowledge_package_contract_is_evidence_grounded():\n"
                "    root = Path(__file__).resolve().parents[1]\n"
                "    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))\n"
                "    procedure = json.loads((root / 'procedure.json').read_text(encoding='utf-8'))\n"
                "    assert manifest['purpose'].strip()\n"
                "    assert manifest['conditions']['applicable_when']\n"
                "    assert manifest['judgement_criteria']\n"
                "    assert manifest['experience']['success']\n"
                "    assert manifest['counterexamples']\n"
                "    assert manifest['recovery']\n"
                "    assert procedure['schema_version'] == '2.0'\n"
                "    assert isinstance(procedure['suggested_steps'], list)\n"
                "    assert procedure['evidence_refs']\n"
                "    assert 'steps' not in procedure\n"
            )
            (stage / "tests" / "test_knowledge_contract.py").write_text(
                package_test, encoding="utf-8"
            )
            evidence_manifest = {
                "source_id": source_id,
                "expert_id": expert_id,
                "knowledge_ids": list(spec.knowledge_ids),
                "evidence_refs": evidence_refs,
                "suggested_step_evidence": [
                    {
                        "suggested_step_id": step.get("step_id", f"suggested-{index + 1}"),
                        "evidence_refs": step.get("evidence_refs", []),
                    }
                    for index, step in enumerate(suggested_steps)
                    if step.get("evidence_refs")
                ],
            }
            (stage / "references" / "evidence_manifest.json").write_text(
                json.dumps(evidence_manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            report = validate_skill_package(stage)
            if not report.passed or report.package_hash is None:
                raise ValueError(
                    "generated knowledge package failed static validation: "
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
