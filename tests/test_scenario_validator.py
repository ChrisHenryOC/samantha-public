"""Tests for scenario ground-truth consistency checker."""

from __future__ import annotations

from typing import Any

import pytest

from src.simulator.scenario_validator import (
    ScenarioValidationError,
    validate_all_scenarios,
    validate_scenario,
)
from src.simulator.schema import ExpectedOutput, Scenario, ScenarioStep
from src.workflow.state_machine import StateMachine

# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def _make_output(**overrides: Any) -> ExpectedOutput:
    defaults: dict[str, Any] = {
        "next_state": "ACCEPTED",
        "applied_rules": ("ACC-008",),
        "flags": (),
    }
    defaults.update(overrides)
    return ExpectedOutput(**defaults)


def _make_step(**overrides: Any) -> ScenarioStep:
    defaults: dict[str, Any] = {
        "step": 1,
        "event_type": "order_received",
        "event_data": {"patient_name": "TESTPATIENT-0001, Jane"},
        "expected_output": _make_output(),
    }
    defaults.update(overrides)
    return ScenarioStep(**defaults)


def _make_scenario(**overrides: Any) -> Scenario:
    defaults: dict[str, Any] = {
        "scenario_id": "SC-001",
        "category": "rule_coverage",
        "description": "Test scenario",
        "steps": (_make_step(),),
    }
    defaults.update(overrides)
    return Scenario(**defaults)


@pytest.fixture()
def sm() -> StateMachine:
    """Return the default StateMachine instance."""
    return StateMachine.get_instance()


# ---------------------------------------------------------------------------
# Check 1: First event
# ---------------------------------------------------------------------------


class TestFirstEvent:
    def test_first_event_order_received(self, sm: StateMachine) -> None:
        scenario = _make_scenario()
        errors = validate_scenario(scenario, sm)
        first_errors = [e for e in errors if e.error_type == "first_event"]
        assert first_errors == []

    # Note: The Scenario dataclass enforces first step = order_received
    # at construction time. The validator check is defensive (for when
    # validator might be used on raw data). We can't construct a Scenario
    # with wrong first event to test this, so we verify it doesn't
    # false-positive on valid scenarios.


# ---------------------------------------------------------------------------
# Check 2: Transition validity
# ---------------------------------------------------------------------------


class TestTransitionValidity:
    def test_valid_transition_no_error(self, sm: StateMachine) -> None:
        scenario = _make_scenario()
        errors = validate_scenario(scenario, sm)
        transition_errors = [e for e in errors if e.error_type == "invalid_transition"]
        assert transition_errors == []

    def test_invalid_transition(self, sm: StateMachine) -> None:
        # ACCESSIONING -> RESULTING is not a valid transition.
        step = _make_step(
            expected_output=_make_output(
                next_state="RESULTING",
                applied_rules=("RES-003",),
            ),
        )
        scenario = _make_scenario(steps=(step,))
        errors = validate_scenario(scenario, sm)
        transition_errors = [e for e in errors if e.error_type == "invalid_transition"]
        assert len(transition_errors) == 1
        assert "ACCESSIONING" in transition_errors[0].message
        assert "RESULTING" in transition_errors[0].message
        assert transition_errors[0].step_number == 1


# ---------------------------------------------------------------------------
# Check 3: Rule existence
# ---------------------------------------------------------------------------


class TestRuleExistence:
    def test_existing_rule_no_error(self, sm: StateMachine) -> None:
        scenario = _make_scenario()
        errors = validate_scenario(scenario, sm)
        rule_errors = [e for e in errors if e.error_type == "rule_not_found"]
        assert rule_errors == []

    def test_nonexistent_rule(self, sm: StateMachine) -> None:
        # ACC-999 is well-formatted (matches schema regex) but not
        # defined in the rule catalog.
        step = _make_step(
            expected_output=_make_output(
                next_state="ACCEPTED",
                applied_rules=("ACC-999",),
            ),
        )
        scenario = _make_scenario(steps=(step,))
        errors = validate_scenario(scenario, sm)
        rule_errors = [e for e in errors if e.error_type == "rule_not_found"]
        assert len(rule_errors) == 1
        assert "ACC-999" in rule_errors[0].message


# ---------------------------------------------------------------------------
# Check 4: Rule applicability
# ---------------------------------------------------------------------------


class TestRuleApplicability:
    def test_applicable_rule_no_error(self, sm: StateMachine) -> None:
        scenario = _make_scenario()
        errors = validate_scenario(scenario, sm)
        applicable_errors = [e for e in errors if e.error_type == "rule_not_applicable"]
        assert applicable_errors == []

    def test_rule_not_applicable_at_state(self, sm: StateMachine) -> None:
        # SP-001 is a SAMPLE_PREP rule, not applicable at ACCESSIONING.
        step = _make_step(
            expected_output=_make_output(
                next_state="ACCEPTED",
                applied_rules=("SP-001",),
            ),
        )
        scenario = _make_scenario(steps=(step,))
        errors = validate_scenario(scenario, sm)
        applicable_errors = [e for e in errors if e.error_type == "rule_not_applicable"]
        assert len(applicable_errors) == 1
        assert "SP-001" in applicable_errors[0].message
        assert "ACCESSIONING" in applicable_errors[0].message

    def test_ihc_rule_at_correct_state(self, sm: StateMachine) -> None:
        """IHC-002 applies at IHC_QC — should not raise rule_not_applicable.

        Walks a valid path from ACCESSIONING through to IHC_QC.
        """
        steps = (
            _make_step(),  # 1: ACCESSIONING -> ACCEPTED
            _make_step(  # 2: ACCEPTED -> SAMPLE_PREP_PROCESSING
                step=2,
                event_type="grossing_complete",
                event_data={"outcome": "success"},
                expected_output=_make_output(
                    next_state="SAMPLE_PREP_PROCESSING",
                    applied_rules=("SP-001",),
                ),
            ),
            _make_step(  # 3: -> SAMPLE_PREP_EMBEDDING
                step=3,
                event_type="processing_complete",
                event_data={"outcome": "success"},
                expected_output=_make_output(
                    next_state="SAMPLE_PREP_EMBEDDING",
                    applied_rules=("SP-001",),
                ),
            ),
            _make_step(  # 4: -> SAMPLE_PREP_SECTIONING
                step=4,
                event_type="embedding_complete",
                event_data={"outcome": "success"},
                expected_output=_make_output(
                    next_state="SAMPLE_PREP_SECTIONING",
                    applied_rules=("SP-001",),
                ),
            ),
            _make_step(  # 5: -> SAMPLE_PREP_QC
                step=5,
                event_type="sectioning_complete",
                event_data={"outcome": "success"},
                expected_output=_make_output(
                    next_state="SAMPLE_PREP_QC",
                    applied_rules=("SP-001",),
                ),
            ),
            _make_step(  # 6: -> HE_STAINING
                step=6,
                event_type="sample_prep_qc",
                event_data={"outcome": "pass"},
                expected_output=_make_output(
                    next_state="HE_STAINING",
                    applied_rules=("SP-004",),
                ),
            ),
            _make_step(  # 7: HE_STAINING -> HE_QC
                step=7,
                event_type="he_staining_complete",
                event_data={},
                expected_output=_make_output(
                    next_state="HE_QC",
                    applied_rules=(),
                ),
            ),
            _make_step(  # 8: HE_QC -> PATHOLOGIST_HE_REVIEW
                step=8,
                event_type="he_qc",
                event_data={"outcome": "pass"},
                expected_output=_make_output(
                    next_state="PATHOLOGIST_HE_REVIEW",
                    applied_rules=("HE-001",),
                ),
            ),
            _make_step(  # 9: -> IHC_STAINING
                step=9,
                event_type="pathologist_he_review",
                event_data={"diagnosis": "invasive_carcinoma"},
                expected_output=_make_output(
                    next_state="IHC_STAINING",
                    applied_rules=("HE-005",),
                ),
            ),
            _make_step(  # 10: IHC_STAINING -> IHC_QC
                step=10,
                event_type="ihc_staining_complete",
                event_data={},
                expected_output=_make_output(
                    next_state="IHC_QC",
                    applied_rules=(),
                ),
            ),
            _make_step(  # 11: IHC_QC -> IHC_SCORING (IHC-002)
                step=11,
                event_type="ihc_qc",
                event_data={"outcome": "all_pass"},
                expected_output=_make_output(
                    next_state="IHC_SCORING",
                    applied_rules=("IHC-002",),
                ),
            ),
        )
        scenario = _make_scenario(steps=steps)
        errors = validate_scenario(scenario, sm)
        applicable_errors = [e for e in errors if e.error_type == "rule_not_applicable"]
        assert applicable_errors == []


# ---------------------------------------------------------------------------
# Check 5: Flag existence
# ---------------------------------------------------------------------------


class TestFlagExistence:
    def test_existing_flag_no_error(self, sm: StateMachine) -> None:
        step = _make_step(
            expected_output=_make_output(
                next_state="MISSING_INFO_PROCEED",
                applied_rules=("ACC-007",),
                flags=("MISSING_INFO_PROCEED",),
            ),
        )
        scenario = _make_scenario(steps=(step,))
        errors = validate_scenario(scenario, sm)
        flag_errors = [e for e in errors if e.error_type == "flag_not_found"]
        assert flag_errors == []

    def test_valid_flag_no_false_positive(self, sm: StateMachine) -> None:
        # Flag existence is enforced by schema (ExpectedOutput.__post_init__
        # validates against VALID_FLAGS), so the flag_not_found code path
        # is defense-in-depth. We verify no false positives on known flags.
        step = _make_step(
            expected_output=_make_output(
                next_state="MISSING_INFO_PROCEED",
                applied_rules=("ACC-007",),
                flags=("MISSING_INFO_PROCEED",),
            ),
        )
        scenario = _make_scenario(steps=(step,))
        errors = validate_scenario(scenario, sm)
        flag_errors = [e for e in errors if e.error_type == "flag_not_found"]
        assert flag_errors == []


# ---------------------------------------------------------------------------
# Check 6: Flag lifecycle
# ---------------------------------------------------------------------------


class TestFlagLifecycle:
    def test_flag_at_correct_state(self, sm: StateMachine) -> None:
        """MISSING_INFO_PROCEED is set at ACCESSIONING — no error."""
        step = _make_step(
            expected_output=_make_output(
                next_state="MISSING_INFO_PROCEED",
                applied_rules=("ACC-007",),
                flags=("MISSING_INFO_PROCEED",),
            ),
        )
        scenario = _make_scenario(steps=(step,))
        errors = validate_scenario(scenario, sm)
        flag_errors = [e for e in errors if e.error_type == "flag_wrong_state"]
        assert flag_errors == []

    def test_flag_at_wrong_state(self, sm: StateMachine) -> None:
        """RECUT_REQUESTED can only be set at PATHOLOGIST_HE_REVIEW."""
        step1 = _make_step(
            expected_output=_make_output(
                next_state="ACCEPTED",
                applied_rules=("ACC-008",),
                flags=("RECUT_REQUESTED",),
            ),
        )
        scenario = _make_scenario(steps=(step1,))
        errors = validate_scenario(scenario, sm)
        flag_errors = [e for e in errors if e.error_type == "flag_wrong_state"]
        assert len(flag_errors) == 1
        assert "RECUT_REQUESTED" in flag_errors[0].message
        assert "ACCESSIONING" in flag_errors[0].message

    def test_flag_at_ihc_phase(self, sm: StateMachine) -> None:
        """FIXATION_WARNING can be set at IHC phase states (phase-level match).

        The flag vocabulary has set_at: [ACCESSIONING, IHC] where IHC is
        a phase name. This tests the _state_matches_set_at branch that
        resolves phase names to states via rule step matching.
        """
        # Walk to IHC_STAINING and set FIXATION_WARNING there.
        steps = (
            _make_step(),  # 1: ACCESSIONING -> ACCEPTED
            _make_step(  # 2: ACCEPTED -> SAMPLE_PREP_PROCESSING
                step=2,
                event_type="grossing_complete",
                event_data={"outcome": "success"},
                expected_output=_make_output(
                    next_state="SAMPLE_PREP_PROCESSING",
                    applied_rules=("SP-001",),
                ),
            ),
            _make_step(  # 3: -> SAMPLE_PREP_EMBEDDING
                step=3,
                event_type="processing_complete",
                event_data={"outcome": "success"},
                expected_output=_make_output(
                    next_state="SAMPLE_PREP_EMBEDDING",
                    applied_rules=("SP-001",),
                ),
            ),
            _make_step(  # 4: -> SAMPLE_PREP_SECTIONING
                step=4,
                event_type="embedding_complete",
                event_data={"outcome": "success"},
                expected_output=_make_output(
                    next_state="SAMPLE_PREP_SECTIONING",
                    applied_rules=("SP-001",),
                ),
            ),
            _make_step(  # 5: -> SAMPLE_PREP_QC
                step=5,
                event_type="sectioning_complete",
                event_data={"outcome": "success"},
                expected_output=_make_output(
                    next_state="SAMPLE_PREP_QC",
                    applied_rules=("SP-001",),
                ),
            ),
            _make_step(  # 6: -> HE_STAINING
                step=6,
                event_type="sample_prep_qc",
                event_data={"outcome": "pass"},
                expected_output=_make_output(
                    next_state="HE_STAINING",
                    applied_rules=("SP-004",),
                ),
            ),
            _make_step(  # 7: -> HE_QC
                step=7,
                event_type="he_staining_complete",
                event_data={},
                expected_output=_make_output(
                    next_state="HE_QC",
                    applied_rules=(),
                ),
            ),
            _make_step(  # 8: -> PATHOLOGIST_HE_REVIEW
                step=8,
                event_type="he_qc",
                event_data={"outcome": "pass"},
                expected_output=_make_output(
                    next_state="PATHOLOGIST_HE_REVIEW",
                    applied_rules=("HE-001",),
                ),
            ),
            _make_step(  # 9: -> IHC_STAINING
                step=9,
                event_type="pathologist_he_review",
                event_data={"diagnosis": "invasive_carcinoma"},
                expected_output=_make_output(
                    next_state="IHC_STAINING",
                    applied_rules=("HE-005",),
                ),
            ),
            _make_step(  # 10: IHC_STAINING -> IHC_STAINING (self-loop, IHC-001)
                step=10,
                event_type="ihc_staining_complete",
                event_data={"fixation_issue": True},
                expected_output=_make_output(
                    next_state="IHC_STAINING",
                    applied_rules=("IHC-001",),
                    flags=("FIXATION_WARNING",),
                ),
            ),
        )
        scenario = _make_scenario(steps=steps)
        errors = validate_scenario(scenario, sm)
        flag_errors = [e for e in errors if e.error_type == "flag_wrong_state"]
        assert flag_errors == []

    def test_flag_carried_forward_allowed(self, sm: StateMachine) -> None:
        """A flag set at step 1 can persist at step 2 without re-validation."""
        step1 = _make_step(
            expected_output=_make_output(
                next_state="MISSING_INFO_PROCEED",
                applied_rules=("ACC-007",),
                flags=("MISSING_INFO_PROCEED",),
            ),
        )
        step2 = _make_step(
            step=2,
            event_type="grossing_complete",
            event_data={"outcome": "success"},
            expected_output=_make_output(
                next_state="SAMPLE_PREP_PROCESSING",
                applied_rules=("SP-001",),
                flags=("MISSING_INFO_PROCEED",),
            ),
        )
        scenario = _make_scenario(steps=(step1, step2))
        errors = validate_scenario(scenario, sm)
        flag_errors = [e for e in errors if e.error_type == "flag_wrong_state"]
        assert flag_errors == []


# ---------------------------------------------------------------------------
# Check 7: State reachability (covered by check 2 transitivity)
# ---------------------------------------------------------------------------


class TestStateReachability:
    def test_reachable_chain(self, sm: StateMachine) -> None:
        """ACCESSIONING -> ACCEPTED -> SAMPLE_PREP_PROCESSING is reachable."""
        step1 = _make_step()  # ACCESSIONING -> ACCEPTED
        step2 = _make_step(
            step=2,
            event_type="grossing_complete",
            event_data={"outcome": "success"},
            expected_output=_make_output(
                next_state="SAMPLE_PREP_PROCESSING",
                applied_rules=("SP-001",),
            ),
        )  # ACCEPTED -> SAMPLE_PREP_PROCESSING
        scenario = _make_scenario(steps=(step1, step2))
        errors = validate_scenario(scenario, sm)
        transition_errors = [e for e in errors if e.error_type == "invalid_transition"]
        assert transition_errors == []

    def test_unreachable_jump(self, sm: StateMachine) -> None:
        """Skipping ACCEPTED straight to HE_STAINING is invalid."""
        step1 = _make_step(
            expected_output=_make_output(
                next_state="HE_STAINING",
                applied_rules=("ACC-008",),
            ),
        )
        scenario = _make_scenario(steps=(step1,))
        errors = validate_scenario(scenario, sm)
        transition_errors = [e for e in errors if e.error_type == "invalid_transition"]
        assert len(transition_errors) == 1


# ---------------------------------------------------------------------------
# Check 8: Terminal state handling
# ---------------------------------------------------------------------------


class TestTerminalStateHandling:
    def test_step_after_terminal_state(self, sm: StateMachine) -> None:
        """No steps should follow a terminal state."""
        step1_terminal = _make_step(
            expected_output=_make_output(
                next_state="DO_NOT_PROCESS",
                applied_rules=("ACC-003",),
            ),
        )
        step2_terminal = _make_step(
            step=2,
            event_type="missing_info_received",
            event_data={},
            expected_output=_make_output(
                next_state="ORDER_TERMINATED",
                applied_rules=(),
            ),
        )
        step3_after_terminal = _make_step(
            step=3,
            event_type="grossing_complete",
            event_data={},
            expected_output=_make_output(
                next_state="SAMPLE_PREP_PROCESSING",
                applied_rules=("SP-001",),
            ),
        )
        scenario = _make_scenario(
            steps=(step1_terminal, step2_terminal, step3_after_terminal),
        )
        errors = validate_scenario(scenario, sm)
        terminal_errors = [e for e in errors if e.error_type == "step_after_terminal"]
        assert len(terminal_errors) == 1
        assert terminal_errors[0].step_number == 3
        assert "ORDER_TERMINATED" in terminal_errors[0].message

    def test_scenario_ending_at_terminal_no_error(self, sm: StateMachine) -> None:
        """Scenario correctly ending at terminal state has no terminal errors."""
        step1 = _make_step(
            expected_output=_make_output(
                next_state="DO_NOT_PROCESS",
                applied_rules=("ACC-003",),
            ),
        )
        step2 = _make_step(
            step=2,
            event_type="missing_info_received",
            event_data={},
            expected_output=_make_output(
                next_state="ORDER_TERMINATED",
                applied_rules=(),
            ),
        )
        scenario = _make_scenario(steps=(step1, step2))
        errors = validate_scenario(scenario, sm)
        terminal_errors = [e for e in errors if e.error_type == "step_after_terminal"]
        assert terminal_errors == []


# ---------------------------------------------------------------------------
# Check 9: Event-state consistency
# ---------------------------------------------------------------------------


class TestEventStateConsistency:
    def test_matching_event_and_state(self, sm: StateMachine) -> None:
        """order_received at ACCESSIONING — no error."""
        scenario = _make_scenario()
        errors = validate_scenario(scenario, sm)
        event_errors = [e for e in errors if e.error_type == "event_state_mismatch"]
        assert event_errors == []

    def test_mismatched_event_and_state(self, sm: StateMachine) -> None:
        """processing_complete expects SAMPLE_PREP_PROCESSING, not ACCEPTED."""
        step1 = _make_step()  # ACCESSIONING -> ACCEPTED
        step2 = _make_step(
            step=2,
            event_type="processing_complete",  # Expects SAMPLE_PREP_PROCESSING
            event_data={"outcome": "success"},
            expected_output=_make_output(
                next_state="SAMPLE_PREP_PROCESSING",
                applied_rules=(),
            ),
        )  # Current state is ACCEPTED, but event expects SAMPLE_PREP_PROCESSING
        scenario = _make_scenario(steps=(step1, step2))
        errors = validate_scenario(scenario, sm)
        event_errors = [e for e in errors if e.error_type == "event_state_mismatch"]
        assert len(event_errors) == 1
        assert "processing_complete" in event_errors[0].message
        assert "SAMPLE_PREP_PROCESSING" in event_errors[0].message

    def test_unmapped_event_no_error(self, sm: StateMachine) -> None:
        """missing_info_received is not in _EVENT_STATE_MAP — no error."""
        step1 = _make_step(
            expected_output=_make_output(
                next_state="MISSING_INFO_HOLD",
                applied_rules=("ACC-001",),
            ),
        )
        step2 = _make_step(
            step=2,
            event_type="missing_info_received",
            event_data={"patient_name": "Smith, John"},
            expected_output=_make_output(
                next_state="ACCEPTED",
                applied_rules=("ACC-008",),
            ),
        )
        scenario = _make_scenario(steps=(step1, step2))
        errors = validate_scenario(scenario, sm)
        event_errors = [e for e in errors if e.error_type == "event_state_mismatch"]
        assert event_errors == []


# ---------------------------------------------------------------------------
# Check 10: Accessioning severity
# ---------------------------------------------------------------------------


class TestAccessioningSeverity:
    def test_multiple_rules_correct_severity(self, sm: StateMachine) -> None:
        """ACC-001 (HOLD) + ACC-007 (PROCEED) -> highest is HOLD -> MISSING_INFO_HOLD."""
        step = _make_step(
            expected_output=_make_output(
                next_state="MISSING_INFO_HOLD",
                applied_rules=("ACC-001", "ACC-007"),
                flags=("MISSING_INFO_PROCEED",),
            ),
        )
        scenario = _make_scenario(steps=(step,))
        errors = validate_scenario(scenario, sm)
        sev_errors = [e for e in errors if e.error_type == "accessioning_severity_mismatch"]
        assert sev_errors == []

    def test_multiple_rules_wrong_severity(self, sm: StateMachine) -> None:
        """ACC-003 (REJECT) + ACC-001 (HOLD) should go to DO_NOT_PROCESS, not MISSING_INFO_HOLD."""
        step = _make_step(
            expected_output=_make_output(
                next_state="MISSING_INFO_HOLD",
                applied_rules=("ACC-003", "ACC-001"),
            ),
        )
        scenario = _make_scenario(steps=(step,))
        errors = validate_scenario(scenario, sm)
        sev_errors = [e for e in errors if e.error_type == "accessioning_severity_mismatch"]
        assert len(sev_errors) == 1
        assert "REJECT" in sev_errors[0].message
        assert "DO_NOT_PROCESS" in sev_errors[0].message

    def test_single_rule_correct_severity(self, sm: StateMachine) -> None:
        """Single ACC-008 (ACCEPT) -> ACCEPTED passes severity check."""
        scenario = _make_scenario()
        errors = validate_scenario(scenario, sm)
        sev_errors = [e for e in errors if e.error_type == "accessioning_severity_mismatch"]
        assert sev_errors == []

    def test_single_rule_wrong_severity(self, sm: StateMachine) -> None:
        """Single ACC-003 (REJECT) should go to DO_NOT_PROCESS, not ACCEPTED."""
        step = _make_step(
            expected_output=_make_output(
                next_state="ACCEPTED",
                applied_rules=("ACC-003",),
            ),
        )
        scenario = _make_scenario(steps=(step,))
        errors = validate_scenario(scenario, sm)
        sev_errors = [e for e in errors if e.error_type == "accessioning_severity_mismatch"]
        assert len(sev_errors) == 1
        assert "REJECT" in sev_errors[0].message
        assert "DO_NOT_PROCESS" in sev_errors[0].message


# ---------------------------------------------------------------------------
# Multi-error detection
# ---------------------------------------------------------------------------


class TestMultiErrorDetection:
    def test_finds_all_errors_not_just_first(self, sm: StateMachine) -> None:
        """Scenario with multiple issues returns ALL errors."""
        # ACCESSIONING -> ACCEPTED is valid, but we set wrong rules and flags.
        step1 = _make_step(
            expected_output=_make_output(
                next_state="ACCEPTED",
                applied_rules=("SP-001",),  # Wrong: SP-001 not applicable at ACCESSIONING
                flags=("RECUT_REQUESTED",),  # Wrong: RECUT_REQUESTED not set at ACCESSIONING
            ),
        )
        # Step 2: processing_complete at ACCEPTED (event-state mismatch).
        step2 = _make_step(
            step=2,
            event_type="processing_complete",
            event_data={"outcome": "success"},
            expected_output=_make_output(
                next_state="SAMPLE_PREP_PROCESSING",
                applied_rules=("SP-001",),
            ),
        )
        scenario = _make_scenario(steps=(step1, step2))
        errors = validate_scenario(scenario, sm)
        error_types = {e.error_type for e in errors}
        # Should find at least: rule_not_applicable, flag_wrong_state,
        # event_state_mismatch (processing_complete at ACCEPTED).
        assert "rule_not_applicable" in error_types
        assert "flag_wrong_state" in error_types
        assert "event_state_mismatch" in error_types
        assert len(errors) >= 3

    def test_multiple_errors_single_step(self, sm: StateMachine) -> None:
        """Single step with multiple issues returns multiple errors."""
        step = _make_step(
            expected_output=_make_output(
                next_state="ACCEPTED",
                applied_rules=("SP-001", "HE-002"),  # Two wrong-state rules
                flags=("RECUT_REQUESTED", "FISH_SUGGESTED"),  # Two wrong-state flags
            ),
        )
        scenario = _make_scenario(steps=(step,))
        errors = validate_scenario(scenario, sm)
        rule_errors = [e for e in errors if e.error_type == "rule_not_applicable"]
        flag_errors = [e for e in errors if e.error_type == "flag_wrong_state"]
        assert len(rule_errors) == 2
        assert len(flag_errors) == 2
        # All errors should be on step 1.
        assert all(e.step_number == 1 for e in errors)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_single_step_scenario(self, sm: StateMachine) -> None:
        """Single-step scenario with valid data passes."""
        scenario = _make_scenario()
        errors = validate_scenario(scenario, sm)
        assert errors == []

    def test_correct_full_scenario_no_errors(self, sm: StateMachine) -> None:
        """A well-formed multi-step scenario produces zero errors."""
        step1 = _make_step()  # ACCESSIONING -> ACCEPTED
        step2 = _make_step(
            step=2,
            event_type="grossing_complete",
            event_data={"outcome": "success"},
            expected_output=_make_output(
                next_state="SAMPLE_PREP_PROCESSING",
                applied_rules=("SP-001",),
            ),
        )  # ACCEPTED -> SAMPLE_PREP_PROCESSING
        scenario = _make_scenario(steps=(step1, step2))
        errors = validate_scenario(scenario, sm)
        assert errors == []


# ---------------------------------------------------------------------------
# ScenarioValidationError dataclass
# ---------------------------------------------------------------------------


class TestScenarioValidationError:
    def test_construction(self) -> None:
        error = ScenarioValidationError(
            scenario_id="SC-001",
            step_number=2,
            error_type="invalid_transition",
            message="Invalid transition from 'A' to 'B'",
        )
        assert error.scenario_id == "SC-001"
        assert error.step_number == 2
        assert error.error_type == "invalid_transition"
        assert "Invalid transition" in error.message

    def test_step_number_none(self) -> None:
        """step_number=None is used for scenario-level errors (e.g., first_event)."""
        error = ScenarioValidationError(
            scenario_id="SC-001",
            step_number=None,
            error_type="first_event",
            message="First event wrong",
        )
        assert error.step_number is None

    def test_frozen(self) -> None:
        error = ScenarioValidationError(
            scenario_id="SC-001",
            step_number=1,
            error_type="test",
            message="test",
        )
        with pytest.raises(AttributeError):
            error.scenario_id = "SC-999"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# validate_all_scenarios
# ---------------------------------------------------------------------------


class TestValidateAllScenarios:
    def test_batch_validation(self, sm: StateMachine) -> None:
        """Multiple scenarios combined errors."""
        good = _make_scenario(scenario_id="SC-001")
        bad = _make_scenario(
            scenario_id="SC-002",
            steps=(
                _make_step(
                    expected_output=_make_output(
                        next_state="ACCEPTED",
                        applied_rules=("SP-001",),  # Wrong step rules
                    ),
                ),
            ),
        )
        errors = validate_all_scenarios([good, bad], sm)
        assert all(e.scenario_id == "SC-002" for e in errors)
        assert len(errors) >= 1

    def test_empty_list(self, sm: StateMachine) -> None:
        errors = validate_all_scenarios([], sm)
        assert errors == []

    def test_all_good_scenarios(self, sm: StateMachine) -> None:
        sc1 = _make_scenario(scenario_id="SC-001")
        sc2 = _make_scenario(scenario_id="SC-002")
        errors = validate_all_scenarios([sc1, sc2], sm)
        assert errors == []
