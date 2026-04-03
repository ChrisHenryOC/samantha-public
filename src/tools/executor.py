"""Tool executor for tool-use query evaluation.

Executes tool calls against a DatabaseStateSnapshot in memory.
Returns JSON strings suitable for sending back to the model as
tool results.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from src.simulator.schema import DatabaseStateSnapshot
from src.workflow.state_machine import StateMachine


class ToolExecutor:
    """Executes tool calls against an in-memory database snapshot.

    Tools operate on the scenario's DatabaseStateSnapshot (orders and
    slides) and the StateMachine singleton (state/flag metadata).
    """

    def __init__(self, database_state: DatabaseStateSnapshot) -> None:
        self._orders = database_state.orders
        self._slides = database_state.slides
        # Index orders by ID for O(1) lookup.
        self._orders_by_id: dict[str, dict[str, Any]] = {
            order["order_id"]: order for order in self._orders
        }
        # Index slides by order_id for O(1) lookup.
        self._slides_by_order: dict[str, list[dict[str, Any]]] = {}
        for slide in self._slides:
            if "order_id" not in slide:
                raise ValueError(f"Slide missing required 'order_id' field: {slide}")
            self._slides_by_order.setdefault(slide["order_id"], []).append(slide)
        self._state_machine = StateMachine.get_instance()
        # Dispatch table built once (bound methods are stable after __init__).
        self._dispatch: dict[str, Callable[..., Any]] = {
            "list_orders": self._list_orders,
            "get_order": self._get_order,
            "get_slides": self._get_slides,
            "get_state_info": self._get_state_info,
            "get_flag_info": self._get_flag_info,
        }

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Dispatch a tool call and return the JSON string result.

        Unknown tools and malformed arguments return an error message
        instead of raising.
        """
        handler = self._dispatch.get(tool_name)
        if handler is None:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})
        try:
            result = handler(**arguments)
            return json.dumps(result)
        except TypeError as exc:
            return json.dumps({"error": f"Invalid arguments for {tool_name}: {exc}"})

    def _list_orders(
        self,
        state: str | None = None,
        priority: str | None = None,
        has_flags: bool | None = None,
    ) -> list[dict[str, Any]]:
        """Filter and list orders."""
        results: list[dict[str, Any]] = []
        for order in self._orders:
            if state is not None and order["current_state"] != state:
                continue
            if priority is not None and order["priority"] != priority:
                continue
            if has_flags is True and not order.get("flags"):
                continue
            if has_flags is False and order.get("flags"):
                continue
            results.append(order)
        return results

    def _get_order(self, order_id: str) -> dict[str, Any]:
        """Get full details for a specific order."""
        order = self._orders_by_id.get(order_id)
        if order is None:
            return {"error": f"Order not found: {order_id}"}
        return dict(order)

    def _get_slides(self, order_id: str) -> list[dict[str, Any]] | dict[str, Any]:
        """Get all slides for a specific order."""
        if order_id not in self._orders_by_id:
            return {"error": f"Order not found: {order_id}"}
        return [dict(s) for s in self._slides_by_order.get(order_id, [])]

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
