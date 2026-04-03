"""RAG vs full-context comparison report.

Loads Phase 4 baseline and Phase 5 RAG evaluation results, computes
per-model deltas, and generates comparison tables and charts.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelComparison:
    """Comparison of a single model's baseline vs RAG performance."""

    model_id: str
    # Baseline metrics
    baseline_accuracy: float
    baseline_rule_accuracy: float
    baseline_flag_accuracy: float
    baseline_scenario_reliability: float
    # RAG metrics
    rag_accuracy: float
    rag_rule_accuracy: float
    rag_flag_accuracy: float
    rag_scenario_reliability: float

    @property
    def accuracy_delta(self) -> float:
        return self.rag_accuracy - self.baseline_accuracy

    @property
    def rule_accuracy_delta(self) -> float:
        return self.rag_rule_accuracy - self.baseline_rule_accuracy

    @property
    def flag_accuracy_delta(self) -> float:
        return self.rag_flag_accuracy - self.baseline_flag_accuracy

    @property
    def reliability_delta(self) -> float:
        return self.rag_scenario_reliability - self.baseline_scenario_reliability


@dataclass(frozen=True)
class CategoryComparison:
    """Comparison for a single category across baseline and RAG."""

    category: str
    baseline_accuracy: float
    rag_accuracy: float

    @property
    def delta(self) -> float:
        return self.rag_accuracy - self.baseline_accuracy


def _load_summary(results_dir: Path) -> tuple[dict[str, dict[str, Any]], str]:
    """Load summary.json from a results directory.

    Returns a tuple of (metrics_by_model_id, summary_type) where
    summary_type is ``"routing"`` or ``"query"``.
    """
    summary_type = "routing"
    for name in ("summary.json", "query_summary.json"):
        summary_path = results_dir / name
        if summary_path.exists():
            data = json.loads(summary_path.read_text(encoding="utf-8"))
            if name == "query_summary.json":
                summary_type = "query"
            break
    else:
        raise FileNotFoundError(f"No summary file found in {results_dir}")

    metrics: dict[str, dict[str, Any]] = {}
    for model_data in data.get("models", []):
        model_id = model_data["model_id"]
        metrics[model_id] = model_data
    return metrics, summary_type


def compare_results(
    baseline_dir: Path,
    rag_dir: Path,
) -> list[ModelComparison]:
    """Compare baseline and RAG results for all models.

    Args:
        baseline_dir: Path to Phase 4 baseline results.
        rag_dir: Path to Phase 5 RAG results.

    Returns:
        List of ModelComparison for each model present in both result sets.
    """
    baseline, b_type = _load_summary(baseline_dir)
    rag, r_type = _load_summary(rag_dir)

    # Only compare models present in both
    common_models = sorted(set(baseline) & set(rag))
    if not common_models:
        logger.warning("No common models between baseline and RAG results")
        return []

    # Use correct field names based on summary type.
    # Routing summaries use "accuracy", query summaries use "query_accuracy".
    b_acc_key = "query_accuracy" if b_type == "query" else "accuracy"
    r_acc_key = "query_accuracy" if r_type == "query" else "accuracy"

    comparisons: list[ModelComparison] = []
    for model_id in common_models:
        b = baseline[model_id]
        r = rag[model_id]
        comparisons.append(
            ModelComparison(
                model_id=model_id,
                baseline_accuracy=b.get(b_acc_key, 0.0),
                baseline_rule_accuracy=b.get("rule_accuracy", 0.0),
                baseline_flag_accuracy=b.get("flag_accuracy", 0.0),
                baseline_scenario_reliability=b.get("scenario_reliability", 0.0),
                rag_accuracy=r.get(r_acc_key, 0.0),
                rag_rule_accuracy=r.get("rule_accuracy", 0.0),
                rag_flag_accuracy=r.get("flag_accuracy", 0.0),
                rag_scenario_reliability=r.get("scenario_reliability", 0.0),
            )
        )
    return comparisons


def compare_categories(
    baseline_dir: Path,
    rag_dir: Path,
) -> list[CategoryComparison]:
    """Compare per-category accuracy between baseline and RAG.

    Aggregates across all models to show category-level impact.
    """
    baseline, b_type = _load_summary(baseline_dir)
    rag, r_type = _load_summary(rag_dir)

    # Collect per-category accuracy across all models.
    # Routing uses "accuracy_by_category", query uses "query_accuracy_by_tier"
    # and "query_accuracy_by_answer_type".
    b_cat_key = "accuracy_by_category"
    r_cat_key = "accuracy_by_category"
    if b_type == "query":
        b_cat_key = "query_accuracy_by_answer_type"
    if r_type == "query":
        r_cat_key = "query_accuracy_by_answer_type"

    baseline_cats: dict[str, list[float]] = {}
    rag_cats: dict[str, list[float]] = {}

    for model_data in baseline.values():
        for cat, acc in model_data.get(b_cat_key, {}).items():
            baseline_cats.setdefault(cat, []).append(acc)

    for model_data in rag.values():
        for cat, acc in model_data.get(r_cat_key, {}).items():
            rag_cats.setdefault(cat, []).append(acc)

    common_cats = sorted(set(baseline_cats) & set(rag_cats))
    comparisons: list[CategoryComparison] = []
    for cat in common_cats:
        b_mean = sum(baseline_cats[cat]) / len(baseline_cats[cat])
        r_mean = sum(rag_cats[cat]) / len(rag_cats[cat])
        comparisons.append(
            CategoryComparison(category=cat, baseline_accuracy=b_mean, rag_accuracy=r_mean)
        )
    return comparisons


def _delta_str(delta: float) -> str:
    """Format a delta with sign indicator."""
    if delta > 0:
        return f"+{delta:.1f}"
    return f"{delta:.1f}"


def print_comparison_table(comparisons: list[ModelComparison]) -> None:
    """Print a formatted comparison table to stdout."""
    if not comparisons:
        print("No comparison data available.")
        return

    print()
    print("=" * 100)
    print("RAG vs Full-Context Comparison")
    print("=" * 100)
    print()
    print(
        f"{'Model':<40s} {'Baseline':>10s} {'RAG':>10s} {'Delta':>10s} "
        f"{'Rule B':>8s} {'Rule R':>8s} {'Rule D':>8s}"
    )
    print("-" * 100)

    for c in comparisons:
        print(
            f"{c.model_id:<40s} "
            f"{c.baseline_accuracy:>9.1f}% {c.rag_accuracy:>9.1f}% "
            f"{_delta_str(c.accuracy_delta):>10s} "
            f"{c.baseline_rule_accuracy:>7.1f}% {c.rag_rule_accuracy:>7.1f}% "
            f"{_delta_str(c.rule_accuracy_delta):>8s}"
        )

    print()
    # Summary: which models improved vs degraded
    improved = [c for c in comparisons if c.accuracy_delta > 0]
    degraded = [c for c in comparisons if c.accuracy_delta < 0]
    unchanged = [c for c in comparisons if c.accuracy_delta == 0]

    if improved:
        print(f"Improved ({len(improved)}): {', '.join(c.model_id for c in improved)}")
    if degraded:
        print(f"Degraded ({len(degraded)}): {', '.join(c.model_id for c in degraded)}")
    if unchanged:
        print(f"Unchanged ({len(unchanged)}): {', '.join(c.model_id for c in unchanged)}")


def write_comparison_report(
    output_dir: Path,
    model_comparisons: list[ModelComparison],
    category_comparisons: list[CategoryComparison],
) -> Path:
    """Write comparison results to JSON.

    Returns the path to the written file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "rag_comparison.json"

    payload = {
        "models": [
            {
                "model_id": c.model_id,
                "baseline": {
                    "accuracy": c.baseline_accuracy,
                    "rule_accuracy": c.baseline_rule_accuracy,
                    "flag_accuracy": c.baseline_flag_accuracy,
                    "scenario_reliability": c.baseline_scenario_reliability,
                },
                "rag": {
                    "accuracy": c.rag_accuracy,
                    "rule_accuracy": c.rag_rule_accuracy,
                    "flag_accuracy": c.rag_flag_accuracy,
                    "scenario_reliability": c.rag_scenario_reliability,
                },
                "delta": {
                    "accuracy": c.accuracy_delta,
                    "rule_accuracy": c.rule_accuracy_delta,
                    "flag_accuracy": c.flag_accuracy_delta,
                    "scenario_reliability": c.reliability_delta,
                },
            }
            for c in model_comparisons
        ],
        "categories": [
            {
                "category": c.category,
                "baseline_accuracy": c.baseline_accuracy,
                "rag_accuracy": c.rag_accuracy,
                "delta": c.delta,
            }
            for c in category_comparisons
        ],
    }

    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("Comparison report written to %s", out_path)
    return out_path


def main() -> None:
    """CLI entry point for generating RAG comparison reports."""
    import argparse

    parser = argparse.ArgumentParser(description="RAG vs full-context comparison report")
    parser.add_argument(
        "--baseline",
        type=Path,
        default=Path("results/routing_baseline"),
        help="Path to Phase 4 baseline results",
    )
    parser.add_argument(
        "--rag",
        type=Path,
        default=Path("results/routing_rag"),
        help="Path to Phase 5 RAG results",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/rag_comparison"),
        help="Output directory for comparison report",
    )
    args = parser.parse_args()

    model_comparisons = compare_results(args.baseline, args.rag)
    category_comparisons = compare_categories(args.baseline, args.rag)

    print_comparison_table(model_comparisons)
    report_path = write_comparison_report(args.output, model_comparisons, category_comparisons)
    print(f"\nReport written to {report_path}")


if __name__ == "__main__":
    main()
