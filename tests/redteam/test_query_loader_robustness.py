"""Red-team tests: malformed JSON fed to query scenario loaders.

Each test starts from a minimal valid query scenario dict and corrupts
one thing. Tests surface uncaught errors for missing required fields and
document silently accepted but semantically wrong inputs.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from src.simulator.loader import (
    load_all_query_scenarios,
    load_query_scenario,
    load_query_scenarios_by_tier,
)

# ---------------------------------------------------------------------------
# Minimal valid query scenario baseline
# ---------------------------------------------------------------------------

_MINIMAL_ORDER: dict[str, Any] = {
    "order_id": "ORD-001",
    "current_state": "ACCEPTED",
    "specimen_type": "biopsy",
    "anatomic_site": "breast",
    "priority": "routine",
    "flags": [],
}

_MINIMAL_VALID: dict[str, Any] = {
    "scenario_id": "QR-001",
    "category": "query",
    "tier": 1,
    "description": "Minimal valid query scenario",
    "database_state": {
        "orders": [_MINIMAL_ORDER],
        "slides": [],
    },
    "query": "What orders are ready?",
    "expected_output": {
        "answer_type": "explanation",
        "reasoning": "Only one order is present.",
    },
}


@pytest.fixture()
def minimal_valid_query() -> dict[str, Any]:
    """Return a deep copy of the minimal valid query scenario dict."""
    return copy.deepcopy(_MINIMAL_VALID)


@pytest.fixture()
def make_json(tmp_path: Path) -> Callable[..., Path]:
    """Factory fixture: write a dict as JSON to a temp file, return its Path."""

    def _make(data: Any, filename: str = "scenario.json") -> Path:
        p = tmp_path / filename
        p.write_text(json.dumps(data))
        return p

    return _make


# ---------------------------------------------------------------------------
# Top-level structural errors
# ---------------------------------------------------------------------------


class TestMalformedJSONStructure:
    """JSON root is wrong type, or required top-level keys are missing."""

    def test_list_root(self, make_json: Any) -> None:
        """JSON root is a list → ValueError."""
        path = make_json([1, 2, 3])
        with pytest.raises(ValueError, match="JSON object"):
            load_query_scenario(path)

    def test_string_root(self, make_json: Any) -> None:
        """JSON root is a string → ValueError."""
        path = make_json("just a string")
        with pytest.raises(ValueError, match="JSON object"):
            load_query_scenario(path)

    def test_null_root(self, make_json: Any) -> None:
        """JSON root is null → ValueError."""
        path = make_json(None)
        with pytest.raises(ValueError, match="JSON object"):
            load_query_scenario(path)

    @pytest.mark.parametrize(
        "missing_key",
        [
            "scenario_id",
            "category",
            "tier",
            "description",
            "database_state",
            "query",
            "expected_output",
        ],
    )
    def test_missing_required_key(
        self, make_json: Any, minimal_valid_query: dict[str, Any], missing_key: str
    ) -> None:
        """Each required key missing one at a time → ValueError."""
        data = minimal_valid_query
        del data[missing_key]
        path = make_json(data)
        with pytest.raises(ValueError, match="missing required keys"):
            load_query_scenario(path)

    def test_extra_keys_accepted(self, make_json: Any, minimal_valid_query: dict[str, Any]) -> None:
        """Extra top-level keys should not cause an error."""
        data = minimal_valid_query
        data["extra_key"] = "bonus"
        data["another_extra"] = 42
        path = make_json(data)
        scenario = load_query_scenario(path)
        assert scenario.scenario_id == "QR-001"

    def test_invalid_json_syntax(self, tmp_path: Path) -> None:
        """Unparseable JSON → ValueError."""
        p = tmp_path / "bad.json"
        p.write_text('{"scenario_id": "QR-001", trailing}')
        with pytest.raises(ValueError, match="Invalid JSON"):
            load_query_scenario(p)

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        """Nonexistent file → FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_query_scenario(tmp_path / "does_not_exist.json")


# ---------------------------------------------------------------------------
# database_state corruption
# ---------------------------------------------------------------------------


class TestDatabaseStateCorruption:
    """database_state field has wrong type or structure."""

    def test_database_state_as_string(
        self, make_json: Any, minimal_valid_query: dict[str, Any]
    ) -> None:
        """database_state is a string → ValueError."""
        data = minimal_valid_query
        data["database_state"] = "not a dict"
        path = make_json(data)
        with pytest.raises(ValueError, match="must be a dict"):
            load_query_scenario(path)

    def test_database_state_as_list(
        self, make_json: Any, minimal_valid_query: dict[str, Any]
    ) -> None:
        """database_state is a list → ValueError."""
        data = minimal_valid_query
        data["database_state"] = [1, 2, 3]
        path = make_json(data)
        with pytest.raises(ValueError, match="must be a dict"):
            load_query_scenario(path)

    def test_database_state_as_null(
        self, make_json: Any, minimal_valid_query: dict[str, Any]
    ) -> None:
        """database_state is null → ValueError."""
        data = minimal_valid_query
        data["database_state"] = None
        path = make_json(data)
        with pytest.raises(ValueError, match="must be a dict"):
            load_query_scenario(path)

    def test_orders_as_string(self, make_json: Any, minimal_valid_query: dict[str, Any]) -> None:
        """database_state.orders is a string → ValueError."""
        data = minimal_valid_query
        data["database_state"]["orders"] = "not a list"
        path = make_json(data)
        with pytest.raises(ValueError, match="orders.*must be a list"):
            load_query_scenario(path)

    def test_orders_as_dict(self, make_json: Any, minimal_valid_query: dict[str, Any]) -> None:
        """database_state.orders is a dict → ValueError."""
        data = minimal_valid_query
        data["database_state"]["orders"] = {"ORD-001": {}}
        path = make_json(data)
        with pytest.raises(ValueError, match="orders.*must be a list"):
            load_query_scenario(path)

    def test_orders_as_null(self, make_json: Any, minimal_valid_query: dict[str, Any]) -> None:
        """database_state.orders is null (missing via .get) → ValueError."""
        data = minimal_valid_query
        data["database_state"]["orders"] = None
        path = make_json(data)
        with pytest.raises(ValueError, match="orders.*must be a list"):
            load_query_scenario(path)

    def test_orders_empty_list(self, make_json: Any, minimal_valid_query: dict[str, Any]) -> None:
        """database_state.orders is empty list → ValueError from schema."""
        data = minimal_valid_query
        data["database_state"]["orders"] = []
        path = make_json(data)
        with pytest.raises(ValueError, match="orders must not be empty"):
            load_query_scenario(path)

    def test_slides_missing_defaults_to_empty(
        self, make_json: Any, minimal_valid_query: dict[str, Any]
    ) -> None:
        """database_state.slides missing → defaults to empty tuple."""
        data = minimal_valid_query
        del data["database_state"]["slides"]
        path = make_json(data)
        scenario = load_query_scenario(path)
        assert scenario.database_state.slides == ()

    def test_slides_as_string(self, make_json: Any, minimal_valid_query: dict[str, Any]) -> None:
        """database_state.slides is a string → ValueError."""
        data = minimal_valid_query
        data["database_state"]["slides"] = "not a list"
        path = make_json(data)
        with pytest.raises(ValueError, match="slides.*must be a list"):
            load_query_scenario(path)

    def test_slides_as_dict(self, make_json: Any, minimal_valid_query: dict[str, Any]) -> None:
        """database_state.slides is a dict → ValueError."""
        data = minimal_valid_query
        data["database_state"]["slides"] = {"SL-001": {}}
        path = make_json(data)
        with pytest.raises(ValueError, match="slides.*must be a list"):
            load_query_scenario(path)

    @pytest.mark.parametrize(
        "missing_field",
        ["order_id", "current_state", "specimen_type", "anatomic_site", "priority"],
    )
    def test_order_missing_required_field(
        self, make_json: Any, minimal_valid_query: dict[str, Any], missing_field: str
    ) -> None:
        """Each required order field missing one at a time → ValueError."""
        data = minimal_valid_query
        del data["database_state"]["orders"][0][missing_field]
        path = make_json(data)
        with pytest.raises(ValueError, match="missing required fields"):
            load_query_scenario(path)

    def test_order_invalid_current_state(
        self, make_json: Any, minimal_valid_query: dict[str, Any]
    ) -> None:
        """Order with non-existent workflow state → ValueError."""
        data = minimal_valid_query
        data["database_state"]["orders"][0]["current_state"] = "INVALID_STATE"
        path = make_json(data)
        with pytest.raises(ValueError, match="invalid current_state"):
            load_query_scenario(path)

    def test_order_invalid_flag(self, make_json: Any, minimal_valid_query: dict[str, Any]) -> None:
        """Order with unrecognised flag → ValueError."""
        data = minimal_valid_query
        data["database_state"]["orders"][0]["flags"] = ["FAKE_FLAG"]
        path = make_json(data)
        with pytest.raises(ValueError, match="invalid flag"):
            load_query_scenario(path)


# ---------------------------------------------------------------------------
# expected_output corruption
# ---------------------------------------------------------------------------


class TestExpectedOutputCorruption:
    """expected_output field has wrong type or structure."""

    def test_expected_output_as_string(
        self, make_json: Any, minimal_valid_query: dict[str, Any]
    ) -> None:
        """expected_output is a string → ValueError."""
        data = minimal_valid_query
        data["expected_output"] = "not a dict"
        path = make_json(data)
        with pytest.raises(ValueError, match="must be a dict"):
            load_query_scenario(path)

    def test_expected_output_as_list(
        self, make_json: Any, minimal_valid_query: dict[str, Any]
    ) -> None:
        """expected_output is a list → ValueError."""
        data = minimal_valid_query
        data["expected_output"] = [1, 2]
        path = make_json(data)
        with pytest.raises(ValueError, match="must be a dict"):
            load_query_scenario(path)

    def test_expected_output_as_null(
        self, make_json: Any, minimal_valid_query: dict[str, Any]
    ) -> None:
        """expected_output is null → ValueError."""
        data = minimal_valid_query
        data["expected_output"] = None
        path = make_json(data)
        with pytest.raises(ValueError, match="must be a dict"):
            load_query_scenario(path)

    def test_missing_answer_type(self, make_json: Any, minimal_valid_query: dict[str, Any]) -> None:
        """expected_output missing answer_type → ValueError."""
        data = minimal_valid_query
        del data["expected_output"]["answer_type"]
        path = make_json(data)
        with pytest.raises(ValueError, match="missing required keys"):
            load_query_scenario(path)

    def test_missing_reasoning(self, make_json: Any, minimal_valid_query: dict[str, Any]) -> None:
        """expected_output missing reasoning → ValueError."""
        data = minimal_valid_query
        del data["expected_output"]["reasoning"]
        path = make_json(data)
        with pytest.raises(ValueError, match="missing required keys"):
            load_query_scenario(path)

    def test_order_ids_as_string(self, make_json: Any, minimal_valid_query: dict[str, Any]) -> None:
        """order_ids as string (not list) → ValueError, not silent char iteration."""
        data = minimal_valid_query
        data["expected_output"]["order_ids"] = "ORD-001"
        path = make_json(data)
        with pytest.raises(ValueError, match="order_ids must be a list"):
            load_query_scenario(path)

    def test_order_ids_missing_defaults_to_empty(
        self, make_json: Any, minimal_valid_query: dict[str, Any]
    ) -> None:
        """order_ids missing entirely → defaults to empty tuple."""
        data = minimal_valid_query
        # Ensure order_ids is not present.
        data["expected_output"].pop("order_ids", None)
        path = make_json(data)
        scenario = load_query_scenario(path)
        assert scenario.expected_output.order_ids == ()

    def test_invalid_answer_type(self, make_json: Any, minimal_valid_query: dict[str, Any]) -> None:
        """answer_type not in VALID_ANSWER_TYPES → ValueError."""
        data = minimal_valid_query
        data["expected_output"]["answer_type"] = "summary"
        path = make_json(data)
        with pytest.raises(ValueError, match="Invalid answer_type"):
            load_query_scenario(path)

    @pytest.mark.parametrize("answer_type", ["order_list", "order_status", "prioritized_list"])
    def test_order_answer_type_requires_order_ids(
        self, make_json: Any, minimal_valid_query: dict[str, Any], answer_type: str
    ) -> None:
        """answer_type that returns orders with no order_ids → ValueError."""
        data = minimal_valid_query
        data["expected_output"]["answer_type"] = answer_type
        data["expected_output"].pop("order_ids", None)
        path = make_json(data)
        with pytest.raises(ValueError, match="requires at least one order_id"):
            load_query_scenario(path)

    def test_order_ids_non_string_elements(
        self, make_json: Any, minimal_valid_query: dict[str, Any]
    ) -> None:
        """order_ids list containing non-string elements → TypeError."""
        data = minimal_valid_query
        data["expected_output"]["order_ids"] = [1, 2]
        path = make_json(data)
        with pytest.raises(TypeError, match=r"order_ids\[0\] must be str"):
            load_query_scenario(path)

    def test_empty_reasoning(self, make_json: Any, minimal_valid_query: dict[str, Any]) -> None:
        """reasoning is empty string → ValueError."""
        data = minimal_valid_query
        data["expected_output"]["reasoning"] = ""
        path = make_json(data)
        with pytest.raises(ValueError, match="reasoning must not be empty"):
            load_query_scenario(path)

    def test_whitespace_reasoning(
        self, make_json: Any, minimal_valid_query: dict[str, Any]
    ) -> None:
        """reasoning is whitespace-only → ValueError."""
        data = minimal_valid_query
        data["expected_output"]["reasoning"] = "   "
        path = make_json(data)
        with pytest.raises(ValueError, match="reasoning must not be empty"):
            load_query_scenario(path)


# ---------------------------------------------------------------------------
# Semantic validation (delegated to dataclass __post_init__)
# ---------------------------------------------------------------------------


class TestSemanticValidation:
    """Values pass structural checks but fail domain validation in __post_init__."""

    def test_invalid_scenario_id_format(
        self, make_json: Any, minimal_valid_query: dict[str, Any]
    ) -> None:
        """scenario_id not matching QR-NNN → ValueError."""
        data = minimal_valid_query
        data["scenario_id"] = "SC-001"
        path = make_json(data)
        with pytest.raises(ValueError, match="Must match QR-NNN"):
            load_query_scenario(path)

    def test_scenario_id_too_few_digits(
        self, make_json: Any, minimal_valid_query: dict[str, Any]
    ) -> None:
        """scenario_id with only two digits → ValueError."""
        data = minimal_valid_query
        data["scenario_id"] = "QR-01"
        path = make_json(data)
        with pytest.raises(ValueError, match="Must match QR-NNN"):
            load_query_scenario(path)

    def test_wrong_category(self, make_json: Any, minimal_valid_query: dict[str, Any]) -> None:
        """category != 'query' → ValueError."""
        data = minimal_valid_query
        data["category"] = "rule_coverage"
        path = make_json(data)
        with pytest.raises(ValueError, match="must be 'query'"):
            load_query_scenario(path)

    def test_empty_query_string(self, make_json: Any, minimal_valid_query: dict[str, Any]) -> None:
        """Empty query string → ValueError."""
        data = minimal_valid_query
        data["query"] = ""
        path = make_json(data)
        with pytest.raises(ValueError, match="query must not be empty"):
            load_query_scenario(path)

    def test_whitespace_query_string(
        self, make_json: Any, minimal_valid_query: dict[str, Any]
    ) -> None:
        """Whitespace-only query → ValueError."""
        data = minimal_valid_query
        data["query"] = "   \t\n"
        path = make_json(data)
        with pytest.raises(ValueError, match="query must not be empty"):
            load_query_scenario(path)

    def test_empty_description(self, make_json: Any, minimal_valid_query: dict[str, Any]) -> None:
        """Empty description → ValueError."""
        data = minimal_valid_query
        data["description"] = ""
        path = make_json(data)
        with pytest.raises(ValueError, match="description must not be empty"):
            load_query_scenario(path)

    def test_whitespace_description(
        self, make_json: Any, minimal_valid_query: dict[str, Any]
    ) -> None:
        """Whitespace-only description → ValueError."""
        data = minimal_valid_query
        data["description"] = "  "
        path = make_json(data)
        with pytest.raises(ValueError, match="description must not be empty"):
            load_query_scenario(path)

    def test_tier_above_maximum(self, make_json: Any, minimal_valid_query: dict[str, Any]) -> None:
        """tier=6 in JSON data exceeds 5-tier spec → ValueError."""
        data = minimal_valid_query
        data["tier"] = 6
        path = make_json(data)
        with pytest.raises(ValueError, match="tier must be 1-5"):
            load_query_scenario(path)

    def test_tier_as_string_in_json(
        self, make_json: Any, minimal_valid_query: dict[str, Any]
    ) -> None:
        """tier="1" (string in JSON) → TypeError from dataclass."""
        data = minimal_valid_query
        data["tier"] = "1"
        path = make_json(data)
        with pytest.raises(TypeError, match="tier must be int"):
            load_query_scenario(path)


# ---------------------------------------------------------------------------
# Loader edge cases: load_all_query_scenarios
# ---------------------------------------------------------------------------


class TestLoadAllQueryScenarios:
    """Edge cases for load_all_query_scenarios."""

    def test_empty_directory(self, tmp_path: Path) -> None:
        """Empty directory (no JSON files) → returns empty list."""
        result = load_all_query_scenarios(tmp_path)
        assert result == []

    def test_nonexistent_directory(self, tmp_path: Path) -> None:
        """Nonexistent directory → FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_all_query_scenarios(tmp_path / "does_not_exist")

    def test_mix_valid_and_invalid(self, tmp_path: Path) -> None:
        """Directory with valid + invalid JSON → any invalid file raises."""
        valid = copy.deepcopy(_MINIMAL_VALID)
        (tmp_path / "valid.json").write_text(json.dumps(valid))
        (tmp_path / "invalid.json").write_text(json.dumps({"bad": "data"}))
        with pytest.raises(ValueError, match="Failed to load"):
            load_all_query_scenarios(tmp_path)


# ---------------------------------------------------------------------------
# Loader edge cases: load_query_scenarios_by_tier
# ---------------------------------------------------------------------------


class TestLoadQueryScenariosByTier:
    """Edge cases for load_query_scenarios_by_tier."""

    def test_tier_zero(self, tmp_path: Path) -> None:
        """tier=0 → ValueError."""
        tmp_path.mkdir(exist_ok=True)
        with pytest.raises(ValueError, match="positive integer"):
            load_query_scenarios_by_tier(tmp_path, tier=0)

    def test_tier_negative(self, tmp_path: Path) -> None:
        """tier=-1 → ValueError."""
        with pytest.raises(ValueError, match="positive integer"):
            load_query_scenarios_by_tier(tmp_path, tier=-1)

    def test_tier_boolean(self, tmp_path: Path) -> None:
        """tier=True (bool is subclass of int) → ValueError."""
        with pytest.raises(ValueError, match="positive integer"):
            load_query_scenarios_by_tier(tmp_path, tier=True)

    def test_tier_float(self, tmp_path: Path) -> None:
        """tier=1.5 (float) → ValueError."""
        with pytest.raises(ValueError, match="positive integer"):
            load_query_scenarios_by_tier(tmp_path, tier=1.5)  # type: ignore[arg-type]

    def test_tier_filters_correctly(self, tmp_path: Path) -> None:
        """Valid tier filtering returns only matching scenarios."""
        t1 = copy.deepcopy(_MINIMAL_VALID)
        t1["scenario_id"] = "QR-001"
        t1["tier"] = 1
        t2 = copy.deepcopy(_MINIMAL_VALID)
        t2["scenario_id"] = "QR-002"
        t2["tier"] = 2
        (tmp_path / "qr_001.json").write_text(json.dumps(t1))
        (tmp_path / "qr_002.json").write_text(json.dumps(t2))

        result = load_query_scenarios_by_tier(tmp_path, tier=1)
        assert len(result) == 1
        assert result[0].scenario_id == "QR-001"
