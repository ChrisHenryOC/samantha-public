"""Tests for hallucination probing scenario JSON files in scenarios/hallucination/.

Loads all 8 scenarios (SC-106 through SC-113) from JSON, validates each
against the scenario validator, and verifies expected behavior for
hallucination probing: extra clinical context, unrecognized tests,
unusual demographics, unmapped diagnoses, near-miss IHC scores,
narrative vs structured data, extra metadata, and boundary fixation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.simulator.loader import load_scenario
from src.simulator.scenario_validator import validate_scenario
from src.simulator.schema import Scenario
from src.workflow.state_machine import StateMachine

SCENARIOS_DIR = Path("scenarios")
HALLUCINATION_DIR = SCENARIOS_DIR / "hallucination"
ID_START = 106
ID_END = 114
EXPECTED_COUNT = ID_END - ID_START


@pytest.fixture()
def state_machine() -> StateMachine:
    return StateMachine.get_instance()


# ── Helpers ───────────────────────────────────────────────────────


_SCENARIO_CACHE: dict[str, Scenario] = {}


def _load_by_id(scenario_id: str) -> Scenario:
    """Load a specific scenario by ID (cached after first call)."""
    if not _SCENARIO_CACHE:
        for json_file in sorted(HALLUCINATION_DIR.glob("*.json")):
            s = load_scenario(json_file)
            _SCENARIO_CACHE[s.scenario_id] = s
    if scenario_id not in _SCENARIO_CACHE:
        raise FileNotFoundError(f"Scenario {scenario_id} not found")
    return _SCENARIO_CACHE[scenario_id]


def _step_rules(scenario: Scenario, step_index: int) -> tuple[str, ...]:
    return scenario.steps[step_index].expected_output.applied_rules


def _step_state(scenario: Scenario, step_index: int) -> str:
    return scenario.steps[step_index].expected_output.next_state


# ── Loading and validation ────────────────────────────────────────


class TestHallucinationLoading:
    """All 8 JSON hallucination scenario files load and validate cleanly."""

    def test_dir_exists(self) -> None:
        assert HALLUCINATION_DIR.exists(), f"{HALLUCINATION_DIR} does not exist"

    def test_all_scenarios_present(self) -> None:
        json_files = sorted(HALLUCINATION_DIR.glob("*.json"))
        assert len(json_files) == EXPECTED_COUNT, (
            f"Expected {EXPECTED_COUNT} scenario files, found {len(json_files)}: "
            f"{[f.name for f in json_files]}"
        )

    def test_all_scenarios_load(self) -> None:
        for json_file in sorted(HALLUCINATION_DIR.glob("*.json")):
            scenario = load_scenario(json_file)
            assert isinstance(scenario, Scenario), f"{json_file.name} did not load"

    def test_all_scenarios_validate(self, state_machine: StateMachine) -> None:
        for json_file in sorted(HALLUCINATION_DIR.glob("*.json")):
            scenario = load_scenario(json_file)
            errors = validate_scenario(scenario, state_machine)
            assert errors == [], (
                f"{json_file.name} ({scenario.scenario_id}) validation errors:\n"
                + "\n".join(f"  Step {e.step_number}: [{e.error_type}] {e.message}" for e in errors)
            )

    def test_all_categories_are_hallucination(self) -> None:
        for json_file in sorted(HALLUCINATION_DIR.glob("*.json")):
            scenario = load_scenario(json_file)
            assert scenario.category == "hallucination"

    def test_unique_scenario_ids(self) -> None:
        ids = set()
        for json_file in sorted(HALLUCINATION_DIR.glob("*.json")):
            scenario = load_scenario(json_file)
            ids.add(scenario.scenario_id)
        assert len(ids) == EXPECTED_COUNT

    def test_scenario_ids_sequential(self) -> None:
        expected_ids = {f"SC-{i:03d}" for i in range(ID_START, ID_END)}
        actual_ids = set()
        for json_file in sorted(HALLUCINATION_DIR.glob("*.json")):
            scenario = load_scenario(json_file)
            actual_ids.add(scenario.scenario_id)
        assert actual_ids == expected_ids


# ── Extra clinical context ignored (SC-106) ──────────────────────


class TestExtraClinicalContext:
    """SC-106: Clinical notes (BRCA1, family history) should not trigger rules."""

    def test_sc106_accepted(self) -> None:
        s = _load_by_id("SC-106")
        assert _step_state(s, 0) == "ACCEPTED"
        assert _step_rules(s, 0) == ("ACC-008",)

    def test_sc106_has_clinical_notes(self) -> None:
        s = _load_by_id("SC-106")
        assert "clinical_notes" in s.steps[0].event_data
        assert "BRCA1" in s.steps[0].event_data["clinical_notes"]


# ── Unrecognized test name (SC-107) ──────────────────────────────


class TestUnrecognizedTestName:
    """SC-107: PD-L1 test name should not trigger rejection."""

    def test_sc107_accepted(self) -> None:
        s = _load_by_id("SC-107")
        assert _step_state(s, 0) == "ACCEPTED"
        assert _step_rules(s, 0) == ("ACC-008",)

    def test_sc107_has_pdl1(self) -> None:
        s = _load_by_id("SC-107")
        assert s.steps[0].event_data["ordered_tests"] == ["PD-L1"]


# ── Unusual demographics (SC-108) ───────────────────────────────


class TestUnusualDemographics:
    """SC-108: Young male patient should not trigger demographic rules."""

    def test_sc108_accepted(self) -> None:
        s = _load_by_id("SC-108")
        assert _step_state(s, 0) == "ACCEPTED"
        assert _step_rules(s, 0) == ("ACC-008",)

    def test_sc108_demographics(self) -> None:
        s = _load_by_id("SC-108")
        assert s.steps[0].event_data["age"] == 19
        assert s.steps[0].event_data["sex"] == "M"


# ── LCIS diagnosis maps to HE-007 (SC-109) ──────────────────────


class TestLCISDiagnosis:
    """SC-109: LCIS maps to suspicious/atypical (HE-007), not an invented rule."""

    def test_sc109_pathologist_step_applies_he007(self) -> None:
        s = _load_by_id("SC-109")
        last = len(s.steps) - 1
        assert _step_state(s, last) == "IHC_STAINING"
        assert _step_rules(s, last) == ("HE-007",)

    def test_sc109_diagnosis_is_lcis(self) -> None:
        s = _load_by_id("SC-109")
        last = len(s.steps) - 1
        assert s.steps[last].event_data["diagnosis"] == "lobular_carcinoma_in_situ"

    def test_sc109_no_invented_rules(self) -> None:
        """No rule ID outside the standard catalog should appear."""
        s = _load_by_id("SC-109")
        for step in s.steps:
            for rule in step.expected_output.applied_rules:
                assert rule in {
                    "ACC-008",
                    "SP-001",
                    "SP-004",
                    "HE-001",
                    "HE-007",
                }, f"Unexpected rule {rule} in SC-109"


# ── HER2 1+ is negative, not equivocal (SC-110) ─────────────────


class TestHER2Negative:
    """SC-110: HER2 1+ routes to RESULTING via IHC-006, not FISH."""

    def test_sc110_scoring_step_applies_ihc006(self) -> None:
        s = _load_by_id("SC-110")
        last = len(s.steps) - 1
        assert _step_state(s, last) == "RESULTING"
        assert _step_rules(s, last) == ("IHC-006",)

    def test_sc110_her2_not_equivocal(self) -> None:
        s = _load_by_id("SC-110")
        last = len(s.steps) - 1
        scores = s.steps[last].event_data["scores"]
        her2 = next(sc for sc in scores if sc["test"] == "HER2")
        assert her2["value"] == "1+"
        assert her2["equivocal"] is False

    def test_sc110_no_fish_suggested_flag(self) -> None:
        s = _load_by_id("SC-110")
        for step in s.steps:
            assert "FISH_SUGGESTED" not in step.expected_output.flags


# ── Benign diagnosis with suspicious narrative (SC-111) ──────────


class TestBenignWithNarrative:
    """SC-111: Structured benign diagnosis governs, not free-text notes."""

    def test_sc111_routes_to_resulting(self) -> None:
        s = _load_by_id("SC-111")
        last = len(s.steps) - 1
        assert _step_state(s, last) == "RESULTING"
        assert _step_rules(s, last) == ("HE-008",)

    def test_sc111_benign_with_atypia_notes(self) -> None:
        s = _load_by_id("SC-111")
        last = len(s.steps) - 1
        assert s.steps[last].event_data["diagnosis"] == "benign"
        assert "atypia" in s.steps[last].event_data["clinical_notes"].lower()


# ── Extra metadata in grossing (SC-112) ──────────────────────────


class TestExtraGrossingMetadata:
    """SC-112: Extra fields in grossing event should be ignored."""

    def test_sc112_advances_normally(self) -> None:
        s = _load_by_id("SC-112")
        assert _step_state(s, 1) == "SAMPLE_PREP_PROCESSING"
        assert _step_rules(s, 1) == ("SP-001",)

    def test_sc112_has_extra_fields(self) -> None:
        s = _load_by_id("SC-112")
        data = s.steps[1].event_data
        assert "gross_description" in data
        assert "tissue_dimensions_cm" in data
        assert "tissue_weight_grams" in data


# ── Fixation time at boundary (SC-113) ───────────────────────────


class TestFixationBoundary:
    """SC-113: 6.0 hours is within tolerance for HER2 — should accept."""

    def test_sc113_accepted(self) -> None:
        s = _load_by_id("SC-113")
        assert _step_state(s, 0) == "ACCEPTED"
        assert _step_rules(s, 0) == ("ACC-008",)

    def test_sc113_fixation_at_boundary(self) -> None:
        s = _load_by_id("SC-113")
        assert s.steps[0].event_data["fixation_time_hours"] == 6.0

    def test_sc113_no_flags(self) -> None:
        s = _load_by_id("SC-113")
        assert s.steps[0].expected_output.flags == ()


# ── Cross-cutting validation ────────────────────────────────────


class TestFirstEventIsOrderReceived:
    """All hallucination scenarios start with order_received."""

    def test_all_start_with_order_received(self) -> None:
        for json_file in sorted(HALLUCINATION_DIR.glob("*.json")):
            scenario = load_scenario(json_file)
            assert scenario.steps[0].event_type == "order_received", (
                f"{scenario.scenario_id} first event is "
                f"'{scenario.steps[0].event_type}', expected 'order_received'"
            )


class TestNoFlagsInAnyScenario:
    """All hallucination scenarios have empty flags at every step."""

    def test_all_flags_empty(self) -> None:
        for json_file in sorted(HALLUCINATION_DIR.glob("*.json")):
            scenario = load_scenario(json_file)
            for step in scenario.steps:
                assert step.expected_output.flags == (), (
                    f"{scenario.scenario_id} step {step.step} has unexpected flags: "
                    f"{step.expected_output.flags}"
                )
