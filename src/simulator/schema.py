"""Scenario data model for test scenario definitions.

Defines frozen dataclasses for scenario structure: ExpectedOutput,
ScenarioStep, and Scenario. All fields are validated in __post_init__
following the pattern from src/workflow/models.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from src.workflow.models import VALID_FLAGS, VALID_STATES

# Valid event types — all events that can occur in the workflow.
VALID_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "order_received",
        "grossing_complete",
        "processing_complete",
        "embedding_complete",
        "sectioning_complete",
        "sample_prep_qc",
        "he_staining_complete",
        "he_qc",
        "pathologist_he_review",
        "ihc_staining_complete",
        "ihc_qc",
        "ihc_scoring",
        "fish_decision",
        "fish_result",
        "missing_info_received",
        "resulting_review",
        "pathologist_signout",
        "report_generated",
    }
)

# Valid scenario categories (see docs/scenarios/scenario-design.md).
VALID_CATEGORIES: frozenset[str] = frozenset(
    {
        "rule_coverage",
        "multi_rule",
        "accumulated_state",
        "unknown_input",
        "hallucination",
        "query",
    }
)

# Scenario ID format: SC-NNN or PT-NNN for routing, QR-NNN for query.
_ROUTING_ID_PATTERN = re.compile(r"^(SC|PT)-\d{3}$")
_QUERY_ID_PATTERN = re.compile(r"^QR-\d{3}$")

# Rule ID format: PREFIX-NNN (ACC, SP, HE, IHC, RES)
_RULE_ID_PATTERN = re.compile(r"^(ACC|SP|HE|IHC|RES)-\d{3}$")

# Routing categories exclude "query" (used in Scenario validation).
_ROUTING_CATEGORIES: frozenset[str] = VALID_CATEGORIES - {"query"}

# Required order fields in a DatabaseStateSnapshot.
_REQUIRED_ORDER_FIELDS: frozenset[str] = frozenset(
    {"order_id", "current_state", "specimen_type", "anatomic_site", "priority"}
)

# Answer types that require at least one order_id in QueryExpectedOutput.
_ORDER_ANSWER_TYPES: frozenset[str] = frozenset({"order_list", "order_status", "prioritized_list"})


@dataclass(frozen=True)
class ExpectedOutput:
    """Ground-truth expected output for a scenario step."""

    next_state: str
    applied_rules: tuple[str, ...]
    flags: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.next_state, str):
            raise TypeError(f"next_state must be str, got {type(self.next_state).__name__}")
        if not isinstance(self.applied_rules, tuple):
            raise TypeError(f"applied_rules must be tuple, got {type(self.applied_rules).__name__}")
        for i, rule in enumerate(self.applied_rules):
            if not isinstance(rule, str):
                raise TypeError(f"applied_rules[{i}] must be str, got {type(rule).__name__}")
        if not isinstance(self.flags, tuple):
            raise TypeError(f"flags must be tuple, got {type(self.flags).__name__}")
        for i, flag in enumerate(self.flags):
            if not isinstance(flag, str):
                raise TypeError(f"flags[{i}] must be str, got {type(flag).__name__}")
        # Semantic validation against canonical constants.
        if self.next_state not in VALID_STATES:
            raise ValueError(
                f"Invalid next_state '{self.next_state}'. Must be one of: {sorted(VALID_STATES)}"
            )
        for i, rule in enumerate(self.applied_rules):
            if not _RULE_ID_PATTERN.match(rule):
                raise ValueError(
                    f"Invalid applied_rules[{i}] '{rule}'. "
                    f"Must match PREFIX-NNN (ACC, SP, HE, IHC, RES)."
                )
        for i, flag in enumerate(self.flags):
            if flag not in VALID_FLAGS:
                raise ValueError(
                    f"Invalid flags[{i}] '{flag}'. Must be one of: {sorted(VALID_FLAGS)}"
                )


@dataclass(frozen=True)
class ScenarioStep:
    """A single step in a test scenario."""

    step: int
    event_type: str
    event_data: dict[str, Any]
    expected_output: ExpectedOutput

    def __post_init__(self) -> None:
        if not isinstance(self.step, int):
            raise TypeError(f"step must be int, got {type(self.step).__name__}")
        if self.step < 1:
            raise ValueError(f"step must be >= 1, got {self.step}")
        if not isinstance(self.event_type, str):
            raise TypeError(f"event_type must be str, got {type(self.event_type).__name__}")
        if self.event_type not in VALID_EVENT_TYPES:
            raise ValueError(
                f"Invalid event_type '{self.event_type}'. "
                f"Must be one of: {sorted(VALID_EVENT_TYPES)}"
            )
        if not isinstance(self.event_data, dict):
            raise TypeError(f"event_data must be dict, got {type(self.event_data).__name__}")
        if not isinstance(self.expected_output, ExpectedOutput):
            raise TypeError(
                f"expected_output must be ExpectedOutput, got {type(self.expected_output).__name__}"
            )


@dataclass(frozen=True)
class Scenario:
    """A complete test scenario with metadata and steps."""

    scenario_id: str
    category: str
    description: str
    steps: tuple[ScenarioStep, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.scenario_id, str):
            raise TypeError(f"scenario_id must be str, got {type(self.scenario_id).__name__}")
        if not _ROUTING_ID_PATTERN.match(self.scenario_id):
            raise ValueError(
                f"Invalid scenario_id '{self.scenario_id}'. Must match SC-NNN or PT-NNN."
            )
        if not isinstance(self.category, str):
            raise TypeError(f"category must be str, got {type(self.category).__name__}")
        if self.category not in _ROUTING_CATEGORIES:
            raise ValueError(
                f"Invalid category '{self.category}'. Must be one of: {sorted(_ROUTING_CATEGORIES)}"
            )
        if not isinstance(self.description, str):
            raise TypeError(f"description must be str, got {type(self.description).__name__}")
        if not isinstance(self.steps, tuple):
            raise TypeError(f"steps must be tuple, got {type(self.steps).__name__}")
        if not self.steps:
            raise ValueError("steps must not be empty")
        for i, step in enumerate(self.steps):
            if not isinstance(step, ScenarioStep):
                raise TypeError(f"steps[{i}] must be ScenarioStep, got {type(step).__name__}")
        # Steps must be sequential starting from 1.
        expected_steps = list(range(1, len(self.steps) + 1))
        actual_steps = [s.step for s in self.steps]
        if actual_steps != expected_steps:
            raise ValueError(f"Steps must be sequential starting from 1. Got: {actual_steps}")
        # First step must be order_received.
        if self.steps[0].event_type != "order_received":
            raise ValueError(
                f"First step must be 'order_received', got '{self.steps[0].event_type}'"
            )


# --- Query scenario dataclasses ---

# Valid answer types for query expected output.
VALID_ANSWER_TYPES: frozenset[str] = frozenset(
    {
        "order_list",
        "order_status",
        "explanation",
        "prioritized_list",
    }
)


@dataclass(frozen=True)
class DatabaseStateSnapshot:
    """Point-in-time snapshot of database state for query scenarios."""

    orders: tuple[dict[str, Any], ...]
    slides: tuple[dict[str, Any], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.orders, tuple):
            raise TypeError(f"orders must be tuple, got {type(self.orders).__name__}")
        if not self.orders:
            raise ValueError("orders must not be empty")
        for i, order in enumerate(self.orders):
            if not isinstance(order, dict):
                raise TypeError(f"orders[{i}] must be dict, got {type(order).__name__}")
            missing_fields = _REQUIRED_ORDER_FIELDS - order.keys()
            if missing_fields:
                raise ValueError(f"orders[{i}] missing required fields: {sorted(missing_fields)}")
            state = order["current_state"]
            if state not in VALID_STATES:
                raise ValueError(
                    f"orders[{i}] invalid current_state '{state}'. "
                    f"Must be one of: {sorted(VALID_STATES)}"
                )
            flags = order.get("flags", [])
            if not isinstance(flags, list):
                raise TypeError(f"orders[{i}].flags must be list, got {type(flags).__name__}")
            for j, flag in enumerate(flags):
                if flag not in VALID_FLAGS:
                    raise ValueError(
                        f"orders[{i}].flags[{j}] invalid flag '{flag}'. "
                        f"Must be one of: {sorted(VALID_FLAGS)}"
                    )
        if not isinstance(self.slides, tuple):
            raise TypeError(f"slides must be tuple, got {type(self.slides).__name__}")
        for i, slide in enumerate(self.slides):
            if not isinstance(slide, dict):
                raise TypeError(f"slides[{i}] must be dict, got {type(slide).__name__}")


@dataclass(frozen=True)
class QueryExpectedOutput:
    """Ground-truth expected output for a query scenario."""

    answer_type: str
    reasoning: str
    order_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.answer_type, str):
            raise TypeError(f"answer_type must be str, got {type(self.answer_type).__name__}")
        if self.answer_type not in VALID_ANSWER_TYPES:
            raise ValueError(
                f"Invalid answer_type '{self.answer_type}'. "
                f"Must be one of: {sorted(VALID_ANSWER_TYPES)}"
            )
        if not isinstance(self.reasoning, str):
            raise TypeError(f"reasoning must be str, got {type(self.reasoning).__name__}")
        if not self.reasoning.strip():
            raise ValueError("reasoning must not be empty")
        if not isinstance(self.order_ids, tuple):
            raise TypeError(f"order_ids must be tuple, got {type(self.order_ids).__name__}")
        for i, oid in enumerate(self.order_ids):
            if not isinstance(oid, str):
                raise TypeError(f"order_ids[{i}] must be str, got {type(oid).__name__}")
        # Cross-field: answer types that return orders require at least one order_id.
        if self.answer_type in _ORDER_ANSWER_TYPES and not self.order_ids:
            raise ValueError(
                f"answer_type '{self.answer_type}' requires at least one order_id, "
                f"but order_ids is empty"
            )


@dataclass(frozen=True)
class QueryScenario:
    """A query test scenario with database state and expected answer."""

    scenario_id: str
    category: str
    tier: int
    description: str
    database_state: DatabaseStateSnapshot
    query: str
    expected_output: QueryExpectedOutput

    def __post_init__(self) -> None:
        if not isinstance(self.scenario_id, str):
            raise TypeError(f"scenario_id must be str, got {type(self.scenario_id).__name__}")
        if not _QUERY_ID_PATTERN.match(self.scenario_id):
            raise ValueError(f"Invalid scenario_id '{self.scenario_id}'. Must match QR-NNN.")
        if not isinstance(self.category, str):
            raise TypeError(f"category must be str, got {type(self.category).__name__}")
        if self.category != "query":
            raise ValueError(f"QueryScenario category must be 'query', got '{self.category}'")
        if isinstance(self.tier, bool) or not isinstance(self.tier, int):
            raise TypeError(f"tier must be int, got {type(self.tier).__name__}")
        if self.tier < 1 or self.tier > 5:
            raise ValueError(f"tier must be 1-5, got {self.tier}")
        if not isinstance(self.description, str):
            raise TypeError(f"description must be str, got {type(self.description).__name__}")
        if not self.description.strip():
            raise ValueError("description must not be empty")
        if not isinstance(self.database_state, DatabaseStateSnapshot):
            raise TypeError(
                f"database_state must be DatabaseStateSnapshot, "
                f"got {type(self.database_state).__name__}"
            )
        if not isinstance(self.query, str):
            raise TypeError(f"query must be str, got {type(self.query).__name__}")
        if not self.query.strip():
            raise ValueError("query must not be empty")
        if not isinstance(self.expected_output, QueryExpectedOutput):
            raise TypeError(
                f"expected_output must be QueryExpectedOutput, "
                f"got {type(self.expected_output).__name__}"
            )
