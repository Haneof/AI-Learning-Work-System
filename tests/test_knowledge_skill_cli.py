"""CLI surface tests for persistent knowledge review and skill compilation."""

import argparse
import json

from aios_work_system.cli import (
    _run_knowledge_add,
    _run_knowledge_review,
    _run_skill_compile,
    build_parser,
)
from aios_work_system.knowledge.repository import KnowledgeRepository
from aios_work_system.knowledge.types import SourceSegment


def test_knowledge_and_skill_cli_commands_parse_expected_arguments():
    parser = build_parser()
    index = parser.parse_args(
        [
            "knowledge-index-media",
            "--run-id",
            "analysis-1",
            "--expert-id",
            "expert-office",
        ]
    )
    add = parser.parse_args(
        ["knowledge-add", "--input-file", "knowledge.json"]
    )
    review = parser.parse_args(
        [
            "knowledge-review",
            "--knowledge-id",
            "knowledge-1",
            "--expert-id",
            "expert-office",
            "--reviewer-id",
            "human-1",
            "--decision",
            "APPROVED",
            "--note",
            "Checked evidence.",
        ]
    )
    compile_args = parser.parse_args(
        [
            "skill-compile",
            "--input-file",
            "procedure.json",
            "--output",
            "packages/skill",
        ]
    )

    assert index.command == "knowledge-index-media"
    assert index.run_id == "analysis-1"
    assert add.command == "knowledge-add"
    assert review.decision == "APPROVED"
    assert compile_args.command == "skill-compile"
    assert compile_args.output == "packages/skill"


def test_knowledge_add_review_and_compile_cli_workflow(tmp_path, capsys):
    knowledge_db = tmp_path / "knowledge.sqlite3"
    versions_db = tmp_path / "versions.sqlite3"
    repository = KnowledgeRepository(knowledge_db)
    repository.add_segment(
        SourceSegment(
            segment_id="asr-segment-1",
            source_id="asset-1",
            expert_id="expert-office",
            locator={"start_ms": 0, "end_ms": 3000},
            text_content="Open the settings menu.",
            modality="asr",
            artifact_ref="/derived/audio.wav",
        )
    )

    knowledge_input = tmp_path / "knowledge.json"
    knowledge_input.write_text(
        json.dumps(
            {
                "knowledge_id": "knowledge-1",
                "expert_id": "expert-office",
                "statement": "Open the settings menu.",
                "knowledge_type": "PROCEDURE",
                "epistemic_type": "INFERENCE",
                "confidence": "HIGH",
                "evidence": [
                    {
                        "source_id": "asset-1",
                        "segment_id": "asr-segment-1",
                        "relation": "SUPPORTS",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    _run_knowledge_add(
        argparse.Namespace(
            input_file=str(knowledge_input),
            knowledge_database=str(knowledge_db),
        )
    )
    added = json.loads(capsys.readouterr().out)
    assert added["accepted"] is True

    _run_knowledge_review(
        argparse.Namespace(
            knowledge_id="knowledge-1",
            expert_id="expert-office",
            reviewer_id="reviewer-1",
            decision="APPROVED",
            note="Reviewed the narration evidence for the stated procedure.",
            knowledge_database=str(knowledge_db),
        )
    )
    reviewed = json.loads(capsys.readouterr().out)
    assert reviewed["state"] == "APPROVED"

    skill_input = tmp_path / "skill.json"
    skill_input.write_text(
        json.dumps(
            {
                "expert_id": "expert-office",
                "skill_id": "office.settings",
                "version": "1.0.0",
                "title": "Open settings",
                "goal": "Open the settings menu.",
                "scope": "Office application navigation.",
                "source_id": "asset-1",
                "knowledge_ids": ["knowledge-1"],
                "annotation_status": "unreviewed",
                "steps": [
                    {
                        "step_id": "step-1",
                        "knowledge_id": "knowledge-1",
                        "goal": "Navigate to settings.",
                        "preconditions": [],
                        "action": "open",
                        "target": "settings menu",
                        "expected_state": "Settings menu is visible.",
                        "evidence_refs": [
                            {
                                "kind": "asr_segment",
                                "ref": "asr-segment-1",
                                "timestamp_seconds": 1.0,
                            }
                        ],
                        "recovery_strategy": "Return to the main screen and retry.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "packages" / "office-settings"
    _run_skill_compile(
        argparse.Namespace(
            input_file=str(skill_input),
            output=str(output),
            knowledge_database=str(knowledge_db),
            versions_database=str(versions_db),
        )
    )
    compiled = json.loads(capsys.readouterr().out)

    assert compiled["lifecycle_status"] == "DRAFT"
    assert compiled["registered"] is False
    assert compiled["execution_status"] == "SPEC_ONLY"
    assert (output / "procedure.json").is_file()
