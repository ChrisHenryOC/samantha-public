"""Red-team tests for src/evaluation/query_metrics.py — edge cases and boundary conditions."""

from __future__ import annotations

from typing import Any

import pytest

from src.evaluation.query_metrics import (
    QueryModelMetrics,
    compute_mean_f1,
    compute_mean_precision,
    compute_mean_recall,
    compute_query_accuracy,
    compute_query_accuracy_by_answer_type,
    compute_query_accuracy_by_tier,
    compute_query_latency_stats,
    compute_query_scenario_reliability,
    compute_query_variance,
)

from .conftest import _make_query_result

# ---------------------------------------------------------------------------
# compute_query_accuracy edge cases
# ---------------------------------------------------------------------------


class TestComputeQueryAccuracyEdgeCases:
    """Edge cases for query accuracy computation."""

    def test_empty_list(self) -> None:
        assert compute_query_accuracy([]) == 0.0

    def test_all_correct(self) -> None:
        results = [_make_query_result() for _ in range(5)]
        assert compute_query_accuracy(results) == 100.0

    def test_none_correct(self) -> None:
        results = [
            _make_query_result(order_ids_correct=False, precision=0.0, recall=0.0, f1=0.0)
            for _ in range(3)
        ]
        assert compute_query_accuracy(results) == 0.0

    def test_mixed(self) -> None:
        results = [
            _make_query_result(),
            _make_query_result(order_ids_correct=False, precision=0.5, recall=0.5, f1=0.5),
        ]
        assert compute_query_accuracy(results) == 50.0


# ---------------------------------------------------------------------------
# compute_query_accuracy_by_tier edge cases
# ---------------------------------------------------------------------------


class TestComputeQueryAccuracyByTierEdgeCases:
    """Edge cases for tier-grouped accuracy."""

    def test_empty_list(self) -> None:
        assert compute_query_accuracy_by_tier([]) == {}

    def test_single_tier(self) -> None:
        results = [_make_query_result(tier=1), _make_query_result(tier=1)]
        by_tier = compute_query_accuracy_by_tier(results)
        assert 1 in by_tier
        assert by_tier[1] == 100.0

    def test_multiple_tiers(self) -> None:
        results = [
            _make_query_result(tier=1),
            _make_query_result(tier=2),
            _make_query_result(tier=3),
        ]
        by_tier = compute_query_accuracy_by_tier(results)
        assert len(by_tier) == 3

    def test_mixed_correctness(self) -> None:
        results = [
            _make_query_result(tier=1),
            _make_query_result(tier=1, order_ids_correct=False, precision=0.0, recall=0.0, f1=0.0),
        ]
        by_tier = compute_query_accuracy_by_tier(results)
        assert by_tier[1] == 50.0


# ---------------------------------------------------------------------------
# compute_query_accuracy_by_answer_type edge cases
# ---------------------------------------------------------------------------


class TestComputeQueryAccuracyByAnswerTypeEdgeCases:
    """Edge cases for answer-type-grouped accuracy."""

    def test_empty_list(self) -> None:
        assert compute_query_accuracy_by_answer_type([]) == {}

    def test_single_type(self) -> None:
        results = [_make_query_result(answer_type="order_list")]
        by_type = compute_query_accuracy_by_answer_type(results)
        assert "order_list" in by_type

    def test_multiple_types(self) -> None:
        results = [
            _make_query_result(answer_type="order_list"),
            _make_query_result(answer_type="explanation"),
            _make_query_result(answer_type="order_status"),
        ]
        by_type = compute_query_accuracy_by_answer_type(results)
        assert len(by_type) == 3


# ---------------------------------------------------------------------------
# _filter_non_explanation
# ---------------------------------------------------------------------------


class TestFilterNonExplanation:
    """Test explanation filtering via the precision/recall/f1 functions."""

    def test_all_explanation_returns_zero(self) -> None:
        results = [_make_query_result(answer_type="explanation") for _ in range(3)]
        assert compute_mean_precision(results) == 0.0

    def test_no_explanation_uses_all(self) -> None:
        results = [_make_query_result(answer_type="order_list", precision=0.8)]
        assert compute_mean_precision(results) == 0.8

    def test_mixed_filters_explanation(self) -> None:
        results = [
            _make_query_result(answer_type="order_list", precision=0.6, recall=0.6, f1=0.6),
            _make_query_result(answer_type="explanation", precision=1.0, recall=1.0, f1=1.0),
        ]
        # Only the non-explanation result should count
        assert compute_mean_precision(results) == 0.6


# ---------------------------------------------------------------------------
# compute_mean_precision/recall/f1
# ---------------------------------------------------------------------------


class TestComputeMeanPrecisionRecallF1:
    """Edge cases for precision/recall/F1 mean computation."""

    def test_empty_returns_zero_precision(self) -> None:
        assert compute_mean_precision([]) == 0.0

    def test_empty_returns_zero_recall(self) -> None:
        assert compute_mean_recall([]) == 0.0

    def test_empty_returns_zero_f1(self) -> None:
        assert compute_mean_f1([]) == 0.0

    def test_all_perfect(self) -> None:
        results = [_make_query_result(precision=1.0, recall=1.0, f1=1.0) for _ in range(3)]
        assert compute_mean_precision(results) == 1.0
        assert compute_mean_recall(results) == 1.0
        assert compute_mean_f1(results) == 1.0

    def test_explanation_filtered_for_precision(self) -> None:
        results = [_make_query_result(answer_type="explanation")]
        assert compute_mean_precision(results) == 0.0

    def test_explanation_filtered_for_f1(self) -> None:
        results = [_make_query_result(answer_type="explanation")]
        assert compute_mean_f1(results) == 0.0


# ---------------------------------------------------------------------------
# compute_query_scenario_reliability
# ---------------------------------------------------------------------------


class TestComputeQueryScenarioReliability:
    """Edge cases for query scenario reliability."""

    def test_empty_list(self) -> None:
        assert compute_query_scenario_reliability([]) == 0.0

    def test_all_reliable(self) -> None:
        results = [
            _make_query_result(scenario_id="Q-001"),
            _make_query_result(scenario_id="Q-002"),
        ]
        assert compute_query_scenario_reliability(results) == 100.0

    def test_none_reliable(self) -> None:
        results = [
            _make_query_result(
                scenario_id="Q-001", order_ids_correct=False, precision=0.0, recall=0.0, f1=0.0
            ),
        ]
        assert compute_query_scenario_reliability(results) == 0.0

    def test_mixed_runs_per_scenario(self) -> None:
        results = [
            _make_query_result(scenario_id="Q-001", run_number=1),
            _make_query_result(
                scenario_id="Q-001",
                run_number=2,
                order_ids_correct=False,
                precision=0.0,
                recall=0.0,
                f1=0.0,
            ),
            _make_query_result(scenario_id="Q-002", run_number=1),
            _make_query_result(scenario_id="Q-002", run_number=2),
        ]
        # Q-001 has one failure, Q-002 is all correct
        reliability = compute_query_scenario_reliability(results)
        assert reliability == 50.0


# ---------------------------------------------------------------------------
# compute_query_variance
# ---------------------------------------------------------------------------


class TestComputeQueryVariance:
    """Edge cases for query variance computation."""

    def test_single_run_returns_none(self) -> None:
        results = [_make_query_result(run_number=1)]
        v = compute_query_variance(results)
        assert v["accuracy_std"] is None

    def test_two_identical_runs_zero_std(self) -> None:
        results = [
            _make_query_result(run_number=1),
            _make_query_result(run_number=2),
        ]
        v = compute_query_variance(results)
        assert v["accuracy_std"] == 0.0

    def test_two_different_runs(self) -> None:
        results = [
            _make_query_result(run_number=1),
            _make_query_result(
                run_number=2, order_ids_correct=False, precision=0.0, recall=0.0, f1=0.0
            ),
        ]
        v = compute_query_variance(results)
        assert v["accuracy_std"] is not None
        assert v["accuracy_std"] > 0


# ---------------------------------------------------------------------------
# compute_query_latency_stats
# ---------------------------------------------------------------------------


class TestComputeQueryLatencyStats:
    """Edge cases for query latency statistics."""

    def test_empty_list(self) -> None:
        stats = compute_query_latency_stats([])
        assert stats["mean"] == 0.0
        assert stats["p50"] == 0.0
        assert stats["p95"] == 0.0

    def test_single_result(self) -> None:
        results = [_make_query_result(latency_ms=300)]
        stats = compute_query_latency_stats(results)
        assert stats["mean"] == 300.0
        assert stats["p50"] == 300.0
        assert stats["p95"] == 300.0

    def test_two_results(self) -> None:
        results = [
            _make_query_result(latency_ms=100),
            _make_query_result(latency_ms=200),
        ]
        stats = compute_query_latency_stats(results)
        assert stats["mean"] == 150.0

    def test_percentile_interpolation(self) -> None:
        results = [_make_query_result(latency_ms=i * 10) for i in range(1, 21)]
        stats = compute_query_latency_stats(results)
        assert stats["p50"] > 0
        assert stats["p95"] > stats["p50"]


# ---------------------------------------------------------------------------
# QueryModelMetrics __post_init__ validation
# ---------------------------------------------------------------------------


class TestQueryModelMetricsPostInitValidation:
    """Validate QueryModelMetrics rejects invalid inputs."""

    def _make_valid_kwargs(self) -> dict[str, Any]:
        return {
            "model_id": "test",
            "query_accuracy": 85.0,
            "query_accuracy_by_tier": {1: 90.0, 2: 80.0},
            "query_accuracy_by_answer_type": {"order_list": 85.0},
            "mean_precision": 0.9,
            "mean_recall": 0.85,
            "mean_f1": 0.87,
            "scenario_reliability": 70.0,
            "accuracy_std": 2.0,
            "latency_mean_ms": 250.0,
            "latency_p50_ms": 200.0,
            "latency_p95_ms": 500.0,
            "token_input_mean": 600.0,
            "token_output_mean": 80.0,
            "total_cost_usd": None,
            "failure_counts": {"wrong_order_ids": 3},
        }

    def test_empty_model_id_rejected(self) -> None:
        kwargs = self._make_valid_kwargs()
        kwargs["model_id"] = ""
        with pytest.raises(ValueError, match="model_id must be a non-empty string"):
            QueryModelMetrics(**kwargs)

    def test_list_failure_counts_rejected(self) -> None:
        kwargs = self._make_valid_kwargs()
        kwargs["failure_counts"] = [("a", 1)]
        with pytest.raises(TypeError, match="failure_counts must be a dict"):
            QueryModelMetrics(**kwargs)

    def test_string_tier_key_rejected(self) -> None:
        kwargs = self._make_valid_kwargs()
        kwargs["query_accuracy_by_tier"] = {"1": 90.0}
        with pytest.raises(TypeError, match="tier key must be int"):
            QueryModelMetrics(**kwargs)

    def test_out_of_range_tier_accuracy_rejected(self) -> None:
        kwargs = self._make_valid_kwargs()
        kwargs["query_accuracy_by_tier"] = {1: 101.0}
        with pytest.raises(ValueError, match="tier accuracy must be 0-100"):
            QueryModelMetrics(**kwargs)

    def test_int_answer_type_key_rejected(self) -> None:
        kwargs = self._make_valid_kwargs()
        kwargs["query_accuracy_by_answer_type"] = {1: 80.0}
        with pytest.raises(TypeError, match="answer_type key must be str"):
            QueryModelMetrics(**kwargs)

    def test_negative_answer_type_accuracy_rejected(self) -> None:
        kwargs = self._make_valid_kwargs()
        kwargs["query_accuracy_by_answer_type"] = {"order_list": -1.0}
        with pytest.raises(ValueError, match="answer_type accuracy must be 0-100"):
            QueryModelMetrics(**kwargs)

    def test_precision_above_one_rejected(self) -> None:
        kwargs = self._make_valid_kwargs()
        kwargs["mean_precision"] = 1.1
        with pytest.raises(ValueError, match="mean_precision must be <= 1.0"):
            QueryModelMetrics(**kwargs)

    def test_accuracy_above_100_rejected(self) -> None:
        kwargs = self._make_valid_kwargs()
        kwargs["query_accuracy"] = 101.0
        with pytest.raises(ValueError, match="query_accuracy must be <= 100"):
            QueryModelMetrics(**kwargs)

    def test_negative_latency_rejected(self) -> None:
        kwargs = self._make_valid_kwargs()
        kwargs["latency_mean_ms"] = -1.0
        with pytest.raises(ValueError, match="latency_mean_ms must be non-negative"):
            QueryModelMetrics(**kwargs)
