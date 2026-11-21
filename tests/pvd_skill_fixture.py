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

    def build(input_overrides=None, expected_overrides=None):
        nonlocal sequence
        sequence += 1
        input_overrides = input_overrides or {}
        expected_overrides = expected_overrides or {}
        root = tmp_path / f"pvd-skill-{sequence}"
        (root / "tests").mkdir(parents=True)
        (root / "references").mkdir()

        steps = []
        step_evidence = []
        for index, task in enumerate(TASKS, start=1):
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
                "recovery_strategy": (
                    "Stop and request human review; do not perform external side effects."
                ),
                "ui_verification_status": "pending_frame_review",
            }
            steps.append(step)
            step_evidence.append({"step_id": step_id, "evidence_refs": step["evidence_refs"]})

        manifest = {
            "id": "pvd.pilot.product-operations",
            "version": "1.0.0",
            "goal": "Evaluate four PVD product-operations procedures.",
            "scope": "PVD pilot tasks; declarative acceptance only.",
            "inputs": {"task_context": "object"},
            "outputs": {"procedure_result": "object"},
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
            "schema_version": "1.0",
            "source_id": SOURCE_ID,
            "expert_id": EXPERT_ID,
            "knowledge_ids": [KNOWLEDGE_ID],
            "annotation_status": "unreviewed",
            "steps": steps,
        }
        evidence_manifest = {
            "source_id": SOURCE_ID,
            "expert_id": EXPERT_ID,
            "knowledge_ids": [KNOWLEDGE_ID],
            "step_evidence": step_evidence,
        }

        (root / "SKILL.md").write_text(
            "# PVD Pilot Product Operations\n\n"
            "This is a declarative, evidence-linked procedure package.\n\n"
            "It is SPEC_ONLY and does not execute listing, purchasing, or payments.\n",
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
            "def test_procedure_contract_is_evidence_linked():\n"
            "    root = Path(__file__).resolve().parents[1]\n"
            "    data = json.loads((root / 'procedure.json').read_text(encoding='utf-8'))\n"
            "    assert data['schema_version'] == '1.0'\n"
            "    assert data['steps']\n"
            "    assert all(step['evidence_refs'] for step in data['steps'])\n"
            "    print('PVD_PROCEDURE_CONTRACT_OK')\n"
            "\n"
            "if __name__ == '__main__':\n"
            "    test_procedure_contract_is_evidence_linked()\n",
            encoding="utf-8",
        )
        (root / "references" / "evidence_manifest.json").write_text(
            json.dumps(evidence_manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return root

    return build

