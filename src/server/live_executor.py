"""Live tool executor for the chat interface.

Executes tool calls against the live SQLite database instead of
in-memory DatabaseStateSnapshot. Provides the same execute() interface
as ToolExecutor so the chat service can use either interchangeably.

Output shape intentionally omits ``scenario_id`` and timestamps
(``created_at``, ``updated_at``) since these are internal fields not
useful in LLM tool responses.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from src.server.roles import ROLE_STATES
from src.workflow.database import Database
from src.workflow.models import Order, Slide
from src.workflow.state_machine import StateMachine

logger = logging.getLogger(__name__)

OUT_OF_SCOPE_MSG = "is not in your workflow scope"


def order_to_dict(order: Order) -> dict[str, Any]:
    """Convert an Order dataclass to a dict for JSON serialization."""
    return {
        "order_id": order.order_id,
        "patient_name": order.patient_name,
        "patient_age": order.patient_age,
        "patient_sex": order.patient_sex,
        "specimen_type": order.specimen_type,
        "anatomic_site": order.anatomic_site,
        "fixative": order.fixative,
        "fixation_time_hours": order.fixation_time_hours,
        "ordered_tests": order.ordered_tests,
        "priority": order.priority,
        "billing_info_present": order.billing_info_present,
        "current_state": order.current_state,
        "flags": order.flags,
    }


def slide_to_dict(slide: Slide) -> dict[str, Any]:
    """Convert a Slide dataclass to a dict for JSON serialization."""
    return {
        "slide_id": slide.slide_id,
        "order_id": slide.order_id,
        "test_assignment": slide.test_assignment,
        "status": slide.status,
        "qc_result": slide.qc_result,
        "score_result": slide.score_result,
        "reported": slide.reported,
    }


class LiveToolExecutor:
    """Executes tool calls against the live database.

    Provides the same ``execute(tool_name, arguments) -> str`` interface
    as ``ToolExecutor`` but queries a live ``Database`` instead of an
    in-memory ``DatabaseStateSnapshot``.
    """

    def __init__(self, db: Database, role: str | None = None) -> None:
        if role is not None and role not in ROLE_STATES:
            raise ValueError(f"Unknown role: {role!r}")
        self._db = db
        self._state_machine = StateMachine.get_instance()
        self._allowed_states: frozenset[str] | None = ROLE_STATES.get(role) if role else None
        self._dispatch: dict[str, Callable[..., Any]] = {
            "list_orders": self._list_orders,
            "get_order": self._get_order,
            "get_slides": self._get_slides,
            "get_state_info": self._get_state_info,
            "get_flag_info": self._get_flag_info,
            "get_events": self._get_events,
        }

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Dispatch a tool call and return the JSON string result.

        Always returns a valid JSON string — never raises. Unknown tools,
        malformed arguments, and database errors all return structured
        error responses.
        """
        handler = self._dispatch.get(tool_name)
        if handler is None:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})
        try:
            result = handler(**arguments)
            return json.dumps(result)
        except TypeError as exc:
            return json.dumps({"error": f"Invalid arguments for {tool_name}: {exc}"})
        except Exception as exc:
            logger.error("Tool %s failed: %s: %s", tool_name, type(exc).__name__, exc)
            return json.dumps({"error": f"Tool execution failed: {type(exc).__name__}"})

    def in_scope(self, order: Order) -> bool:
        """Check if an order is within this executor's role scope."""
        if self._allowed_states is None:
            return True
        return order.current_state in self._allowed_states

    def _list_orders(
        self,
        state: str | None = None,
        priority: str | None = None,
        has_flags: bool | None = None,
    ) -> list[dict[str, Any]]:
        """Filter and list orders from the live database."""
        orders = self._db.list_orders(state=state, priority=priority, has_flags=has_flags)
        if self._allowed_states is not None:
            orders = [o for o in orders if o.current_state in self._allowed_states]
        return [order_to_dict(o) for o in orders]

    def _get_order(self, order_id: str) -> dict[str, Any]:
        """Get full details for a specific order."""
        order = self._db.get_order(order_id)
        if order is None:
            return {"error": f"Order not found: {order_id}"}
        if not self.in_scope(order):
            return {"error": f"Order {order_id} {OUT_OF_SCOPE_MSG}"}
        return order_to_dict(order)

    def _get_slides(self, order_id: str) -> list[dict[str, Any]] | dict[str, Any]:
        """Get all slides for a specific order."""
        order = self._db.get_order(order_id)
        if order is None:
            return {"error": f"Order not found: {order_id}"}
        if not self.in_scope(order):
            return {"error": f"Order {order_id} {OUT_OF_SCOPE_MSG}"}
        slides = self._db.get_slides_for_order(order_id)
        return [slide_to_dict(s) for s in slides]

    def _get_state_info(self, state_id: str) -> dict[str, Any]:
        """Get information about a workflow state."""
        try:
            state = self._state_machine.get_state(state_id)
        except KeyError:
            return {"error": f"Unknown state: {state_id}"}
        return {
            "state_id": state.id,
            "phase": state.phase,
            "description": state.description,
            "terminal": state.terminal,
        }

    def _get_flag_info(self, flag_id: str) -> dict[str, Any]:
        """Get information about a workflow flag."""
        vocabulary = self._state_machine.get_flag_vocabulary()
        flag_data = vocabulary.get(flag_id)
        if flag_data is None:
            return {"error": f"Unknown flag: {flag_id}"}
        return {"flag_id": flag_id, **flag_data}

    # Fields stripped from event_data to avoid sending PHI through
    # tool results (which may be forwarded to cloud model providers).
    _PHI_FIELDS: frozenset[str] = frozenset(
        {
            "patient_name",
            "age",
            "sex",
        }
    )

    def _get_events(self, order_id: str) -> list[dict[str, Any]] | dict[str, Any]:
        """Get event history for a specific order."""
        order = self._db.get_order(order_id)
        if order is None:
            return {"error": f"Order not found: {order_id}"}
        if not self.in_scope(order):
            return {"error": f"Order {order_id} {OUT_OF_SCOPE_MSG}"}
        events = self._db.get_events_for_order(order_id)
        return [
            {
                "step_number": e.step_number,
                "event_type": e.event_type,
                "event_data": {k: v for k, v in e.event_data.items() if k not in self._PHI_FIELDS},
            }
            for e in events
        ]
