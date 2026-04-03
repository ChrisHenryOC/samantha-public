"""Tool definitions for tool-use query evaluation.

Defines 6 tools as JSON Schema in OpenAI function-calling format
(compatible with both Ollama and OpenRouter). Each tool has a name,
description, and parameters schema.
"""

from __future__ import annotations

import copy
from typing import Any, TypedDict


class ParametersSchema(TypedDict):
    """JSON Schema for tool parameters (OpenAI function-calling format)."""

    type: str  # Always "object"
    properties: dict[str, dict[str, Any]]
    required: list[str]


class FunctionSchema(TypedDict):
    """Function definition within a tool (OpenAI function-calling format)."""

    name: str
    description: str
    parameters: ParametersSchema


class ToolDefinition(TypedDict):
    """Complete tool definition in OpenAI function-calling format."""

    type: str  # Always "function"
    function: FunctionSchema


_LIST_ORDERS: ToolDefinition = {
    "type": "function",
    "function": {
        "name": "list_orders",
        "description": ("List orders, optionally filtered by state, priority, or flag presence."),
        "parameters": {
            "type": "object",
            "properties": {
                "state": {
                    "type": "string",
                    "description": "Filter by current_state (e.g. ACCEPTED, RESULTING)",
                },
                "priority": {
                    "type": "string",
                    "enum": ["rush", "routine"],
                    "description": "Filter by priority (rush or routine)",
                },
                "has_flags": {
                    "type": "boolean",
                    "description": "If true, only orders with active flags",
                },
            },
            "required": [],
        },
    },
}

_GET_ORDER: ToolDefinition = {
    "type": "function",
    "function": {
        "name": "get_order",
        "description": "Get full details for a specific order by ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "The order ID to look up (e.g. ORD-101)",
                },
            },
            "required": ["order_id"],
        },
    },
}

_GET_SLIDES: ToolDefinition = {
    "type": "function",
    "function": {
        "name": "get_slides",
        "description": "Get all slides for a specific order.",
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "The order ID whose slides to retrieve",
                },
            },
            "required": ["order_id"],
        },
    },
}

_GET_STATE_INFO: ToolDefinition = {
    "type": "function",
    "function": {
        "name": "get_state_info",
        "description": (
            "Get information about a workflow state: its phase, description, "
            "and whether it is terminal."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "state_id": {
                    "type": "string",
                    "description": "The state ID to look up (e.g. ACCEPTED, HE_QC)",
                },
            },
            "required": ["state_id"],
        },
    },
}

_GET_FLAG_INFO: ToolDefinition = {
    "type": "function",
    "function": {
        "name": "get_flag_info",
        "description": (
            "Get information about a workflow flag: where it is set, "
            "its effect, and how it is cleared."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "flag_id": {
                    "type": "string",
                    "description": "The flag ID to look up (e.g. MISSING_INFO_HOLD)",
                },
            },
            "required": ["flag_id"],
        },
    },
}

_GET_EVENTS: ToolDefinition = {
    "type": "function",
    "function": {
        "name": "get_events",
        "description": (
            "Get the event history for an order, showing each workflow event "
            "and its data in chronological order. Always call this tool when "
            "explaining why a flag is set or why an order is in its current "
            "state — it shows the specific events that led there."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "The order ID whose events to retrieve (e.g. ORD-101)",
                },
            },
            "required": ["order_id"],
        },
    },
}

TOOL_REGISTRY: dict[str, ToolDefinition] = {
    "list_orders": _LIST_ORDERS,
    "get_order": _GET_ORDER,
    "get_slides": _GET_SLIDES,
    "get_state_info": _GET_STATE_INFO,
    "get_flag_info": _GET_FLAG_INFO,
    "get_events": _GET_EVENTS,
}


def get_all_tool_definitions() -> list[ToolDefinition]:
    """Return all tool definitions in API-ready format.

    Returns deep copies so callers can modify definitions without
    corrupting the shared registry.
    """
    return [copy.deepcopy(defn) for defn in TOOL_REGISTRY.values()]
