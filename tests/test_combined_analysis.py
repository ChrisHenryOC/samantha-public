"""Tests for src.evaluation.combined_analysis — combined Phase 4 report."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.evaluation.combined_analysis import (
    _CLOUD_PREFIX,
    format_capability_matrix,
    format_cross_track_analysis,
    format_executive_summary,
    format_go_no_go_assessment,
    format_phase5_recommendations,
    format_unified_scorecard,
    generate_combined_report,
    load_query_summary,
    load_routing_summary,
    main,
    merge_model_data,
)

# ---------------------------------------------------------------------------
# Fixtures — inline JSON dicts
# ---------------------------------------------------------------------------


def _make_routing_model(
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
) -> dict[str, Any]:
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
        "failure_counts": failure_counts or {"wrong_state": 10},
        "accuracy_by_category": accuracy_by_category or {"rule_coverage": 80.0},
        "latency_mean_ms": latency_mean_ms,
        "latency_p50_ms": latency_p50_ms,
        "latency_p95_ms": latency_p95_ms,
        "token_input_mean": token_input_mean,
        "token_output_mean": token_output_mean,
        "total_cost_usd": None,
    }


def _make_query_model(
    model_id: str = "test-vendor/test-model",
    query_accuracy: float = 85.0,
    mean_precision: float = 0.9,
    mean_recall: float = 0.9,
    mean_f1: float = 0.9,
    scenario_reliability: float = 70.0,
    accuracy_std: float | None = None,
    latency_mean_ms: float = 1200.0,
    latency_p50_ms: float = 1000.0,
    latency_p95_ms: float = 2500.0,
    token_input_mean: float = 1600.0,
    token_output_mean: float = 120.0,
    failure_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    return {
        "model_id": model_id,
        "query_accuracy": query_accuracy,
        "query_accuracy_by_tier": {"1": 100.0, "2": 80.0},
        "query_accuracy_by_answer_type": {"order_list": 80.0, "order_status": 100.0},
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
        "failure_counts": failure_counts or {},
    }


# ---------------------------------------------------------------------------
# Tests: data loading
# ---------------------------------------------------------------------------


class TestLoadRoutingSummary:
    def test_valid_load(self, tmp_path: Path) -> None:
        summary = {"timestamps": {}, "models": [{"model_id": "test"}]}
        (tmp_path / "summary.json").write_text(json.dumps(summary))
        result = load_routing_summary(tmp_path)
        assert result["models"][0]["model_id"] == "test"

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_routing_summary(tmp_path)


class TestLoadQuerySummary:
    def test_valid_load(self, tmp_path: Path) -> None:
        summary = {"timestamps": {}, "models": [{"model_id": "test"}]}
        (tmp_path / "query_summary.json").write_text(json.dumps(summary))
        result = load_query_summary(tmp_path)
        assert result["models"][0]["model_id"] == "test"

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_query_summary(tmp_path)


# ---------------------------------------------------------------------------
# Tests: model merging
# ---------------------------------------------------------------------------


class TestMergeModelData:
    def test_both_tracks(self) -> None:
        routing = [_make_routing_model(model_id="shared-model", accuracy=90.0)]
        query = [_make_query_model(model_id="shared-model", query_accuracy=85.0)]
        merged = merge_model_data(routing, query)
        assert len(merged) == 1
        assert merged[0]["model_id"] == "shared-model"
        assert merged[0]["routing"] is not None
        assert merged[0]["query"] is not None
        assert merged[0]["combined_score"] == pytest.approx(87.5)

    def test_routing_only(self) -> None:
        routing = [_make_routing_model(model_id="routing-only", accuracy=70.0)]
        merged = merge_model_data(routing, [])
        assert len(merged) == 1
        assert merged[0]["routing"] is not None
        assert merged[0]["query"] is None
        assert merged[0]["combined_score"] == pytest.approx(70.0)

    def test_query_only(self) -> None:
        query = [_make_query_model(model_id="query-only", query_accuracy=60.0)]
        merged = merge_model_data([], query)
        assert len(merged) == 1
        assert merged[0]["routing"] is None
        assert merged[0]["query"] is not None
        assert merged[0]["combined_score"] == pytest.approx(60.0)

    def test_mixed_models(self) -> None:
        routing = [
            _make_routing_model(model_id="shared", accuracy=90.0),
            _make_routing_model(model_id="routing-only", accuracy=50.0),
        ]
        query = [
            _make_query_model(model_id="shared", query_accuracy=80.0),
            _make_query_model(model_id="query-only", query_accuracy=60.0),
        ]
        merged = merge_model_data(routing, query)
        assert len(merged) == 3
        # Sorted by combined score descending
        assert merged[0]["model_id"] == "shared"  # (90+80)/2 = 85
        assert merged[1]["model_id"] == "query-only"  # 60
        assert merged[2]["model_id"] == "routing-only"  # 50

    def test_cloud_model_detection(self) -> None:
        routing = [_make_routing_model(model_id="claude-opus-4-6-20250514")]
        merged = merge_model_data(routing, [])
        assert merged[0]["is_cloud"] is True

    def test_local_model_detection(self) -> None:
        routing = [_make_routing_model(model_id="meta-llama/llama-3.1-8b")]
        merged = merge_model_data(routing, [])
        assert merged[0]["is_cloud"] is False

    def test_empty_inputs(self) -> None:
        merged = merge_model_data([], [])
        assert merged == []


# ---------------------------------------------------------------------------
# Tests: formatting functions
# ---------------------------------------------------------------------------


class TestFormatExecutiveSummary:
    def test_contains_key_info(self) -> None:
        merged = [
            {
                "model_id": "best-model",
                "is_cloud": True,
                "routing": _make_routing_model(accuracy=95.0),
                "query": _make_query_model(query_accuracy=90.0),
                "combined_score": 92.5,
            },
        ]
        ts_r = {"started_at": "T1", "completed_at": "T2"}
        ts_q = {"started_at": "T3", "completed_at": "T4"}
        result = format_executive_summary(merged, ts_r, ts_q)
        assert "Total unique models" in result
        assert "best-model" in result
        assert "Top Performers" in result

    def test_routing_only_model(self) -> None:
        merged = [
            {
                "model_id": "r-only",
                "is_cloud": False,
                "routing": _make_routing_model(accuracy=70.0),
                "query": None,
                "combined_score": 70.0,
            },
        ]
        result = format_executive_summary(merged, {}, {})
        assert "routing 70.0%" in result
        r_only_lines = [line for line in result.split("\n") if "r-only" in line]
        assert r_only_lines, "Expected a line containing 'r-only'"
        assert "query" not in r_only_lines[0]


class TestFormatUnifiedScorecard:
    def test_both_tracks(self) -> None:
        merged = [
            {
                "model_id": "test/model",
                "is_cloud": False,
                "routing": _make_routing_model(
                    accuracy=80.0, scenario_reliability=50.0, accuracy_std=1.5
                ),
                "query": _make_query_model(query_accuracy=85.0, scenario_reliability=70.0),
                "combined_score": 82.5,
            },
        ]
        result = format_unified_scorecard(merged)
        assert "| model |" in result.lower() or "Model" in result
        assert "80.0" in result
        assert "85.0" in result
        assert "±1.5" in result

    def test_missing_track_shows_dash(self) -> None:
        merged = [
            {
                "model_id": "partial",
                "is_cloud": False,
                "routing": None,
                "query": _make_query_model(query_accuracy=75.0),
                "combined_score": 75.0,
            },
        ]
        result = format_unified_scorecard(merged)
        # Routing columns should have dashes
        lines = result.split("\n")
        data_line = [line for line in lines if "partial" in line][0]
        assert "—" in data_line


class TestFormatCrossTrackAnalysis:
    def test_with_both_tracks(self) -> None:
        merged = [
            {
                "model_id": "model-a",
                "is_cloud": True,
                "routing": _make_routing_model(accuracy=90.0),
                "query": _make_query_model(query_accuracy=80.0),
                "combined_score": 85.0,
            },
            {
                "model_id": "model-b",
                "is_cloud": False,
                "routing": _make_routing_model(accuracy=60.0),
                "query": _make_query_model(query_accuracy=70.0),
                "combined_score": 65.0,
            },
        ]
        result = format_cross_track_analysis(merged)
        assert "Cross-Track" in result
        assert "model-a" in result
        assert "model-b" in result
        assert "Delta" in result

    def test_no_models_in_both(self) -> None:
        merged = [
            {
                "model_id": "r-only",
                "is_cloud": False,
                "routing": _make_routing_model(),
                "query": None,
                "combined_score": 80.0,
            },
        ]
        result = format_cross_track_analysis(merged)
        assert "No models evaluated on both tracks" in result

    def test_balanced_delta(self) -> None:
        merged = [
            {
                "model_id": "balanced",
                "is_cloud": True,
                "routing": _make_routing_model(accuracy=80.0),
                "query": _make_query_model(query_accuracy=80.5),
                "combined_score": 80.25,
            },
        ]
        result = format_cross_track_analysis(merged)
        assert "Balanced" in result


class TestFormatCapabilityMatrix:
    def test_ratings(self) -> None:
        merged = [
            {
                "model_id": "strong-model",
                "is_cloud": True,
                "routing": _make_routing_model(
                    accuracy=95.0, accuracy_std=0.5, latency_p50_ms=1000.0
                ),
                "query": _make_query_model(query_accuracy=92.0),
                "combined_score": 93.5,
            },
        ]
        result = format_capability_matrix(merged)
        assert "Strong" in result
        assert "High" in result
        assert "Fast" in result

    def test_weak_model(self) -> None:
        merged = [
            {
                "model_id": "weak-model",
                "is_cloud": False,
                "routing": _make_routing_model(
                    accuracy=45.0, accuracy_std=3.0, latency_p50_ms=5000.0
                ),
                "query": _make_query_model(query_accuracy=50.0),
                "combined_score": 47.5,
            },
        ]
        result = format_capability_matrix(merged)
        assert "Weak" in result
        assert "Low" in result
        assert "Slow" in result

    def test_na_for_missing_data(self) -> None:
        merged = [
            {
                "model_id": "partial",
                "is_cloud": False,
                "routing": None,
                "query": _make_query_model(query_accuracy=60.0, latency_p50_ms=1000.0),
                "combined_score": 60.0,
            },
        ]
        result = format_capability_matrix(merged)
        assert "N/A" in result


class TestFormatGoNoGoAssessment:
    def test_feasible_models(self) -> None:
        merged = [
            {
                "model_id": "claude-opus",
                "is_cloud": True,
                "routing": _make_routing_model(accuracy=95.0, accuracy_std=1.0),
                "query": _make_query_model(query_accuracy=96.0),
                "combined_score": 95.5,
            },
            {
                "model_id": "local-model",
                "is_cloud": False,
                "routing": _make_routing_model(
                    accuracy=60.0,
                    accuracy_std=1.5,
                    token_input_mean=1500.0,
                ),
                "query": _make_query_model(query_accuracy=74.0),
                "combined_score": 67.0,
            },
        ]
        result = format_go_no_go_assessment(merged)
        assert "Feasibility" in result
        assert "Ceiling Benchmark" in result
        assert "RAG Justification" in result
        assert "Variance" in result
        assert "feasible" in result.lower()
        # Flag accuracy column should appear in variance table
        assert "Flag Acc%" in result

    def test_no_feasible_models(self) -> None:
        merged = [
            {
                "model_id": "weak-local",
                "is_cloud": False,
                "routing": _make_routing_model(accuracy=30.0, accuracy_std=5.0),
                "query": _make_query_model(query_accuracy=40.0),
                "combined_score": 35.0,
            },
        ]
        result = format_go_no_go_assessment(merged)
        assert "No models achieve" in result or "No local models" in result

    def test_variance_table(self) -> None:
        merged = [
            {
                "model_id": "stable-local",
                "is_cloud": False,
                "routing": _make_routing_model(accuracy=85.0, accuracy_std=1.0),
                "query": None,
                "combined_score": 85.0,
            },
        ]
        result = format_go_no_go_assessment(merged)
        assert "Clinical Viable?" in result
        assert "Yes" in result


class TestCloudModelDetection:
    """Direct tests for the cloud-model prefix convention (#22)."""

    def test_claude_prefix_is_cloud(self) -> None:
        assert "claude-opus".startswith(_CLOUD_PREFIX)

    def test_local_model_is_not_cloud(self) -> None:
        assert not "meta-llama/llama-3.1-8b".startswith(_CLOUD_PREFIX)

    def test_openrouter_model_is_not_cloud(self) -> None:
        assert not "openrouter/auto".startswith(_CLOUD_PREFIX)


class TestFormatCapabilityMatrixBoundaries:
    """Boundary tests for rating tiers (#6)."""

    def _make_merged(
        self,
        accuracy: float = 95.0,
        query_accuracy: float = 95.0,
        accuracy_std: float = 0.5,
        latency_p50_ms: float = 1000.0,
    ) -> list[dict[str, Any]]:
        return [
            {
                "model_id": "boundary-model",
                "is_cloud": False,
                "routing": _make_routing_model(
                    accuracy=accuracy,
                    accuracy_std=accuracy_std,
                    latency_p50_ms=latency_p50_ms,
                ),
                "query": _make_query_model(
                    query_accuracy=query_accuracy,
                    latency_p50_ms=latency_p50_ms,
                ),
                "combined_score": (accuracy + query_accuracy) / 2,
            },
        ]

    def test_strong_boundary(self) -> None:
        result = format_capability_matrix(self._make_merged(accuracy=90.0))
        assert "Strong" in result

    def test_moderate_boundary(self) -> None:
        result = format_capability_matrix(self._make_merged(accuracy=70.0))
        assert "Moderate" in result

    def test_just_below_moderate(self) -> None:
        result = format_capability_matrix(self._make_merged(accuracy=69.9))
        assert "Weak" in result

    def test_weak_boundary(self) -> None:
        result = format_capability_matrix(self._make_merged(accuracy=40.0))
        assert "Weak" in result

    def test_poor_boundary(self) -> None:
        result = format_capability_matrix(self._make_merged(accuracy=39.9))
        assert "Poor" in result

    def test_query_moderate(self) -> None:
        result = format_capability_matrix(self._make_merged(accuracy=95.0, query_accuracy=70.0))
        lines = result.split("\n")
        data_line = [line for line in lines if "boundary-model" in line][0]
        # Routing=Strong, Query=Moderate
        assert "Strong" in data_line
        assert "Moderate" in data_line

    def test_consistency_moderate_boundary(self) -> None:
        result = format_capability_matrix(self._make_merged(accuracy_std=2.0))
        assert "Moderate" in result

    def test_consistency_low_boundary(self) -> None:
        result = format_capability_matrix(self._make_merged(accuracy_std=2.1))
        assert "Low" in result

    def test_latency_moderate_boundary(self) -> None:
        result = format_capability_matrix(self._make_merged(latency_p50_ms=2000.0))
        lines = result.split("\n")
        data_line = [line for line in lines if "boundary-model" in line][0]
        # Should be "Moderate" latency (1500 < 2000 <= 3000)
        assert "Moderate" in data_line


class TestFormatGoNoGoFeasibilityBoundaries:
    """Boundary tests for the 80% feasibility threshold (#7)."""

    def test_exactly_at_threshold(self) -> None:
        merged = [
            {
                "model_id": "borderline",
                "is_cloud": False,
                "routing": _make_routing_model(accuracy=80.0, accuracy_std=1.0),
                "query": _make_query_model(query_accuracy=80.0),
                "combined_score": 80.0,
            },
        ]
        result = format_go_no_go_assessment(merged)
        assert "feasible" in result.lower()
        assert "1 model(s) achieve" in result

    def test_just_below_threshold(self) -> None:
        merged = [
            {
                "model_id": "almost",
                "is_cloud": False,
                "routing": _make_routing_model(accuracy=79.9, accuracy_std=1.0),
                "query": _make_query_model(query_accuracy=79.9),
                "combined_score": 79.9,
            },
        ]
        result = format_go_no_go_assessment(merged)
        assert "No models achieve" in result


class TestFormatGoNoGoCloudOnly:
    """Tests for cloud-only configuration (#8)."""

    def test_cloud_only_no_local_models(self) -> None:
        merged = [
            {
                "model_id": "claude-opus",
                "is_cloud": True,
                "routing": _make_routing_model(
                    model_id="claude-opus",
                    accuracy=95.0,
                    accuracy_std=1.0,
                ),
                "query": _make_query_model(
                    model_id="claude-opus",
                    query_accuracy=96.0,
                ),
                "combined_score": 95.5,
            },
        ]
        result = format_go_no_go_assessment(merged)
        assert "No local models evaluated for routing" in result
        assert "No multi-run variance data available for local models" in result


class TestFormatGoNoGoReliabilityWarning:
    """Test scenario reliability warnings in feasibility (#1)."""

    def test_low_reliability_warning(self) -> None:
        merged = [
            {
                "model_id": "high-acc-low-rel",
                "is_cloud": False,
                "routing": _make_routing_model(
                    accuracy=90.0,
                    scenario_reliability=30.0,
                    accuracy_std=1.0,
                ),
                "query": _make_query_model(
                    query_accuracy=85.0,
                    scenario_reliability=40.0,
                ),
                "combined_score": 87.5,
            },
        ]
        result = format_go_no_go_assessment(merged)
        assert "reliability warning" in result.lower()

    def test_no_warning_when_reliable(self) -> None:
        merged = [
            {
                "model_id": "good-model",
                "is_cloud": False,
                "routing": _make_routing_model(
                    accuracy=90.0,
                    scenario_reliability=60.0,
                    accuracy_std=1.0,
                ),
                "query": _make_query_model(
                    query_accuracy=85.0,
                    scenario_reliability=60.0,
                ),
                "combined_score": 87.5,
            },
        ]
        result = format_go_no_go_assessment(merged)
        assert "reliability warning" not in result.lower()


class TestFormatGoNoGoQueryOnlyFeasible:
    """Test feasibility verdict when only query is feasible (#13)."""

    def test_query_feasible_routing_not(self) -> None:
        merged = [
            {
                "model_id": "query-strong",
                "is_cloud": False,
                "routing": _make_routing_model(accuracy=50.0, accuracy_std=1.0),
                "query": _make_query_model(query_accuracy=90.0),
                "combined_score": 70.0,
            },
        ]
        result = format_go_no_go_assessment(merged)
        assert "Query task is feasible" in result
        assert "Routing remains the primary challenge" in result


class TestFormatGoNoCeilingMissingTier:
    """Test ceiling benchmark with missing tiers (#12)."""

    def test_local_only_ceiling(self) -> None:
        merged = [
            {
                "model_id": "local-only",
                "is_cloud": False,
                "routing": _make_routing_model(accuracy=60.0, accuracy_std=1.0),
                "query": _make_query_model(query_accuracy=70.0),
                "combined_score": 65.0,
            },
        ]
        result = format_go_no_go_assessment(merged)
        assert "Insufficient data" in result


class TestFormatGoNoGoFlagAccuracy:
    """Test flag accuracy in clinical viability (#14)."""

    def test_low_flag_accuracy_not_viable(self) -> None:
        merged = [
            {
                "model_id": "bad-flags",
                "is_cloud": False,
                "routing": _make_routing_model(
                    accuracy=85.0,
                    flag_accuracy=60.0,
                    accuracy_std=1.0,
                ),
                "query": None,
                "combined_score": 85.0,
            },
        ]
        result = format_go_no_go_assessment(merged)
        assert "60.0" in result  # Flag accuracy shown
        assert "| No |" in result  # Not clinically viable


class TestFormatPhase5Recommendations:
    def test_with_promising_models(self) -> None:
        merged = [
            {
                "model_id": "claude-opus",
                "is_cloud": True,
                "routing": _make_routing_model(accuracy=95.0),
                "query": _make_query_model(query_accuracy=96.0),
                "combined_score": 95.5,
            },
            {
                "model_id": "good-local",
                "is_cloud": False,
                "routing": _make_routing_model(accuracy=60.0),
                "query": _make_query_model(query_accuracy=74.0),
                "combined_score": 67.0,
            },
        ]
        result = format_phase5_recommendations(merged)
        assert "Priority Models" in result
        assert "good-local" in result

    def test_with_non_viable_models(self) -> None:
        merged = [
            {
                "model_id": "terrible-model",
                "is_cloud": False,
                "routing": _make_routing_model(accuracy=12.0),
                "query": None,
                "combined_score": 12.0,
            },
        ]
        result = format_phase5_recommendations(merged)
        assert "Exclude" in result
        assert "terrible-model" in result

    def test_insufficient_data_branch(self) -> None:
        """Test 'Insufficient data' when all models have routing=None (#9)."""
        merged = [
            {
                "model_id": "query-only",
                "is_cloud": False,
                "routing": None,
                "query": _make_query_model(query_accuracy=80.0),
                "combined_score": 80.0,
            },
            {
                "model_id": "claude-query-only",
                "is_cloud": True,
                "routing": None,
                "query": _make_query_model(query_accuracy=90.0),
                "combined_score": 90.0,
            },
        ]
        result = format_phase5_recommendations(merged)
        assert "Insufficient data" in result


class TestFormatCrossTrackBranches:
    """Test routing-wins/query-wins and ranking branches (#20, #21)."""

    def test_routing_dominant(self) -> None:
        merged = [
            {
                "model_id": "model-a",
                "is_cloud": False,
                "routing": _make_routing_model(accuracy=90.0),
                "query": _make_query_model(query_accuracy=70.0),
                "combined_score": 80.0,
            },
            {
                "model_id": "model-b",
                "is_cloud": False,
                "routing": _make_routing_model(accuracy=80.0),
                "query": _make_query_model(query_accuracy=60.0),
                "combined_score": 70.0,
            },
        ]
        result = format_cross_track_analysis(merged)
        assert "perform better at routing" in result

    def test_query_dominant(self) -> None:
        merged = [
            {
                "model_id": "model-a",
                "is_cloud": False,
                "routing": _make_routing_model(accuracy=60.0),
                "query": _make_query_model(query_accuracy=90.0),
                "combined_score": 75.0,
            },
            {
                "model_id": "model-b",
                "is_cloud": False,
                "routing": _make_routing_model(accuracy=50.0),
                "query": _make_query_model(query_accuracy=80.0),
                "combined_score": 65.0,
            },
        ]
        result = format_cross_track_analysis(merged)
        assert "perform better at queries" in result

    def test_identical_ranking(self) -> None:
        merged = [
            {
                "model_id": "model-a",
                "is_cloud": False,
                "routing": _make_routing_model(accuracy=90.0),
                "query": _make_query_model(query_accuracy=90.0),
                "combined_score": 90.0,
            },
            {
                "model_id": "model-b",
                "is_cloud": False,
                "routing": _make_routing_model(accuracy=70.0),
                "query": _make_query_model(query_accuracy=70.0),
                "combined_score": 70.0,
            },
        ]
        result = format_cross_track_analysis(merged)
        assert "ranking is identical" in result


# ---------------------------------------------------------------------------
# Tests: data loading edge cases
# ---------------------------------------------------------------------------


class TestMalformedInput:
    """Test malformed JSON input handling (#10)."""

    def test_malformed_routing_json(self, tmp_path: Path) -> None:
        (tmp_path / "summary.json").write_text("not valid json")
        with pytest.raises(json.JSONDecodeError):
            load_routing_summary(tmp_path)

    def test_malformed_query_json(self, tmp_path: Path) -> None:
        (tmp_path / "query_summary.json").write_text("{truncated")
        with pytest.raises(json.JSONDecodeError):
            load_query_summary(tmp_path)

    def test_missing_model_id_in_routing(self) -> None:
        with pytest.raises(ValueError, match="routing models.*missing 'model_id'"):
            merge_model_data([{"accuracy": 80.0}], [_make_query_model()])

    def test_missing_model_id_in_query(self) -> None:
        with pytest.raises(ValueError, match="query models.*missing 'model_id'"):
            merge_model_data([_make_routing_model()], [{"query_accuracy": 80.0}])


# ---------------------------------------------------------------------------
# Tests: integration
# ---------------------------------------------------------------------------


class TestGenerateCombinedReport:
    def test_end_to_end(self, tmp_path: Path) -> None:
        routing_dir = tmp_path / "routing"
        routing_dir.mkdir()
        query_dir = tmp_path / "query"
        query_dir.mkdir()

        routing_summary = {
            "timestamps": {"started_at": "2026-02-23", "completed_at": "2026-02-24"},
            "models": [
                _make_routing_model(model_id="claude-opus-4-6", accuracy=95.0),
                _make_routing_model(model_id="vendor/local-model", accuracy=60.0, accuracy_std=1.5),
            ],
        }
        query_summary = {
            "timestamps": {"started_at": "2026-03-03", "completed_at": "2026-03-03"},
            "models": [
                _make_query_model(model_id="claude-opus-4-6", query_accuracy=96.0),
                _make_query_model(model_id="vendor/local-model", query_accuracy=74.0),
            ],
        }

        (routing_dir / "summary.json").write_text(json.dumps(routing_summary))
        (query_dir / "query_summary.json").write_text(json.dumps(query_summary))

        output_path = tmp_path / "report.md"
        result = generate_combined_report(routing_dir, query_dir, output_path)

        assert result == output_path
        assert output_path.exists()

        content = output_path.read_text()

        expected_sections = [
            "# Phase 4 Combined Baseline Report",
            "## 1. Executive Summary",
            "## 2. Unified Scorecard",
            "## 3. Cross-Track Correlation",
            "## 4. Model Capability Matrix",
            "## 5. Go/No-Go Assessment",
            "## 6. Phase 5 Recommendations",
        ]
        for section in expected_sections:
            assert section in content, f"Missing section: {section}"

    def test_disjoint_models(self, tmp_path: Path) -> None:
        """Models that appear in only one track should still be included."""
        routing_dir = tmp_path / "routing"
        routing_dir.mkdir()
        query_dir = tmp_path / "query"
        query_dir.mkdir()

        routing_summary = {
            "timestamps": {},
            "models": [_make_routing_model(model_id="routing-only", accuracy=70.0)],
        }
        query_summary = {
            "timestamps": {},
            "models": [_make_query_model(model_id="query-only", query_accuracy=80.0)],
        }

        (routing_dir / "summary.json").write_text(json.dumps(routing_summary))
        (query_dir / "query_summary.json").write_text(json.dumps(query_summary))

        output_path = tmp_path / "report.md"
        generate_combined_report(routing_dir, query_dir, output_path)

        content = output_path.read_text()
        assert "routing-only" in content
        assert "query-only" in content
        assert "Models in both tracks:** 0" in content

    def test_missing_routing_models(self, tmp_path: Path) -> None:
        routing_dir = tmp_path / "routing"
        routing_dir.mkdir()
        query_dir = tmp_path / "query"
        query_dir.mkdir()

        (routing_dir / "summary.json").write_text(json.dumps({"timestamps": {}}))
        (query_dir / "query_summary.json").write_text(
            json.dumps({"timestamps": {}, "models": [_make_query_model()]})
        )

        with pytest.raises(ValueError, match="routing summary"):
            generate_combined_report(routing_dir, query_dir, tmp_path / "out.md")

    def test_nested_directory_creation(self, tmp_path: Path) -> None:
        """Test that nested output directories are created (#24)."""
        routing_dir = tmp_path / "routing"
        routing_dir.mkdir()
        query_dir = tmp_path / "query"
        query_dir.mkdir()

        (routing_dir / "summary.json").write_text(
            json.dumps(
                {
                    "timestamps": {},
                    "models": [_make_routing_model(model_id="m1")],
                }
            )
        )
        (query_dir / "query_summary.json").write_text(
            json.dumps(
                {
                    "timestamps": {},
                    "models": [_make_query_model(model_id="m1")],
                }
            )
        )

        output_path = tmp_path / "sub" / "dir" / "report.md"
        result = generate_combined_report(routing_dir, query_dir, output_path)
        assert result == output_path
        assert output_path.exists()

    def test_missing_query_models(self, tmp_path: Path) -> None:
        routing_dir = tmp_path / "routing"
        routing_dir.mkdir()
        query_dir = tmp_path / "query"
        query_dir.mkdir()

        (routing_dir / "summary.json").write_text(
            json.dumps({"timestamps": {}, "models": [_make_routing_model()]})
        )
        (query_dir / "query_summary.json").write_text(json.dumps({"timestamps": {}}))

        with pytest.raises(ValueError, match="query summary"):
            generate_combined_report(routing_dir, query_dir, tmp_path / "out.md")


# ---------------------------------------------------------------------------
# Tests: CLI main()
# ---------------------------------------------------------------------------


class TestMain:
    def test_default_arguments(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        routing_dir = tmp_path / "routing"
        routing_dir.mkdir()
        query_dir = tmp_path / "query"
        query_dir.mkdir()

        (routing_dir / "summary.json").write_text(
            json.dumps(
                {
                    "timestamps": {},
                    "models": [_make_routing_model(model_id="claude-test")],
                }
            )
        )
        (query_dir / "query_summary.json").write_text(
            json.dumps(
                {
                    "timestamps": {},
                    "models": [_make_query_model(model_id="claude-test")],
                }
            )
        )

        output = tmp_path / "report.md"
        main(
            [
                "--routing-dir",
                str(routing_dir),
                "--query-dir",
                str(query_dir),
                "--output",
                str(output),
            ]
        )

        assert output.exists()
        captured = capsys.readouterr()
        assert "Report written to" in captured.out
