"""Tests for the chat service with streaming and tool use."""

from __future__ import annotations

from collections.abc import Generator, Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.models.base import ChatMessage, ChatResponse, ChatRole, ToolCall
from src.models.llamacpp_adapter import LlamaCppAdapter
from src.prediction.engine import PredictionEngine
from src.server.chat_service import (
    ChatService,
    _build_system_prompt,
    _get_chat_tools,
)
from src.server.routing_service import RoutingService
from src.workflow.database import Database
from src.workflow.models import Event, Order
from src.workflow.state_machine import StateMachine

# --- Helpers ---


def _make_order(
    order_id: str = "ORD-001",
    state: str = "ACCESSIONING",
) -> Order:
    return Order(
        order_id=order_id,
        scenario_id="test",
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
    )


def _text_stream(text: str, latency_ms: float = 100.0) -> Iterator[str | ChatResponse]:
    """Simulate a streaming response that yields tokens then a final ChatResponse."""
    for word in text.split():
        yield word + " "
    yield ChatResponse(
        message=ChatMessage(role=ChatRole.ASSISTANT, content=text),
        latency_ms=latency_ms,
        input_tokens=50,
        output_tokens=25,
        cost_estimate_usd=None,
        model_id="test-model",
    )


def _tool_call_stream(
    tool_name: str,
    arguments: dict[str, Any],
    latency_ms: float = 50.0,
) -> Iterator[str | ChatResponse]:
    """Simulate a streaming response that yields a tool call."""
    yield ChatResponse(
        message=ChatMessage(
            role=ChatRole.ASSISTANT,
            content=None,
            tool_calls=(ToolCall(id="call_0", function_name=tool_name, arguments=arguments),),
        ),
        latency_ms=latency_ms,
        input_tokens=50,
        output_tokens=25,
        cost_estimate_usd=None,
        model_id="test-model",
    )


def _error_stream(error: str) -> Iterator[str | ChatResponse]:
    """Simulate a streaming response that yields an error."""
    yield ChatResponse(
        message=ChatMessage(role=ChatRole.ASSISTANT, content=None),
        latency_ms=10.0,
        input_tokens=0,
        output_tokens=0,
        cost_estimate_usd=None,
        model_id="test-model",
        error=error,
    )


# --- Fixtures ---


@pytest.fixture
def db(tmp_path: Path) -> Generator[Database, None, None]:
    database = Database(tmp_path / "test.sqlite", check_same_thread=False)
    with database:
        database.init_db()
        database.insert_order(_make_order("ORD-001", "ACCESSIONING"))
        database.insert_order(_make_order("ORD-002", "ACCEPTED"))
        database.insert_event(
            Event(
                event_id="EVT-001",
                order_id="ORD-001",
                step_number=1,
                event_type="order_received",
                event_data={"billing_info_present": True},
            )
        )
        yield database


@pytest.fixture
def mock_adapter() -> MagicMock:
    adapter = MagicMock(spec=LlamaCppAdapter)
    adapter.model_id = "test-model"
    return adapter


@pytest.fixture
def mock_engine() -> MagicMock:
    engine = MagicMock(spec=PredictionEngine)
    engine.model_id = "test-model"
    return engine


@pytest.fixture
def service(mock_adapter: MagicMock, db: Database, mock_engine: MagicMock) -> ChatService:
    state_machine = StateMachine.get_instance()
    routing_service = RoutingService(db, mock_engine, state_machine)
    return ChatService(mock_adapter, db, routing_service)


# --- System prompt tests ---


class TestSystemPrompt:
    def test_accessioner_prompt_mentions_role(self) -> None:
        prompt = _build_system_prompt("accessioner")
        assert "accessioner" in prompt
        assert "ACCESSIONING" in prompt

    def test_pathologist_prompt_mentions_role(self) -> None:
        prompt = _build_system_prompt("pathologist")
        assert "pathologist" in prompt
        assert "PATHOLOGIST_HE_REVIEW" in prompt

    def test_lab_manager_sees_all(self) -> None:
        prompt = _build_system_prompt("lab_manager")
        assert "all workflow states" in prompt


# --- Tool definitions ---


class TestToolDefinitions:
    def test_includes_submit_event(self) -> None:
        tools = _get_chat_tools()
        names = {t["function"]["name"] for t in tools}
        assert "submit_event" in names
        assert "list_orders" in names
        assert len(tools) == 7  # 6 query tools + submit_event


# --- Streaming text response ---


class TestStreamingTextResponse:
    def test_yields_tokens_then_done(self, service: ChatService, mock_adapter: MagicMock) -> None:
        mock_adapter.chat_stream.return_value = _text_stream("Hello world")

        events = list(service.handle_message_stream("sess-1", "Hi", "lab_manager"))

        token_events = [e for e in events if e["type"] == "token"]
        assert len(token_events) >= 1
        assert any("Hello" in e["content"] for e in token_events)

        done_events = [e for e in events if e["type"] == "done"]
        assert len(done_events) == 1
        assert done_events[0]["session_id"] == "sess-1"

    def test_session_history_accumulates(
        self, service: ChatService, mock_adapter: MagicMock
    ) -> None:
        mock_adapter.chat_stream.return_value = _text_stream("First response")
        list(service.handle_message_stream("sess-1", "Hello", "lab_manager"))

        mock_adapter.chat_stream.return_value = _text_stream("Second response")
        list(service.handle_message_stream("sess-1", "Follow up", "lab_manager"))

        # Session should have: system + user + assistant + user + assistant
        session = service._sessions["sess-1"]
        assert len(session) == 5
        assert session[0].role == ChatRole.SYSTEM
        assert session[1].role == ChatRole.USER
        assert session[2].role == ChatRole.ASSISTANT


# --- Tool call flow ---


class TestToolCallFlow:
    def test_tool_call_then_text(self, service: ChatService, mock_adapter: MagicMock) -> None:
        # First call returns a tool call, second returns text
        mock_adapter.chat_stream.side_effect = [
            _tool_call_stream("list_orders", {}),
            _text_stream("You have 2 orders"),
        ]

        events = list(service.handle_message_stream("sess-1", "What orders?", "lab_manager"))

        tool_events = [e for e in events if e["type"] == "tool_status"]
        assert len(tool_events) == 2  # executing + complete
        assert tool_events[0]["status"] == "executing"
        assert tool_events[1]["status"] == "complete"

        done_events = [e for e in events if e["type"] == "done"]
        assert len(done_events) == 1

    def test_get_order_tool_call(self, service: ChatService, mock_adapter: MagicMock) -> None:
        mock_adapter.chat_stream.side_effect = [
            _tool_call_stream("get_order", {"order_id": "ORD-001"}),
            _text_stream("ORD-001 is in ACCESSIONING"),
        ]

        events = list(
            service.handle_message_stream("sess-1", "Tell me about ORD-001", "lab_manager")
        )

        tool_events = [e for e in events if e["type"] == "tool_status"]
        assert tool_events[0]["tool"] == "get_order"

    def test_get_events_tool_call(self, service: ChatService, mock_adapter: MagicMock) -> None:
        mock_adapter.chat_stream.side_effect = [
            _tool_call_stream("get_events", {"order_id": "ORD-001"}),
            _text_stream("ORD-001 was received with billing info present"),
        ]

        events = list(
            service.handle_message_stream("sess-1", "What happened to ORD-001?", "lab_manager")
        )

        tool_events = [e for e in events if e["type"] == "tool_status"]
        assert tool_events[0]["tool"] == "get_events"
        assert tool_events[0]["status"] == "executing"
        assert tool_events[1]["status"] == "complete"

    def test_get_events_error_flow(self, service: ChatService, mock_adapter: MagicMock) -> None:
        mock_adapter.chat_stream.side_effect = [
            _tool_call_stream("get_events", {"order_id": "ORD-MISSING"}),
            _text_stream("That order was not found"),
        ]

        events = list(
            service.handle_message_stream("sess-1", "Events for ORD-MISSING?", "lab_manager")
        )

        tool_events = [e for e in events if e["type"] == "tool_status"]
        assert tool_events[0]["tool"] == "get_events"
        assert tool_events[1]["status"] == "complete"


# --- Submit event tool ---


class TestSubmitEventTool:
    def test_submit_event_delegates_to_routing_service(
        self, service: ChatService, mock_adapter: MagicMock, mock_engine: MagicMock
    ) -> None:
        from src.models.base import ModelResponse
        from src.prediction.engine import PredictionResult

        # Mock the prediction engine to return a valid routing result
        mock_engine.predict_routing.return_value = PredictionResult(
            next_state="ACCEPTED",
            applied_rules=("ACC-008",),
            flags=(),
            reasoning="All checks passed",
            raw_response=ModelResponse(
                raw_text="{}",
                parsed_output={},
                latency_ms=100.0,
                input_tokens=50,
                output_tokens=25,
                cost_estimate_usd=None,
                model_id="test-model",
            ),
        )

        # First call: model calls submit_event tool
        mock_adapter.chat_stream.side_effect = [
            _tool_call_stream(
                "submit_event",
                {
                    "order_id": "ORD-001",
                    "event_type": "order_received",
                    "event_data": {},
                },
            ),
            _text_stream("Order ORD-001 has been advanced to ACCEPTED"),
        ]

        events = list(
            service.handle_message_stream("sess-1", "Mark ORD-001 as received", "accessioner")
        )

        tool_events = [e for e in events if e["type"] == "tool_status"]
        assert tool_events[0]["tool"] == "submit_event"

        # Verify routing was called
        mock_engine.predict_routing.assert_called_once()


# --- Error handling ---


class TestErrorHandling:
    def test_model_error_yields_error_event(
        self, service: ChatService, mock_adapter: MagicMock
    ) -> None:
        mock_adapter.chat_stream.return_value = _error_stream(
            "connection_error: llama-server unreachable"
        )

        events = list(service.handle_message_stream("sess-1", "Hello", "lab_manager"))

        error_events = [e for e in events if e["type"] == "error"]
        assert len(error_events) == 1
        assert "connection_error" in error_events[0]["message"]

    def test_new_session_vs_existing(self, service: ChatService, mock_adapter: MagicMock) -> None:
        mock_adapter.chat_stream.return_value = _text_stream("Hi")
        list(service.handle_message_stream("sess-1", "Hello", "accessioner"))
        assert "sess-1" in service._sessions

        # Different session
        mock_adapter.chat_stream.return_value = _text_stream("Hi")
        list(service.handle_message_stream("sess-2", "Hello", "pathologist"))
        assert "sess-2" in service._sessions

        # Different system prompts
        sess1_system = service._sessions["sess-1"][0].content
        sess2_system = service._sessions["sess-2"][0].content
        assert sess1_system is not None
        assert sess2_system is not None
        assert "accessioner" in sess1_system
        assert "pathologist" in sess2_system


# --- Executor lifecycle tests ---


class TestExecutorLifecycle:
    """Test per-session executor creation, removal, and eviction."""

    def test_session_creates_executor(self, service: ChatService, mock_adapter: MagicMock) -> None:
        mock_adapter.chat_stream.return_value = _text_stream("Hi")
        list(service.handle_message_stream("sess-1", "Hello", "accessioner"))
        assert "sess-1" in service._executors
        # Executor should have role-based filtering
        executor = service._executors["sess-1"]
        assert executor._allowed_states is not None

    def test_remove_session_clears_executor(
        self, service: ChatService, mock_adapter: MagicMock
    ) -> None:
        mock_adapter.chat_stream.return_value = _text_stream("Hi")
        list(service.handle_message_stream("sess-1", "Hello", "lab_manager"))
        assert "sess-1" in service._executors
        service.remove_session("sess-1")
        assert "sess-1" not in service._executors
        assert "sess-1" not in service._sessions

    def test_session_eviction_removes_oldest_executor(
        self, service: ChatService, mock_adapter: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("src.server.chat_service._MAX_SESSIONS", 2)
        mock_adapter.chat_stream.return_value = _text_stream("Hi")
        list(service.handle_message_stream("sess-1", "Hello", "lab_manager"))
        mock_adapter.chat_stream.return_value = _text_stream("Hi")
        list(service.handle_message_stream("sess-2", "Hello", "lab_manager"))
        assert "sess-1" in service._executors

        # Third session should evict sess-1
        mock_adapter.chat_stream.return_value = _text_stream("Hi")
        list(service.handle_message_stream("sess-3", "Hello", "lab_manager"))
        assert "sess-1" not in service._executors
        assert "sess-1" not in service._sessions
        assert "sess-3" in service._executors


# --- Submit event scope tests ---


class TestSubmitEventScope:
    """Test role-scope enforcement on submit_event."""

    def test_submit_event_blocked_for_out_of_scope_order(
        self, service: ChatService, mock_adapter: MagicMock
    ) -> None:
        # Pathologist should not be able to submit events for ACCESSIONING orders
        mock_adapter.chat_stream.side_effect = [
            _tool_call_stream(
                "submit_event",
                {"order_id": "ORD-001", "event_type": "order_received", "event_data": {}},
            ),
            _text_stream("That order is not in your scope"),
        ]

        events = list(service.handle_message_stream("sess-1", "Process ORD-001", "pathologist"))

        # Tool should still complete (error returned in tool result, not as stream error)
        tool_events = [e for e in events if e["type"] == "tool_status"]
        assert any(e["tool"] == "submit_event" for e in tool_events)
