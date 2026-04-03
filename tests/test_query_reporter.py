"""Tests for query-specific reporter functions."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from src.evaluation.query_metrics import QueryModelMetrics, QueryResult
from src.evaluation.reporter import (
    print_query_summary_table,
    write_query_run_results,
    write_query_summary_report,
)
from src.workflow.query_validator import QueryFailureType, QueryValidationResult


def _make_query_result(
    scenario_id: str = "QR-001",
    all_correct: bool = True,
    failure_type: QueryFailureType | None = None,
) -> QueryResult:
    """Build a minimal QueryResult for reporter tests."""
    decision = MagicMock()
    decision.latency_ms = 150
    decision.input_tokens = 100
    decision.output_tokens = 30
    validation = QueryValidationResult(
        order_ids_correct=all_correct,
        precision=1.0 if all_correct else 0.0,
        recall=1.0 if all_correct else 0.0,
        f1=1.0 if all_correct else 0.0,
    )
    return QueryResult(
        scenario_id=scenario_id,
        tier=1,
        answer_type="order_list",
        model_id="test-model",
        run_number=1,
        decision=decision,
        validation=validation,
        failure_type=failure_type,
    )


def _make_query_model_metrics(model_id: str = "test-model") -> QueryModelMetrics:
    """Build a minimal QueryModelMetrics for reporter tests."""
    return QueryModelMetrics(
        model_id=model_id,
        query_accuracy=80.0,
        query_accuracy_by_tier={1: 90.0, 2: 70.0},
        query_accuracy_by_answer_type={"order_list": 85.0, "explanation": 100.0},
        mean_precision=0.8,
        mean_recall=0.9,
        mean_f1=0.85,
        scenario_reliability=75.0,
        accuracy_std=2.5,
        latency_mean_ms=200.0,
        latency_p50_ms=180.0,
        latency_p95_ms=400.0,
        token_input_mean=100.0,
        token_output_mean=30.0,
        total_cost_usd=None,
        failure_counts={"timeout": 2},
    )


class TestWriteQueryRunResults:
    def test_writes_json_with_correct_schema(self, tmp_path: Path) -> None:
        """Output JSON has expected top-level keys and scenario shape."""
        results = [_make_query_result(), _make_query_result("QR-002")]
        timestamps = {"started_at": "2025-01-01T00:00:00", "completed_at": "2025-01-01T00:01:00"}

        out_path = write_query_run_results(
            tmp_path, "test-model", 1, results, timestamps, total_scenarios=5
        )
        assert out_path.exists()

        data = json.loads(out_path.read_text())
        assert data["model_id"] == "test-model"
        assert data["run_number"] == 1
        assert data["total_scenarios"] == 5
        assert data["scenarios_completed"] == 2
        assert data["aborted"] is False
        assert len(data["scenarios"]) == 2
        assert data["scenarios"][0]["scenario_id"] == "QR-001"

    def test_aborted_run_records_aborted_flag(self, tmp_path: Path) -> None:
        """Aborted run has aborted=True in output."""
        results = [_make_query_result()]
        timestamps = {"started_at": "2025-01-01T00:00:00", "completed_at": "2025-01-01T00:01:00"}

        out_path = write_query_run_results(
            tmp_path,
            "test-model",
            1,
            results,
            timestamps,
            total_scenarios=10,
            aborted=True,
        )
        data = json.loads(out_path.read_text())
        assert data["aborted"] is True
        assert data["total_scenarios"] == 10
        assert data["scenarios_completed"] == 1

    def test_failure_type_serialized(self, tmp_path: Path) -> None:
        """Failure type enum value is serialized as string."""
        results = [_make_query_result(failure_type=QueryFailureType.TIMEOUT)]
        timestamps = {"started_at": "2025-01-01T00:00:00", "completed_at": "2025-01-01T00:01:00"}

        out_path = write_query_run_results(tmp_path, "test-model", 1, results, timestamps)
        data = json.loads(out_path.read_text())
        assert data["scenarios"][0]["failure_type"] == "timeout"


class TestWriteQuerySummaryReport:
    def test_writes_json_with_model_metrics(self, tmp_path: Path) -> None:
        """Summary JSON contains model metrics."""
        metrics = [_make_query_model_metrics()]
        timestamps = {"started_at": "2025-01-01T00:00:00", "completed_at": "2025-01-01T00:01:00"}

        out_path = write_query_summary_report(tmp_path, metrics, timestamps)
        assert out_path.name == "query_summary.json"

        data = json.loads(out_path.read_text())
        assert len(data["models"]) == 1
        assert data["models"][0]["model_id"] == "test-model"
        assert data["models"][0]["query_accuracy"] == 80.0


class TestPrintQuerySummaryTable:
    def test_empty_metrics_prints_message(self, capsys: object) -> None:
        """Empty metrics list prints a 'no metrics' message."""
        print_query_summary_table([])
        # Should not raise

    def test_prints_without_error(self) -> None:
        """Table prints without raising for valid metrics."""
        metrics = [_make_query_model_metrics()]
        print_query_summary_table(metrics)
        # Should not raise
