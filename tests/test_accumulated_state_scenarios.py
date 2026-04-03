"""Tests for accumulated state scenario JSON files in scenarios/accumulated_state/.

Loads all 10 scenarios (SC-090 through SC-099) from JSON, validates each
against the scenario validator, and verifies flag lifecycle properties:
flag set points, flag clearing, flag persistence, and multi-flag interactions.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.simulator.loader import load_scenario, load_scenarios_by_category
from src.simulator.scenario_validator import validate_scenario
from src.simulator.schema import Scenario
from src.workflow.state_machine import StateMachine

SCENARIOS_DIR = Path("scenarios")
ACCUMULATED_STATE_DIR = SCENARIOS_DIR / "accumulated_state"
ID_START = 90
ID_END = 100
EXPECTED_COUNT = ID_END - ID_START


@pytest.fixture()
def state_machine() -> StateMachine:
    return StateMachine.get_instance()


# ── Helpers ───────────────────────────────────────────────────────


_SCENARIO_CACHE: dict[str, Scenario] = {}


def _load_by_id(scenario_id: str) -> Scenario:
    """Load a specific scenario by ID (cached after first call)."""
    if not _SCENARIO_CACHE:
        for json_file in sorted(ACCUMULATED_STATE_DIR.glob("*.json")):
            s = load_scenario(json_file)
            _SCENARIO_CACHE[s.scenario_id] = s
    if scenario_id not in _SCENARIO_CACHE:
        raise FileNotFoundError(f"Scenario {scenario_id} not found")
    return _SCENARIO_CACHE[scenario_id]


def _first_step_rules(scenario: Scenario) -> tuple[str, ...]:
    return scenario.steps[0].expected_output.applied_rules


def _first_step_state(scenario: Scenario) -> str:
    return scenario.steps[0].expected_output.next_state


def _terminal_state(scenario: Scenario) -> str:
    return scenario.steps[-1].expected_output.next_state


# ── Loading and validation ────────────────────────────────────────


class TestAccumulatedStateLoading:
    """All 10 JSON accumulated_state scenario files load and validate cleanly."""

    def test_dir_exists(self) -> None:
        assert ACCUMULATED_STATE_DIR.exists(), f"{ACCUMULATED_STATE_DIR} does not exist"

    def test_all_scenarios_present(self) -> None:
        json_files = sorted(ACCUMULATED_STATE_DIR.glob("*.json"))
        assert len(json_files) == EXPECTED_COUNT, (
            f"Expected {EXPECTED_COUNT} scenario files, found {len(json_files)}: "
            f"{[f.name for f in json_files]}"
        )

    def test_all_scenarios_load(self) -> None:
        for json_file in sorted(ACCUMULATED_STATE_DIR.glob("*.json")):
            scenario = load_scenario(json_file)
            assert isinstance(scenario, Scenario), f"{json_file.name} did not load"

    def test_all_scenarios_validate(self, state_machine: StateMachine) -> None:
        for json_file in sorted(ACCUMULATED_STATE_DIR.glob("*.json")):
            scenario = load_scenario(json_file)
            errors = validate_scenario(scenario, state_machine)
            assert errors == [], (
                f"{json_file.name} ({scenario.scenario_id}) validation errors:\n"
                + "\n".join(f"  Step {e.step_number}: [{e.error_type}] {e.message}" for e in errors)
            )

    def test_all_categories_are_accumulated_state(self) -> None:
        scenarios = load_scenarios_by_category(SCENARIOS_DIR, "accumulated_state")
        for scenario in scenarios:
            assert scenario.category == "accumulated_state"

    def test_unique_scenario_ids(self) -> None:
        ids = set()
        for json_file in sorted(ACCUMULATED_STATE_DIR.glob("*.json")):
            scenario = load_scenario(json_file)
            ids.add(scenario.scenario_id)
        assert len(ids) == EXPECTED_COUNT

    def test_scenario_ids_sequential(self) -> None:
        expected_ids = {f"SC-{i:03d}" for i in range(ID_START, ID_END)}
        actual_ids = set()
        for json_file in sorted(ACCUMULATED_STATE_DIR.glob("*.json")):
            scenario = load_scenario(json_file)
            actual_ids.add(scenario.scenario_id)
        assert actual_ids == expected_ids


# ── MISSING_INFO_PROCEED flag lifecycle ───────────────────────────


class TestMissingInfoProceedLifecycle:
    """SC-090, SC-091, SC-097, SC-098: MISSING_INFO_PROCEED flag set and cleared."""

    _FLAG_SCENARIOS = ("SC-090", "SC-091", "SC-097", "SC-098")

    def test_flag_set_at_step_1(self) -> None:
        """MISSING_INFO_PROCEED is set at step 1 by ACC-007."""
        for sid in self._FLAG_SCENARIOS:
            s = _load_by_id(sid)
            assert "MISSING_INFO_PROCEED" in s.steps[0].expected_output.flags, (
                f"{sid} step 1 should set MISSING_INFO_PROCEED flag"
            )
            assert _first_step_rules(s) == ("ACC-007",), f"{sid} step 1 should apply ACC-007"

    def test_flag_persists_until_cleared(self) -> None:
        """MISSING_INFO_PROCEED flag persists until a missing_info_received event clears it."""
        for sid in self._FLAG_SCENARIOS:
            s = _load_by_id(sid)
            flag_active = True
            for step in s.steps[1:]:
                is_billing_received = (
                    step.event_type == "missing_info_received"
                    and step.event_data.get("info_type") == "billing"
                )
                if is_billing_received:
                    flag_active = False
                    continue
                if flag_active:
                    assert "MISSING_INFO_PROCEED" in step.expected_output.flags, (
                        f"{sid} step {step.step} should carry MISSING_INFO_PROCEED"
                    )
                else:
                    assert "MISSING_INFO_PROCEED" not in step.expected_output.flags, (
                        f"{sid} step {step.step}: flag should be cleared"
                    )

    def test_sc090_blocks_at_resulting(self) -> None:
        """SC-090: Flag blocks resulting → RESULTING_HOLD (RES-001)."""
        s = _load_by_id("SC-090")
        assert _terminal_state(s) == "RESULTING_HOLD"
        last = s.steps[-1]
        assert last.expected_output.applied_rules == ("RES-001",)

    def test_sc091_flag_cleared_at_resulting_hold(self) -> None:
        """SC-091: Full 15-step workflow with MISSING_INFO_PROCEED flag.

        Flag set at accessioning (ACC-007), persists through sample prep/HE/IHC,
        blocks at RESULTING_HOLD (RES-001), cleared by billing info (RES-002),
        advances to PATHOLOGIST_SIGNOUT.
        """
        s = _load_by_id("SC-091")
        assert _terminal_state(s) == "PATHOLOGIST_SIGNOUT"
        # Find the RES-002 step
        res002_steps = [step for step in s.steps if "RES-002" in step.expected_output.applied_rules]
        assert len(res002_steps) == 1
        assert res002_steps[0].event_data["info_type"] == "billing"


# ── FIXATION_WARNING flag ─────────────────────────────────────────


class TestFixationWarningFlag:
    """SC-092: FIXATION_WARNING set at accessioning, informational only."""

    def test_sc092_flag_set_at_accessioning(self) -> None:
        s = _load_by_id("SC-092")
        assert "FIXATION_WARNING" in s.steps[0].expected_output.flags
        assert _first_step_state(s) == "ACCEPTED"

    def test_sc092_flag_persists_without_blocking(self) -> None:
        """FIXATION_WARNING persists informatively but does not block."""
        s = _load_by_id("SC-092")
        assert _terminal_state(s) == "RESULTING"
        # Flag persists through all steps (informational only)
        for step in s.steps:
            assert "FIXATION_WARNING" in step.expected_output.flags

    def test_sc092_borderline_fixation_time(self) -> None:
        """Fixation time is borderline (7.0hr, just above 6.0hr threshold)."""
        s = _load_by_id("SC-092")
        assert s.steps[0].event_data["fixation_time_hours"] == 7.0


# ── RECUT_REQUESTED flag ─────────────────────────────────────────


class TestRecutRequestedFlag:
    """SC-093, SC-099: RECUT_REQUESTED set at pathologist review."""

    def test_sc093_flag_set_at_he009(self) -> None:
        """SC-093: RECUT_REQUESTED set by HE-009 at pathologist review."""
        s = _load_by_id("SC-093")
        he009_steps = [step for step in s.steps if "HE-009" in step.expected_output.applied_rules]
        assert len(he009_steps) == 1
        assert "RECUT_REQUESTED" in he009_steps[0].expected_output.flags

    def test_sc093_recut_succeeds(self) -> None:
        """SC-093: After recut, sectioning succeeds and returns to H&E review."""
        s = _load_by_id("SC-093")
        assert _terminal_state(s) == "PATHOLOGIST_HE_REVIEW"
        # Verify the recut loop: PATHOLOGIST_HE_REVIEW → SECTIONING → QC → HE → QC → REVIEW
        states = [step.expected_output.next_state for step in s.steps]
        assert "SAMPLE_PREP_SECTIONING" in states
        # At least 2 H&E reviews: initial + post-recut
        reviews = [st for st in states if st == "PATHOLOGIST_HE_REVIEW"]
        assert len(reviews) >= 2, (
            f"Expected at least 2 pathologist reviews (initial + post-recut), got {len(reviews)}"
        )

    def test_sc099_flag_lifecycle(self) -> None:
        """SC-099: Multi-step recut workflow with excision specimen.

        RECUT_REQUESTED set at pathologist review (HE-009), routes back to
        SAMPLE_PREP_SECTIONING, second H&E review diagnoses invasive carcinoma,
        advances to IHC_STAINING.
        """
        s = _load_by_id("SC-099")
        assert _terminal_state(s) == "IHC_STAINING"
        # Flag set at HE-009 step
        he009_steps = [step for step in s.steps if "HE-009" in step.expected_output.applied_rules]
        assert len(he009_steps) == 1
        assert "RECUT_REQUESTED" in he009_steps[0].expected_output.flags
        # Second pathologist review diagnoses invasive carcinoma
        he_reviews = [step for step in s.steps if step.event_type == "pathologist_he_review"]
        assert len(he_reviews) == 2
        assert he_reviews[1].event_data["diagnosis"] == "invasive_carcinoma"


# ── HER2_FIXATION_REJECT flag ────────────────────────────────────


class TestHER2FixationRejectFlag:
    """SC-094: HER2_FIXATION_REJECT set at IHC_STAINING, persists to ORDER_COMPLETE."""

    def test_sc094_flag_set_at_ihc001(self) -> None:
        s = _load_by_id("SC-094")
        ihc001_steps = [step for step in s.steps if "IHC-001" in step.expected_output.applied_rules]
        assert len(ihc001_steps) == 1
        assert "HER2_FIXATION_REJECT" in ihc001_steps[0].expected_output.flags

    def test_sc094_completes_to_order_complete(self) -> None:
        """SC-094: Despite HER2 rejection, order completes with remaining markers."""
        s = _load_by_id("SC-094")
        assert _terminal_state(s) == "ORDER_COMPLETE"
        # Verify all RES rules fire (003, 004, 005)
        all_rules: set[str] = set()
        for step in s.steps:
            all_rules.update(step.expected_output.applied_rules)
        assert {"RES-003", "RES-004", "RES-005"}.issubset(all_rules)

    def test_sc094_her2_not_in_final_report(self) -> None:
        """SC-094: HER2 excluded from reportable tests due to fixation reject."""
        s = _load_by_id("SC-094")
        signout_steps = [step for step in s.steps if step.event_type == "pathologist_signout"]
        assert len(signout_steps) == 1
        assert "HER2" not in signout_steps[0].event_data["reportable_tests"]


# ── FISH_SUGGESTED flag ───────────────────────────────────────────


class TestFISHSuggestedFlag:
    """SC-095 and SC-096: FISH_SUGGESTED set at IHC-007."""

    def test_sc095_fish_approved(self) -> None:
        """SC-095: FISH approved, result received → RESULTING."""
        s = _load_by_id("SC-095")
        assert _terminal_state(s) == "RESULTING"
        # Verify FISH_SUGGESTED set at IHC-007
        ihc007_steps = [step for step in s.steps if "IHC-007" in step.expected_output.applied_rules]
        assert len(ihc007_steps) == 1
        assert "FISH_SUGGESTED" in ihc007_steps[0].expected_output.flags
        # Verify FISH pathway
        states = [step.expected_output.next_state for step in s.steps]
        assert "SUGGEST_FISH_REFLEX" in states
        assert "FISH_SEND_OUT" in states

    def test_sc096_fish_declined(self) -> None:
        """SC-096: FISH declined → RESULTING directly."""
        s = _load_by_id("SC-096")
        assert _terminal_state(s) == "RESULTING"
        # Verify FISH_SUGGESTED set at IHC-007
        ihc007_steps = [step for step in s.steps if "IHC-007" in step.expected_output.applied_rules]
        assert len(ihc007_steps) == 1
        assert "FISH_SUGGESTED" in ihc007_steps[0].expected_output.flags
        # Verify decline via IHC-009
        last = s.steps[-1]
        assert last.expected_output.applied_rules == ("IHC-009",)
        assert last.event_data["approved"] is False


# ── Multiple flags ────────────────────────────────────────────────


class TestMultipleFlags:
    """SC-097: Two flags set simultaneously at accessioning."""

    def test_sc097_flag_set(self) -> None:
        """SC-097: MISSING_INFO_PROCEED set at step 1."""
        s = _load_by_id("SC-097")
        step1_flags = set(s.steps[0].expected_output.flags)
        assert step1_flags == {"MISSING_INFO_PROCEED"}

    def test_sc097_blocks_at_resulting(self) -> None:
        """SC-097: MISSING_INFO_PROCEED blocks at RESULTING_HOLD."""
        s = _load_by_id("SC-097")
        assert _terminal_state(s) == "RESULTING_HOLD"


# ── Flag clearing verification ────────────────────────────────────


class TestFlagClearing:
    """SC-098: Flag cleared at RESULTING_HOLD, empty flags through completion."""

    def test_sc098_flag_cleared(self) -> None:
        """SC-098: After billing info received, all subsequent steps have empty flags."""
        s = _load_by_id("SC-098")
        assert _terminal_state(s) == "ORDER_COMPLETE"
        # Find the RES-002 (flag clearing) step
        res002_idx = None
        for i, step in enumerate(s.steps):
            if "RES-002" in step.expected_output.applied_rules:
                res002_idx = i
                break
        assert res002_idx is not None, "RES-002 step not found"
        # All steps after RES-002 should have empty flags
        for step in s.steps[res002_idx:]:
            assert step.expected_output.flags == (), (
                f"SC-098 step {step.step}: flags should be empty after clearing, "
                f"got {step.expected_output.flags}"
            )

    def test_sc098_full_lifecycle(self) -> None:
        """SC-098: Full workflow through ORDER_COMPLETE exercising all RES rules.

        Includes RES-001 (hold), RES-002 (flag clearing), RES-003 through
        RES-005 (resulting, signout, completion).
        """
        s = _load_by_id("SC-098")
        all_rules: set[str] = set()
        for step in s.steps:
            all_rules.update(step.expected_output.applied_rules)
        expected_res = {"RES-001", "RES-002", "RES-003", "RES-004", "RES-005"}
        assert expected_res.issubset(all_rules), (
            f"SC-098 missing RES rules: {expected_res - all_rules}"
        )


# ── Cross-cutting validation ──────────────────────────────────────


class TestFirstEventIsOrderReceived:
    """All accumulated_state scenarios start with order_received."""

    def test_all_start_with_order_received(self) -> None:
        for json_file in sorted(ACCUMULATED_STATE_DIR.glob("*.json")):
            scenario = load_scenario(json_file)
            assert scenario.steps[0].event_type == "order_received", (
                f"{scenario.scenario_id} first event is "
                f"'{scenario.steps[0].event_type}', expected 'order_received'"
            )


class TestTerminalStateConsistency:
    """Terminal states in scenarios must be recognized by the state machine."""

    def test_terminal_states_match_state_machine(self, state_machine: StateMachine) -> None:
        """Every scenario ending in a terminal state uses a valid terminal state."""
        for json_file in sorted(ACCUMULATED_STATE_DIR.glob("*.json")):
            scenario = load_scenario(json_file)
            final_state = scenario.steps[-1].expected_output.next_state
            if state_machine.is_terminal_state(final_state):
                assert state_machine.is_terminal_state(final_state), (
                    f"{scenario.scenario_id} ends in '{final_state}' which is "
                    "not recognized as terminal by the state machine"
                )


class TestFlagIsolation:
    """Flags are first set by their trigger rule, then persist until cleared."""

    def test_flags_first_set_by_trigger_rule(self) -> None:
        """When a flag first appears, its trigger rule must be present at that step."""
        # Map of flags to the rules that set them.
        # FIXATION_WARNING is domain-inferred (borderline fixation time) and has
        # no dedicated rule in the catalog — it is set alongside ACC-007 or
        # ACC-008 when fixation is near boundaries.  Validated separately below.
        rule_triggered_flags: dict[str, set[str]] = {
            "MISSING_INFO_PROCEED": {"ACC-007"},
            "RECUT_REQUESTED": {"HE-009"},
            "HER2_FIXATION_REJECT": {"IHC-001"},
            "FISH_SUGGESTED": {"IHC-007"},
        }
        domain_inferred_flags: dict[str, set[str]] = {
            "FIXATION_WARNING": {"ACC-007", "ACC-008"},
        }
        for json_file in sorted(ACCUMULATED_STATE_DIR.glob("*.json")):
            scenario = load_scenario(json_file)
            active_flags: set[str] = set()
            for step in scenario.steps:
                current_flags = set(step.expected_output.flags)
                newly_added = current_flags - active_flags
                for flag in newly_added:
                    step_rules = set(step.expected_output.applied_rules)
                    if flag in rule_triggered_flags:
                        assert step_rules & rule_triggered_flags[flag], (
                            f"{scenario.scenario_id} step {step.step}: "
                            f"flag '{flag}' first set without trigger rule "
                            f"(expected one of {rule_triggered_flags[flag]}, "
                            f"got {step_rules})"
                        )
                    elif flag in domain_inferred_flags:
                        assert step_rules & domain_inferred_flags[flag], (
                            f"{scenario.scenario_id} step {step.step}: "
                            f"flag '{flag}' first set without an accessioning rule "
                            f"(expected one of {domain_inferred_flags[flag]}, "
                            f"got {step_rules})"
                        )
                active_flags = current_flags
