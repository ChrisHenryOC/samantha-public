"""Evaluation reporting: JSON output and summary tables.

Writes per-run JSON results, a summary report, and prints a formatted
summary table to stdout.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict
from pathlib import Path

from src.evaluation.metrics import ModelMetrics, ScenarioResult
from src.evaluation.query_metrics import QueryModelMetrics, QueryResult
from src.evaluation.tool_use_metrics import ToolUseModelMetrics

_logger = logging.getLogger(__name__)


def write_run_results(
    output_dir: Path,
    model_id: str,
    run_number: int,
    scenario_results: list[ScenarioResult],
    timestamps: dict[str, str],
    *,
    total_scenarios: int | None = None,
    aborted: bool = False,
) -> Path:
    """Write per-run results to JSON.

    Output path: ``output_dir/<model_id_safe>/run_<N>.json``

    Args:
        total_scenarios: Expected total scenarios before any abort. When
            ``None``, defaults to ``len(scenario_results)`` (i.e. all
            scenarios completed).
        aborted: If True, the run was cut short by early-abort.
    """
    model_dir = output_dir / _safe_filename(model_id)
    model_dir.mkdir(parents=True, exist_ok=True)
    out_path = model_dir / f"run_{run_number}.json"

    results = []
    for sr in scenario_results:
        steps = []
        for step_result in sr.step_results:
            steps.append(
                {
                    "state_correct": step_result.validation.state_correct,
                    "rules_correct": step_result.validation.rules_correct,
                    "flags_correct": step_result.validation.flags_correct,
                    "failure_type": (
                        step_result.failure_type.value if step_result.failure_type else None
                    ),
                    "latency_ms": step_result.decision.latency_ms,
                    "predicted_state": step_result.decision.predicted_next_state,
                    "expected_state": step_result.decision.expected_next_state,
                }
            )
        results.append(
            {
                "scenario_id": sr.scenario_id,
                "category": sr.category,
                "all_correct": sr.all_correct,
                "steps": steps,
            }
        )

    payload: dict[str, object] = {
        "model_id": model_id,
        "run_number": run_number,
        "timestamps": timestamps,
        "total_scenarios": (
            total_scenarios if total_scenarios is not None else len(scenario_results)
        ),
        "scenarios_completed": len(scenario_results),
        "aborted": aborted,
        "scenarios": results,
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path


def write_summary_report(
    output_dir: Path,
    all_metrics: list[ModelMetrics],
    timestamps: dict[str, str],
) -> Path:
    """Write summary metrics for all models to JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "summary.json"

    models = []
    for m in all_metrics:
        models.append(asdict(m))

    payload = {
        "timestamps": timestamps,
        "models": models,
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path


def print_summary_table(all_metrics: list[ModelMetrics]) -> None:
    """Print a formatted summary table to stdout."""
    if not all_metrics:
        print("No metrics to display.")
        return

    header = (
        f"{'Model':<35} {'Acc%':>6} {'Rule%':>6} {'Flag%':>6} "
        f"{'Rel%':>6} {'FP%':>6} {'p50ms':>7} {'p95ms':>7}"
    )
    sep = "-" * len(header)

    print()
    print(sep)
    print(header)
    print(sep)

    for m in all_metrics:
        std_suffix = f" ±{m.accuracy_std:.1f}" if m.accuracy_std is not None else ""
        print(
            f"{m.model_id:<35} {m.accuracy:>5.1f}{std_suffix:>5} "
            f"{m.rule_accuracy:>5.1f}  {m.flag_accuracy:>5.1f}  "
            f"{m.scenario_reliability:>5.1f}  {m.false_positive_rate:>5.1f}  "
            f"{m.latency_p50_ms:>6.0f}  {m.latency_p95_ms:>6.0f}"
        )

    print(sep)
    print()


def write_query_run_results(
    output_dir: Path,
    model_id: str,
    run_number: int,
    query_results: list[QueryResult],
    timestamps: dict[str, str],
    *,
    total_scenarios: int | None = None,
    aborted: bool = False,
) -> Path:
    """Write per-run query results to JSON.

    Output path: ``output_dir/<model_id_safe>/query_run_<N>.json``
    """
    model_dir = output_dir / _safe_filename(model_id)
    model_dir.mkdir(parents=True, exist_ok=True)
    out_path = model_dir / f"query_run_{run_number}.json"

    results = []
    for qr in query_results:
        results.append(
            {
                "scenario_id": qr.scenario_id,
                "tier": qr.tier,
                "answer_type": qr.answer_type,
                "all_correct": qr.all_correct,
                "order_ids_correct": qr.validation.order_ids_correct,
                "precision": qr.validation.precision,
                "recall": qr.validation.recall,
                "f1": qr.validation.f1,
                "failure_type": (qr.failure_type.value if qr.failure_type else None),
                "latency_ms": qr.decision.latency_ms,
            }
        )

    payload: dict[str, object] = {
        "model_id": model_id,
        "run_number": run_number,
        "timestamps": timestamps,
        "total_scenarios": (total_scenarios if total_scenarios is not None else len(query_results)),
        "scenarios_completed": len(query_results),
        "aborted": aborted,
        "scenarios": results,
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path


def write_query_summary_report(
    output_dir: Path,
    all_metrics: list[QueryModelMetrics],
    timestamps: dict[str, str],
) -> Path:
    """Write query summary metrics for all models to JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "query_summary.json"

    models = []
    for m in all_metrics:
        models.append(asdict(m))

    payload = {
        "timestamps": timestamps,
        "models": models,
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path


def print_query_summary_table(all_metrics: list[QueryModelMetrics]) -> None:
    """Print a formatted query summary table to stdout."""
    if not all_metrics:
        print("No query metrics to display.")
        return

    header = (
        f"{'Model':<35} {'Acc%':>6} {'Prec':>6} {'Rec':>6} "
        f"{'F1':>6} {'Rel%':>6} {'p50ms':>7} {'p95ms':>7}"
    )
    sep = "-" * len(header)

    print()
    print(sep)
    print(header)
    print(sep)

    for m in all_metrics:
        std_suffix = f" ±{m.accuracy_std:.1f}" if m.accuracy_std is not None else ""
        print(
            f"{m.model_id:<35} {m.query_accuracy:>5.1f}{std_suffix:>5} "
            f"{m.mean_precision:>5.3f}  {m.mean_recall:>5.3f}  "
            f"{m.mean_f1:>5.3f}  {m.scenario_reliability:>5.1f}  "
            f"{m.latency_p50_ms:>6.0f}  {m.latency_p95_ms:>6.0f}"
        )

    print(sep)

    # Per-tier breakdown
    if all_metrics:
        print("\nPer-tier accuracy:")
        for m in all_metrics:
            tier_str = ", ".join(
                f"T{t}: {a:.1f}%" for t, a in sorted(m.query_accuracy_by_tier.items())
            )
            print(f"  {m.model_id}: {tier_str}")

        print("\nPer-answer-type accuracy:")
        for m in all_metrics:
            type_str = ", ".join(
                f"{at}: {a:.1f}%" for at, a in sorted(m.query_accuracy_by_answer_type.items())
            )
            print(f"  {m.model_id}: {type_str}")

    print()


def write_tool_use_run_results(
    output_dir: Path,
    model_id: str,
    run_number: int,
    query_results: list[QueryResult],
    timestamps: dict[str, str],
    *,
    total_scenarios: int | None = None,
    aborted: bool = False,
) -> Path:
    """Write per-run tool-use query results to JSON.

    Extends the standard query run results with tool-use metadata
    (tool_calls, turns) extracted from ``QueryDecision.model_output``.

    Output path: ``output_dir/<model_id_safe>/tool_use_run_<N>.json``
    """
    model_dir = output_dir / _safe_filename(model_id)
    model_dir.mkdir(parents=True, exist_ok=True)
    out_path = model_dir / f"tool_use_run_{run_number}.json"

    results = []
    for qr in query_results:
        model_output = getattr(qr.decision, "model_output", {})
        if not isinstance(model_output, dict):
            _logger.warning(
                "Non-dict model_output for scenario %s, writing empty tool_calls",
                qr.scenario_id,
            )
            tool_calls: list[object] = []
            turns: int = 0
        else:
            tool_calls = model_output.get("tool_calls", [])
            turns = model_output.get("turns", 0)
        results.append(
            {
                "scenario_id": qr.scenario_id,
                "tier": qr.tier,
                "answer_type": qr.answer_type,
                "all_correct": qr.all_correct,
                "order_ids_correct": qr.validation.order_ids_correct,
                "precision": qr.validation.precision,
                "recall": qr.validation.recall,
                "f1": qr.validation.f1,
                "failure_type": (qr.failure_type.value if qr.failure_type else None),
                "latency_ms": qr.decision.latency_ms,
                "tool_calls": tool_calls,
                "turns": turns,
            }
        )

    payload: dict[str, object] = {
        "model_id": model_id,
        "run_number": run_number,
        "timestamps": timestamps,
        "total_scenarios": (total_scenarios if total_scenarios is not None else len(query_results)),
        "scenarios_completed": len(query_results),
        "aborted": aborted,
        "scenarios": results,
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path


def write_tool_use_summary_report(
    output_dir: Path,
    all_metrics: list[ToolUseModelMetrics],
    timestamps: dict[str, str],
) -> Path:
    """Write tool-use summary metrics for all models to JSON.

    Includes both standard query metrics and tool-use dimensions.

    Output path: ``output_dir/tool_use_query_summary.json``
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "tool_use_query_summary.json"

    models = []
    for m in all_metrics:
        entry = asdict(m.standard)
        entry["tool_calls_total"] = m.tool_calls_total
        entry["tool_calls_per_scenario_mean"] = m.tool_calls_per_scenario_mean
        entry["turns_per_scenario_mean"] = m.turns_per_scenario_mean
        entry["max_turns_hit_count"] = m.max_turns_hit_count
        entry["most_used_tools"] = dict(m.most_used_tools)
        models.append(entry)

    payload = {
        "timestamps": timestamps,
        "models": models,
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path


def print_tool_use_summary_table(all_metrics: list[ToolUseModelMetrics]) -> None:
    """Print a formatted tool-use query summary table to stdout."""
    if not all_metrics:
        print("No tool-use metrics to display.")
        return

    header = (
        f"{'Model':<35} {'Acc%':>6} {'Prec':>6} {'Rec':>6} "
        f"{'F1':>6} {'Calls':>6} {'Turns':>6} {'p50ms':>7}"
    )
    sep = "-" * len(header)

    print()
    print(sep)
    print(header)
    print(sep)

    for m in all_metrics:
        s = m.standard
        std_suffix = f" ±{s.accuracy_std:.1f}" if s.accuracy_std is not None else ""
        print(
            f"{s.model_id:<35} {s.query_accuracy:>5.1f}{std_suffix:>5} "
            f"{s.mean_precision:>5.3f}  {s.mean_recall:>5.3f}  "
            f"{s.mean_f1:>5.3f}  {m.tool_calls_per_scenario_mean:>5.1f}  "
            f"{m.turns_per_scenario_mean:>5.1f}  {s.latency_p50_ms:>6.0f}"
        )

    print(sep)

    # Per-tier breakdown
    if all_metrics:
        print("\nPer-tier accuracy:")
        for m in all_metrics:
            s = m.standard
            tier_str = ", ".join(
                f"T{t}: {a:.1f}%" for t, a in sorted(s.query_accuracy_by_tier.items())
            )
            print(f"  {s.model_id}: {tier_str}")

        print("\nTool usage:")
        for m in all_metrics:
            top_tools = ", ".join(
                f"{name}: {count}" for name, count in list(m.most_used_tools.items())[:5]
            )
            print(
                f"  {m.model_id}: {m.tool_calls_total} calls, {m.max_turns_hit_count} max-turns-hit"
            )
            if top_tools:
                print(f"    Top tools: {top_tools}")

    print()


def _safe_filename(model_id: str) -> str:
    """Convert a model ID to a filesystem-safe directory name."""
    return re.sub(r"[^\w\-]", "_", model_id)
