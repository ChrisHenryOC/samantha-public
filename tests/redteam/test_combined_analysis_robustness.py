"""Red-team tests for src/evaluation/combined_analysis.py — merge, assessment, formatting."""

from __future__ import annotations

from typing import Any

import pytest

from src.evaluation.combined_analysis import (
    format_capability_matrix,
    format_cross_track_analysis,
    format_go_no_go_assessment,
    format_phase5_recommendations,
    format_unified_scorecard,
    merge_model_data,
)
from src.evaluation.combined_analysis import (
    format_executive_summary as format_combined_executive_summary,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _routing_model(model_id: str, accuracy: float = 80.0, **kwargs: Any) -> dict[str, Any]:
    """Build a minimal routing model dict."""
    return {
        "model_id": model_id,
        "accuracy": accuracy,
        "rule_accuracy": kwargs.get("rule_accuracy", accuracy),
        "flag_accuracy": kwargs.get("flag_accuracy", accuracy),
        "false_positive_rate": kwargs.get("false_positive_rate", 5.0),
        "scenario_reliability": kwargs.get("scenario_reliability", 60.0),
        "accuracy_std": kwargs.get("accuracy_std"),
        "rule_accuracy_std": kwargs.get("rule_accuracy_std"),
        "flag_accuracy_std": kwargs.get("flag_accuracy_std"),
        "accuracy_by_category": kwargs.get("accuracy_by_category", {}),
        "failure_counts": kwargs.get("failure_counts", {}),
        "latency_mean_ms": kwargs.get("latency_mean_ms", 500.0),
        "latency_p50_ms": kwargs.get("latency_p50_ms", 400.0),
        "latency_p95_ms": kwargs.get("latency_p95_ms", 900.0),
        "token_input_mean": kwargs.get("token_input_mean", 1000.0),
        "token_output_mean": kwargs.get("token_output_mean", 100.0),
    }


def _query_model(model_id: str, query_accuracy: float = 75.0, **kwargs: Any) -> dict[str, Any]:
    """Build a minimal query model dict."""
    return {
        "model_id": model_id,
        "query_accuracy": query_accuracy,
        "scenario_reliability": kwargs.get("scenario_reliability", 50.0),
        "accuracy_std": kwargs.get("accuracy_std"),
        "latency_mean_ms": kwargs.get("latency_mean_ms", 600.0),
        "latency_p50_ms": kwargs.get("latency_p50_ms", 500.0),
        "latency_p95_ms": kwargs.get("latency_p95_ms", 1000.0),
        "mean_precision": kwargs.get("mean_precision", 0.8),
        "mean_recall": kwargs.get("mean_recall", 0.75),
        "mean_f1": kwargs.get("mean_f1", 0.77),
        "token_input_mean": kwargs.get("token_input_mean", 1200.0),
        "token_output_mean": kwargs.get("token_output_mean", 120.0),
        "failure_counts": kwargs.get("failure_counts", {}),
        "query_accuracy_by_tier": kwargs.get("query_accuracy_by_tier", {}),
        "query_accuracy_by_answer_type": kwargs.get("query_accuracy_by_answer_type", {}),
    }


# ---------------------------------------------------------------------------
# merge_model_data
# ---------------------------------------------------------------------------


class TestMergeModelData:
    """Edge cases for merge_model_data."""

    def test_both_empty(self) -> None:
        result = merge_model_data([], [])
        assert result == []

    def test_routing_only(self) -> None:
        result = merge_model_data([_routing_model("m1")], [])
        assert len(result) == 1
        assert result[0]["routing"] is not None
        assert result[0]["query"] is None

    def test_query_only(self) -> None:
        result = merge_model_data([], [_query_model("m1")])
        assert len(result) == 1
        assert result[0]["routing"] is None
        assert result[0]["query"] is not None

    def test_overlapping_models(self) -> None:
        result = merge_model_data(
            [_routing_model("m1", accuracy=90.0)],
            [_query_model("m1", query_accuracy=80.0)],
        )
        assert len(result) == 1
        assert result[0]["routing"] is not None
        assert result[0]["query"] is not None

    def test_combined_score_math(self) -> None:
        result = merge_model_data(
            [_routing_model("m1", accuracy=90.0)],
            [_query_model("m1", query_accuracy=80.0)],
        )
        assert result[0]["combined_score"] == 85.0  # (90+80)/2

    def test_sort_order_descending(self) -> None:
        result = merge_model_data(
            [_routing_model("low", accuracy=50.0), _routing_model("high", accuracy=95.0)],
            [],
        )
        assert result[0]["model_id"] == "high"
        assert result[1]["model_id"] == "low"

    def test_missing_model_id_in_routing_raises(self) -> None:
        with pytest.raises(ValueError, match="missing 'model_id'"):
            merge_model_data([{"accuracy": 80.0}], [])

    def test_missing_model_id_in_query_raises(self) -> None:
        with pytest.raises(ValueError, match="missing 'model_id'"):
            merge_model_data([], [{"query_accuracy": 75.0}])

    def test_cloud_detection_claude_prefix(self) -> None:
        result = merge_model_data([_routing_model("claude-opus-4-6")], [])
        assert result[0]["is_cloud"] is True

    def test_local_detection(self) -> None:
        result = merge_model_data([_routing_model("llama-3.1-8b")], [])
        assert result[0]["is_cloud"] is False


# ---------------------------------------------------------------------------
# format_go_no_go_assessment
# ---------------------------------------------------------------------------


class TestFormatGoNoGoAssessment:
    """Edge cases for go/no-go assessment formatting."""

    def _merged(self, **overrides: Any) -> list[dict[str, Any]]:
        """Build a single-model merged list with optional overrides."""
        defaults = {
            "model_id": "test-model",
            "is_cloud": False,
            "routing": _routing_model(
                "test-model",
                accuracy=85.0,
                scenario_reliability=60.0,
                accuracy_std=1.5,
            ),
            "query": _query_model(
                "test-model",
                query_accuracy=75.0,
                scenario_reliability=50.0,
            ),
            "combined_score": 80.0,
        }
        defaults.update(overrides)
        return [defaults]

    def test_no_feasible_models(self) -> None:
        m = self._merged()
        m[0]["routing"]["accuracy"] = 50.0
        m[0]["query"]["query_accuracy"] = 50.0
        text = format_go_no_go_assessment(m)
        assert "No models achieve" in text

    def test_one_at_exactly_80(self) -> None:
        m = self._merged()
        m[0]["routing"]["accuracy"] = 80.0
        text = format_go_no_go_assessment(m)
        assert "feasible" in text.lower()

    def test_query_feasible_routing_not(self) -> None:
        m = self._merged()
        m[0]["routing"]["accuracy"] = 50.0
        m[0]["query"]["query_accuracy"] = 85.0
        text = format_go_no_go_assessment(m)
        assert "Query task is feasible" in text

    def test_both_feasible(self) -> None:
        m = self._merged()
        m[0]["routing"]["accuracy"] = 90.0
        m[0]["query"]["query_accuracy"] = 90.0
        text = format_go_no_go_assessment(m)
        assert "feasible" in text.lower()

    def test_no_cloud_models(self) -> None:
        m = self._merged()
        text = format_go_no_go_assessment(m)
        assert "Insufficient data" in text
        assert "need both cloud and local" in text

    def test_no_local_models(self) -> None:
        m = self._merged()
        m[0]["is_cloud"] = True
        m[0]["model_id"] = "claude-test"
        text = format_go_no_go_assessment(m)
        assert "Insufficient data" in text
        assert "need both cloud and local" in text

    def test_large_cloud_local_gap(self) -> None:
        cloud = {
            "model_id": "claude-test",
            "is_cloud": True,
            "routing": _routing_model("claude-test", accuracy=95.0),
            "query": _query_model("claude-test", query_accuracy=95.0),
            "combined_score": 95.0,
        }
        local = {
            "model_id": "local-test",
            "is_cloud": False,
            "routing": _routing_model("local-test", accuracy=50.0),
            "query": _query_model("local-test", query_accuracy=50.0),
            "combined_score": 50.0,
        }
        text = format_go_no_go_assessment([cloud, local])
        assert "Significant headroom" in text

    def test_small_cloud_local_gap(self) -> None:
        cloud = {
            "model_id": "claude-test",
            "is_cloud": True,
            "routing": _routing_model("claude-test", accuracy=82.0),
            "query": _query_model("claude-test", query_accuracy=82.0),
            "combined_score": 82.0,
        }
        local = {
            "model_id": "local-test",
            "is_cloud": False,
            "routing": _routing_model("local-test", accuracy=80.0),
            "query": _query_model("local-test", query_accuracy=80.0),
            "combined_score": 80.0,
        }
        text = format_go_no_go_assessment([cloud, local])
        assert "Minimal gap" in text

    def test_moderate_gap(self) -> None:
        cloud = {
            "model_id": "claude-test",
            "is_cloud": True,
            "routing": _routing_model("claude-test", accuracy=90.0),
            "query": _query_model("claude-test", query_accuracy=90.0),
            "combined_score": 90.0,
        }
        local = {
            "model_id": "local-test",
            "is_cloud": False,
            "routing": _routing_model("local-test", accuracy=80.0),
            "query": _query_model("local-test", query_accuracy=80.0),
            "combined_score": 80.0,
        }
        text = format_go_no_go_assessment([cloud, local])
        assert "Moderate headroom" in text

    def test_no_variance_data(self) -> None:
        m = self._merged()
        m[0]["routing"]["accuracy_std"] = None
        text = format_go_no_go_assessment(m)
        assert "No multi-run variance" in text


# ---------------------------------------------------------------------------
# format_capability_matrix
# ---------------------------------------------------------------------------


class TestFormatCapabilityMatrix:
    """Edge cases for capability matrix formatting."""

    def _merged_entry(
        self,
        routing_acc: float | None = None,
        query_acc: float | None = None,
        **kw: Any,
    ) -> dict[str, Any]:
        routing = (
            _routing_model("m", accuracy=routing_acc, **kw) if routing_acc is not None else None
        )
        query = _query_model("m", query_accuracy=query_acc) if query_acc is not None else None
        return {
            "model_id": "m",
            "is_cloud": False,
            "routing": routing,
            "query": query,
            "combined_score": 0.0,
        }

    def test_strong_rating(self) -> None:
        text = format_capability_matrix([self._merged_entry(routing_acc=95.0, query_acc=92.0)])
        assert "Strong" in text

    def test_moderate_rating(self) -> None:
        text = format_capability_matrix([self._merged_entry(routing_acc=75.0, query_acc=72.0)])
        assert "Moderate" in text

    def test_weak_rating(self) -> None:
        text = format_capability_matrix([self._merged_entry(routing_acc=45.0, query_acc=42.0)])
        assert "Weak" in text

    def test_poor_rating(self) -> None:
        text = format_capability_matrix([self._merged_entry(routing_acc=30.0, query_acc=30.0)])
        assert "Poor" in text

    def test_na_routing(self) -> None:
        text = format_capability_matrix([self._merged_entry(query_acc=80.0)])
        assert "N/A" in text

    def test_high_consistency(self) -> None:
        text = format_capability_matrix([self._merged_entry(routing_acc=90.0, accuracy_std=0.5)])
        assert "High" in text

    def test_fast_latency(self) -> None:
        entry = self._merged_entry(routing_acc=90.0, latency_p50_ms=500.0)
        text = format_capability_matrix([entry])
        assert "Fast" in text

    def test_slow_latency(self) -> None:
        entry = self._merged_entry(routing_acc=90.0, latency_p50_ms=5000.0)
        text = format_capability_matrix([entry])
        assert "Slow" in text


# ---------------------------------------------------------------------------
# format_phase5_recommendations
# ---------------------------------------------------------------------------


class TestFormatPhase5Recommendations:
    """Edge cases for Phase 5 recommendation formatting."""

    def test_no_promising_models(self) -> None:
        entry = {
            "model_id": "bad-model",
            "is_cloud": False,
            "routing": _routing_model("bad-model", accuracy=10.0),
            "query": None,
            "combined_score": 10.0,
        }
        text = format_phase5_recommendations([entry])
        # Should mention models to exclude or lack of promising models
        assert "Exclude" in text or "below 20%" in text

    def test_promising_identified(self) -> None:
        entry = {
            "model_id": "good-model",
            "is_cloud": False,
            "routing": _routing_model("good-model", accuracy=60.0),
            "query": None,
            "combined_score": 60.0,
        }
        text = format_phase5_recommendations([entry])
        assert "Priority Models" in text
        assert "good-model" in text

    def test_non_viable_excluded(self) -> None:
        entry = {
            "model_id": "bad-model",
            "is_cloud": False,
            "routing": _routing_model("bad-model", accuracy=15.0),
            "query": None,
            "combined_score": 15.0,
        }
        text = format_phase5_recommendations([entry])
        assert "Exclude" in text or "below 20%" in text

    def test_empty_merged(self) -> None:
        text = format_phase5_recommendations([])
        # Should not crash; with no models, no Priority Models section appears
        assert "Insufficient data" in text


# ---------------------------------------------------------------------------
# Combined report end-to-end edge cases
# ---------------------------------------------------------------------------


class TestCombinedReportEndToEnd:
    """End-to-end edge cases for report generation inputs."""

    def test_missing_routing_summary_models(self) -> None:
        with pytest.raises(ValueError, match="missing 'model_id'"):
            merge_model_data([{"accuracy": 80.0}], [])

    def test_missing_query_summary_models(self) -> None:
        with pytest.raises(ValueError, match="missing 'model_id'"):
            merge_model_data([], [{"query_accuracy": 75.0}])

    def test_empty_models_both_tracks(self) -> None:
        result = merge_model_data([], [])
        assert result == []


# ---------------------------------------------------------------------------
# format_executive_summary (combined) (#6)
# ---------------------------------------------------------------------------


class TestFormatCombinedExecutiveSummary:
    """Red-team tests for combined format_executive_summary."""

    def _entry(
        self,
        model_id: str = "m",
        routing_acc: float = 80.0,
        query_acc: float | None = None,
    ) -> dict[str, Any]:
        routing = _routing_model(model_id, accuracy=routing_acc)
        query = _query_model(model_id, query_accuracy=query_acc) if query_acc is not None else None
        return {
            "model_id": model_id,
            "is_cloud": False,
            "routing": routing,
            "query": query,
            "combined_score": routing_acc,
        }

    def test_empty_merged(self) -> None:
        text = format_combined_executive_summary([], {}, {})
        assert "Total unique models:** 0" in text

    def test_routing_only(self) -> None:
        entry = self._entry(routing_acc=90.0)
        text = format_combined_executive_summary(
            [entry],
            {},
            {},
        )
        assert "routing 90.0%" in text
        assert "Models in routing baseline:** 1" in text

    def test_both_tracks(self) -> None:
        entry = self._entry(routing_acc=90.0, query_acc=85.0)
        text = format_combined_executive_summary(
            [entry],
            {},
            {},
        )
        assert "routing 90.0%" in text
        assert "query 85.0%" in text
        assert "Models in both tracks:** 1" in text


# ---------------------------------------------------------------------------
# format_unified_scorecard (#6)
# ---------------------------------------------------------------------------


class TestFormatUnifiedScorecardEdgeCases:
    """Red-team tests for format_unified_scorecard."""

    def _entry(self, **kw: Any) -> dict[str, Any]:
        return {
            "model_id": kw.get("model_id", "m"),
            "is_cloud": kw.get("is_cloud", False),
            "routing": kw.get("routing", _routing_model("m")),
            "query": kw.get("query"),
            "combined_score": 0.0,
        }

    def test_empty_merged(self) -> None:
        text = format_unified_scorecard([])
        assert "Unified Scorecard" in text

    def test_routing_only_model(self) -> None:
        text = format_unified_scorecard([self._entry()])
        assert "Local" in text
        # Query columns should show "—"
        assert "\u2014" in text

    def test_cloud_model(self) -> None:
        text = format_unified_scorecard(
            [self._entry(is_cloud=True)],
        )
        assert "Cloud" in text

    def test_variance_shown(self) -> None:
        r = _routing_model("m", accuracy_std=2.0)
        text = format_unified_scorecard(
            [self._entry(routing=r)],
        )
        assert "±2.0" in text

    def test_no_variance(self) -> None:
        r = _routing_model("m", accuracy_std=None)
        text = format_unified_scorecard(
            [self._entry(routing=r)],
        )
        # Should show em dash for missing variance
        assert "\u2014" in text


# ---------------------------------------------------------------------------
# format_cross_track_analysis (#6)
# ---------------------------------------------------------------------------


class TestFormatCrossTrackAnalysisEdgeCases:
    """Red-team tests for format_cross_track_analysis."""

    def _entry(
        self,
        model_id: str = "m",
        routing_acc: float = 80.0,
        query_acc: float = 75.0,
    ) -> dict[str, Any]:
        return {
            "model_id": model_id,
            "is_cloud": False,
            "routing": _routing_model(
                model_id,
                accuracy=routing_acc,
            ),
            "query": _query_model(
                model_id,
                query_accuracy=query_acc,
            ),
            "combined_score": (routing_acc + query_acc) / 2,
        }

    def test_no_both_track_models(self) -> None:
        entry = {
            "model_id": "m",
            "is_cloud": False,
            "routing": _routing_model("m"),
            "query": None,
            "combined_score": 0.0,
        }
        text = format_cross_track_analysis([entry])
        assert "No models evaluated on both tracks" in text

    def test_routing_stronger(self) -> None:
        entry = self._entry(routing_acc=90.0, query_acc=70.0)
        text = format_cross_track_analysis([entry])
        assert "Routing" in text
        assert "+20.0" in text

    def test_query_stronger(self) -> None:
        entry = self._entry(routing_acc=70.0, query_acc=90.0)
        text = format_cross_track_analysis([entry])
        assert "Query" in text

    def test_balanced(self) -> None:
        entry = self._entry(routing_acc=80.0, query_acc=79.0)
        text = format_cross_track_analysis([entry])
        assert "Balanced" in text

    def test_ranking_consistency(self) -> None:
        e1 = self._entry("m1", routing_acc=90.0, query_acc=85.0)
        e2 = self._entry("m2", routing_acc=80.0, query_acc=75.0)
        text = format_cross_track_analysis([e1, e2])
        assert "ranking is identical" in text

    def test_ranking_differs(self) -> None:
        e1 = self._entry("m1", routing_acc=90.0, query_acc=70.0)
        e2 = self._entry("m2", routing_acc=80.0, query_acc=95.0)
        text = format_cross_track_analysis([e1, e2])
        assert "ranking differs" in text
