"""Red-team tests for src/evaluation/analysis.py and query_analysis.py — robustness."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.evaluation.analysis import (
    compute_hardest_scenarios,
    compute_per_category_comparison,
    compute_rule_selection_matrix,
    filter_aborted_runs,
    format_executive_summary,
    format_failure_breakdown,
    format_hardest_scenarios,
    format_latency_table,
    format_non_viable_section,
    format_rule_selection_matrix,
    format_summary_table,
    format_variance_table,
    identify_non_viable_models,
    load_run_files_by_model,
)
from src.evaluation.query_analysis import (
    compute_answer_type_model_matrix,
    compute_hardest_query_scenarios,
    compute_tier_model_matrix,
    identify_query_non_viable_models,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_run_file(
    model_dir: Path,
    filename: str,
    data: dict[str, Any],
) -> Path:
    model_dir.mkdir(parents=True, exist_ok=True)
    p = model_dir / filename
    p.write_text(json.dumps(data))
    return p


# ---------------------------------------------------------------------------
# load_run_files_by_model robustness
# ---------------------------------------------------------------------------


class TestLoadRunFilesByModelRobustness:
    """Adversarial filesystem layouts for load_run_files_by_model."""

    def test_empty_dir(self, tmp_path: Path) -> None:
        result = load_run_files_by_model(tmp_path)
        assert result == {}

    def test_no_run_files(self, tmp_path: Path) -> None:
        model_dir = tmp_path / "model-a"
        model_dir.mkdir()
        (model_dir / "notes.txt").write_text("not a run file")
        result = load_run_files_by_model(tmp_path)
        assert result == {}

    def test_missing_model_id_raises(self, tmp_path: Path) -> None:
        model_dir = tmp_path / "model-a"
        _write_run_file(model_dir, "run_1.json", {"scenarios": []})
        with pytest.raises(KeyError, match="Missing 'model_id'"):
            load_run_files_by_model(tmp_path)

    def test_inconsistent_model_id_raises(self, tmp_path: Path) -> None:
        model_dir = tmp_path / "model-a"
        _write_run_file(model_dir, "run_1.json", {"model_id": "model-a", "scenarios": []})
        _write_run_file(model_dir, "run_2.json", {"model_id": "model-b", "scenarios": []})
        with pytest.raises(ValueError, match="Inconsistent model_id"):
            load_run_files_by_model(tmp_path)

    def test_malformed_json_raises(self, tmp_path: Path) -> None:
        model_dir = tmp_path / "model-a"
        model_dir.mkdir()
        (model_dir / "run_1.json").write_text("{not valid json")
        with pytest.raises(json.JSONDecodeError):
            load_run_files_by_model(tmp_path)

    def test_non_dir_files_ignored(self, tmp_path: Path) -> None:
        (tmp_path / "stray_file.txt").write_text("hello")
        model_dir = tmp_path / "model-a"
        _write_run_file(model_dir, "run_1.json", {"model_id": "a", "scenarios": []})
        result = load_run_files_by_model(tmp_path)
        assert "a" in result

    def test_single_run(self, tmp_path: Path) -> None:
        model_dir = tmp_path / "model-a"
        _write_run_file(model_dir, "run_1.json", {"model_id": "a", "scenarios": []})
        result = load_run_files_by_model(tmp_path)
        assert len(result["a"]) == 1

    def test_multiple_dirs(self, tmp_path: Path) -> None:
        for name in ("model-a", "model-b"):
            d = tmp_path / name
            _write_run_file(d, "run_1.json", {"model_id": name, "scenarios": []})
        result = load_run_files_by_model(tmp_path)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# filter_aborted_runs
# ---------------------------------------------------------------------------


class TestFilterAbortedRuns:
    """Edge cases for aborted run filtering."""

    def test_no_aborted(self) -> None:
        data = {"m": [{"model_id": "m", "aborted": False}]}
        result = filter_aborted_runs(data)
        assert len(result["m"]) == 1

    def test_all_aborted_model_omitted(self) -> None:
        data = {"m": [{"model_id": "m", "aborted": True}]}
        result = filter_aborted_runs(data)
        assert "m" not in result

    def test_mixed(self) -> None:
        data = {
            "m": [
                {"model_id": "m", "aborted": False},
                {"model_id": "m", "aborted": True},
            ]
        }
        result = filter_aborted_runs(data)
        assert len(result["m"]) == 1

    def test_empty_input(self) -> None:
        assert filter_aborted_runs({}) == {}

    def test_missing_aborted_key_treated_as_not_aborted(self) -> None:
        data = {"m": [{"model_id": "m"}]}
        result = filter_aborted_runs(data)
        assert len(result["m"]) == 1


# ---------------------------------------------------------------------------
# compute_rule_selection_matrix
# ---------------------------------------------------------------------------


class TestComputeRuleSelectionMatrix:
    """Edge cases for the 2x2 rule-selection matrix."""

    def test_empty(self) -> None:
        matrix = compute_rule_selection_matrix([])
        assert all(v == 0 for v in matrix.values())

    def test_all_correct(self) -> None:
        steps = [{"rules_correct": True, "state_correct": True} for _ in range(3)]
        matrix = compute_rule_selection_matrix(steps)
        assert matrix["right_rule_right_state"] == 3
        assert matrix["wrong_rule_wrong_state"] == 0

    def test_all_wrong(self) -> None:
        steps = [{"rules_correct": False, "state_correct": False} for _ in range(2)]
        matrix = compute_rule_selection_matrix(steps)
        assert matrix["wrong_rule_wrong_state"] == 2

    def test_mixed_quadrants(self) -> None:
        steps = [
            {"rules_correct": True, "state_correct": True},
            {"rules_correct": True, "state_correct": False},
            {"rules_correct": False, "state_correct": True},
            {"rules_correct": False, "state_correct": False},
        ]
        matrix = compute_rule_selection_matrix(steps)
        assert matrix["right_rule_right_state"] == 1
        assert matrix["right_rule_wrong_state"] == 1
        assert matrix["wrong_rule_right_state"] == 1
        assert matrix["wrong_rule_wrong_state"] == 1


# ---------------------------------------------------------------------------
# compute_hardest_scenarios
# ---------------------------------------------------------------------------


class TestComputeHardestScenarios:
    """Edge cases for hardest scenario computation."""

    def test_empty(self) -> None:
        assert compute_hardest_scenarios({}) == []

    def test_all_correct(self) -> None:
        data = {
            "m": [
                {
                    "scenarios": [
                        {
                            "scenario_id": "S-001",
                            "category": "cat",
                            "steps": [{"state_correct": True}],
                        }
                    ]
                }
            ]
        }
        result = compute_hardest_scenarios(data)
        assert len(result) == 1
        assert result[0]["accuracy"] == 100.0

    def test_top_n_limit(self) -> None:
        data = {
            "m": [
                {
                    "scenarios": [
                        {
                            "scenario_id": f"S-{i:03d}",
                            "category": "cat",
                            "steps": [{"state_correct": False}],
                        }
                        for i in range(20)
                    ]
                }
            ]
        }
        result = compute_hardest_scenarios(data, top_n=5)
        assert len(result) == 5

    def test_zero_accuracy(self) -> None:
        data = {
            "m": [
                {
                    "scenarios": [
                        {
                            "scenario_id": "S-001",
                            "category": "cat",
                            "steps": [{"state_correct": False}],
                        }
                    ]
                }
            ]
        }
        result = compute_hardest_scenarios(data)
        assert result[0]["accuracy"] == 0.0

    def test_sorted_ascending(self) -> None:
        data = {
            "m": [
                {
                    "scenarios": [
                        {
                            "scenario_id": "S-001",
                            "category": "cat",
                            "steps": [{"state_correct": True}],
                        },
                        {
                            "scenario_id": "S-002",
                            "category": "cat",
                            "steps": [{"state_correct": False}],
                        },
                    ]
                }
            ]
        }
        result = compute_hardest_scenarios(data)
        assert result[0]["accuracy"] <= result[-1]["accuracy"]


# ---------------------------------------------------------------------------
# identify_non_viable_models
# ---------------------------------------------------------------------------


class TestIdentifyNonViableModels:
    """Edge cases for non-viable model identification."""

    def test_no_failures(self) -> None:
        models = [{"model_id": "m", "failure_counts": {}}]
        assert identify_non_viable_models(models) == []

    def test_above_threshold(self) -> None:
        models = [
            {
                "model_id": "m",
                "failure_counts": {"invalid_json": 10, "wrong_state": 2},
                "accuracy": 30.0,
            }
        ]
        result = identify_non_viable_models(models)
        assert len(result) == 1
        assert result[0]["model_id"] == "m"

    def test_at_threshold_not_non_viable(self) -> None:
        models = [
            {
                "model_id": "m",
                "failure_counts": {"invalid_json": 5, "wrong_state": 5},
                "accuracy": 50.0,
            }
        ]
        # 5/10 = 0.5, threshold is >0.5, so not non-viable
        result = identify_non_viable_models(models)
        assert result == []

    def test_missing_failure_counts_key(self) -> None:
        models = [{"model_id": "m"}]
        assert identify_non_viable_models(models) == []

    def test_zero_total_failures(self) -> None:
        models = [{"model_id": "m", "failure_counts": {}}]
        assert identify_non_viable_models(models) == []


# ---------------------------------------------------------------------------
# compute_per_category_comparison
# ---------------------------------------------------------------------------


class TestComputePerCategoryComparison:
    """Edge cases for category comparison matrix."""

    def test_empty(self) -> None:
        assert compute_per_category_comparison([]) == {}

    def test_single_model(self) -> None:
        models = [
            {
                "model_id": "m",
                "accuracy_by_category": {"accessioning": 90.0, "review": 80.0},
            }
        ]
        result = compute_per_category_comparison(models)
        assert result["accessioning"]["m"] == 90.0
        assert result["review"]["m"] == 80.0

    def test_multiple_models(self) -> None:
        models = [
            {"model_id": "a", "accuracy_by_category": {"cat": 90.0}},
            {"model_id": "b", "accuracy_by_category": {"cat": 70.0}},
        ]
        result = compute_per_category_comparison(models)
        assert result["cat"]["a"] == 90.0
        assert result["cat"]["b"] == 70.0


# ---------------------------------------------------------------------------
# Query analysis robustness
# ---------------------------------------------------------------------------


class TestQueryAnalysisRobustness:
    """Edge cases for query_analysis functions."""

    def test_empty_hardest_scenarios(self) -> None:
        assert compute_hardest_query_scenarios({}) == []

    def test_empty_non_viable(self) -> None:
        assert identify_query_non_viable_models([]) == []

    def test_empty_tier_matrix(self) -> None:
        assert compute_tier_model_matrix([]) == {}

    def test_missing_tier_data(self) -> None:
        models = [{"model_id": "m"}]
        result = compute_tier_model_matrix(models)
        assert result == {}

    def test_missing_answer_type_data(self) -> None:
        models = [{"model_id": "m"}]
        result = compute_answer_type_model_matrix(models)
        assert result == {}


# ---------------------------------------------------------------------------
# Formatting function edge cases (#5)
# ---------------------------------------------------------------------------


def _model_summary(
    model_id: str = "test-model",
    accuracy: float = 80.0,
    **kw: Any,
) -> dict[str, Any]:
    """Build a minimal model summary dict for formatting functions."""
    return {
        "model_id": model_id,
        "accuracy": accuracy,
        "rule_accuracy": kw.get("rule_accuracy", accuracy),
        "flag_accuracy": kw.get("flag_accuracy", accuracy),
        "false_positive_rate": kw.get("false_positive_rate", 5.0),
        "scenario_reliability": kw.get("scenario_reliability", 60.0),
        "accuracy_std": kw.get("accuracy_std"),
        "rule_accuracy_std": kw.get("rule_accuracy_std"),
        "flag_accuracy_std": kw.get("flag_accuracy_std"),
        "accuracy_by_category": kw.get(
            "accuracy_by_category",
            {},
        ),
        "failure_counts": kw.get("failure_counts", {}),
        "latency_mean_ms": kw.get("latency_mean_ms", 500.0),
        "latency_p50_ms": kw.get("latency_p50_ms", 400.0),
        "latency_p95_ms": kw.get("latency_p95_ms", 900.0),
        "token_input_mean": kw.get("token_input_mean", 1000.0),
        "token_output_mean": kw.get("token_output_mean", 100.0),
    }


class TestFormatSummaryTableEdgeCases:
    """Red-team tests for format_summary_table."""

    def test_empty_models(self) -> None:
        text = format_summary_table([])
        assert "Model" in text  # header still present
        assert text.count("|") > 0

    def test_with_std(self) -> None:
        m = _model_summary(accuracy_std=2.5)
        text = format_summary_table([m])
        assert "±2.5" in text

    def test_without_std(self) -> None:
        m = _model_summary(accuracy_std=None)
        text = format_summary_table([m])
        assert "±" not in text


class TestFormatVarianceTableEdgeCases:
    """Red-team tests for format_variance_table."""

    def test_no_local_models_returns_empty(self) -> None:
        m = _model_summary(accuracy_std=None)
        assert format_variance_table([m]) == ""

    def test_with_local_models(self) -> None:
        m = _model_summary(
            accuracy_std=1.5,
            rule_accuracy_std=1.0,
            flag_accuracy_std=0.5,
        )
        text = format_variance_table([m])
        assert "Variance" in text
        assert "±1.5" in text

    def test_none_substd_treated_as_zero(self) -> None:
        m = _model_summary(
            accuracy_std=1.0,
            rule_accuracy_std=None,
            flag_accuracy_std=None,
        )
        text = format_variance_table([m])
        assert "±0.0" in text


class TestFormatRuleSelectionMatrixEdgeCases:
    """Red-team tests for format_rule_selection_matrix."""

    def test_total_zero_no_division_error(self) -> None:
        matrix = {
            "right_rule_right_state": 0,
            "right_rule_wrong_state": 0,
            "wrong_rule_right_state": 0,
            "wrong_rule_wrong_state": 0,
        }
        text = format_rule_selection_matrix("m", matrix, total=0)
        assert "0.0%" in text

    def test_all_correct(self) -> None:
        matrix = {
            "right_rule_right_state": 10,
            "right_rule_wrong_state": 0,
            "wrong_rule_right_state": 0,
            "wrong_rule_wrong_state": 0,
        }
        text = format_rule_selection_matrix("m", matrix, total=10)
        assert "100.0%" in text


class TestFormatFailureBreakdownEdgeCases:
    """Red-team tests for format_failure_breakdown."""

    def test_no_failures_returns_empty(self) -> None:
        m = _model_summary(failure_counts={})
        assert format_failure_breakdown([m]) == ""

    def test_with_failures(self) -> None:
        m = _model_summary(
            failure_counts={"wrong_state": 3, "invalid_json": 1},
        )
        text = format_failure_breakdown([m])
        assert "wrong_state" in text
        assert "invalid_json" in text


class TestFormatHardestScenariosEdgeCases:
    """Red-team tests for format_hardest_scenarios."""

    def test_empty_list(self) -> None:
        text = format_hardest_scenarios([])
        assert "Hardest" in text

    def test_with_scenarios(self) -> None:
        scenarios = [
            {
                "scenario_id": "S-001",
                "category": "accessioning",
                "accuracy": 25.0,
                "total_evals": 10,
            }
        ]
        text = format_hardest_scenarios(scenarios)
        assert "S-001" in text
        assert "25.0" in text


class TestFormatNonViableSectionEdgeCases:
    """Red-team tests for format_non_viable_section."""

    def test_no_non_viable(self) -> None:
        text = format_non_viable_section([])
        assert "No models exceeded" in text

    def test_with_non_viable(self) -> None:
        nv = [
            {
                "model_id": "bad-model",
                "structural_failures": 20,
                "total_failures": 30,
                "structural_fraction": 0.667,
                "accuracy": 30.0,
            }
        ]
        text = format_non_viable_section(nv)
        assert "bad-model" in text
        assert "66.7%" in text


class TestFormatLatencyTableEdgeCases:
    """Red-team tests for format_latency_table."""

    def test_empty_models(self) -> None:
        text = format_latency_table([])
        assert "Latency" in text

    def test_with_models(self) -> None:
        m = _model_summary(
            latency_mean_ms=250.0,
            latency_p50_ms=200.0,
            latency_p95_ms=500.0,
            token_input_mean=800.0,
            token_output_mean=80.0,
        )
        text = format_latency_table([m])
        assert "250" in text
        assert "800" in text


class TestFormatExecutiveSummaryEdgeCases:
    """Red-team tests for format_executive_summary."""

    def test_empty_models_and_runs(self) -> None:
        text = format_executive_summary(
            [],
            {},
            [],
            {"started_at": "N/A", "completed_at": "N/A"},
        )
        assert "Models evaluated:** 0" in text

    def test_with_non_viable(self) -> None:
        nv = [
            {
                "model_id": "bad",
                "structural_failures": 10,
                "structural_fraction": 0.8,
                "accuracy": 20.0,
            }
        ]
        text = format_executive_summary(
            [_model_summary()],
            {},
            nv,
            {"started_at": "2025-01-01", "completed_at": "2025-01-02"},
        )
        assert "Non-Viable" in text
        assert "bad" in text
