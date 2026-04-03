"""Tests for evaluation metric computation.

Pure data tests — no mocks, no I/O. Uses minimal Decision-like objects
that satisfy the StepResult contract.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.evaluation.metrics import (
    ScenarioResult,
    StepResult,
    compute_accuracy,
    compute_accuracy_by_category,
    compute_failure_breakdown,
    compute_false_positive_rate,
    compute_flag_accuracy,
    compute_latency_stats,
    compute_model_metrics,
    compute_rule_accuracy,
    compute_scenario_reliability,
    compute_variance_across_runs,
)
from src.workflow.validator import FailureType, ValidationResult


# Minimal stand-in for Decision — only the fields StepResult/metrics access.
@dataclass
class FakeDecision:
    """Minimal Decision-like object for metric tests."""

    predicted_flags: list[str]
    expected_flags: list[str]
    predicted_next_state: str = "ACCEPTED"
    expected_next_state: str = "ACCEPTED"
    latency_ms: int = 100
    input_tokens: int = 50
    output_tokens: int = 20


def _step(
    *,
    state_ok: bool = True,
    rules_ok: bool = True,
    flags_ok: bool = True,
    failure: FailureType | None = None,
    predicted_flags: list[str] | None = None,
    expected_flags: list[str] | None = None,
    latency_ms: int = 100,
    input_tokens: int = 50,
    output_tokens: int = 20,
) -> StepResult:
    """Create a StepResult with given parameters."""
    return StepResult(
        decision=FakeDecision(
            predicted_flags=predicted_flags or [],
            expected_flags=expected_flags or [],
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        ),
        validation=ValidationResult(
            state_correct=state_ok,
            rules_correct=rules_ok,
            flags_correct=flags_ok,
        ),
        failure_type=failure,
    )


def _scenario(
    scenario_id: str = "SC-001",
    category: str = "rule_coverage",
    model_id: str = "test-model",
    run_number: int = 1,
    steps: list[StepResult] | None = None,
) -> ScenarioResult:
    """Create a ScenarioResult with given parameters."""
    step_list = steps or [_step()]
    return ScenarioResult(
        scenario_id=scenario_id,
        category=category,
        model_id=model_id,
        run_number=run_number,
        step_results=tuple(step_list),
        all_correct=all(s.validation.all_correct for s in step_list),
    )


# --- compute_accuracy ---


class TestComputeAccuracy:
    def test_all_correct(self) -> None:
        steps = [_step(state_ok=True), _step(state_ok=True)]
        assert compute_accuracy(steps) == 100.0

    def test_mixed(self) -> None:
        steps = [_step(state_ok=True), _step(state_ok=False)]
        assert compute_accuracy(steps) == 50.0

    def test_none_correct(self) -> None:
        steps = [_step(state_ok=False), _step(state_ok=False)]
        assert compute_accuracy(steps) == 0.0

    def test_empty(self) -> None:
        assert compute_accuracy([]) == 0.0


# --- compute_rule_accuracy ---


class TestComputeRuleAccuracy:
    def test_all_correct(self) -> None:
        steps = [_step(rules_ok=True), _step(rules_ok=True)]
        assert compute_rule_accuracy(steps) == 100.0

    def test_mixed(self) -> None:
        steps = [_step(rules_ok=True), _step(rules_ok=False)]
        assert compute_rule_accuracy(steps) == 50.0

    def test_empty(self) -> None:
        assert compute_rule_accuracy([]) == 0.0


# --- compute_flag_accuracy ---


class TestComputeFlagAccuracy:
    def test_all_correct(self) -> None:
        steps = [_step(flags_ok=True), _step(flags_ok=True)]
        assert compute_flag_accuracy(steps) == 100.0

    def test_mixed(self) -> None:
        steps = [_step(flags_ok=True), _step(flags_ok=False)]
        assert compute_flag_accuracy(steps) == 50.0

    def test_empty(self) -> None:
        assert compute_flag_accuracy([]) == 0.0


# --- compute_false_positive_rate ---


class TestComputeFalsePositiveRate:
    def test_no_fps(self) -> None:
        steps = [
            _step(predicted_flags=["FISH_SUGGESTED"], expected_flags=["FISH_SUGGESTED"]),
        ]
        assert compute_false_positive_rate(steps) == 0.0

    def test_with_fps(self) -> None:
        steps = [
            _step(
                predicted_flags=["FISH_SUGGESTED", "FIXATION_WARNING"],
                expected_flags=["FISH_SUGGESTED"],
            ),
        ]
        assert compute_false_positive_rate(steps) == 100.0

    def test_empty(self) -> None:
        assert compute_false_positive_rate([]) == 0.0


# --- compute_scenario_reliability ---


class TestComputeScenarioReliability:
    def test_all_reliable(self) -> None:
        results = [_scenario(steps=[_step()]), _scenario(steps=[_step()])]
        assert compute_scenario_reliability(results) == 100.0

    def test_mixed(self) -> None:
        results = [
            _scenario(steps=[_step()]),
            _scenario(steps=[_step(state_ok=False)]),
        ]
        assert compute_scenario_reliability(results) == 50.0

    def test_empty(self) -> None:
        assert compute_scenario_reliability([]) == 0.0


# --- compute_accuracy_by_category ---


class TestComputeAccuracyByCategory:
    def test_single_category(self) -> None:
        results = [_scenario(category="rule_coverage", steps=[_step(state_ok=True)])]
        by_cat = compute_accuracy_by_category(results)
        assert by_cat == {"rule_coverage": 100.0}

    def test_multiple_categories(self) -> None:
        results = [
            _scenario(category="rule_coverage", steps=[_step(state_ok=True)]),
            _scenario(category="multi_rule", steps=[_step(state_ok=False)]),
        ]
        by_cat = compute_accuracy_by_category(results)
        assert by_cat["rule_coverage"] == 100.0
        assert by_cat["multi_rule"] == 0.0


# --- compute_variance_across_runs ---


class TestComputeVarianceAcrossRuns:
    def test_single_run_returns_none(self) -> None:
        results = [_scenario(model_id="m1", run_number=1)]
        v = compute_variance_across_runs(results, "m1")
        assert v["accuracy_std"] is None
        assert v["rule_accuracy_std"] is None
        assert v["flag_accuracy_std"] is None

    def test_multiple_runs(self) -> None:
        results = [
            _scenario(model_id="m1", run_number=1, steps=[_step(state_ok=True)]),
            _scenario(model_id="m1", run_number=2, steps=[_step(state_ok=False)]),
        ]
        v = compute_variance_across_runs(results, "m1")
        assert v["accuracy_std"] is not None
        assert v["accuracy_std"] > 0

    def test_identical_runs_zero_std(self) -> None:
        results = [
            _scenario(model_id="m1", run_number=1, steps=[_step(state_ok=True)]),
            _scenario(model_id="m1", run_number=2, steps=[_step(state_ok=True)]),
        ]
        v = compute_variance_across_runs(results, "m1")
        assert v["accuracy_std"] == 0.0


# --- compute_latency_stats ---


class TestComputeLatencyStats:
    def test_basic(self) -> None:
        steps = [_step(latency_ms=100), _step(latency_ms=200), _step(latency_ms=300)]
        stats = compute_latency_stats(steps)
        assert stats["mean"] == 200.0
        assert stats["p50"] == 200.0
        assert stats["p95"] >= 280  # 95th percentile of [100, 200, 300]

    def test_empty(self) -> None:
        stats = compute_latency_stats([])
        assert stats["mean"] == 0.0


# --- compute_failure_breakdown ---


class TestComputeFailureBreakdown:
    def test_no_failures(self) -> None:
        steps = [_step()]
        assert compute_failure_breakdown(steps) == {}

    def test_with_failures(self) -> None:
        steps = [
            _step(failure=FailureType.WRONG_STATE),
            _step(failure=FailureType.WRONG_STATE),
            _step(failure=FailureType.TIMEOUT),
        ]
        breakdown = compute_failure_breakdown(steps)
        assert breakdown["wrong_state"] == 2
        assert breakdown["timeout"] == 1

    def test_mixed_success_and_failure(self) -> None:
        steps = [
            _step(failure=None),
            _step(failure=FailureType.HALLUCINATED_STATE),
        ]
        breakdown = compute_failure_breakdown(steps)
        assert breakdown == {"hallucinated_state": 1}


# --- compute_model_metrics ---


class TestComputeModelMetrics:
    def test_basic(self) -> None:
        results = [
            _scenario(
                model_id="m1",
                run_number=1,
                steps=[_step(state_ok=True, rules_ok=True, flags_ok=True)],
            ),
        ]
        metrics = compute_model_metrics("m1", results)
        assert metrics.model_id == "m1"
        assert metrics.accuracy == 100.0
        assert metrics.rule_accuracy == 100.0
        assert metrics.flag_accuracy == 100.0
        assert metrics.scenario_reliability == 100.0

    def test_empty_model_results(self) -> None:
        metrics = compute_model_metrics("m1", [])
        assert metrics.accuracy == 0.0
        assert metrics.scenario_reliability == 0.0
