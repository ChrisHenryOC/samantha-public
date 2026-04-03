"""Tests for tool definition schemas and registry.

Validates JSON Schema structure, registry completeness, and
get_all_tool_definitions() output format.
"""

from __future__ import annotations

import pytest

from src.tools.definitions import (
    TOOL_REGISTRY,
    ToolDefinition,
    get_all_tool_definitions,
)

# Expected tool names from the Phase 7a plan.
EXPECTED_TOOLS = {
    "list_orders",
    "get_order",
    "get_slides",
    "get_state_info",
    "get_flag_info",
    "get_events",
}


class TestToolRegistry:
    def test_registry_contains_all_expected_tools(self) -> None:
        assert set(TOOL_REGISTRY.keys()) == EXPECTED_TOOLS

    def test_registry_values_are_dicts(self) -> None:
        for name, defn in TOOL_REGISTRY.items():
            assert isinstance(defn, dict), f"{name} definition is not a dict"


class TestToolSchemaStructure:
    """Each tool definition must follow OpenAI function-calling format."""

    @pytest.fixture(params=list(TOOL_REGISTRY.keys()))
    def tool_def(self, request: pytest.FixtureRequest) -> tuple[str, ToolDefinition]:
        name = request.param
        return name, TOOL_REGISTRY[name]

    def test_has_type_function(self, tool_def: tuple[str, ToolDefinition]) -> None:
        name, defn = tool_def
        assert defn["type"] == "function", f"{name}: type must be 'function'"

    def test_has_function_key(self, tool_def: tuple[str, ToolDefinition]) -> None:
        name, defn = tool_def
        assert "function" in defn, f"{name}: missing 'function' key"

    def test_function_has_name(self, tool_def: tuple[str, ToolDefinition]) -> None:
        name, defn = tool_def
        func = defn["function"]
        assert func["name"] == name, f"Registry key '{name}' != function name '{func['name']}'"

    def test_function_has_description(self, tool_def: tuple[str, ToolDefinition]) -> None:
        name, defn = tool_def
        func = defn["function"]
        assert isinstance(func["description"], str), f"{name}: description must be str"
        assert len(func["description"]) > 0, f"{name}: description must not be empty"

    def test_function_has_parameters(self, tool_def: tuple[str, ToolDefinition]) -> None:
        name, defn = tool_def
        func = defn["function"]
        params = func["parameters"]
        assert params["type"] == "object", f"{name}: parameters.type must be 'object'"
        assert "properties" in params, f"{name}: parameters must have 'properties'"
        assert "required" in params, f"{name}: parameters must have 'required'"

    def test_required_is_subset_of_properties(self, tool_def: tuple[str, ToolDefinition]) -> None:
        name, defn = tool_def
        params = defn["function"]["parameters"]
        props = set(params["properties"].keys())
        required = set(params["required"])
        assert required <= props, f"{name}: required {required - props} not in properties"


class TestToolRequiredParameters:
    """Verify which parameters are required vs optional for each tool."""

    def test_list_orders_has_no_required(self) -> None:
        params = TOOL_REGISTRY["list_orders"]["function"]["parameters"]
        assert params["required"] == []

    def test_get_order_requires_order_id(self) -> None:
        params = TOOL_REGISTRY["get_order"]["function"]["parameters"]
        assert params["required"] == ["order_id"]

    def test_get_slides_requires_order_id(self) -> None:
        params = TOOL_REGISTRY["get_slides"]["function"]["parameters"]
        assert params["required"] == ["order_id"]

    def test_get_state_info_requires_state_id(self) -> None:
        params = TOOL_REGISTRY["get_state_info"]["function"]["parameters"]
        assert params["required"] == ["state_id"]

    def test_get_flag_info_requires_flag_id(self) -> None:
        params = TOOL_REGISTRY["get_flag_info"]["function"]["parameters"]
        assert params["required"] == ["flag_id"]

    def test_get_events_requires_order_id(self) -> None:
        params = TOOL_REGISTRY["get_events"]["function"]["parameters"]
        assert params["required"] == ["order_id"]


class TestListOrdersProperties:
    def test_has_state_property(self) -> None:
        props = TOOL_REGISTRY["list_orders"]["function"]["parameters"]["properties"]
        assert "state" in props
        assert props["state"]["type"] == "string"

    def test_has_priority_property(self) -> None:
        props = TOOL_REGISTRY["list_orders"]["function"]["parameters"]["properties"]
        assert "priority" in props
        assert props["priority"]["type"] == "string"

    def test_has_flags_property(self) -> None:
        props = TOOL_REGISTRY["list_orders"]["function"]["parameters"]["properties"]
        assert "has_flags" in props
        assert props["has_flags"]["type"] == "boolean"

    def test_priority_has_enum(self) -> None:
        props = TOOL_REGISTRY["list_orders"]["function"]["parameters"]["properties"]
        assert props["priority"]["enum"] == ["rush", "routine"]


class TestGetAllToolDefinitions:
    def test_returns_list(self) -> None:
        result = get_all_tool_definitions()
        assert isinstance(result, list)

    def test_returns_correct_count(self) -> None:
        result = get_all_tool_definitions()
        assert len(result) == 6

    def test_returns_all_tool_names(self) -> None:
        result = get_all_tool_definitions()
        names = {d["function"]["name"] for d in result}
        assert names == EXPECTED_TOOLS

    def test_returns_deep_copies(self) -> None:
        a = get_all_tool_definitions()
        b = get_all_tool_definitions()
        assert a is not b
        # Elements are deep copies, not shared references.
        assert a[0] is not b[0]
        # Mutating a returned definition does not corrupt the registry.
        a[0]["function"]["name"] = "mutated"
        fresh = get_all_tool_definitions()
        assert fresh[0]["function"]["name"] != "mutated"
