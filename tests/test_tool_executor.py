"""Tests for ToolExecutor against sample DatabaseStateSnapshots.

Covers each tool method: filtering, edge cases (empty results, unknown
IDs), and JSON serialization of results.
"""

from __future__ import annotations

import json

import pytest

from src.simulator.schema import DatabaseStateSnapshot
from src.tools.executor import ToolExecutor


@pytest.fixture()
def sample_snapshot() -> DatabaseStateSnapshot:
    """A snapshot with 4 orders and 2 slides for testing."""
    return DatabaseStateSnapshot(
        orders=(
            {
                "order_id": "ORD-001",
                "current_state": "ACCEPTED",
                "specimen_type": "biopsy",
                "anatomic_site": "breast",
                "priority": "routine",
                "flags": [],
            },
            {
                "order_id": "ORD-002",
                "current_state": "ACCEPTED",
                "specimen_type": "excision",
                "anatomic_site": "breast",
                "priority": "rush",
                "flags": ["FIXATION_WARNING"],
            },
            {
                "order_id": "ORD-003",
                "current_state": "HE_QC",
                "specimen_type": "biopsy",
                "anatomic_site": "breast",
                "priority": "routine",
                "flags": [],
            },
            {
                "order_id": "ORD-004",
                "current_state": "RESULTING",
                "specimen_type": "resection",
                "anatomic_site": "breast",
                "priority": "rush",
                "flags": ["MISSING_INFO_PROCEED"],
            },
        ),
        slides=(
            {
                "slide_id": "SLD-001",
                "order_id": "ORD-003",
                "stain_type": "H&E",
                "status": "stained",
            },
            {
                "slide_id": "SLD-002",
                "order_id": "ORD-003",
                "stain_type": "ER",
                "status": "pending",
            },
        ),
    )


@pytest.fixture()
def executor(sample_snapshot: DatabaseStateSnapshot) -> ToolExecutor:
    return ToolExecutor(sample_snapshot)


class TestExecuteDispatch:
    def test_unknown_tool_returns_error(self, executor: ToolExecutor) -> None:
        result = json.loads(executor.execute("nonexistent_tool", {}))
        assert "error" in result
        assert "Unknown tool" in result["error"]

    def test_execute_returns_json_string(self, executor: ToolExecutor) -> None:
        result = executor.execute("list_orders", {})
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert isinstance(parsed, list)

    def test_known_tool_dispatches(self, executor: ToolExecutor) -> None:
        result = json.loads(executor.execute("get_order", {"order_id": "ORD-001"}))
        assert result["order_id"] == "ORD-001"

    def test_unexpected_keyword_returns_error(self, executor: ToolExecutor) -> None:
        result = json.loads(
            executor.execute("get_order", {"order_id": "ORD-001", "extra_arg": "val"})
        )
        assert "error" in result
        assert "Invalid arguments" in result["error"]

    def test_missing_required_arg_returns_error(self, executor: ToolExecutor) -> None:
        result = json.loads(executor.execute("get_order", {}))
        assert "error" in result
        assert "Invalid arguments" in result["error"]


class TestListOrders:
    def test_no_filters_returns_all(self, executor: ToolExecutor) -> None:
        result = json.loads(executor.execute("list_orders", {}))
        assert len(result) == 4

    def test_filter_by_state(self, executor: ToolExecutor) -> None:
        result = json.loads(executor.execute("list_orders", {"state": "ACCEPTED"}))
        assert len(result) == 2
        assert all(o["current_state"] == "ACCEPTED" for o in result)

    def test_filter_by_state_no_match(self, executor: ToolExecutor) -> None:
        result = json.loads(executor.execute("list_orders", {"state": "ORDER_COMPLETE"}))
        assert result == []

    def test_filter_by_priority(self, executor: ToolExecutor) -> None:
        result = json.loads(executor.execute("list_orders", {"priority": "rush"}))
        assert len(result) == 2
        assert all(o["priority"] == "rush" for o in result)

    def test_filter_has_flags_true(self, executor: ToolExecutor) -> None:
        result = json.loads(executor.execute("list_orders", {"has_flags": True}))
        assert len(result) == 2
        for order in result:
            assert len(order["flags"]) > 0

    def test_filter_has_flags_false(self, executor: ToolExecutor) -> None:
        result = json.loads(executor.execute("list_orders", {"has_flags": False}))
        assert len(result) == 2
        for order in result:
            assert order["flags"] == []

    def test_combined_filters(self, executor: ToolExecutor) -> None:
        result = json.loads(
            executor.execute("list_orders", {"state": "ACCEPTED", "priority": "rush"})
        )
        assert len(result) == 1
        assert result[0]["order_id"] == "ORD-002"

    def test_combined_state_and_flags(self, executor: ToolExecutor) -> None:
        result = json.loads(
            executor.execute("list_orders", {"state": "ACCEPTED", "has_flags": True})
        )
        assert len(result) == 1
        assert result[0]["order_id"] == "ORD-002"

    def test_combined_all_three_filters(self, executor: ToolExecutor) -> None:
        result = json.loads(
            executor.execute(
                "list_orders", {"state": "ACCEPTED", "priority": "rush", "has_flags": True}
            )
        )
        assert len(result) == 1
        assert result[0]["order_id"] == "ORD-002"


class TestGetOrder:
    def test_existing_order(self, executor: ToolExecutor) -> None:
        result = json.loads(executor.execute("get_order", {"order_id": "ORD-001"}))
        assert result["order_id"] == "ORD-001"
        assert result["current_state"] == "ACCEPTED"
        assert result["specimen_type"] == "biopsy"

    def test_nonexistent_order(self, executor: ToolExecutor) -> None:
        result = json.loads(executor.execute("get_order", {"order_id": "ORD-999"}))
        assert "error" in result
        assert "not found" in result["error"].lower()

    def test_returns_all_fields(self, executor: ToolExecutor) -> None:
        result = json.loads(executor.execute("get_order", {"order_id": "ORD-002"}))
        assert result["flags"] == ["FIXATION_WARNING"]
        assert result["priority"] == "rush"


class TestGetSlides:
    def test_order_with_slides(self, executor: ToolExecutor) -> None:
        result = json.loads(executor.execute("get_slides", {"order_id": "ORD-003"}))
        assert len(result) == 2
        slide_ids = {s["slide_id"] for s in result}
        assert slide_ids == {"SLD-001", "SLD-002"}

    def test_order_without_slides(self, executor: ToolExecutor) -> None:
        result = json.loads(executor.execute("get_slides", {"order_id": "ORD-001"}))
        assert result == []

    def test_nonexistent_order_returns_error(self, executor: ToolExecutor) -> None:
        result = json.loads(executor.execute("get_slides", {"order_id": "ORD-999"}))
        assert "error" in result
        assert "not found" in result["error"].lower()


class TestGetStateInfo:
    def test_known_state(self, executor: ToolExecutor) -> None:
        result = json.loads(executor.execute("get_state_info", {"state_id": "ACCEPTED"}))
        assert result["state_id"] == "ACCEPTED"
        assert "phase" in result
        assert "description" in result
        assert "terminal" in result
        assert result["terminal"] is False

    def test_terminal_state(self, executor: ToolExecutor) -> None:
        result = json.loads(executor.execute("get_state_info", {"state_id": "ORDER_COMPLETE"}))
        assert result["terminal"] is True

    def test_unknown_state(self, executor: ToolExecutor) -> None:
        result = json.loads(executor.execute("get_state_info", {"state_id": "NONEXISTENT"}))
        assert "error" in result
        assert "Unknown state" in result["error"]


class TestGetFlagInfo:
    def test_known_flag(self, executor: ToolExecutor) -> None:
        result = json.loads(executor.execute("get_flag_info", {"flag_id": "MISSING_INFO_PROCEED"}))
        assert result["flag_id"] == "MISSING_INFO_PROCEED"
        assert "effect" in result
        assert "cleared_by" in result
        assert "set_at" in result

    def test_unknown_flag(self, executor: ToolExecutor) -> None:
        result = json.loads(executor.execute("get_flag_info", {"flag_id": "NONEXISTENT"}))
        assert "error" in result
        assert "Unknown flag" in result["error"]


class TestMinimalSnapshot:
    """Edge case: snapshot with minimal data (one order, no slides)."""

    @pytest.fixture()
    def minimal_executor(self) -> ToolExecutor:
        snapshot = DatabaseStateSnapshot(
            orders=(
                {
                    "order_id": "ORD-SOLO",
                    "current_state": "ACCESSIONING",
                    "specimen_type": "biopsy",
                    "anatomic_site": "breast",
                    "priority": "routine",
                    "flags": [],
                },
            ),
            slides=(),
        )
        return ToolExecutor(snapshot)

    def test_list_orders_single(self, minimal_executor: ToolExecutor) -> None:
        result = json.loads(minimal_executor.execute("list_orders", {}))
        assert len(result) == 1

    def test_get_slides_empty(self, minimal_executor: ToolExecutor) -> None:
        result = json.loads(minimal_executor.execute("get_slides", {"order_id": "ORD-SOLO"}))
        assert result == []
