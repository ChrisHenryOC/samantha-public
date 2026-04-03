"""Chat service for interactive LLM conversations with tool use.

Manages multi-turn conversations where the LLM uses tools to query
the live database before answering. Supports streaming responses
and a submit_event tool for triggering workflow state transitions.
"""

from __future__ import annotations

import copy
import json
import logging
import time
import uuid
from collections.abc import Iterator
from datetime import datetime
from typing import Any

from src.models.base import ChatMessage, ChatResponse, ChatRole, ModelAdapter
from src.server.live_executor import OUT_OF_SCOPE_MSG, LiveToolExecutor
from src.server.roles import ROLE_STATES
from src.server.routing_service import RoutingService
from src.tools.definitions import get_all_tool_definitions
from src.workflow.database import Database
from src.workflow.models import Event

logger = logging.getLogger(__name__)

_MAX_TOOL_USE_TURNS = 10
_MAX_SESSIONS = 100

# submit_event tool definition (added to the 5 existing tools)
_SUBMIT_EVENT_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "submit_event",
        "description": (
            "Submit a workflow event to advance an order to its next state. "
            "Use this when the user asks to mark work as complete."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "The order to advance",
                },
                "event_type": {
                    "type": "string",
                    "description": ("The event type (e.g., grossing_complete, he_qc)"),
                },
                "event_data": {
                    "type": "object",
                    "description": "Event-specific data",
                },
            },
            "required": ["order_id", "event_type", "event_data"],
        },
    },
}


def _build_system_prompt(role: str) -> str:
    """Build a role-aware system prompt for the chat service."""
    states = ROLE_STATES.get(role)
    if states is None:
        state_desc = "You can see all workflow states."
    else:
        state_list = ", ".join(sorted(states))
        state_desc = f"Your workflow states are: {state_list}."

    return (
        f"You are Samantha, a laboratory workflow assistant for breast cancer "
        f"specimen processing. You are helping a {role}. {state_desc}\n\n"
        f"You have tools to query orders, slides, workflow states, and flags "
        f"from the live database. Always call tools to get current data — "
        f"do not guess or make up information.\n\n"
        f"You can also submit workflow events on behalf of the user when they "
        f"ask to mark work as complete (e.g., 'mark grossing complete for "
        f"ORD-001').\n\n"
        f"When explaining why an order is blocked or flagged, always use "
        f"get_events to check the event history for the specific trigger. "
        f"Give case-specific answers, not general explanations.\n\n"
        f"Respond in natural language. Be concise and helpful. When listing "
        f"orders, include the order ID, patient name, current state, and "
        f"priority."
    )


def _get_chat_tools() -> list[dict[str, Any]]:
    """Get all tool definitions including submit_event."""
    tools: list[dict[str, Any]] = get_all_tool_definitions()  # type: ignore[assignment]
    tools.append(copy.deepcopy(_SUBMIT_EVENT_TOOL))
    return tools


class ChatService:
    """Manages multi-turn chat conversations with tool use and streaming.

    Each session maintains its own conversation history. The LLM can
    call tools to query the live database and submit workflow events.
    Sessions are evicted when max count is reached (oldest first).
    """

    def __init__(
        self,
        adapter: ModelAdapter,
        db: Database,
        routing_service: RoutingService,
    ) -> None:
        self._adapter = adapter
        self._supports_streaming = hasattr(adapter, "chat_stream")
        self._db = db
        self._routing_service = routing_service
        self._sessions: dict[str, list[ChatMessage]] = {}
        self._executors: dict[str, LiveToolExecutor] = {}
        self._tools = _get_chat_tools()

    def remove_session(self, session_id: str) -> None:
        """Remove a session and its history. Called on WebSocket disconnect."""
        self._sessions.pop(session_id, None)
        self._executors.pop(session_id, None)

    def _execute_tool(self, session_id: str, tool_name: str, arguments: dict[str, Any]) -> str:
        """Execute a tool call, routing submit_event specially."""
        executor = self._executors.get(session_id)
        if executor is None:
            return json.dumps({"error": "Session not initialized"})
        if tool_name == "submit_event":
            return self._handle_submit_event(executor, arguments)
        return executor.execute(tool_name, arguments)

    def _handle_submit_event(self, executor: LiveToolExecutor, arguments: dict[str, Any]) -> str:
        """Handle the submit_event tool by delegating to RoutingService."""
        order_id = arguments.get("order_id", "")
        event_type = arguments.get("event_type", "")
        event_data = arguments.get("event_data", {})

        if not order_id or not event_type:
            return json.dumps({"error": "order_id and event_type are required"})

        # Verify order is in the user's role scope
        order = self._db.get_order(order_id)
        if order is None:
            return json.dumps({"error": f"Order not found: {order_id}"})
        if not executor.in_scope(order):
            return json.dumps({"error": f"Order {order_id} {OUT_OF_SCOPE_MSG}"})

        try:
            step_number = self._db.get_max_step_number(order_id) + 1
        except Exception as exc:
            logger.error("Failed to get step number for %s: %s", order_id, exc)
            return json.dumps({"error": f"Database error: {type(exc).__name__}"})

        event = Event(
            event_id=str(uuid.uuid4()),
            order_id=order_id,
            step_number=step_number,
            event_type=event_type,
            event_data=event_data if isinstance(event_data, dict) else {},
            created_at=datetime.now(),
        )

        try:
            result = self._routing_service.process_event(order_id, event)
        except Exception as exc:
            logger.error(
                "submit_event failed for %s/%s: %s: %s",
                order_id,
                event_type,
                type(exc).__name__,
                exc,
            )
            return json.dumps({"error": str(exc)})

        return json.dumps(
            {
                "applied": result.applied,
                "from_state": result.from_state,
                "to_state": result.to_state,
                "applied_rules": list(result.applied_rules),
                "reasoning": result.reasoning,
                "error": result.error,
            }
        )

    def _get_or_create_session(self, session_id: str, role: str) -> list[ChatMessage]:
        """Get existing session or create with system prompt."""
        if session_id not in self._sessions:
            # Evict oldest session if at capacity
            if len(self._sessions) >= _MAX_SESSIONS:
                oldest_key = next(iter(self._sessions))
                del self._sessions[oldest_key]
                self._executors.pop(oldest_key, None)
            executor = LiveToolExecutor(self._db, role=role)
            system_prompt = _build_system_prompt(role)
            self._sessions[session_id] = [ChatMessage(role=ChatRole.SYSTEM, content=system_prompt)]
            self._executors[session_id] = executor
        return self._sessions[session_id]

    def _append_error_assistant_message(self, messages: list[ChatMessage], error_msg: str) -> None:
        """Append a synthetic assistant message to keep history valid."""
        messages.append(
            ChatMessage(
                role=ChatRole.ASSISTANT,
                content=f"[Error: {error_msg}]",
            )
        )

    def handle_message_stream(
        self,
        session_id: str,
        user_message: str,
        role: str,
    ) -> Iterator[dict[str, Any]]:
        """Process a user message, yielding streaming events.

        Yields dicts that map to WebSocket JSON frames:
        - ``{"type": "token", "content": "..."}``
        - ``{"type": "tool_status", "tool": "...", "status": "executing"}``
        - ``{"type": "tool_status", "tool": "...", "status": "complete"}``
        - ``{"type": "done", "session_id": "...", "latency_ms": ...}``
        - ``{"type": "error", "message": "..."}``
        """
        start = time.monotonic()
        messages = self._get_or_create_session(session_id, role)
        messages.append(ChatMessage(role=ChatRole.USER, content=user_message))

        for _turn in range(1, _MAX_TOOL_USE_TURNS + 1):
            final_response: ChatResponse | None = None

            if self._supports_streaming:
                for item in self._adapter.chat_stream(  # type: ignore[attr-defined]
                    messages, tools=self._tools
                ):
                    if isinstance(item, str):
                        yield {"type": "token", "content": item}
                    elif isinstance(item, ChatResponse):
                        final_response = item
            else:
                # Non-streaming fallback (e.g. OpenRouter)
                final_response = self._adapter.chat(messages, tools=self._tools)
                if (
                    final_response.message.content is not None
                    and not final_response.message.tool_calls
                ):
                    yield {
                        "type": "token",
                        "content": final_response.message.content,
                    }

            if final_response is None:
                error_msg = "No response from model"
                self._append_error_assistant_message(messages, error_msg)
                yield {"type": "error", "message": error_msg}
                return

            if final_response.error is not None:
                self._append_error_assistant_message(messages, final_response.error)
                yield {"type": "error", "message": final_response.error}
                return

            msg = final_response.message

            # Model returned tool calls — execute and continue loop
            if msg.tool_calls:
                messages.append(msg)
                for tc in msg.tool_calls:
                    yield {
                        "type": "tool_status",
                        "tool": tc.function_name,
                        "status": "executing",
                    }
                    result_str = self._execute_tool(session_id, tc.function_name, tc.arguments)
                    yield {
                        "type": "tool_status",
                        "tool": tc.function_name,
                        "status": "complete",
                    }
                    messages.append(
                        ChatMessage(
                            role=ChatRole.TOOL,
                            content=result_str,
                            tool_call_id=tc.id,
                        )
                    )
                continue

            # Model returned text — we're done
            if msg.content is not None:
                messages.append(msg)
                latency_ms = (time.monotonic() - start) * 1000
                yield {
                    "type": "done",
                    "session_id": session_id,
                    "latency_ms": round(latency_ms, 1),
                }
                return

            # Neither tool calls nor content
            error_msg = "Model returned empty response"
            self._append_error_assistant_message(messages, error_msg)
            yield {"type": "error", "message": error_msg}
            return

        # Max turns exceeded — append synthetic assistant message to keep
        # session history valid for subsequent calls
        error_msg = f"Reached maximum {_MAX_TOOL_USE_TURNS} tool-use turns"
        logger.warning(
            "Chat session %s reached %d turns without converging",
            session_id,
            _MAX_TOOL_USE_TURNS,
        )
        self._append_error_assistant_message(messages, error_msg)
        yield {"type": "error", "message": error_msg}
