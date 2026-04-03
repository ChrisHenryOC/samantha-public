"""Red-team tests for src/evaluation/metrics.py — edge cases and boundary conditions."""

from __future__ import annotations

from typing import Any

import pytest

from src.evaluation.metrics import (
    ModelMetrics,
    ScenarioResult,
    compute_accuracy,
    compute_failure_breakdown,
    compute_false_positive_rate,
    compute_flag_accuracy,
    compute_latency_stats,
    compute_rule_accuracy,
    compute_scenario_reliability,
    compute_variance_across_runs,
)
from src.workflow.validator import FailureType

from .conftest import _make_scenario_result, _make_step_result

# ---------------------------------------------------------------------------
# compute_accuracy edge cases
# ---------------------------------------------------------------------------


class TestComputeAccuracyEdgeCases:
    """Edge cases for state accuracy computation."""

    def test_empty_list(self) -> None:
        assert compute_accuracy([]) == 0.0

    def test_all_correct(self) -> None:
        steps = [_make_step_result(state_correct=True) for _ in range(5)]
        assert compute_accuracy(steps) == 100.0

    def test_none_correct(self) -> None:
        steps = [_make_step_result(state_correct=False) for _ in range(5)]
        assert compute_accuracy(steps) == 0.0

    def test_single_correct(self) -> None:
        steps = [_make_step_result(state_correct=True)]
        assert compute_accuracy(steps) == 100.0

    def test_mixed(self) -> None:
        steps = [
            _make_step_result(state_correct=True),
            _make_step_result(state_correct=False),
        ]
        assert compute_accuracy(steps) == 50.0


# ---------------------------------------------------------------------------
# compute_rule_accuracy edge cases
# ---------------------------------------------------------------------------


class TestComputeRuleAccuracyEdgeCases:
    """Edge cases for rule accuracy computation."""

    def test_empty_list(self) -> None:
        assert compute_rule_accuracy([]) == 0.0

    def test_all_correct(self) -> None:
        steps = [_make_step_result(rules_correct=True) for _ in range(3)]
        assert compute_rule_accuracy(steps) == 100.0

    def test_none_correct(self) -> None:
        steps = [_make_step_result(rules_correct=False) for _ in range(3)]
        assert compute_rule_accuracy(steps) == 0.0


# ---------------------------------------------------------------------------
# compute_flag_accuracy edge cases
# ---------------------------------------------------------------------------


class TestComputeFlagAccuracyEdgeCases:
    """Edge cases for flag accuracy computation."""

    def test_empty_list(self) -> None:
        assert compute_flag_accuracy([]) == 0.0

    def test_all_correct(self) -> None:
        steps = [_make_step_result(flags_correct=True) for _ in range(3)]
        assert compute_flag_accuracy(steps) == 100.0

    def test_none_correct(self) -> None:
        steps = [_make_step_result(flags_correct=False) for _ in range(3)]
        assert compute_flag_accuracy(steps) == 0.0


# ---------------------------------------------------------------------------
# compute_false_positive_rate edge cases
# ---------------------------------------------------------------------------


class TestComputeFalsePositiveRateEdgeCases:
    """Edge cases for false-positive rate computation."""

    def test_empty_list(self) -> None:
        assert compute_false_positive_rate([]) == 0.0

    def test_no_false_positives(self) -> None:
        steps = [
            _make_step_result(predicted_flags=["A"], expected_flags=["A"]),
            _make_step_result(predicted_flags=[], expected_flags=[]),
        ]
        assert compute_false_positive_rate(steps) == 0.0

    def test_all_false_positives(self) -> None:
        steps = [
            _make_step_result(predicted_flags=["X"], expected_flags=[]),
            _make_step_result(predicted_flags=["Y"], expected_flags=[]),
        ]
        assert compute_false_positive_rate(steps) == 100.0

    def test_subset_no_fp(self) -> None:
        steps = [_make_step_result(predicted_flags=["A"], expected_flags=["A", "B"])]
        assert compute_false_positive_rate(steps) == 0.0

    def test_superset_has_fp(self) -> None:
        steps = [_make_step_result(predicted_flags=["A", "B"], expected_flags=["A"])]
        assert compute_false_positive_rate(steps) == 100.0


# ---------------------------------------------------------------------------
# compute_scenario_reliability edge cases
# ---------------------------------------------------------------------------


class TestComputeScenarioReliabilityEdgeCases:
    """Edge cases for scenario reliability computation."""

    def test_empty_list(self) -> None:
        assert compute_scenario_reliability([]) == 0.0

    def test_all_reliable(self) -> None:
        results = [_make_scenario_result(all_correct=True) for _ in range(3)]
        assert compute_scenario_reliability(results) == 100.0

    def test_none_reliable(self) -> None:
        bad_step = _make_step_result(state_correct=False)
        results = [
            _make_scenario_result(step_results=(bad_step,), all_correct=False) for _ in range(3)
        ]
        assert compute_scenario_reliability(results) == 0.0

    def test_mixed(self) -> None:
        good = _make_scenario_result(all_correct=True)
        bad_step = _make_step_result(state_correct=False)
        bad = _make_scenario_result(step_results=(bad_step,), all_correct=False)
        assert compute_scenario_reliability([good, bad]) == 50.0


# ---------------------------------------------------------------------------
# compute_variance_across_runs edge cases
# ---------------------------------------------------------------------------


class TestComputeVarianceEdgeCases:
    """Edge cases for variance computation."""

    def test_single_run_returns_none(self) -> None:
        results = [_make_scenario_result(model_id="m", run_number=1)]
        v = compute_variance_across_runs(results, "m")
        assert v["accuracy_std"] is None
        assert v["rule_accuracy_std"] is None
        assert v["flag_accuracy_std"] is None

    def test_two_identical_runs_zero_std(self) -> None:
        results = [
            _make_scenario_result(model_id="m", run_number=1),
            _make_scenario_result(model_id="m", run_number=2),
        ]
        v = compute_variance_across_runs(results, "m")
        assert v["accuracy_std"] == 0.0

    def test_two_different_runs(self) -> None:
        good = _make_step_result(state_correct=True)
        bad = _make_step_result(state_correct=False)
        results = [
            _make_scenario_result(
                model_id="m", run_number=1, step_results=(good,), all_correct=True
            ),
            _make_scenario_result(
                model_id="m", run_number=2, step_results=(bad,), all_correct=False
            ),
        ]
        v = compute_variance_across_runs(results, "m")
        assert v["accuracy_std"] is not None
        assert v["accuracy_std"] > 0

    def test_no_matching_model(self) -> None:
        results = [_make_scenario_result(model_id="other")]
        v = compute_variance_across_runs(results, "m")
        assert v["accuracy_std"] is None

    def test_empty_results(self) -> None:
        v = compute_variance_across_runs([], "m")
        assert v["accuracy_std"] is None


# ---------------------------------------------------------------------------
# compute_latency_stats edge cases
# ---------------------------------------------------------------------------


class TestComputeLatencyStatsEdgeCases:
    """Edge cases for latency statistics computation."""

    def test_empty_list(self) -> None:
        stats = compute_latency_stats([])
        assert stats["mean"] == 0.0
        assert stats["p50"] == 0.0
        assert stats["p95"] == 0.0

    def test_single_step(self) -> None:
        steps = [_make_step_result(latency_ms=200)]
        stats = compute_latency_stats(steps)
        assert stats["mean"] == 200.0
        assert stats["p50"] == 200.0
        assert stats["p95"] == 200.0

    def test_two_steps(self) -> None:
        steps = [
            _make_step_result(latency_ms=100),
            _make_step_result(latency_ms=200),
        ]
        stats = compute_latency_stats(steps)
        assert stats["mean"] == 150.0

    def test_large_spread_p95(self) -> None:
        steps = [_make_step_result(latency_ms=i * 100) for i in range(1, 101)]
        stats = compute_latency_stats(steps)
        assert stats["p95"] > stats["p50"]
        assert stats["p95"] > stats["mean"]


# ---------------------------------------------------------------------------
# compute_failure_breakdown edge cases
# ---------------------------------------------------------------------------


class TestComputeFailureBreakdownEdgeCases:
    """Edge cases for failure breakdown computation."""

    def test_empty_list(self) -> None:
        assert compute_failure_breakdown([]) == {}

    def test_no_failures(self) -> None:
        steps = [_make_step_result(failure_type=None)]
        assert compute_failure_breakdown(steps) == {}

    def test_multiple_types(self) -> None:
        steps = [
            _make_step_result(state_correct=False, failure_type=FailureType.WRONG_STATE),
            _make_step_result(state_correct=False, failure_type=FailureType.WRONG_STATE),
            _make_step_result(state_correct=False, failure_type=FailureType.INVALID_JSON),
        ]
        result = compute_failure_breakdown(steps)
        assert result["wrong_state"] == 2
        assert result["invalid_json"] == 1


# ---------------------------------------------------------------------------
# ScenarioResult all_correct invariant
# ---------------------------------------------------------------------------


class TestScenarioResultAllCorrectInvariant:
    """Verify the all_correct invariant enforcement in ScenarioResult."""

    def test_all_correct_true_with_bad_step_raises(self) -> None:
        bad_step = _make_step_result(state_correct=False)
        with pytest.raises(ValueError, match="inconsistent with step results"):
            ScenarioResult(
                scenario_id="S-001",
                category="test",
                model_id="m",
                run_number=1,
                step_results=(bad_step,),
                all_correct=True,
            )

    def test_all_correct_false_with_good_steps_raises(self) -> None:
        good_step = _make_step_result()
        with pytest.raises(ValueError, match="inconsistent with step results"):
            ScenarioResult(
                scenario_id="S-001",
                category="test",
                model_id="m",
                run_number=1,
                step_results=(good_step,),
                all_correct=False,
            )

    def test_valid_all_correct_true(self) -> None:
        good_step = _make_step_result()
        sr = ScenarioResult(
            scenario_id="S-001",
            category="test",
            model_id="m",
            run_number=1,
            step_results=(good_step,),
            all_correct=True,
        )
        assert sr.all_correct is True

    def test_valid_all_correct_false(self) -> None:
        bad_step = _make_step_result(state_correct=False)
        sr = ScenarioResult(
            scenario_id="S-001",
            category="test",
            model_id="m",
            run_number=1,
            step_results=(bad_step,),
            all_correct=False,
        )
        assert sr.all_correct is False


# ---------------------------------------------------------------------------
# ModelMetrics __post_init__ validation
# ---------------------------------------------------------------------------


class TestModelMetricsPostInitValidation:
    """Validate ModelMetrics rejects invalid inputs."""

    def _make_valid_kwargs(self) -> dict[str, Any]:
        return {
            "model_id": "test",
            "accuracy": 90.0,
            "accuracy_by_category": {"cat": 90.0},
            "rule_accuracy": 85.0,
            "flag_accuracy": 95.0,
            "false_positive_rate": 5.0,
            "scenario_reliability": 80.0,
            "accuracy_std": 1.5,
            "rule_accuracy_std": 1.0,
            "flag_accuracy_std": 0.5,
            "latency_mean_ms": 200.0,
            "latency_p50_ms": 180.0,
            "latency_p95_ms": 400.0,
            "token_input_mean": 500.0,
            "token_output_mean": 50.0,
            "total_cost_usd": None,
            "failure_counts": {"wrong_state": 3},
        }

    def test_empty_model_id_rejected(self) -> None:
        kwargs = self._make_valid_kwargs()
        kwargs["model_id"] = ""
        with pytest.raises(ValueError, match="model_id must be a non-empty string"):
            ModelMetrics(**kwargs)

    def test_negative_accuracy_rejected(self) -> None:
        kwargs = self._make_valid_kwargs()
        kwargs["accuracy"] = -1.0
        with pytest.raises(ValueError, match="accuracy must be non-negative"):
            ModelMetrics(**kwargs)

    def test_failure_counts_not_dict_rejected(self) -> None:
        kwargs = self._make_valid_kwargs()
        kwargs["failure_counts"] = [("a", 1)]
        with pytest.raises(TypeError, match="failure_counts must be a dict"):
            ModelMetrics(**kwargs)

    def test_accuracy_by_category_not_dict_rejected(self) -> None:
        kwargs = self._make_valid_kwargs()
        kwargs["accuracy_by_category"] = "not a dict"
        with pytest.raises(TypeError, match="accuracy_by_category must be a dict"):
            ModelMetrics(**kwargs)

    def test_string_latency_rejected(self) -> None:
        kwargs = self._make_valid_kwargs()
        kwargs["latency_mean_ms"] = "fast"
        with pytest.raises(TypeError, match="latency_mean_ms must be numeric"):
            ModelMetrics(**kwargs)


# ---------------------------------------------------------------------------
# Token stats via compute_latency_stats (#15)
# ---------------------------------------------------------------------------


class TestComputeLatencyStatsTokenFields:
    """Verify token fields on FakeDecision are exercised."""

    def test_custom_token_values(self) -> None:
        sr1 = _make_step_result(
            latency_ms=100,
            input_tokens=1000,
            output_tokens=200,
        )
        sr2 = _make_step_result(
            latency_ms=200,
            input_tokens=2000,
            output_tokens=400,
        )
        stats = compute_latency_stats([sr1, sr2])
        assert stats["mean"] == 150.0
        # Verify the token fields are accessible (used by compute_model_metrics)
        assert sr1.decision.input_tokens == 1000
        assert sr2.decision.output_tokens == 400


# ---------------------------------------------------------------------------
# compute_scenario_reliability multi-run behavior (#16)
# ---------------------------------------------------------------------------


class TestComputeScenarioReliabilityMultiRun:
    """Verify multi-run deduplication behavior."""

    def test_duplicate_scenario_across_runs_counted_separately(self) -> None:
        """Same scenario_id in different runs counts as separate items."""
        sr1 = _make_scenario_result(
            scenario_id="S-001",
            run_number=1,
            all_correct=True,
        )
        bad_step = _make_step_result(state_correct=False)
        sr2 = _make_scenario_result(
            scenario_id="S-001",
            run_number=2,
            step_results=(bad_step,),
            all_correct=False,
        )
        reliability = compute_scenario_reliability([sr1, sr2])
        # 1 of 2 results is all_correct → 50%
        assert reliability == 50.0

    def test_all_runs_correct(self) -> None:
        sr1 = _make_scenario_result(
            scenario_id="S-001",
            run_number=1,
            all_correct=True,
        )
        sr2 = _make_scenario_result(
            scenario_id="S-001",
            run_number=2,
            all_correct=True,
        )
        reliability = compute_scenario_reliability([sr1, sr2])
        assert reliability == 100.0
