"""Combined Phase 4 baseline report — routing + query analysis.

Merges routing and query baseline results into a unified scorecard,
cross-track correlation analysis, go/no-go assessment, and Phase 5
recommendations.

Usage:
    uv run python -m src.evaluation.combined_analysis
    uv run python -m src.evaluation.combined_analysis \
        --routing-dir results/routing_baseline \
        --query-dir results/query_baseline \
        --output results/phase4_baseline_report/phase4_report.md
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from src.evaluation.analysis import short_name

DEFAULT_ROUTING_DIR = Path("results/routing_baseline")
DEFAULT_QUERY_DIR = Path("results/query_baseline")
DEFAULT_OUTPUT = Path("results/phase4_baseline_report/phase4_report.md")

# Models are "cloud" if their model_id starts with "claude-"
_CLOUD_PREFIX = "claude-"

# Clinical deployment thresholds
_ACCEPTABLE_ACCURACY = 80.0  # Minimum accuracy for feasibility
_LOW_VARIANCE_THRESHOLD = 2.0  # Maximum acceptable σ for clinical use

# Qualitative rating thresholds for capability matrix
_STRONG_ACCURACY = 90.0
_MODERATE_ACCURACY = 70.0
_WEAK_ACCURACY = 40.0
_FAST_LATENCY_MS = 1500.0
_MODERATE_LATENCY_MS = 3000.0
_ACCEPTABLE_RELIABILITY = 50.0  # Minimum scenario reliability for feasibility


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_routing_summary(routing_dir: Path) -> dict[str, Any]:
    """Read summary.json from the routing results directory."""
    path = routing_dir / "summary.json"
    result: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return result


def load_query_summary(query_dir: Path) -> dict[str, Any]:
    """Read query_summary.json from the query results directory."""
    path = query_dir / "query_summary.json"
    result: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return result


# ---------------------------------------------------------------------------
# Model merging
# ---------------------------------------------------------------------------


def merge_model_data(
    routing_models: list[dict[str, Any]],
    query_models: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge routing and query model data into a unified list.

    Each merged entry has:
    - ``model_id``: the shared model identifier
    - ``is_cloud``: whether this is a cloud model
    - ``routing``: routing metrics dict (or None if model only in query)
    - ``query``: query metrics dict (or None if model only in routing)

    Returns the list sorted by combined score descending. Models present
    in both tracks are ranked by (routing_accuracy + query_accuracy) / 2;
    models in only one track use that single score.
    """
    for i, m in enumerate(routing_models):
        if "model_id" not in m:
            raise ValueError(f"routing models[{i}] missing 'model_id'")
    for i, m in enumerate(query_models):
        if "model_id" not in m:
            raise ValueError(f"query models[{i}] missing 'model_id'")

    routing_by_id = {m["model_id"]: m for m in routing_models}
    query_by_id = {m["model_id"]: m for m in query_models}

    all_ids = set(routing_by_id.keys()) | set(query_by_id.keys())

    merged: list[dict[str, Any]] = []
    for mid in all_ids:
        r = routing_by_id.get(mid)
        q = query_by_id.get(mid)

        scores: list[float] = []
        if r is not None:
            scores.append(r["accuracy"])
        if q is not None:
            scores.append(q["query_accuracy"])
        combined = sum(scores) / len(scores) if scores else 0.0

        merged.append(
            {
                "model_id": mid,
                "is_cloud": mid.startswith(_CLOUD_PREFIX),
                "routing": r,
                "query": q,
                "combined_score": combined,
            }
        )

    merged.sort(key=lambda m: m["combined_score"], reverse=True)
    return merged


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------


def format_executive_summary(
    merged: list[dict[str, Any]],
    routing_timestamps: dict[str, str],
    query_timestamps: dict[str, str],
) -> str:
    """Format the executive summary section."""
    routing_count = sum(1 for m in merged if m["routing"] is not None)
    query_count = sum(1 for m in merged if m["query"] is not None)
    both_count = sum(1 for m in merged if m["routing"] is not None and m["query"] is not None)
    total_unique = len(merged)

    top_3 = merged[:3]

    lines = [
        "## 1. Executive Summary",
        "",
        f"- **Total unique models:** {total_unique}",
        f"- **Models in routing baseline:** {routing_count}",
        f"- **Models in query baseline:** {query_count}",
        f"- **Models in both tracks:** {both_count}",
        f"- **Routing evaluation period:** "
        f"{routing_timestamps.get('started_at', 'N/A')} to "
        f"{routing_timestamps.get('completed_at', 'N/A')}",
        f"- **Query evaluation period:** "
        f"{query_timestamps.get('started_at', 'N/A')} to "
        f"{query_timestamps.get('completed_at', 'N/A')}",
        "",
        "### Top Performers (Combined Score)",
        "",
    ]

    for i, m in enumerate(top_3, 1):
        name = short_name(m["model_id"])
        scores: list[str] = []
        if m["routing"] is not None:
            scores.append(f"routing {m['routing']['accuracy']:.1f}%")
        if m["query"] is not None:
            scores.append(f"query {m['query']['query_accuracy']:.1f}%")
        score_str = ", ".join(scores) if scores else "no scores"
        lines.append(f"{i}. **{name}** — {score_str}")

    lines.append("")
    return "\n".join(lines)


def format_unified_scorecard(merged: list[dict[str, Any]]) -> str:
    """Format the unified scorecard table.

    Columns: Model, Type, Routing Acc%, Query Acc%, Routing Rel%,
    Query Rel%, Variance (routing σ).
    """
    lines = [
        "## 2. Unified Scorecard",
        "",
        "| Model | Type | Routing Acc% | Query Acc% | Routing Rel% | Query Rel% | Routing σ |",
        "|-------|------|------------:|----------:|--------------:|----------:|---------:|",
    ]

    for m in merged:
        name = short_name(m["model_id"])
        mtype = "Cloud" if m["is_cloud"] else "Local"

        r = m["routing"]
        q = m["query"]

        r_acc = f"{r['accuracy']:.1f}" if r else "—"
        q_acc = f"{q['query_accuracy']:.1f}" if q else "—"
        r_rel = f"{r['scenario_reliability']:.1f}" if r else "—"
        q_rel = f"{q['scenario_reliability']:.1f}" if q else "—"

        r_std = f"±{r['accuracy_std']:.1f}" if r and r.get("accuracy_std") is not None else "—"

        lines.append(f"| {name} | {mtype} | {r_acc} | {q_acc} | {r_rel} | {q_rel} | {r_std} |")

    lines.append("")
    return "\n".join(lines)


def format_cross_track_analysis(merged: list[dict[str, Any]]) -> str:
    """Format cross-track correlation analysis.

    Compares routing vs query performance for models in both tracks.
    """
    both = [m for m in merged if m["routing"] is not None and m["query"] is not None]

    lines = [
        "## 3. Cross-Track Correlation",
        "",
    ]

    if not both:
        lines.append("No models evaluated on both tracks.")
        lines.append("")
        return "\n".join(lines)

    lines.extend(
        [
            "### 3.1 Routing vs Query Performance",
            "",
            "| Model | Routing Acc% | Query Acc% | Delta | Stronger Track |",
            "|-------|------------:|----------:|------:|----------------|",
        ]
    )

    routing_wins = 0
    query_wins = 0
    for m in both:
        name = short_name(m["model_id"])
        r_acc = m["routing"]["accuracy"]
        q_acc = m["query"]["query_accuracy"]
        delta = r_acc - q_acc

        if abs(delta) < 2.0:
            stronger = "Balanced"
        elif delta > 0:
            stronger = "Routing"
            routing_wins += 1
        else:
            stronger = "Query"
            query_wins += 1

        lines.append(f"| {name} | {r_acc:.1f} | {q_acc:.1f} | {delta:+.1f} | {stronger} |")

    lines.append("")

    # Summary observation
    lines.append("### 3.2 Observations")
    lines.append("")

    if routing_wins > query_wins:
        lines.append(
            f"- **{routing_wins} of {len(both)} models perform better at routing** "
            f"than query answering, suggesting these are partially independent capabilities."
        )
    elif query_wins > routing_wins:
        lines.append(
            f"- **{query_wins} of {len(both)} models perform better at queries** "
            f"than routing, suggesting query answering is the easier task."
        )
    else:
        lines.append("- Performance is **balanced across tracks** for most models.")

    # Check if ranking order is consistent
    both_by_routing = sorted(both, key=lambda m: m["routing"]["accuracy"], reverse=True)
    both_by_query = sorted(both, key=lambda m: m["query"]["query_accuracy"], reverse=True)
    routing_order = [m["model_id"] for m in both_by_routing]
    query_order = [m["model_id"] for m in both_by_query]

    if routing_order == query_order:
        lines.append(
            "- **Model ranking is identical** across both tracks — models that "
            "excel at routing also excel at query answering."
        )
    else:
        lines.append(
            "- **Model ranking differs** between tracks — routing ability and "
            "query ability are partially independent skills."
        )

    lines.append("")
    return "\n".join(lines)


def format_capability_matrix(merged: list[dict[str, Any]]) -> str:
    """Format model capability matrix.

    Shows routing strength, query strength, consistency, and latency
    as qualitative ratings.
    """
    lines = [
        "## 4. Model Capability Matrix",
        "",
        "| Model | Type | Routing | Query | Consistency | Latency |",
        "|-------|------|---------|-------|-------------|---------|",
    ]

    for m in merged:
        name = short_name(m["model_id"])
        mtype = "Cloud" if m["is_cloud"] else "Local"

        # Routing strength
        if m["routing"] is None:
            r_rating = "N/A"
        elif m["routing"]["accuracy"] >= _STRONG_ACCURACY:
            r_rating = "Strong"
        elif m["routing"]["accuracy"] >= _MODERATE_ACCURACY:
            r_rating = "Moderate"
        elif m["routing"]["accuracy"] >= _WEAK_ACCURACY:
            r_rating = "Weak"
        else:
            r_rating = "Poor"

        # Query strength
        if m["query"] is None:
            q_rating = "N/A"
        elif m["query"]["query_accuracy"] >= _STRONG_ACCURACY:
            q_rating = "Strong"
        elif m["query"]["query_accuracy"] >= _MODERATE_ACCURACY:
            q_rating = "Moderate"
        elif m["query"]["query_accuracy"] >= _WEAK_ACCURACY:
            q_rating = "Weak"
        else:
            q_rating = "Poor"

        # Consistency (based on routing variance, which has multi-run data)
        if m["routing"] is not None and m["routing"].get("accuracy_std") is not None:
            std = m["routing"]["accuracy_std"]
            if std <= 1.0:
                consistency = "High"
            elif std <= _LOW_VARIANCE_THRESHOLD:
                consistency = "Moderate"
            else:
                consistency = "Low"
        else:
            consistency = "N/A"

        # Latency (use routing latency since it has more data points)
        latency_src = m["routing"] or m["query"]
        p50 = latency_src.get("latency_p50_ms") if latency_src else None
        if p50 is not None:
            if p50 <= _FAST_LATENCY_MS:
                latency = "Fast"
            elif p50 <= _MODERATE_LATENCY_MS:
                latency = "Moderate"
            else:
                latency = "Slow"
        else:
            latency = "N/A"

        lines.append(f"| {name} | {mtype} | {r_rating} | {q_rating} | {consistency} | {latency} |")

    lines.append("")
    return "\n".join(lines)


def format_go_no_go_assessment(merged: list[dict[str, Any]]) -> str:
    """Format the go/no-go assessment for Phase 5 RAG pipeline.

    Addresses four key questions:
    1. Feasibility — do any models achieve acceptable accuracy?
    2. Ceiling benchmark — headroom between local and cloud models?
    3. RAG justification — do smaller-context models degrade?
    4. Variance — are local models consistent enough?
    """
    cloud = [m for m in merged if m["is_cloud"]]
    local = [m for m in merged if not m["is_cloud"]]

    lines = [
        "## 5. Go/No-Go Assessment",
        "",
    ]

    # Q1: Feasibility
    lines.append("### 5.1 Feasibility")
    lines.append("")

    feasible_routing = [
        m
        for m in merged
        if m["routing"] is not None and m["routing"]["accuracy"] >= _ACCEPTABLE_ACCURACY
    ]
    feasible_query = [
        m
        for m in merged
        if m["query"] is not None and m["query"]["query_accuracy"] >= _ACCEPTABLE_ACCURACY
    ]

    if feasible_routing:
        names = ", ".join(short_name(m["model_id"]) for m in feasible_routing)
        lines.append(
            f"- **Routing:** {len(feasible_routing)} model(s) achieve "
            f"≥{_ACCEPTABLE_ACCURACY:.0f}% accuracy: {names}"
        )
    else:
        lines.append(
            f"- **Routing:** No models achieve ≥{_ACCEPTABLE_ACCURACY:.0f}% accuracy "
            "with full context."
        )

    if feasible_query:
        names = ", ".join(short_name(m["model_id"]) for m in feasible_query)
        lines.append(
            f"- **Query:** {len(feasible_query)} model(s) achieve "
            f"≥{_ACCEPTABLE_ACCURACY:.0f}% accuracy: {names}"
        )
    else:
        lines.append(
            f"- **Query:** No models achieve ≥{_ACCEPTABLE_ACCURACY:.0f}% accuracy "
            "with full context."
        )

    # Scenario reliability check — the spec calls this "the key metric"
    reliable_routing = [
        m
        for m in feasible_routing
        if m["routing"].get("scenario_reliability", 0.0) >= _ACCEPTABLE_RELIABILITY
    ]
    reliable_query = [
        m
        for m in feasible_query
        if m["query"].get("scenario_reliability", 0.0) >= _ACCEPTABLE_RELIABILITY
    ]

    if feasible_routing and not reliable_routing:
        lines.append(
            f"- **Routing reliability warning:** {len(feasible_routing)} model(s) "
            f"reach ≥{_ACCEPTABLE_ACCURACY:.0f}% step accuracy but none achieve "
            f"≥{_ACCEPTABLE_RELIABILITY:.0f}% scenario reliability."
        )
    if feasible_query and not reliable_query:
        lines.append(
            f"- **Query reliability warning:** {len(feasible_query)} model(s) "
            f"reach ≥{_ACCEPTABLE_ACCURACY:.0f}% accuracy but none achieve "
            f"≥{_ACCEPTABLE_RELIABILITY:.0f}% scenario reliability."
        )

    # Routing feasibility is required for an overall "feasible" verdict
    if feasible_routing:
        lines.append("")
        lines.append(
            "**Verdict:** The task is feasible — at least one model achieves "
            "acceptable routing accuracy with full context."
        )
    elif feasible_query:
        lines.append("")
        lines.append(
            "**Verdict:** Query task is feasible, but no models achieve "
            f"≥{_ACCEPTABLE_ACCURACY:.0f}% routing accuracy. "
            "Routing remains the primary challenge."
        )
    else:
        lines.append("")
        lines.append(
            "**Verdict:** No models achieve acceptable accuracy. "
            "The task may be too hard for current models."
        )

    lines.append("")

    # Q2: Ceiling benchmark
    lines.append("### 5.2 Ceiling Benchmark")
    lines.append("")

    cloud_has_routing = any(m["routing"] is not None for m in cloud)
    local_has_routing = any(m["routing"] is not None for m in local)
    cloud_has_query = any(m["query"] is not None for m in cloud)
    local_has_query = any(m["query"] is not None for m in local)

    if cloud_has_routing and local_has_routing:
        best_cloud_routing = max(
            m["routing"]["accuracy"] for m in cloud if m["routing"] is not None
        )
        best_local_routing = max(
            m["routing"]["accuracy"] for m in local if m["routing"] is not None
        )
        routing_gap = best_cloud_routing - best_local_routing
        lines.append(
            f"- **Routing:** Best cloud {best_cloud_routing:.1f}% vs "
            f"best local {best_local_routing:.1f}% "
            f"(gap: {routing_gap:.1f} pp)"
        )
    else:
        routing_gap = None
        lines.append(
            "- **Routing:** Insufficient data — need both cloud and local "
            "models with routing results."
        )

    if cloud_has_query and local_has_query:
        best_cloud_query = max(
            m["query"]["query_accuracy"] for m in cloud if m["query"] is not None
        )
        best_local_query = max(
            m["query"]["query_accuracy"] for m in local if m["query"] is not None
        )
        query_gap = best_cloud_query - best_local_query
        lines.append(
            f"- **Query:** Best cloud {best_cloud_query:.1f}% vs "
            f"best local {best_local_query:.1f}% "
            f"(gap: {query_gap:.1f} pp)"
        )
    else:
        query_gap = None
        lines.append(
            "- **Query:** Insufficient data — need both cloud and local models with query results."
        )

    r_gap = routing_gap if routing_gap is not None else 0.0
    q_gap = query_gap if query_gap is not None else 0.0

    if routing_gap is None and query_gap is None:
        lines.append("")
        lines.append(
            "**Verdict:** Insufficient data to assess ceiling benchmark. "
            "Ensure both cloud and local models are evaluated."
        )
    elif r_gap > 20 or q_gap > 20:
        lines.append("")
        lines.append(
            "**Verdict:** Significant headroom exists between cloud and local models. "
            "RAG or other retrieval strategies could help close this gap."
        )
    elif r_gap > 5 or q_gap > 5:
        lines.append("")
        lines.append(
            "**Verdict:** Moderate headroom between cloud and local models. "
            "RAG may yield improvements."
        )
    else:
        lines.append("")
        lines.append(
            "**Verdict:** Minimal gap between cloud and local. "
            "Improvements from RAG may be limited."
        )

    lines.append("")

    # Q3: RAG justification
    lines.append("### 5.3 RAG Justification")
    lines.append("")

    local_with_routing = [m for m in local if m["routing"] is not None]
    if local_with_routing:
        # Compare local models' token usage (proxy for context consumption)
        token_usage = [
            (short_name(m["model_id"]), m["routing"].get("token_input_mean", 0.0))
            for m in local_with_routing
        ]
        token_usage.sort(key=lambda t: t[1])

        lines.append("Local model context usage (mean input tokens, routing):")
        lines.append("")
        for name, tokens in token_usage:
            lines.append(f"- **{name}:** {tokens:.0f} tokens")

        lines.append("")

        # Models with lower accuracy + high context → candidates for RAG
        low_acc_local = [
            m for m in local_with_routing if m["routing"]["accuracy"] < _ACCEPTABLE_ACCURACY
        ]
        if low_acc_local:
            names = ", ".join(short_name(m["model_id"]) for m in low_acc_local)
            lines.append(
                f"**{len(low_acc_local)} local model(s) fail to reach "
                f"{_ACCEPTABLE_ACCURACY:.0f}% routing accuracy** ({names}), "
                "despite receiving full context. RAG could help these models by "
                "providing more targeted, relevant context rather than the entire "
                "knowledge base."
            )
        else:
            lines.append(
                "All local models achieve acceptable routing accuracy with full context. "
                "RAG may still help with consistency and latency."
            )
    else:
        lines.append("No local models evaluated for routing.")

    lines.append("")

    # Q4: Variance
    lines.append("### 5.4 Variance Assessment")
    lines.append("")

    local_with_std = [
        m
        for m in local
        if m["routing"] is not None and m["routing"].get("accuracy_std") is not None
    ]

    if local_with_std:
        lines.append(
            "| Model | Routing Acc% | Flag Acc% | σ | Clinical Viable? |",
        )
        lines.append(
            "|-------|------------:|----------:|----:|-----------------|",
        )

        for m in local_with_std:
            name = short_name(m["model_id"])
            acc = m["routing"]["accuracy"]
            flag_acc = m["routing"].get("flag_accuracy")
            std = m["routing"]["accuracy_std"]
            flag_ok = flag_acc is None or flag_acc >= _ACCEPTABLE_ACCURACY
            viable = (
                "Yes"
                if acc >= _ACCEPTABLE_ACCURACY and std <= _LOW_VARIANCE_THRESHOLD and flag_ok
                else "No"
            )
            flag_str = f"{flag_acc:.1f}" if flag_acc is not None else "N/A"
            lines.append(f"| {name} | {acc:.1f} | {flag_str} | ±{std:.1f} | {viable} |")

        lines.append("")

        clinically_viable = [
            m
            for m in local_with_std
            if m["routing"]["accuracy"] >= _ACCEPTABLE_ACCURACY
            and m["routing"]["accuracy_std"] <= _LOW_VARIANCE_THRESHOLD
            and (
                m["routing"].get("flag_accuracy") is None
                or m["routing"]["flag_accuracy"] >= _ACCEPTABLE_ACCURACY
            )
        ]
        if clinically_viable:
            names = ", ".join(short_name(m["model_id"]) for m in clinically_viable)
            lines.append(
                f"**{len(clinically_viable)} local model(s) meet clinical deployment "
                f"criteria** (≥{_ACCEPTABLE_ACCURACY:.0f}% accuracy, "
                f"≤{_LOW_VARIANCE_THRESHOLD:.1f}σ): {names}"
            )
        else:
            lines.append(
                "**No local models currently meet clinical deployment criteria** "
                f"(≥{_ACCEPTABLE_ACCURACY:.0f}% accuracy with "
                f"≤{_LOW_VARIANCE_THRESHOLD:.1f}σ variance)."
            )
    else:
        lines.append("No multi-run variance data available for local models.")

    lines.append("")
    return "\n".join(lines)


def format_phase5_recommendations(merged: list[dict[str, Any]]) -> str:
    """Format Phase 5 recommendations based on baseline results."""
    cloud = [m for m in merged if m["is_cloud"]]
    local = [m for m in merged if not m["is_cloud"]]

    lines = [
        "## 6. Phase 5 Recommendations",
        "",
    ]

    # Identify promising local models (those with routing accuracy > 40%)
    promising = [m for m in local if m["routing"] is not None and m["routing"]["accuracy"] >= 40.0]
    promising.sort(
        key=lambda m: m["routing"]["accuracy"],
        reverse=True,
    )

    if promising:
        lines.append("### 6.1 Priority Models for RAG")
        lines.append("")
        lines.append(
            "These local models show sufficient baseline capability to benefit "
            "from RAG-enhanced context:"
        )
        lines.append("")
        for m in promising:
            name = short_name(m["model_id"])
            r_acc = m["routing"]["accuracy"]
            q_info = ""
            if m["query"] is not None:
                q_info = f", query {m['query']['query_accuracy']:.1f}%"
            lines.append(f"1. **{name}** — routing {r_acc:.1f}%{q_info}")
        lines.append("")

    # Non-viable models to skip
    non_viable = [m for m in local if m["routing"] is not None and m["routing"]["accuracy"] < 20.0]
    if non_viable:
        lines.append("### 6.2 Models to Exclude")
        lines.append("")
        names = ", ".join(short_name(m["model_id"]) for m in non_viable)
        lines.append(
            f"These models ({names}) perform below 20% routing accuracy "
            "and are unlikely to benefit from RAG. Exclude from Phase 5."
        )
        lines.append("")

    # Expected impact
    lines.append("### 6.3 Expected RAG Impact")
    lines.append("")

    best_cloud_acc = max(
        (m["routing"]["accuracy"] for m in cloud if m["routing"] is not None),
        default=0.0,
    )
    best_local_acc = max(
        (m["routing"]["accuracy"] for m in local if m["routing"] is not None),
        default=0.0,
    )

    if best_cloud_acc > 0 and best_local_acc > 0:
        gap = best_cloud_acc - best_local_acc
        lines.append(
            f"- The cloud-local gap of **{gap:.1f} percentage points** on routing "
            f"represents the theoretical maximum improvement from better context."
        )
        lines.append(
            "- RAG is expected to improve local models by providing focused, "
            "relevant context instead of the full knowledge base."
        )
        lines.append(
            "- Priority should be given to models that already demonstrate "
            "strong rule-matching ability but struggle with state transitions."
        )
    else:
        lines.append(
            "- Insufficient data to estimate RAG impact. "
            "Ensure both cloud and local models are evaluated."
        )

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def generate_combined_report(
    routing_dir: Path,
    query_dir: Path,
    output_path: Path,
) -> Path:
    """Load data from both baselines, merge, and write the combined report."""
    routing_summary = load_routing_summary(routing_dir)
    query_summary = load_query_summary(query_dir)

    routing_models = routing_summary.get("models")
    if not routing_models:
        raise ValueError(f"No 'models' key (or empty list) in routing summary at {routing_dir}")
    query_models = query_summary.get("models")
    if not query_models:
        raise ValueError(f"No 'models' key (or empty list) in query summary at {query_dir}")

    routing_timestamps = routing_summary.get("timestamps", {})
    query_timestamps = query_summary.get("timestamps", {})

    merged = merge_model_data(routing_models, query_models)

    sections = [
        "# Phase 4 Combined Baseline Report",
        "",
        format_executive_summary(merged, routing_timestamps, query_timestamps),
        format_unified_scorecard(merged),
        format_cross_track_analysis(merged),
        format_capability_matrix(merged),
        format_go_no_go_assessment(merged),
        format_phase5_recommendations(merged),
    ]

    content = "\n".join(sections)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")

    return output_path


def _lint_markdown(path: Path) -> None:
    """Best-effort markdownlint fix. Only called from CLI entry point."""
    try:
        result = subprocess.run(
            ["markdownlint-cli2", "--fix", str(path)],
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            print(
                f"Warning: markdownlint reported unfixable issues in {path}",
                file=sys.stderr,
            )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        print(f"Warning: markdown linting skipped: {exc}", file=sys.stderr)


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate combined Phase 4 baseline report",
    )
    parser.add_argument(
        "--routing-dir",
        type=Path,
        default=DEFAULT_ROUTING_DIR,
        help=f"Path to routing results directory (default: {DEFAULT_ROUTING_DIR})",
    )
    parser.add_argument(
        "--query-dir",
        type=Path,
        default=DEFAULT_QUERY_DIR,
        help=f"Path to query results directory (default: {DEFAULT_QUERY_DIR})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output markdown path (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args(argv)
    output = generate_combined_report(args.routing_dir, args.query_dir, args.output)
    _lint_markdown(output)
    print(f"Report written to {output}")


if __name__ == "__main__":
    main()
