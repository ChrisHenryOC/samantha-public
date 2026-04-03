"""Tests for tool-use reporting functions and analysis module (Phase 7e).

Tests cover write_tool_use_run_results, write_tool_use_summary_report,
print_tool_use_summary_table, and the analysis report generator.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from src.evaluation.query_metrics import QueryModelMetrics, QueryResult
from src.evaluation.reporter import (
    print_tool_use_summary_table,
    write_tool_use_run_results,
    write_tool_use_summary_report,
)
from src.evaluation.tool_use_analysis import (
    generate_report,
    load_tool_use_details,
    load_tool_use_summary,
)
from src.evaluation.tool_use_metrics import ToolUseModelMetrics
from src.workflow.query_validator import QueryValidationResult

# --- Mock decision ---


@dataclass
class MockDecisionWithOutput:
    """Mock decision with model_output for tool-use reporting."""

    predicted_order_ids: list[str]
    expected_order_ids: list[str]
    latency_ms: int
    input_tokens: int
    output_tokens: int
    model_output: dict[str, Any]


def _make_query_result(
    *,
    scenario_id: str = "QR-001",
    model_id: str = "test-model",
    tool_calls: list[dict[str, Any]] | None = None,
    turns: int = 2,
    correct: bool = True,
) -> QueryResult:
    decision = MockDecisionWithOutput(
        predicted_order_ids=["ORD-101"],
        expected_order_ids=["ORD-101"],
        latency_ms=100,
        input_tokens=50,
        output_tokens=30,
        model_output={
            "order_ids": ["ORD-101"],
            "reasoning": "test",
            "tool_calls": tool_calls
            or [
                {"tool_name": "list_orders", "arguments": {}, "result": "[]", "turn": 1},
            ],
            "turns": turns,
        },
    )
    validation = QueryValidationResult(
        order_ids_correct=correct,
        precision=1.0 if correct else 0.0,
        recall=1.0 if correct else 0.0,
        f1=1.0 if correct else 0.0,
    )
    return QueryResult(
        scenario_id=scenario_id,
        tier=1,
        answer_type="order_list",
        model_id=model_id,
        run_number=1,
        decision=decision,
        validation=validation,
        failure_type=None,
    )


def _make_standard_metrics(model_id: str = "test-model") -> QueryModelMetrics:
    return QueryModelMetrics(
        model_id=model_id,
        query_accuracy=100.0,
        query_accuracy_by_tier={1: 100.0},
        query_accuracy_by_answer_type={"order_list": 100.0},
        mean_precision=1.0,
        mean_recall=1.0,
        mean_f1=1.0,
        scenario_reliability=100.0,
        accuracy_std=None,
        latency_mean_ms=100.0,
        latency_p50_ms=100.0,
        latency_p95_ms=150.0,
        token_input_mean=50.0,
        token_output_mean=30.0,
        total_cost_usd=None,
        failure_counts={},
    )


def _make_tool_use_metrics(model_id: str = "test-model") -> ToolUseModelMetrics:
    return ToolUseModelMetrics(
        standard=_make_standard_metrics(model_id),
        tool_calls_total=5,
        tool_calls_per_scenario_mean=2.5,
        turns_per_scenario_mean=3.0,
        max_turns_hit_count=0,
        most_used_tools={"list_orders": 3, "get_order": 2},
    )


# ===========================================================================
# Reporter function tests
# ===========================================================================


class TestWriteToolUseRunResults:
    def test_writes_json_with_tool_calls(self) -> None:
        result = _make_query_result()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_tool_use_run_results(
                Path(tmpdir),
                "test-model",
                1,
                [result],
                {"started_at": "now", "completed_at": "now"},
            )
            assert path.exists()
            data = json.loads(path.read_text())
            assert data["model_id"] == "test-model"
            assert len(data["scenarios"]) == 1
            scenario = data["scenarios"][0]
            assert "tool_calls" in scenario
            assert len(scenario["tool_calls"]) == 1
            assert scenario["tool_calls"][0]["tool_name"] == "list_orders"
            assert "turns" in scenario
            assert scenario["turns"] == 2

    def test_filename_includes_tool_use(self) -> None:
        result = _make_query_result()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_tool_use_run_results(
                Path(tmpdir),
                "test-model",
                1,
                [result],
                {"started_at": "now", "completed_at": "now"},
            )
            assert "tool_use_run_1" in path.name


class TestWriteToolUseSummaryReport:
    def test_writes_combined_metrics(self) -> None:
        metrics = [_make_tool_use_metrics()]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_tool_use_summary_report(
                Path(tmpdir),
                metrics,
                {"started_at": "now", "completed_at": "now"},
            )
            assert path.exists()
            assert "tool_use_query_summary" in path.name
            data = json.loads(path.read_text())
            model = data["models"][0]
            # Standard fields
            assert "query_accuracy" in model
            assert model["query_accuracy"] == 100.0
            # Tool-use fields
            assert model["tool_calls_total"] == 5
            assert model["tool_calls_per_scenario_mean"] == 2.5
            assert model["turns_per_scenario_mean"] == 3.0
            assert model["most_used_tools"] == {"list_orders": 3, "get_order": 2}


class TestPrintToolUseSummaryTable:
    def test_prints_without_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        metrics = [_make_tool_use_metrics()]
        print_tool_use_summary_table(metrics)
        output = capsys.readouterr().out
        assert "test-model" in output
        assert "100.0" in output  # accuracy
        assert "Tool usage" in output

    def test_empty_metrics(self, capsys: pytest.CaptureFixture[str]) -> None:
        print_tool_use_summary_table([])
        output = capsys.readouterr().out
        assert "No tool-use metrics" in output


# ===========================================================================
# Analysis module tests
# ===========================================================================


class TestLoadToolUseSummary:
    def test_loads_combined_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "tool_use_query_summary.json"
            path.write_text(json.dumps({"models": [{"model_id": "test"}]}))
            result = load_tool_use_summary(Path(tmpdir))
            assert result["models"][0]["model_id"] == "test"

    def test_fallback_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            # Only query_summary.json exists
            path = Path(tmpdir) / "query_summary.json"
            path.write_text(json.dumps({"models": []}))
            result = load_tool_use_summary(Path(tmpdir))
            assert "models" in result

    def test_no_files_raises(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            pytest.raises(FileNotFoundError, match="No summary found"),
        ):
            load_tool_use_summary(Path(tmpdir))


class TestLoadToolUseDetails:
    def test_returns_empty_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = load_tool_use_details(Path(tmpdir))
            assert result == {}


class TestGenerateReport:
    def test_generates_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            results_dir = Path(tmpdir)
            summary = {
                "models": [
                    {
                        "model_id": "test-model",
                        "query_accuracy": 80.0,
                        "mean_precision": 0.9,
                        "mean_recall": 0.8,
                        "mean_f1": 0.85,
                        "scenario_reliability": 70.0,
                        "query_accuracy_by_tier": {1: 90.0, 2: 70.0},
                        "query_accuracy_by_answer_type": {"order_list": 80.0},
                        "failure_counts": {"timeout": 1, "invalid_json": 2},
                        "tool_calls_total": 10,
                        "tool_calls_per_scenario_mean": 3.0,
                        "turns_per_scenario_mean": 2.5,
                        "max_turns_hit_count": 0,
                        "most_used_tools": {"list_orders": 5, "get_order": 3},
                    }
                ],
            }
            (results_dir / "tool_use_query_summary.json").write_text(json.dumps(summary))

            report = generate_report(results_dir)
            assert "# Tool-Use Query Evaluation Analysis" in report
            assert "test-model" in report
            assert "80.0%" in report
            assert "Tool Usage" in report
            assert "Failure Breakdown" in report

    def test_comparison_section_included(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            results_dir = Path(tmpdir) / "tool_use"
            baseline_dir = Path(tmpdir) / "baseline"
            results_dir.mkdir()
            baseline_dir.mkdir()

            tool_use_summary = {
                "models": [
                    {
                        "model_id": "test-model",
                        "query_accuracy": 85.0,
                        "mean_precision": 0.9,
                        "mean_recall": 0.85,
                        "mean_f1": 0.87,
                        "scenario_reliability": 75.0,
                        "query_accuracy_by_tier": {1: 90.0, 4: 50.0},
                        "query_accuracy_by_answer_type": {"order_list": 85.0},
                        "failure_counts": {},
                    }
                ],
            }
            baseline_summary = {
                "models": [
                    {
                        "model_id": "test-model",
                        "query_accuracy": 70.0,
                        "query_accuracy_by_tier": {1: 80.0, 4: 0.0},
                    }
                ],
            }

            (results_dir / "tool_use_query_summary.json").write_text(json.dumps(tool_use_summary))
            (baseline_dir / "query_summary.json").write_text(json.dumps(baseline_summary))

            report = generate_report(results_dir, baseline_dir=baseline_dir)
            assert "Context-Stuffing vs Tool-Use" in report
            assert "+15.0%" in report  # 85 - 70
            assert "+50.0%" in report  # T4: 50 - 0
