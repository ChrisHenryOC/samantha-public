"""Scenario file loader for JSON scenario definitions.

Reads scenario JSON files and constructs validated frozen dataclasses.
The JSON format uses "events" as the array key; the loader maps this
to the dataclass "steps" field.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.simulator.schema import (
    VALID_CATEGORIES,
    DatabaseStateSnapshot,
    ExpectedOutput,
    QueryExpectedOutput,
    QueryScenario,
    Scenario,
    ScenarioStep,
)

_REQUIRED_SCENARIO_KEYS: frozenset[str] = frozenset(
    {"scenario_id", "category", "description", "events"}
)
_REQUIRED_EVENT_KEYS: frozenset[str] = frozenset(
    {"step", "event_type", "event_data", "expected_output"}
)
_REQUIRED_EXPECTED_KEYS: frozenset[str] = frozenset({"next_state", "applied_rules", "flags"})

_REQUIRED_QUERY_KEYS: frozenset[str] = frozenset(
    {
        "scenario_id",
        "category",
        "tier",
        "description",
        "database_state",
        "query",
        "expected_output",
    }
)

_REQUIRED_QUERY_EXPECTED_KEYS: frozenset[str] = frozenset({"answer_type", "reasoning"})


def load_scenario(path: Path) -> Scenario:
    """Load a single scenario from a JSON file.

    Reads the JSON file at *path*, maps the ``"events"`` key to
    ``steps``, converts lists to tuples, and constructs validated
    dataclasses.

    Raises:
        FileNotFoundError: If *path* does not exist.
        ValueError: If the JSON is invalid or does not conform to the
            expected scenario structure.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise FileNotFoundError(f"Scenario file not found: {path}") from None

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from None

    if not isinstance(data, dict):
        raise ValueError(f"Scenario root must be a JSON object, got {type(data).__name__}")

    # Validate required top-level keys.
    missing = _REQUIRED_SCENARIO_KEYS - data.keys()
    if missing:
        raise ValueError(f"Scenario JSON missing required keys: {sorted(missing)}")

    events = data["events"]
    if not isinstance(events, list):
        raise ValueError(f"'events' must be a list, got {type(events).__name__}")

    steps_list: list[ScenarioStep] = []
    for i, event in enumerate(events):
        if not isinstance(event, dict):
            raise ValueError(f"events[{i}] must be a dict, got {type(event).__name__}")
        missing_event = _REQUIRED_EVENT_KEYS - event.keys()
        if missing_event:
            raise ValueError(f"events[{i}] missing required keys: {sorted(missing_event)}")

        expected = event["expected_output"]
        if not isinstance(expected, dict):
            raise ValueError(
                f"events[{i}].expected_output must be a dict, got {type(expected).__name__}"
            )
        missing_expected = _REQUIRED_EXPECTED_KEYS - expected.keys()
        if missing_expected:
            raise ValueError(
                f"events[{i}].expected_output missing required keys: {sorted(missing_expected)}"
            )

        # Validate list types before tuple conversion (CLAUDE.md type-safety).
        raw_rules = expected["applied_rules"]
        if not isinstance(raw_rules, list):
            raise ValueError(
                f"events[{i}].expected_output.applied_rules must be a list, "
                f"got {type(raw_rules).__name__}"
            )
        raw_flags = expected["flags"]
        if not isinstance(raw_flags, list):
            raise ValueError(
                f"events[{i}].expected_output.flags must be a list, got {type(raw_flags).__name__}"
            )

        expected_output = ExpectedOutput(
            next_state=expected["next_state"],
            applied_rules=tuple(raw_rules),
            flags=tuple(raw_flags),
        )
        step = ScenarioStep(
            step=event["step"],
            event_type=event["event_type"],
            event_data=event["event_data"],
            expected_output=expected_output,
        )
        steps_list.append(step)

    return Scenario(
        scenario_id=data["scenario_id"],
        category=data["category"],
        description=data["description"],
        steps=tuple(steps_list),
    )


def load_all_scenarios(directory: Path) -> list[Scenario]:
    """Load all scenario JSON files from a directory tree.

    Recursively finds ``*.json`` files under *directory* and returns
    a list of scenarios sorted by ``scenario_id``.

    Raises:
        FileNotFoundError: If *directory* does not exist.
    """
    if not directory.exists():
        raise FileNotFoundError(f"Scenario directory not found: {directory}")

    scenarios: list[Scenario] = []
    for json_path in directory.rglob("*.json"):
        try:
            scenarios.append(load_scenario(json_path))
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Failed to load {json_path}: {exc}") from exc

    scenarios.sort(key=lambda s: s.scenario_id)
    return scenarios


def load_scenarios_by_category(directory: Path, category: str) -> list[Scenario]:
    """Load scenarios from a category subdirectory.

    Expects scenarios to live in ``directory/category/*.json``. Validates
    that *category* is a known category and that all loaded scenarios
    match the requested category.

    Raises:
        ValueError: If *category* is not a valid category or if a loaded
            scenario has a mismatched category.
        FileNotFoundError: If *directory* or the category subdirectory
            does not exist.
    """
    if category not in VALID_CATEGORIES:
        raise ValueError(
            f"Invalid category '{category}'. Must be one of: {sorted(VALID_CATEGORIES)}"
        )

    category_dir = directory / category
    if not category_dir.exists():
        raise FileNotFoundError(f"Category directory not found: {category_dir}")

    scenarios = load_all_scenarios(category_dir)

    for scenario in scenarios:
        if scenario.category != category:
            raise ValueError(
                f"Scenario {scenario.scenario_id} has category "
                f"'{scenario.category}' but was loaded from "
                f"'{category}' directory"
            )

    return scenarios


# --- Query scenario loaders ---


def load_query_scenario(path: Path) -> QueryScenario:
    """Load a single query scenario from a JSON file.

    Reads the JSON file at *path*, validates required keys, converts
    lists to tuples, and constructs validated dataclasses.

    Raises:
        FileNotFoundError: If *path* does not exist.
        ValueError: If the JSON is invalid or does not conform to the
            expected query scenario structure.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise FileNotFoundError(f"Scenario file not found: {path}") from None

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from None

    if not isinstance(data, dict):
        raise ValueError(f"Scenario root must be a JSON object, got {type(data).__name__}")

    missing = _REQUIRED_QUERY_KEYS - data.keys()
    if missing:
        raise ValueError(f"Query scenario JSON missing required keys: {sorted(missing)}")

    # Parse database_state.
    db_state_raw = data["database_state"]
    if not isinstance(db_state_raw, dict):
        raise ValueError(f"'database_state' must be a dict, got {type(db_state_raw).__name__}")

    raw_orders = db_state_raw.get("orders")
    if not isinstance(raw_orders, list):
        raise ValueError(f"'database_state.orders' must be a list, got {type(raw_orders).__name__}")
    raw_slides = db_state_raw.get("slides")
    if raw_slides is None:
        raw_slides = []
    if not isinstance(raw_slides, list):
        raise ValueError(f"'database_state.slides' must be a list, got {type(raw_slides).__name__}")

    database_state = DatabaseStateSnapshot(
        orders=tuple(raw_orders),
        slides=tuple(raw_slides),
    )

    # Parse expected_output.
    expected_raw = data["expected_output"]
    if not isinstance(expected_raw, dict):
        raise ValueError(f"'expected_output' must be a dict, got {type(expected_raw).__name__}")

    missing_expected = _REQUIRED_QUERY_EXPECTED_KEYS - expected_raw.keys()
    if missing_expected:
        raise ValueError(f"expected_output missing required keys: {sorted(missing_expected)}")

    raw_order_ids = expected_raw.get("order_ids")
    if raw_order_ids is not None:
        if not isinstance(raw_order_ids, list):
            raise ValueError(
                f"expected_output.order_ids must be a list, got {type(raw_order_ids).__name__}"
            )
        order_ids = tuple(raw_order_ids)
    else:
        order_ids = ()

    expected_output = QueryExpectedOutput(
        answer_type=expected_raw["answer_type"],
        reasoning=expected_raw["reasoning"],
        order_ids=order_ids,
    )

    return QueryScenario(
        scenario_id=data["scenario_id"],
        category=data["category"],
        tier=data["tier"],
        description=data["description"],
        database_state=database_state,
        query=data["query"],
        expected_output=expected_output,
    )


def load_all_query_scenarios(directory: Path) -> list[QueryScenario]:
    """Load all query scenario JSON files from a directory tree.

    Recursively finds ``*.json`` files under *directory* and returns
    a list of query scenarios sorted by ``scenario_id``.

    Raises:
        FileNotFoundError: If *directory* does not exist.
    """
    if not directory.exists():
        raise FileNotFoundError(f"Scenario directory not found: {directory}")

    scenarios: list[QueryScenario] = []
    for json_path in directory.rglob("*.json"):
        try:
            scenarios.append(load_query_scenario(json_path))
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Failed to load {json_path}: {exc}") from exc

    scenarios.sort(key=lambda s: s.scenario_id)
    return scenarios


def load_query_scenarios_by_tier(directory: Path, tier: int) -> list[QueryScenario]:
    """Load query scenarios filtered by tier.

    Loads all query scenarios from *directory* and returns only those
    matching the requested *tier*.

    Raises:
        ValueError: If *tier* is less than 1.
        FileNotFoundError: If *directory* does not exist.
    """
    if isinstance(tier, bool) or not isinstance(tier, int) or tier < 1:
        raise ValueError(f"tier must be a positive integer, got {tier!r}")

    all_scenarios = load_all_query_scenarios(directory)
    return [s for s in all_scenarios if s.tier == tier]
