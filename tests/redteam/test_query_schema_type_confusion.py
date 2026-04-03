"""Red-team tests: type confusion and boundary values in query scenario schema.

Feeds wrong types into DatabaseStateSnapshot, QueryExpectedOutput, and
QueryScenario to verify that __post_init__ guards reject bad inputs rather
than silently corrupting data (e.g., set("ACC-001") character iteration).

Scope vs tests/test_scenario_schema.py
--------------------------------------
The main schema test file covers each guard once with a representative bad
input. This red-team file adds *additional* adversarial inputs that exercise
Python language quirks and subtle type-coercion bugs:

  - Wrong container types (dict where tuple expected, string where list expected)
  - Python bool-is-int subclass quirk (True/False as tier)
  - Float where int expected
  - Character-iteration hazards (string passed where sequence expected)
  - Boundary values (minimum/maximum valid, terminal states, extra fields)

Some guards are exercised in both files. The main test provides baseline
coverage; this file provides defense-in-depth for the same guards with
inputs chosen specifically to exploit Python's type system.
"""

from __future__ import annotations

import pytest

from src.simulator.schema import (
    DatabaseStateSnapshot,
    QueryExpectedOutput,
    QueryScenario,
)

# ---------------------------------------------------------------------------
# Helpers — minimal valid instances for composition
# ---------------------------------------------------------------------------


def _valid_order(**overrides: object) -> dict[str, object]:
    """Minimal order dict that passes DatabaseStateSnapshot validation."""
    base: dict[str, object] = {
        "order_id": "ORD-001",
        "current_state": "ACCEPTED",
        "specimen_type": "breast_core_biopsy",
        "anatomic_site": "left_breast",
        "priority": "routine",
    }
    base.update(overrides)
    return base


def _valid_db_state(**kwargs: object) -> DatabaseStateSnapshot:
    """Minimal valid DatabaseStateSnapshot."""
    return DatabaseStateSnapshot(
        orders=kwargs.get("orders", (_valid_order(),)),  # type: ignore[arg-type]
        slides=kwargs.get("slides", ()),  # type: ignore[arg-type]
    )


def _valid_expected_output(**kwargs: object) -> QueryExpectedOutput:
    """Minimal valid QueryExpectedOutput."""
    return QueryExpectedOutput(
        answer_type=kwargs.get("answer_type", "explanation"),  # type: ignore[arg-type]
        reasoning=kwargs.get("reasoning", "Because the order is routine."),  # type: ignore[arg-type]
        order_ids=kwargs.get("order_ids", ()),  # type: ignore[arg-type]
    )


def _valid_query_scenario(**kwargs: object) -> QueryScenario:
    """Minimal valid QueryScenario.

    kwargs may supply deliberately wrong types for type-confusion tests;
    the ``# type: ignore[arg-type]`` comments on each field are intentional.
    """
    return QueryScenario(
        scenario_id=kwargs.get("scenario_id", "QR-001"),  # type: ignore[arg-type]
        category=kwargs.get("category", "query"),  # type: ignore[arg-type]
        tier=kwargs.get("tier", 1),  # type: ignore[arg-type]
        description=kwargs.get("description", "Test query scenario."),  # type: ignore[arg-type]
        database_state=kwargs.get("database_state", _valid_db_state()),  # type: ignore[arg-type]
        query=kwargs.get("query", "Which orders are in ACCEPTED state?"),  # type: ignore[arg-type]
        expected_output=kwargs.get("expected_output", _valid_expected_output()),  # type: ignore[arg-type]
    )


# ===========================================================================
# DatabaseStateSnapshot — type confusion
# ===========================================================================


class TestDatabaseStateSnapshotTypeConfusion:
    """Feed wrong types into DatabaseStateSnapshot constructor."""

    def test_orders_as_string(self) -> None:
        """String orders would iterate characters — caught by type guard."""
        with pytest.raises(TypeError, match="orders must be tuple"):
            DatabaseStateSnapshot(orders="not-a-tuple", slides=())  # type: ignore[arg-type]

    def test_orders_as_none(self) -> None:
        """None orders — caught by type guard."""
        with pytest.raises(TypeError, match="orders must be tuple"):
            DatabaseStateSnapshot(orders=None, slides=())  # type: ignore[arg-type]

    def test_orders_as_dict(self) -> None:
        """Dict orders — wrong container type, caught by type guard."""
        with pytest.raises(TypeError, match="orders must be tuple"):
            DatabaseStateSnapshot(orders={"a": 1}, slides=())  # type: ignore[arg-type]

    def test_orders_containing_non_dict_entry(self) -> None:
        """Order entry that is a string, not a dict — caught by element guard."""
        with pytest.raises(TypeError, match=r"orders\[0\] must be dict"):
            DatabaseStateSnapshot(orders=("not-a-dict",), slides=())  # type: ignore[arg-type]

    def test_orders_containing_int_entry(self) -> None:
        """Order entry that is an int, not a dict."""
        with pytest.raises(TypeError, match=r"orders\[0\] must be dict"):
            DatabaseStateSnapshot(orders=(42,), slides=())  # type: ignore[arg-type]

    def test_orders_missing_required_fields(self) -> None:
        """Order dict missing required fields raises ValueError."""
        incomplete = {"order_id": "ORD-001"}
        with pytest.raises(ValueError, match="missing required fields"):
            DatabaseStateSnapshot(orders=(incomplete,), slides=())

    def test_orders_invalid_current_state(self) -> None:
        """Order with invalid current_state raises ValueError."""
        order = _valid_order(current_state="NONEXISTENT_STATE")
        with pytest.raises(ValueError, match="invalid current_state"):
            DatabaseStateSnapshot(orders=(order,), slides=())

    def test_orders_invalid_flag(self) -> None:
        """Order with invalid flag in flags list raises ValueError."""
        order = _valid_order(flags=["BOGUS_FLAG"])
        with pytest.raises(ValueError, match="invalid flag"):
            DatabaseStateSnapshot(orders=(order,), slides=())

    def test_order_flags_as_string(self) -> None:
        """String flags would iterate characters — caught by type guard.

        Bug: iterating "FIXATION_WARNING" yields 'F','I','X',... and the
        per-character check produces a misleading "invalid flag 'F'" error.
        The list type guard prevents this before any iteration occurs.
        """
        order = _valid_order(flags="FIXATION_WARNING")
        with pytest.raises(TypeError, match=r"orders\[0\]\.flags must be list"):
            DatabaseStateSnapshot(orders=(order,), slides=())

    def test_order_flags_as_none(self) -> None:
        """None flags — caught by type guard."""
        order = _valid_order(flags=None)
        with pytest.raises(TypeError, match=r"orders\[0\]\.flags must be list"):
            DatabaseStateSnapshot(orders=(order,), slides=())

    def test_slides_as_string(self) -> None:
        """String slides would iterate characters — caught by type guard."""
        with pytest.raises(TypeError, match="slides must be tuple"):
            DatabaseStateSnapshot(orders=(_valid_order(),), slides="not-a-tuple")  # type: ignore[arg-type]

    def test_slides_as_none(self) -> None:
        """None slides — caught by type guard."""
        with pytest.raises(TypeError, match="slides must be tuple"):
            DatabaseStateSnapshot(orders=(_valid_order(),), slides=None)  # type: ignore[arg-type]

    def test_slides_containing_non_dict_entry(self) -> None:
        """Slide entry that is a string, not a dict."""
        with pytest.raises(TypeError, match=r"slides\[0\] must be dict"):
            DatabaseStateSnapshot(
                orders=(_valid_order(),),
                slides=("not-a-dict",),  # type: ignore[arg-type]
            )

    def test_empty_orders(self) -> None:
        """Empty orders tuple raises ValueError (at least one order required)."""
        with pytest.raises(ValueError, match="orders must not be empty"):
            DatabaseStateSnapshot(orders=(), slides=())


# ===========================================================================
# QueryExpectedOutput — type confusion
# ===========================================================================


class TestQueryExpectedOutputTypeConfusion:
    """Feed wrong types into QueryExpectedOutput constructor."""

    def test_answer_type_as_int(self) -> None:
        """Integer answer_type — caught by type guard."""
        with pytest.raises(TypeError, match="answer_type must be str"):
            QueryExpectedOutput(answer_type=42, reasoning="test")  # type: ignore[arg-type]

    def test_answer_type_as_none(self) -> None:
        """None answer_type — caught by type guard."""
        with pytest.raises(TypeError, match="answer_type must be str"):
            QueryExpectedOutput(answer_type=None, reasoning="test")  # type: ignore[arg-type]

    def test_answer_type_as_list(self) -> None:
        """List answer_type — caught by type guard."""
        with pytest.raises(TypeError, match="answer_type must be str"):
            QueryExpectedOutput(answer_type=["explanation"], reasoning="test")  # type: ignore[arg-type]

    def test_answer_type_invalid_value(self) -> None:
        """String but not a valid answer_type — ValueError."""
        with pytest.raises(ValueError, match="Invalid answer_type"):
            QueryExpectedOutput(answer_type="invalid_type", reasoning="test")

    def test_reasoning_as_int(self) -> None:
        """Integer reasoning — caught by type guard."""
        with pytest.raises(TypeError, match="reasoning must be str"):
            QueryExpectedOutput(answer_type="explanation", reasoning=42)  # type: ignore[arg-type]

    def test_reasoning_as_none(self) -> None:
        """None reasoning — caught by type guard."""
        with pytest.raises(TypeError, match="reasoning must be str"):
            QueryExpectedOutput(answer_type="explanation", reasoning=None)  # type: ignore[arg-type]

    def test_reasoning_empty(self) -> None:
        """Empty reasoning string raises ValueError."""
        with pytest.raises(ValueError, match="reasoning must not be empty"):
            QueryExpectedOutput(answer_type="explanation", reasoning="")

    def test_reasoning_whitespace_only(self) -> None:
        """Whitespace-only reasoning is effectively empty — rejected by .strip() guard."""
        with pytest.raises(ValueError, match="reasoning must not be empty"):
            QueryExpectedOutput(answer_type="explanation", reasoning="   ")

    def test_order_ids_as_string(self) -> None:
        """String order_ids triggers character iteration bug — caught by type guard.

        Bug: set("ACC-001") produces {'A','C','-','0','1'} — character iteration.
        The tuple type guard prevents this before any set/iteration occurs.
        """
        with pytest.raises(TypeError, match="order_ids must be tuple"):
            QueryExpectedOutput(
                answer_type="order_list",
                reasoning="test",
                order_ids="ACC-001",  # type: ignore[arg-type]
            )

    def test_order_ids_containing_non_string(self) -> None:
        """Non-string element in order_ids — caught by element guard."""
        with pytest.raises(TypeError, match=r"order_ids\[0\] must be str"):
            QueryExpectedOutput(
                answer_type="explanation",
                reasoning="test",
                order_ids=(42,),  # type: ignore[arg-type]
            )

    def test_order_list_requires_order_ids(self) -> None:
        """answer_type 'order_list' with empty order_ids raises ValueError."""
        with pytest.raises(ValueError, match="requires at least one order_id"):
            QueryExpectedOutput(
                answer_type="order_list",
                reasoning="test",
                order_ids=(),
            )

    def test_order_status_requires_order_ids(self) -> None:
        """answer_type 'order_status' with empty order_ids raises ValueError."""
        with pytest.raises(ValueError, match="requires at least one order_id"):
            QueryExpectedOutput(
                answer_type="order_status",
                reasoning="test",
                order_ids=(),
            )

    def test_prioritized_list_requires_order_ids(self) -> None:
        """answer_type 'prioritized_list' with empty order_ids raises ValueError."""
        with pytest.raises(ValueError, match="requires at least one order_id"):
            QueryExpectedOutput(
                answer_type="prioritized_list",
                reasoning="test",
                order_ids=(),
            )


# ===========================================================================
# QueryScenario — type confusion
# ===========================================================================


class TestQueryScenarioTypeConfusion:
    """Feed wrong types into QueryScenario constructor."""

    def test_tier_as_bool(self) -> None:
        """Bool tier — isinstance(True, int) is True, but the guard rejects bools.

        Python quirk: True/False are ints. The explicit isinstance(tier, bool)
        check fires before isinstance(tier, int) to prevent this.
        """
        with pytest.raises(TypeError, match="tier must be int"):
            _valid_query_scenario(tier=True)

    def test_tier_as_false(self) -> None:
        """Bool False as tier — same guard catches it."""
        with pytest.raises(TypeError, match="tier must be int"):
            _valid_query_scenario(tier=False)

    def test_tier_as_float(self) -> None:
        """Float tier — not an int, caught by type guard."""
        with pytest.raises(TypeError, match="tier must be int"):
            _valid_query_scenario(tier=1.5)

    def test_tier_as_string(self) -> None:
        """String tier — caught by type guard."""
        with pytest.raises(TypeError, match="tier must be int"):
            _valid_query_scenario(tier="1")

    def test_tier_as_none(self) -> None:
        """None tier — caught by type guard."""
        with pytest.raises(TypeError, match="tier must be int"):
            _valid_query_scenario(tier=None)

    def test_tier_below_minimum(self) -> None:
        """Tier 0 is below minimum (must be 1-5)."""
        with pytest.raises(ValueError, match="tier must be 1-5"):
            _valid_query_scenario(tier=0)

    def test_tier_negative(self) -> None:
        """Negative tier rejected."""
        with pytest.raises(ValueError, match="tier must be 1-5"):
            _valid_query_scenario(tier=-1)

    def test_tier_above_maximum(self) -> None:
        """Tier 6 exceeds the five-tier spec — rejected by upper bound."""
        with pytest.raises(ValueError, match="tier must be 1-5"):
            _valid_query_scenario(tier=6)

    def test_scenario_id_wrong_format(self) -> None:
        """scenario_id not matching QR-NNN pattern rejected."""
        with pytest.raises(ValueError, match="Must match QR-NNN"):
            _valid_query_scenario(scenario_id="SC-001")

    def test_scenario_id_too_few_digits(self) -> None:
        """scenario_id with only 2 digits rejected — pattern requires exactly 3."""
        with pytest.raises(ValueError, match="Must match QR-NNN"):
            _valid_query_scenario(scenario_id="QR-01")

    def test_category_not_query(self) -> None:
        """QueryScenario category must be 'query' — any other value rejected."""
        with pytest.raises(ValueError, match="must be 'query'"):
            _valid_query_scenario(category="rule_coverage")

    def test_empty_query_string(self) -> None:
        """Empty query string rejected."""
        with pytest.raises(ValueError, match="query must not be empty"):
            _valid_query_scenario(query="")

    def test_query_whitespace_only(self) -> None:
        """Whitespace-only query is effectively empty — rejected by .strip() guard."""
        with pytest.raises(ValueError, match="query must not be empty"):
            _valid_query_scenario(query="\t\n")

    def test_empty_description(self) -> None:
        """Empty description rejected."""
        with pytest.raises(ValueError, match="description must not be empty"):
            _valid_query_scenario(description="")

    def test_description_whitespace_only(self) -> None:
        """Whitespace-only description is effectively empty — rejected by .strip() guard."""
        with pytest.raises(ValueError, match="description must not be empty"):
            _valid_query_scenario(description="  ")

    def test_database_state_as_dict(self) -> None:
        """Dict instead of DatabaseStateSnapshot — caught by type guard."""
        with pytest.raises(TypeError, match="database_state must be DatabaseStateSnapshot"):
            _valid_query_scenario(database_state={"orders": [], "slides": []})

    def test_expected_output_as_dict(self) -> None:
        """Dict instead of QueryExpectedOutput — caught by type guard."""
        with pytest.raises(TypeError, match="expected_output must be QueryExpectedOutput"):
            _valid_query_scenario(
                expected_output={"answer_type": "explanation", "reasoning": "test"}
            )

    def test_query_as_int(self) -> None:
        """Integer query — caught by type guard."""
        with pytest.raises(TypeError, match="query must be str"):
            _valid_query_scenario(query=42)

    def test_scenario_id_as_int(self) -> None:
        """Integer scenario_id — caught by type guard."""
        with pytest.raises(TypeError, match="scenario_id must be str"):
            _valid_query_scenario(scenario_id=123)


# ===========================================================================
# Boundary values
# ===========================================================================


class TestDatabaseStateSnapshotBoundary:
    """Boundary value tests for DatabaseStateSnapshot."""

    def test_single_order_minimum_valid(self) -> None:
        """Single order with only required fields — minimum valid snapshot."""
        snap = DatabaseStateSnapshot(orders=(_valid_order(),), slides=())
        assert len(snap.orders) == 1
        assert len(snap.slides) == 0

    def test_order_with_empty_flags_list(self) -> None:
        """Order with explicit empty flags list — silently accepted."""
        order = _valid_order(flags=[])
        snap = DatabaseStateSnapshot(orders=(order,), slides=())
        assert snap.orders[0]["flags"] == []

    def test_order_without_flags_key(self) -> None:
        """Order missing flags key entirely — silently accepted (flags optional)."""
        order = _valid_order()
        # flags key is not in base _valid_order
        assert "flags" not in order
        snap = DatabaseStateSnapshot(orders=(order,), slides=())
        assert "flags" not in snap.orders[0]

    def test_order_with_extra_fields_accepted(self) -> None:
        """Order with extra fields (e.g., fixation_time_hours) — silently accepted.

        The schema validates required fields but does not reject extras,
        allowing forward-compatible extension of order data. Note: this also
        means typos in optional field names (e.g., ``fixation_time_hour`` vs
        ``fixation_time_hours``) are silently stored under the wrong key and
        only surface as KeyError downstream.
        """
        order = _valid_order(fixation_time_hours=6.5, receptor_status="ER+")
        snap = DatabaseStateSnapshot(orders=(order,), slides=())
        assert snap.orders[0]["fixation_time_hours"] == 6.5
        assert snap.orders[0]["receptor_status"] == "ER+"

    def test_order_with_valid_flags(self) -> None:
        """Order with valid flags — accepted without error."""
        order = _valid_order(flags=["FIXATION_WARNING"])
        snap = DatabaseStateSnapshot(orders=(order,), slides=())
        assert snap.orders[0]["flags"] == ["FIXATION_WARNING"]

    def test_multiple_orders(self) -> None:
        """Multiple orders with different states — all accepted."""
        orders = (
            _valid_order(order_id="ORD-001", current_state="ACCEPTED"),
            _valid_order(order_id="ORD-002", current_state="ACCESSIONING"),
        )
        snap = DatabaseStateSnapshot(orders=orders, slides=())
        assert len(snap.orders) == 2

    def test_terminal_state_orders_accepted(self) -> None:
        """Orders in terminal states are valid in a query snapshot.

        A lab tech might query "Which orders were terminated this week?"
        so terminal states must be accepted in DatabaseStateSnapshot.
        """
        orders = (
            _valid_order(order_id="ORD-001", current_state="ORDER_COMPLETE"),
            _valid_order(order_id="ORD-002", current_state="ORDER_TERMINATED"),
            _valid_order(order_id="ORD-003", current_state="ORDER_TERMINATED_QNS"),
        )
        snap = DatabaseStateSnapshot(orders=orders, slides=())
        assert len(snap.orders) == 3


class TestQueryExpectedOutputBoundary:
    """Boundary value tests for QueryExpectedOutput."""

    def test_explanation_without_order_ids(self) -> None:
        """answer_type 'explanation' with empty order_ids — valid.

        Explanation-type answers don't require specific order references.
        """
        output = QueryExpectedOutput(
            answer_type="explanation",
            reasoning="General workflow explanation.",
            order_ids=(),
        )
        assert output.order_ids == ()

    def test_order_list_with_order_ids(self) -> None:
        """answer_type 'order_list' with order_ids — valid."""
        output = QueryExpectedOutput(
            answer_type="order_list",
            reasoning="Found matching orders.",
            order_ids=("ORD-001", "ORD-002"),
        )
        assert len(output.order_ids) == 2

    def test_explanation_with_optional_order_ids(self) -> None:
        """answer_type 'explanation' can optionally include order_ids."""
        output = QueryExpectedOutput(
            answer_type="explanation",
            reasoning="Explanation referencing specific orders.",
            order_ids=("ORD-001",),
        )
        assert output.order_ids == ("ORD-001",)


class TestQueryScenarioBoundary:
    """Boundary value tests for QueryScenario."""

    def test_tier_minimum_valid(self) -> None:
        """Tier 1 — minimum valid tier value."""
        scenario = _valid_query_scenario(tier=1)
        assert scenario.tier == 1

    def test_tier_maximum_valid(self) -> None:
        """Tier 5 — maximum valid tier (five-tier spec)."""
        scenario = _valid_query_scenario(tier=5)
        assert scenario.tier == 5

    def test_valid_scenario_round_trip(self) -> None:
        """Fully constructed valid scenario — all fields accessible."""
        scenario = _valid_query_scenario()
        assert scenario.scenario_id == "QR-001"
        assert scenario.category == "query"
        assert scenario.tier == 1
        assert scenario.query == "Which orders are in ACCEPTED state?"
        assert isinstance(scenario.database_state, DatabaseStateSnapshot)
        assert isinstance(scenario.expected_output, QueryExpectedOutput)
