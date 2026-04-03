"""Tests for tool-use-specific metric computation (Phase 7d).

Tests cover ToolUseModelMetrics computation from mock QueryResult lists
with tool-use metadata in model_output.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from src.evaluation.query_metrics import QueryResult
from src.evaluation.tool_use_metrics import ToolUseModelMetrics, compute_tool_use_metrics
from src.workflow.query_validator import QueryFailureType, QueryValidationResult

# --- Mock decision that satisfies QueryDecisionLike ---


@dataclass
class MockDecision:
    """Minimal QueryDecisionLike with tool-use metadata."""

    predicted_order_ids: list[str]
    expected_order_ids: list[str]
    latency_ms: int
    input_tokens: int
    output_tokens: int
    model_output: dict[str, Any]


def _make_result(
    *,
    scenario_id: str = "QR-001",
    tier: int = 1,
    answer_type: str = "order_list",
    model_id: str = "test-model",
    run_number: int = 1,
    correct: bool = True,
    tool_calls: list[dict[str, Any]] | None = None,
    turns: int = 1,
    failure_type: QueryFailureType | None = None,
) -> QueryResult:
    predicted = ["ORD-101"] if correct else ["ORD-999"]
    expected = ["ORD-101"]
    validation = QueryValidationResult(
        order_ids_correct=correct,
        precision=1.0 if correct else 0.0,
        recall=1.0 if correct else 0.0,
        f1=1.0 if correct else 0.0,
    )
    decision = MockDecision(
        predicted_order_ids=predicted,
        expected_order_ids=expected,
        latency_ms=100,
        input_tokens=50,
        output_tokens=30,
        model_output={
            "tool_calls": tool_calls or [],
            "turns": turns,
            "order_ids": predicted,
            "reasoning": "test",
        },
    )
    return QueryResult(
        scenario_id=scenario_id,
        tier=tier,
        answer_type=answer_type,
        model_id=model_id,
        run_number=run_number,
        decision=decision,
        validation=validation,
        failure_type=failure_type,
    )


# ===========================================================================
# ToolUseModelMetrics computation tests
# ===========================================================================


class TestComputeToolUseMetrics:
    def test_basic_metrics(self) -> None:
        results = [
            _make_result(
                tool_calls=[
                    {"tool_name": "list_orders", "arguments": {}, "result": "[]", "turn": 1},
                    {
                        "tool_name": "get_order",
                        "arguments": {"order_id": "ORD-101"},
                        "result": "{}",
                        "turn": 1,
                    },
                ],
                turns=2,
            ),
        ]
        metrics = compute_tool_use_metrics("test-model", results)

        assert isinstance(metrics, ToolUseModelMetrics)
        assert metrics.model_id == "test-model"
        assert metrics.tool_calls_total == 2
        assert metrics.tool_calls_per_scenario_mean == 2.0
        assert metrics.turns_per_scenario_mean == 2.0
        assert metrics.max_turns_hit_count == 0
        assert metrics.most_used_tools == {"list_orders": 1, "get_order": 1}

    def test_max_turns_hit(self) -> None:
        results = [
            _make_result(turns=10, correct=False),
        ]
        metrics = compute_tool_use_metrics("test-model", results, max_turns=10)
        assert metrics.max_turns_hit_count == 1

    def test_no_tool_calls(self) -> None:
        results = [_make_result(tool_calls=[], turns=1)]
        metrics = compute_tool_use_metrics("test-model", results)
        assert metrics.tool_calls_total == 0
        assert metrics.tool_calls_per_scenario_mean == 0.0
        assert metrics.most_used_tools == {}

    def test_multiple_scenarios(self) -> None:
        results = [
            _make_result(
                scenario_id="QR-001",
                tool_calls=[
                    {"tool_name": "list_orders", "arguments": {}, "result": "[]", "turn": 1},
                ],
                turns=2,
            ),
            _make_result(
                scenario_id="QR-002",
                tool_calls=[
                    {"tool_name": "list_orders", "arguments": {}, "result": "[]", "turn": 1},
                    {"tool_name": "list_orders", "arguments": {}, "result": "[]", "turn": 2},
                    {
                        "tool_name": "get_order",
                        "arguments": {"order_id": "ORD-101"},
                        "result": "{}",
                        "turn": 2,
                    },
                ],
                turns=3,
            ),
        ]
        metrics = compute_tool_use_metrics("test-model", results)
        assert metrics.tool_calls_total == 4
        assert metrics.tool_calls_per_scenario_mean == 2.0
        assert metrics.turns_per_scenario_mean == 2.5
        assert metrics.most_used_tools["list_orders"] == 3
        assert metrics.most_used_tools["get_order"] == 1

    def test_standard_metrics_delegated(self) -> None:
        results = [_make_result()]
        metrics = compute_tool_use_metrics("test-model", results)
        assert metrics.standard.query_accuracy == 100.0
        assert metrics.standard.model_id == "test-model"

    def test_filters_by_model_id(self) -> None:
        results = [
            _make_result(model_id="model-a"),
            _make_result(model_id="model-b"),
        ]
        metrics = compute_tool_use_metrics("model-a", results)
        assert metrics.standard.model_id == "model-a"


class TestToolUseModelMetricsValidation:
    def test_negative_tool_calls_total_raises(self) -> None:
        from src.evaluation.query_metrics import QueryModelMetrics

        standard = QueryModelMetrics(
            model_id="test",
            query_accuracy=0.0,
            query_accuracy_by_tier={},
            query_accuracy_by_answer_type={},
            mean_precision=0.0,
            mean_recall=0.0,
            mean_f1=0.0,
            scenario_reliability=0.0,
            accuracy_std=None,
            latency_mean_ms=0.0,
            latency_p50_ms=0.0,
            latency_p95_ms=0.0,
            token_input_mean=0.0,
            token_output_mean=0.0,
            total_cost_usd=None,
            failure_counts={},
        )
        with pytest.raises(ValueError, match="non-negative"):
            ToolUseModelMetrics(
                standard=standard,
                tool_calls_total=-1,
                tool_calls_per_scenario_mean=0.0,
                turns_per_scenario_mean=0.0,
                max_turns_hit_count=0,
                most_used_tools={},
            )

    def test_negative_float_field_raises(self) -> None:
        from src.evaluation.query_metrics import QueryModelMetrics

        standard = QueryModelMetrics(
            model_id="test",
            query_accuracy=0.0,
            query_accuracy_by_tier={},
            query_accuracy_by_answer_type={},
            mean_precision=0.0,
            mean_recall=0.0,
            mean_f1=0.0,
            scenario_reliability=0.0,
            accuracy_std=None,
            latency_mean_ms=0.0,
            latency_p50_ms=0.0,
            latency_p95_ms=0.0,
            token_input_mean=0.0,
            token_output_mean=0.0,
            total_cost_usd=None,
            failure_counts={},
        )
        with pytest.raises(ValueError, match="non-negative"):
            ToolUseModelMetrics(
                standard=standard,
                tool_calls_total=0,
                tool_calls_per_scenario_mean=-1.0,
                turns_per_scenario_mean=0.0,
                max_turns_hit_count=0,
                most_used_tools={},
            )

    def test_invalid_most_used_tools_raises(self) -> None:
        from src.evaluation.query_metrics import QueryModelMetrics

        standard = QueryModelMetrics(
            model_id="test",
            query_accuracy=0.0,
            query_accuracy_by_tier={},
            query_accuracy_by_answer_type={},
            mean_precision=0.0,
            mean_recall=0.0,
            mean_f1=0.0,
            scenario_reliability=0.0,
            accuracy_std=None,
            latency_mean_ms=0.0,
            latency_p50_ms=0.0,
            latency_p95_ms=0.0,
            token_input_mean=0.0,
            token_output_mean=0.0,
            total_cost_usd=None,
            failure_counts={},
        )
        with pytest.raises(ValueError, match="non-negative int"):
            ToolUseModelMetrics(
                standard=standard,
                tool_calls_total=0,
                tool_calls_per_scenario_mean=0.0,
                turns_per_scenario_mean=0.0,
                max_turns_hit_count=0,
                most_used_tools={"get_order": -1},
            )


class TestExtractToolUseMetadataFallback:
    """#11: Non-dict model_output fallback."""

    def test_non_dict_model_output_returns_defaults(self) -> None:
        from src.evaluation.tool_use_metrics import _extract_tool_use_metadata

        result = _make_result()
        # Override model_output to be a non-dict
        object.__setattr__(result.decision, "model_output", "not a dict")
        meta = _extract_tool_use_metadata(result)
        assert meta["tool_calls"] == []
        assert meta["turns"] == 0

    def test_missing_model_output_returns_defaults(self) -> None:
        from src.evaluation.tool_use_metrics import _extract_tool_use_metadata

        @dataclass
        class MinimalDecision:
            predicted_order_ids: list[str]
            expected_order_ids: list[str]
            latency_ms: int
            input_tokens: int
            output_tokens: int
            # No model_output field

        decision = MinimalDecision(
            predicted_order_ids=["ORD-101"],
            expected_order_ids=["ORD-101"],
            latency_ms=100,
            input_tokens=50,
            output_tokens=30,
        )
        validation = QueryValidationResult(
            order_ids_correct=True,
            precision=1.0,
            recall=1.0,
            f1=1.0,
        )
        result = QueryResult(
            scenario_id="QR-001",
            tier=1,
            answer_type="order_list",
            model_id="test-model",
            run_number=1,
            decision=decision,
            validation=validation,
            failure_type=None,
        )
        meta = _extract_tool_use_metadata(result)
        assert meta["tool_calls"] == []
        assert meta["turns"] == 0


class TestComputeToolUseMetricsEdgeCases:
    """#10: Edge cases for compute_tool_use_metrics."""

    def test_unknown_model_id_raises(self) -> None:
        results = [_make_result(model_id="model-a")]
        with pytest.raises(ValueError, match="No results found"):
            compute_tool_use_metrics("nonexistent-model", results)
