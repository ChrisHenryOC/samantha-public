"""Tool-use-specific metric computation for query evaluation results.

Extends the standard query metrics with tool-use dimensions: tool call
counts, turns per scenario, max-turns-hit rate, and most-used tools.
Operates on the same ``QueryResult`` objects as the standard metrics —
tool-use metadata is stored in ``QueryDecision.model_output``.
"""

from __future__ import annotations

import statistics
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from src.evaluation.query_metrics import (
    QueryModelMetrics,
    QueryResult,
    compute_query_model_metrics,
)


@dataclass(frozen=True)
class ToolUseModelMetrics:
    """Aggregated metrics for a single model across all tool-use query runs.

    Extends standard query metrics with tool-use dimensions.
    """

    # Standard query metrics (delegated)
    standard: QueryModelMetrics

    # Tool-use dimensions
    tool_calls_total: int
    tool_calls_per_scenario_mean: float
    turns_per_scenario_mean: float
    max_turns_hit_count: int
    most_used_tools: Mapping[str, int]

    def __post_init__(self) -> None:
        if not isinstance(self.standard, QueryModelMetrics):
            raise TypeError(
                f"standard must be QueryModelMetrics, got {type(self.standard).__name__}"
            )
        if not isinstance(self.tool_calls_total, int) or isinstance(self.tool_calls_total, bool):
            raise TypeError(
                f"tool_calls_total must be int, got {type(self.tool_calls_total).__name__}"
            )
        if self.tool_calls_total < 0:
            raise ValueError(f"tool_calls_total must be non-negative, got {self.tool_calls_total}")
        if not isinstance(self.max_turns_hit_count, int) or isinstance(
            self.max_turns_hit_count, bool
        ):
            raise TypeError(
                f"max_turns_hit_count must be int, got {type(self.max_turns_hit_count).__name__}"
            )
        if self.max_turns_hit_count < 0:
            raise ValueError(
                f"max_turns_hit_count must be non-negative, got {self.max_turns_hit_count}"
            )
        for field_name in ("tool_calls_per_scenario_mean", "turns_per_scenario_mean"):
            val = getattr(self, field_name)
            if not isinstance(val, (int, float)):
                raise TypeError(f"{field_name} must be numeric, got {type(val).__name__}")
            if val < 0:
                raise ValueError(f"{field_name} must be non-negative, got {val}")
        if not isinstance(self.most_used_tools, dict):
            raise TypeError(
                f"most_used_tools must be dict, got {type(self.most_used_tools).__name__}"
            )
        for key, count in self.most_used_tools.items():
            if not isinstance(key, str):
                raise TypeError(f"most_used_tools key must be str, got {type(key).__name__}")
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                raise ValueError(f"most_used_tools[{key!r}] must be non-negative int, got {count}")

    @property
    def model_id(self) -> str:
        return self.standard.model_id


def _extract_tool_use_metadata(result: QueryResult) -> dict[str, Any]:
    """Extract tool-use metadata from a QueryResult's decision model_output.

    Returns a dict with 'tool_calls' (list) and 'turns' (int) keys.
    Falls back to empty/zero if the metadata is not present (e.g. when
    the result came from a non-tool-use harness).
    """
    model_output = getattr(result.decision, "model_output", {})
    if not isinstance(model_output, dict):
        return {"tool_calls": [], "turns": 0}
    return {
        "tool_calls": model_output.get("tool_calls", []),
        "turns": model_output.get("turns", 0),
    }


def compute_tool_use_metrics(
    model_id: str,
    results: list[QueryResult],
    *,
    max_turns: int = 10,
) -> ToolUseModelMetrics:
    """Compute standard + tool-use metrics for a model's results.

    Args:
        model_id: The model identifier to filter results.
        results: All query results (may include multiple models).
        max_turns: The max-turns limit used during evaluation.

    Returns:
        ToolUseModelMetrics with both standard and tool-use dimensions.
    """
    standard = compute_query_model_metrics(model_id, results)
    model_results = [r for r in results if r.model_id == model_id]

    total_tool_calls = 0
    tool_name_counter: Counter[str] = Counter()
    turns_list: list[int] = []
    max_turns_hit = 0

    for r in model_results:
        meta = _extract_tool_use_metadata(r)
        tool_calls = meta["tool_calls"]
        turns = meta["turns"]

        if isinstance(tool_calls, list):
            total_tool_calls += len(tool_calls)
            for tc in tool_calls:
                if isinstance(tc, dict) and "tool_name" in tc:
                    tool_name_counter[tc["tool_name"]] += 1

        if isinstance(turns, int):
            turns_list.append(turns)
            if turns >= max_turns:
                max_turns_hit += 1

    n = len(model_results)
    tool_calls_per_scenario = total_tool_calls / n if n else 0.0
    turns_per_scenario = statistics.mean(turns_list) if turns_list else 0.0

    return ToolUseModelMetrics(
        standard=standard,
        tool_calls_total=total_tool_calls,
        tool_calls_per_scenario_mean=tool_calls_per_scenario,
        turns_per_scenario_mean=turns_per_scenario,
        max_turns_hit_count=max_turns_hit,
        most_used_tools=dict(tool_name_counter.most_common()),
    )
