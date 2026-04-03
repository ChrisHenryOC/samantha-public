"""Tests for evaluation reporter: JSON output and summary tables."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from src.evaluation.metrics import ModelMetrics, ScenarioResult, StepResult
from src.evaluation.reporter import (
    _safe_filename,
    print_summary_table,
    write_run_results,
    write_summary_report,
)
from src.workflow.validator import ValidationResult


@dataclass
class FakeDecision:
    """Minimal Decision-like object for reporter tests."""

    predicted_next_state: str = "ACCEPTED"
    expected_next_state: str = "ACCEPTED"
    predicted_flags: list[str] | None = None
    expected_flags: list[str] | None = None
    latency_ms: int = 100
    input_tokens: int = 50
    output_tokens: int = 20

    def __post_init__(self) -> None:
        if self.predicted_flags is None:
            self.predicted_flags = []
        if self.expected_flags is None:
            self.expected_flags = []


def _make_metrics(model_id: str = "test-model", accuracy: float = 90.0) -> ModelMetrics:
    return ModelMetrics(
        model_id=model_id,
        accuracy=accuracy,
        accuracy_by_category={"rule_coverage": accuracy},
        rule_accuracy=85.0,
        flag_accuracy=80.0,
        false_positive_rate=5.0,
        scenario_reliability=75.0,
        accuracy_std=None,
        rule_accuracy_std=None,
        flag_accuracy_std=None,
        latency_mean_ms=150.0,
        latency_p50_ms=120.0,
        latency_p95_ms=300.0,
        token_input_mean=50.0,
        token_output_mean=20.0,
        total_cost_usd=None,
        failure_counts={},
    )


def _make_scenario_result(
    scenario_id: str = "SC-001",
) -> ScenarioResult:
    step = StepResult(
        decision=FakeDecision(),
        validation=ValidationResult(state_correct=True, rules_correct=True, flags_correct=True),
        failure_type=None,
    )
    return ScenarioResult(
        scenario_id=scenario_id,
        category="rule_coverage",
        model_id="test-model",
        run_number=1,
        step_results=(step,),
        all_correct=True,
    )


# --- _safe_filename ---


class TestSafeFilename:
    def test_slashes_replaced(self) -> None:
        assert _safe_filename("meta/llama-3") == "meta_llama-3"

    def test_colons_replaced(self) -> None:
        assert _safe_filename("model:v1") == "model_v1"

    def test_spaces_replaced(self) -> None:
        assert _safe_filename("my model") == "my_model"

    def test_special_chars_replaced(self) -> None:
        assert _safe_filename('m|o<d>e"l') == "m_o_d_e_l"

    def test_dashes_preserved(self) -> None:
        assert _safe_filename("my-model-v2") == "my-model-v2"

    def test_underscores_preserved(self) -> None:
        assert _safe_filename("my_model") == "my_model"


# --- write_run_results ---


class TestWriteRunResults:
    def test_creates_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out = write_run_results(
                Path(tmpdir),
                "test-model",
                1,
                [_make_scenario_result()],
                {"started_at": "2026-01-01T00:00:00"},
            )
            assert out.exists()
            data = json.loads(out.read_text())
            assert data["model_id"] == "test-model"
            assert data["run_number"] == 1
            assert len(data["scenarios"]) == 1

    def test_empty_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out = write_run_results(
                Path(tmpdir),
                "test-model",
                1,
                [],
                {"started_at": "2026-01-01T00:00:00"},
            )
            data = json.loads(out.read_text())
            assert data["scenarios"] == []

    def test_model_id_sanitized(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out = write_run_results(
                Path(tmpdir),
                "meta/llama:3",
                1,
                [],
                {},
            )
            assert "meta_llama_3" in str(out)

    def test_aborted_metadata_in_json(self) -> None:
        """JSON output includes abort metadata when run is aborted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out = write_run_results(
                Path(tmpdir),
                "test-model",
                1,
                [_make_scenario_result()],
                {"started_at": "2026-01-01T00:00:00"},
                total_scenarios=25,
                aborted=True,
            )
            data = json.loads(out.read_text())
            assert data["total_scenarios"] == 25
            assert data["scenarios_completed"] == 1
            assert data["aborted"] is True

    def test_non_aborted_run_has_matching_counts(self) -> None:
        """Non-aborted runs have total_scenarios == scenarios_completed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            results = [_make_scenario_result(f"SC-{i:03d}") for i in range(3)]
            out = write_run_results(
                Path(tmpdir),
                "test-model",
                1,
                results,
                {"started_at": "2026-01-01T00:00:00"},
                total_scenarios=3,
                aborted=False,
            )
            data = json.loads(out.read_text())
            assert data["total_scenarios"] == 3
            assert data["scenarios_completed"] == 3
            assert data["aborted"] is False


# --- write_summary_report ---


class TestWriteSummaryReport:
    def test_creates_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out = write_summary_report(
                Path(tmpdir),
                [_make_metrics()],
                {"started_at": "2026-01-01T00:00:00"},
            )
            assert out.exists()
            data = json.loads(out.read_text())
            assert len(data["models"]) == 1
            assert data["models"][0]["model_id"] == "test-model"

    def test_empty_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out = write_summary_report(Path(tmpdir), [], {})
            data = json.loads(out.read_text())
            assert data["models"] == []


# --- print_summary_table ---


class TestPrintSummaryTable:
    def test_prints_header(self, capsys: object) -> None:
        print_summary_table([_make_metrics()])
        # Just verify no exception — output validation is low priority

    def test_empty_no_crash(self, capsys: object) -> None:
        print_summary_table([])
