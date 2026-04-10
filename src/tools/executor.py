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
            # Routing tools (tool-assisted routing experiment)
            "check_threshold": self._check_threshold,
            "check_field_present": self._check_field_present,
            "check_enum_membership": self._check_enum_membership,
            "list_applicable_rules": self._list_applicable_rules,
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

    # --- Routing tools (tool-assisted routing experiment) ---

    @staticmethod
    def _check_threshold(
        value: float | int,
        min: float | int,
        max: float | int,
    ) -> dict[str, Any]:
        """Check whether a numeric value falls within a range (inclusive)."""
        in_range = min <= value <= max
        return {"in_range": in_range, "value": value, "min": min, "max": max}

    @staticmethod
    def _check_field_present(
        field_name: str,
        field_value: Any,
    ) -> dict[str, Any]:
        """Check whether a field has a non-null, non-empty value."""
        if field_value is None or (isinstance(field_value, str) and not field_value.strip()):
            present = False
        else:
            present = True
        return {"present": present, "field": field_name, "value": field_value}

    @staticmethod
    def _check_enum_membership(
        value: str,
        allowed_values: list[str],
    ) -> dict[str, Any]:
        """Check whether a value is in an allowed set (case-insensitive)."""
        value_lower = value.lower()
        allowed_lower = {v.lower() for v in allowed_values}
        is_member = value_lower in allowed_lower
        return {"is_member": is_member, "value": value, "allowed": allowed_values}

    def _list_applicable_rules(self, current_state: str) -> list[dict[str, str]] | dict[str, str]:
        """List all rules that could apply at the given workflow state."""
        try:
            rules = self._state_machine.get_rules_for_state(current_state)
        except (ValueError, KeyError):
            return {"error": f"Unknown state: {current_state}"}
        return [
            {
                "rule_id": r.rule_id,
                "trigger": r.trigger,
                "action": r.action,
            }
            for r in rules
        ]
