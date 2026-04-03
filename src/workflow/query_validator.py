"""Validation functions for comparing query predictions against ground truth.

Provides set-based and sequence-based order ID validation, precision/recall/F1
computation, and a failure classifier for query prediction errors.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class QueryFailureType(Enum):
    """Categories of query prediction failure, ordered by classification priority."""

    TIMEOUT = "timeout"
    INVALID_JSON = "invalid_json"
    EMPTY_RESPONSE = "empty_response"
    WRONG_FIELD_NAMES = "wrong_field_names"
    WRONG_FIELD_TYPE = "wrong_field_type"
    WRONG_ORDER_IDS = "wrong_order_ids"
    WRONG_ORDER_SEQUENCE = "wrong_order_sequence"
    MISSING_ORDERS = "missing_orders"
    EXTRA_ORDERS = "extra_orders"


_REQUIRED_FIELDS: dict[str, set[str]] = {
    "order_list": {"order_ids", "reasoning"},
    "order_status": {"order_ids", "status_summary", "reasoning"},
    "explanation": {"explanation", "reasoning"},
    "prioritized_list": {"order_ids", "reasoning"},
}


@dataclass(frozen=True)
class QueryValidationResult:
    """Result of comparing a query prediction against expected ground truth."""

    order_ids_correct: bool
    precision: float
    recall: float
    f1: float

    @property
    def all_correct(self) -> bool:
        """True if order IDs match exactly."""
        return self.order_ids_correct

    def __post_init__(self) -> None:
        for field_name in ("precision", "recall", "f1"):
            val = getattr(self, field_name)
            if not isinstance(val, (int, float)):
                raise TypeError(f"{field_name} must be numeric, got {type(val).__name__}")
            if val < 0.0 or val > 1.0:
                raise ValueError(f"{field_name} must be in [0.0, 1.0], got {val}")


def _is_string_list(value: Any) -> bool:
    """Check if value is a list of strings."""
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _score_order_id_sets(
    predicted_set: set[str], expected_set: set[str]
) -> tuple[float, float, float]:
    """Compute precision, recall, and F1 from predicted/expected sets."""
    if not predicted_set and not expected_set:
        return (1.0, 1.0, 1.0)

    intersection = predicted_set & expected_set
    precision = len(intersection) / len(predicted_set) if predicted_set else 0.0
    recall = len(intersection) / len(expected_set) if expected_set else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return (precision, recall, f1)


def validate_order_ids_set(
    predicted: list[str], expected: list[str]
) -> tuple[bool, float, float, float]:
    """Validate order IDs as unordered sets, computing precision/recall/F1.

    Duplicate IDs in either list are ignored (treated as a set).

    Returns:
        Tuple of (exact_match, precision, recall, f1).
    """
    predicted_set = set(predicted)
    expected_set = set(expected)
    exact_match = predicted_set == expected_set
    precision, recall, f1 = _score_order_id_sets(predicted_set, expected_set)
    return (exact_match, precision, recall, f1)


def validate_order_ids_sequence(
    predicted: list[str], expected: list[str]
) -> tuple[bool, float, float, float]:
    """Validate order IDs as ordered sequences, computing precision/recall/F1.

    Exact match requires both the same elements and the same order.
    Precision/recall are set-based (order doesn't affect partial scores).
    Duplicate IDs in either list are ignored for set-based scoring.

    Returns:
        Tuple of (exact_match, precision, recall, f1).
    """
    predicted_set = set(predicted)
    expected_set = set(expected)
    exact_match = predicted == expected
    precision, recall, f1 = _score_order_id_sets(predicted_set, expected_set)
    return (exact_match, precision, recall, f1)


def validate_query_prediction(
    prediction: dict[str, Any],
    expected: dict[str, Any],
    answer_type: str,
) -> QueryValidationResult:
    """Compare a query prediction against expected ground truth.

    Args:
        prediction: Model output dict.
        expected: Ground-truth dict with expected values.
        answer_type: One of order_list, order_status, explanation, prioritized_list.

    Raises:
        ValueError: If answer_type is not recognized.
    """
    if answer_type not in _REQUIRED_FIELDS:
        raise ValueError(f"Unknown answer_type: {answer_type}")

    if answer_type == "explanation":
        return QueryValidationResult(
            order_ids_correct=True,
            precision=1.0,
            recall=1.0,
            f1=1.0,
        )

    predicted_ids = prediction.get("order_ids", [])
    expected_ids = expected.get("order_ids", [])

    if not _is_string_list(predicted_ids):
        return QueryValidationResult(order_ids_correct=False, precision=0.0, recall=0.0, f1=0.0)
    if not _is_string_list(expected_ids):
        raise ValueError(
            f"expected['order_ids'] must be a list of strings, got {type(expected_ids).__name__}"
        )

    if answer_type == "prioritized_list":
        exact, prec, rec, f1 = validate_order_ids_sequence(predicted_ids, expected_ids)
    else:
        exact, prec, rec, f1 = validate_order_ids_set(predicted_ids, expected_ids)

    return QueryValidationResult(
        order_ids_correct=exact,
        precision=prec,
        recall=rec,
        f1=f1,
    )


def classify_query_failure(
    prediction: dict[str, Any] | None,
    expected: dict[str, Any],
    answer_type: str,
    *,
    timed_out: bool = False,
) -> QueryFailureType | None:
    """Classify the type of query prediction failure, or ``None`` if correct.

    Classification priority (highest first):
    TIMEOUT > INVALID_JSON > EMPTY_RESPONSE > WRONG_FIELD_NAMES >
    WRONG_FIELD_TYPE > (content checks) > None
    """
    if answer_type not in _REQUIRED_FIELDS:
        raise ValueError(f"Unknown answer_type: {answer_type}")

    if timed_out:
        return QueryFailureType.TIMEOUT

    if prediction is None:
        return QueryFailureType.INVALID_JSON

    if not prediction:
        return QueryFailureType.EMPTY_RESPONSE

    required = _REQUIRED_FIELDS[answer_type]
    if not required.issubset(prediction.keys()):
        return QueryFailureType.WRONG_FIELD_NAMES

    # Type checks
    if not isinstance(prediction.get("reasoning"), str):
        return QueryFailureType.WRONG_FIELD_TYPE
    if answer_type != "explanation" and not _is_string_list(prediction["order_ids"]):
        return QueryFailureType.WRONG_FIELD_TYPE
    if answer_type == "order_status" and not isinstance(prediction.get("status_summary"), str):
        return QueryFailureType.WRONG_FIELD_TYPE
    if answer_type == "explanation" and not isinstance(prediction.get("explanation"), str):
        return QueryFailureType.WRONG_FIELD_TYPE

    # For explanation type, if structurally valid, it's correct
    if answer_type == "explanation":
        return None

    # Content checks for order types
    predicted_ids = prediction["order_ids"]
    expected_ids = expected.get("order_ids", [])
    predicted_set = set(predicted_ids)
    expected_set = set(expected_ids)

    missing = expected_set - predicted_set
    extra = predicted_set - expected_set

    if missing and extra:
        return QueryFailureType.WRONG_ORDER_IDS

    if missing:
        return QueryFailureType.MISSING_ORDERS

    if extra:
        return QueryFailureType.EXTRA_ORDERS

    # Same set — check sequence for prioritized_list
    if answer_type == "prioritized_list" and predicted_ids != expected_ids:
        return QueryFailureType.WRONG_ORDER_SEQUENCE

    return None
