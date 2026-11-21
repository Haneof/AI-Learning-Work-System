"""Shared hand-authored fixture for the compiled PVD skill package contract."""

from __future__ import annotations

import json
from pathlib import Path

SOURCE_ID = "pvd-pilot-source"
EXPERT_ID = "pvd-pilot"
KNOWLEDGE_ID = "pvd-approved-procedure"

GROSS_INPUT = {
    "fee_rate": "0.15",
    "fixed_order_fee": "0.40",
    "products": [
        {
            "name": "Joolim 项链",
            "unit_cost_min": "1.59",
            "unit_cost_max": "2.19",
            "sale_price": "14.99",
        },
        {
            "name": "Emanco 耳圈",
            "unit_cost_min": "1.23",
            "unit_cost_max": "1.88",
            "sale_price": "12.99",
        },
        {
            "name": "stick 耳圈",
            "unit_cost_min": "2.53",
            "unit_cost_max": "2.79",
            "sale_price": "14.99",
        },
    ],
}
GROSS_EXPECTED = {
    "remaining_ranges": {
        "Joolim 项链": ["10.15", "10.75"],
        "Emanco 耳圈": ["8.76", "9.41"],
        "stick 耳圈": ["9.55", "9.81"],
    }
}

IMAGE_INPUT = {
    "images": [
        {
            "id": "supplier_real",
            "source": "supplier_real_photo",
            "is_actual_supplier_photo": True,
            "modified_product_attributes": [],
        },
        {
            "id": "lifestyle_scene",
            "source": "scene",
            "is_actual_supplier_photo": False,
            "modified_product_attributes": [],
        },
        {
            "id": "ai_color_changed",
            "source": "ai_generated",
            "is_actual_supplier_photo": False,
            "modified_product_attributes": ["color"],
        },
        {
            "id": "ai_shape_changed",
            "source": "ai_generated",
            "is_actual_supplier_photo": False,
            "modified_product_attributes": ["shape"],
        },
        {
            "id": "ai_material_changed",
            "source": "ai_generated",
            "is_actual_supplier_photo": False,
            "modified_product_attributes": ["material"],
        },
    ]
}
IMAGE_EXPECTED = {
    "main_image_id": "supplier_real",
    "placements": {
        "supplier_real": "main",
        "lifestyle_scene": "secondary",
        "ai_color_changed": "reject",
        "ai_shape_changed": "reject",
        "ai_material_changed": "reject",
    },
}

SAMPLE_INPUT = {"sample_received": False, "day": 4}
SAMPLE_EXPECTED = {"decision": "do_not_list"}

SUPPLIER_INPUT = {
    "platform": "AliExpress",
    "unit_price_usd": "3.10",
    "rating": "4.5",
    "shipping_usd": "1.35",
    "delivery_days": 7,
}
SUPPLIER_EXPECTED = {"decision": "ready_for_manual_order_approval"}

TASKS = (
    {
        "step_id": "gross_recalculation",
        "goal": "Recalculate the take-home remainder for all three jewelry products.",
        "action": (
            "Apply the 15 percent category fee and 0.40 USD per-order fee, then subtract unit cost."
        ),
        "target": "US eBay jewelry listing economics",
        "preconditions": GROSS_INPUT,
        "expected_state": GROSS_EXPECTED,
    },
    {
        "step_id": "main_image_redline",
        "goal": "Classify supplier photos, scene images, and AI-altered product images.",
        "action": (
            "Only an actual supplier product photo may be the main image; scenes are secondary."
        ),
        "target": "Product listing image set",
        "preconditions": IMAGE_INPUT,
        "expected_state": IMAGE_EXPECTED,
    },
    {
        "step_id": "sample_gate",
        "goal": "Prevent listing before a physical sample has arrived.",
        "action": (
            "Block listing while sample_received is false, regardless of elapsed preparation days."
        ),
        "target": "Sample status and listing decision",
        "preconditions": SAMPLE_INPUT,
        "expected_state": SAMPLE_EXPECTED,
    },
    {
        "step_id": "supplier_checklist",
        "goal": "Check all required AliExpress supplier facts before an order is eligible.",
        "action": "Require unit price, rating at least 4.5, shipping cost, and delivery time.",
        "target": "AliExpress supplier verification",
        "preconditions": SUPPLIER_INPUT,
        "expected_state": SUPPLIER_EXPECTED,
    },
)


def make_compiled_pvd_skill_factory(tmp_path: Path):
    """Write a minimal, contract-shaped package without invoking the compiler."""
    sequence = 0

    def build(input_overrides=None, expected_overrides=None, include_suggested_steps=True):
        nonlocal sequence
        sequence += 1
        input_overrides = input_overrides or {}
        expected_overrides = expected_overrides or {}
        root = tmp_path / f"pvd-skill-{sequence}"
        (root / "tests").mkdir(parents=True)
        (root / "references").mkdir()

        suggested_steps = []
        suggested_step_evidence = []
        for index, task in enumerate(TASKS, start=1):
            if not include_suggested_steps:
                continue
            step_id = task["step_id"]
            evidence_ref = f"pvd-pilot-segment-{index}"
            step = {
                "step_id": step_id,
                "knowledge_id": KNOWLEDGE_ID,
                "goal": task["goal"],
                "preconditions": [
                    json.dumps(
                        input_overrides.get(step_id, task["preconditions"]),
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                ],
                "action": task["action"],
                "target": task["target"],
                "expected_state": json.dumps(
                    expected_overrides.get(step_id, task["expected_state"]),
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                "evidence_refs": [
                    {
                        "kind": "video_frame",
                        "ref": evidence_ref,
                        "timestamp_seconds": float(index * 10),
                    }
                ],
                "ui_verification_status": "pending_frame_review",
            }
            suggested_steps.append(step)
            suggested_step_evidence.append(
                {"suggested_step_id": step_id, "evidence_refs": step["evidence_refs"]}
            )

        evidence_refs = [
            {
                "kind": "video_frame",
                "ref": f"pvd-pilot-segment-{index}",
                "timestamp_seconds": float(index * 10),
            }
            for index, _task in enumerate(TASKS, start=1)
        ]
        manifest = {
            "id": "pvd.pilot.product-operations",
            "version": "1.0.0",
            "purpose": (
                "Make evidence-based PVD product-operation decisions "
                "without bypassing safety gates."
            ),
            "conditions": {
                "applicable_when": ["Product and supplier information is available for review."],
                "not_applicable_when": [
                    "Required facts are missing or external authorization is needed."
                ],
            },
            "judgement_criteria": [
                "All calculations match the declared fee and cost inputs.",
                "Product images preserve actual product attributes.",
                "Listing remains blocked until the sample is received.",
                "Supplier eligibility requires complete facts and the rating threshold.",
            ],
            "experience": {
                "success": ["Recalculate every product instead of extrapolating one example."],
                "failure": ["A plausible total or image appearance does not prove the facts."],
            },
            "counterexamples": [
                "A lifestyle image may look like a supplier photo but is not the actual product.",
                "A 4.49 supplier rating is close to 4.5 but does not meet the threshold.",
            ],
            "recovery": [
                "Stop when required facts are missing and request the missing evidence.",
                "Keep listing and ordering blocked until human review of updated evidence.",
            ],
            "scope": "PVD pilot tasks; declarative acceptance only.",
            "inputs": {"task_context": "object"},
            "outputs": {"knowledge_result": "object"},
            "tools": [],
            "permissions": [],
            "risk": "LOW",
            "evidence": [KNOWLEDGE_ID],
            "tests": ["tests/test_procedure_contract.py"],
            "dependencies": [],
            "lifecycle_status": "DRAFT",
            "execution_status": "SPEC_ONLY",
            "expert_id": EXPERT_ID,
        }
        procedure = {
            "schema_version": "2.0",
            "source_id": SOURCE_ID,
            "expert_id": EXPERT_ID,
            "knowledge_ids": [KNOWLEDGE_ID],
            "annotation_status": "unreviewed",
            "evidence_refs": evidence_refs,
            "suggested_steps": suggested_steps,
        }
        evidence_manifest = {
            "source_id": SOURCE_ID,
            "expert_id": EXPERT_ID,
            "knowledge_ids": [KNOWLEDGE_ID],
            "evidence_refs": evidence_refs,
            "suggested_step_evidence": suggested_step_evidence,
        }

        (root / "SKILL.md").write_text(
            "# PVD Pilot Product Operations\n\n"
            "## Purpose\n\n"
            "Make evidence-based PVD product-operation decisions "
            "without bypassing safety gates.\n\n"
            "## Conditions\n\n"
            "Apply only when product and supplier facts are available; do not apply when "
            "required facts or authorization are missing.\n\n"
            "## Judgement criteria\n\n"
            "Validate calculations, image integrity, sample status, and supplier evidence.\n\n"
            "## Experience\n\n"
            "Success: recalculate all products. Failure: do not infer facts from appearance.\n\n"
            "## Counterexamples\n\n"
            "A near-threshold rating or plausible-looking image can still be invalid.\n\n"
            "## Recovery\n\n"
            "Stop and request missing evidence or human review.\n\n"
            "## Suggested steps\n\n"
            "Optional reference hints only; not a mandatory execution checklist.\n\n"
            "This package is SPEC_ONLY and does not execute listing, purchasing, or payments.\n",
            encoding="utf-8",
        )
        (root / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (root / "procedure.json").write_text(
            json.dumps(procedure, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (root / "tests" / "test_procedure_contract.py").write_text(
            "import json\n"
            "from pathlib import Path\n\n"
            "def test_knowledge_package_contract_is_evidence_linked():\n"
            "    root = Path(__file__).resolve().parents[1]\n"
            "    data = json.loads((root / 'procedure.json').read_text(encoding='utf-8'))\n"
            "    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))\n"
            "    assert data['schema_version'] == '2.0'\n"
            "    assert isinstance(data['suggested_steps'], list)\n"
            "    assert data['evidence_refs']\n"
            "    assert manifest['purpose']\n"
            "    assert manifest['judgement_criteria']\n"
            "    print('PVD_PROCEDURE_CONTRACT_OK')\n"
            "\n"
            "if __name__ == '__main__':\n"
            "    test_knowledge_package_contract_is_evidence_linked()\n",
            encoding="utf-8",
        )
        (root / "references" / "evidence_manifest.json").write_text(
            json.dumps(evidence_manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return root

    return build
