"""Generate 16 accessioning rule coverage scenarios as JSON files.

Produces validated JSON scenario files in scenarios/rule_coverage/ for
all 9 accessioning rules (ACC-001 through ACC-009), 2 scenarios per rule.

Usage:
    uv run python scripts/generate_accessioning_scenarios.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.simulator.event_builder import (
    build_grossing_complete,
    build_order_received,
)
from src.simulator.order_generator import (
    FIXATION_BOUNDARY_HIGH,
    HER2_FIXATION_OVER,
    HER2_FIXATION_UNDER,
    HER2_NOT_FORMALIN,
    HER2_NOT_FORMALIN_ALCOHOL,
    INCOMPATIBLE_SPECIMEN,
    INCOMPATIBLE_SPECIMEN_NON_FORMALIN,
    INVALID_ANATOMIC_SITE,
    MISSING_BILLING,
    MISSING_PATIENT_NAME,
    MISSING_PATIENT_SEX,
    MULTI_DEFECT_DUAL_HOLD,
    MULTI_DEFECT_HOLD_PROCEED,
    MULTI_DEFECT_HOLD_REJECT,
    STANDARD_INVASIVE,
    OrderProfile,
)
from src.simulator.path_templates import assemble_scenario
from src.simulator.schema import Scenario

SCENARIOS_DIR = Path("scenarios/rule_coverage")


def _make_step(
    event: dict[str, Any],
    next_state: str,
    applied_rules: tuple[str, ...],
    flags: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Create an unnumbered step dict."""
    return {
        "event_type": event["event_type"],
        "event_data": event["event_data"],
        "expected_output": {
            "next_state": next_state,
            "applied_rules": applied_rules,
            "flags": flags,
        },
    }


def _accessioning_step(
    profile: OrderProfile,
    seq_num: int,
    *,
    next_state: str,
    applied_rules: tuple[str, ...] | None = None,
    flags: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    """Build an accessioning step for the given outcome state."""
    return [
        _make_step(
            build_order_received(profile, seq_num),
            next_state=next_state,
            applied_rules=applied_rules or profile.target_rules,
            flags=flags,
        ),
    ]


def _grossing_step() -> list[dict[str, Any]]:
    """Grossing complete (SP-001)."""
    return [
        _make_step(
            build_grossing_complete(),
            next_state="SAMPLE_PREP_PROCESSING",
            applied_rules=("SP-001",),
        ),
    ]


def scenario_to_json(scenario: Scenario) -> dict[str, Any]:
    """Convert a Scenario dataclass to JSON-compatible dict."""
    events = []
    for step in scenario.steps:
        events.append(
            {
                "step": step.step,
                "event_type": step.event_type,
                "event_data": step.event_data,
                "expected_output": {
                    "next_state": step.expected_output.next_state,
                    "applied_rules": list(step.expected_output.applied_rules),
                    "flags": list(step.expected_output.flags),
                },
            }
        )
    return {
        "scenario_id": scenario.scenario_id,
        "category": scenario.category,
        "description": scenario.description,
        "events": events,
    }


# ── Billing missing + boundary fixation profile ───────────────────

MISSING_BILLING_BOUNDARY_LOW = OrderProfile(
    name="missing_billing_boundary_low",
    target_rules=("ACC-007",),
    patient_name="present",
    patient_sex="F",
    specimen_type="biopsy",
    anatomic_site="breast",
    fixative="formalin",
    fixation_time_hours=6.0,
    ordered_tests=("Breast IHC Panel",),
    priority="routine",
    billing_info_present=False,
    age=51,
)


# ── Scenario definitions ──────────────────────────────────────────


def build_all_scenarios() -> list[Scenario]:
    """Build and validate all 16 accessioning scenarios."""
    scenarios = []

    # SC-001: ACC-008 — Standard invasive, all fields valid → ACCEPTED
    # Extends through grossing_complete for multi-step coverage.
    steps = [
        *_accessioning_step(
            STANDARD_INVASIVE,
            1,
            next_state="ACCEPTED",
            applied_rules=("ACC-008",),
        ),
        *_grossing_step(),
    ]
    scenarios.append(
        assemble_scenario(
            "SC-001",
            "rule_coverage",
            "ACC-008: Standard invasive, all fields valid, accepted",
            steps,
        )
    )

    # SC-002: ACC-008 — Boundary fixation at 72.0hr → ACCEPTED
    # Complicating: fixation at exact upper boundary is still valid.
    # Extends through grossing_complete.
    steps = [
        *_accessioning_step(
            FIXATION_BOUNDARY_HIGH,
            2,
            next_state="ACCEPTED",
            applied_rules=("ACC-008",),
        ),
        *_grossing_step(),
    ]
    scenarios.append(
        assemble_scenario(
            "SC-002",
            "rule_coverage",
            "ACC-008: Fixation at upper boundary 72.0hr, accepted",
            steps,
        )
    )

    # SC-003: ACC-001 — Patient name missing → MISSING_INFO_HOLD
    steps = [*_accessioning_step(MISSING_PATIENT_NAME, 3, next_state="MISSING_INFO_HOLD")]
    scenarios.append(
        assemble_scenario(
            "SC-003",
            "rule_coverage",
            "ACC-001: Patient name missing, order held for missing info",
            steps,
        )
    )

    # SC-004: ACC-001 — Patient name + billing missing → MISSING_INFO_HOLD
    # Complicating: ACC-001 (HOLD) and ACC-007 (PROCEED) both fire;
    # HOLD > PROCEED so next_state is MISSING_INFO_HOLD.
    steps = [*_accessioning_step(MULTI_DEFECT_HOLD_PROCEED, 4, next_state="MISSING_INFO_HOLD")]
    scenarios.append(
        assemble_scenario(
            "SC-004",
            "rule_coverage",
            "ACC-001: Patient name and billing missing; HOLD beats PROCEED, order held",
            steps,
        )
    )

    # SC-005: ACC-002 — Patient sex missing → MISSING_INFO_HOLD
    steps = [*_accessioning_step(MISSING_PATIENT_SEX, 5, next_state="MISSING_INFO_HOLD")]
    scenarios.append(
        assemble_scenario(
            "SC-005",
            "rule_coverage",
            "ACC-002: Patient sex missing, order held for missing info",
            steps,
        )
    )

    # SC-006: ACC-002 — Patient name + sex both missing → MISSING_INFO_HOLD
    # Complicating: both ACC-001 and ACC-002 fire (same severity HOLD);
    # patient name present is not tested (no false positive on name).
    steps = [*_accessioning_step(MULTI_DEFECT_DUAL_HOLD, 6, next_state="MISSING_INFO_HOLD")]
    scenarios.append(
        assemble_scenario(
            "SC-006",
            "rule_coverage",
            "ACC-002: Patient name and sex both missing; both HOLD rules fire, order held",
            steps,
        )
    )

    # SC-007: ACC-003 — Invalid anatomic site (lung) → DO_NOT_PROCESS
    steps = [*_accessioning_step(INVALID_ANATOMIC_SITE, 7, next_state="DO_NOT_PROCESS")]
    scenarios.append(
        assemble_scenario(
            "SC-007",
            "rule_coverage",
            "ACC-003: Invalid anatomic site (lung), order rejected",
            steps,
        )
    )

    # SC-008: ACC-003 — Invalid site + name missing → DO_NOT_PROCESS
    # Complicating: ACC-003 (REJECT) and ACC-001 (HOLD) both fire;
    # REJECT > HOLD so next_state is DO_NOT_PROCESS.
    steps = [*_accessioning_step(MULTI_DEFECT_HOLD_REJECT, 8, next_state="DO_NOT_PROCESS")]
    scenarios.append(
        assemble_scenario(
            "SC-008",
            "rule_coverage",
            "ACC-003: Invalid site + missing name; REJECT beats HOLD",
            steps,
        )
    )

    # SC-009: ACC-004 — Incompatible specimen type (FNA) → DO_NOT_PROCESS
    steps = [*_accessioning_step(INCOMPATIBLE_SPECIMEN, 9, next_state="DO_NOT_PROCESS")]
    scenarios.append(
        assemble_scenario(
            "SC-009",
            "rule_coverage",
            "ACC-004: Incompatible specimen type (FNA), order rejected",
            steps,
        )
    )

    # SC-010: ACC-004 + ACC-005 — Incompatible specimen + non-formalin
    # Complicating: cytospin with alcohol fixative triggers both ACC-004
    # (incompatible specimen) and ACC-005 (non-formalin). Both REJECT rules
    # fire; outcome is still DO_NOT_PROCESS.
    steps = [
        *_accessioning_step(
            INCOMPATIBLE_SPECIMEN_NON_FORMALIN,
            10,
            next_state="DO_NOT_PROCESS",
        )
    ]
    scenarios.append(
        assemble_scenario(
            "SC-010",
            "rule_coverage",
            "ACC-004+ACC-005: Cytospin with alcohol fixative; both REJECT rules fire",
            steps,
        )
    )

    # SC-011: ACC-005 — HER2 ordered, not formalin → DO_NOT_PROCESS
    steps = [*_accessioning_step(HER2_NOT_FORMALIN, 11, next_state="DO_NOT_PROCESS")]
    scenarios.append(
        assemble_scenario(
            "SC-011",
            "rule_coverage",
            "ACC-005: HER2 ordered with non-formalin fixative (fresh), order rejected",
            steps,
        )
    )

    # SC-012: ACC-005 — HER2 ordered, alcohol fixative → DO_NOT_PROCESS
    # Complicating: different non-formalin fixative (alcohol vs fresh in
    # SC-011), different fixation time and patient sex. Tests domain
    # generalization — any non-formalin fixative triggers ACC-005.
    steps = [
        *_accessioning_step(
            HER2_NOT_FORMALIN_ALCOHOL,
            12,
            next_state="DO_NOT_PROCESS",
        )
    ]
    scenarios.append(
        assemble_scenario(
            "SC-012",
            "rule_coverage",
            "ACC-005: Alcohol fixative, different patient; domain generalization",
            steps,
        )
    )

    # SC-013: ACC-006 — HER2 ordered, fixation under 6hr → DO_NOT_PROCESS
    steps = [*_accessioning_step(HER2_FIXATION_UNDER, 13, next_state="DO_NOT_PROCESS")]
    scenarios.append(
        assemble_scenario(
            "SC-013",
            "rule_coverage",
            "ACC-006: HER2 ordered with fixation time under 6 hours (5.0hr), order rejected",
            steps,
        )
    )

    # SC-014: ACC-006 — HER2 ordered, fixation over 72hr → DO_NOT_PROCESS
    # Complicating: all other fields valid — fixation time is the only issue.
    steps = [*_accessioning_step(HER2_FIXATION_OVER, 14, next_state="DO_NOT_PROCESS")]
    scenarios.append(
        assemble_scenario(
            "SC-014",
            "rule_coverage",
            "ACC-006: Fixation over 72hr (73.0hr), all else valid",
            steps,
        )
    )

    # SC-015: ACC-007 — Billing info missing, all else valid → MISSING_INFO_PROCEED
    steps = [
        *_accessioning_step(
            MISSING_BILLING,
            15,
            next_state="MISSING_INFO_PROCEED",
            flags=("MISSING_INFO_PROCEED",),
        )
    ]
    scenarios.append(
        assemble_scenario(
            "SC-015",
            "rule_coverage",
            "ACC-007: Billing info missing, all else valid, order proceeds with flag",
            steps,
        )
    )

    # SC-016: ACC-007 — Billing missing + fixation at boundary 6.0hr → MISSING_INFO_PROCEED
    # Boundary probe: fixation at exact lower bound should pass ACC-006.
    steps = [
        *_accessioning_step(
            MISSING_BILLING_BOUNDARY_LOW,
            16,
            next_state="MISSING_INFO_PROCEED",
            flags=("MISSING_INFO_PROCEED",),
        )
    ]
    scenarios.append(
        assemble_scenario(
            "SC-016",
            "rule_coverage",
            "ACC-007: Billing missing, fixation at boundary 6.0hr",
            steps,
        )
    )

    return scenarios


def main() -> None:
    """Generate and save all 16 scenarios."""
    SCENARIOS_DIR.mkdir(parents=True, exist_ok=True)

    scenarios = build_all_scenarios()

    for scenario in scenarios:
        filename = f"{scenario.scenario_id.lower().replace('-', '_')}.json"
        filepath = SCENARIOS_DIR / filename
        data = scenario_to_json(scenario)
        filepath.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"  {filepath}")

    print(f"\nGenerated {len(scenarios)} scenarios in {SCENARIOS_DIR}/")


if __name__ == "__main__":
    main()
