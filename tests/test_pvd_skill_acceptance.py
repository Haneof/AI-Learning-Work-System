"""Acceptance tests for declarative PVD knowledge packages.

The fixture is hand-authored to the new package contract. These tests inspect
knowledge content, optional suggested steps, static validation, and Docker command
construction only; they never execute a container or perform external actions.
"""

from __future__ import annotations

import json
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest

from aios_work_system.skills.sandbox import DockerSandboxRunner
from aios_work_system.skills.validator import validate_skill_package

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


@pytest.fixture
def compiled_pvd_skill_factory(tmp_path):
    """Write a minimal new-format package without invoking the compiler."""
    sequence = 0

    def build(input_overrides=None, expected_overrides=None, include_suggested_steps=True):
        nonlocal sequence
        sequence += 1
        input_overrides = input_overrides or {}
        expected_overrides = expected_overrides or {}
        root = tmp_path / f"pvd-knowledge-{sequence}"
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
                {
                    "suggested_step_id": step_id,
                    "evidence_refs": step["evidence_refs"],
                }
            )

        evidence_refs = [
            {
                "kind": "video_frame",
                "ref": f"pvd-pilot-segment-{index}",
                "timestamp_seconds": float(index * 10),
            }
            for index in range(1, len(TASKS) + 1)
        ]
        manifest = {
            "id": "pvd.pilot.product-operations",
            "version": "1.0.0",
            "purpose": (
                "Make evidence-based product-operation decisions "
                "without bypassing safety gates."
            ),
            "conditions": {
                "applicable_when": [
                    "Product and supplier information is available for review."
                ],
                "not_applicable_when": [
                    "Required facts are missing or a decision needs external authorization."
                ],
            },
            "judgement_criteria": [
                "All calculations match the declared fee and cost inputs.",
                "Product images preserve actual product attributes.",
                "Listing remains blocked until the sample is received.",
                "Supplier eligibility requires complete facts and the rating threshold.",
            ],
            "experience": {
                "success": [
                    "Recalculate every product rather than extrapolating from one example."
                ],
                "failure": [
                    "A plausible total or image appearance does not prove the underlying facts."
                ],
            },
            "counterexamples": [
                (
                    "A lifestyle image can look like a supplier photo "
                    "but is not an actual product photo."
                ),
                "A supplier rating of 4.49 looks close to 4.5 but does not meet the threshold.",
            ],
            "recovery": [
                "Stop when required facts are missing and request the missing evidence.",
                (
                    "Preserve the no-list/no-order decision until a human "
                    "reviews the updated evidence."
                ),
            ],
            "scope": "PVD pilot tasks; declarative acceptance only.",
            "inputs": {"task_context": "object"},
            "outputs": {"knowledge_result": "object"},
            "tools": [],
            "permissions": [],
            "risk": "LOW",
            "evidence": [KNOWLEDGE_ID],
            "tests": ["tests/test_knowledge_contract.py"],
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
            "Make evidence-based product-operation decisions without bypassing safety gates.\n\n"
            "## Conditions\n\n"
            "Apply only when product and supplier information is available; do not apply when "
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
        (root / "tests" / "test_knowledge_contract.py").write_text(
            "import json\n"
            "from pathlib import Path\n\n"
            "def test_knowledge_package_contract_is_evidence_linked():\n"
            "    root = Path(__file__).resolve().parents[1]\n"
            "    data = json.loads((root / 'procedure.json').read_text(encoding='utf-8'))\n"
            "    assert data['schema_version'] == '2.0'\n"
            "    assert isinstance(data['suggested_steps'], list)\n"
            "    assert data['evidence_refs']\n",
            encoding="utf-8",
        )
        (root / "references" / "evidence_manifest.json").write_text(
            json.dumps(evidence_manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return root

    return build


def _load_step(package: Path, step_id: str) -> tuple[dict, dict, dict]:
    report = validate_skill_package(package)
    assert report.passed, report.errors
    assert report.package_hash

    command = DockerSandboxRunner().build_command(
        package_path=package,
        script_path="tests/test_knowledge_contract.py",
        image_digest="python@sha256:" + "a" * 64,
    )
    assert "--pull=never" in command
    assert "--network=none" in command
    assert "--read-only" in command
    assert "--cap-drop=ALL" in command
    assert "--security-opt=no-new-privileges" in command
    assert command[-2:] == ["python", "tests/test_knowledge_contract.py"]

    procedure = json.loads((package / "procedure.json").read_text(encoding="utf-8"))
    assert procedure["schema_version"] == "2.0"
    assert procedure["source_id"] == SOURCE_ID
    assert procedure["expert_id"] == EXPERT_ID
    assert procedure["annotation_status"] == "unreviewed"
    assert len(procedure["suggested_steps"]) == 4

    step = next(item for item in procedure["suggested_steps"] if item["step_id"] == step_id)
    assert step["knowledge_id"] == KNOWLEDGE_ID
    assert step["evidence_refs"]
    assert step["ui_verification_status"] == "pending_frame_review"
    assert isinstance(step["preconditions"], list) and len(step["preconditions"]) == 1
    inputs = json.loads(step["preconditions"][0])
    declared = json.loads(step["expected_state"])
    return step, inputs, declared


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _calculate_gross_ranges(inputs: dict) -> dict:
    fee_rate = Decimal(inputs["fee_rate"])
    fixed_fee = Decimal(inputs["fixed_order_fee"])
    ranges = {}
    for product in inputs["products"]:
        proceeds = Decimal(product["sale_price"]) * (Decimal("1") - fee_rate)
        low_remaining = _money(proceeds - fixed_fee - Decimal(product["unit_cost_max"]))
        high_remaining = _money(proceeds - fixed_fee - Decimal(product["unit_cost_min"]))
        ranges[product["name"]] = [low_remaining, high_remaining]
    return {"remaining_ranges": ranges}


def _image_placements(inputs: dict) -> dict:
    placements = {}
    main_image_id = None
    for image in inputs["images"]:
        image_id = image["id"]
        changed = set(image["modified_product_attributes"])
        if changed.intersection({"color", "shape", "material"}):
            placement = "reject"
        elif image["source"] == "supplier_real_photo" and image["is_actual_supplier_photo"]:
            placement = "main"
            main_image_id = image_id
        elif image["source"] == "scene":
            placement = "secondary"
        else:
            placement = "reject"
        placements[image_id] = placement
    return {"main_image_id": main_image_id, "placements": placements}


def _sample_decision(inputs: dict) -> dict:
    if not inputs["sample_received"]:
        return {"decision": "do_not_list"}
    return {"decision": "eligible_for_manual_listing_review"}


def _supplier_decision(inputs: dict) -> dict:
    if inputs.get("platform") != "AliExpress":
        return {"decision": "do_not_order"}
    required = ("unit_price_usd", "rating", "shipping_usd", "delivery_days")
    if any(
        key not in inputs or inputs[key] is None or str(inputs[key]).strip() == ""
        for key in required
    ):
        return {"decision": "do_not_order"}
    try:
        unit_price = Decimal(str(inputs["unit_price_usd"]))
        rating = Decimal(str(inputs["rating"]))
        shipping = Decimal(str(inputs["shipping_usd"]))
        delivery_days = int(inputs["delivery_days"])
    except (ArithmeticError, ValueError):
        return {"decision": "do_not_order"}
    complete_and_valid = (
        unit_price > 0 and rating >= Decimal("4.5") and shipping >= 0 and delivery_days > 0
    )
    decision = "ready_for_manual_order_approval" if complete_and_valid else "do_not_order"
    return {"decision": decision}


def test_optional_suggested_steps_do_not_change_pvd_judgement_criteria(
    compiled_pvd_skill_factory,
):
    package = compiled_pvd_skill_factory(include_suggested_steps=False)
    report = validate_skill_package(package)
    procedure = json.loads((package / "procedure.json").read_text(encoding="utf-8"))
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))

    assert report.passed, report.errors
    assert procedure["suggested_steps"] == []
    assert manifest["judgement_criteria"]


def test_gross_recalculation_matches_all_three_ranges_and_rejects_wrong_result(
    compiled_pvd_skill_factory,
):
    package = compiled_pvd_skill_factory()
    _, inputs, declared = _load_step(package, "gross_recalculation")
    calculated = _calculate_gross_ranges(inputs)

    assert calculated == GROSS_EXPECTED
    assert declared == calculated

    wrong_result = json.loads(json.dumps(GROSS_EXPECTED, ensure_ascii=False))
    wrong_result["remaining_ranges"]["Joolim 项链"][0] = "10.14"
    wrong_package = compiled_pvd_skill_factory(
        expected_overrides={"gross_recalculation": wrong_result}
    )
    _, _, wrong_declared = _load_step(wrong_package, "gross_recalculation")
    assert wrong_declared != _calculate_gross_ranges(GROSS_INPUT)


def test_main_image_redline_requires_supplier_photo_and_rejects_ai_product_edits(
    compiled_pvd_skill_factory,
):
    package = compiled_pvd_skill_factory()
    _, inputs, declared = _load_step(package, "main_image_redline")
    calculated = _image_placements(inputs)

    assert calculated["main_image_id"] == "supplier_real"
    assert calculated == IMAGE_EXPECTED
    assert declared == calculated

    wrong_result = json.loads(json.dumps(IMAGE_EXPECTED, ensure_ascii=False))
    wrong_result["main_image_id"] = "lifestyle_scene"
    wrong_result["placements"]["lifestyle_scene"] = "main"
    wrong_result["placements"]["ai_color_changed"] = "main"
    wrong_result["placements"]["ai_shape_changed"] = "secondary"
    wrong_result["placements"]["ai_material_changed"] = "secondary"
    wrong_package = compiled_pvd_skill_factory(
        expected_overrides={"main_image_redline": wrong_result}
    )
    _, _, wrong_declared = _load_step(wrong_package, "main_image_redline")
    assert wrong_declared != _image_placements(IMAGE_INPUT)


def test_sample_gate_blocks_listing_on_day_four_until_sample_arrives(
    compiled_pvd_skill_factory,
):
    package = compiled_pvd_skill_factory()
    _, inputs, declared = _load_step(package, "sample_gate")

    assert inputs == {"sample_received": False, "day": 4}
    assert _sample_decision(inputs) == SAMPLE_EXPECTED
    assert declared == {"decision": "do_not_list"}

    received_package = compiled_pvd_skill_factory(
        input_overrides={"sample_gate": {"sample_received": True, "day": 4}},
        expected_overrides={"sample_gate": {"decision": "eligible_for_manual_listing_review"}},
    )
    _, received_inputs, received_declared = _load_step(received_package, "sample_gate")
    assert _sample_decision(received_inputs) == {"decision": "eligible_for_manual_listing_review"}
    assert received_declared == _sample_decision(received_inputs)

    wrong_package = compiled_pvd_skill_factory(
        expected_overrides={"sample_gate": {"decision": "list"}}
    )
    _, wrong_inputs, wrong_declared = _load_step(wrong_package, "sample_gate")
    assert wrong_declared != _sample_decision(wrong_inputs)


@pytest.mark.parametrize(
    "missing_field",
    ("unit_price_usd", "rating", "shipping_usd", "delivery_days"),
)
def test_supplier_gate_requires_every_field_and_rejects_order_when_one_is_missing(
    compiled_pvd_skill_factory,
    missing_field,
):
    incomplete = dict(SUPPLIER_INPUT)
    incomplete.pop(missing_field)
    package = compiled_pvd_skill_factory(
        input_overrides={"supplier_checklist": incomplete},
        expected_overrides={"supplier_checklist": {"decision": "do_not_order"}},
    )
    _, inputs, declared = _load_step(package, "supplier_checklist")

    assert _supplier_decision(inputs) == {"decision": "do_not_order"}
    assert declared == _supplier_decision(inputs)

    wrong_package = compiled_pvd_skill_factory(
        input_overrides={"supplier_checklist": incomplete},
        expected_overrides={"supplier_checklist": {"decision": "ready_for_manual_order_approval"}},
    )
    _, wrong_inputs, wrong_declared = _load_step(wrong_package, "supplier_checklist")
    assert wrong_declared != _supplier_decision(wrong_inputs)


def test_supplier_gate_accepts_rating_of_4_5_but_blocks_a_lower_rating(
    compiled_pvd_skill_factory,
):
    package = compiled_pvd_skill_factory()
    _, inputs, declared = _load_step(package, "supplier_checklist")
    assert inputs["rating"] == "4.5"
    assert _supplier_decision(inputs) == SUPPLIER_EXPECTED
    assert declared == SUPPLIER_EXPECTED

    low_rating = dict(SUPPLIER_INPUT)
    low_rating["rating"] = "4.49"
    blocked_package = compiled_pvd_skill_factory(
        input_overrides={"supplier_checklist": low_rating},
        expected_overrides={"supplier_checklist": {"decision": "do_not_order"}},
    )
    _, blocked_inputs, blocked_declared = _load_step(blocked_package, "supplier_checklist")
    assert blocked_declared == _supplier_decision(blocked_inputs)

    wrong_package = compiled_pvd_skill_factory(
        input_overrides={"supplier_checklist": low_rating},
        expected_overrides={"supplier_checklist": {"decision": "ready_for_manual_order_approval"}},
    )
    _, wrong_inputs, wrong_declared = _load_step(wrong_package, "supplier_checklist")
    assert wrong_declared != _supplier_decision(wrong_inputs)
