"""Tests for unknown input scenario JSON files in scenarios/unknown_input/.

Loads all 6 scenarios (SC-100 through SC-105) from JSON, validates each
against the scenario validator, and verifies expected behavior for
unknown/unexpected inputs: unrecognized specimen types, ambiguous sites,
missing fixation data, and empty orders.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.simulator.loader import load_scenario, load_scenarios_by_category
from src.simulator.scenario_validator import validate_scenario
from src.simulator.schema import _ROUTING_CATEGORIES, Scenario
from src.workflow.state_machine import StateMachine

SCENARIOS_DIR = Path("scenarios")
UNKNOWN_INPUT_DIR = SCENARIOS_DIR / "unknown_input"
ID_START = 100
ID_END = 106
EXPECTED_COUNT = ID_END - ID_START


@pytest.fixture()
def state_machine() -> StateMachine:
    return StateMachine.get_instance()


# ── Helpers ───────────────────────────────────────────────────────


_SCENARIO_CACHE: dict[str, Scenario] = {}


def _load_by_id(scenario_id: str) -> Scenario:
    """Load a specific scenario by ID (cached after first call)."""
    if not _SCENARIO_CACHE:
        for json_file in sorted(UNKNOWN_INPUT_DIR.glob("*.json")):
            s = load_scenario(json_file)
            _SCENARIO_CACHE[s.scenario_id] = s
    if scenario_id not in _SCENARIO_CACHE:
        raise FileNotFoundError(f"Scenario {scenario_id} not found")
    return _SCENARIO_CACHE[scenario_id]


def _first_step_rules(scenario: Scenario) -> tuple[str, ...]:
    return scenario.steps[0].expected_output.applied_rules


def _first_step_state(scenario: Scenario) -> str:
    return scenario.steps[0].expected_output.next_state


# ── Loading and validation ────────────────────────────────────────


class TestUnknownInputLoading:
    """All 6 JSON unknown_input scenario files load and validate cleanly."""

    def test_dir_exists(self) -> None:
        assert UNKNOWN_INPUT_DIR.exists(), f"{UNKNOWN_INPUT_DIR} does not exist"

    def test_all_scenarios_present(self) -> None:
        json_files = sorted(UNKNOWN_INPUT_DIR.glob("*.json"))
        assert len(json_files) == EXPECTED_COUNT, (
            f"Expected {EXPECTED_COUNT} scenario files, found {len(json_files)}: "
            f"{[f.name for f in json_files]}"
        )

    def test_all_scenarios_load(self) -> None:
        for json_file in sorted(UNKNOWN_INPUT_DIR.glob("*.json")):
            scenario = load_scenario(json_file)
            assert isinstance(scenario, Scenario), f"{json_file.name} did not load"

    def test_all_scenarios_validate(self, state_machine: StateMachine) -> None:
        for json_file in sorted(UNKNOWN_INPUT_DIR.glob("*.json")):
            scenario = load_scenario(json_file)
            errors = validate_scenario(scenario, state_machine)
            assert errors == [], (
                f"{json_file.name} ({scenario.scenario_id}) validation errors:\n"
                + "\n".join(f"  Step {e.step_number}: [{e.error_type}] {e.message}" for e in errors)
            )

    def test_all_categories_are_unknown_input(self) -> None:
        scenarios = load_scenarios_by_category(SCENARIOS_DIR, "unknown_input")
        for scenario in scenarios:
            assert scenario.category == "unknown_input"

    def test_unique_scenario_ids(self) -> None:
        ids = set()
        for json_file in sorted(UNKNOWN_INPUT_DIR.glob("*.json")):
            scenario = load_scenario(json_file)
            ids.add(scenario.scenario_id)
        assert len(ids) == EXPECTED_COUNT

    def test_scenario_ids_sequential(self) -> None:
        expected_ids = {f"SC-{i:03d}" for i in range(ID_START, ID_END)}
        actual_ids = set()
        for json_file in sorted(UNKNOWN_INPUT_DIR.glob("*.json")):
            scenario = load_scenario(json_file)
            actual_ids.add(scenario.scenario_id)
        assert actual_ids == expected_ids


# ── Incompatible specimen type (ACC-004) ──────────────────────────


class TestIncompatibleSpecimenType:
    """SC-100 and SC-101: Known and unknown specimen types → DO_NOT_PROCESS."""

    def test_sc100_fna(self) -> None:
        """SC-100: FNA specimen → DO_NOT_PROCESS (ACC-004)."""
        s = _load_by_id("SC-100")
        assert _first_step_state(s) == "DO_NOT_PROCESS"
        assert _first_step_rules(s) == ("ACC-004",)
        assert s.steps[0].event_data["specimen_type"] == "FNA"

    def test_sc101_swab(self) -> None:
        """SC-101: Unrecognized 'swab' type → DO_NOT_PROCESS (ACC-004)."""
        s = _load_by_id("SC-101")
        assert _first_step_state(s) == "DO_NOT_PROCESS"
        assert _first_step_rules(s) == ("ACC-004",)
        assert s.steps[0].event_data["specimen_type"] == "swab"


# ── Ambiguous anatomic site (ACC-003) ─────────────────────────────


class TestAmbiguousAnatomicSite:
    """SC-102: Ambiguous site that could go either way."""

    def test_sc102_skin_overlying_breast(self) -> None:
        """SC-102: 'skin overlying breast' → DO_NOT_PROCESS (primary expectation)."""
        s = _load_by_id("SC-102")
        assert _first_step_state(s) == "DO_NOT_PROCESS"
        assert _first_step_rules(s) == ("ACC-003",)
        assert s.steps[0].event_data["anatomic_site"] == "skin overlying breast"


# ── Missing fixation time (ACC-006) ───────────────────────────────


class TestMissingFixationTime:
    """SC-103: Null fixation time with HER2 order → implicit violation."""

    def test_sc103_null_fixation(self) -> None:
        """SC-103: fixation_time_hours=null → MISSING_INFO_HOLD (missing data, not out-of-range)."""
        s = _load_by_id("SC-103")
        assert _first_step_state(s) == "MISSING_INFO_HOLD"
        assert _first_step_rules(s) == ("ACC-009",)
        assert s.steps[0].event_data["fixation_time_hours"] is None


# ── Missing fixation time + missing billing ───────────────────────


class TestMissingFixationTimeWithBilling:
    """SC-105: Null fixation time + missing billing → HOLD outranks PROCEED."""

    def test_sc105_hold_outranks_proceed(self) -> None:
        """SC-105: ACC-009 (HOLD) + ACC-007 (PROCEED) → MISSING_INFO_HOLD."""
        s = _load_by_id("SC-105")
        assert _first_step_state(s) == "MISSING_INFO_HOLD"
        assert set(_first_step_rules(s)) == {"ACC-007", "ACC-009"}

    def test_sc105_null_fixation(self) -> None:
        """SC-105: fixation_time_hours is null."""
        s = _load_by_id("SC-105")
        assert s.steps[0].event_data["fixation_time_hours"] is None
        assert s.steps[0].event_data["billing_info_present"] is False


# ── Empty order (multiple defects) ────────────────────────────────


class TestEmptyOrder:
    """SC-104: All fields null/missing → multiple rules fire."""

    def test_sc104_all_defects(self) -> None:
        """SC-104: Empty order → 5 accessioning rules fire."""
        s = _load_by_id("SC-104")
        assert _first_step_state(s) == "DO_NOT_PROCESS"
        rules = set(_first_step_rules(s))
        assert rules == {"ACC-001", "ACC-002", "ACC-003", "ACC-004", "ACC-007"}

    def test_sc104_null_fields(self) -> None:
        """SC-104: All identifying fields are null."""
        s = _load_by_id("SC-104")
        data = s.steps[0].event_data
        assert data["patient_name"] is None
        assert data["sex"] is None
        assert data["specimen_type"] is None
        assert data["anatomic_site"] is None
        assert data["fixation_time_hours"] is None
        assert data["billing_info_present"] is False


# ── Cross-cutting validation ──────────────────────────────────────


class TestAllSingleStep:
    """All unknown input scenarios are single-step accessioning tests."""

    def test_all_single_step(self) -> None:
        for json_file in sorted(UNKNOWN_INPUT_DIR.glob("*.json")):
            scenario = load_scenario(json_file)
            assert len(scenario.steps) == 1, (
                f"{scenario.scenario_id} has {len(scenario.steps)} steps, expected 1"
            )


class TestAllRejectOrHoldAtAccessioning:
    """All unknown input scenarios result in DO_NOT_PROCESS or MISSING_INFO_HOLD."""

    _VALID_STATES = {"DO_NOT_PROCESS", "MISSING_INFO_HOLD"}

    def test_all_reject_or_hold(self) -> None:
        for json_file in sorted(UNKNOWN_INPUT_DIR.glob("*.json")):
            scenario = load_scenario(json_file)
            state = _first_step_state(scenario)
            assert state in self._VALID_STATES, (
                f"{scenario.scenario_id} state is '{state}', expected one of {self._VALID_STATES}"
            )


class TestFirstEventIsOrderReceived:
    """All unknown_input scenarios start with order_received."""

    def test_all_start_with_order_received(self) -> None:
        for json_file in sorted(UNKNOWN_INPUT_DIR.glob("*.json")):
            scenario = load_scenario(json_file)
            assert scenario.steps[0].event_type == "order_received", (
                f"{scenario.scenario_id} first event is "
                f"'{scenario.steps[0].event_type}', expected 'order_received'"
            )


# ── Total scenario count ──────────────────────────────────────────


class TestTotalScenarioCount:
    """Verify total routing scenario count and ID uniqueness across all categories."""

    @staticmethod
    def _load_all_routing_scenarios() -> list[Scenario]:
        from src.simulator.loader import load_all_scenarios

        scenarios: list[Scenario] = []
        missing = []
        for category in _ROUTING_CATEGORIES:
            category_dir = SCENARIOS_DIR / category
            if category_dir.exists():
                scenarios.extend(load_all_scenarios(category_dir))
            else:
                missing.append(category)
        assert not missing, f"Missing routing category directories: {missing}"
        scenarios.sort(key=lambda s: s.scenario_id)
        return scenarios

    def test_total_count_ge_103(self) -> None:
        """Total routing scenarios across all categories >= 103."""
        scenarios = self._load_all_routing_scenarios()
        assert len(scenarios) >= 103, f"Expected >= 103 total scenarios, found {len(scenarios)}"

    def test_scenario_ids_unique_across_categories(self) -> None:
        """Scenario IDs must be globally unique across all categories."""
        scenarios = self._load_all_routing_scenarios()
        ids = [s.scenario_id for s in scenarios]
        duplicates = {sid for sid in ids if ids.count(sid) > 1}
        assert not duplicates, f"Duplicate scenario IDs across categories: {duplicates}"
