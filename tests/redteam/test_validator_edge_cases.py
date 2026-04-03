"""Red-team tests: boundary values, priority chain, and silent failures.

Tests large inputs, empty vocabularies, the full failure-type priority
ordering, and documents StateMachine methods that silently return defaults
for unknown states.
"""

from __future__ import annotations

import pytest

from src.workflow.state_machine import StateMachine
from src.workflow.validator import (
    FailureType,
    classify_failure,
)
from tests.redteam.conftest import ALL_FLAG_IDS, ALL_RULE_IDS, ALL_STATES, _expected

# ---------------------------------------------------------------------------
# classify_failure — boundary inputs
# ---------------------------------------------------------------------------


class TestClassifyFailureBoundaryInputs:
    """Boundary values and large inputs for classify_failure."""

    def test_10k_applied_rules(self) -> None:
        """10,000-element applied_rules list completes without error."""
        big_rules = [f"R-{i:05d}" for i in range(10_000)]
        pred = {"next_state": "ACCEPTED", "applied_rules": big_rules, "flags": []}
        # No all_rule_ids → skips hallucination check, falls to WRONG_RULES.
        result = classify_failure(pred, _expected(), ALL_STATES)
        assert result == FailureType.WRONG_RULES

    def test_10k_flags(self) -> None:
        """10,000-element flags list completes without error."""
        big_flags = [f"F-{i:05d}" for i in range(10_000)]
        pred = {"next_state": "ACCEPTED", "applied_rules": ["ACC-008"], "flags": big_flags}
        result = classify_failure(pred, _expected(), ALL_STATES)
        assert result == FailureType.WRONG_FLAGS

    def test_duplicate_rules_in_prediction_hallucination_vs_correctness(self) -> None:
        """Hallucination check uses set (deduplicates), correctness uses Counter (counts).

        A prediction with ["ACC-001", "ACC-001"] against expected ["ACC-001"]
        passes hallucination (set → {"ACC-001"} ⊆ ALL_RULE_IDS) but fails
        correctness (Counter mismatch).
        """
        pred = {
            "next_state": "ACCEPTED",
            "applied_rules": ["ACC-001", "ACC-001"],
            "flags": [],
        }
        exp = {"next_state": "ACCEPTED", "applied_rules": ["ACC-001"], "flags": []}
        result = classify_failure(pred, exp, ALL_STATES, all_rule_ids=ALL_RULE_IDS)
        # Passes hallucination check (set dedup), fails at WRONG_RULES (Counter).
        assert result == FailureType.WRONG_RULES

    def test_empty_all_states_everything_hallucinated(self) -> None:
        """Empty all_states frozenset → every state is 'hallucinated'."""
        pred = {"next_state": "ACCEPTED", "applied_rules": ["ACC-008"], "flags": []}
        result = classify_failure(pred, _expected(), frozenset())
        assert result == FailureType.HALLUCINATED_STATE

    def test_extra_keys_in_expected_ignored(self) -> None:
        """Extra keys in expected dict are silently ignored by classify_failure."""
        exp = {
            "next_state": "ACCEPTED",
            "applied_rules": ["ACC-008"],
            "flags": [],
            "reasoning": "expected reasoning",
        }
        pred = {"next_state": "ACCEPTED", "applied_rules": ["ACC-008"], "flags": []}
        result = classify_failure(pred, exp, ALL_STATES)
        assert result is None


# ---------------------------------------------------------------------------
# classify_failure — exhaustive priority chain
# ---------------------------------------------------------------------------


class TestClassifyFailurePriorityChain:
    """Exhaustively test every adjacent pair in the priority ordering.

    TIMEOUT > INVALID_JSON > EMPTY_RESPONSE > WRONG_FIELD_NAMES >
    WRONG_FIELD_TYPE > HALLUCINATED_STATE > HALLUCINATED_RULE >
    HALLUCINATED_FLAG > WRONG_STATE > WRONG_RULES > WRONG_FLAGS
    """

    def test_timeout_over_invalid_json(self) -> None:
        """TIMEOUT wins even when prediction is None (would be INVALID_JSON)."""
        result = classify_failure(None, _expected(), ALL_STATES, timed_out=True)
        assert result == FailureType.TIMEOUT

    def test_invalid_json_over_empty_response(self) -> None:
        """None prediction → INVALID_JSON (not EMPTY_RESPONSE for {})."""
        result = classify_failure(None, _expected(), ALL_STATES)
        assert result == FailureType.INVALID_JSON

    def test_empty_response_over_wrong_field_names(self) -> None:
        """Empty dict → EMPTY_RESPONSE (not WRONG_FIELD_NAMES for missing keys)."""
        result = classify_failure({}, _expected(), ALL_STATES)
        assert result == FailureType.EMPTY_RESPONSE

    def test_wrong_field_names_over_wrong_field_type(self) -> None:
        """Wrong keys → WRONG_FIELD_NAMES even if values have wrong types."""
        pred = {"state": 42, "rules": None, "flag_list": "not_a_list"}
        result = classify_failure(pred, _expected(), ALL_STATES)
        assert result == FailureType.WRONG_FIELD_NAMES

    def test_wrong_field_type_over_hallucinated_state(self) -> None:
        """Wrong type → WRONG_FIELD_TYPE even if value would be hallucinated."""
        pred = {"next_state": 42, "applied_rules": ["ACC-008"], "flags": []}
        result = classify_failure(pred, _expected(), ALL_STATES)
        assert result == FailureType.WRONG_FIELD_TYPE

    def test_hallucinated_state_over_hallucinated_rule(self) -> None:
        """Hallucinated state wins over hallucinated rule."""
        pred = {
            "next_state": "FANTASY",
            "applied_rules": ["FAKE-001"],
            "flags": [],
        }
        result = classify_failure(pred, _expected(), ALL_STATES, all_rule_ids=ALL_RULE_IDS)
        assert result == FailureType.HALLUCINATED_STATE

    def test_hallucinated_rule_over_hallucinated_flag(self) -> None:
        """Hallucinated rule wins over hallucinated flag."""
        pred = {
            "next_state": "ACCEPTED",
            "applied_rules": ["FAKE-001"],
            "flags": ["FAKE_FLAG"],
        }
        result = classify_failure(
            pred,
            _expected(),
            ALL_STATES,
            all_rule_ids=ALL_RULE_IDS,
            all_flag_ids=ALL_FLAG_IDS,
        )
        assert result == FailureType.HALLUCINATED_RULE

    def test_hallucinated_flag_over_wrong_state(self) -> None:
        """Hallucinated flag wins over wrong state."""
        pred = {
            "next_state": "ORDER_COMPLETE",
            "applied_rules": ["ACC-008"],
            "flags": ["FAKE_FLAG"],
        }
        result = classify_failure(pred, _expected(), ALL_STATES, all_flag_ids=ALL_FLAG_IDS)
        assert result == FailureType.HALLUCINATED_FLAG

    def test_wrong_state_over_wrong_rules(self) -> None:
        """Wrong state wins over wrong rules."""
        pred = {
            "next_state": "ORDER_COMPLETE",
            "applied_rules": ["ACC-001"],
            "flags": [],
        }
        result = classify_failure(pred, _expected(), ALL_STATES)
        assert result == FailureType.WRONG_STATE

    def test_wrong_rules_over_wrong_flags(self) -> None:
        """Wrong rules wins over wrong flags."""
        pred = {
            "next_state": "ACCEPTED",
            "applied_rules": ["ACC-001"],
            "flags": ["FISH_SUGGESTED"],
        }
        exp = {"next_state": "ACCEPTED", "applied_rules": ["ACC-008"], "flags": []}
        result = classify_failure(pred, exp, ALL_STATES)
        assert result == FailureType.WRONG_RULES


# ---------------------------------------------------------------------------
# StateMachine silent failures
# ---------------------------------------------------------------------------


class TestStateMachineSilentFailures:
    """Documents methods that silently return defaults for unknown states."""

    @pytest.fixture()
    def sm(self) -> StateMachine:
        return StateMachine()

    def test_is_valid_transition_unknown_from_state(self, sm: StateMachine) -> None:
        """Unknown from_state → False (no error raised)."""
        assert sm.is_valid_transition("NONEXISTENT", "ACCEPTED") is False

    def test_is_terminal_state_unknown_state(self, sm: StateMachine) -> None:
        """Unknown state → False (no error raised)."""
        assert sm.is_terminal_state("NONEXISTENT") is False

    def test_get_rules_for_step_unknown_step(self, sm: StateMachine) -> None:
        """Unknown step → empty list (no error raised)."""
        assert sm.get_rules_for_step("NONEXISTENT") == []

    def test_get_valid_transitions_unknown_state(self, sm: StateMachine) -> None:
        """Unknown state → empty list (no error raised)."""
        assert sm.get_valid_transitions("NONEXISTENT") == []

    def test_get_rules_for_state_unknown_raises(self, sm: StateMachine) -> None:
        """get_rules_for_state raises ValueError for unknown states.

        Documents the asymmetry: this is the ONLY method that raises for
        unknown states — all others silently return defaults.
        """
        with pytest.raises(ValueError, match="Unknown state"):
            sm.get_rules_for_state("NONEXISTENT")
