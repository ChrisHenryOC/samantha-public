"""Red-team tests: source-of-truth synchronization.

Verifies that YAML, _STATE_TO_STEP, and models.VALID_STATES / VALID_FLAGS
all agree. Catches drift when one is updated but others are not.
"""

from __future__ import annotations

import pytest

from src.workflow.models import VALID_FLAGS, VALID_STATES
from src.workflow.state_machine import (
    _STATE_TO_STEP,
    StateMachine,
)


@pytest.fixture(scope="module")
def sm() -> StateMachine:
    return StateMachine()


# ---------------------------------------------------------------------------
# _STATE_TO_STEP coverage
# ---------------------------------------------------------------------------


class TestStateToStepCoverage:
    """Every key/value in _STATE_TO_STEP references real YAML entries."""

    def test_every_key_is_a_valid_state(self, sm: StateMachine) -> None:
        """Every state mapped in _STATE_TO_STEP exists in YAML."""
        all_states = sm.get_all_states()
        for state in _STATE_TO_STEP:
            assert state in all_states, f"{state} in _STATE_TO_STEP but not in YAML"

    def test_every_value_is_a_valid_step(self, sm: StateMachine) -> None:
        """Every step mapped to in _STATE_TO_STEP has rules in YAML."""
        for state, step in _STATE_TO_STEP.items():
            rules = sm.get_rules_for_step(step)
            assert len(rules) > 0, f"_STATE_TO_STEP maps {state}→{step} but {step} has no rules"

    def test_ihc_states_not_in_state_to_step(self, sm: StateMachine) -> None:
        """IHC states use applies_at, not _STATE_TO_STEP."""
        ihc_states = {sid for sid, s in sm._states.items() if s.phase == "ihc"}
        for state in ihc_states:
            assert state not in _STATE_TO_STEP, f"IHC state {state} should not be in _STATE_TO_STEP"

    def test_unmapped_states_return_empty_rules(self, sm: StateMachine) -> None:
        """States not in _STATE_TO_STEP and without applies_at rules return []."""
        # These are pass-through or terminal states that intentionally have no rules.
        unmapped_non_ihc = sm.get_all_states() - frozenset(_STATE_TO_STEP.keys())
        ihc_states = {sid for sid, s in sm._states.items() if s.phase == "ihc"}
        pass_through_or_terminal = unmapped_non_ihc - ihc_states
        for state in pass_through_or_terminal:
            rules = sm.get_rules_for_state(state)
            assert rules == [], f"Unmapped state {state} unexpectedly has rules: {rules}"


# ---------------------------------------------------------------------------
# Model constants sync
# ---------------------------------------------------------------------------


class TestModelConstantsSync:
    """models.VALID_STATES and VALID_FLAGS match StateMachine."""

    def test_valid_states_match_yaml(self, sm: StateMachine) -> None:
        """models.VALID_STATES == sm.get_all_states()."""
        assert sm.get_all_states() == VALID_STATES

    def test_valid_flags_match_yaml(self, sm: StateMachine) -> None:
        """models.VALID_FLAGS == sm.get_all_flag_ids()."""
        assert sm.get_all_flag_ids() == VALID_FLAGS

    def test_terminal_states_match_yaml_terminal_field(self, sm: StateMachine) -> None:
        """terminal_states list matches states with terminal: true in YAML."""
        states_marked_terminal = frozenset(
            sid for sid, state in sm._states.items() if state.terminal is True
        )
        assert sm._terminal_states == states_marked_terminal


# ---------------------------------------------------------------------------
# _STATE_TO_STEP completeness
# ---------------------------------------------------------------------------


class TestStateToStepCompleteness:
    """Every state is covered by _STATE_TO_STEP, applies_at, or an allowlist."""

    def test_every_state_has_rule_coverage(self, sm: StateMachine) -> None:
        """Every state is in _STATE_TO_STEP, has applies_at rules, or is
        an intentionally ruleless state (pass-through or terminal).
        """
        # States that intentionally return empty rules.
        ruleless_allowlist = {
            # Pass-through states
            "MISSING_INFO_HOLD",
            "DO_NOT_PROCESS",
            "HE_STAINING",
            # Terminal states
            "ORDER_COMPLETE",
            "ORDER_TERMINATED",
            "ORDER_TERMINATED_QNS",
        }

        mapped_states = frozenset(_STATE_TO_STEP.keys())

        # States with applies_at rules (IHC states that have rules).
        states_with_applies_at = frozenset(
            rule.applies_at for rule in sm._rules if rule.applies_at is not None
        )

        for state in sm.get_all_states():
            covered = (
                state in mapped_states
                or state in states_with_applies_at
                or state in ruleless_allowlist
            )
            assert covered, (
                f"State {state} is not in _STATE_TO_STEP, has no applies_at rules, "
                f"and is not in the ruleless allowlist"
            )
