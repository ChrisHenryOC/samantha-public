"""Tests for scenario data model and file loader."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.simulator.loader import (
    load_all_query_scenarios,
    load_all_scenarios,
    load_query_scenario,
    load_query_scenarios_by_tier,
    load_scenario,
    load_scenarios_by_category,
)
from src.simulator.schema import (
    VALID_ANSWER_TYPES,
    VALID_CATEGORIES,
    VALID_EVENT_TYPES,
    DatabaseStateSnapshot,
    ExpectedOutput,
    QueryExpectedOutput,
    QueryScenario,
    Scenario,
    ScenarioStep,
)
from src.workflow.models import VALID_FLAGS, VALID_STATES

# --- Factory helpers ---


def _make_expected_output(**overrides: Any) -> ExpectedOutput:
    defaults: dict[str, Any] = {
        "next_state": "ACCEPTED",
        "applied_rules": ("ACC-008",),
        "flags": (),
    }
    defaults.update(overrides)
    return ExpectedOutput(**defaults)


def _make_scenario_step(**overrides: Any) -> ScenarioStep:
    defaults: dict[str, Any] = {
        "step": 1,
        "event_type": "order_received",
        "event_data": {"patient_name": "TESTPATIENT-0001, Jane"},
        "expected_output": _make_expected_output(),
    }
    defaults.update(overrides)
    return ScenarioStep(**defaults)


def _make_scenario(**overrides: Any) -> Scenario:
    defaults: dict[str, Any] = {
        "scenario_id": "SC-001",
        "category": "rule_coverage",
        "description": "Standard order, all validations pass",
        "steps": (_make_scenario_step(),),
    }
    defaults.update(overrides)
    return Scenario(**defaults)


def _write_scenario_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _valid_scenario_dict(**overrides: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "scenario_id": "SC-001",
        "category": "rule_coverage",
        "description": "Standard order, all validations pass",
        "events": [
            {
                "step": 1,
                "event_type": "order_received",
                "event_data": {"patient_name": "TESTPATIENT-0001, Jane"},
                "expected_output": {
                    "next_state": "ACCEPTED",
                    "applied_rules": ["ACC-008"],
                    "flags": [],
                },
            },
        ],
    }
    defaults.update(overrides)
    return defaults


# --- TestExpectedOutput ---


class TestExpectedOutput:
    def test_valid_construction(self) -> None:
        eo = _make_expected_output()
        assert eo.next_state == "ACCEPTED"
        assert eo.applied_rules == ("ACC-008",)
        assert eo.flags == ()

    def test_frozen(self) -> None:
        eo = _make_expected_output()
        with pytest.raises(AttributeError):
            eo.next_state = "REJECTED"  # type: ignore[misc]

    def test_next_state_must_be_str(self) -> None:
        with pytest.raises(TypeError, match="next_state must be str"):
            _make_expected_output(next_state=123)

    def test_applied_rules_must_be_tuple(self) -> None:
        with pytest.raises(TypeError, match="applied_rules must be tuple"):
            _make_expected_output(applied_rules=["ACC-008"])

    def test_applied_rules_elements_must_be_str(self) -> None:
        with pytest.raises(TypeError, match=r"applied_rules\[0\] must be str"):
            _make_expected_output(applied_rules=(123,))

    def test_flags_must_be_tuple(self) -> None:
        with pytest.raises(TypeError, match="flags must be tuple"):
            _make_expected_output(flags=["FISH_SUGGESTED"])

    def test_flags_elements_must_be_str(self) -> None:
        with pytest.raises(TypeError, match=r"flags\[0\] must be str"):
            _make_expected_output(flags=(42,))

    def test_next_state_must_be_valid_state(self) -> None:
        with pytest.raises(ValueError, match="Invalid next_state"):
            _make_expected_output(next_state="BOGUS_STATE")

    def test_next_state_accepts_all_valid_states(self) -> None:
        for state in VALID_STATES:
            eo = _make_expected_output(next_state=state)
            assert eo.next_state == state

    def test_applied_rules_must_match_pattern(self) -> None:
        with pytest.raises(ValueError, match="Invalid applied_rules"):
            _make_expected_output(applied_rules=("BOGUS-RULE",))

    def test_applied_rules_rejects_wrong_prefix(self) -> None:
        with pytest.raises(ValueError, match="Invalid applied_rules"):
            _make_expected_output(applied_rules=("XXX-001",))

    def test_applied_rules_accepts_valid_prefixes(self) -> None:
        for prefix in ("ACC", "SP", "HE", "IHC", "RES"):
            eo = _make_expected_output(applied_rules=(f"{prefix}-001",))
            assert eo.applied_rules == (f"{prefix}-001",)

    def test_flags_must_be_valid_flags(self) -> None:
        with pytest.raises(ValueError, match="Invalid flags"):
            _make_expected_output(flags=("BOGUS_FLAG",))

    def test_flags_accepts_all_valid_flags(self) -> None:
        for flag in VALID_FLAGS:
            eo = _make_expected_output(flags=(flag,))
            assert eo.flags == (flag,)


# --- TestScenarioStep ---


class TestScenarioStep:
    def test_valid_construction(self) -> None:
        step = _make_scenario_step()
        assert step.step == 1
        assert step.event_type == "order_received"
        assert step.event_data == {"patient_name": "TESTPATIENT-0001, Jane"}
        assert isinstance(step.expected_output, ExpectedOutput)

    def test_frozen(self) -> None:
        step = _make_scenario_step()
        with pytest.raises(AttributeError):
            step.step = 2  # type: ignore[misc]

    def test_step_must_be_int(self) -> None:
        with pytest.raises(TypeError, match="step must be int"):
            _make_scenario_step(step="1")

    def test_step_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="step must be >= 1"):
            _make_scenario_step(step=0)

    def test_step_rejects_negative(self) -> None:
        with pytest.raises(ValueError, match="step must be >= 1"):
            _make_scenario_step(step=-1)

    def test_event_type_must_be_str(self) -> None:
        with pytest.raises(TypeError, match="event_type must be str"):
            _make_scenario_step(event_type=123)

    def test_invalid_event_type(self) -> None:
        with pytest.raises(ValueError, match="Invalid event_type"):
            _make_scenario_step(event_type="bogus_event")

    def test_all_valid_event_types(self) -> None:
        for event_type in VALID_EVENT_TYPES:
            step = _make_scenario_step(step=1, event_type=event_type)
            assert step.event_type == event_type

    def test_event_data_must_be_dict(self) -> None:
        with pytest.raises(TypeError, match="event_data must be dict"):
            _make_scenario_step(event_data="not a dict")

    def test_expected_output_must_be_expected_output(self) -> None:
        with pytest.raises(TypeError, match="expected_output must be ExpectedOutput"):
            _make_scenario_step(expected_output={"next_state": "ACCEPTED"})


# --- TestScenario ---


class TestScenario:
    def test_valid_construction(self) -> None:
        scenario = _make_scenario()
        assert scenario.scenario_id == "SC-001"
        assert scenario.category == "rule_coverage"
        assert scenario.description == "Standard order, all validations pass"
        assert len(scenario.steps) == 1

    def test_frozen(self) -> None:
        scenario = _make_scenario()
        with pytest.raises(AttributeError):
            scenario.scenario_id = "SC-999"  # type: ignore[misc]

    def test_scenario_id_must_be_str(self) -> None:
        with pytest.raises(TypeError, match="scenario_id must be str"):
            _make_scenario(scenario_id=1)

    def test_invalid_scenario_id_format(self) -> None:
        with pytest.raises(ValueError, match="Invalid scenario_id"):
            _make_scenario(scenario_id="SCENARIO-001")

    def test_scenario_id_too_many_digits(self) -> None:
        with pytest.raises(ValueError, match="Invalid scenario_id"):
            _make_scenario(scenario_id="SC-1234")

    def test_category_must_be_str(self) -> None:
        with pytest.raises(TypeError, match="category must be str"):
            _make_scenario(category=123)

    def test_invalid_category(self) -> None:
        with pytest.raises(ValueError, match="Invalid category"):
            _make_scenario(category="bogus_category")

    def test_all_valid_categories(self) -> None:
        routing_categories = VALID_CATEGORIES - {"query"}
        for category in routing_categories:
            scenario = _make_scenario(category=category)
            assert scenario.category == category

    def test_query_category_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid category"):
            _make_scenario(category="query")

    def test_description_must_be_str(self) -> None:
        with pytest.raises(TypeError, match="description must be str"):
            _make_scenario(description=42)

    def test_steps_must_be_tuple(self) -> None:
        with pytest.raises(TypeError, match="steps must be tuple"):
            _make_scenario(steps=[_make_scenario_step()])

    def test_steps_must_not_be_empty(self) -> None:
        with pytest.raises(ValueError, match="steps must not be empty"):
            _make_scenario(steps=())

    def test_steps_elements_must_be_scenario_step(self) -> None:
        with pytest.raises(TypeError, match=r"steps\[0\] must be ScenarioStep"):
            _make_scenario(steps=({"step": 1},))

    def test_steps_must_be_sequential(self) -> None:
        step1 = _make_scenario_step(step=1)
        step3 = _make_scenario_step(step=3, event_type="grossing_complete")
        with pytest.raises(ValueError, match="Steps must be sequential"):
            _make_scenario(steps=(step1, step3))

    def test_first_step_must_be_order_received(self) -> None:
        step = _make_scenario_step(step=1, event_type="grossing_complete")
        with pytest.raises(ValueError, match="First step must be 'order_received'"):
            _make_scenario(steps=(step,))

    def test_multi_step_scenario(self) -> None:
        step1 = _make_scenario_step(step=1, event_type="order_received")
        step2 = _make_scenario_step(
            step=2,
            event_type="grossing_complete",
            event_data={"outcome": "success"},
            expected_output=_make_expected_output(
                next_state="SAMPLE_PREP_PROCESSING",
                applied_rules=("SP-001",),
            ),
        )
        scenario = _make_scenario(steps=(step1, step2))
        assert len(scenario.steps) == 2
        assert scenario.steps[1].event_type == "grossing_complete"


# --- TestLoadScenario ---


class TestLoadScenario:
    def test_load_valid_scenario(self, tmp_path: Path) -> None:
        path = tmp_path / "sc001.json"
        _write_scenario_json(path, _valid_scenario_dict())
        scenario = load_scenario(path)
        assert scenario.scenario_id == "SC-001"
        assert scenario.category == "rule_coverage"
        assert len(scenario.steps) == 1
        assert scenario.steps[0].event_type == "order_received"

    def test_file_not_found(self, tmp_path: Path) -> None:
        path = tmp_path / "nonexistent.json"
        with pytest.raises(FileNotFoundError, match="Scenario file not found"):
            load_scenario(path)

    def test_invalid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text("{invalid json", encoding="utf-8")
        with pytest.raises(ValueError, match="Invalid JSON"):
            load_scenario(path)

    def test_non_object_root(self, tmp_path: Path) -> None:
        path = tmp_path / "array.json"
        path.write_text("[1, 2, 3]", encoding="utf-8")
        with pytest.raises(ValueError, match="must be a JSON object"):
            load_scenario(path)

    def test_lists_converted_to_tuples(self, tmp_path: Path) -> None:
        path = tmp_path / "sc001.json"
        _write_scenario_json(path, _valid_scenario_dict())
        scenario = load_scenario(path)
        assert isinstance(scenario.steps, tuple)
        assert isinstance(scenario.steps[0].expected_output.applied_rules, tuple)
        assert isinstance(scenario.steps[0].expected_output.flags, tuple)

    def test_events_key_maps_to_steps(self, tmp_path: Path) -> None:
        path = tmp_path / "sc001.json"
        _write_scenario_json(path, _valid_scenario_dict())
        scenario = load_scenario(path)
        assert hasattr(scenario, "steps")
        assert len(scenario.steps) == 1

    def test_multi_step_load(self, tmp_path: Path) -> None:
        data = _valid_scenario_dict(
            events=[
                {
                    "step": 1,
                    "event_type": "order_received",
                    "event_data": {"patient_name": "TESTPATIENT-0001, Jane"},
                    "expected_output": {
                        "next_state": "ACCEPTED",
                        "applied_rules": ["ACC-008"],
                        "flags": [],
                    },
                },
                {
                    "step": 2,
                    "event_type": "grossing_complete",
                    "event_data": {"outcome": "success"},
                    "expected_output": {
                        "next_state": "SAMPLE_PREP_PROCESSING",
                        "applied_rules": ["SP-001"],
                        "flags": [],
                    },
                },
            ]
        )
        path = tmp_path / "sc001.json"
        _write_scenario_json(path, data)
        scenario = load_scenario(path)
        assert len(scenario.steps) == 2
        assert scenario.steps[1].step == 2

    def test_load_empty_events(self, tmp_path: Path) -> None:
        data = _valid_scenario_dict(events=[])
        path = tmp_path / "empty.json"
        _write_scenario_json(path, data)
        with pytest.raises(ValueError, match="steps must not be empty"):
            load_scenario(path)

    def test_load_non_dict_event_data(self, tmp_path: Path) -> None:
        data = _valid_scenario_dict()
        data["events"][0]["event_data"] = "not a dict"
        path = tmp_path / "bad.json"
        _write_scenario_json(path, data)
        with pytest.raises(TypeError, match="event_data must be dict"):
            load_scenario(path)

    def test_load_missing_scenario_id(self, tmp_path: Path) -> None:
        data = _valid_scenario_dict()
        del data["scenario_id"]
        path = tmp_path / "missing.json"
        _write_scenario_json(path, data)
        with pytest.raises(ValueError, match="missing required keys.*scenario_id"):
            load_scenario(path)

    def test_load_missing_event_keys(self, tmp_path: Path) -> None:
        data = _valid_scenario_dict()
        del data["events"][0]["event_type"]
        path = tmp_path / "missing_event_key.json"
        _write_scenario_json(path, data)
        with pytest.raises(ValueError, match="missing required keys.*event_type"):
            load_scenario(path)

    def test_load_applied_rules_string_not_list(self, tmp_path: Path) -> None:
        data = _valid_scenario_dict()
        data["events"][0]["expected_output"]["applied_rules"] = "ACC-008"
        path = tmp_path / "string_rules.json"
        _write_scenario_json(path, data)
        with pytest.raises(ValueError, match="applied_rules must be a list"):
            load_scenario(path)

    def test_load_flags_string_not_list(self, tmp_path: Path) -> None:
        data = _valid_scenario_dict()
        data["events"][0]["expected_output"]["flags"] = "FISH_SUGGESTED"
        path = tmp_path / "string_flags.json"
        _write_scenario_json(path, data)
        with pytest.raises(ValueError, match="flags must be a list"):
            load_scenario(path)


# --- TestLoadAllScenarios ---


class TestLoadAllScenarios:
    def test_load_multiple_files(self, tmp_path: Path) -> None:
        _write_scenario_json(
            tmp_path / "sc001.json",
            _valid_scenario_dict(scenario_id="SC-001"),
        )
        _write_scenario_json(
            tmp_path / "sc002.json",
            _valid_scenario_dict(scenario_id="SC-002"),
        )
        scenarios = load_all_scenarios(tmp_path)
        assert len(scenarios) == 2
        assert scenarios[0].scenario_id == "SC-001"
        assert scenarios[1].scenario_id == "SC-002"

    def test_sorted_by_scenario_id(self, tmp_path: Path) -> None:
        _write_scenario_json(
            tmp_path / "b.json",
            _valid_scenario_dict(scenario_id="SC-003"),
        )
        _write_scenario_json(
            tmp_path / "a.json",
            _valid_scenario_dict(scenario_id="SC-001"),
        )
        scenarios = load_all_scenarios(tmp_path)
        assert scenarios[0].scenario_id == "SC-001"
        assert scenarios[1].scenario_id == "SC-003"

    def test_recursive_loading(self, tmp_path: Path) -> None:
        subdir = tmp_path / "sub"
        subdir.mkdir()
        _write_scenario_json(
            tmp_path / "sc001.json",
            _valid_scenario_dict(scenario_id="SC-001"),
        )
        _write_scenario_json(
            subdir / "sc002.json",
            _valid_scenario_dict(scenario_id="SC-002"),
        )
        scenarios = load_all_scenarios(tmp_path)
        assert len(scenarios) == 2

    def test_empty_directory(self, tmp_path: Path) -> None:
        scenarios = load_all_scenarios(tmp_path)
        assert scenarios == []

    def test_directory_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="Scenario directory not found"):
            load_all_scenarios(tmp_path / "nonexistent")

    def test_invalid_file_in_directory(self, tmp_path: Path) -> None:
        _write_scenario_json(
            tmp_path / "valid.json",
            _valid_scenario_dict(scenario_id="SC-001"),
        )
        (tmp_path / "invalid.json").write_text("{bad json", encoding="utf-8")
        with pytest.raises(ValueError, match="Invalid JSON"):
            load_all_scenarios(tmp_path)


# --- TestLoadScenariosByCategory ---


class TestLoadScenariosByCategory:
    def test_load_category(self, tmp_path: Path) -> None:
        cat_dir = tmp_path / "rule_coverage"
        cat_dir.mkdir()
        _write_scenario_json(
            cat_dir / "sc001.json",
            _valid_scenario_dict(scenario_id="SC-001", category="rule_coverage"),
        )
        scenarios = load_scenarios_by_category(tmp_path, "rule_coverage")
        assert len(scenarios) == 1
        assert scenarios[0].category == "rule_coverage"

    def test_invalid_category(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Invalid category"):
            load_scenarios_by_category(tmp_path, "bogus")

    def test_category_directory_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="Category directory not found"):
            load_scenarios_by_category(tmp_path, "rule_coverage")

    def test_category_mismatch(self, tmp_path: Path) -> None:
        cat_dir = tmp_path / "rule_coverage"
        cat_dir.mkdir()
        _write_scenario_json(
            cat_dir / "sc001.json",
            _valid_scenario_dict(scenario_id="SC-001", category="multi_rule"),
        )
        with pytest.raises(ValueError, match="has category 'multi_rule'"):
            load_scenarios_by_category(tmp_path, "rule_coverage")

    def test_empty_category_directory(self, tmp_path: Path) -> None:
        cat_dir = tmp_path / "rule_coverage"
        cat_dir.mkdir()
        scenarios = load_scenarios_by_category(tmp_path, "rule_coverage")
        assert scenarios == []


# --- Query scenario factory helpers ---


def _make_database_state(**overrides: Any) -> DatabaseStateSnapshot:
    defaults: dict[str, Any] = {
        "orders": (
            {
                "order_id": "ORD-001",
                "current_state": "ACCEPTED",
                "specimen_type": "biopsy",
                "anatomic_site": "breast",
                "priority": "routine",
                "flags": [],
                "created_at": "2025-01-15T08:00:00Z",
            },
        ),
        "slides": (),
    }
    defaults.update(overrides)
    return DatabaseStateSnapshot(**defaults)


def _make_query_expected_output(**overrides: Any) -> QueryExpectedOutput:
    defaults: dict[str, Any] = {
        "answer_type": "order_list",
        "reasoning": "Orders in ACCEPTED state are ready for grossing",
        "order_ids": ("ORD-001",),
    }
    defaults.update(overrides)
    return QueryExpectedOutput(**defaults)


def _make_query_scenario(**overrides: Any) -> QueryScenario:
    defaults: dict[str, Any] = {
        "scenario_id": "QR-001",
        "category": "query",
        "tier": 1,
        "description": "Simple worklist query — orders ready for grossing",
        "database_state": _make_database_state(),
        "query": "What orders are ready for grossing?",
        "expected_output": _make_query_expected_output(),
    }
    defaults.update(overrides)
    return QueryScenario(**defaults)


def _valid_query_scenario_dict(**overrides: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "scenario_id": "QR-001",
        "category": "query",
        "tier": 1,
        "description": "Simple worklist query — orders ready for grossing",
        "database_state": {
            "orders": [
                {
                    "order_id": "ORD-001",
                    "current_state": "ACCEPTED",
                    "specimen_type": "biopsy",
                    "anatomic_site": "breast",
                    "priority": "routine",
                    "flags": [],
                    "created_at": "2025-01-15T08:00:00Z",
                },
            ],
            "slides": [],
        },
        "query": "What orders are ready for grossing?",
        "expected_output": {
            "answer_type": "order_list",
            "order_ids": ["ORD-001"],
            "reasoning": "Orders in ACCEPTED state are ready for grossing",
        },
    }
    defaults.update(overrides)
    return defaults


# --- TestDatabaseStateSnapshot ---


class TestDatabaseStateSnapshot:
    def test_valid_construction(self) -> None:
        db = _make_database_state()
        assert len(db.orders) == 1
        assert db.orders[0]["order_id"] == "ORD-001"
        assert db.slides == ()

    def test_frozen(self) -> None:
        db = _make_database_state()
        with pytest.raises(AttributeError):
            db.orders = ()  # type: ignore[misc]

    def test_orders_must_be_tuple(self) -> None:
        with pytest.raises(TypeError, match="orders must be tuple"):
            _make_database_state(orders=[{"order_id": "ORD-001"}])

    def test_orders_must_not_be_empty(self) -> None:
        with pytest.raises(ValueError, match="orders must not be empty"):
            _make_database_state(orders=())

    def test_orders_elements_must_be_dict(self) -> None:
        with pytest.raises(TypeError, match=r"orders\[0\] must be dict"):
            _make_database_state(orders=("not a dict",))

    def test_slides_must_be_tuple(self) -> None:
        with pytest.raises(TypeError, match="slides must be tuple"):
            _make_database_state(slides=[])

    def test_slides_elements_must_be_dict(self) -> None:
        with pytest.raises(TypeError, match=r"slides\[0\] must be dict"):
            _make_database_state(slides=("not a dict",))

    def test_slides_can_be_empty(self) -> None:
        db = _make_database_state(slides=())
        assert db.slides == ()

    def test_multiple_orders(self) -> None:
        db = _make_database_state(
            orders=(
                {
                    "order_id": "ORD-001",
                    "current_state": "ACCEPTED",
                    "specimen_type": "biopsy",
                    "anatomic_site": "breast",
                    "priority": "routine",
                },
                {
                    "order_id": "ORD-002",
                    "current_state": "ACCESSIONING",
                    "specimen_type": "excision",
                    "anatomic_site": "breast",
                    "priority": "rush",
                },
            )
        )
        assert len(db.orders) == 2

    def test_order_missing_required_fields(self) -> None:
        with pytest.raises(ValueError, match=r"orders\[0\] missing required fields"):
            _make_database_state(orders=({"order_id": "ORD-001"},))


# --- TestQueryExpectedOutput ---


class TestQueryExpectedOutput:
    def test_valid_construction(self) -> None:
        eo = _make_query_expected_output()
        assert eo.answer_type == "order_list"
        assert eo.order_ids == ("ORD-001",)
        assert eo.reasoning == "Orders in ACCEPTED state are ready for grossing"

    def test_frozen(self) -> None:
        eo = _make_query_expected_output()
        with pytest.raises(AttributeError):
            eo.answer_type = "explanation"  # type: ignore[misc]

    def test_answer_type_must_be_str(self) -> None:
        with pytest.raises(TypeError, match="answer_type must be str"):
            _make_query_expected_output(answer_type=123)

    def test_invalid_answer_type(self) -> None:
        with pytest.raises(ValueError, match="Invalid answer_type"):
            _make_query_expected_output(answer_type="bogus")

    def test_all_valid_answer_types(self) -> None:
        for at in VALID_ANSWER_TYPES:
            eo = _make_query_expected_output(answer_type=at)
            assert eo.answer_type == at

    def test_reasoning_must_be_str(self) -> None:
        with pytest.raises(TypeError, match="reasoning must be str"):
            _make_query_expected_output(reasoning=42)

    def test_reasoning_must_not_be_empty(self) -> None:
        with pytest.raises(ValueError, match="reasoning must not be empty"):
            _make_query_expected_output(reasoning="")

    def test_order_ids_must_be_tuple(self) -> None:
        with pytest.raises(TypeError, match="order_ids must be tuple"):
            _make_query_expected_output(order_ids=["ORD-001"])

    def test_order_ids_elements_must_be_str(self) -> None:
        with pytest.raises(TypeError, match=r"order_ids\[0\] must be str"):
            _make_query_expected_output(order_ids=(123,))

    def test_order_ids_defaults_to_empty(self) -> None:
        eo = QueryExpectedOutput(
            answer_type="explanation",
            reasoning="Some reasoning",
        )
        assert eo.order_ids == ()

    def test_order_list_requires_order_ids(self) -> None:
        with pytest.raises(ValueError, match="requires at least one order_id"):
            _make_query_expected_output(answer_type="order_list", order_ids=())

    def test_order_status_requires_order_ids(self) -> None:
        with pytest.raises(ValueError, match="requires at least one order_id"):
            _make_query_expected_output(answer_type="order_status", order_ids=())

    def test_prioritized_list_requires_order_ids(self) -> None:
        with pytest.raises(ValueError, match="requires at least one order_id"):
            _make_query_expected_output(answer_type="prioritized_list", order_ids=())

    def test_explanation_allows_empty_order_ids(self) -> None:
        eo = _make_query_expected_output(answer_type="explanation", order_ids=())
        assert eo.order_ids == ()


# --- TestQueryScenario ---


class TestQueryScenario:
    def test_valid_construction(self) -> None:
        qs = _make_query_scenario()
        assert qs.scenario_id == "QR-001"
        assert qs.category == "query"
        assert qs.tier == 1
        assert qs.query == "What orders are ready for grossing?"
        assert isinstance(qs.database_state, DatabaseStateSnapshot)
        assert isinstance(qs.expected_output, QueryExpectedOutput)

    def test_frozen(self) -> None:
        qs = _make_query_scenario()
        with pytest.raises(AttributeError):
            qs.scenario_id = "QR-999"  # type: ignore[misc]

    def test_scenario_id_must_be_str(self) -> None:
        with pytest.raises(TypeError, match="scenario_id must be str"):
            _make_query_scenario(scenario_id=1)

    def test_invalid_scenario_id_format(self) -> None:
        with pytest.raises(ValueError, match="Invalid scenario_id"):
            _make_query_scenario(scenario_id="QUERY-001")

    def test_qr_prefix_accepted(self) -> None:
        qs = _make_query_scenario(scenario_id="QR-001")
        assert qs.scenario_id == "QR-001"

    def test_category_must_be_query(self) -> None:
        with pytest.raises(ValueError, match="category must be 'query'"):
            _make_query_scenario(category="rule_coverage")

    def test_tier_must_be_int(self) -> None:
        with pytest.raises(TypeError, match="tier must be int"):
            _make_query_scenario(tier="1")

    def test_tier_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="tier must be 1-5"):
            _make_query_scenario(tier=0)

    def test_tier_rejects_bool(self) -> None:
        with pytest.raises(TypeError, match="tier must be int"):
            _make_query_scenario(tier=True)

    def test_description_must_be_str(self) -> None:
        with pytest.raises(TypeError, match="description must be str"):
            _make_query_scenario(description=42)

    def test_description_must_not_be_empty(self) -> None:
        with pytest.raises(ValueError, match="description must not be empty"):
            _make_query_scenario(description="")

    def test_database_state_must_be_snapshot(self) -> None:
        with pytest.raises(TypeError, match="database_state must be DatabaseStateSnapshot"):
            _make_query_scenario(database_state={"orders": []})

    def test_query_must_be_str(self) -> None:
        with pytest.raises(TypeError, match="query must be str"):
            _make_query_scenario(query=42)

    def test_query_must_not_be_empty(self) -> None:
        with pytest.raises(ValueError, match="query must not be empty"):
            _make_query_scenario(query="")

    def test_expected_output_must_be_query_expected_output(self) -> None:
        with pytest.raises(TypeError, match="expected_output must be QueryExpectedOutput"):
            _make_query_scenario(expected_output={"answer_type": "order_list"})

    def test_query_category_in_valid_categories(self) -> None:
        assert "query" in VALID_CATEGORIES


# --- TestLoadQueryScenario ---


class TestLoadQueryScenario:
    def test_load_valid_query_scenario(self, tmp_path: Path) -> None:
        path = tmp_path / "qr001.json"
        _write_scenario_json(path, _valid_query_scenario_dict())
        qs = load_query_scenario(path)
        assert qs.scenario_id == "QR-001"
        assert qs.category == "query"
        assert qs.tier == 1
        assert qs.query == "What orders are ready for grossing?"
        assert len(qs.database_state.orders) == 1
        assert qs.expected_output.answer_type == "order_list"

    def test_file_not_found(self, tmp_path: Path) -> None:
        path = tmp_path / "nonexistent.json"
        with pytest.raises(FileNotFoundError, match="Scenario file not found"):
            load_query_scenario(path)

    def test_invalid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text("{invalid json", encoding="utf-8")
        with pytest.raises(ValueError, match="Invalid JSON"):
            load_query_scenario(path)

    def test_non_object_root(self, tmp_path: Path) -> None:
        path = tmp_path / "array.json"
        path.write_text("[1, 2, 3]", encoding="utf-8")
        with pytest.raises(ValueError, match="must be a JSON object"):
            load_query_scenario(path)

    def test_missing_required_keys(self, tmp_path: Path) -> None:
        data = _valid_query_scenario_dict()
        del data["query"]
        path = tmp_path / "missing.json"
        _write_scenario_json(path, data)
        with pytest.raises(ValueError, match="missing required keys.*query"):
            load_query_scenario(path)

    def test_lists_converted_to_tuples(self, tmp_path: Path) -> None:
        path = tmp_path / "qr001.json"
        _write_scenario_json(path, _valid_query_scenario_dict())
        qs = load_query_scenario(path)
        assert isinstance(qs.database_state.orders, tuple)
        assert isinstance(qs.database_state.slides, tuple)
        assert isinstance(qs.expected_output.order_ids, tuple)

    def test_slides_defaults_to_empty(self, tmp_path: Path) -> None:
        data = _valid_query_scenario_dict()
        del data["database_state"]["slides"]
        path = tmp_path / "no_slides.json"
        _write_scenario_json(path, data)
        qs = load_query_scenario(path)
        assert qs.database_state.slides == ()

    def test_order_ids_optional(self, tmp_path: Path) -> None:
        data = _valid_query_scenario_dict()
        data["expected_output"]["answer_type"] = "explanation"
        del data["expected_output"]["order_ids"]
        path = tmp_path / "no_ids.json"
        _write_scenario_json(path, data)
        qs = load_query_scenario(path)
        assert qs.expected_output.order_ids == ()

    def test_database_state_must_be_dict(self, tmp_path: Path) -> None:
        data = _valid_query_scenario_dict()
        data["database_state"] = "not a dict"
        path = tmp_path / "bad_db.json"
        _write_scenario_json(path, data)
        with pytest.raises(ValueError, match="database_state.*must be a dict"):
            load_query_scenario(path)

    def test_orders_must_be_list(self, tmp_path: Path) -> None:
        data = _valid_query_scenario_dict()
        data["database_state"]["orders"] = "not a list"
        path = tmp_path / "bad_orders.json"
        _write_scenario_json(path, data)
        with pytest.raises(ValueError, match="database_state.orders.*must be a list"):
            load_query_scenario(path)

    def test_expected_output_must_be_dict(self, tmp_path: Path) -> None:
        data = _valid_query_scenario_dict()
        data["expected_output"] = "not a dict"
        path = tmp_path / "bad_expected.json"
        _write_scenario_json(path, data)
        with pytest.raises(ValueError, match="expected_output.*must be a dict"):
            load_query_scenario(path)

    def test_order_ids_must_be_list(self, tmp_path: Path) -> None:
        data = _valid_query_scenario_dict()
        data["expected_output"]["order_ids"] = "ORD-001"
        path = tmp_path / "bad_ids.json"
        _write_scenario_json(path, data)
        with pytest.raises(ValueError, match="order_ids must be a list"):
            load_query_scenario(path)

    def test_round_trip(self, tmp_path: Path) -> None:
        original = _valid_query_scenario_dict()
        path = tmp_path / "qr001.json"
        _write_scenario_json(path, original)
        qs = load_query_scenario(path)
        assert qs.scenario_id == original["scenario_id"]
        assert qs.tier == original["tier"]
        assert qs.query == original["query"]
        assert qs.expected_output.answer_type == original["expected_output"]["answer_type"]
        assert list(qs.expected_output.order_ids) == original["expected_output"]["order_ids"]
        assert len(qs.database_state.orders) == len(original["database_state"]["orders"])


# --- TestLoadAllQueryScenarios ---


class TestLoadAllQueryScenarios:
    def test_load_multiple_files(self, tmp_path: Path) -> None:
        _write_scenario_json(
            tmp_path / "qr001.json",
            _valid_query_scenario_dict(scenario_id="QR-001"),
        )
        _write_scenario_json(
            tmp_path / "qr002.json",
            _valid_query_scenario_dict(scenario_id="QR-002"),
        )
        scenarios = load_all_query_scenarios(tmp_path)
        assert len(scenarios) == 2
        assert scenarios[0].scenario_id == "QR-001"
        assert scenarios[1].scenario_id == "QR-002"

    def test_sorted_by_scenario_id(self, tmp_path: Path) -> None:
        _write_scenario_json(
            tmp_path / "b.json",
            _valid_query_scenario_dict(scenario_id="QR-003"),
        )
        _write_scenario_json(
            tmp_path / "a.json",
            _valid_query_scenario_dict(scenario_id="QR-001"),
        )
        scenarios = load_all_query_scenarios(tmp_path)
        assert scenarios[0].scenario_id == "QR-001"
        assert scenarios[1].scenario_id == "QR-003"

    def test_recursive_loading(self, tmp_path: Path) -> None:
        subdir = tmp_path / "tier1"
        subdir.mkdir()
        _write_scenario_json(
            subdir / "qr001.json",
            _valid_query_scenario_dict(scenario_id="QR-001"),
        )
        scenarios = load_all_query_scenarios(tmp_path)
        assert len(scenarios) == 1
        assert scenarios[0].scenario_id == "QR-001"

    def test_empty_directory(self, tmp_path: Path) -> None:
        scenarios = load_all_query_scenarios(tmp_path)
        assert scenarios == []

    def test_directory_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="Scenario directory not found"):
            load_all_query_scenarios(tmp_path / "nonexistent")


# --- TestLoadQueryScenariosByTier ---


class TestLoadQueryScenariosByTier:
    def test_filter_by_tier(self, tmp_path: Path) -> None:
        _write_scenario_json(
            tmp_path / "qr001.json",
            _valid_query_scenario_dict(scenario_id="QR-001", tier=1),
        )
        _write_scenario_json(
            tmp_path / "qr002.json",
            _valid_query_scenario_dict(scenario_id="QR-002", tier=2),
        )
        tier1 = load_query_scenarios_by_tier(tmp_path, 1)
        assert len(tier1) == 1
        assert tier1[0].scenario_id == "QR-001"

    def test_invalid_tier(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="tier must be a positive integer"):
            load_query_scenarios_by_tier(tmp_path, 0)

    def test_tier_rejects_bool(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="tier must be a positive integer"):
            load_query_scenarios_by_tier(tmp_path, True)

    def test_no_matching_tier(self, tmp_path: Path) -> None:
        _write_scenario_json(
            tmp_path / "qr001.json",
            _valid_query_scenario_dict(scenario_id="QR-001", tier=1),
        )
        tier5 = load_query_scenarios_by_tier(tmp_path, 5)
        assert tier5 == []
