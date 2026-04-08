"""Regenerate summary.json / query_summary.json from per-run JSON and DB data.

Reads per-run JSON files (intact after the Phase 5 evaluation) and the
SQLite evaluation database to reconstruct proper summary files that were
overwritten with placeholder data.

Usage:
    uv run python scripts/regenerate_summary.py --routing results/routing_rag
    uv run python scripts/regenerate_summary.py --query results/query_rag
    uv run python scripts/regenerate_summary.py \
        --routing results/routing_rag --query results/query_rag

Committed copies are also written to data/evaluation_summaries/ for git
tracking (results/ is gitignored).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.metrics import ModelMetrics  # noqa: E402
from src.evaluation.query_metrics import QueryModelMetrics  # noqa: E402

COMMITTED_DIR = PROJECT_ROOT / "data" / "evaluation_summaries"


# ---------------------------------------------------------------------------
# Per-run JSON loading (reuses patterns from analysis.py)
# ---------------------------------------------------------------------------


def load_run_files(results_dir: Path, glob_pattern: str) -> dict[str, list[dict[str, Any]]]:
    """Read per-model run JSON files, grouped by model_id."""
    by_model: dict[str, list[dict[str, Any]]] = {}
    for model_dir in sorted(results_dir.iterdir()):
        if not model_dir.is_dir():
            continue
        run_files = sorted(model_dir.glob(glob_pattern))
        if not run_files:
            continue
        runs: list[dict[str, Any]] = []
        for rf in run_files:
            try:
                runs.append(json.loads(rf.read_text(encoding="utf-8")))
            except json.JSONDecodeError as exc:
                print(
                    f"  WARNING: skipping malformed run file {rf}: {exc}",
                    file=sys.stderr,
                )
        if not runs:
            continue
        model_ids = {r["model_id"] for r in runs}
        if len(model_ids) != 1:
            raise ValueError(f"{model_dir.name}: expected single model_id, found {model_ids}")
        by_model[next(iter(model_ids))] = runs
    return by_model


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


_ALLOWED_TABLES = frozenset({"decisions", "query_decisions"})


def get_token_averages(db_path: Path, table: str = "decisions") -> dict[str, dict[str, float]]:
    """Query the evaluation DB for average input/output tokens per model."""
    if table not in _ALLOWED_TABLES:
        raise ValueError(f"Unknown table: {table!r}")
    if not db_path.exists():
        print(
            f"  WARNING: DB not found at {db_path}; token metrics will be 0.0",
            file=sys.stderr,
        )
        return {}
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            f"SELECT d.model_id, AVG(d.input_tokens), AVG(d.output_tokens) "
            f"FROM {table} d GROUP BY d.model_id"
        ).fetchall()
    finally:
        conn.close()
    return {row[0]: {"input_mean": row[1] or 0.0, "output_mean": row[2] or 0.0} for row in rows}


def get_false_positive_rates(db_path: Path) -> dict[str, float]:
    """Compute false-positive rate per model from DB decision data.

    A false positive is a step where predicted_flags contains flags
    not in expected_flags.
    """
    if not db_path.exists():
        print(
            f"  WARNING: DB not found at {db_path}; FP metrics will be 0.0",
            file=sys.stderr,
        )
        return {}
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT model_id, predicted_flags, expected_flags FROM decisions"
        ).fetchall()
    finally:
        conn.close()

    by_model: dict[str, dict[str, int]] = {}
    for model_id, pred_raw, exp_raw in rows:
        try:
            predicted = set(json.loads(pred_raw))
            expected = set(json.loads(exp_raw))
        except json.JSONDecodeError as exc:
            print(
                f"  WARNING: skipping malformed flags row for model {model_id}: {exc}",
                file=sys.stderr,
            )
            continue
        if model_id not in by_model:
            by_model[model_id] = {"fp": 0, "total": 0}
        by_model[model_id]["total"] += 1
        if predicted - expected:
            by_model[model_id]["fp"] += 1

    return {
        mid: (counts["fp"] / counts["total"] * 100 if counts["total"] > 0 else 0.0)
        for mid, counts in by_model.items()
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _percentile(sorted_data: list[int | float], pct: float) -> float:
    """Nearest-rank percentile with linear interpolation."""
    n = len(sorted_data)
    if n == 1:
        return float(sorted_data[0])
    k = (n - 1) * pct / 100
    f = int(k)
    c = min(f + 1, n - 1)
    frac = k - f
    return sorted_data[f] + frac * (sorted_data[c] - sorted_data[f])


# ---------------------------------------------------------------------------
# Routing summary regeneration
# ---------------------------------------------------------------------------


def compute_routing_metrics(
    run_data: dict[str, list[dict[str, Any]]],
    db_path: Path,
) -> list[ModelMetrics]:
    """Compute ModelMetrics for each model from per-run JSON and DB data."""
    token_avgs = get_token_averages(db_path, "decisions")
    fp_rates = get_false_positive_rates(db_path)

    all_metrics: list[ModelMetrics] = []
    for model_id, runs in run_data.items():
        try:
            # Flatten all steps across all runs
            all_steps: list[dict[str, Any]] = []
            scenarios_by_run: dict[int, list[dict[str, Any]]] = {}
            all_scenarios: list[dict[str, Any]] = []

            for run in runs:
                run_num = run["run_number"]
                run_scenarios = run.get("scenarios", [])
                scenarios_by_run[run_num] = run_scenarios
                all_scenarios.extend(run_scenarios)
                for scenario in run_scenarios:
                    all_steps.extend(scenario.get("steps", []))

            total = len(all_steps)
            if total == 0:
                continue

            # Accuracy
            accuracy = sum(1 for s in all_steps if s["state_correct"]) / total * 100
            rule_accuracy = sum(1 for s in all_steps if s["rules_correct"]) / total * 100
            flag_accuracy = sum(1 for s in all_steps if s["flags_correct"]) / total * 100

            # Scenario reliability
            scenario_count = len(all_scenarios)
            reliable = sum(1 for sc in all_scenarios if sc["all_correct"])
            scenario_reliability = reliable / scenario_count * 100 if scenario_count else 0.0

            # Accuracy by category
            cat_steps: dict[str, list[dict[str, Any]]] = {}
            for scenario in all_scenarios:
                cat = scenario["category"]
                cat_steps.setdefault(cat, []).extend(scenario.get("steps", []))
            accuracy_by_category = {
                cat: sum(1 for s in steps if s["state_correct"]) / len(steps) * 100
                for cat, steps in sorted(cat_steps.items())
            }

            # Variance across runs
            accuracy_std = None
            rule_accuracy_std = None
            flag_accuracy_std = None
            if len(scenarios_by_run) >= 2:
                acc_per_run = []
                rule_per_run = []
                flag_per_run = []
                for run_scenarios in scenarios_by_run.values():
                    run_steps = [s for sc in run_scenarios for s in sc.get("steps", [])]
                    if run_steps:
                        r_total = len(run_steps)
                        acc_per_run.append(
                            sum(1 for s in run_steps if s["state_correct"]) / r_total * 100
                        )
                        rule_per_run.append(
                            sum(1 for s in run_steps if s["rules_correct"]) / r_total * 100
                        )
                        flag_per_run.append(
                            sum(1 for s in run_steps if s["flags_correct"]) / r_total * 100
                        )
                if len(acc_per_run) >= 2:
                    accuracy_std = statistics.stdev(acc_per_run)
                    rule_accuracy_std = statistics.stdev(rule_per_run)
                    flag_accuracy_std = statistics.stdev(flag_per_run)

            # Latency
            latencies = [s["latency_ms"] for s in all_steps if s.get("latency_ms", 0) > 0]
            if latencies:
                latency_mean = statistics.mean(latencies)
                sorted_lat = sorted(latencies)
                latency_p50 = _percentile(sorted_lat, 50)
                latency_p95 = _percentile(sorted_lat, 95)
            else:
                latency_mean = latency_p50 = latency_p95 = 0.0

            # Failure breakdown
            failure_counts: dict[str, int] = {}
            for s in all_steps:
                ft = s.get("failure_type")
                if ft:
                    failure_counts[ft] = failure_counts.get(ft, 0) + 1

            # Tokens from DB
            tokens = token_avgs.get(model_id, {"input_mean": 0.0, "output_mean": 0.0})

            # FP rate from DB
            false_positive_rate = fp_rates.get(model_id, 0.0)

            metrics = ModelMetrics(
                model_id=model_id,
                accuracy=accuracy,
                accuracy_by_category=accuracy_by_category,
                rule_accuracy=rule_accuracy,
                flag_accuracy=flag_accuracy,
                false_positive_rate=false_positive_rate,
                scenario_reliability=scenario_reliability,
                accuracy_std=accuracy_std,
                rule_accuracy_std=rule_accuracy_std,
                flag_accuracy_std=flag_accuracy_std,
                latency_mean_ms=latency_mean,
                latency_p50_ms=latency_p50,
                latency_p95_ms=latency_p95,
                token_input_mean=tokens["input_mean"],
                token_output_mean=tokens["output_mean"],
                total_cost_usd=None,
                failure_counts=failure_counts,
            )
            all_metrics.append(metrics)
        except KeyError as exc:
            print(
                f"  WARNING: skipping model {model_id} — missing field {exc}",
                file=sys.stderr,
            )
            continue

    # Sort by accuracy descending (matches original output order)
    all_metrics.sort(key=lambda m: m.accuracy, reverse=True)
    return all_metrics


# ---------------------------------------------------------------------------
# Query summary regeneration
# ---------------------------------------------------------------------------


def compute_query_metrics(
    run_data: dict[str, list[dict[str, Any]]],
    db_path: Path,
) -> list[QueryModelMetrics]:
    """Compute QueryModelMetrics for each model from per-run JSON and DB."""
    token_avgs = get_token_averages(db_path, "query_decisions")

    all_metrics: list[QueryModelMetrics] = []
    for model_id, runs in run_data.items():
        try:
            all_results: list[dict[str, Any]] = []
            results_by_run: dict[int, list[dict[str, Any]]] = {}

            for run in runs:
                run_num = run["run_number"]
                scenarios = run.get("scenarios", [])
                results_by_run[run_num] = scenarios
                all_results.extend(scenarios)

            total = len(all_results)
            if total == 0:
                continue

            # Query accuracy
            correct = sum(1 for r in all_results if r["all_correct"])
            query_accuracy = correct / total * 100

            # Accuracy by tier
            by_tier: dict[int, list[dict[str, Any]]] = {}
            for r in all_results:
                by_tier.setdefault(r["tier"], []).append(r)
            query_accuracy_by_tier = {
                tier: sum(1 for r in items if r["all_correct"]) / len(items) * 100
                for tier, items in sorted(by_tier.items())
            }

            # Accuracy by answer type
            by_type: dict[str, list[dict[str, Any]]] = {}
            for r in all_results:
                by_type.setdefault(r["answer_type"], []).append(r)
            query_accuracy_by_answer_type = {
                at: sum(1 for r in items if r["all_correct"]) / len(items) * 100
                for at, items in sorted(by_type.items())
            }

            # Precision, recall, F1 (exclude explanation type)
            non_explanation = [r for r in all_results if r["answer_type"] != "explanation"]
            if non_explanation:
                mean_precision = statistics.mean(r["precision"] for r in non_explanation)
                mean_recall = statistics.mean(r["recall"] for r in non_explanation)
                mean_f1 = statistics.mean(r["f1"] for r in non_explanation)
            else:
                mean_precision = mean_recall = mean_f1 = 0.0

            # Scenario reliability
            by_scenario: dict[str, list[dict[str, Any]]] = {}
            for r in all_results:
                by_scenario.setdefault(r["scenario_id"], []).append(r)
            reliable = sum(
                1
                for scenario_runs in by_scenario.values()
                if all(r["all_correct"] for r in scenario_runs)
            )
            scenario_reliability = reliable / len(by_scenario) * 100

            # Variance
            accuracy_std = None
            if len(results_by_run) >= 2:
                acc_per_run = []
                for run_results in results_by_run.values():
                    if run_results:
                        r_correct = sum(1 for r in run_results if r["all_correct"])
                        acc_per_run.append(r_correct / len(run_results) * 100)
                if len(acc_per_run) >= 2:
                    accuracy_std = statistics.stdev(acc_per_run)

            # Latency
            latencies = [r["latency_ms"] for r in all_results if r.get("latency_ms", 0) > 0]
            if latencies:
                latency_mean = statistics.mean(latencies)
                sorted_lat = sorted(latencies)
                latency_p50 = _percentile(sorted_lat, 50)
                latency_p95 = _percentile(sorted_lat, 95)
            else:
                latency_mean = latency_p50 = latency_p95 = 0.0

            # Failure breakdown
            failure_counts: dict[str, int] = {}
            for r in all_results:
                ft = r.get("failure_type")
                if ft:
                    failure_counts[ft] = failure_counts.get(ft, 0) + 1

            # Tokens from DB
            tokens = token_avgs.get(model_id, {"input_mean": 0.0, "output_mean": 0.0})

            metrics = QueryModelMetrics(
                model_id=model_id,
                query_accuracy=query_accuracy,
                query_accuracy_by_tier=query_accuracy_by_tier,
                query_accuracy_by_answer_type=query_accuracy_by_answer_type,
                mean_precision=mean_precision,
                mean_recall=mean_recall,
                mean_f1=mean_f1,
                scenario_reliability=scenario_reliability,
                accuracy_std=accuracy_std,
                latency_mean_ms=latency_mean,
                latency_p50_ms=latency_p50,
                latency_p95_ms=latency_p95,
                token_input_mean=tokens["input_mean"],
                token_output_mean=tokens["output_mean"],
                total_cost_usd=None,
                failure_counts=failure_counts,
            )
            all_metrics.append(metrics)
        except KeyError as exc:
            print(
                f"  WARNING: skipping model {model_id} — missing field {exc}",
                file=sys.stderr,
            )
            continue

    all_metrics.sort(key=lambda m: m.query_accuracy, reverse=True)
    return all_metrics


def get_timestamps_from_runs(runs: dict[str, list[dict[str, Any]]]) -> dict[str, str]:
    """Extract earliest start and latest end from all runs."""
    starts: list[str] = []
    ends: list[str] = []
    for model_runs in runs.values():
        for run in model_runs:
            ts = run.get("timestamps", {})
            if ts.get("started_at"):
                starts.append(ts["started_at"])
            if ts.get("completed_at"):
                ends.append(ts["completed_at"])
    return {
        "started_at": min(starts) if starts else "unknown",
        "completed_at": max(ends) if ends else "unknown",
    }


def write_summary(
    output_path: Path,
    metrics_list: list[ModelMetrics] | list[QueryModelMetrics],
    timestamps: dict[str, str],
) -> None:
    """Write summary JSON using dataclass serialization."""
    payload = {
        "timestamps": timestamps,
        "models": [asdict(m) for m in metrics_list],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_routing(metrics: list[ModelMetrics]) -> None:
    """Print routing metrics for manual comparison against run.log."""
    print("\n=== Routing Summary (compare against run.log) ===")
    print(
        f"{'Model':<45} {'Acc%':>6} {'Rule%':>6} {'Flag%':>6} "
        f"{'Rel%':>6} {'FP%':>6} {'p50ms':>7} {'p95ms':>7}"
    )
    print("-" * 100)
    for m in metrics:
        std = f" ±{m.accuracy_std:.1f}" if m.accuracy_std is not None else ""
        print(
            f"{m.model_id:<45} {m.accuracy:>5.1f}{std:<5} "
            f"{m.rule_accuracy:>5.1f}  {m.flag_accuracy:>5.1f}  "
            f"{m.scenario_reliability:>5.1f}  {m.false_positive_rate:>5.1f}  "
            f"{m.latency_p50_ms:>6.0f}  {m.latency_p95_ms:>6.0f}"
        )
    print()


def validate_query(metrics: list[QueryModelMetrics]) -> None:
    """Print query metrics for manual comparison against run.log."""
    print("\n=== Query Summary (compare against run.log) ===")
    print(
        f"{'Model':<45} {'Acc%':>6} {'Prec':>6} {'Rec':>6} "
        f"{'F1':>6} {'Rel%':>6} {'p50ms':>7} {'p95ms':>7}"
    )
    print("-" * 100)
    for m in metrics:
        std = f" ±{m.accuracy_std:.1f}" if m.accuracy_std is not None else ""
        print(
            f"{m.model_id:<45} {m.query_accuracy:>5.1f}{std:<5} "
            f"{m.mean_precision:>5.3f}  {m.mean_recall:>5.3f}  "
            f"{m.mean_f1:>5.3f}  {m.scenario_reliability:>5.1f}  "
            f"{m.latency_p50_ms:>6.0f}  {m.latency_p95_ms:>6.0f}"
        )
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Regenerate summary.json from per-run data and evaluation DB",
    )
    parser.add_argument(
        "--routing",
        type=Path,
        default=None,
        help="Path to routing results directory (e.g. results/routing_rag)",
    )
    parser.add_argument(
        "--query",
        type=Path,
        default=None,
        help="Path to query results directory (e.g. results/query_rag)",
    )
    args = parser.parse_args(argv)

    if not args.routing and not args.query:
        parser.error("At least one of --routing or --query is required")

    COMMITTED_DIR.mkdir(parents=True, exist_ok=True)

    if args.routing:
        routing_dir = args.routing
        db_path = routing_dir / "evaluation.db"
        print(f"Loading routing runs from {routing_dir} ...")
        run_data = load_run_files(routing_dir, "run_*.json")
        print(f"  Found {len(run_data)} models")

        metrics = compute_routing_metrics(run_data, db_path)
        timestamps = get_timestamps_from_runs(run_data)

        # Write to results/ (for analysis scripts)
        out_path = routing_dir / "summary.json"
        write_summary(out_path, metrics, timestamps)
        print(f"  Wrote {out_path}")

        # Write committed copy
        committed_path = COMMITTED_DIR / "routing_rag_summary.json"
        write_summary(committed_path, metrics, timestamps)
        print(f"  Wrote {committed_path}")

        validate_routing(metrics)

    if args.query:
        query_dir = args.query
        db_path = query_dir / "evaluation.db"
        print(f"Loading query runs from {query_dir} ...")
        run_data = load_run_files(query_dir, "query_run_*.json")
        print(f"  Found {len(run_data)} models")

        metrics = compute_query_metrics(run_data, db_path)
        timestamps = get_timestamps_from_runs(run_data)

        # Write to results/ (for analysis scripts)
        out_path = query_dir / "query_summary.json"
        write_summary(out_path, metrics, timestamps)
        print(f"  Wrote {out_path}")

        # Write committed copy
        committed_path = COMMITTED_DIR / "query_rag_summary.json"
        write_summary(committed_path, metrics, timestamps)
        print(f"  Wrote {committed_path}")

        validate_query(metrics)

    print("Done.")


if __name__ == "__main__":
    main()
