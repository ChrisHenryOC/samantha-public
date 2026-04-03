"""Red-team tests: type confusion in validator functions.

Feeds wrong types (string, None, int, bool, nested list) into classify_failure
and validate_prediction to surface implicit set()/Counter() bugs.
"""

from __future__ import annotations

from src.workflow.validator import (
    FailureType,
    classify_failure,
    validate_prediction,
    validate_rules,
    validate_state,
)
from tests.redteam.conftest import ALL_FLAG_IDS, ALL_RULE_IDS, ALL_STATES, _expected

# ---------------------------------------------------------------------------
# classify_failure — type confusion
# ---------------------------------------------------------------------------


class TestClassifyFailureTypeConfusion:
    """Feed non-list/non-string types into classify_failure fields."""

    def test_next_state_as_list(self) -> None:
        """List next_state → caught by type guard, returns WRONG_FIELD_TYPE."""
        pred = {"next_state": ["ACCEPTED"], "applied_rules": ["ACC-008"], "flags": []}
        result = classify_failure(pred, _expected(), ALL_STATES)
        assert result == FailureType.WRONG_FIELD_TYPE

    def test_next_state_as_int(self) -> None:
        """Integer next_state is not in all_states → WRONG_FIELD_TYPE."""
        pred = {"next_state": 42, "applied_rules": ["ACC-008"], "flags": []}
        result = classify_failure(pred, _expected(), ALL_STATES)
        assert result == FailureType.WRONG_FIELD_TYPE

    def test_next_state_as_none(self) -> None:
        """None next_state is not in all_states → WRONG_FIELD_TYPE."""
        pred = {"next_state": None, "applied_rules": ["ACC-008"], "flags": []}
        result = classify_failure(pred, _expected(), ALL_STATES)
        assert result == FailureType.WRONG_FIELD_TYPE

    def test_next_state_as_bool(self) -> None:
        """Bool next_state is not in all_states → WRONG_FIELD_TYPE."""
        pred = {"next_state": True, "applied_rules": ["ACC-008"], "flags": []}
        result = classify_failure(pred, _expected(), ALL_STATES)
        assert result == FailureType.WRONG_FIELD_TYPE

    def test_next_state_as_empty_string(self) -> None:
        """Empty string is not in all_states → HALLUCINATED_STATE."""
        pred = {"next_state": "", "applied_rules": ["ACC-008"], "flags": []}
        result = classify_failure(pred, _expected(), ALL_STATES)
        assert result == FailureType.HALLUCINATED_STATE

    def test_applied_rules_as_string(self) -> None:
        """String applied_rules → type guard catches it before set() iteration.

        Bug: set("ACC-001") produces {'A','C','-','0','1'} — character iteration.
        The type guard now catches this before the hallucination check.
        """
        pred = {"next_state": "ACCEPTED", "applied_rules": "ACC-001", "flags": []}
        result = classify_failure(pred, _expected(), ALL_STATES, all_rule_ids=ALL_RULE_IDS)
        # Type guard catches this before hallucination check.
        assert result == FailureType.WRONG_FIELD_TYPE

    def test_applied_rules_as_none(self) -> None:
        """None applied_rules → caught by type guard, returns WRONG_FIELD_TYPE."""
        pred = {"next_state": "ACCEPTED", "applied_rules": None, "flags": []}
        result = classify_failure(pred, _expected(), ALL_STATES, all_rule_ids=ALL_RULE_IDS)
        assert result == FailureType.WRONG_FIELD_TYPE

    def test_flags_as_string(self) -> None:
        """String flags → type guard catches it before set() iteration.

        Bug: set("FISH_SUGGESTED") produces {'F','I','S','H','_',...} — character iteration.
        The type guard now catches this before the hallucination check.
        """
        pred = {"next_state": "ACCEPTED", "applied_rules": ["ACC-008"], "flags": "FISH_SUGGESTED"}
        result = classify_failure(pred, _expected(), ALL_STATES, all_flag_ids=ALL_FLAG_IDS)
        # Type guard catches this before hallucination check.
        assert result == FailureType.WRONG_FIELD_TYPE

    def test_flags_as_none(self) -> None:
        """None flags → caught by type guard, returns WRONG_FIELD_TYPE."""
        pred = {"next_state": "ACCEPTED", "applied_rules": ["ACC-008"], "flags": None}
        result = classify_failure(pred, _expected(), ALL_STATES, all_flag_ids=ALL_FLAG_IDS)
        assert result == FailureType.WRONG_FIELD_TYPE

    def test_applied_rules_as_nested_list(self) -> None:
        """Nested list in applied_rules → caught by type guard, returns WRONG_FIELD_TYPE."""
        pred = {
            "next_state": "ACCEPTED",
            "applied_rules": [["ACC-001"]],
            "flags": [],
        }
        result = classify_failure(pred, _expected(), ALL_STATES, all_rule_ids=ALL_RULE_IDS)
        assert result == FailureType.WRONG_FIELD_TYPE

    def test_flags_as_nested_list(self) -> None:
        """Nested list in flags → type guard catches non-string inner list."""
        pred = {
            "next_state": "ACCEPTED",
            "applied_rules": ["ACC-008"],
            "flags": [["FISH_SUGGESTED"]],
        }
        result = classify_failure(pred, _expected(), ALL_STATES, all_flag_ids=ALL_FLAG_IDS)
        assert result == FailureType.WRONG_FIELD_TYPE

    def test_extra_keys_in_prediction_ignored(self) -> None:
        """Extra keys in prediction dict are silently ignored."""
        pred = {
            "next_state": "ACCEPTED",
            "applied_rules": ["ACC-008"],
            "flags": [],
            "reasoning": "some text",
            "confidence": 0.99,
        }
        result = classify_failure(pred, _expected(), ALL_STATES)
        assert result is None


# ---------------------------------------------------------------------------
# validate_prediction — type confusion
# ---------------------------------------------------------------------------


class TestValidatePredictionTypeConfusion:
    """Type mismatches flowing through validate_prediction."""

    def test_next_state_as_int_both_sides(self) -> None:
        """Integer next_state on both sides: type guard returns False."""
        pred = {"next_state": 0, "applied_rules": [], "flags": []}
        exp = {"next_state": 0, "applied_rules": [], "flags": []}
        result = validate_prediction(pred, exp)
        assert result.state_correct is False

    def test_applied_rules_string_vs_list(self) -> None:
        """String vs list applied_rules: Counter mismatch."""
        pred = {"next_state": "ACCEPTED", "applied_rules": "ACC-008", "flags": []}
        exp = {"next_state": "ACCEPTED", "applied_rules": ["ACC-008"], "flags": []}
        result = validate_prediction(pred, exp)
        # Counter("ACC-008") counts characters, Counter(["ACC-008"]) counts the string.
        assert result.rules_correct is False

    def test_applied_rules_string_both_sides_matches(self) -> None:
        """String applied_rules on both sides: type guard returns False.

        Previously Counter("ACC-008") == Counter("ACC-008") was True because
        both sides iterated characters identically. The type guard in
        validate_rules() now catches non-list inputs and returns False.
        """
        pred = {"next_state": "ACCEPTED", "applied_rules": "ACC-008", "flags": []}
        exp = {"next_state": "ACCEPTED", "applied_rules": "ACC-008", "flags": []}
        result = validate_prediction(pred, exp)
        assert result.rules_correct is False


# ---------------------------------------------------------------------------
# validate_state — string edge cases
# ---------------------------------------------------------------------------


class TestValidateStateEdgeCases:
    """String handling edge cases in validate_state."""

    def test_case_sensitivity(self) -> None:
        """Lowercase vs uppercase: exact match is case-sensitive."""
        assert validate_state("accepted", "ACCEPTED") is False

    def test_whitespace_padding(self) -> None:
        """Whitespace padding: exact match does not strip."""
        assert validate_state(" ACCEPTED ", "ACCEPTED") is False

    def test_unicode_homoglyph(self) -> None:
        """Unicode look-alike characters don't match ASCII."""
        # U+0410 Cyrillic А vs ASCII A
        assert validate_state("\u0410CCEPTED", "ACCEPTED") is False


# ---------------------------------------------------------------------------
# validate_rules — type confusion
# ---------------------------------------------------------------------------


class TestValidateRulesTypeConfusion:
    """Type confusion in validate_rules via Counter."""

    def test_counter_string_vs_list_mismatch(self) -> None:
        """Counter("ABC") != Counter(["ABC"]) — different iteration."""
        assert validate_rules("ABC", ["ABC"]) is False  # type: ignore[arg-type]

    def test_counter_string_both_sides_match(self) -> None:
        """Counter("ABC") == Counter("ABC") — type guard now prevents this."""
        assert validate_rules("ABC", "ABC") is False  # type: ignore[arg-type]
