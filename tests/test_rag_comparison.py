"""Tests for RAG comparison module (issue #8)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.evaluation.rag_comparison import (
    CategoryComparison,
    ModelComparison,
    _load_summary,
    compare_categories,
    compare_results,
    write_comparison_report,
)


def _write_routing_summary(path: Path, models: list[dict]) -> None:
    """Write a routing-format summary.json."""
    path.mkdir(parents=True, exist_ok=True)
    (path / "summary.json").write_text(
        json.dumps({"models": models}),
        encoding="utf-8",
    )


def _write_query_summary(path: Path, models: list[dict]) -> None:
    """Write a query-format query_summary.json."""
    path.mkdir(parents=True, exist_ok=True)
    (path / "query_summary.json").write_text(
        json.dumps({"models": models}),
        encoding="utf-8",
    )


class TestLoadSummary:
    def test_loads_routing_summary(self, tmp_path: Path) -> None:
        _write_routing_summary(
            tmp_path,
            [
                {"model_id": "m1", "accuracy": 75.0, "rule_accuracy": 60.0},
            ],
        )
        metrics, summary_type = _load_summary(tmp_path)
        assert summary_type == "routing"
        assert "m1" in metrics
        assert metrics["m1"]["accuracy"] == 75.0

    def test_loads_query_summary(self, tmp_path: Path) -> None:
        _write_query_summary(
            tmp_path,
            [
                {"model_id": "m1", "query_accuracy": 80.0},
            ],
        )
        metrics, summary_type = _load_summary(tmp_path)
        assert summary_type == "query"
        assert metrics["m1"]["query_accuracy"] == 80.0

    def test_missing_summary_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="No summary file"):
            _load_summary(tmp_path)


class TestCompareResults:
    def test_routing_comparison(self, tmp_path: Path) -> None:
        baseline = tmp_path / "baseline"
        rag = tmp_path / "rag"
        _write_routing_summary(
            baseline,
            [
                {
                    "model_id": "m1",
                    "accuracy": 70.0,
                    "rule_accuracy": 60.0,
                    "flag_accuracy": 50.0,
                    "scenario_reliability": 40.0,
                },
            ],
        )
        _write_routing_summary(
            rag,
            [
                {
                    "model_id": "m1",
                    "accuracy": 80.0,
                    "rule_accuracy": 70.0,
                    "flag_accuracy": 60.0,
                    "scenario_reliability": 50.0,
                },
            ],
        )
        results = compare_results(baseline, rag)
        assert len(results) == 1
        assert results[0].accuracy_delta == pytest.approx(10.0)
        assert results[0].rule_accuracy_delta == pytest.approx(10.0)

    def test_query_comparison_uses_query_accuracy(self, tmp_path: Path) -> None:
        baseline = tmp_path / "baseline"
        rag = tmp_path / "rag"
        _write_query_summary(
            baseline,
            [
                {"model_id": "m1", "query_accuracy": 50.0, "scenario_reliability": 30.0},
            ],
        )
        _write_query_summary(
            rag,
            [
                {"model_id": "m1", "query_accuracy": 70.0, "scenario_reliability": 40.0},
            ],
        )
        results = compare_results(baseline, rag)
        assert len(results) == 1
        assert results[0].accuracy_delta == pytest.approx(20.0)

    def test_no_common_models_returns_empty(self, tmp_path: Path) -> None:
        baseline = tmp_path / "baseline"
        rag = tmp_path / "rag"
        _write_routing_summary(
            baseline,
            [
                {"model_id": "m1", "accuracy": 70.0},
            ],
        )
        _write_routing_summary(
            rag,
            [
                {"model_id": "m2", "accuracy": 80.0},
            ],
        )
        results = compare_results(baseline, rag)
        assert results == []


class TestCompareCategories:
    def test_routing_categories(self, tmp_path: Path) -> None:
        baseline = tmp_path / "baseline"
        rag = tmp_path / "rag"
        _write_routing_summary(
            baseline,
            [
                {"model_id": "m1", "accuracy_by_category": {"accessioning": 60.0}},
            ],
        )
        _write_routing_summary(
            rag,
            [
                {"model_id": "m1", "accuracy_by_category": {"accessioning": 80.0}},
            ],
        )
        results = compare_categories(baseline, rag)
        assert len(results) == 1
        assert results[0].category == "accessioning"
        assert results[0].delta == pytest.approx(20.0)


class TestWriteComparisonReport:
    def test_writes_json(self, tmp_path: Path) -> None:
        mc = ModelComparison(
            model_id="m1",
            baseline_accuracy=70.0,
            baseline_rule_accuracy=60.0,
            baseline_flag_accuracy=50.0,
            baseline_scenario_reliability=40.0,
            rag_accuracy=80.0,
            rag_rule_accuracy=70.0,
            rag_flag_accuracy=60.0,
            rag_scenario_reliability=50.0,
        )
        cc = CategoryComparison(
            category="accessioning",
            baseline_accuracy=60.0,
            rag_accuracy=80.0,
        )
        out = write_comparison_report(tmp_path, [mc], [cc])
        assert out.exists()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert len(data["models"]) == 1
        assert data["models"][0]["delta"]["accuracy"] == pytest.approx(10.0)
        assert len(data["categories"]) == 1
