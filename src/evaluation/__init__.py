"""Evaluation package: harness, metrics, reporting, and CLI runner."""

from src.evaluation.harness import (
    EvaluationHarness,
    advance_order_state,
    build_event,
    build_order_from_event_data,
    build_slides_for_order,
)
from src.evaluation.metrics import (
    ModelMetrics,
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
from src.evaluation.reporter import (
    print_summary_table,
    write_run_results,
    write_summary_report,
)

__all__ = [
    "EvaluationHarness",
    "ModelMetrics",
    "ScenarioResult",
    "StepResult",
    "advance_order_state",
    "build_event",
    "build_order_from_event_data",
    "build_slides_for_order",
    "compute_accuracy",
    "compute_accuracy_by_category",
    "compute_failure_breakdown",
    "compute_false_positive_rate",
    "compute_flag_accuracy",
    "compute_latency_stats",
    "compute_model_metrics",
    "compute_rule_accuracy",
    "compute_scenario_reliability",
    "compute_variance_across_runs",
    "print_summary_table",
    "write_run_results",
    "write_summary_report",
]
