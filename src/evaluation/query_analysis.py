"""Query baseline analysis and markdown report generation.

Reads per-run query JSON results and query_summary.json to produce a
comprehensive markdown comparison report. Mirrors the routing analysis
pattern in analysis.py.

Usage:
    uv run python -m src.evaluation.query_analysis
    uv run python -m src.evaluation.query_analysis --results-dir results/query_baseline \
        --output results/query_baseline/query_analysis.md --top-n 15
"""

from __future__ import annotations

import argparse
import heapq
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from src.evaluation.analysis import (
    STRUCTURAL_FAILURE_TYPES,
    load_run_files_by_model,
    short_name,
)

DEFAULT_RESULTS_DIR = Path("results/query_baseline")
DEFAULT_OUTPUT = Path("results/query_baseline/query_analysis.md")
DEFAULT_TOP_N = 10


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_query_summary(results_dir: Path) -> dict[str, Any]:
    """Read query_summary.json from the results directory."""
    path = results_dir / "query_summary.json"
    result: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return result


def load_query_run_results(results_dir: Path) -> dict[str, list[dict[str, Any]]]:
    """Read all per-model query run JSON files, organized by model_id.

    Returns ``{model_id: [run_1_data, run_2_data, ...]}``, where each run
    dict must contain at minimum ``model_id``, ``run_number``, and
    ``scenarios`` keys.

    Convenience wrapper around :func:`~src.evaluation.analysis.load_run_files_by_model`
    with glob pattern ``query_run_*.json``.
    """
    return load_run_files_by_model(results_dir, "query_run_*.json")


# ---------------------------------------------------------------------------
# Analysis functions
# ---------------------------------------------------------------------------


def compute_hardest_query_scenarios(
    run_data: dict[str, list[dict[str, Any]]], top_n: int = 10
) -> list[dict[str, Any]]:
    """Find query scenarios with the lowest accuracy across all models.

    Returns a list of dicts with ``scenario_id``, ``tier``,
    ``answer_type``, ``accuracy``, and ``total_evals``, sorted ascending
    by accuracy.
    """
    scenario_stats: dict[str, dict[str, Any]] = {}
    for runs in run_data.values():
        for run in runs:
            for scenario in run.get("scenarios", []):
                sid = scenario["scenario_id"]
                if sid not in scenario_stats:
                    scenario_stats[sid] = {
                        "tier": scenario.get("tier"),
                        "answer_type": scenario.get("answer_type"),
                        "correct": 0,
                        "total": 0,
                    }
                scenario_stats[sid]["total"] += 1
                if scenario.get("all_correct"):
                    scenario_stats[sid]["correct"] += 1

    results = []
    for sid, info in scenario_stats.items():
        total = info["total"]
        accuracy = (info["correct"] / total * 100) if total > 0 else 0.0
        results.append(
            {
                "scenario_id": sid,
                "tier": info["tier"],
                "answer_type": info["answer_type"],
                "accuracy": accuracy,
                "total_evals": total,
            }
        )
    return heapq.nsmallest(top_n, results, key=lambda x: x["accuracy"])


def identify_query_non_viable_models(
    models: list[dict[str, Any]], threshold: float = 0.5
) -> list[dict[str, Any]]:
    """Identify models where structural failures exceed the threshold.

    A model is non-viable if structural failures (invalid_json, timeout,
    empty_response) as a fraction of **all failure counts** exceed
    ``threshold`` (default: 0.5, i.e., >50% of all failures).
    """
    non_viable = []
    for m in models:
        counts = m.get("failure_counts", {})
        structural = sum(counts.get(ft, 0) for ft in STRUCTURAL_FAILURE_TYPES)
        total_failures = sum(counts.values())
        if total_failures > 0 and structural / total_failures > threshold:
            non_viable.append(
                {
                    "model_id": m["model_id"],
                    "structural_failures": structural,
                    "total_failures": total_failures,
                    "structural_fraction": structural / total_failures,
                    "query_accuracy": m.get("query_accuracy", 0),
                }
            )
    return non_viable


def compute_tier_model_matrix(
    models: list[dict[str, Any]],
) -> dict[str, dict[str, float]]:
    """Reshape query_accuracy_by_tier into a tier x model matrix.

    Each model dict must have ``model_id`` and optionally
    ``query_accuracy_by_tier: dict[str, float]``.  Tier keys are
    preserved as strings (e.g., ``"1"``, ``"2"``); callers that need
    numeric sorting should ensure keys are integer strings.

    Returns ``{tier: {model_id: accuracy, ...}, ...}``.
    """
    matrix: dict[str, dict[str, float]] = {}
    for m in models:
        by_tier = m.get("query_accuracy_by_tier") or {}
        for tier, acc in by_tier.items():
            matrix.setdefault(tier, {})[m["model_id"]] = acc
    return matrix


def compute_answer_type_model_matrix(
    models: list[dict[str, Any]],
) -> dict[str, dict[str, float]]:
    """Reshape query_accuracy_by_answer_type into an answer_type x model matrix.

    Each model dict must have ``model_id`` and optionally
    ``query_accuracy_by_answer_type: dict[str, float]``.

    Returns ``{answer_type: {model_id: accuracy, ...}, ...}``.
    """
    matrix: dict[str, dict[str, float]] = {}
    for m in models:
        by_atype = m.get("query_accuracy_by_answer_type") or {}
        for atype, acc in by_atype.items():
            matrix.setdefault(atype, {})[m["model_id"]] = acc
    return matrix


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------


def compute_run_overview(
    run_data: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Pre-compute run overview stats in a single pass.

    Returns a dict with ``unique_scenarios``, ``total_runs``, and
    ``total_queries`` counts.
    """
    scenario_ids: set[str] = set()
    total_runs = 0
    total_queries = 0
    for runs in run_data.values():
        total_runs += len(runs)
        for run in runs:
            for s in run.get("scenarios", []):
                scenario_ids.add(s["scenario_id"])
                total_queries += 1
    return {
        "unique_scenarios": len(scenario_ids),
        "total_runs": total_runs,
        "total_queries": total_queries,
    }


def format_query_executive_summary(
    models: list[dict[str, Any]],
    run_overview: dict[str, Any],
    non_viable: list[dict[str, Any]],
    timestamps: dict[str, str],
) -> str:
    """Format the executive summary section.

    *run_overview* should be the dict returned by :func:`compute_run_overview`
    (keys: ``unique_scenarios``, ``total_runs``, ``total_queries``).
    For backward compatibility, a raw ``run_data`` dict is also accepted
    and will be converted automatically.
    """
    # Accept either pre-computed overview or raw run_data
    if "total_runs" not in run_overview:
        run_overview = compute_run_overview(run_overview)

    total_models = len(models)
    top_3 = models[:3]

    lines = [
        "## 1. Executive Summary",
        "",
        f"- **Models evaluated:** {total_models}",
        f"- **Scenarios:** {run_overview['unique_scenarios']}",
        f"- **Total runs:** {run_overview['total_runs']}",
        f"- **Total queries:** {run_overview['total_queries']:,}",
        f"- **Evaluation period:** {timestamps.get('started_at', 'N/A')} "
        f"to {timestamps.get('completed_at', 'N/A')}",
        "",
        "### Top Performers",
        "",
    ]

    for i, m in enumerate(top_3, 1):
        name = short_name(m["model_id"])
        lines.append(
            f"{i}. **{name}** — "
            f"{m['query_accuracy']:.1f}% accuracy, "
            f"{m['scenario_reliability']:.1f}% scenario reliability"
        )

    if non_viable:
        lines.extend(["", "### Non-Viable Models", ""])
        for nv in non_viable:
            name = short_name(nv["model_id"])
            lines.append(
                f"- **{name}** — "
                f"{nv['structural_failures']} structural failures "
                f"({nv['structural_fraction']:.0%} of all failures), "
                f"{nv['query_accuracy']:.1f}% accuracy"
            )

    lines.append("")
    return "\n".join(lines)


def format_query_summary_table(models: list[dict[str, Any]]) -> str:
    """Format the primary metrics comparison table."""
    lines = [
        "## 2. Model Performance Overview",
        "",
        "### 2.1 Primary Metrics",
        "",
        "| Model | Acc% | Prec | Recall | F1 | Rel% |",
        "|-------|-----:|-----:|-------:|---:|-----:|",
    ]

    for m in models:
        name = short_name(m["model_id"])
        std_str = ""
        if m.get("accuracy_std") is not None:
            std_str = f" ±{m['accuracy_std']:.1f}"
        lines.append(
            f"| {name} "
            f"| {m['query_accuracy']:.1f}{std_str} "
            f"| {m['mean_precision']:.3f} "
            f"| {m['mean_recall']:.3f} "
            f"| {m['mean_f1']:.3f} "
            f"| {m['scenario_reliability']:.1f} |"
        )

    lines.append("")
    return "\n".join(lines)


def format_query_variance_table(models: list[dict[str, Any]]) -> str:
    """Format variance analysis table for local models (those with std values)."""
    local_models = [m for m in models if m.get("accuracy_std") is not None]
    if not local_models:
        return ""

    lines = [
        "### 2.2 Variance Analysis — Local Models",
        "",
        "| Model | Acc (mean ±σ) |",
        "|-------|-------------:|",
    ]

    for m in local_models:
        name = short_name(m["model_id"])
        lines.append(f"| {name} | {m['query_accuracy']:.1f} ±{m['accuracy_std']:.1f} |")

    lines.append("")
    return "\n".join(lines)


def _format_accuracy_matrix_table(
    section_title: str,
    row_label: str,
    row_keys: list[str],
    matrix: dict[str, dict[str, float]],
    model_ids: list[str],
) -> str:
    """Build a row-label x model accuracy markdown table."""
    header_names = [short_name(mid) for mid in model_ids]
    header = f"| {row_label} | " + " | ".join(header_names) + " |"
    label_sep = "-" * (len(row_label) + 2)
    sep = f"|{label_sep}|" + "|".join("-----:" for _ in model_ids) + "|"

    lines = [section_title, "", header, sep]
    for key in row_keys:
        row = f"| {key} "
        for mid in model_ids:
            val = matrix[key].get(mid, 0.0)
            row += f"| {val:.1f} "
        row += "|"
        lines.append(row)

    lines.append("")
    return "\n".join(lines)


def _safe_int_sort_key(t: str) -> tuple[int, str]:
    """Sort key that handles non-integer tier strings gracefully."""
    try:
        return (int(t), t)
    except ValueError:
        return (999_999, t)


def format_tier_matrix(models: list[dict[str, Any]]) -> str:
    """Format the tier x model accuracy table."""
    tier_matrix = compute_tier_model_matrix(models)
    if not tier_matrix:
        return ""

    tiers = sorted(tier_matrix.keys(), key=_safe_int_sort_key)
    model_ids = [m["model_id"] for m in models]

    return _format_accuracy_matrix_table(
        "## 3. Accuracy by Tier", "Tier", tiers, tier_matrix, model_ids
    )


def format_answer_type_matrix(models: list[dict[str, Any]]) -> str:
    """Format the answer_type x model accuracy table."""
    at_matrix = compute_answer_type_model_matrix(models)
    if not at_matrix:
        return ""

    answer_types = sorted(at_matrix.keys())
    model_ids = [m["model_id"] for m in models]

    return _format_accuracy_matrix_table(
        "## 4. Accuracy by Answer Type",
        "Answer Type",
        answer_types,
        at_matrix,
        model_ids,
    )


def format_query_failure_breakdown(models: list[dict[str, Any]]) -> str:
    """Format failure type breakdown table."""
    all_types: set[str] = set()
    for m in models:
        all_types.update(m.get("failure_counts", {}).keys())
    failure_types = sorted(all_types)

    if not failure_types:
        return ""

    header = "| Model | " + " | ".join(failure_types) + " | Total |"
    sep = "|-------|" + "|".join("-----:" for _ in failure_types) + "|------:|"

    lines = [
        "## 5. Failure Analysis",
        "",
        "### 5.1 Failure Type Breakdown",
        "",
        header,
        sep,
    ]

    for m in models:
        name = short_name(m["model_id"])
        counts = m.get("failure_counts", {})
        row = f"| {name} "
        total = 0
        for ft in failure_types:
            c = counts.get(ft, 0)
            total += c
            row += f"| {c} "
        row += f"| {total} |"
        lines.append(row)

    lines.append("")
    return "\n".join(lines)


def format_hardest_query_scenarios(scenarios: list[dict[str, Any]]) -> str:
    """Format the hardest scenarios table."""
    lines = [
        "### 5.2 Hardest Scenarios",
        "",
        "| Scenario | Tier | Answer Type | Accuracy% | Total Evals |",
        "|----------|-----:|-------------|----------:|------------:|",
    ]

    for s in scenarios:
        lines.append(
            f"| {s['scenario_id']} "
            f"| {s['tier']} "
            f"| {s['answer_type']} "
            f"| {s['accuracy']:.1f} "
            f"| {s['total_evals']} |"
        )

    lines.append("")
    return "\n".join(lines)


def format_query_non_viable_section(
    non_viable: list[dict[str, Any]], threshold: float = 0.5
) -> str:
    """Format the non-viable models detail section."""
    if not non_viable:
        lines = [
            "### 5.3 Non-Viable Models",
            "",
            "No models exceeded the structural failure threshold.",
            "",
        ]
        return "\n".join(lines)

    lines = [
        "### 5.3 Non-Viable Models",
        "",
        "Models where structural failures (invalid JSON, timeout, empty response) "
        f"exceed {threshold:.0%} of all failures:",
        "",
        "| Model | Structural | Total Failures | Structural% | Accuracy% |",
        "|-------|----------:|---------------:|------------:|----------:|",
    ]

    for nv in non_viable:
        name = short_name(nv["model_id"])
        lines.append(
            f"| {name} "
            f"| {nv['structural_failures']} "
            f"| {nv['total_failures']} "
            f"| {nv['structural_fraction']:.1%} "
            f"| {nv['query_accuracy']:.1f} |"
        )

    lines.append("")
    return "\n".join(lines)


def format_query_latency_table(models: list[dict[str, Any]]) -> str:
    """Format latency and token usage table."""
    lines = [
        "## 6. Secondary Metrics",
        "",
        "### 6.1 Latency and Token Usage",
        "",
        "| Model | Mean (ms) | p50 (ms) | p95 (ms) | Tokens In | Tokens Out |",
        "|-------|----------:|---------:|---------:|----------:|-----------:|",
    ]

    for m in models:
        name = short_name(m["model_id"])
        lines.append(
            f"| {name} "
            f"| {m['latency_mean_ms']:.0f} "
            f"| {m['latency_p50_ms']:.0f} "
            f"| {m['latency_p95_ms']:.0f} "
            f"| {m['token_input_mean']:.0f} "
            f"| {m['token_output_mean']:.0f} |"
        )

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


_REQUIRED_MODEL_KEYS = frozenset(
    {
        "model_id",
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
    }
)


def _validate_model_keys(models: list[dict[str, Any]]) -> None:
    """Validate that each model dict has all required keys."""
    for m in models:
        missing = _REQUIRED_MODEL_KEYS - m.keys()
        if missing:
            mid = m.get("model_id", "<unknown>")
            raise KeyError(f"Model {mid!r} missing required keys: {sorted(missing)}")


def generate_query_report(
    results_dir: Path,
    output_path: Path,
    top_n: int = DEFAULT_TOP_N,
) -> Path:
    """Load data, run analyses, assemble markdown, and write the report."""
    summary = load_query_summary(results_dir)
    run_data = load_query_run_results(results_dir)

    models = summary.get("models")
    if not models:
        raise ValueError(f"No 'models' key (or empty list) in query_summary at {results_dir}")
    _validate_model_keys(models)
    timestamps = summary.get("timestamps", {})

    ranked = sorted(models, key=lambda m: m["query_accuracy"], reverse=True)

    non_viable = identify_query_non_viable_models(models)
    run_overview = compute_run_overview(run_data)
    hardest = compute_hardest_query_scenarios(run_data, top_n=top_n)

    sections = [
        "# Query Baseline Analysis",
        "",
        format_query_executive_summary(ranked, run_overview, non_viable, timestamps),
        format_query_summary_table(ranked),
        format_query_variance_table(ranked),
        format_tier_matrix(ranked),
        format_answer_type_matrix(ranked),
        format_query_failure_breakdown(ranked),
        format_hardest_query_scenarios(hardest),
        format_query_non_viable_section(non_viable),
        format_query_latency_table(ranked),
    ]

    content = "\n".join(sections)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")

    try:
        lint_result = subprocess.run(
            ["markdownlint-cli2", "--fix", str(output_path)],
            capture_output=True,
            timeout=30,
        )
        if lint_result.returncode not in (0, 1):
            stderr_text = lint_result.stderr.decode(errors="replace").strip()
            print(
                f"Warning: markdownlint-cli2 exited {lint_result.returncode}: {stderr_text}",
                file=sys.stderr,
            )
    except Exception as exc:  # noqa: BLE001
        print(f"Warning: markdown linting skipped: {exc}", file=sys.stderr)

    return output_path


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate query baseline analysis report",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=DEFAULT_RESULTS_DIR,
        help=f"Path to results directory (default: {DEFAULT_RESULTS_DIR})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output markdown path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=DEFAULT_TOP_N,
        help=f"Number of hardest scenarios to include (default: {DEFAULT_TOP_N})",
    )
    args = parser.parse_args(argv)
    output = generate_query_report(args.results_dir, args.output, args.top_n)
    print(f"Report written to {output}")


if __name__ == "__main__":
    main()
