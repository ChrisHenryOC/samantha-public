"""Tests for query validation functions.

Pure data tests — no mocks, no I/O. Covers all failure types, precision/recall
edge cases, sequence ordering, and explanation passthrough.
"""

from __future__ import annotations

import pytest

from src.workflow.query_validator import (
    QueryFailureType,
    QueryValidationResult,
    classify_query_failure,
    validate_order_ids_sequence,
    validate_order_ids_set,
    validate_query_prediction,
)

# --- TestQueryValidationResult ---


class TestQueryValidationResult:
    def test_all_correct_property(self) -> None:
        r = QueryValidationResult(order_ids_correct=True, precision=1.0, recall=1.0, f1=1.0)
        assert r.all_correct is True

    def test_not_all_correct(self) -> None:
        r = QueryValidationResult(order_ids_correct=False, precision=0.5, recall=0.5, f1=0.5)
        assert r.all_correct is False

    def test_precision_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="precision"):
            QueryValidationResult(order_ids_correct=True, precision=1.5, recall=1.0, f1=1.0)

    def test_recall_negative(self) -> None:
        with pytest.raises(ValueError, match="recall"):
            QueryValidationResult(order_ids_correct=True, precision=1.0, recall=-0.1, f1=1.0)

    def test_f1_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="f1"):
            QueryValidationResult(order_ids_correct=True, precision=1.0, recall=1.0, f1=2.0)

    def test_non_numeric_precision(self) -> None:
        with pytest.raises(TypeError, match="precision"):
            QueryValidationResult(
                order_ids_correct=True,
                precision="high",
                recall=1.0,
                f1=1.0,  # type: ignore[arg-type]
            )

    def test_frozen(self) -> None:
        r = QueryValidationResult(order_ids_correct=True, precision=1.0, recall=1.0, f1=1.0)
        with pytest.raises(AttributeError):
            r.precision = 0.5  # type: ignore[misc]


# --- TestValidateOrderIdsSet ---


class TestValidateOrderIdsSet:
    def test_exact_match(self) -> None:
        exact, prec, rec, f1 = validate_order_ids_set(["A", "B"], ["A", "B"])
        assert exact is True
        assert prec == 1.0
        assert rec == 1.0
        assert f1 == 1.0

    def test_order_independent(self) -> None:
        exact, prec, rec, f1 = validate_order_ids_set(["B", "A"], ["A", "B"])
        assert exact is True

    def test_partial_overlap(self) -> None:
        exact, prec, rec, f1 = validate_order_ids_set(["A", "C"], ["A", "B"])
        assert exact is False
        assert prec == 0.5
        assert rec == 0.5

    def test_completely_wrong(self) -> None:
        exact, prec, rec, f1 = validate_order_ids_set(["C", "D"], ["A", "B"])
        assert exact is False
        assert prec == 0.0
        assert rec == 0.0
        assert f1 == 0.0

    def test_empty_predicted(self) -> None:
        exact, prec, rec, f1 = validate_order_ids_set([], ["A", "B"])
        assert exact is False
        assert prec == 0.0
        assert rec == 0.0
        assert f1 == 0.0

    def test_empty_expected(self) -> None:
        exact, prec, rec, f1 = validate_order_ids_set(["A"], [])
        assert exact is False
        assert prec == 0.0
        assert rec == 0.0

    def test_both_empty(self) -> None:
        exact, prec, rec, f1 = validate_order_ids_set([], [])
        assert exact is True
        assert prec == 1.0
        assert rec == 1.0
        assert f1 == 1.0

    def test_extra_orders(self) -> None:
        exact, prec, rec, f1 = validate_order_ids_set(["A", "B", "C"], ["A", "B"])
        assert exact is False
        assert prec == pytest.approx(2 / 3)
        assert rec == 1.0

    def test_missing_orders(self) -> None:
        exact, prec, rec, f1 = validate_order_ids_set(["A"], ["A", "B"])
        assert exact is False
        assert prec == 1.0
        assert rec == 0.5


# --- TestValidateOrderIdsSequence ---


class TestValidateOrderIdsSequence:
    def test_exact_match(self) -> None:
        exact, prec, rec, f1 = validate_order_ids_sequence(["A", "B"], ["A", "B"])
        assert exact is True
        assert f1 == 1.0

    def test_wrong_order(self) -> None:
        exact, prec, rec, f1 = validate_order_ids_sequence(["B", "A"], ["A", "B"])
        assert exact is False
        assert prec == 1.0
        assert rec == 1.0
        assert f1 == 1.0

    def test_partial_overlap(self) -> None:
        exact, prec, rec, f1 = validate_order_ids_sequence(["A", "C"], ["A", "B"])
        assert exact is False
        assert prec == 0.5
        assert rec == 0.5

    def test_both_empty(self) -> None:
        exact, prec, rec, f1 = validate_order_ids_sequence([], [])
        assert exact is True
        assert f1 == 1.0

    def test_completely_wrong(self) -> None:
        exact, prec, rec, f1 = validate_order_ids_sequence(["X", "Y"], ["A", "B"])
        assert exact is False
        assert prec == 0.0
        assert rec == 0.0


# --- TestValidateQueryPrediction ---


class TestValidateQueryPrediction:
    def test_order_list_correct(self) -> None:
        result = validate_query_prediction(
            {"order_ids": ["A", "B"], "reasoning": "test"},
            {"order_ids": ["B", "A"]},
            "order_list",
        )
        assert result.all_correct is True
        assert result.precision == 1.0

    def test_order_list_wrong(self) -> None:
        result = validate_query_prediction(
            {"order_ids": ["A", "C"], "reasoning": "test"},
            {"order_ids": ["A", "B"]},
            "order_list",
        )
        assert result.all_correct is False
        assert result.precision == 0.5

    def test_order_status_correct(self) -> None:
        result = validate_query_prediction(
            {"order_ids": ["A"], "status_summary": "pending", "reasoning": "test"},
            {"order_ids": ["A"]},
            "order_status",
        )
        assert result.all_correct is True

    def test_prioritized_list_correct_order(self) -> None:
        result = validate_query_prediction(
            {"order_ids": ["A", "B", "C"], "reasoning": "test"},
            {"order_ids": ["A", "B", "C"]},
            "prioritized_list",
        )
        assert result.all_correct is True

    def test_prioritized_list_wrong_order(self) -> None:
        result = validate_query_prediction(
            {"order_ids": ["B", "A", "C"], "reasoning": "test"},
            {"order_ids": ["A", "B", "C"]},
            "prioritized_list",
        )
        assert result.all_correct is False
        assert result.precision == 1.0
        assert result.recall == 1.0

    def test_explanation_passthrough(self) -> None:
        result = validate_query_prediction(
            {"explanation": "some explanation", "reasoning": "test"},
            {},
            "explanation",
        )
        assert result.all_correct is True
        assert result.precision == 1.0
        assert result.recall == 1.0

    def test_unknown_answer_type(self) -> None:
        with pytest.raises(ValueError, match="Unknown answer_type"):
            validate_query_prediction({}, {}, "invalid_type")

    def test_string_order_ids_returns_zero_scores(self) -> None:
        result = validate_query_prediction(
            {"order_ids": "ORD-001", "reasoning": "test"},
            {"order_ids": ["ORD-001"]},
            "order_list",
        )
        assert result.all_correct is False
        assert result.precision == 0.0
        assert result.recall == 0.0

    def test_none_order_ids_returns_zero_scores(self) -> None:
        result = validate_query_prediction(
            {"order_ids": None, "reasoning": "test"},
            {"order_ids": ["A"]},
            "order_list",
        )
        assert result.all_correct is False
        assert result.precision == 0.0

    def test_invalid_expected_order_ids_raises(self) -> None:
        with pytest.raises(ValueError, match="expected"):
            validate_query_prediction(
                {"order_ids": ["A"], "reasoning": "test"},
                {"order_ids": "A"},
                "order_list",
            )

    def test_prioritized_list_single_element(self) -> None:
        result = validate_query_prediction(
            {"order_ids": ["A"], "reasoning": "test"},
            {"order_ids": ["A"]},
            "prioritized_list",
        )
        assert result.all_correct is True
        assert result.f1 == 1.0

    def test_duplicate_predicted_ids(self) -> None:
        result = validate_query_prediction(
            {"order_ids": ["A", "A", "B"], "reasoning": "test"},
            {"order_ids": ["A", "B"]},
            "order_list",
        )
        assert result.all_correct is True


# --- TestClassifyQueryFailure ---


class TestClassifyQueryFailure:
    def test_timeout(self) -> None:
        result = classify_query_failure(None, {}, "order_list", timed_out=True)
        assert result is QueryFailureType.TIMEOUT

    def test_invalid_json(self) -> None:
        result = classify_query_failure(None, {}, "order_list")
        assert result is QueryFailureType.INVALID_JSON

    def test_empty_response(self) -> None:
        result = classify_query_failure({}, {}, "order_list")
        assert result is QueryFailureType.EMPTY_RESPONSE

    def test_wrong_field_names(self) -> None:
        result = classify_query_failure(
            {"ids": ["A"], "reasoning": "test"},
            {"order_ids": ["A"]},
            "order_list",
        )
        assert result is QueryFailureType.WRONG_FIELD_NAMES

    def test_wrong_field_type_order_ids_not_list(self) -> None:
        result = classify_query_failure(
            {"order_ids": "A", "reasoning": "test"},
            {"order_ids": ["A"]},
            "order_list",
        )
        assert result is QueryFailureType.WRONG_FIELD_TYPE

    def test_wrong_field_type_order_ids_not_strings(self) -> None:
        result = classify_query_failure(
            {"order_ids": [1, 2], "reasoning": "test"},
            {"order_ids": ["A"]},
            "order_list",
        )
        assert result is QueryFailureType.WRONG_FIELD_TYPE

    def test_wrong_field_type_status_summary(self) -> None:
        result = classify_query_failure(
            {"order_ids": ["A"], "status_summary": 123, "reasoning": "test"},
            {"order_ids": ["A"]},
            "order_status",
        )
        assert result is QueryFailureType.WRONG_FIELD_TYPE

    def test_wrong_field_type_explanation_not_str(self) -> None:
        result = classify_query_failure(
            {"explanation": 42, "reasoning": "test"},
            {},
            "explanation",
        )
        assert result is QueryFailureType.WRONG_FIELD_TYPE

    def test_wrong_order_ids_both_missing_and_extra(self) -> None:
        result = classify_query_failure(
            {"order_ids": ["A", "C"], "reasoning": "test"},
            {"order_ids": ["A", "B"]},
            "order_list",
        )
        assert result is QueryFailureType.WRONG_ORDER_IDS

    def test_missing_orders(self) -> None:
        result = classify_query_failure(
            {"order_ids": ["A"], "reasoning": "test"},
            {"order_ids": ["A", "B"]},
            "order_list",
        )
        assert result is QueryFailureType.MISSING_ORDERS

    def test_extra_orders(self) -> None:
        result = classify_query_failure(
            {"order_ids": ["A", "B", "C"], "reasoning": "test"},
            {"order_ids": ["A", "B"]},
            "order_list",
        )
        assert result is QueryFailureType.EXTRA_ORDERS

    def test_wrong_order_sequence(self) -> None:
        result = classify_query_failure(
            {"order_ids": ["B", "A"], "reasoning": "test"},
            {"order_ids": ["A", "B"]},
            "prioritized_list",
        )
        assert result is QueryFailureType.WRONG_ORDER_SEQUENCE

    def test_correct_returns_none(self) -> None:
        result = classify_query_failure(
            {"order_ids": ["A", "B"], "reasoning": "test"},
            {"order_ids": ["A", "B"]},
            "order_list",
        )
        assert result is None

    def test_explanation_structurally_valid(self) -> None:
        result = classify_query_failure(
            {"explanation": "some text", "reasoning": "test"},
            {},
            "explanation",
        )
        assert result is None

    def test_unknown_answer_type(self) -> None:
        with pytest.raises(ValueError, match="Unknown answer_type"):
            classify_query_failure({"a": 1}, {}, "bad_type")

    def test_timeout_takes_priority_over_invalid_json(self) -> None:
        result = classify_query_failure(None, {}, "order_list", timed_out=True)
        assert result is QueryFailureType.TIMEOUT

    def test_correct_prioritized_list(self) -> None:
        result = classify_query_failure(
            {"order_ids": ["A", "B"], "reasoning": "test"},
            {"order_ids": ["A", "B"]},
            "prioritized_list",
        )
        assert result is None

    def test_reasoning_not_string(self) -> None:
        result = classify_query_failure(
            {"order_ids": ["A"], "reasoning": None},
            {"order_ids": ["A"]},
            "order_list",
        )
        assert result is QueryFailureType.WRONG_FIELD_TYPE

    def test_reasoning_missing_integer(self) -> None:
        result = classify_query_failure(
            {"order_ids": ["A"], "reasoning": 42},
            {"order_ids": ["A"]},
            "order_list",
        )
        assert result is QueryFailureType.WRONG_FIELD_TYPE

    def test_unknown_answer_type_with_none_prediction_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown answer_type"):
            classify_query_failure(None, {}, "bad_type")

    def test_unknown_answer_type_with_empty_prediction_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown answer_type"):
            classify_query_failure({}, {}, "bad_type")
