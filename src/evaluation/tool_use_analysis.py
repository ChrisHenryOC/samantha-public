"""Tool-use query analysis and markdown report generation.

Reads tool-use evaluation results and optionally compares with
context-stuffing baselines to produce a markdown analysis report.

Usage:

    uv run python -m src.evaluation.tool_use_analysis
    uv run python -m src.evaluation.tool_use_analysis \
        --results-dir results/query_tool_use \
        --baseline-dir results/query_rag \
        --output results/query_tool_use/tool_use_analysis.md
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

from src.evaluation.analysis import load_run_files_by_model, short_name

logger = logging.getLogger(__name__)

DEFAULT_RESULTS_DIR = Path("results/query_tool_use")
DEFAULT_BASELINE_DIR = Path("results/query_rag")
DEFAULT_OUTPUT = Path("results/query_tool_use/tool_use_analysis.md")


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_tool_use_summary(results_dir: Path) -> dict[str, Any]:
    """Read tool_use_query_summary.json from the results directory."""
    path = results_dir / "tool_use_query_summary.json"
    if not path.exists():
        fallback = results_dir / "query_summary.json"
        if not fallback.exists():
            raise FileNotFoundError(
                f"No summary found in {results_dir}: "
                f"expected tool_use_query_summary.json or query_summary.json"
            )
        logger.warning(
            "tool_use_query_summary.json not found, falling back to query_summary.json "
            "(tool-use-specific metrics will be missing)"
        )
        path = fallback
    result: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return result


def load_tool_use_details(results_dir: Path) -> dict[str, Any]:
    """Read tool-use-specific dimensions from the combined summary.

    Reads from ``tool_use_query_summary.json`` which contains both
    standard and tool-use fields. Falls back to empty dict if not found.
    """
    path = results_dir / "tool_use_query_summary.json"
    if not path.exists():
        return {}
    result: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return result


def load_baseline_summary(baseline_dir: Path) -> dict[str, Any] | None:
    """Read query_summary.json from the baseline results directory."""
    path = baseline_dir / "query_summary.json"
    if not path.exists():
        return None
    result: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return result


def load_tool_use_run_results(
    results_dir: Path,
) -> dict[str, list[dict[str, Any]]]:
    """Read all per-model tool-use run JSON files."""
    return load_run_files_by_model(results_dir, "tool_use_run_*.json")


# ---------------------------------------------------------------------------
# Analysis functions
# ---------------------------------------------------------------------------


def _format_accuracy_table(models: list[dict[str, Any]]) -> str:
    """Format a per-model accuracy table in markdown."""
    lines: list[str] = []
    lines.append("| Model | Accuracy | Precision | Recall | F1 | Reliability |")
    lines.append("|-------|----------|-----------|--------|----|-------------|")
    for m in models:
        name = short_name(m["model_id"])
        acc = m.get("query_accuracy", 0.0)
        prec = m.get("mean_precision", 0.0)
        rec = m.get("mean_recall", 0.0)
        f1 = m.get("mean_f1", 0.0)
        rel = m.get("scenario_reliability", 0.0)
        lines.append(f"| {name} | {acc:.1f}% | {prec:.3f} | {rec:.3f} | {f1:.3f} | {rel:.1f}% |")
    return "\n".join(lines)


def _format_tier_table(models: list[dict[str, Any]]) -> str:
    """Format per-tier accuracy breakdown."""
    all_tiers: set[int] = set()
    for m in models:
        for t in m.get("query_accuracy_by_tier", {}):
            all_tiers.add(int(t))
    tiers = sorted(all_tiers)
    if not tiers:
        return "No tier data available."

    header = "| Model | " + " | ".join(f"T{t}" for t in tiers) + " |"
    separator = "|-------| " + " | ".join("---" for _ in tiers) + " |"

    lines = [header, separator]
    for m in models:
        name = short_name(m["model_id"])
        by_tier = m.get("query_accuracy_by_tier", {})
        cells = []
        for t in tiers:
            acc = by_tier.get(str(t), by_tier.get(t, 0.0))
            cells.append(f"{acc:.1f}%")
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _format_tool_usage_section(details: dict[str, Any]) -> str:
    """Format tool usage statistics section."""
    models = details.get("models", [])
    if not models:
        return "No tool usage data available."

    lines: list[str] = []
    lines.append("| Model | Total Calls | Calls/Scenario | Turns/Scenario | Max-Turns Hit |")
    lines.append("|-------|-------------|----------------|----------------|---------------|")
    for m in models:
        name = short_name(m["model_id"])
        total = m.get("tool_calls_total", 0)
        per_sc = m.get("tool_calls_per_scenario_mean", 0.0)
        turns = m.get("turns_per_scenario_mean", 0.0)
        max_hit = m.get("max_turns_hit_count", 0)
        lines.append(f"| {name} | {total} | {per_sc:.1f} | {turns:.1f} | {max_hit} |")

    lines.append("")
    lines.append("### Most-Used Tools")
    lines.append("")
    for m in models:
        name = short_name(m["model_id"])
        tools = m.get("most_used_tools", {})
        if tools:
            tool_list = ", ".join(
                f"`{tool_name}` ({tool_count})"
                for tool_name, tool_count in sorted(tools.items(), key=lambda x: -x[1])[:5]
            )
            lines.append(f"**{name}**: {tool_list}")
        else:
            lines.append(f"**{name}**: No tool calls recorded")

    return "\n".join(lines)


def _format_comparison_section(
    tool_use_models: list[dict[str, Any]],
    baseline_models: list[dict[str, Any]],
) -> str:
    """Format side-by-side comparison of tool-use vs context-stuffing."""
    # Build lookup by model_id
    baseline_by_id = {m["model_id"]: m for m in baseline_models}

    lines: list[str] = []
    lines.append("| Model | Context-Stuffing | Tool-Use | Delta |")
    lines.append("|-------|-----------------|----------|-------|")

    for m in tool_use_models:
        name = short_name(m["model_id"])
        tu_acc = m.get("query_accuracy", 0.0)
        baseline = baseline_by_id.get(m["model_id"])
        if baseline:
            cs_acc = baseline.get("query_accuracy", 0.0)
            delta = tu_acc - cs_acc
            sign = "+" if delta >= 0 else ""
            lines.append(f"| {name} | {cs_acc:.1f}% | {tu_acc:.1f}% | {sign}{delta:.1f}% |")
        else:
            lines.append(f"| {name} | — | {tu_acc:.1f}% | — |")

    # Per-tier comparison
    lines.append("")
    lines.append("### Per-Tier Delta (Tool-Use minus Context-Stuffing)")
    lines.append("")

    all_tiers: set[int] = set()
    for m in tool_use_models:
        for t in m.get("query_accuracy_by_tier", {}):
            all_tiers.add(int(t))
    tiers = sorted(all_tiers)

    if tiers:
        header = "| Model | " + " | ".join(f"T{t}" for t in tiers) + " |"
        separator = "|-------| " + " | ".join("---" for _ in tiers) + " |"
        lines.append(header)
        lines.append(separator)

        for m in tool_use_models:
            name = short_name(m["model_id"])
            tu_by_tier = m.get("query_accuracy_by_tier", {})
            baseline = baseline_by_id.get(m["model_id"])
            cs_by_tier = baseline.get("query_accuracy_by_tier", {}) if baseline else {}
            cells = []
            for t in tiers:
                tu = tu_by_tier.get(str(t), tu_by_tier.get(t, 0.0))
                cs = cs_by_tier.get(str(t), cs_by_tier.get(t, 0.0))
                delta = tu - cs
                sign = "+" if delta >= 0 else ""
                cells.append(f"{sign}{delta:.1f}%")
            lines.append(f"| {name} | " + " | ".join(cells) + " |")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def generate_report(
    results_dir: Path,
    baseline_dir: Path | None = None,
) -> str:
    """Generate a markdown analysis report for tool-use evaluation.

    Args:
        results_dir: Directory containing tool-use evaluation results.
        baseline_dir: Optional directory with context-stuffing results
            for side-by-side comparison.

    Returns:
        Markdown report as a string.
    """
    summary = load_tool_use_summary(results_dir)
    details = load_tool_use_details(results_dir)
    models = summary.get("models", [])

    sections: list[str] = []
    sections.append("# Tool-Use Query Evaluation Analysis")
    sections.append("")

    # Overall accuracy
    sections.append("## Overall Accuracy")
    sections.append("")
    sections.append(_format_accuracy_table(models))
    sections.append("")

    # Per-tier breakdown
    sections.append("## Per-Tier Accuracy")
    sections.append("")
    sections.append(_format_tier_table(models))
    sections.append("")

    # Tool usage
    sections.append("## Tool Usage")
    sections.append("")
    sections.append(_format_tool_usage_section(details))
    sections.append("")

    # Comparison with context-stuffing
    if baseline_dir and baseline_dir.exists():
        baseline = load_baseline_summary(baseline_dir)
        if baseline:
            baseline_models = baseline.get("models", [])
            sections.append("## Context-Stuffing vs Tool-Use Comparison")
            sections.append("")
            sections.append(_format_comparison_section(models, baseline_models))
            sections.append("")

    # Failure breakdown
    sections.append("## Failure Breakdown")
    sections.append("")
    sections.append(
        "| Model | "
        + " | ".join(["Timeout", "Invalid JSON", "Empty", "Wrong Schema", "Wrong IDs"])
        + " |"
    )
    sections.append("|-------| " + " | ".join(["---"] * 5) + " |")
    for m in models:
        name = short_name(m["model_id"])
        fc = m.get("failure_counts", {})
        cells = [
            str(fc.get("timeout", 0)),
            str(fc.get("invalid_json", 0)),
            str(fc.get("empty_response", 0)),
            str(fc.get("wrong_field_names", 0) + fc.get("wrong_field_type", 0)),
            str(
                fc.get("wrong_order_ids", 0)
                + fc.get("wrong_order_sequence", 0)
                + fc.get("missing_orders", 0)
                + fc.get("extra_orders", 0)
            ),
        ]
        sections.append(f"| {name} | " + " | ".join(cells) + " |")
    sections.append("")

    return "\n".join(sections)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Generate a tool-use analysis report."""
    parser = argparse.ArgumentParser(
        description="Generate tool-use query evaluation analysis report.",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=DEFAULT_RESULTS_DIR,
        help=f"Tool-use results directory (default: {DEFAULT_RESULTS_DIR})",
    )
    parser.add_argument(
        "--baseline-dir",
        type=Path,
        default=DEFAULT_BASELINE_DIR,
        help=f"Context-stuffing baseline directory (default: {DEFAULT_BASELINE_DIR})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output markdown path (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args(argv)

    if not args.results_dir.exists():
        print(
            f"Results directory not found: {args.results_dir}",
            file=sys.stderr,
        )
        return 1

    report = generate_report(
        args.results_dir,
        baseline_dir=args.baseline_dir if args.baseline_dir.exists() else None,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(f"Analysis report written to {args.output}")

    # Run markdownlint if available
    with contextlib.suppress(FileNotFoundError):
        subprocess.run(
            ["markdownlint-cli2", "--fix", str(args.output)],
            check=False,
            capture_output=True,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
