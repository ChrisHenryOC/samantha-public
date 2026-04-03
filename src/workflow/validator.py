"""Validation functions for comparing model predictions against ground truth.

Provides exact-match validation for state, rules, and flags, plus a failure
classifier that categorizes prediction errors by type.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Any


class FailureType(Enum):
    """Categories of prediction failure, ordered by classification priority."""

    TIMEOUT = "timeout"
    INVALID_JSON = "invalid_json"
    EMPTY_RESPONSE = "empty_response"
    WRONG_FIELD_NAMES = "wrong_field_names"
    WRONG_FIELD_TYPE = "wrong_field_type"
    HALLUCINATED_STATE = "hallucinated_state"
    HALLUCINATED_RULE = "hallucinated_rule"
    HALLUCINATED_FLAG = "hallucinated_flag"
    WRONG_STATE = "wrong_state"
    WRONG_RULES = "wrong_rules"
    WRONG_FLAGS = "wrong_flags"


@dataclass(frozen=True)
class ValidationResult:
    """Result of comparing a prediction against expected ground truth."""

    state_correct: bool
    rules_correct: bool
    flags_correct: bool

    @property
    def all_correct(self) -> bool:
        """True if state, rules, and flags all match."""
        return self.state_correct and self.rules_correct and self.flags_correct


def validate_state(predicted: str, expected: str) -> bool:
    """Check if the predicted state exactly matches the expected state."""
    if not isinstance(predicted, str) or not isinstance(expected, str):
        return False
    return predicted == expected


def validate_rules(predicted_rules: list[str], expected_rules: list[str]) -> bool:
    """Check if predicted rules match expected rules (order-independent, count-sensitive).

    Duplicate rule IDs are treated as distinct — ``["ACC-001", "ACC-001"]``
    does **not** match ``["ACC-001"]``.
    """
    if not isinstance(predicted_rules, list) or not isinstance(expected_rules, list):
        return False
    return Counter(predicted_rules) == Counter(expected_rules)


def validate_flags(predicted_flags: list[str], expected_flags: list[str]) -> bool:
    """Check if predicted flags match expected flags (order-independent, count-sensitive).

    Duplicate flag names are treated as distinct.
    """
    if not isinstance(predicted_flags, list) or not isinstance(expected_flags, list):
        return False
    return Counter(predicted_flags) == Counter(expected_flags)


_PREDICTION_KEYS = {"next_state", "applied_rules", "flags"}


def _is_string_list(value: Any) -> bool:
    """Check if value is a list of strings."""
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def validate_prediction(prediction: dict[str, Any], expected: dict[str, Any]) -> ValidationResult:
    """Compare a full prediction against expected ground truth.

    Args:
        prediction: Model output with keys ``next_state``, ``applied_rules``,
            and ``flags``.
        expected: Ground-truth dict with the same keys.

    Raises:
        ValueError: If either dict is missing a required key.
    """
    for label, d in (("prediction", prediction), ("expected", expected)):
        missing = _PREDICTION_KEYS - d.keys()
        if missing:
            raise ValueError(f"{label} missing required keys: {sorted(missing)}")

    return ValidationResult(
        state_correct=validate_state(prediction["next_state"], expected["next_state"]),
        rules_correct=validate_rules(prediction["applied_rules"], expected["applied_rules"]),
        flags_correct=validate_flags(prediction["flags"], expected["flags"]),
    )


def classify_failure(
    prediction: dict[str, Any] | None,
    expected: dict[str, Any],
    all_states: frozenset[str] | set[str],
    *,
    timed_out: bool = False,
    all_rule_ids: frozenset[str] | set[str] | None = None,
    all_flag_ids: frozenset[str] | set[str] | None = None,
) -> FailureType | None:
    """Classify the type of prediction failure, or ``None`` if correct.

    Args:
        prediction: Parsed model output dict, or ``None`` if parsing failed.
        expected: Ground-truth dict with ``next_state``, ``applied_rules``,
            ``flags``.
        all_states: Set of all valid state IDs for hallucination detection.
        timed_out: Whether the model timed out.
        all_rule_ids: Optional set of valid rule IDs.  When provided, enables
            ``HALLUCINATED_RULE`` classification.
        all_flag_ids: Optional set of valid flag IDs.  When provided, enables
            ``HALLUCINATED_FLAG`` classification.

    Classification priority (highest first):
    TIMEOUT > INVALID_JSON > EMPTY_RESPONSE > WRONG_FIELD_NAMES >
    WRONG_FIELD_TYPE > HALLUCINATED_STATE > HALLUCINATED_RULE >
    HALLUCINATED_FLAG > WRONG_STATE > WRONG_RULES > WRONG_FLAGS > None
    """
    if timed_out:
        return FailureType.TIMEOUT

    if prediction is None:
        return FailureType.INVALID_JSON

    if not prediction:
        return FailureType.EMPTY_RESPONSE

    required_keys = {"next_state", "applied_rules", "flags"}
    if not required_keys.issubset(prediction.keys()):
        return FailureType.WRONG_FIELD_NAMES

    # Type-check field values before set()/Counter() operations that crash
    # or silently produce wrong results on non-string/non-list inputs:
    # - non-str next_state: unhashable list crashes frozenset membership test
    # - non-list applied_rules/flags: set(None) crashes, set("str") iterates chars
    # - nested lists: set([["X"]]) crashes on unhashable inner list
    if not isinstance(prediction["next_state"], str):
        return FailureType.WRONG_FIELD_TYPE

    if not _is_string_list(prediction["applied_rules"]):
        return FailureType.WRONG_FIELD_TYPE

    if not _is_string_list(prediction["flags"]):
        return FailureType.WRONG_FIELD_TYPE

    if prediction["next_state"] not in all_states:
        return FailureType.HALLUCINATED_STATE

    if all_rule_ids is not None:
        predicted_rules = set(prediction["applied_rules"])
        if not predicted_rules.issubset(all_rule_ids):
            return FailureType.HALLUCINATED_RULE

    if all_flag_ids is not None:
        predicted_flags = set(prediction["flags"])
        if not predicted_flags.issubset(all_flag_ids):
            return FailureType.HALLUCINATED_FLAG

    if not validate_state(prediction["next_state"], expected["next_state"]):
        return FailureType.WRONG_STATE

    if not validate_rules(prediction["applied_rules"], expected["applied_rules"]):
        return FailureType.WRONG_RULES

    if not validate_flags(prediction["flags"], expected["flags"]):
        return FailureType.WRONG_FLAGS

    return None
