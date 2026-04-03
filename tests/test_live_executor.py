"""Tests for the live tool executor."""

from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path

import pytest

from src.server.live_executor import LiveToolExecutor
from src.workflow.database import Database
from src.workflow.models import Event, Order, Slide

# --- Fixtures ---


def _make_order(
    order_id: str,
    state: str = "ACCESSIONING",
    priority: str = "routine",
    flags: list[str] | None = None,
) -> Order:
    return Order(
        order_id=order_id,
        scenario_id="live",
        patient_name="Jane Doe",
        patient_age=55,
        patient_sex="F",
        specimen_type="Core Needle Biopsy",
        anatomic_site="Left Breast",
        fixative="10% NBF",
        fixation_time_hours=12.0,
        ordered_tests=["ER", "PR", "HER2", "Ki-67"],
        priority=priority,
        billing_info_present=True,
        current_state=state,
        flags=flags or [],
    )


def _make_slide(
    slide_id: str,
    order_id: str,
    test: str = "H&E",
    status: str = "sectioned",
) -> Slide:
    return Slide(
        slide_id=slide_id,
        order_id=order_id,
        test_assignment=test,
        status=status,
    )


@pytest.fixture
def db(tmp_path: Path) -> Generator[Database, None, None]:
    """Create a temporary database with test data."""
    database = Database(tmp_path / "test.sqlite")
    with database:
        database.init_db()

        # 5 orders at various states
        database.insert_order(
            _make_order("ORD-001", state="ACCESSIONING", priority="routine"),
            _commit=False,
        )
        database.insert_order(
            _make_order(
                "ORD-002",
                state="ACCEPTED",
                priority="rush",
                flags=["FIXATION_WARNING"],
            ),
            _commit=False,
        )
        database.insert_order(
            _make_order("ORD-003", state="ACCESSIONING", priority="rush"),
            _commit=False,
        )
        database.insert_order(
            _make_order(
                "ORD-004",
                state="PATHOLOGIST_HE_REVIEW",
                priority="routine",
                flags=["MISSING_INFO_PROCEED"],
            ),
            _commit=False,
        )
        database.insert_order(
            _make_order("ORD-005", state="ORDER_COMPLETE", priority="routine"),
            _commit=False,
        )

        # Slides for ORD-001 and ORD-002
        database.insert_slide(_make_slide("SLD-001", "ORD-001", "H&E"), _commit=False)
        database.insert_slide(_make_slide("SLD-002", "ORD-001", "ER"), _commit=False)
        database.insert_slide(
            _make_slide("SLD-003", "ORD-002", "H&E", status="qc_pass"),
            _commit=False,
        )

        # Events for ORD-004 (missing info scenario)
        database.insert_event(
            Event(
                event_id="EVT-004-1",
                order_id="ORD-004",
                step_number=1,
                event_type="order_received",
                event_data={
                    "patient_name": "Jane Doe",
                    "billing_info_present": False,
                },
            ),
            _commit=False,
        )
        database.insert_event(
            Event(
                event_id="EVT-004-2",
                order_id="ORD-004",
                step_number=2,
                event_type="grossing_complete",
                event_data={"outcome": "success"},
            ),
            _commit=False,
        )

        database.commit()
        yield database


@pytest.fixture
def executor(db: Database) -> LiveToolExecutor:
    return LiveToolExecutor(db)


# --- list_orders tests ---


class TestListOrders:
    """Test list_orders tool."""

    def test_all_orders(self, executor: LiveToolExecutor) -> None:
        result = json.loads(executor.execute("list_orders", {}))
        assert len(result) == 5

    def test_filter_by_state(self, executor: LiveToolExecutor) -> None:
        result = json.loads(executor.execute("list_orders", {"state": "ACCESSIONING"}))
        assert len(result) == 2
        assert all(o["current_state"] == "ACCESSIONING" for o in result)

    def test_filter_by_priority(self, executor: LiveToolExecutor) -> None:
        result = json.loads(executor.execute("list_orders", {"priority": "rush"}))
        assert len(result) == 2
        assert all(o["priority"] == "rush" for o in result)

    def test_filter_has_flags_true(self, executor: LiveToolExecutor) -> None:
        result = json.loads(executor.execute("list_orders", {"has_flags": True}))
        assert len(result) == 2
        assert all(len(o["flags"]) > 0 for o in result)

    def test_filter_has_flags_false(self, executor: LiveToolExecutor) -> None:
        result = json.loads(executor.execute("list_orders", {"has_flags": False}))
        assert len(result) == 3
        assert all(len(o["flags"]) == 0 for o in result)

    def test_combined_filters(self, executor: LiveToolExecutor) -> None:
        result = json.loads(
            executor.execute("list_orders", {"state": "ACCESSIONING", "priority": "rush"})
        )
        assert len(result) == 1
        assert result[0]["order_id"] == "ORD-003"

    def test_no_matches(self, executor: LiveToolExecutor) -> None:
        result = json.loads(executor.execute("list_orders", {"state": "IHC_STAINING"}))
        assert result == []


# --- get_order tests ---


class TestGetOrder:
    """Test get_order tool."""

    def test_existing_order(self, executor: LiveToolExecutor) -> None:
        result = json.loads(executor.execute("get_order", {"order_id": "ORD-001"}))
        assert result["order_id"] == "ORD-001"
        assert result["current_state"] == "ACCESSIONING"
        assert result["patient_name"] == "Jane Doe"
        assert result["ordered_tests"] == ["ER", "PR", "HER2", "Ki-67"]

    def test_missing_order(self, executor: LiveToolExecutor) -> None:
        result = json.loads(executor.execute("get_order", {"order_id": "ORD-MISSING"}))
        assert "error" in result
        assert "Order not found" in result["error"]

    def test_order_with_flags(self, executor: LiveToolExecutor) -> None:
        result = json.loads(executor.execute("get_order", {"order_id": "ORD-002"}))
        assert result["flags"] == ["FIXATION_WARNING"]


# --- get_slides tests ---


class TestGetSlides:
    """Test get_slides tool."""

    def test_order_with_slides(self, executor: LiveToolExecutor) -> None:
        result = json.loads(executor.execute("get_slides", {"order_id": "ORD-001"}))
        assert len(result) == 2
        slide_ids = {s["slide_id"] for s in result}
        assert slide_ids == {"SLD-001", "SLD-002"}

    def test_order_with_no_slides(self, executor: LiveToolExecutor) -> None:
        result = json.loads(executor.execute("get_slides", {"order_id": "ORD-003"}))
        assert result == []

    def test_missing_order(self, executor: LiveToolExecutor) -> None:
        result = json.loads(executor.execute("get_slides", {"order_id": "ORD-MISSING"}))
        assert "error" in result

    def test_slide_fields(self, executor: LiveToolExecutor) -> None:
        result = json.loads(executor.execute("get_slides", {"order_id": "ORD-002"}))
        assert len(result) == 1
        slide = result[0]
        assert slide["slide_id"] == "SLD-003"
        assert slide["test_assignment"] == "H&E"
        assert slide["status"] == "qc_pass"
        assert slide["order_id"] == "ORD-002"
        assert slide["qc_result"] is None
        assert slide["score_result"] is None
        assert slide["reported"] is False


# --- get_state_info tests ---


class TestGetStateInfo:
    """Test get_state_info tool."""

    def test_valid_state(self, executor: LiveToolExecutor) -> None:
        result = json.loads(executor.execute("get_state_info", {"state_id": "ACCESSIONING"}))
        assert result["state_id"] == "ACCESSIONING"
        assert "phase" in result
        assert "description" in result
        assert result["terminal"] is False

    def test_terminal_state(self, executor: LiveToolExecutor) -> None:
        result = json.loads(executor.execute("get_state_info", {"state_id": "ORDER_COMPLETE"}))
        assert result["terminal"] is True

    def test_unknown_state(self, executor: LiveToolExecutor) -> None:
        result = json.loads(executor.execute("get_state_info", {"state_id": "NONEXISTENT"}))
        assert "error" in result
        assert "Unknown state" in result["error"]


# --- get_flag_info tests ---


class TestGetFlagInfo:
    """Test get_flag_info tool."""

    def test_valid_flag(self, executor: LiveToolExecutor) -> None:
        result = json.loads(executor.execute("get_flag_info", {"flag_id": "FIXATION_WARNING"}))
        assert result["flag_id"] == "FIXATION_WARNING"
        assert "effect" in result
        assert "set_at" in result
        assert "cleared_by" in result

    def test_unknown_flag(self, executor: LiveToolExecutor) -> None:
        result = json.loads(executor.execute("get_flag_info", {"flag_id": "NONEXISTENT"}))
        assert "error" in result
        assert "Unknown flag" in result["error"]


# --- execute dispatch tests ---


class TestExecuteDispatch:
    """Test the execute() dispatch mechanism."""

    def test_unknown_tool(self, executor: LiveToolExecutor) -> None:
        result = json.loads(executor.execute("nonexistent_tool", {}))
        assert "error" in result
        assert "Unknown tool" in result["error"]

    def test_invalid_arguments(self, executor: LiveToolExecutor) -> None:
        result = json.loads(executor.execute("get_order", {"bad_arg": "value"}))
        assert "error" in result
        assert "Invalid arguments" in result["error"]


# --- Database.list_orders tests ---


class TestDatabaseListOrders:
    """Test Database.list_orders() directly."""

    def test_all_orders(self, db: Database) -> None:
        orders = db.list_orders()
        assert len(orders) == 5

    def test_filter_by_state(self, db: Database) -> None:
        orders = db.list_orders(state="ACCEPTED")
        assert len(orders) == 1
        assert orders[0].order_id == "ORD-002"

    def test_filter_by_priority(self, db: Database) -> None:
        orders = db.list_orders(priority="rush")
        assert len(orders) == 2

    def test_filter_has_flags(self, db: Database) -> None:
        orders = db.list_orders(has_flags=True)
        assert len(orders) == 2
        for o in orders:
            assert len(o.flags) > 0

    def test_filter_no_flags(self, db: Database) -> None:
        orders = db.list_orders(has_flags=False)
        assert len(orders) == 3
        for o in orders:
            assert len(o.flags) == 0

    def test_combined_filters(self, db: Database) -> None:
        orders = db.list_orders(state="ACCESSIONING", priority="routine")
        assert len(orders) == 1
        assert orders[0].order_id == "ORD-001"

    def test_no_matches(self, db: Database) -> None:
        orders = db.list_orders(state="IHC_STAINING")
        assert orders == []


# --- get_events tests ---


class TestGetEvents:
    """Test get_events tool."""

    def test_order_with_events(self, executor: LiveToolExecutor) -> None:
        result = json.loads(executor.execute("get_events", {"order_id": "ORD-004"}))
        assert len(result) == 2
        assert result[0]["step_number"] == 1
        assert result[0]["event_type"] == "order_received"
        assert result[0]["event_data"]["billing_info_present"] is False
        # PHI fields should be stripped
        assert "patient_name" not in result[0]["event_data"]
        assert result[1]["step_number"] == 2
        assert result[1]["event_type"] == "grossing_complete"

    def test_order_with_no_events(self, executor: LiveToolExecutor) -> None:
        result = json.loads(executor.execute("get_events", {"order_id": "ORD-001"}))
        assert result == []

    def test_missing_order(self, executor: LiveToolExecutor) -> None:
        result = json.loads(executor.execute("get_events", {"order_id": "ORD-MISSING"}))
        assert "error" in result
        assert "Order not found" in result["error"]

    def test_excludes_internal_fields(self, executor: LiveToolExecutor) -> None:
        result = json.loads(executor.execute("get_events", {"order_id": "ORD-004"}))
        for event in result:
            assert "event_id" not in event
            assert "created_at" not in event

    def test_invalid_arguments(self, executor: LiveToolExecutor) -> None:
        result = json.loads(executor.execute("get_events", {}))
        assert "error" in result
        assert "Invalid arguments" in result["error"]


# --- Role filtering tests ---


class TestRoleFiltering:
    """Test role-based filtering of tool results."""

    def test_pathologist_only_sees_relevant_states(self, db: Database) -> None:
        executor = LiveToolExecutor(db, role="pathologist")
        result = json.loads(executor.execute("list_orders", {}))
        # Only ORD-004 (PATHOLOGIST_HE_REVIEW) should be visible
        assert len(result) == 1
        assert result[0]["order_id"] == "ORD-004"

    def test_accessioner_only_sees_relevant_states(self, db: Database) -> None:
        executor = LiveToolExecutor(db, role="accessioner")
        result = json.loads(executor.execute("list_orders", {}))
        # ORD-001 and ORD-003 (both ACCESSIONING) should be visible
        assert len(result) == 2
        ids = {o["order_id"] for o in result}
        assert ids == {"ORD-001", "ORD-003"}

    def test_lab_manager_sees_all(self, db: Database) -> None:
        executor = LiveToolExecutor(db, role="lab_manager")
        result = json.loads(executor.execute("list_orders", {}))
        assert len(result) == 5

    def test_no_role_sees_all(self, db: Database) -> None:
        executor = LiveToolExecutor(db)
        result = json.loads(executor.execute("list_orders", {}))
        assert len(result) == 5

    def test_get_order_blocked_by_role(self, db: Database) -> None:
        executor = LiveToolExecutor(db, role="pathologist")
        result = json.loads(executor.execute("get_order", {"order_id": "ORD-001"}))
        assert "error" in result
        assert "not in your workflow scope" in result["error"]

    def test_get_order_allowed_by_role(self, db: Database) -> None:
        executor = LiveToolExecutor(db, role="pathologist")
        result = json.loads(executor.execute("get_order", {"order_id": "ORD-004"}))
        assert result["order_id"] == "ORD-004"

    def test_histotech_only_sees_relevant_states(self, db: Database) -> None:
        executor = LiveToolExecutor(db, role="histotech")
        result = json.loads(executor.execute("list_orders", {}))
        # Only ORD-002 (ACCEPTED) should be visible
        assert len(result) == 1
        assert result[0]["order_id"] == "ORD-002"

    def test_get_slides_blocked_by_role(self, db: Database) -> None:
        executor = LiveToolExecutor(db, role="pathologist")
        result = json.loads(executor.execute("get_slides", {"order_id": "ORD-001"}))
        assert "error" in result
        assert "not in your workflow scope" in result["error"]

    def test_get_slides_allowed_by_role(self, db: Database) -> None:
        executor = LiveToolExecutor(db, role="pathologist")
        result = json.loads(executor.execute("get_slides", {"order_id": "ORD-004"}))
        assert isinstance(result, list)

    def test_get_events_blocked_by_role(self, db: Database) -> None:
        executor = LiveToolExecutor(db, role="accessioner")
        result = json.loads(executor.execute("get_events", {"order_id": "ORD-004"}))
        assert "error" in result
        assert "not in your workflow scope" in result["error"]

    def test_get_events_allowed_by_role(self, db: Database) -> None:
        executor = LiveToolExecutor(db, role="pathologist")
        result = json.loads(executor.execute("get_events", {"order_id": "ORD-004"}))
        assert isinstance(result, list)

    def test_invalid_role_raises(self, db: Database) -> None:
        with pytest.raises(ValueError, match="Unknown role"):
            LiveToolExecutor(db, role="admin")
