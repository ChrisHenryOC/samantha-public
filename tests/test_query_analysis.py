"""Tests for src.evaluation.query_analysis — query baseline analysis and reporting."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.evaluation.query_analysis import (
    compute_answer_type_model_matrix,
    compute_hardest_query_scenarios,
    compute_run_overview,
    compute_tier_model_matrix,
    format_answer_type_matrix,
    format_hardest_query_scenarios,
    format_query_executive_summary,
    format_query_failure_breakdown,
    format_query_latency_table,
    format_query_non_viable_section,
    format_query_summary_table,
    format_query_variance_table,
    format_tier_matrix,
    generate_query_report,
    identify_query_non_viable_models,
    load_query_run_results,
    load_query_summary,
    main,
)

# ---------------------------------------------------------------------------
# Fixtures — inline JSON dicts
# ---------------------------------------------------------------------------


def _make_query_scenario(
    scenario_id: str = "QR-001",
    tier: int = 1,
    answer_type: str = "order_list",
    all_correct: bool = True,
    precision: float = 1.0,
    recall: float = 1.0,
    f1: float = 1.0,
    failure_type: str | None = None,
    latency_ms: int = 2000,
) -> dict[str, Any]:
    return {
        "scenario_id": scenario_id,
        "tier": tier,
        "answer_type": answer_type,
        "all_correct": all_correct,
        "order_ids_correct": all_correct,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "failure_type": failure_type,
        "latency_ms": latency_ms,
    }


def _make_query_run(
    model_id: str = "test-vendor/test-model",
    run_number: int = 1,
    scenarios: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "model_id": model_id,
        "run_number": run_number,
        "timestamps": {
            "started_at": "2026-01-01T00:00:00",
            "completed_at": "2026-01-01T01:00:00",
        },
        "total_scenarios": 27,
        "scenarios_completed": 27,
        "aborted": False,
        "scenarios": scenarios if scenarios is not None else [_make_query_scenario()],
    }


def _make_query_model_summary(
    model_id: str = "test-vendor/test-model",
    query_accuracy: float = 80.0,
    mean_precision: float = 0.9,
    mean_recall: float = 0.85,
    mean_f1: float = 0.87,
    scenario_reliability: float = 80.0,
    accuracy_std: float | None = None,
    failure_counts: dict[str, int] | None = None,
    query_accuracy_by_tier: dict[str, float] | None = None,
    query_accuracy_by_answer_type: dict[str, float] | None = None,
    latency_mean_ms: float = 3000.0,
    latency_p50_ms: float = 2500.0,
    latency_p95_ms: float = 5000.0,
    token_input_mean: float = 1500.0,
    token_output_mean: float = 100.0,
) -> dict[str, Any]:
    if failure_counts is None:
        failure_counts = {"wrong_order_ids": 3}
    if query_accuracy_by_tier is None:
        query_accuracy_by_tier = {"1": 100.0, "2": 80.0, "3": 60.0}
    if query_accuracy_by_answer_type is None:
        query_accuracy_by_answer_type = {"order_list": 80.0, "order_status": 90.0}
    return {
        "model_id": model_id,
        "query_accuracy": query_accuracy,
        "query_accuracy_by_tier": query_accuracy_by_tier,
        "query_accuracy_by_answer_type": query_accuracy_by_answer_type,
        "mean_precision": mean_precision,
        "mean_recall": mean_recall,
        "mean_f1": mean_f1,
        "scenario_reliability": scenario_reliability,
        "accuracy_std": accuracy_std,
        "latency_mean_ms": latency_mean_ms,
        "latency_p50_ms": latency_p50_ms,
        "latency_p95_ms": latency_p95_ms,
        "token_input_mean": token_input_mean,
        "token_output_mean": token_output_mean,
        "total_cost_usd": None,
        "failure_counts": failure_counts,
    }


# ---------------------------------------------------------------------------
# Tests: data loading
# ---------------------------------------------------------------------------


class TestLoadQuerySummary:
    def test_valid_load(self, tmp_path: Path) -> None:
        summary = {"timestamps": {}, "models": [{"model_id": "test"}]}
        (tmp_path / "query_summary.json").write_text(json.dumps(summary))
        result = load_query_summary(tmp_path)
        assert result["models"][0]["model_id"] == "test"

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_query_summary(tmp_path)

    def test_malformed_json(self, tmp_path: Path) -> None:
        (tmp_path / "query_summary.json").write_text("{bad json")
        with pytest.raises(json.JSONDecodeError):
            load_query_summary(tmp_path)


class TestLoadQueryRunResults:
    def test_loads_runs_by_model(self, tmp_path: Path) -> None:
        model_dir = tmp_path / "test_model"
        model_dir.mkdir()
        run1 = _make_query_run(model_id="vendor/test-model", run_number=1)
        run2 = _make_query_run(model_id="vendor/test-model", run_number=2)
        (model_dir / "query_run_1.json").write_text(json.dumps(run1))
        (model_dir / "query_run_2.json").write_text(json.dumps(run2))

        result = load_query_run_results(tmp_path)
        assert "vendor/test-model" in result
        assert len(result["vendor/test-model"]) == 2

    def test_ignores_non_directories(self, tmp_path: Path) -> None:
        (tmp_path / "query_summary.json").write_text("{}")
        result = load_query_run_results(tmp_path)
        assert result == {}

    def test_ignores_dirs_without_query_run_files(self, tmp_path: Path) -> None:
        (tmp_path / "empty_dir").mkdir()
        result = load_query_run_results(tmp_path)
        assert result == {}

    def test_multiple_models(self, tmp_path: Path) -> None:
        for name, mid in [("model_a", "v/a"), ("model_b", "v/b")]:
            d = tmp_path / name
            d.mkdir()
            (d / "query_run_1.json").write_text(json.dumps(_make_query_run(model_id=mid)))

        result = load_query_run_results(tmp_path)
        assert len(result) == 2
        assert "v/a" in result
        assert "v/b" in result

    def test_inconsistent_model_ids(self, tmp_path: Path) -> None:
        model_dir = tmp_path / "test_model"
        model_dir.mkdir()
        (model_dir / "query_run_1.json").write_text(
            json.dumps(_make_query_run(model_id="vendor/model-a"))
        )
        (model_dir / "query_run_2.json").write_text(
            json.dumps(_make_query_run(model_id="vendor/model-b"))
        )
        with pytest.raises(ValueError, match="Inconsistent model_id"):
            load_query_run_results(tmp_path)

    def test_corrupt_json(self, tmp_path: Path) -> None:
        model_dir = tmp_path / "test_model"
        model_dir.mkdir()
        (model_dir / "query_run_1.json").write_text("{bad json")
        with pytest.raises(json.JSONDecodeError):
            load_query_run_results(tmp_path)

    def test_missing_model_id_key(self, tmp_path: Path) -> None:
        model_dir = tmp_path / "test_model"
        model_dir.mkdir()
        (model_dir / "query_run_1.json").write_text(json.dumps({"run_number": 1}))
        with pytest.raises(KeyError):
            load_query_run_results(tmp_path)


# ---------------------------------------------------------------------------
# Tests: analysis functions
# ---------------------------------------------------------------------------


class TestComputeHardestQueryScenarios:
    def test_returns_sorted_ascending(self) -> None:
        run_data = {
            "model_a": [
                _make_query_run(
                    model_id="model_a",
                    scenarios=[
                        _make_query_scenario("QR-001", all_correct=True),
                        _make_query_scenario("QR-002", all_correct=False),
                        _make_query_scenario("QR-003", all_correct=True),
                    ],
                )
            ],
        }
        result = compute_hardest_query_scenarios(run_data, top_n=10)
        assert result[0]["scenario_id"] == "QR-002"
        assert result[0]["accuracy"] == 0.0
        assert result[-1]["scenario_id"] in ("QR-001", "QR-003")
        assert result[-1]["accuracy"] == 100.0

    def test_top_n_limits(self) -> None:
        scenarios = [_make_query_scenario(f"QR-{i:03d}", all_correct=False) for i in range(20)]
        run_data = {"m": [_make_query_run(model_id="m", scenarios=scenarios)]}
        result = compute_hardest_query_scenarios(run_data, top_n=5)
        assert len(result) == 5

    def test_aggregates_across_models(self) -> None:
        run_data = {
            "model_a": [
                _make_query_run(
                    model_id="model_a",
                    scenarios=[_make_query_scenario("QR-001", all_correct=True)],
                )
            ],
            "model_b": [
                _make_query_run(
                    model_id="model_b",
                    scenarios=[_make_query_scenario("QR-001", all_correct=False)],
                )
            ],
        }
        result = compute_hardest_query_scenarios(run_data)
        assert len(result) == 1
        assert result[0]["accuracy"] == 50.0

    def test_empty_scenarios(self) -> None:
        run_data = {"m": [_make_query_run(model_id="m", scenarios=[])]}
        result = compute_hardest_query_scenarios(run_data)
        assert result == []

    def test_includes_tier_and_answer_type(self) -> None:
        run_data = {
            "m": [
                _make_query_run(
                    model_id="m",
                    scenarios=[
                        _make_query_scenario("QR-001", tier=3, answer_type="prioritized_list")
                    ],
                )
            ],
        }
        result = compute_hardest_query_scenarios(run_data)
        assert result[0]["tier"] == 3
        assert result[0]["answer_type"] == "prioritized_list"


class TestComputeRunOverview:
    def test_counts_correctly(self) -> None:
        run_data = {
            "model_a": [
                _make_query_run(
                    model_id="model_a",
                    scenarios=[
                        _make_query_scenario("QR-001"),
                        _make_query_scenario("QR-002"),
                    ],
                ),
                _make_query_run(
                    model_id="model_a",
                    run_number=2,
                    scenarios=[_make_query_scenario("QR-001")],
                ),
            ],
        }
        overview = compute_run_overview(run_data)
        assert overview["unique_scenarios"] == 2
        assert overview["total_runs"] == 2
        assert overview["total_queries"] == 3

    def test_empty_run_data(self) -> None:
        overview = compute_run_overview({})
        assert overview["unique_scenarios"] == 0
        assert overview["total_runs"] == 0
        assert overview["total_queries"] == 0


class TestIdentifyQueryNonViableModels:
    def test_model_with_high_structural_failures(self) -> None:
        models = [
            _make_query_model_summary(
                model_id="bad-model",
                failure_counts={"invalid_json": 100, "wrong_order_ids": 10},
            ),
        ]
        result = identify_query_non_viable_models(models, threshold=0.5)
        assert len(result) == 1
        assert result[0]["model_id"] == "bad-model"

    def test_model_with_low_structural_failures(self) -> None:
        models = [
            _make_query_model_summary(
                model_id="good-model",
                failure_counts={"wrong_order_ids": 100, "invalid_json": 2},
            ),
        ]
        result = identify_query_non_viable_models(models, threshold=0.5)
        assert len(result) == 0

    def test_no_failures(self) -> None:
        models = [_make_query_model_summary(failure_counts={})]
        result = identify_query_non_viable_models(models)
        assert len(result) == 0

    def test_model_at_exact_threshold_not_flagged(self) -> None:
        models = [
            _make_query_model_summary(
                model_id="boundary",
                failure_counts={"invalid_json": 5, "wrong_order_ids": 5},
            ),
        ]
        result = identify_query_non_viable_models(models, threshold=0.5)
        assert len(result) == 0

    def test_uses_query_accuracy_field(self) -> None:
        models = [
            _make_query_model_summary(
                model_id="bad",
                query_accuracy=15.0,
                failure_counts={"invalid_json": 80, "timeout": 10, "wrong_order_ids": 5},
            ),
        ]
        result = identify_query_non_viable_models(models)
        assert result[0]["query_accuracy"] == 15.0


class TestComputeTierModelMatrix:
    def test_reshapes_correctly(self) -> None:
        models = [
            _make_query_model_summary(
                model_id="a",
                query_accuracy_by_tier={"1": 100.0, "2": 80.0},
            ),
            _make_query_model_summary(
                model_id="b",
                query_accuracy_by_tier={"1": 90.0, "2": 70.0},
            ),
        ]
        result = compute_tier_model_matrix(models)
        assert result["1"]["a"] == 100.0
        assert result["1"]["b"] == 90.0
        assert result["2"]["a"] == 80.0
        assert result["2"]["b"] == 70.0

    def test_empty(self) -> None:
        assert compute_tier_model_matrix([]) == {}


class TestComputeAnswerTypeModelMatrix:
    def test_reshapes_correctly(self) -> None:
        models = [
            _make_query_model_summary(
                model_id="a",
                query_accuracy_by_answer_type={"order_list": 90.0, "order_status": 100.0},
            ),
            _make_query_model_summary(
                model_id="b",
                query_accuracy_by_answer_type={"order_list": 70.0, "order_status": 80.0},
            ),
        ]
        result = compute_answer_type_model_matrix(models)
        assert result["order_list"]["a"] == 90.0
        assert result["order_status"]["b"] == 80.0

    def test_empty(self) -> None:
        assert compute_answer_type_model_matrix([]) == {}


# ---------------------------------------------------------------------------
# Tests: formatting functions
# ---------------------------------------------------------------------------


class TestFormatQuerySummaryTable:
    def test_contains_markdown_table(self) -> None:
        models = [_make_query_model_summary()]
        result = format_query_summary_table(models)
        assert "| Model |" in result
        assert "|----" in result
        assert "| test-model " in result
        assert "80.0" in result

    def test_preserves_input_order(self) -> None:
        models = [
            _make_query_model_summary(model_id="high", query_accuracy=90.0),
            _make_query_model_summary(model_id="low", query_accuracy=50.0),
        ]
        result = format_query_summary_table(models)
        high_pos = result.index("high")
        low_pos = result.index("low")
        assert high_pos < low_pos

    def test_includes_precision_recall_f1(self) -> None:
        models = [_make_query_model_summary(mean_precision=0.95, mean_recall=0.88, mean_f1=0.91)]
        result = format_query_summary_table(models)
        assert "0.950" in result
        assert "0.880" in result
        assert "0.910" in result


class TestFormatQueryVarianceTable:
    def test_includes_local_models(self) -> None:
        models = [_make_query_model_summary(accuracy_std=2.0)]
        result = format_query_variance_table(models)
        assert "±2.0" in result

    def test_empty_when_no_local(self) -> None:
        models = [_make_query_model_summary(accuracy_std=None)]
        result = format_query_variance_table(models)
        assert result == ""


class TestFormatTierMatrix:
    def test_contains_tiers(self) -> None:
        models = [
            _make_query_model_summary(query_accuracy_by_tier={"1": 100.0, "2": 80.0}),
        ]
        result = format_tier_matrix(models)
        assert "| 1 " in result
        assert "| 2 " in result
        assert "100.0" in result

    def test_non_numeric_tier_keys_handled(self) -> None:
        models = [
            _make_query_model_summary(query_accuracy_by_tier={"1": 100.0, "T2": 80.0}),
        ]
        result = format_tier_matrix(models)
        assert "| 1 " in result
        assert "| T2 " in result

    def test_empty_when_no_tiers(self) -> None:
        models = [_make_query_model_summary(query_accuracy_by_tier={})]
        result = format_tier_matrix(models)
        assert result == ""


class TestFormatAnswerTypeMatrix:
    def test_contains_answer_types(self) -> None:
        models = [
            _make_query_model_summary(
                query_accuracy_by_answer_type={"order_list": 85.0, "order_status": 95.0}
            ),
        ]
        result = format_answer_type_matrix(models)
        assert "order_list" in result
        assert "order_status" in result

    def test_empty_when_no_answer_types(self) -> None:
        models = [_make_query_model_summary(query_accuracy_by_answer_type={})]
        result = format_answer_type_matrix(models)
        assert result == ""


class TestFormatQueryFailureBreakdown:
    def test_contains_failure_types(self) -> None:
        models = [
            _make_query_model_summary(failure_counts={"wrong_order_ids": 50, "invalid_json": 10}),
        ]
        result = format_query_failure_breakdown(models)
        assert "| Model |" in result
        assert "|----" in result
        assert "wrong_order_ids" in result
        assert "invalid_json" in result
        assert "| 60 |" in result

    def test_empty_when_no_failures(self) -> None:
        models = [_make_query_model_summary(failure_counts={})]
        result = format_query_failure_breakdown(models)
        assert result == ""


class TestFormatHardestQueryScenarios:
    def test_contains_scenario_data(self) -> None:
        scenarios = [
            {
                "scenario_id": "QR-001",
                "tier": 1,
                "answer_type": "order_list",
                "accuracy": 10.0,
                "total_evals": 50,
            },
        ]
        result = format_hardest_query_scenarios(scenarios)
        assert "| QR-001 " in result
        assert "|----" in result
        assert "order_list" in result
        assert "10.0" in result


class TestFormatQueryNonViableSection:
    def test_with_non_viable(self) -> None:
        nv = [
            {
                "model_id": "bad/model",
                "structural_failures": 100,
                "total_failures": 120,
                "structural_fraction": 0.833,
                "query_accuracy": 12.0,
            },
        ]
        result = format_query_non_viable_section(nv)
        assert "model" in result
        assert "100" in result

    def test_without_non_viable(self) -> None:
        result = format_query_non_viable_section([])
        assert "No models exceeded" in result


class TestFormatQueryLatencyTable:
    def test_contains_latency_data(self) -> None:
        models = [_make_query_model_summary(latency_mean_ms=1234.0)]
        result = format_query_latency_table(models)
        assert "1234" in result
        assert "p50" in result


class TestFormatQueryExecutiveSummary:
    def test_contains_key_info(self) -> None:
        models = [
            _make_query_model_summary(
                model_id="best", query_accuracy=95.0, scenario_reliability=90.0
            ),
            _make_query_model_summary(
                model_id="worst", query_accuracy=30.0, scenario_reliability=20.0
            ),
        ]
        run_data = {
            "best": [_make_query_run(model_id="best")],
            "worst": [_make_query_run(model_id="worst")],
        }
        timestamps = {"started_at": "T1", "completed_at": "T2"}
        result = format_query_executive_summary(models, run_data, [], timestamps)
        assert "Models evaluated" in result
        assert "best" in result
        assert "Top Performers" in result
        assert "Total queries" in result

    def test_non_viable_section_displayed(self) -> None:
        models = [
            _make_query_model_summary(
                model_id="good", query_accuracy=95.0, scenario_reliability=90.0
            ),
        ]
        run_data = {"good": [_make_query_run(model_id="good")]}
        non_viable = [
            {
                "model_id": "bad/model",
                "structural_failures": 80,
                "total_failures": 100,
                "structural_fraction": 0.8,
                "query_accuracy": 10.0,
            },
        ]
        timestamps = {"started_at": "T1", "completed_at": "T2"}
        result = format_query_executive_summary(models, run_data, non_viable, timestamps)
        assert "Non-Viable Models" in result
        assert "model" in result


# ---------------------------------------------------------------------------
# Tests: integration
# ---------------------------------------------------------------------------


class TestGenerateQueryReport:
    def test_end_to_end(self, tmp_path: Path) -> None:
        models = [
            _make_query_model_summary(
                model_id="v/model-a",
                query_accuracy=90.0,
                failure_counts={"wrong_order_ids": 3},
            ),
            _make_query_model_summary(
                model_id="v/model-b",
                query_accuracy=40.0,
                failure_counts={"invalid_json": 80, "wrong_order_ids": 5},
            ),
        ]
        summary = {
            "timestamps": {"started_at": "2026-01-01", "completed_at": "2026-01-02"},
            "models": models,
        }
        (tmp_path / "query_summary.json").write_text(json.dumps(summary))

        for name, mid in [("v_model-a", "v/model-a"), ("v_model-b", "v/model-b")]:
            model_dir = tmp_path / name
            model_dir.mkdir()
            run = _make_query_run(
                model_id=mid,
                scenarios=[
                    _make_query_scenario("QR-001", all_correct=mid == "v/model-a"),
                    _make_query_scenario("QR-002", all_correct=True),
                    _make_query_scenario(
                        "QR-003", tier=4, answer_type="prioritized_list", all_correct=False
                    ),
                ],
            )
            (model_dir / "query_run_1.json").write_text(json.dumps(run))

        output_path = tmp_path / "query_analysis.md"
        result = generate_query_report(tmp_path, output_path)

        assert result == output_path
        assert output_path.exists()

        content = output_path.read_text()

        expected_sections = [
            "# Query Baseline Analysis",
            "## 1. Executive Summary",
            "## 2. Model Performance Overview",
            "### 2.1 Primary Metrics",
            "## 3. Accuracy by Tier",
            "## 4. Accuracy by Answer Type",
            "## 5. Failure Analysis",
            "### 5.1 Failure Type Breakdown",
            "### 5.2 Hardest Scenarios",
            "### 5.3 Non-Viable Models",
            "## 6. Secondary Metrics",
        ]
        for section in expected_sections:
            assert section in content, f"Missing section: {section}"

        # Models should be ranked by accuracy (model-a=90% before model-b=40%)
        assert content.index("model-a") < content.index("model-b")

    def test_multi_run_per_model(self, tmp_path: Path) -> None:
        models = [
            _make_query_model_summary(
                model_id="v/multi",
                query_accuracy=70.0,
                accuracy_std=5.0,
            ),
        ]
        summary = {
            "timestamps": {"started_at": "2026-01-01", "completed_at": "2026-01-02"},
            "models": models,
        }
        (tmp_path / "query_summary.json").write_text(json.dumps(summary))

        model_dir = tmp_path / "v_multi"
        model_dir.mkdir()
        for run_num in (1, 2):
            run = _make_query_run(
                model_id="v/multi",
                run_number=run_num,
                scenarios=[
                    _make_query_scenario("QR-001", all_correct=run_num == 1),
                    _make_query_scenario("QR-002", all_correct=True),
                ],
            )
            (model_dir / f"query_run_{run_num}.json").write_text(json.dumps(run))

        output_path = tmp_path / "report.md"
        generate_query_report(tmp_path, output_path)
        content = output_path.read_text()
        assert "# Query Baseline Analysis" in content
        assert "multi" in content
        assert "Variance Analysis" in content

    def test_with_no_variance_models(self, tmp_path: Path) -> None:
        models = [_make_query_model_summary(model_id="cloud-model", accuracy_std=None)]
        summary = {"timestamps": {}, "models": models}
        (tmp_path / "query_summary.json").write_text(json.dumps(summary))

        model_dir = tmp_path / "cloud-model"
        model_dir.mkdir()
        (model_dir / "query_run_1.json").write_text(
            json.dumps(_make_query_run(model_id="cloud-model"))
        )

        output_path = tmp_path / "report.md"
        generate_query_report(tmp_path, output_path)
        content = output_path.read_text()
        assert "Variance Analysis" not in content

    def test_with_variance_models(self, tmp_path: Path) -> None:
        models = [_make_query_model_summary(model_id="local-model", accuracy_std=2.5)]
        summary = {"timestamps": {}, "models": models}
        (tmp_path / "query_summary.json").write_text(json.dumps(summary))

        model_dir = tmp_path / "local-model"
        model_dir.mkdir()
        (model_dir / "query_run_1.json").write_text(
            json.dumps(_make_query_run(model_id="local-model"))
        )

        output_path = tmp_path / "report.md"
        generate_query_report(tmp_path, output_path)
        content = output_path.read_text()
        assert "Variance Analysis" in content
        assert "±2.5" in content

    def test_missing_models_key(self, tmp_path: Path) -> None:
        (tmp_path / "query_summary.json").write_text(json.dumps({"timestamps": {}}))
        with pytest.raises(ValueError, match="No 'models' key"):
            generate_query_report(tmp_path, tmp_path / "out.md")

    def test_no_failures_still_renders(self, tmp_path: Path) -> None:
        models = [_make_query_model_summary(model_id="perfect", failure_counts={})]
        summary = {"timestamps": {}, "models": models}
        (tmp_path / "query_summary.json").write_text(json.dumps(summary))

        model_dir = tmp_path / "perfect"
        model_dir.mkdir()
        (model_dir / "query_run_1.json").write_text(json.dumps(_make_query_run(model_id="perfect")))

        output_path = tmp_path / "report.md"
        generate_query_report(tmp_path, output_path)
        content = output_path.read_text()
        assert "# Query Baseline Analysis" in content
        assert "No models exceeded" in content


# ---------------------------------------------------------------------------
# Tests: CLI main()
# ---------------------------------------------------------------------------


class TestQueryMain:
    def test_default_arguments(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        summary = {"timestamps": {}, "models": [_make_query_model_summary()]}
        (tmp_path / "query_summary.json").write_text(json.dumps(summary))
        model_dir = tmp_path / "test-model"
        model_dir.mkdir()
        (model_dir / "query_run_1.json").write_text(json.dumps(_make_query_run()))
        output = tmp_path / "report.md"
        main(["--results-dir", str(tmp_path), "--output", str(output)])
        assert output.exists()
        captured = capsys.readouterr()
        assert "Report written to" in captured.out

    def test_custom_top_n(self, tmp_path: Path) -> None:
        summary = {"timestamps": {}, "models": [_make_query_model_summary()]}
        (tmp_path / "query_summary.json").write_text(json.dumps(summary))
        model_dir = tmp_path / "test-model"
        model_dir.mkdir()
        (model_dir / "query_run_1.json").write_text(json.dumps(_make_query_run()))
        output = tmp_path / "report.md"
        main(["--results-dir", str(tmp_path), "--output", str(output), "--top-n", "5"])
        assert output.exists()

    def test_missing_results_dir(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent"
        with pytest.raises(FileNotFoundError):
            main(["--results-dir", str(missing), "--output", str(tmp_path / "out.md")])
