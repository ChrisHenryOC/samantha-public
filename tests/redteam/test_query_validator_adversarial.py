"""Red-team tests for src/workflow/query_validator.py — adversarial inputs and priority chain."""

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

# ---------------------------------------------------------------------------
# QueryValidationResult __post_init__
# ---------------------------------------------------------------------------


class TestQueryValidationResultPostInit:
    """Validate QueryValidationResult boundary conditions."""

    def test_precision_above_one_rejected(self) -> None:
        with pytest.raises(ValueError, match="precision must be in"):
            QueryValidationResult(order_ids_correct=True, precision=1.1, recall=1.0, f1=1.0)

    def test_recall_below_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="recall must be in"):
            QueryValidationResult(order_ids_correct=False, precision=0.0, recall=-0.1, f1=0.0)

    def test_f1_as_string_rejected(self) -> None:
        with pytest.raises(TypeError, match="f1 must be numeric"):
            QueryValidationResult(
                order_ids_correct=True,
                precision=1.0,
                recall=1.0,
                f1="high",  # type: ignore[arg-type]
            )

    def test_zeros_valid(self) -> None:
        r = QueryValidationResult(order_ids_correct=False, precision=0.0, recall=0.0, f1=0.0)
        assert not r.all_correct

    def test_ones_valid(self) -> None:
        r = QueryValidationResult(order_ids_correct=True, precision=1.0, recall=1.0, f1=1.0)
        assert r.all_correct


# ---------------------------------------------------------------------------
# validate_order_ids_set edge cases
# ---------------------------------------------------------------------------


class TestValidateOrderIdsSetEdgeCases:
    """Edge cases for set-based order ID validation."""

    def test_both_empty(self) -> None:
        exact, prec, rec, f1 = validate_order_ids_set([], [])
        assert exact is True
        assert prec == 1.0 and rec == 1.0 and f1 == 1.0

    def test_predicted_empty(self) -> None:
        exact, prec, rec, f1 = validate_order_ids_set([], ["A"])
        assert exact is False
        assert prec == 0.0 and rec == 0.0

    def test_expected_empty(self) -> None:
        exact, prec, rec, f1 = validate_order_ids_set(["A"], [])
        assert exact is False
        assert prec == 0.0
        assert rec == 0.0
        assert f1 == 0.0

    def test_duplicates_ignored(self) -> None:
        exact, prec, rec, f1 = validate_order_ids_set(["A", "A"], ["A"])
        assert exact is True
        assert prec == 1.0

    def test_partial_overlap(self) -> None:
        exact, prec, rec, f1 = validate_order_ids_set(["A", "B"], ["B", "C"])
        assert exact is False
        assert prec == 0.5
        assert rec == 0.5


# ---------------------------------------------------------------------------
# validate_order_ids_sequence edge cases
# ---------------------------------------------------------------------------


class TestValidateOrderIdsSequenceEdgeCases:
    """Edge cases for sequence-based order ID validation."""

    def test_same_set_different_order(self) -> None:
        exact, prec, rec, f1 = validate_order_ids_sequence(["A", "B"], ["B", "A"])
        assert exact is False  # order matters
        assert prec == 1.0 and rec == 1.0  # set-based scores

    def test_both_empty(self) -> None:
        exact, prec, rec, f1 = validate_order_ids_sequence([], [])
        assert exact is True
        assert prec == 1.0

    def test_single_match(self) -> None:
        exact, prec, rec, f1 = validate_order_ids_sequence(["A"], ["A"])
        assert exact is True
        assert f1 == 1.0

    def test_single_mismatch(self) -> None:
        exact, prec, rec, f1 = validate_order_ids_sequence(["A"], ["B"])
        assert exact is False
        assert prec == 0.0 and rec == 0.0

    def test_reversed_list(self) -> None:
        exact, _, _, _ = validate_order_ids_sequence(["C", "B", "A"], ["A", "B", "C"])
        assert exact is False


# ---------------------------------------------------------------------------
# validate_query_prediction edge cases
# ---------------------------------------------------------------------------


class TestValidateQueryPredictionEdgeCases:
    """Edge cases for query prediction validation."""

    def test_unknown_answer_type_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown answer_type"):
            validate_query_prediction({}, {}, "unknown_type")

    def test_explanation_always_perfect(self) -> None:
        result = validate_query_prediction(
            {"explanation": "test", "reasoning": "ok"},
            {},
            "explanation",
        )
        assert result.order_ids_correct is True
        assert result.precision == 1.0

    def test_non_string_predicted_ids_zero_scores(self) -> None:
        result = validate_query_prediction(
            {"order_ids": [1, 2, 3], "reasoning": "test"},
            {"order_ids": ["A", "B"]},
            "order_list",
        )
        assert result.order_ids_correct is False
        assert result.precision == 0.0

    def test_non_string_expected_raises(self) -> None:
        with pytest.raises(ValueError, match="must be a list of strings"):
            validate_query_prediction(
                {"order_ids": ["A"], "reasoning": "test"},
                {"order_ids": [1, 2]},
                "order_list",
            )

    def test_missing_order_ids_treated_as_empty(self) -> None:
        result = validate_query_prediction(
            {"reasoning": "test"},
            {"order_ids": ["A"]},
            "order_list",
        )
        # Missing order_ids defaults to [] which is a valid string list (empty)
        assert result.order_ids_correct is False

    def test_prioritized_list_uses_sequence(self) -> None:
        result = validate_query_prediction(
            {"order_ids": ["B", "A"], "reasoning": "test"},
            {"order_ids": ["A", "B"]},
            "prioritized_list",
        )
        assert result.order_ids_correct is False  # order matters

    def test_order_list_uses_set(self) -> None:
        result = validate_query_prediction(
            {"order_ids": ["B", "A"], "reasoning": "test"},
            {"order_ids": ["A", "B"]},
            "order_list",
        )
        assert result.order_ids_correct is True  # order doesn't matter

    def test_order_status_uses_set(self) -> None:
        result = validate_query_prediction(
            {"order_ids": ["B", "A"], "status_summary": "ok", "reasoning": "test"},
            {"order_ids": ["A", "B"]},
            "order_status",
        )
        assert result.order_ids_correct is True


# ---------------------------------------------------------------------------
# classify_query_failure priority chain
# ---------------------------------------------------------------------------


class TestClassifyQueryFailurePriorityChain:
    """Exhaustive test of failure classification priority."""

    def test_timeout_highest_priority(self) -> None:
        result = classify_query_failure(None, {}, "order_list", timed_out=True)
        assert result == QueryFailureType.TIMEOUT

    def test_invalid_json(self) -> None:
        result = classify_query_failure(None, {}, "order_list")
        assert result == QueryFailureType.INVALID_JSON

    def test_empty_response(self) -> None:
        result = classify_query_failure({}, {"order_ids": ["A"]}, "order_list")
        assert result == QueryFailureType.EMPTY_RESPONSE

    def test_wrong_field_names(self) -> None:
        result = classify_query_failure(
            {"wrong_key": "val"},
            {"order_ids": ["A"]},
            "order_list",
        )
        assert result == QueryFailureType.WRONG_FIELD_NAMES

    def test_wrong_field_type_reasoning(self) -> None:
        result = classify_query_failure(
            {"order_ids": ["A"], "reasoning": 42},
            {"order_ids": ["A"]},
            "order_list",
        )
        assert result == QueryFailureType.WRONG_FIELD_TYPE

    def test_wrong_field_type_order_ids(self) -> None:
        result = classify_query_failure(
            {"order_ids": "not-a-list", "reasoning": "test"},
            {"order_ids": ["A"]},
            "order_list",
        )
        assert result == QueryFailureType.WRONG_FIELD_TYPE

    def test_wrong_order_ids_both_missing_and_extra(self) -> None:
        result = classify_query_failure(
            {"order_ids": ["X"], "reasoning": "test"},
            {"order_ids": ["A"]},
            "order_list",
        )
        assert result == QueryFailureType.WRONG_ORDER_IDS

    def test_missing_orders(self) -> None:
        result = classify_query_failure(
            {"order_ids": [], "reasoning": "test"},
            {"order_ids": ["A"]},
            "order_list",
        )
        assert result == QueryFailureType.MISSING_ORDERS

    def test_extra_orders(self) -> None:
        result = classify_query_failure(
            {"order_ids": ["A", "B"], "reasoning": "test"},
            {"order_ids": ["A"]},
            "order_list",
        )
        assert result == QueryFailureType.EXTRA_ORDERS

    def test_wrong_order_sequence(self) -> None:
        result = classify_query_failure(
            {"order_ids": ["B", "A"], "reasoning": "test"},
            {"order_ids": ["A", "B"]},
            "prioritized_list",
        )
        assert result == QueryFailureType.WRONG_ORDER_SEQUENCE

    def test_correct_returns_none(self) -> None:
        result = classify_query_failure(
            {"order_ids": ["A", "B"], "reasoning": "test"},
            {"order_ids": ["A", "B"]},
            "order_list",
        )
        assert result is None

    def test_explanation_correct_returns_none(self) -> None:
        result = classify_query_failure(
            {"explanation": "Analysis shows...", "reasoning": "test"},
            {},
            "explanation",
        )
        assert result is None

    def test_unknown_answer_type_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown answer_type"):
            classify_query_failure(
                {"order_ids": ["A"], "reasoning": "test"},
                {"order_ids": ["A"]},
                "bad_type",
            )
