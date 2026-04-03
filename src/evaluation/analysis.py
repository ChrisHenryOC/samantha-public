"""Routing baseline analysis and markdown report generation.

Reads per-run JSON results and summary.json to produce a comprehensive
markdown comparison report. Works directly with JSON dicts — no dataclass
reconstruction needed.

Usage:
    uv run python -m src.evaluation.analysis
    uv run python -m src.evaluation.analysis --results-dir results/routing_baseline \
        --output results/routing_baseline/analysis.md --top-n 15
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

DEFAULT_RESULTS_DIR = Path("results/routing_baseline")
DEFAULT_OUTPUT = Path("results/routing_baseline/analysis.md")
DEFAULT_TOP_N = 10
STRUCTURAL_FAILURE_TYPES = frozenset({"invalid_json", "timeout", "empty_response"})


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_summary(results_dir: Path) -> dict[str, Any]:
    """Read summary.json from the results directory."""
    path = results_dir / "summary.json"
    result: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return result


def load_run_files_by_model(
    results_dir: Path, glob_pattern: str = "run_*.json"
) -> dict[str, list[dict[str, Any]]]:
    """Read all per-model run JSON files, organized by model_id.

    Each subdirectory of *results_dir* is treated as a model directory.
    Files matching *glob_pattern* are loaded and grouped by ``model_id``.

    Returns ``{model_id: [run_1_data, run_2_data, ...]}``.

    Raises ``ValueError`` if runs within a directory have inconsistent
    ``model_id`` values. JSON parse errors propagate directly.
    """
    by_model: dict[str, list[dict[str, Any]]] = {}
    for model_dir in sorted(results_dir.iterdir()):
        if not model_dir.is_dir():
            continue
        run_files = sorted(model_dir.glob(glob_pattern))
        if not run_files:
            continue
        runs: list[dict[str, Any]] = []
        for rf in run_files:
            data = json.loads(rf.read_text(encoding="utf-8"))
            runs.append(data)
        try:
            model_id = runs[0]["model_id"]
        except KeyError:
            raise KeyError(f"Missing 'model_id' key in {run_files[0]}") from None
        for i, run in enumerate(runs[1:], start=1):
            if run["model_id"] != model_id:
                raise ValueError(
                    f"Inconsistent model_id in {model_dir.name}: "
                    f"{run_files[0].name} has {model_id!r}, "
                    f"{run_files[i].name} has {run['model_id']!r}"
                )
        by_model[model_id] = runs
    return by_model


def load_run_results(results_dir: Path) -> dict[str, list[dict[str, Any]]]:
    """Read all per-model routing run JSON files, organized by model_id.

    Convenience wrapper around :func:`load_run_files_by_model` with the
    default glob pattern ``run_*.json``.
    """
    return load_run_files_by_model(results_dir, "run_*.json")


# ---------------------------------------------------------------------------
# Short model name helper
# ---------------------------------------------------------------------------


def short_name(model_id: str) -> str:
    """Extract a short display name from a model_id.

    ``meta-llama/llama-3.1-8b-instruct`` → ``llama-3.1-8b-instruct``
    ``claude-opus-4-6-20250514`` → ``claude-opus-4-6-20250514``
    """
    return model_id.rsplit("/", 1)[-1]


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------


def filter_aborted_runs(
    run_data: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    """Remove aborted runs from the per-model run data.

    An aborted run contains only a subset of scenarios, which skews
    per-scenario accuracy calculations. Returns a new dict with the
    same model keys but only non-aborted runs. Models whose runs are
    all aborted are omitted entirely.
    """
    filtered: dict[str, list[dict[str, Any]]] = {}
    for model_id, runs in run_data.items():
        good_runs = [r for r in runs if not r.get("aborted", False)]
        if good_runs:
            filtered[model_id] = good_runs
    return filtered


# ---------------------------------------------------------------------------
# Analysis functions
# ---------------------------------------------------------------------------


def compute_rule_selection_matrix(steps: list[dict[str, Any]]) -> dict[str, int]:
    """Compute the 2×2 rule-selection diagnostic matrix.

    Returns counts for the four quadrants:
    - ``right_rule_right_state``: both correct
    - ``right_rule_wrong_state``: rule correct, state wrong
    - ``wrong_rule_right_state``: state correct, rule wrong
    - ``wrong_rule_wrong_state``: both wrong
    """
    matrix = {
        "right_rule_right_state": 0,
        "right_rule_wrong_state": 0,
        "wrong_rule_right_state": 0,
        "wrong_rule_wrong_state": 0,
    }
    for step in steps:
        rules_ok = step["rules_correct"]
        state_ok = step["state_correct"]
        if rules_ok and state_ok:
            matrix["right_rule_right_state"] += 1
        elif rules_ok and not state_ok:
            matrix["right_rule_wrong_state"] += 1
        elif not rules_ok and state_ok:
            matrix["wrong_rule_right_state"] += 1
        else:
            matrix["wrong_rule_wrong_state"] += 1
    return matrix


def compute_hardest_scenarios(
    run_data: dict[str, list[dict[str, Any]]], top_n: int = 10
) -> list[dict[str, Any]]:
    """Find the scenarios with the lowest accuracy across all models.

    Returns a list of dicts with ``scenario_id``, ``category``,
    ``accuracy``, and ``total_evals`` (total step evaluations across
    all models and runs), sorted ascending by accuracy.
    """
    # Aggregate per-scenario step correctness across ALL models and runs
    scenario_steps: dict[str, dict[str, Any]] = {}
    for runs in run_data.values():
        for run in runs:
            for scenario in run.get("scenarios", []):
                sid = scenario["scenario_id"]
                if sid not in scenario_steps:
                    scenario_steps[sid] = {
                        "category": scenario["category"],
                        "correct": 0,
                        "total": 0,
                    }
                for step in scenario.get("steps", []):
                    scenario_steps[sid]["total"] += 1
                    if step["state_correct"]:
                        scenario_steps[sid]["correct"] += 1

    results = []
    for sid, info in scenario_steps.items():
        total = info["total"]
        accuracy = (info["correct"] / total * 100) if total > 0 else 0.0
        results.append(
            {
                "scenario_id": sid,
                "category": info["category"],
                "accuracy": accuracy,
                "total_evals": total,
            }
        )
    results.sort(key=lambda x: x["accuracy"])
    return results[:top_n]


def identify_non_viable_models(
    models: list[dict[str, Any]], threshold: float = 0.5
) -> list[dict[str, Any]]:
    """Identify models where structural failures exceed the threshold.

    A model is non-viable if structural failures (invalid_json, timeout,
    empty_response) as a fraction of **all failure counts** exceed
    ``threshold``.  The denominator is total failure counts, not total
    steps, because summary.json does not carry a total-steps field.
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
                    "accuracy": m.get("accuracy", 0),
                }
            )
    return non_viable


def compute_per_category_comparison(
    models: list[dict[str, Any]],
) -> dict[str, dict[str, float]]:
    """Reshape accuracy_by_category into a category × model matrix.

    Returns ``{category: {model_id: accuracy, ...}, ...}``.
    """
    matrix: dict[str, dict[str, float]] = {}
    for m in models:
        for cat, acc in m.get("accuracy_by_category", {}).items():
            matrix.setdefault(cat, {})[m["model_id"]] = acc
    return matrix


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------


def format_executive_summary(
    models: list[dict[str, Any]],
    run_data: dict[str, list[dict[str, Any]]],
    non_viable: list[dict[str, Any]],
    timestamps: dict[str, str],
) -> str:
    """Format the executive summary section."""
    total_models = len(models)
    # Count unique scenarios from any model's first run
    scenario_ids: set[str] = set()
    total_runs = 0
    total_decisions = 0
    for runs in run_data.values():
        total_runs += len(runs)
        for run in runs:
            for s in run.get("scenarios", []):
                scenario_ids.add(s["scenario_id"])
                total_decisions += len(s.get("steps", []))

    top_3 = models[:3]

    lines = [
        "## 1. Executive Summary",
        "",
        f"- **Models evaluated:** {total_models}",
        f"- **Scenarios:** {len(scenario_ids)}",
        f"- **Total runs:** {total_runs}",
        f"- **Total decisions:** {total_decisions:,}",
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
            f"{m['accuracy']:.1f}% accuracy, "
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
                f"{nv['accuracy']:.1f}% accuracy"
            )

    lines.append("")
    return "\n".join(lines)


def format_summary_table(models: list[dict[str, Any]]) -> str:
    """Format the primary metrics comparison table.

    Expects *models* pre-sorted by accuracy descending.
    """
    lines = [
        "## 2. Model Performance Overview",
        "",
        "### 2.1 Primary Metrics",
        "",
        "| Model | Acc% | Rule% | Flag% | Rel% | FP% |",
        "|-------|-----:|------:|------:|-----:|----:|",
    ]

    for m in models:
        name = short_name(m["model_id"])
        std_str = ""
        if m.get("accuracy_std") is not None:
            std_str = f" ±{m['accuracy_std']:.1f}"
        lines.append(
            f"| {name} "
            f"| {m['accuracy']:.1f}{std_str} "
            f"| {m['rule_accuracy']:.1f} "
            f"| {m['flag_accuracy']:.1f} "
            f"| {m['scenario_reliability']:.1f} "
            f"| {m['false_positive_rate']:.1f} |"
        )

    lines.append("")
    return "\n".join(lines)


def format_variance_table(models: list[dict[str, Any]]) -> str:
    """Format variance analysis table for local models (those with std values)."""
    local_models = [m for m in models if m.get("accuracy_std") is not None]
    if not local_models:
        return ""

    lines = [
        "### 2.2 Variance Analysis — Local Models",
        "",
        "| Model | Acc (mean ±σ) | Rule (mean ±σ) | Flag (mean ±σ) |",
        "|-------|-------------:|---------------:|---------------:|",
    ]

    for m in local_models:
        name = short_name(m["model_id"])
        acc_std = m.get("accuracy_std", 0) or 0
        rule_std = m.get("rule_accuracy_std", 0) or 0
        flag_std = m.get("flag_accuracy_std", 0) or 0
        lines.append(
            f"| {name} "
            f"| {m['accuracy']:.1f} ±{acc_std:.1f} "
            f"| {m['rule_accuracy']:.1f} ±{rule_std:.1f} "
            f"| {m['flag_accuracy']:.1f} ±{flag_std:.1f} |"
        )

    lines.append("")
    return "\n".join(lines)


def format_category_matrix(models: list[dict[str, Any]]) -> str:
    """Format the model × category accuracy table."""
    cat_matrix = compute_per_category_comparison(models)
    if not cat_matrix:
        return ""

    categories = sorted(cat_matrix.keys())
    model_ids = [m["model_id"] for m in models]

    header_names = [short_name(mid) for mid in model_ids]
    header = "| Category | " + " | ".join(header_names) + " |"
    sep = "|----------|" + "|".join("-----:" for _ in model_ids) + "|"

    lines = [
        "## 3. Accuracy by Category",
        "",
        "### 3.1 Category Performance Matrix",
        "",
        header,
        sep,
    ]

    for cat in categories:
        row = f"| {cat} "
        for mid in model_ids:
            val = cat_matrix[cat].get(mid, 0.0)
            row += f"| {val:.1f} "
        row += "|"
        lines.append(row)

    lines.append("")
    return "\n".join(lines)


def format_rule_selection_matrix(model_id: str, matrix: dict[str, int], total: int) -> str:
    """Format a single model's 2×2 rule-selection diagnostic table."""
    name = short_name(model_id)

    def pct(count: int) -> str:
        return f"{count / total * 100:.1f}%" if total > 0 else "0.0%"

    rr = matrix["right_rule_right_state"]
    rw = matrix["right_rule_wrong_state"]
    wr = matrix["wrong_rule_right_state"]
    ww = matrix["wrong_rule_wrong_state"]

    lines = [
        f"#### {name}",
        "",
        "| | Right State | Wrong State | Total |",
        "|------------|----------:|----------:|------:|",
        f"| **Right Rule** | {rr} ({pct(rr)}) | {rw} ({pct(rw)}) | {rr + rw} |",
        f"| **Wrong Rule** | {wr} ({pct(wr)}) | {ww} ({pct(ww)}) | {wr + ww} |",
        f"| **Total** | {rr + wr} | {rw + ww} | {total} |",
        "",
    ]
    return "\n".join(lines)


def format_all_rule_matrices(run_data: dict[str, list[dict[str, Any]]]) -> str:
    """Format rule selection matrices for all models."""
    lines = ["## 4. Rule Selection Diagnostics", ""]

    for model_id in sorted(run_data.keys()):
        all_steps: list[dict[str, Any]] = []
        for run in run_data[model_id]:
            for scenario in run.get("scenarios", []):
                all_steps.extend(scenario.get("steps", []))
        matrix = compute_rule_selection_matrix(all_steps)
        total = len(all_steps)
        lines.append(format_rule_selection_matrix(model_id, matrix, total))

    return "\n".join(lines)


def format_failure_breakdown(models: list[dict[str, Any]]) -> str:
    """Format failure type breakdown table."""
    # Collect all failure types across models
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


def format_hardest_scenarios(scenarios: list[dict[str, Any]]) -> str:
    """Format the hardest scenarios table."""
    lines = [
        "### 5.2 Hardest Scenarios",
        "",
        "| Scenario | Category | Accuracy% | Total Evals |",
        "|----------|----------|----------:|------------:|",
    ]

    for s in scenarios:
        lines.append(
            f"| {s['scenario_id']} | {s['category']} | {s['accuracy']:.1f} | {s['total_evals']} |"
        )

    lines.append("")
    return "\n".join(lines)


def format_non_viable_section(non_viable: list[dict[str, Any]]) -> str:
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
        "exceed 50% of all failures:",
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
            f"| {nv['accuracy']:.1f} |"
        )

    lines.append("")
    return "\n".join(lines)


def format_latency_table(models: list[dict[str, Any]]) -> str:
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


def generate_report(
    results_dir: Path,
    output_path: Path,
    top_n: int = DEFAULT_TOP_N,
) -> Path:
    """Load data, run analyses, assemble markdown, and write the report."""
    summary = load_summary(results_dir)
    run_data = filter_aborted_runs(load_run_results(results_dir))

    models = summary.get("models")
    if not models:
        raise ValueError(f"No 'models' key (or empty list) in summary at {results_dir}")
    timestamps = summary.get("timestamps", {})

    # Sort once by accuracy descending — formatting functions expect this order
    ranked = sorted(models, key=lambda m: m["accuracy"], reverse=True)

    non_viable = identify_non_viable_models(models)
    hardest = compute_hardest_scenarios(run_data, top_n=top_n)

    sections = [
        "# Routing Baseline Analysis",
        "",
        format_executive_summary(ranked, run_data, non_viable, timestamps),
        format_summary_table(ranked),
        format_variance_table(ranked),
        format_category_matrix(ranked),
        format_all_rule_matrices(run_data),
        format_failure_breakdown(ranked),
        format_hardest_scenarios(hardest),
        format_non_viable_section(non_viable),
        format_latency_table(ranked),
    ]

    content = "\n".join(sections)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")

    # Auto-lint the output (best-effort — linting is cosmetic)
    try:
        subprocess.run(
            ["markdownlint-cli2", "--fix", str(output_path)],
            capture_output=True,
            timeout=30,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Warning: markdown linting skipped: {exc}", file=sys.stderr)

    return output_path


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate routing baseline analysis report",
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
    output = generate_report(args.results_dir, args.output, args.top_n)
    print(f"Report written to {output}")


if __name__ == "__main__":
    main()
