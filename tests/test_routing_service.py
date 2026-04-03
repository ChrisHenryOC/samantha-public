"""Tests for the live routing service."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.models.base import ModelResponse
from src.prediction.engine import PredictionEngine, PredictionResult
from src.server.models import RoutingResult
from src.server.routing_service import RoutingService
from src.workflow.database import Database
from src.workflow.models import Event, Order, Slide
from src.workflow.state_machine import StateMachine

# --- Fixtures ---


def _make_order(
    order_id: str = "ORD-001",
    state: str = "ACCESSIONING",
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
        priority="routine",
        billing_info_present=True,
        current_state=state,
        flags=flags or [],
    )


def _make_slide(order_id: str = "ORD-001", test: str = "H&E") -> Slide:
    return Slide(
        slide_id=f"SLD-{uuid.uuid4().hex[:8]}",
        order_id=order_id,
        test_assignment=test,
        status="sectioned",
    )


def _make_event(
    order_id: str = "ORD-001",
    event_type: str = "order_received",
    event_data: dict[str, Any] | None = None,
    step_number: int = 1,
) -> Event:
    return Event(
        event_id=f"EVT-{uuid.uuid4().hex[:8]}",
        order_id=order_id,
        step_number=step_number,
        event_type=event_type,
        event_data=event_data or {},
    )


def _make_model_response(
    next_state: str = "ACCEPTED",
    applied_rules: list[str] | None = None,
    flags: list[str] | None = None,
    reasoning: str = "All checks passed",
    error: str | None = None,
    latency_ms: float = 500.0,
) -> ModelResponse:
    if error is not None:
        return ModelResponse(
            raw_text=f"<{error}>",
            parsed_output=None,
            latency_ms=latency_ms,
            input_tokens=100,
            output_tokens=50,
            cost_estimate_usd=None,
            model_id="test-model",
            error=error,
        )
    output = {
        "next_state": next_state,
        "applied_rules": applied_rules or ["ACC-008"],
        "flags": flags or [],
        "reasoning": reasoning,
    }
    return ModelResponse(
        raw_text=str(output),
        parsed_output=output,
        latency_ms=latency_ms,
        input_tokens=100,
        output_tokens=50,
        cost_estimate_usd=None,
        model_id="test-model",
    )


def _make_prediction_result(
    next_state: str | None = "ACCEPTED",
    applied_rules: list[str] | None = None,
    flags: list[str] | None = None,
    reasoning: str = "All checks passed",
    error: str | None = None,
    latency_ms: float = 500.0,
) -> PredictionResult:
    response = _make_model_response(
        next_state=next_state or "ACCEPTED",
        applied_rules=applied_rules,
        flags=flags,
        reasoning=reasoning,
        error=error,
        latency_ms=latency_ms,
    )
    if error is not None:
        return PredictionResult(
            next_state=None,
            applied_rules=(),
            flags=(),
            reasoning=None,
            raw_response=response,
            error=error,
        )
    return PredictionResult(
        next_state=next_state,
        applied_rules=tuple(applied_rules or ["ACC-008"]),
        flags=tuple(flags or []),
        reasoning=reasoning,
        raw_response=response,
    )


@pytest.fixture
def db(tmp_path: Path) -> Generator[Database, None, None]:
    """Create a temporary database with schema initialized."""
    database = Database(tmp_path / "test.sqlite")
    with database:
        database.init_db()
        yield database


@pytest.fixture
def state_machine() -> StateMachine:
    return StateMachine.get_instance()


@pytest.fixture
def mock_engine() -> MagicMock:
    """Create a mock PredictionEngine."""
    engine = MagicMock(spec=PredictionEngine)
    engine.model_id = "test-model"
    engine.provider = "mock"
    return engine


@pytest.fixture
def service(db: Database, mock_engine: MagicMock, state_machine: StateMachine) -> RoutingService:
    return RoutingService(db, mock_engine, state_machine)


# --- Tests ---


class TestRoutingServiceValidTransition:
    """Test successful event processing with valid state transitions."""

    def test_valid_transition_updates_order_state(
        self, db: Database, service: RoutingService, mock_engine: MagicMock
    ) -> None:
        order = _make_order()
        db.insert_order(order)

        mock_engine.predict_routing.return_value = _make_prediction_result(
            next_state="ACCEPTED", applied_rules=["ACC-008"]
        )

        event = _make_event(event_type="order_received")
        result = service.process_event("ORD-001", event)

        assert result.applied is True
        assert result.transition_valid is True
        assert result.from_state == "ACCESSIONING"
        assert result.to_state == "ACCEPTED"
        assert result.applied_rules == ("ACC-008",)
        assert result.error is None

        # Verify DB state updated
        updated_order = db.get_order("ORD-001")
        assert updated_order is not None
        assert updated_order.current_state == "ACCEPTED"

    def test_valid_transition_persists_routing_decision(
        self, db: Database, service: RoutingService, mock_engine: MagicMock
    ) -> None:
        order = _make_order()
        db.insert_order(order)

        mock_engine.predict_routing.return_value = _make_prediction_result()

        event = _make_event(event_type="order_received")
        result = service.process_event("ORD-001", event)

        decisions = db.get_routing_decisions_for_order("ORD-001")
        assert len(decisions) == 1
        assert decisions[0]["decision_id"] == result.decision_id
        assert decisions[0]["from_state"] == "ACCESSIONING"
        assert decisions[0]["to_state"] == "ACCEPTED"
        assert decisions[0]["applied"] is True
        assert decisions[0]["transition_valid"] is True

    def test_valid_transition_inserts_event(
        self, db: Database, service: RoutingService, mock_engine: MagicMock
    ) -> None:
        order = _make_order()
        db.insert_order(order)

        mock_engine.predict_routing.return_value = _make_prediction_result()

        event = _make_event(event_type="order_received")
        service.process_event("ORD-001", event)

        events = db.get_events_for_order("ORD-001")
        assert len(events) == 1
        assert events[0].event_type == "order_received"


class TestRoutingServiceInvalidTransition:
    """Test handling of invalid state transitions."""

    def test_invalid_transition_does_not_update_order(
        self, db: Database, service: RoutingService, mock_engine: MagicMock
    ) -> None:
        order = _make_order(state="ACCESSIONING")
        db.insert_order(order)

        # Predict an impossible transition (ACCESSIONING -> ORDER_COMPLETE)
        mock_engine.predict_routing.return_value = _make_prediction_result(
            next_state="ORDER_COMPLETE", applied_rules=["ACC-008"]
        )

        event = _make_event(event_type="order_received")
        result = service.process_event("ORD-001", event)

        assert result.applied is False
        assert result.transition_valid is False
        assert result.to_state == "ORDER_COMPLETE"

        # Order state should be unchanged
        updated_order = db.get_order("ORD-001")
        assert updated_order is not None
        assert updated_order.current_state == "ACCESSIONING"

    def test_invalid_transition_persists_decision(
        self, db: Database, service: RoutingService, mock_engine: MagicMock
    ) -> None:
        order = _make_order(state="ACCESSIONING")
        db.insert_order(order)

        mock_engine.predict_routing.return_value = _make_prediction_result(
            next_state="ORDER_COMPLETE"
        )

        event = _make_event(event_type="order_received")
        service.process_event("ORD-001", event)

        decisions = db.get_routing_decisions_for_order("ORD-001")
        assert len(decisions) == 1
        assert decisions[0]["applied"] is False
        assert decisions[0]["transition_valid"] is False


class TestRoutingServiceModelError:
    """Test handling of model errors."""

    def test_model_error_does_not_update_order(
        self, db: Database, service: RoutingService, mock_engine: MagicMock
    ) -> None:
        order = _make_order()
        db.insert_order(order)

        mock_engine.predict_routing.return_value = _make_prediction_result(
            error="adapter_error: ConnectionError: model unavailable"
        )

        event = _make_event(event_type="order_received")
        result = service.process_event("ORD-001", event)

        assert result.applied is False
        assert result.error is not None
        assert "adapter_error" in result.error

        # Order state unchanged
        updated_order = db.get_order("ORD-001")
        assert updated_order is not None
        assert updated_order.current_state == "ACCESSIONING"

    def test_model_error_persists_decision(
        self, db: Database, service: RoutingService, mock_engine: MagicMock
    ) -> None:
        order = _make_order()
        db.insert_order(order)

        mock_engine.predict_routing.return_value = _make_prediction_result(
            error="adapter_error: timeout"
        )

        event = _make_event(event_type="order_received")
        service.process_event("ORD-001", event)

        decisions = db.get_routing_decisions_for_order("ORD-001")
        assert len(decisions) == 1
        assert decisions[0]["applied"] is False


class TestRoutingServiceOrderNotFound:
    """Test handling of missing orders."""

    def test_raises_for_nonexistent_order(self, service: RoutingService) -> None:
        event = _make_event(order_id="ORD-MISSING", event_type="order_received")
        with pytest.raises(ValueError, match="Order not found: ORD-MISSING"):
            service.process_event("ORD-MISSING", event)


class TestRoutingServiceTerminalState:
    """Test that events for terminal-state orders are rejected."""

    def test_raises_for_completed_order(self, db: Database, service: RoutingService) -> None:
        order = _make_order(state="ORDER_COMPLETE")
        db.insert_order(order)

        event = _make_event(event_type="order_received")
        with pytest.raises(ValueError, match="terminal state ORDER_COMPLETE"):
            service.process_event("ORD-001", event)

    def test_raises_for_terminated_order(self, db: Database, service: RoutingService) -> None:
        order = _make_order(state="ORDER_TERMINATED")
        db.insert_order(order)

        event = _make_event(event_type="order_received")
        with pytest.raises(ValueError, match="terminal state ORDER_TERMINATED"):
            service.process_event("ORD-001", event)


class TestRoutingServiceFlagAccumulation:
    """Test that predicted flags merge with existing order flags."""

    def test_flags_merge_on_valid_transition(
        self, db: Database, service: RoutingService, mock_engine: MagicMock
    ) -> None:
        # Order already has FIXATION_WARNING flag
        order = _make_order(state="ACCESSIONING", flags=["FIXATION_WARNING"])
        db.insert_order(order)

        # Model predicts MISSING_INFO_PROCEED flag
        mock_engine.predict_routing.return_value = _make_prediction_result(
            next_state="MISSING_INFO_PROCEED",
            applied_rules=["ACC-003"],
            flags=["MISSING_INFO_PROCEED"],
        )

        event = _make_event(event_type="order_received")
        result = service.process_event("ORD-001", event)

        assert result.applied is True
        # Both flags should be present (sorted)
        assert result.flags == ("FIXATION_WARNING", "MISSING_INFO_PROCEED")

        # Verify in DB
        updated_order = db.get_order("ORD-001")
        assert updated_order is not None
        assert set(updated_order.flags) == {"FIXATION_WARNING", "MISSING_INFO_PROCEED"}

    def test_invalid_flags_are_filtered(
        self, db: Database, service: RoutingService, mock_engine: MagicMock
    ) -> None:
        order = _make_order(state="ACCESSIONING")
        db.insert_order(order)

        # Model hallucinates an invalid flag
        mock_engine.predict_routing.return_value = _make_prediction_result(
            next_state="ACCEPTED",
            applied_rules=["ACC-008"],
            flags=["FIXATION_WARNING", "HALLUCINATED_FLAG"],
        )

        event = _make_event(event_type="order_received")
        result = service.process_event("ORD-001", event)

        assert result.applied is True
        # Only valid flag survives
        assert result.flags == ("FIXATION_WARNING",)


class TestRoutingServiceMissingNextState:
    """Test handling when prediction returns no next_state."""

    def test_none_next_state_treated_as_error(
        self, db: Database, service: RoutingService, mock_engine: MagicMock
    ) -> None:
        order = _make_order()
        db.insert_order(order)

        mock_engine.predict_routing.return_value = _make_prediction_result(next_state=None)

        event = _make_event(event_type="order_received")
        result = service.process_event("ORD-001", event)

        assert result.applied is False
        assert result.error is not None
        assert "prediction_missing_state" in result.error

        # Order unchanged
        updated = db.get_order("ORD-001")
        assert updated is not None
        assert updated.current_state == "ACCESSIONING"


class TestRoutingServiceRagRetriever:
    """Test that RAG retriever is forwarded to the prediction engine."""

    def test_rag_retriever_passed_to_engine(
        self, db: Database, mock_engine: MagicMock, state_machine: StateMachine
    ) -> None:
        mock_retriever = MagicMock()
        service = RoutingService(db, mock_engine, state_machine, rag_retriever=mock_retriever)

        order = _make_order()
        db.insert_order(order)

        mock_engine.predict_routing.return_value = _make_prediction_result()

        event = _make_event(event_type="order_received")
        service.process_event("ORD-001", event)

        # Verify the retriever was passed through
        call_kwargs = mock_engine.predict_routing.call_args
        assert call_kwargs.kwargs["rag_retriever"] is mock_retriever


class TestRoutingServiceMultipleEvents:
    """Test processing multiple events for the same order."""

    def test_sequential_events_advance_order(
        self, db: Database, service: RoutingService, mock_engine: MagicMock
    ) -> None:
        order = _make_order(state="ACCESSIONING")
        db.insert_order(order)

        # First event: ACCESSIONING -> ACCEPTED
        mock_engine.predict_routing.return_value = _make_prediction_result(
            next_state="ACCEPTED", applied_rules=["ACC-008"]
        )
        event1 = _make_event(event_type="order_received", step_number=1)
        result1 = service.process_event("ORD-001", event1)
        assert result1.applied is True
        assert result1.to_state == "ACCEPTED"

        # Second event: ACCEPTED -> SAMPLE_PREP_PROCESSING
        mock_engine.predict_routing.return_value = _make_prediction_result(
            next_state="SAMPLE_PREP_PROCESSING", applied_rules=["SP-001"]
        )
        event2 = _make_event(
            event_type="grossing_complete",
            event_data={"tissue_adequate": True, "sections_taken": 4},
            step_number=2,
        )
        result2 = service.process_event("ORD-001", event2)
        assert result2.applied is True
        assert result2.from_state == "ACCEPTED"
        assert result2.to_state == "SAMPLE_PREP_PROCESSING"

        # Verify final DB state
        updated = db.get_order("ORD-001")
        assert updated is not None
        assert updated.current_state == "SAMPLE_PREP_PROCESSING"

        # Verify two routing decisions persisted
        decisions = db.get_routing_decisions_for_order("ORD-001")
        assert len(decisions) == 2


class TestRoutingResultValidation:
    """Test RoutingResult dataclass validation."""

    def test_empty_decision_id_raises(self) -> None:
        with pytest.raises(ValueError, match="decision_id must be a non-empty string"):
            RoutingResult(
                decision_id="",
                order_id="ORD-001",
                from_state="ACCESSIONING",
                to_state="ACCEPTED",
                applied_rules=(),
                flags=(),
                reasoning=None,
                transition_valid=True,
                applied=True,
                latency_ms=100.0,
            )

    def test_empty_to_state_without_error_raises(self) -> None:
        with pytest.raises(ValueError, match="to_state must be non-empty when error is None"):
            RoutingResult(
                decision_id="d-1",
                order_id="ORD-001",
                from_state="ACCESSIONING",
                to_state="",
                applied_rules=(),
                flags=(),
                reasoning=None,
                transition_valid=False,
                applied=False,
                latency_ms=100.0,
            )

    def test_empty_to_state_with_error_is_valid(self) -> None:
        result = RoutingResult(
            decision_id="d-1",
            order_id="ORD-001",
            from_state="ACCESSIONING",
            to_state="",
            applied_rules=(),
            flags=(),
            reasoning=None,
            transition_valid=False,
            applied=False,
            latency_ms=100.0,
            error="model_error: timeout",
        )
        assert result.to_state == ""
        assert result.error is not None

    def test_applied_rules_must_be_tuple(self) -> None:
        with pytest.raises(TypeError, match="applied_rules must be tuple"):
            RoutingResult(
                decision_id="d-1",
                order_id="ORD-001",
                from_state="ACCESSIONING",
                to_state="ACCEPTED",
                applied_rules=["ACC-008"],  # type: ignore[arg-type]
                flags=(),
                reasoning=None,
                transition_valid=True,
                applied=True,
                latency_ms=100.0,
            )


class TestRoutingDecisionDbRoundTrip:
    """Test DB round-trip for routing_decisions table."""

    def test_insert_and_retrieve(self, db: Database) -> None:
        from datetime import datetime

        order = _make_order()
        db.insert_order(order)
        event = _make_event()
        db.insert_event(event)

        now = datetime.now()
        db.insert_routing_decision(
            decision_id="RD-001",
            event_id=event.event_id,
            order_id="ORD-001",
            model_id="test-model",
            from_state="ACCESSIONING",
            to_state="ACCEPTED",
            applied_rules=["ACC-008"],
            flags=["FIXATION_WARNING"],
            reasoning="All checks passed",
            transition_valid=True,
            applied=True,
            latency_ms=500.0,
            created_at=now,
        )

        decisions = db.get_routing_decisions_for_order("ORD-001")
        assert len(decisions) == 1
        d = decisions[0]
        assert d["decision_id"] == "RD-001"
        assert d["event_id"] == event.event_id
        assert d["order_id"] == "ORD-001"
        assert d["model_id"] == "test-model"
        assert d["from_state"] == "ACCESSIONING"
        assert d["to_state"] == "ACCEPTED"
        assert d["applied_rules"] == ["ACC-008"]
        assert d["flags"] == ["FIXATION_WARNING"]
        assert d["reasoning"] == "All checks passed"
        assert d["transition_valid"] is True
        assert d["applied"] is True
        assert d["latency_ms"] == 500.0

    def test_none_reasoning_round_trips(self, db: Database) -> None:
        from datetime import datetime

        order = _make_order()
        db.insert_order(order)
        event = _make_event()
        db.insert_event(event)

        db.insert_routing_decision(
            decision_id="RD-002",
            event_id=event.event_id,
            order_id="ORD-001",
            model_id="test-model",
            from_state="ACCESSIONING",
            to_state="",
            applied_rules=[],
            flags=[],
            reasoning=None,
            transition_valid=False,
            applied=False,
            latency_ms=0.0,
            created_at=datetime.now(),
        )

        decisions = db.get_routing_decisions_for_order("ORD-001")
        assert len(decisions) == 1
        assert decisions[0]["reasoning"] is None
        assert decisions[0]["applied_rules"] == []
        assert decisions[0]["flags"] == []

    def test_empty_list_for_unknown_order(self, db: Database) -> None:
        decisions = db.get_routing_decisions_for_order("ORD-NONEXISTENT")
        assert decisions == []
