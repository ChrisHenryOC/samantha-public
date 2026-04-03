"""Metric computation for evaluation results.

Pure functions that compute accuracy, reliability, variance, latency, and
failure breakdown from scenario/step results. No database or I/O dependencies.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Protocol

from src.workflow.validator import FailureType, ValidationResult


class DecisionLike(Protocol):
    """Protocol for Decision-like objects used by metrics and reporting."""

    predicted_next_state: str
    expected_next_state: str
    predicted_flags: list[str]
    expected_flags: list[str]
    latency_ms: int
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class StepResult:
    """Result of a single scenario step evaluation."""

    decision: DecisionLike
    validation: ValidationResult
    failure_type: FailureType | None


@dataclass(frozen=True)
class ScenarioResult:
    """Result of a complete scenario evaluation for one model run."""

    scenario_id: str
    category: str
    model_id: str
    run_number: int
    step_results: tuple[StepResult, ...]
    all_correct: bool

    def __post_init__(self) -> None:
        expected = all(sr.validation.all_correct for sr in self.step_results)
        if self.all_correct != expected:
            raise ValueError(
                f"all_correct={self.all_correct} inconsistent with step results "
                f"(expected {expected})"
            )


@dataclass(frozen=True)
class ModelMetrics:
    """Aggregated metrics for a single model across all runs."""

    model_id: str
    # Primary
    accuracy: float
    accuracy_by_category: dict[str, float]
    rule_accuracy: float
    flag_accuracy: float
    false_positive_rate: float
    scenario_reliability: float
    # Variance (None if < 2 runs)
    accuracy_std: float | None
    rule_accuracy_std: float | None
    flag_accuracy_std: float | None
    # Secondary
    latency_mean_ms: float
    latency_p50_ms: float
    latency_p95_ms: float
    token_input_mean: float
    token_output_mean: float
    total_cost_usd: float | None
    # Failure breakdown
    failure_counts: dict[str, int]

    def __post_init__(self) -> None:
        if not isinstance(self.model_id, str) or not self.model_id:
            raise ValueError("model_id must be a non-empty string")
        if not isinstance(self.failure_counts, dict):
            raise TypeError("failure_counts must be a dict")
        if not isinstance(self.accuracy_by_category, dict):
            raise TypeError("accuracy_by_category must be a dict")
        for field_name in (
            "accuracy",
            "rule_accuracy",
            "flag_accuracy",
            "false_positive_rate",
            "scenario_reliability",
            "latency_mean_ms",
            "latency_p50_ms",
            "latency_p95_ms",
            "token_input_mean",
            "token_output_mean",
        ):
            val = getattr(self, field_name)
            if not isinstance(val, (int, float)):
                raise TypeError(f"{field_name} must be numeric, got {type(val).__name__}")
            if val < 0:
                raise ValueError(f"{field_name} must be non-negative, got {val}")


def compute_accuracy(step_results: list[StepResult]) -> float:
    """Compute state accuracy as percentage of correct state predictions."""
    if not step_results:
        return 0.0
    correct = sum(1 for sr in step_results if sr.validation.state_correct)
    return correct / len(step_results) * 100


def compute_rule_accuracy(step_results: list[StepResult]) -> float:
    """Compute rule accuracy as percentage of correct rule predictions."""
    if not step_results:
        return 0.0
    correct = sum(1 for sr in step_results if sr.validation.rules_correct)
    return correct / len(step_results) * 100


def compute_flag_accuracy(step_results: list[StepResult]) -> float:
    """Compute flag accuracy as percentage of correct flag predictions."""
    if not step_results:
        return 0.0
    correct = sum(1 for sr in step_results if sr.validation.flags_correct)
    return correct / len(step_results) * 100


def compute_false_positive_rate(step_results: list[StepResult]) -> float:
    """Compute flag false-positive rate: steps with extra flags not in expected.

    Counts steps where the model predicted flags not in the expected set.
    This measures flag-specific false positives only; unwarranted state
    transitions are captured separately by state accuracy.
    """
    if not step_results:
        return 0.0
    fp_count = 0
    for sr in step_results:
        decision = sr.decision
        predicted = set(decision.predicted_flags)
        expected = set(decision.expected_flags)
        if predicted - expected:
            fp_count += 1
    return fp_count / len(step_results) * 100


def compute_scenario_reliability(scenario_results: list[ScenarioResult]) -> float:
    """Compute scenario reliability: percentage of scenarios where ALL steps passed."""
    if not scenario_results:
        return 0.0
    correct = sum(1 for sr in scenario_results if sr.all_correct)
    return correct / len(scenario_results) * 100


def compute_accuracy_by_category(
    scenario_results: list[ScenarioResult],
) -> dict[str, float]:
    """Compute state accuracy grouped by scenario category."""
    by_category: dict[str, list[StepResult]] = {}
    for sr in scenario_results:
        by_category.setdefault(sr.category, []).extend(sr.step_results)
    return {cat: compute_accuracy(steps) for cat, steps in sorted(by_category.items())}


def compute_variance_across_runs(
    scenario_results: list[ScenarioResult],
    model_id: str,
) -> dict[str, float | None]:
    """Compute standard deviation of metrics across runs.

    Returns dict with accuracy_std, rule_accuracy_std, flag_accuracy_std.
    Values are None if fewer than 2 runs exist.
    """
    by_run: dict[int, list[StepResult]] = {}
    for sr in scenario_results:
        if sr.model_id == model_id:
            by_run.setdefault(sr.run_number, []).extend(sr.step_results)

    if len(by_run) < 2:
        return {
            "accuracy_std": None,
            "rule_accuracy_std": None,
            "flag_accuracy_std": None,
        }

    acc_per_run = [compute_accuracy(steps) for steps in by_run.values()]
    rule_per_run = [compute_rule_accuracy(steps) for steps in by_run.values()]
    flag_per_run = [compute_flag_accuracy(steps) for steps in by_run.values()]

    return {
        "accuracy_std": statistics.stdev(acc_per_run),
        "rule_accuracy_std": statistics.stdev(rule_per_run),
        "flag_accuracy_std": statistics.stdev(flag_per_run),
    }


def compute_latency_stats(step_results: list[StepResult]) -> dict[str, float]:
    """Compute latency statistics: mean, p50, p95."""
    if not step_results:
        return {"mean": 0.0, "p50": 0.0, "p95": 0.0}
    latencies = [sr.decision.latency_ms for sr in step_results]
    mean = statistics.mean(latencies)
    if len(latencies) == 1:
        return {"mean": mean, "p50": float(latencies[0]), "p95": float(latencies[0])}
    quantiles = statistics.quantiles(latencies, n=100, method="inclusive")
    return {
        "mean": mean,
        "p50": quantiles[49],
        "p95": quantiles[94],
    }


def compute_failure_breakdown(step_results: list[StepResult]) -> dict[str, int]:
    """Count failures by type."""
    counts: dict[str, int] = {}
    for sr in step_results:
        if sr.failure_type is not None:
            key = sr.failure_type.value
            counts[key] = counts.get(key, 0) + 1
    return counts


def compute_model_metrics(
    model_id: str,
    scenario_results: list[ScenarioResult],
) -> ModelMetrics:
    """Top-level aggregation: compute all metrics for a model."""
    model_results = [sr for sr in scenario_results if sr.model_id == model_id]
    all_steps = [step for sr in model_results for step in sr.step_results]

    variance = compute_variance_across_runs(scenario_results, model_id)
    latency = compute_latency_stats(all_steps)

    # Token stats
    input_tokens = [sr.decision.input_tokens for sr in all_steps]
    output_tokens = [sr.decision.output_tokens for sr in all_steps]
    token_input_mean = statistics.mean(input_tokens) if input_tokens else 0.0
    token_output_mean = statistics.mean(output_tokens) if output_tokens else 0.0

    # Cost: sum all non-None cost_estimate_usd from raw_response
    # Cost tracking deferred — adapters provide cost_estimate_usd on
    # ModelResponse, but Decision doesn't persist it. Will be added when
    # the cost column is added to the decisions table.
    total_cost: float | None = None

    return ModelMetrics(
        model_id=model_id,
        accuracy=compute_accuracy(all_steps),
        accuracy_by_category=compute_accuracy_by_category(model_results),
        rule_accuracy=compute_rule_accuracy(all_steps),
        flag_accuracy=compute_flag_accuracy(all_steps),
        false_positive_rate=compute_false_positive_rate(all_steps),
        scenario_reliability=compute_scenario_reliability(model_results),
        accuracy_std=variance["accuracy_std"],
        rule_accuracy_std=variance["rule_accuracy_std"],
        flag_accuracy_std=variance["flag_accuracy_std"],
        latency_mean_ms=latency["mean"],
        latency_p50_ms=latency["p50"],
        latency_p95_ms=latency["p95"],
        token_input_mean=token_input_mean,
        token_output_mean=token_output_mean,
        total_cost_usd=total_cost,
        failure_counts=compute_failure_breakdown(all_steps),
    )
