"""Deterministic Phase 0 integration demo using synthetic, non-sensitive source material.

This proves the contracts connect. It does not run an LLM, real OCR/ASR, or Docker.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from aios_work_system.knowledge import (
    ConfidenceLabel,
    EpistemicType,
    EvidenceLink,
    EvidenceRelation,
    KnowledgeItem,
    KnowledgeRegistry,
    KnowledgeState,
    KnowledgeType,
    SourceSegment,
)
from aios_work_system.media import SegmentRecord, register_source
from aios_work_system.skills.registry import SkillVersionRecord, SkillVersionRegistry
from aios_work_system.skills.sandbox import DockerSandboxRunner
from aios_work_system.skills.validator import validate_skill_package

FIXTURE_TEXT = (
    "A reliable procedure records the original source hash and preserves the page "
    "or timestamp locator for every extracted knowledge statement."
)


def _write_skill_package(root: Path, *, unsafe: bool = False) -> None:
    (root / "scripts").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "SKILL.md").write_text(
        "# Evidence-backed extraction skill\n\n"
        "Extract a concise statement and retain its source segment reference.\n",
        encoding="utf-8",
    )
    manifest = {
        "id": "demo.evidence-extractor",
        "version": "1.0.0",
        "goal": "Extract a statement while retaining source evidence",
        "scope": "demo-expert",
        "inputs": {"text": "string", "segment_id": "string"},
        "outputs": {"statement": "string", "evidence_segment_id": "string"},
        "tools": ["text.extract"],
        "permissions": ["workspace.read"],
        "risk": "LOW",
        "evidence": ["source-segment"],
        "tests": ["tests/test_skill.py"],
        "dependencies": [],
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    script = "def extract(text, segment_id):\n    return {'statement': text, 'evidence_segment_id': segment_id}\n"
    if unsafe:
        script = "import socket\n" + script
    (root / "scripts" / "run.py").write_text(script, encoding="utf-8")
    (root / "tests" / "test_skill.py").write_text(
        "def test_placeholder():\n    assert True\n",
        encoding="utf-8",
    )


def _write_report(output: Path, report: dict[str, Any]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "phase0-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    checks = report["checks"]
    lines = [
        "# Phase 0 End-to-End Demo Report",
        "",
        f"- Overall: **{report['overall_status']}**",
        f"- Fixture mode: {report['mode']}",
        f"- Expert scope: `{report['expert_id']}`",
        "",
        "## Pipeline",
        "",
        f"- Source SHA-256: `{report['source']['sha256']}`",
        f"- Source ID: `{report['source']['source_id']}`",
        f"- Segment ID: `{report['evidence']['segment_id']}`",
        f"- Locator: `{json.dumps(report['evidence']['locator'])}`",
        f"- Knowledge ID: `{report['knowledge']['knowledge_id']}`",
        f"- Knowledge state: `{report['knowledge']['state']}`",
        f"- Skill: `{report['skill']['id']}@{report['skill']['version']}`",
        f"- Skill package hash: `{report['skill']['package_hash']}`",
        f"- Static validation: **{'PASS' if report['skill']['static_validation_passed'] else 'FAIL'}**",
        "",
        "## Fail-closed checks",
        "",
    ]
    for name, passed in checks.items():
        lines.append(f"- {'PASS' if passed else 'FAIL'} — {name}")
    lines.extend(
        [
            "",
            "## Execution boundary",
            "",
            "- Docker execution: **NOT EXECUTED**; only the constrained command plan was built.",
            "- LLM extraction: **NOT EXECUTED**; the fixture knowledge statement is deterministic.",
            "- Real PDF/video, ASR, OCR, Windows FFmpeg, RAM/VRAM peak: **NOT VALIDATED**.",
            "- This report is a contract-integration demo, not a production acceptance certificate.",
            "",
        ]
    )
    (output / "phase0-report.md").write_text("\n".join(lines), encoding="utf-8")


def run_phase0_demo(output_dir: str | Path) -> dict[str, Any]:
    output = Path(output_dir).expanduser().resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"Output directory must be empty: {output}")
    output.mkdir(parents=True, exist_ok=True)

    source_path = output / "input" / "lesson.txt"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(FIXTURE_TEXT, encoding="utf-8")

    source = register_source(source_path, "TEXT", parser_name="fixture-text", parser_version="1")
    segment = SegmentRecord.create(
        source_id=source.source_id,
        segment_type="TEXT",
        locator={"timestamp_ms": 0},
        parser_name="fixture-text",
        parser_version="1",
        text_content=FIXTURE_TEXT,
    )
    source.add_segment(segment)
    source.save(output / "source-manifest.json")

    expert_id = "demo-expert"
    knowledge_registry = KnowledgeRegistry()
    knowledge_registry.add_segment(
        SourceSegment(
            segment_id=segment.segment_id,
            source_id=source.source_id,
            expert_id=expert_id,
            locator={"timestamp_ms": 0},
            text_content=FIXTURE_TEXT,
        )
    )
    knowledge_item = KnowledgeItem(
        knowledge_id="demo.knowledge.001",
        expert_id=expert_id,
        statement=FIXTURE_TEXT,
        knowledge_type=KnowledgeType.RULE,
        epistemic_type=EpistemicType.DIRECT_QUOTE,
        state=KnowledgeState.APPROVED,
        confidence=ConfidenceLabel.HIGH,
        evidence=[
            EvidenceLink(
                source_id=source.source_id,
                segment_id=segment.segment_id,
                relation=EvidenceRelation.SUPPORTS,
                excerpt=FIXTURE_TEXT,
            )
        ],
    )
    knowledge_result = knowledge_registry.add_knowledge(knowledge_item)
    if not knowledge_result.accepted or knowledge_result.errors:
        raise RuntimeError(f"Fixture knowledge failed validation: {knowledge_result.errors}")

    ungrounded = KnowledgeItem(
        knowledge_id="demo.knowledge.ungrounded",
        expert_id=expert_id,
        statement="This statement has no source evidence.",
        knowledge_type=KnowledgeType.FACT,
        epistemic_type=EpistemicType.EXTRACTED_FACT,
        state=KnowledgeState.APPROVED,
    )
    ungrounded_result = knowledge_registry.add_knowledge(ungrounded)

    skill_root = output / "skill-package"
    _write_skill_package(skill_root)
    skill_report = validate_skill_package(skill_root)
    if not skill_report.passed or not skill_report.package_hash:
        raise RuntimeError(f"Fixture skill failed validation: {skill_report.errors}")
    skill_registry = SkillVersionRegistry()
    skill_registry.register(
        SkillVersionRecord(
            skill_id=skill_report.skill_id or "",
            version=skill_report.version or "",
            package_hash=skill_report.package_hash,
        )
    )

    sandbox_command = DockerSandboxRunner().build_command(
        package_path=skill_root,
        script_path="scripts/run.py",
        image_digest="python@sha256:" + "a" * 64,
        timeout_seconds=30,
    )
    sandbox_flags = [
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pids-limit=64",
        "--user=65534:65534",
    ]
    malicious_root = output / "malicious-skill"
    _write_skill_package(malicious_root, unsafe=True)
    malicious_report = validate_skill_package(malicious_root)

    checks = {
        "source hash and source manifest created": bool(source.sha256),
        "segment locator retained in source manifest": (
            source.segments[0].locator == {"timestamp_ms": 0}
        ),
        "approved direct quote has verifiable supporting evidence": (
            knowledge_result.accepted and not knowledge_result.errors
        ),
        "approved knowledge without evidence is rejected": (
            not ungrounded_result.accepted and bool(ungrounded_result.errors)
        ),
        "valid skill package passes static validation": skill_report.passed,
        "skill version is registered against immutable package hash": (
            skill_registry.get(
                skill_report.skill_id or "",
                skill_report.version or "",
            ).package_hash
            == skill_report.package_hash
        ),
        "network import in malicious skill is blocked": (
            not malicious_report.passed
            and any("blocked import 'socket'" in error for error in malicious_report.errors)
        ),
        "sandbox command contains required isolation flags": all(
            flag in sandbox_command for flag in sandbox_flags
        ),
    }
    report: dict[str, Any] = {
        "schema_version": "1.0",
        "mode": "SYNTHETIC_FIXTURE_NO_MODEL_NO_DOCKER",
        "overall_status": "PASS" if all(checks.values()) else "FAIL",
        "expert_id": expert_id,
        "source": {
            "source_id": source.source_id,
            "sha256": source.sha256,
            "mime_type": source.mime_type,
            "size_bytes": source.size_bytes,
            "manifest_path": "source-manifest.json",
        },
        "evidence": {
            "segment_id": segment.segment_id,
            "locator": segment.locator,
            "content_hash": segment.content_hash,
        },
        "knowledge": {
            "knowledge_id": knowledge_item.knowledge_id,
            "state": knowledge_item.state.value,
            "evidence_count": len(knowledge_item.evidence),
            "ungrounded_rejection_errors": list(ungrounded_result.errors),
        },
        "skill": {
            "id": skill_report.skill_id,
            "version": skill_report.version,
            "package_hash": skill_report.package_hash,
            "static_validation_passed": skill_report.passed,
            "malicious_package_errors": malicious_report.errors,
            "sandbox_execution": "NOT_EXECUTED",
            "sandbox_plan_flags": sandbox_flags,
            "sandbox_command_argument_count": len(sandbox_command),
        },
        "checks": checks,
        "limitations": [
            "No LLM inference was performed; knowledge content is deterministic fixture text.",
            "No real PDF/video, ASR, OCR, or FFmpeg runtime was exercised.",
            "Docker command was built but no container was started.",
            "Resource peak measurements are not available in this demo.",
        ],
    }
    _write_report(output, report)
    return report
