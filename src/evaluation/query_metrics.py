"""Metric computation for query evaluation results.

Pure functions that compute accuracy, reliability, variance, latency, and
failure breakdown from query results. No database or I/O dependencies.
"""

from __future__ import annotations

import statistics
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from src.workflow.query_validator import QueryFailureType, QueryValidationResult

# Fields whose valid range is 0–100 (percentage scale).
_PERCENTAGE_FIELDS: frozenset[str] = frozenset({"query_accuracy", "scenario_reliability"})

# Fields whose valid range is 0–1.0 (unit interval).
_UNIT_RANGE_FIELDS: frozenset[str] = frozenset({"mean_precision", "mean_recall", "mean_f1"})


class QueryDecisionLike(Protocol):
    """Protocol for query Decision-like objects used by metrics."""

    predicted_order_ids: list[str]
    expected_order_ids: list[str]
    latency_ms: int
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class QueryResult:
    """Result of a single query scenario evaluation."""

    scenario_id: str
    tier: int
    answer_type: str
    model_id: str
    run_number: int
    decision: QueryDecisionLike
    validation: QueryValidationResult
    failure_type: QueryFailureType | None

    @property
    def all_correct(self) -> bool:
        """True if the query answer is fully correct with no failure."""
        return self.failure_type is None and self.validation.all_correct


@dataclass(frozen=True)
class QueryModelMetrics:
    """Aggregated metrics for a single model across all query runs."""

    model_id: str
    query_accuracy: float
    query_accuracy_by_tier: Mapping[int, float]
    query_accuracy_by_answer_type: Mapping[str, float]
    mean_precision: float
    mean_recall: float
    mean_f1: float
    scenario_reliability: float
    accuracy_std: float | None
    latency_mean_ms: float
    latency_p50_ms: float
    latency_p95_ms: float
    token_input_mean: float
    token_output_mean: float
    total_cost_usd: float | None
    failure_counts: Mapping[str, int]

    def __post_init__(self) -> None:
        if not isinstance(self.model_id, str) or not self.model_id:
            raise ValueError("model_id must be a non-empty string")
        if not isinstance(self.failure_counts, dict):
            raise TypeError("failure_counts must be a dict")
        if not isinstance(self.query_accuracy_by_tier, dict):
            raise TypeError("query_accuracy_by_tier must be a dict")
        if not isinstance(self.query_accuracy_by_answer_type, dict):
            raise TypeError("query_accuracy_by_answer_type must be a dict")
        for tier, acc in self.query_accuracy_by_tier.items():
            if not isinstance(tier, int):
                raise TypeError(f"tier key must be int, got {type(tier).__name__}")
            if not isinstance(acc, (int, float)) or acc < 0 or acc > 100:
                raise ValueError(f"tier accuracy must be 0-100, got {acc}")
        for atype, acc in self.query_accuracy_by_answer_type.items():
            if not isinstance(atype, str):
                raise TypeError(f"answer_type key must be str, got {type(atype).__name__}")
            if not isinstance(acc, (int, float)) or acc < 0 or acc > 100:
                raise ValueError(f"answer_type accuracy must be 0-100, got {acc}")
        for key, count in self.failure_counts.items():
            if not isinstance(key, str):
                raise TypeError(f"failure_type key must be str, got {type(key).__name__}")
            if not isinstance(count, int) or count < 0:
                raise ValueError(f"failure count must be non-negative int, got {count}")

        for field_name in (
            "query_accuracy",
            "mean_precision",
            "mean_recall",
            "mean_f1",
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
            if field_name in _PERCENTAGE_FIELDS and val > 100:
                raise ValueError(f"{field_name} must be <= 100, got {val}")
            if field_name in _UNIT_RANGE_FIELDS and val > 1.0:
                raise ValueError(f"{field_name} must be <= 1.0, got {val}")


def compute_query_accuracy(results: list[QueryResult]) -> float:
    """Compute query accuracy as percentage of correct answers."""
    if not results:
        return 0.0
    correct = sum(1 for r in results if r.all_correct)
    return correct / len(results) * 100


def compute_query_accuracy_by_tier(results: list[QueryResult]) -> dict[int, float]:
    """Compute query accuracy grouped by tier."""
    by_tier: dict[int, list[QueryResult]] = {}
    for r in results:
        by_tier.setdefault(r.tier, []).append(r)
    return {tier: compute_query_accuracy(items) for tier, items in sorted(by_tier.items())}


def compute_query_accuracy_by_answer_type(results: list[QueryResult]) -> dict[str, float]:
    """Compute query accuracy grouped by answer type."""
    by_type: dict[str, list[QueryResult]] = {}
    for r in results:
        by_type.setdefault(r.answer_type, []).append(r)
    return {atype: compute_query_accuracy(items) for atype, items in sorted(by_type.items())}


def _filter_non_explanation(results: list[QueryResult]) -> list[QueryResult]:
    """Filter out explanation-type results (no order IDs to score)."""
    return [r for r in results if r.answer_type != "explanation"]


def compute_mean_precision(
    results: list[QueryResult],
    *,
    _pre_filtered: list[QueryResult] | None = None,
) -> float:
    """Compute mean precision across results, excluding explanation type."""
    filtered = _pre_filtered if _pre_filtered is not None else _filter_non_explanation(results)
    if not filtered:
        return 0.0
    return statistics.mean(r.validation.precision for r in filtered)


def compute_mean_recall(
    results: list[QueryResult],
    *,
    _pre_filtered: list[QueryResult] | None = None,
) -> float:
    """Compute mean recall across results, excluding explanation type."""
    filtered = _pre_filtered if _pre_filtered is not None else _filter_non_explanation(results)
    if not filtered:
        return 0.0
    return statistics.mean(r.validation.recall for r in filtered)


def compute_mean_f1(
    results: list[QueryResult],
    *,
    _pre_filtered: list[QueryResult] | None = None,
) -> float:
    """Compute mean F1 across results, excluding explanation type."""
    filtered = _pre_filtered if _pre_filtered is not None else _filter_non_explanation(results)
    if not filtered:
        return 0.0
    return statistics.mean(r.validation.f1 for r in filtered)


def compute_query_scenario_reliability(results: list[QueryResult]) -> float:
    """Compute scenario reliability: % of scenarios where ALL runs were correct.

    Groups results by scenario_id, then checks if every run within each
    scenario was correct. A scenario is reliable only if it never failed.
    """
    if not results:
        return 0.0
    by_scenario: dict[str, list[QueryResult]] = {}
    for r in results:
        by_scenario.setdefault(r.scenario_id, []).append(r)
    reliable = sum(1 for runs in by_scenario.values() if all(r.all_correct for r in runs))
    return reliable / len(by_scenario) * 100


def compute_query_variance(
    results: list[QueryResult],
) -> dict[str, float | None]:
    """Compute standard deviation of accuracy across runs.

    Args:
        results: Pre-filtered results for a single model.

    Returns dict with accuracy_std. Value is None if fewer than 2 runs exist.
    """
    by_run: dict[int, list[QueryResult]] = {}
    for r in results:
        by_run.setdefault(r.run_number, []).append(r)

    if len(by_run) < 2:
        return {"accuracy_std": None}

    acc_per_run = [compute_query_accuracy(items) for items in by_run.values()]
    return {"accuracy_std": statistics.stdev(acc_per_run)}


def compute_query_latency_stats(results: list[QueryResult]) -> dict[str, float]:
    """Compute latency statistics: mean, p50, p95."""
    if not results:
        return {"mean": 0.0, "p50": 0.0, "p95": 0.0}
    latencies = sorted(r.decision.latency_ms for r in results)
    n = len(latencies)
    mean = statistics.mean(latencies)
    if n == 1:
        return {"mean": mean, "p50": float(latencies[0]), "p95": float(latencies[0])}

    def _percentile(sorted_data: list[int], pct: float) -> float:
        """Nearest-rank percentile with linear interpolation."""
        k = (len(sorted_data) - 1) * pct / 100
        f = int(k)
        c = f + 1 if f + 1 < len(sorted_data) else f
        frac = k - f
        return sorted_data[f] + frac * (sorted_data[c] - sorted_data[f])

    return {
        "mean": mean,
        "p50": _percentile(latencies, 50),
        "p95": _percentile(latencies, 95),
    }


def compute_query_failure_breakdown(results: list[QueryResult]) -> dict[str, int]:
    """Count failures by type."""
    counts: dict[str, int] = {}
    for r in results:
        if r.failure_type is not None:
            key = r.failure_type.value
            counts[key] = counts.get(key, 0) + 1
    return counts


def compute_query_model_metrics(
    model_id: str,
    results: list[QueryResult],
) -> QueryModelMetrics:
    """Top-level aggregation: compute all metrics for a model's query results."""
    model_results = [r for r in results if r.model_id == model_id]
    if not model_results:
        raise ValueError(f"No results found for model_id '{model_id}'")

    variance = compute_query_variance(model_results)
    latency = compute_query_latency_stats(model_results)

    input_tokens = [r.decision.input_tokens for r in model_results]
    output_tokens = [r.decision.output_tokens for r in model_results]
    token_input_mean = statistics.mean(input_tokens)
    token_output_mean = statistics.mean(output_tokens)

    total_cost: float | None = None
    non_explanation = _filter_non_explanation(model_results)

    return QueryModelMetrics(
        model_id=model_id,
        query_accuracy=compute_query_accuracy(model_results),
        query_accuracy_by_tier=compute_query_accuracy_by_tier(model_results),
        query_accuracy_by_answer_type=compute_query_accuracy_by_answer_type(model_results),
        mean_precision=compute_mean_precision(model_results, _pre_filtered=non_explanation),
        mean_recall=compute_mean_recall(model_results, _pre_filtered=non_explanation),
        mean_f1=compute_mean_f1(model_results, _pre_filtered=non_explanation),
        scenario_reliability=compute_query_scenario_reliability(model_results),
        accuracy_std=variance["accuracy_std"],
        latency_mean_ms=latency["mean"],
        latency_p50_ms=latency["p50"],
        latency_p95_ms=latency["p95"],
        token_input_mean=token_input_mean,
        token_output_mean=token_output_mean,
        total_cost_usd=total_cost,
        failure_counts=compute_query_failure_breakdown(model_results),
    )
