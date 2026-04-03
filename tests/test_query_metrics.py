"""Tests for query metric computation.

Pure data tests — no mocks, no I/O. Uses minimal QueryDecision-like objects
that satisfy the QueryResult contract.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.evaluation.query_metrics import (
    QueryModelMetrics,
    QueryResult,
    compute_mean_f1,
    compute_mean_precision,
    compute_mean_recall,
    compute_query_accuracy,
    compute_query_accuracy_by_answer_type,
    compute_query_accuracy_by_tier,
    compute_query_failure_breakdown,
    compute_query_latency_stats,
    compute_query_model_metrics,
    compute_query_scenario_reliability,
    compute_query_variance,
)
from src.workflow.query_validator import QueryFailureType, QueryValidationResult


@dataclass
class FakeQueryDecision:
    """Minimal QueryDecision-like object for metric tests."""

    predicted_order_ids: list[str]
    expected_order_ids: list[str]
    latency_ms: int = 100
    input_tokens: int = 50
    output_tokens: int = 20


def _query_result(
    *,
    scenario_id: str = "QS-001",
    tier: int = 1,
    answer_type: str = "order_list",
    model_id: str = "test-model",
    run_number: int = 1,
    order_ids_correct: bool = True,
    precision: float = 1.0,
    recall: float = 1.0,
    f1: float = 1.0,
    failure: QueryFailureType | None = None,
    latency_ms: int = 100,
    input_tokens: int = 50,
    output_tokens: int = 20,
) -> QueryResult:
    """Create a QueryResult with given parameters."""
    return QueryResult(
        scenario_id=scenario_id,
        tier=tier,
        answer_type=answer_type,
        model_id=model_id,
        run_number=run_number,
        decision=FakeQueryDecision(
            predicted_order_ids=["A"] if order_ids_correct else ["X"],
            expected_order_ids=["A"],
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        ),
        validation=QueryValidationResult(
            order_ids_correct=order_ids_correct,
            precision=precision,
            recall=recall,
            f1=f1,
        ),
        failure_type=failure,
    )


# --- compute_query_accuracy ---


class TestComputeQueryAccuracy:
    def test_all_correct(self) -> None:
        results = [_query_result(order_ids_correct=True)] * 2
        assert compute_query_accuracy(results) == 100.0

    def test_mixed(self) -> None:
        results = [
            _query_result(order_ids_correct=True),
            _query_result(order_ids_correct=False),
        ]
        assert compute_query_accuracy(results) == 50.0

    def test_none_correct(self) -> None:
        results = [_query_result(order_ids_correct=False)] * 2
        assert compute_query_accuracy(results) == 0.0

    def test_empty(self) -> None:
        assert compute_query_accuracy([]) == 0.0


# --- QueryResult.all_correct ---


class TestQueryResultAllCorrect:
    def test_correct_with_no_failure(self) -> None:
        r = _query_result(order_ids_correct=True, failure=None)
        assert r.all_correct is True

    def test_correct_ids_but_timeout_is_not_correct(self) -> None:
        r = _query_result(order_ids_correct=True, failure=QueryFailureType.TIMEOUT)
        assert r.all_correct is False

    def test_wrong_ids_no_failure(self) -> None:
        r = _query_result(order_ids_correct=False, failure=None)
        assert r.all_correct is False


# --- compute_query_accuracy_by_tier ---


class TestComputeQueryAccuracyByTier:
    def test_single_tier(self) -> None:
        results = [_query_result(tier=1, order_ids_correct=True)]
        by_tier = compute_query_accuracy_by_tier(results)
        assert by_tier == {1: 100.0}

    def test_multiple_tiers(self) -> None:
        results = [
            _query_result(tier=1, order_ids_correct=True),
            _query_result(tier=2, order_ids_correct=False),
        ]
        by_tier = compute_query_accuracy_by_tier(results)
        assert by_tier[1] == 100.0
        assert by_tier[2] == 0.0


# --- compute_query_accuracy_by_answer_type ---


class TestComputeQueryAccuracyByAnswerType:
    def test_single_type(self) -> None:
        results = [_query_result(answer_type="order_list", order_ids_correct=True)]
        by_type = compute_query_accuracy_by_answer_type(results)
        assert by_type == {"order_list": 100.0}

    def test_multiple_types(self) -> None:
        results = [
            _query_result(answer_type="order_list", order_ids_correct=True),
            _query_result(answer_type="order_status", order_ids_correct=False),
        ]
        by_type = compute_query_accuracy_by_answer_type(results)
        assert by_type["order_list"] == 100.0
        assert by_type["order_status"] == 0.0


# --- compute_mean_precision/recall/f1 ---


class TestComputeMeanPrecisionRecallF1:
    def test_mean_precision(self) -> None:
        results = [
            _query_result(precision=1.0),
            _query_result(precision=0.5),
        ]
        assert compute_mean_precision(results) == 0.75

    def test_mean_recall(self) -> None:
        results = [
            _query_result(recall=1.0),
            _query_result(recall=0.0),
        ]
        assert compute_mean_recall(results) == 0.5

    def test_mean_f1(self) -> None:
        results = [
            _query_result(f1=0.8),
            _query_result(f1=0.6),
        ]
        assert compute_mean_f1(results) == pytest.approx(0.7)

    def test_excludes_explanation_type(self) -> None:
        results = [
            _query_result(answer_type="order_list", precision=0.5),
            _query_result(answer_type="explanation", precision=1.0),
        ]
        assert compute_mean_precision(results) == 0.5

    def test_empty(self) -> None:
        assert compute_mean_precision([]) == 0.0
        assert compute_mean_recall([]) == 0.0
        assert compute_mean_f1([]) == 0.0

    def test_only_explanation(self) -> None:
        results = [_query_result(answer_type="explanation")]
        assert compute_mean_precision(results) == 0.0


# --- compute_query_scenario_reliability ---


class TestComputeQueryScenarioReliability:
    def test_single_scenario_all_correct(self) -> None:
        results = [
            _query_result(scenario_id="QS-001", run_number=1, order_ids_correct=True),
            _query_result(scenario_id="QS-001", run_number=2, order_ids_correct=True),
        ]
        assert compute_query_scenario_reliability(results) == 100.0

    def test_single_scenario_one_failure(self) -> None:
        results = [
            _query_result(scenario_id="QS-001", run_number=1, order_ids_correct=True),
            _query_result(scenario_id="QS-001", run_number=2, order_ids_correct=False),
        ]
        assert compute_query_scenario_reliability(results) == 0.0

    def test_two_scenarios_one_reliable(self) -> None:
        results = [
            _query_result(scenario_id="QS-001", run_number=1, order_ids_correct=True),
            _query_result(scenario_id="QS-001", run_number=2, order_ids_correct=True),
            _query_result(scenario_id="QS-002", run_number=1, order_ids_correct=True),
            _query_result(scenario_id="QS-002", run_number=2, order_ids_correct=False),
        ]
        assert compute_query_scenario_reliability(results) == 50.0

    def test_empty(self) -> None:
        assert compute_query_scenario_reliability([]) == 0.0


# --- compute_query_variance ---


class TestComputeQueryVariance:
    def test_single_run_returns_none(self) -> None:
        results = [_query_result(model_id="m1", run_number=1)]
        v = compute_query_variance(results)
        assert v["accuracy_std"] is None

    def test_multiple_runs(self) -> None:
        results = [
            _query_result(model_id="m1", run_number=1, order_ids_correct=True),
            _query_result(model_id="m1", run_number=2, order_ids_correct=False),
        ]
        v = compute_query_variance(results)
        assert v["accuracy_std"] is not None
        assert v["accuracy_std"] > 0

    def test_identical_runs_zero_std(self) -> None:
        results = [
            _query_result(model_id="m1", run_number=1, order_ids_correct=True),
            _query_result(model_id="m1", run_number=2, order_ids_correct=True),
        ]
        v = compute_query_variance(results)
        assert v["accuracy_std"] == 0.0


# --- compute_query_latency_stats ---


class TestComputeQueryLatencyStats:
    def test_basic(self) -> None:
        results = [
            _query_result(latency_ms=100),
            _query_result(latency_ms=200),
            _query_result(latency_ms=300),
        ]
        stats = compute_query_latency_stats(results)
        assert stats["mean"] == 200.0
        assert stats["p50"] == 200.0
        assert stats["p95"] >= 280

    def test_empty(self) -> None:
        stats = compute_query_latency_stats([])
        assert stats["mean"] == 0.0

    def test_single_result(self) -> None:
        stats = compute_query_latency_stats([_query_result(latency_ms=150)])
        assert stats["mean"] == 150.0
        assert stats["p50"] == 150.0
        assert stats["p95"] == 150.0


# --- compute_query_failure_breakdown ---


class TestComputeQueryFailureBreakdown:
    def test_no_failures(self) -> None:
        results = [_query_result()]
        assert compute_query_failure_breakdown(results) == {}

    def test_with_failures(self) -> None:
        results = [
            _query_result(failure=QueryFailureType.WRONG_ORDER_IDS),
            _query_result(failure=QueryFailureType.WRONG_ORDER_IDS),
            _query_result(failure=QueryFailureType.TIMEOUT),
        ]
        breakdown = compute_query_failure_breakdown(results)
        assert breakdown["wrong_order_ids"] == 2
        assert breakdown["timeout"] == 1

    def test_mixed_success_and_failure(self) -> None:
        results = [
            _query_result(failure=None),
            _query_result(failure=QueryFailureType.MISSING_ORDERS),
        ]
        breakdown = compute_query_failure_breakdown(results)
        assert breakdown == {"missing_orders": 1}


# --- compute_query_model_metrics ---


class TestComputeQueryModelMetrics:
    def test_basic(self) -> None:
        results = [
            _query_result(model_id="m1", run_number=1, order_ids_correct=True),
        ]
        metrics = compute_query_model_metrics("m1", results)
        assert metrics.model_id == "m1"
        assert metrics.query_accuracy == 100.0
        assert metrics.scenario_reliability == 100.0
        assert metrics.mean_precision == 1.0
        assert metrics.mean_recall == 1.0
        assert metrics.mean_f1 == 1.0

    def test_empty_model_results_raises(self) -> None:
        with pytest.raises(ValueError, match="No results found"):
            compute_query_model_metrics("m1", [])

    def test_filters_by_model_id(self) -> None:
        results = [
            _query_result(model_id="m1", order_ids_correct=True),
            _query_result(model_id="m2", order_ids_correct=False),
        ]
        metrics = compute_query_model_metrics("m1", results)
        assert metrics.query_accuracy == 100.0

    def test_unknown_model_id_raises(self) -> None:
        results = [_query_result(model_id="m1")]
        with pytest.raises(ValueError, match="No results found"):
            compute_query_model_metrics("nonexistent", results)

    def test_variance_isolated_across_models(self) -> None:
        results = [
            _query_result(model_id="m1", run_number=1, order_ids_correct=True),
            _query_result(model_id="m1", run_number=2, order_ids_correct=True),
            _query_result(model_id="m2", run_number=1, order_ids_correct=True),
            _query_result(model_id="m2", run_number=2, order_ids_correct=False),
        ]
        m1_metrics = compute_query_model_metrics("m1", results)
        m2_metrics = compute_query_model_metrics("m2", results)
        assert m1_metrics.accuracy_std == 0.0
        assert m2_metrics.accuracy_std is not None
        assert m2_metrics.accuracy_std > 0


# --- QueryModelMetrics validation ---


class TestQueryModelMetricsValidation:
    def test_empty_model_id(self) -> None:
        with pytest.raises(ValueError, match="model_id"):
            QueryModelMetrics(
                model_id="",
                query_accuracy=0.0,
                query_accuracy_by_tier={},
                query_accuracy_by_answer_type={},
                mean_precision=0.0,
                mean_recall=0.0,
                mean_f1=0.0,
                scenario_reliability=0.0,
                accuracy_std=None,
                latency_mean_ms=0.0,
                latency_p50_ms=0.0,
                latency_p95_ms=0.0,
                token_input_mean=0.0,
                token_output_mean=0.0,
                total_cost_usd=None,
                failure_counts={},
            )

    def test_negative_accuracy(self) -> None:
        with pytest.raises(ValueError, match="query_accuracy"):
            QueryModelMetrics(
                model_id="m1",
                query_accuracy=-1.0,
                query_accuracy_by_tier={},
                query_accuracy_by_answer_type={},
                mean_precision=0.0,
                mean_recall=0.0,
                mean_f1=0.0,
                scenario_reliability=0.0,
                accuracy_std=None,
                latency_mean_ms=0.0,
                latency_p50_ms=0.0,
                latency_p95_ms=0.0,
                token_input_mean=0.0,
                token_output_mean=0.0,
                total_cost_usd=None,
                failure_counts={},
            )
