"""Tests for src.evaluation.analysis — routing baseline analysis and reporting."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.evaluation.analysis import (
    compute_hardest_scenarios,
    compute_per_category_comparison,
    compute_rule_selection_matrix,
    filter_aborted_runs,
    format_all_rule_matrices,
    format_category_matrix,
    format_executive_summary,
    format_failure_breakdown,
    format_hardest_scenarios,
    format_latency_table,
    format_non_viable_section,
    format_rule_selection_matrix,
    format_summary_table,
    format_variance_table,
    generate_report,
    identify_non_viable_models,
    load_run_results,
    load_summary,
    main,
    short_name,
)

# ---------------------------------------------------------------------------
# Fixtures — inline JSON dicts
# ---------------------------------------------------------------------------


def _make_step(
    *,
    state_correct: bool = True,
    rules_correct: bool = True,
    flags_correct: bool = True,
    failure_type: str | None = None,
    latency_ms: int = 100,
) -> dict:
    return {
        "state_correct": state_correct,
        "rules_correct": rules_correct,
        "flags_correct": flags_correct,
        "failure_type": failure_type,
        "latency_ms": latency_ms,
        "predicted_state": "ACCEPTED" if state_correct else "WRONG",
        "expected_state": "ACCEPTED",
    }


def _make_scenario(
    scenario_id: str = "SC-001",
    category: str = "rule_coverage",
    steps: list[dict] | None = None,
) -> dict:
    steps = steps or [_make_step()]
    all_correct = all(s["state_correct"] for s in steps)
    return {
        "scenario_id": scenario_id,
        "category": category,
        "all_correct": all_correct,
        "steps": steps,
    }


def _make_run(
    model_id: str = "test-vendor/test-model",
    run_number: int = 1,
    scenarios: list[dict] | None = None,
    *,
    aborted: bool = False,
) -> dict:
    return {
        "model_id": model_id,
        "run_number": run_number,
        "timestamps": {"started_at": "2026-01-01T00:00:00", "completed_at": "2026-01-01T01:00:00"},
        "aborted": aborted,
        "scenarios": scenarios or [_make_scenario()],
    }


def _make_model_summary(
    model_id: str = "test-vendor/test-model",
    accuracy: float = 80.0,
    rule_accuracy: float = 90.0,
    flag_accuracy: float = 95.0,
    false_positive_rate: float = 5.0,
    scenario_reliability: float = 50.0,
    accuracy_std: float | None = 1.5,
    rule_accuracy_std: float | None = 0.5,
    flag_accuracy_std: float | None = 0.3,
    failure_counts: dict[str, int] | None = None,
    accuracy_by_category: dict[str, float] | None = None,
    latency_mean_ms: float = 1000.0,
    latency_p50_ms: float = 900.0,
    latency_p95_ms: float = 2000.0,
    token_input_mean: float = 1500.0,
    token_output_mean: float = 100.0,
) -> dict:
    if failure_counts is None:
        failure_counts = {"wrong_state": 10}
    if accuracy_by_category is None:
        accuracy_by_category = {"rule_coverage": 80.0, "multi_rule": 70.0}
    return {
        "model_id": model_id,
        "accuracy": accuracy,
        "rule_accuracy": rule_accuracy,
        "flag_accuracy": flag_accuracy,
        "false_positive_rate": false_positive_rate,
        "scenario_reliability": scenario_reliability,
        "accuracy_std": accuracy_std,
        "rule_accuracy_std": rule_accuracy_std,
        "flag_accuracy_std": flag_accuracy_std,
        "failure_counts": failure_counts,
        "accuracy_by_category": accuracy_by_category,
        "latency_mean_ms": latency_mean_ms,
        "latency_p50_ms": latency_p50_ms,
        "latency_p95_ms": latency_p95_ms,
        "token_input_mean": token_input_mean,
        "token_output_mean": token_output_mean,
        "total_cost_usd": None,
    }


# ---------------------------------------------------------------------------
# Tests: short_name
# ---------------------------------------------------------------------------


class TestShortName:
    def test_with_vendor_prefix(self) -> None:
        assert short_name("meta-llama/llama-3.1-8b-instruct") == "llama-3.1-8b-instruct"

    def test_without_prefix(self) -> None:
        assert short_name("claude-opus-4-6-20250514") == "claude-opus-4-6-20250514"

    def test_multiple_slashes(self) -> None:
        assert short_name("org/sub/model") == "model"


# ---------------------------------------------------------------------------
# Tests: data loading
# ---------------------------------------------------------------------------


class TestLoadSummary:
    def test_valid_load(self, tmp_path: Path) -> None:
        summary = {"timestamps": {}, "models": [{"model_id": "test"}]}
        (tmp_path / "summary.json").write_text(json.dumps(summary))
        result = load_summary(tmp_path)
        assert result["models"][0]["model_id"] == "test"

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_summary(tmp_path)

    def test_malformed_json(self, tmp_path: Path) -> None:
        (tmp_path / "summary.json").write_text("{bad json")
        with pytest.raises(json.JSONDecodeError):
            load_summary(tmp_path)


class TestLoadRunResults:
    def test_loads_runs_by_model(self, tmp_path: Path) -> None:
        model_dir = tmp_path / "test_model"
        model_dir.mkdir()
        run1 = _make_run(model_id="vendor/test-model", run_number=1)
        run2 = _make_run(model_id="vendor/test-model", run_number=2)
        (model_dir / "run_1.json").write_text(json.dumps(run1))
        (model_dir / "run_2.json").write_text(json.dumps(run2))

        result = load_run_results(tmp_path)
        assert "vendor/test-model" in result
        assert len(result["vendor/test-model"]) == 2

    def test_ignores_non_directories(self, tmp_path: Path) -> None:
        (tmp_path / "summary.json").write_text("{}")
        result = load_run_results(tmp_path)
        assert result == {}

    def test_ignores_dirs_without_run_files(self, tmp_path: Path) -> None:
        (tmp_path / "empty_dir").mkdir()
        result = load_run_results(tmp_path)
        assert result == {}

    def test_multiple_models(self, tmp_path: Path) -> None:
        for name, mid in [("model_a", "v/a"), ("model_b", "v/b")]:
            d = tmp_path / name
            d.mkdir()
            (d / "run_1.json").write_text(json.dumps(_make_run(model_id=mid)))

        result = load_run_results(tmp_path)
        assert len(result) == 2
        assert "v/a" in result
        assert "v/b" in result


# ---------------------------------------------------------------------------
# Tests: analysis functions
# ---------------------------------------------------------------------------


class TestComputeRuleSelectionMatrix:
    def test_normal(self) -> None:
        steps = [
            _make_step(state_correct=True, rules_correct=True),
            _make_step(state_correct=True, rules_correct=False),
            _make_step(state_correct=False, rules_correct=True),
            _make_step(state_correct=False, rules_correct=False),
        ]
        matrix = compute_rule_selection_matrix(steps)
        assert matrix["right_rule_right_state"] == 1
        assert matrix["right_rule_wrong_state"] == 1
        assert matrix["wrong_rule_right_state"] == 1
        assert matrix["wrong_rule_wrong_state"] == 1

    def test_all_correct(self) -> None:
        steps = [_make_step() for _ in range(5)]
        matrix = compute_rule_selection_matrix(steps)
        assert matrix["right_rule_right_state"] == 5
        assert matrix["right_rule_wrong_state"] == 0
        assert matrix["wrong_rule_right_state"] == 0
        assert matrix["wrong_rule_wrong_state"] == 0

    def test_empty(self) -> None:
        matrix = compute_rule_selection_matrix([])
        assert all(v == 0 for v in matrix.values())


class TestComputeHardestScenarios:
    def test_returns_sorted_ascending(self) -> None:
        run_data = {
            "model_a": [
                _make_run(
                    model_id="model_a",
                    scenarios=[
                        _make_scenario("SC-001", steps=[_make_step(state_correct=True)]),
                        _make_scenario("SC-002", steps=[_make_step(state_correct=False)]),
                        _make_scenario(
                            "SC-003",
                            steps=[
                                _make_step(state_correct=True),
                                _make_step(state_correct=False),
                            ],
                        ),
                    ],
                )
            ],
        }
        result = compute_hardest_scenarios(run_data, top_n=10)
        assert result[0]["scenario_id"] == "SC-002"
        assert result[0]["accuracy"] == 0.0
        assert result[-1]["scenario_id"] == "SC-001"

    def test_top_n_limits(self) -> None:
        scenarios = [
            _make_scenario(f"SC-{i:03d}", steps=[_make_step(state_correct=False)])
            for i in range(20)
        ]
        run_data = {"m": [_make_run(model_id="m", scenarios=scenarios)]}
        result = compute_hardest_scenarios(run_data, top_n=5)
        assert len(result) == 5

    def test_aggregates_across_models(self) -> None:
        # SC-001: model_a gets it right, model_b gets it wrong → 50%
        run_data = {
            "model_a": [
                _make_run(
                    model_id="model_a",
                    scenarios=[_make_scenario("SC-001", steps=[_make_step(state_correct=True)])],
                )
            ],
            "model_b": [
                _make_run(
                    model_id="model_b",
                    scenarios=[_make_scenario("SC-001", steps=[_make_step(state_correct=False)])],
                )
            ],
        }
        result = compute_hardest_scenarios(run_data)
        assert len(result) == 1
        assert result[0]["accuracy"] == 50.0


class TestIdentifyNonViableModels:
    def test_model_with_high_structural_failures(self) -> None:
        models = [
            _make_model_summary(
                model_id="bad-model",
                failure_counts={"invalid_json": 100, "wrong_state": 10},
            ),
        ]
        result = identify_non_viable_models(models, threshold=0.5)
        assert len(result) == 1
        assert result[0]["model_id"] == "bad-model"

    def test_model_with_low_structural_failures(self) -> None:
        models = [
            _make_model_summary(
                model_id="good-model",
                failure_counts={"wrong_state": 100, "invalid_json": 2},
            ),
        ]
        result = identify_non_viable_models(models, threshold=0.5)
        assert len(result) == 0

    def test_no_failures(self) -> None:
        models = [_make_model_summary(failure_counts={})]
        result = identify_non_viable_models(models)
        assert len(result) == 0


class TestComputePerCategoryComparison:
    def test_reshapes_correctly(self) -> None:
        models = [
            _make_model_summary(
                model_id="a",
                accuracy_by_category={"cat1": 90.0, "cat2": 80.0},
            ),
            _make_model_summary(
                model_id="b",
                accuracy_by_category={"cat1": 70.0, "cat2": 60.0},
            ),
        ]
        result = compute_per_category_comparison(models)
        assert result["cat1"]["a"] == 90.0
        assert result["cat1"]["b"] == 70.0
        assert result["cat2"]["a"] == 80.0

    def test_empty(self) -> None:
        assert compute_per_category_comparison([]) == {}


# ---------------------------------------------------------------------------
# Tests: formatting functions
# ---------------------------------------------------------------------------


class TestFormatSummaryTable:
    def test_contains_markdown_table(self) -> None:
        models = [_make_model_summary()]
        result = format_summary_table(models)
        assert "| Model |" in result
        assert "test-model" in result
        assert "80.0" in result

    def test_preserves_input_order(self) -> None:
        models = [
            _make_model_summary(model_id="high", accuracy=90.0),
            _make_model_summary(model_id="low", accuracy=50.0),
        ]
        result = format_summary_table(models)
        high_pos = result.index("high")
        low_pos = result.index("low")
        assert high_pos < low_pos


class TestFormatVarianceTable:
    def test_includes_local_models(self) -> None:
        models = [_make_model_summary(accuracy_std=2.0)]
        result = format_variance_table(models)
        assert "±2.0" in result

    def test_empty_when_no_local(self) -> None:
        models = [_make_model_summary(accuracy_std=None)]
        result = format_variance_table(models)
        assert result == ""


class TestFormatCategoryMatrix:
    def test_contains_categories(self) -> None:
        models = [
            _make_model_summary(accuracy_by_category={"cat_a": 85.0, "cat_b": 75.0}),
        ]
        result = format_category_matrix(models)
        assert "cat_a" in result
        assert "cat_b" in result

    def test_empty_when_no_categories(self) -> None:
        models = [_make_model_summary(accuracy_by_category={})]
        result = format_category_matrix(models)
        assert result == ""


class TestFormatAllRuleMatrices:
    def test_generates_per_model(self) -> None:
        run_data = {
            "v/model-a": [_make_run(model_id="v/model-a")],
            "v/model-b": [_make_run(model_id="v/model-b")],
        }
        result = format_all_rule_matrices(run_data)
        assert "model-a" in result
        assert "model-b" in result
        assert "Right Rule" in result


class TestFormatFailureBreakdown:
    def test_contains_failure_types(self) -> None:
        models = [
            _make_model_summary(failure_counts={"wrong_state": 50, "invalid_json": 10}),
        ]
        result = format_failure_breakdown(models)
        assert "wrong_state" in result
        assert "invalid_json" in result
        assert "| 60 |" in result  # total

    def test_empty_when_no_failures(self) -> None:
        models = [_make_model_summary(failure_counts={})]
        result = format_failure_breakdown(models)
        assert result == ""


class TestFormatHardestScenarios:
    def test_contains_scenario_data(self) -> None:
        scenarios = [
            {
                "scenario_id": "SC-001",
                "category": "multi_rule",
                "accuracy": 10.0,
                "total_evals": 50,
            },
        ]
        result = format_hardest_scenarios(scenarios)
        assert "SC-001" in result
        assert "multi_rule" in result
        assert "10.0" in result


class TestFormatNonViableSection:
    def test_with_non_viable(self) -> None:
        nv = [
            {
                "model_id": "bad/model",
                "structural_failures": 100,
                "total_failures": 120,
                "structural_fraction": 0.833,
                "accuracy": 12.0,
            },
        ]
        result = format_non_viable_section(nv)
        assert "model" in result
        assert "100" in result

    def test_without_non_viable(self) -> None:
        result = format_non_viable_section([])
        assert "No models exceeded" in result


class TestFormatLatencyTable:
    def test_contains_latency_data(self) -> None:
        models = [_make_model_summary(latency_mean_ms=1234.0)]
        result = format_latency_table(models)
        assert "1234" in result
        assert "p50" in result


class TestFormatExecutiveSummary:
    def test_contains_key_info(self) -> None:
        models = [
            _make_model_summary(model_id="best", accuracy=95.0, scenario_reliability=60.0),
            _make_model_summary(model_id="worst", accuracy=30.0, scenario_reliability=5.0),
        ]
        run_data = {
            "best": [_make_run(model_id="best")],
            "worst": [_make_run(model_id="worst")],
        }
        timestamps = {"started_at": "T1", "completed_at": "T2"}
        result = format_executive_summary(models, run_data, [], timestamps)
        assert "Models evaluated" in result
        assert "best" in result
        assert "Top Performers" in result


# ---------------------------------------------------------------------------
# Tests: integration
# ---------------------------------------------------------------------------


class TestGenerateReport:
    def test_end_to_end(self, tmp_path: Path) -> None:
        # Create summary.json
        models = [
            _make_model_summary(
                model_id="v/model-a",
                accuracy=90.0,
                accuracy_by_category={"cat1": 90.0},
                failure_counts={"wrong_state": 10},
            ),
            _make_model_summary(
                model_id="v/model-b",
                accuracy=40.0,
                accuracy_by_category={"cat1": 40.0},
                failure_counts={"invalid_json": 80, "wrong_state": 5},
            ),
        ]
        summary = {
            "timestamps": {"started_at": "2026-01-01", "completed_at": "2026-01-02"},
            "models": models,
        }
        (tmp_path / "summary.json").write_text(json.dumps(summary))

        # Create run files for both models
        for name, mid in [("v_model-a", "v/model-a"), ("v_model-b", "v/model-b")]:
            model_dir = tmp_path / name
            model_dir.mkdir()
            run = _make_run(
                model_id=mid,
                scenarios=[
                    _make_scenario(
                        "SC-001",
                        "cat1",
                        [
                            _make_step(state_correct=mid == "v/model-a"),
                        ],
                    ),
                    _make_scenario(
                        "SC-002",
                        "cat1",
                        [
                            _make_step(state_correct=True),
                            _make_step(state_correct=False),
                        ],
                    ),
                ],
            )
            (model_dir / "run_1.json").write_text(json.dumps(run))

        output_path = tmp_path / "analysis.md"
        result = generate_report(tmp_path, output_path)

        assert result == output_path
        assert output_path.exists()

        content = output_path.read_text()

        # Verify all expected sections
        expected_sections = [
            "# Routing Baseline Analysis",
            "## 1. Executive Summary",
            "## 2. Model Performance Overview",
            "### 2.1 Primary Metrics",
            "### 2.2 Variance Analysis",
            "## 3. Accuracy by Category",
            "## 4. Rule Selection Diagnostics",
            "## 5. Failure Analysis",
            "### 5.1 Failure Type Breakdown",
            "### 5.2 Hardest Scenarios",
            "### 5.3 Non-Viable Models",
            "## 6. Secondary Metrics",
        ]
        for section in expected_sections:
            assert section in content, f"Missing section: {section}"

    def test_with_no_variance_models(self, tmp_path: Path) -> None:
        """Models with no std values (cloud, single run) should still render."""
        models = [
            _make_model_summary(
                model_id="cloud-model",
                accuracy_std=None,
                rule_accuracy_std=None,
                flag_accuracy_std=None,
            ),
        ]
        summary = {"timestamps": {}, "models": models}
        (tmp_path / "summary.json").write_text(json.dumps(summary))

        model_dir = tmp_path / "cloud-model"
        model_dir.mkdir()
        (model_dir / "run_1.json").write_text(json.dumps(_make_run(model_id="cloud-model")))

        output_path = tmp_path / "report.md"
        generate_report(tmp_path, output_path)
        content = output_path.read_text()
        # Variance table should not appear (no local models)
        assert "Variance Analysis" not in content

    def test_missing_models_key(self, tmp_path: Path) -> None:
        """generate_report raises ValueError when summary has no models."""
        (tmp_path / "summary.json").write_text(json.dumps({"timestamps": {}}))
        with pytest.raises(ValueError, match="No 'models' key"):
            generate_report(tmp_path, tmp_path / "out.md")

    def test_aborted_runs_excluded_from_report(self, tmp_path: Path) -> None:
        """Aborted runs should not affect executive summary counts."""
        models = [_make_model_summary(model_id="v/model-a")]
        summary = {"timestamps": {}, "models": models}
        (tmp_path / "summary.json").write_text(json.dumps(summary))

        model_dir = tmp_path / "v_model-a"
        model_dir.mkdir()
        # Run 1: normal, 1 scenario with 1 step
        (model_dir / "run_1.json").write_text(
            json.dumps(
                _make_run(
                    model_id="v/model-a",
                    run_number=1,
                    scenarios=[_make_scenario("SC-001", steps=[_make_step()])],
                )
            )
        )
        # Run 2: aborted, should be excluded
        (model_dir / "run_2.json").write_text(
            json.dumps(
                _make_run(
                    model_id="v/model-a",
                    run_number=2,
                    scenarios=[_make_scenario("SC-001", steps=[_make_step(state_correct=False)])],
                    aborted=True,
                )
            )
        )

        output_path = tmp_path / "analysis.md"
        generate_report(tmp_path, output_path)
        content = output_path.read_text()
        # Only 1 run should be counted (the non-aborted one)
        assert "**Total runs:** 1" in content
        # Only 1 decision from the non-aborted run
        assert "**Total decisions:** 1" in content


# ---------------------------------------------------------------------------
# Tests: load_run_results error handling (#10, #8)
# ---------------------------------------------------------------------------


class TestLoadRunResultsErrors:
    def test_corrupt_json_in_run_file(self, tmp_path: Path) -> None:
        model_dir = tmp_path / "test_model"
        model_dir.mkdir()
        (model_dir / "run_1.json").write_text("{bad json")
        with pytest.raises(json.JSONDecodeError):
            load_run_results(tmp_path)

    def test_run_file_missing_model_id(self, tmp_path: Path) -> None:
        model_dir = tmp_path / "test_model"
        model_dir.mkdir()
        (model_dir / "run_1.json").write_text(json.dumps({"run_number": 1}))
        with pytest.raises(KeyError):
            load_run_results(tmp_path)

    def test_inconsistent_model_ids(self, tmp_path: Path) -> None:
        model_dir = tmp_path / "test_model"
        model_dir.mkdir()
        (model_dir / "run_1.json").write_text(json.dumps(_make_run(model_id="vendor/model-a")))
        (model_dir / "run_2.json").write_text(json.dumps(_make_run(model_id="vendor/model-b")))
        with pytest.raises(ValueError, match="Inconsistent model_id"):
            load_run_results(tmp_path)


# ---------------------------------------------------------------------------
# Tests: edge cases (#11, #12)
# ---------------------------------------------------------------------------


class TestFormatRuleSelectionMatrixEdgeCases:
    def test_zero_total(self) -> None:
        matrix = {
            "right_rule_right_state": 0,
            "right_rule_wrong_state": 0,
            "wrong_rule_right_state": 0,
            "wrong_rule_wrong_state": 0,
        }
        result = format_rule_selection_matrix("test/model", matrix, total=0)
        assert "0.0%" in result
        assert "| 0 " in result


class TestComputeHardestScenariosEdgeCases:
    def test_scenario_with_zero_steps(self) -> None:
        # Build scenario dict directly to avoid _make_scenario's default step
        scenario = {
            "scenario_id": "SC-001",
            "category": "rule_coverage",
            "all_correct": True,
            "steps": [],
        }
        run_data = {
            "m": [{"model_id": "m", "run_number": 1, "scenarios": [scenario]}],
        }
        result = compute_hardest_scenarios(run_data)
        assert len(result) == 1
        assert result[0]["accuracy"] == 0.0
        assert result[0]["total_evals"] == 0


# ---------------------------------------------------------------------------
# Tests: filter_aborted_runs (#121)
# ---------------------------------------------------------------------------


class TestFilterAbortedRuns:
    def test_removes_aborted_runs(self) -> None:
        run_data = {
            "model_a": [
                _make_run(model_id="model_a", run_number=1),
                _make_run(model_id="model_a", run_number=2, aborted=True),
            ],
        }
        result = filter_aborted_runs(run_data)
        assert len(result["model_a"]) == 1
        assert result["model_a"][0]["run_number"] == 1

    def test_keeps_all_when_none_aborted(self) -> None:
        run_data = {
            "model_a": [
                _make_run(model_id="model_a", run_number=1),
                _make_run(model_id="model_a", run_number=2),
            ],
        }
        result = filter_aborted_runs(run_data)
        assert len(result["model_a"]) == 2

    def test_omits_model_when_all_aborted(self) -> None:
        run_data = {
            "model_a": [
                _make_run(model_id="model_a", run_number=1, aborted=True),
            ],
            "model_b": [
                _make_run(model_id="model_b", run_number=1),
            ],
        }
        result = filter_aborted_runs(run_data)
        assert "model_a" not in result
        assert "model_b" in result

    def test_missing_aborted_field_treated_as_false(self) -> None:
        """Runs without the 'aborted' key are treated as non-aborted."""
        run_data = {
            "model_a": [{"model_id": "model_a", "run_number": 1, "scenarios": []}],
        }
        result = filter_aborted_runs(run_data)
        assert len(result["model_a"]) == 1

    def test_empty_input(self) -> None:
        assert filter_aborted_runs({}) == {}

    def test_aborted_runs_excluded_from_hardest_scenarios(self) -> None:
        """Aborted runs should not contribute to scenario accuracy."""
        # model_a: non-aborted run with SC-001 correct
        # model_a: aborted run with SC-001 wrong (should be excluded)
        run_data = {
            "model_a": [
                _make_run(
                    model_id="model_a",
                    run_number=1,
                    scenarios=[_make_scenario("SC-001", steps=[_make_step(state_correct=True)])],
                ),
                _make_run(
                    model_id="model_a",
                    run_number=2,
                    scenarios=[_make_scenario("SC-001", steps=[_make_step(state_correct=False)])],
                    aborted=True,
                ),
            ],
        }
        # Without filtering: SC-001 accuracy = 50% (1/2 steps correct)
        unfiltered = compute_hardest_scenarios(run_data)
        assert unfiltered[0]["accuracy"] == 50.0

        # With filtering: SC-001 accuracy = 100% (1/1 step correct)
        filtered = filter_aborted_runs(run_data)
        result = compute_hardest_scenarios(filtered)
        assert result[0]["accuracy"] == 100.0


# ---------------------------------------------------------------------------
# Tests: CLI main() (#5)
# ---------------------------------------------------------------------------


class TestMain:
    def test_default_arguments(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        summary = {
            "timestamps": {},
            "models": [_make_model_summary()],
        }
        (tmp_path / "summary.json").write_text(json.dumps(summary))
        model_dir = tmp_path / "test-model"
        model_dir.mkdir()
        (model_dir / "run_1.json").write_text(json.dumps(_make_run()))
        output = tmp_path / "report.md"
        main(["--results-dir", str(tmp_path), "--output", str(output)])
        assert output.exists()
        captured = capsys.readouterr()
        assert "Report written to" in captured.out

    def test_custom_top_n(self, tmp_path: Path) -> None:
        summary = {
            "timestamps": {},
            "models": [_make_model_summary()],
        }
        (tmp_path / "summary.json").write_text(json.dumps(summary))
        model_dir = tmp_path / "test-model"
        model_dir.mkdir()
        (model_dir / "run_1.json").write_text(json.dumps(_make_run()))
        output = tmp_path / "report.md"
        main(["--results-dir", str(tmp_path), "--output", str(output), "--top-n", "5"])
        assert output.exists()

    def test_missing_results_dir(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent"
        with pytest.raises(FileNotFoundError):
            main(["--results-dir", str(missing), "--output", str(tmp_path / "out.md")])
