"""Tests for multi-rule scenario JSON files in scenarios/multi_rule/.

Loads all 10 scenarios (SC-080 through SC-089) from JSON, validates each
against the scenario validator, and verifies key properties like
all-match semantics, severity hierarchy, and false-positive probes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.simulator.loader import load_scenario, load_scenarios_by_category
from src.simulator.scenario_validator import validate_scenario
from src.simulator.schema import Scenario
from src.workflow.state_machine import StateMachine

SCENARIOS_DIR = Path("scenarios")
MULTI_RULE_DIR = SCENARIOS_DIR / "multi_rule"
ID_START = 80
ID_END = 90
EXPECTED_COUNT = ID_END - ID_START


@pytest.fixture()
def state_machine() -> StateMachine:
    return StateMachine.get_instance()


# ── Helpers ───────────────────────────────────────────────────────


_SCENARIO_CACHE: dict[str, Scenario] = {}


def _load_by_id(scenario_id: str) -> Scenario:
    """Load a specific scenario by ID (cached after first call)."""
    if not _SCENARIO_CACHE:
        for json_file in sorted(MULTI_RULE_DIR.glob("*.json")):
            s = load_scenario(json_file)
            _SCENARIO_CACHE[s.scenario_id] = s
    if scenario_id not in _SCENARIO_CACHE:
        raise FileNotFoundError(f"Scenario {scenario_id} not found")
    return _SCENARIO_CACHE[scenario_id]


def _first_step_rules(scenario: Scenario) -> tuple[str, ...]:
    """Get applied_rules from the first (accessioning) step."""
    return scenario.steps[0].expected_output.applied_rules


def _first_step_state(scenario: Scenario) -> str:
    """Get next_state from the first (accessioning) step."""
    return scenario.steps[0].expected_output.next_state


def _terminal_state(scenario: Scenario) -> str:
    """Get next_state from the last step."""
    return scenario.steps[-1].expected_output.next_state


# ── Loading and validation ────────────────────────────────────────


class TestMultiRuleLoading:
    """All 10 JSON multi_rule scenario files load and validate cleanly."""

    def test_multi_rule_dir_exists(self) -> None:
        assert MULTI_RULE_DIR.exists(), f"{MULTI_RULE_DIR} does not exist"

    def test_all_scenarios_present(self) -> None:
        json_files = sorted(MULTI_RULE_DIR.glob("*.json"))
        assert len(json_files) == EXPECTED_COUNT, (
            f"Expected {EXPECTED_COUNT} scenario files, found {len(json_files)}: "
            f"{[f.name for f in json_files]}"
        )

    def test_all_scenarios_load(self) -> None:
        """Every JSON file loads without errors."""
        for json_file in sorted(MULTI_RULE_DIR.glob("*.json")):
            scenario = load_scenario(json_file)
            assert isinstance(scenario, Scenario), f"{json_file.name} did not load"

    def test_all_scenarios_validate(self, state_machine: StateMachine) -> None:
        """Every loaded scenario passes validation with zero errors."""
        for json_file in sorted(MULTI_RULE_DIR.glob("*.json")):
            scenario = load_scenario(json_file)
            errors = validate_scenario(scenario, state_machine)
            assert errors == [], (
                f"{json_file.name} ({scenario.scenario_id}) validation errors:\n"
                + "\n".join(f"  Step {e.step_number}: [{e.error_type}] {e.message}" for e in errors)
            )

    def test_all_categories_are_multi_rule(self) -> None:
        """All scenarios have category 'multi_rule'."""
        scenarios = load_scenarios_by_category(SCENARIOS_DIR, "multi_rule")
        for scenario in scenarios:
            assert scenario.category == "multi_rule"

    def test_unique_scenario_ids(self) -> None:
        """All 10 scenarios have unique IDs."""
        ids = set()
        for json_file in sorted(MULTI_RULE_DIR.glob("*.json")):
            scenario = load_scenario(json_file)
            ids.add(scenario.scenario_id)
        assert len(ids) == EXPECTED_COUNT

    def test_scenario_ids_sequential(self) -> None:
        """Scenario IDs are SC-080 through SC-089."""
        expected_ids = {f"SC-{i:03d}" for i in range(ID_START, ID_END)}
        actual_ids = set()
        for json_file in sorted(MULTI_RULE_DIR.glob("*.json")):
            scenario = load_scenario(json_file)
            actual_ids.add(scenario.scenario_id)
        assert actual_ids == expected_ids


# ── Multi-rule accessioning (all-match semantics) ────────────────


class TestMultiRuleAllMatch:
    """Multi-rule scenarios must list ALL matching rules in applied_rules."""

    def test_sc080_name_and_site(self) -> None:
        """SC-080: ACC-001 (HOLD) + ACC-003 (REJECT) → DO_NOT_PROCESS."""
        s = _load_by_id("SC-080")
        assert _first_step_state(s) == "DO_NOT_PROCESS"
        rules = set(_first_step_rules(s))
        assert rules == {"ACC-001", "ACC-003"}

    def test_sc081_name_and_fixation(self) -> None:
        """SC-081: ACC-001 (HOLD) + ACC-006 (REJECT) → DO_NOT_PROCESS."""
        s = _load_by_id("SC-081")
        assert _first_step_state(s) == "DO_NOT_PROCESS"
        rules = set(_first_step_rules(s))
        assert rules == {"ACC-001", "ACC-006"}

    def test_sc082_all_defects(self) -> None:
        """SC-082: 5 rules fire simultaneously → DO_NOT_PROCESS."""
        s = _load_by_id("SC-082")
        assert _first_step_state(s) == "DO_NOT_PROCESS"
        rules = set(_first_step_rules(s))
        assert rules == {"ACC-001", "ACC-002", "ACC-003", "ACC-006", "ACC-007"}
        assert len(_first_step_rules(s)) == 5


class TestSeverityResolution:
    """Severity hierarchy: REJECT > HOLD > PROCEED."""

    def test_reject_beats_hold_sc080(self) -> None:
        """SC-080: REJECT (ACC-003) > HOLD (ACC-001) → DO_NOT_PROCESS."""
        s = _load_by_id("SC-080")
        assert _first_step_state(s) == "DO_NOT_PROCESS"

    def test_reject_beats_hold_sc081(self) -> None:
        """SC-081: REJECT (ACC-006) > HOLD (ACC-001) → DO_NOT_PROCESS."""
        s = _load_by_id("SC-081")
        assert _first_step_state(s) == "DO_NOT_PROCESS"

    def test_hold_beats_proceed(self) -> None:
        """SC-083: HOLD (ACC-002) > PROCEED (ACC-007) → MISSING_INFO_HOLD."""
        s = _load_by_id("SC-083")
        assert _first_step_state(s) == "MISSING_INFO_HOLD"
        rules = set(_first_step_rules(s))
        assert rules == {"ACC-002", "ACC-007"}


# ── H&E QC ambiguity (restain vs recut) ──────────────────────────


class TestHEQCAmbiguity:
    """SC-084 and SC-085: restain preferred with backup; recut when no backup."""

    def test_sc084_restain_preferred(self) -> None:
        """SC-084: Backup slides available → restain (HE-002)."""
        s = _load_by_id("SC-084")
        assert _terminal_state(s) == "HE_STAINING"
        last = s.steps[-1]
        assert last.event_type == "he_qc"
        assert last.event_data["outcome"] == "fail_restain"
        assert last.event_data["backup_slides_available"] is True
        assert last.expected_output.applied_rules == ("HE-002",)

    def test_sc085_recut_only_option(self) -> None:
        """SC-085: No backup slides → recut (HE-003)."""
        s = _load_by_id("SC-085")
        assert _terminal_state(s) == "SAMPLE_PREP_SECTIONING"
        last = s.steps[-1]
        assert last.event_type == "he_qc"
        assert last.event_data["outcome"] == "fail_recut"
        assert last.event_data["backup_slides_available"] is False
        assert last.expected_output.applied_rules == ("HE-003",)


# ── False-positive probes ─────────────────────────────────────────


class TestFalsePositiveProbes:
    """Model must not invent problems where none exist."""

    def test_sc086_perfect_order(self) -> None:
        """SC-086: All fields valid → only ACC-008 fires."""
        s = _load_by_id("SC-086")
        assert _first_step_state(s) == "ACCEPTED"
        assert _first_step_rules(s) == ("ACC-008",)
        assert s.steps[0].expected_output.flags == ()

    def test_sc087_benign_cancels_ihc(self) -> None:
        """SC-087: Benign diagnosis → RESULTING, IHC cancelled."""
        s = _load_by_id("SC-087")
        assert _terminal_state(s) == "RESULTING"
        last = s.steps[-1]
        assert last.event_data["diagnosis"] == "benign"
        assert last.expected_output.applied_rules == ("HE-008",)
        assert last.event_data["ihc_cancelled"] is True

    def test_sc088_boundary_6hr(self) -> None:
        """SC-088: 6.0hr boundary → ACCEPTED (valid)."""
        s = _load_by_id("SC-088")
        assert _first_step_state(s) == "ACCEPTED"
        assert _first_step_rules(s) == ("ACC-008",)
        assert s.steps[0].event_data["fixation_time_hours"] == 6.0

    def test_sc089_boundary_72hr(self) -> None:
        """SC-089: 72.0hr boundary → ACCEPTED (valid)."""
        s = _load_by_id("SC-089")
        assert _first_step_state(s) == "ACCEPTED"
        assert _first_step_rules(s) == ("ACC-008",)
        assert s.steps[0].event_data["fixation_time_hours"] == 72.0


# ── Cross-cutting validation ──────────────────────────────────────


class TestFirstEventIsOrderReceived:
    """All multi_rule scenarios start with order_received."""

    def test_all_start_with_order_received(self) -> None:
        for json_file in sorted(MULTI_RULE_DIR.glob("*.json")):
            scenario = load_scenario(json_file)
            assert scenario.steps[0].event_type == "order_received", (
                f"{scenario.scenario_id} first event is "
                f"'{scenario.steps[0].event_type}', expected 'order_received'"
            )
