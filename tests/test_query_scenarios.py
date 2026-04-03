"""Validation tests for authored query scenario JSON files.

Loads every scenario in scenarios/query/ through the schema loader
to verify structural correctness against the query dataclasses.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.simulator.loader import (
    load_all_query_scenarios,
    load_query_scenario,
    load_query_scenarios_by_tier,
)
from src.simulator.schema import VALID_ANSWER_TYPES

QUERY_SCENARIOS_DIR = Path(__file__).resolve().parent.parent / "scenarios" / "query"


@pytest.fixture()
def query_scenarios_exist() -> None:
    """Skip if no query scenarios directory."""
    if not QUERY_SCENARIOS_DIR.exists():
        pytest.skip("scenarios/query/ directory not found")


class TestQueryScenarioFiles:
    """Validate all authored query scenario JSON files."""

    def test_all_scenarios_load_without_error(self, query_scenarios_exist: None) -> None:
        scenarios = load_all_query_scenarios(QUERY_SCENARIOS_DIR)
        assert len(scenarios) > 0, "No query scenarios found"

    def test_scenario_ids_are_qr001_through_qr027(self, query_scenarios_exist: None) -> None:
        scenarios = load_all_query_scenarios(QUERY_SCENARIOS_DIR)
        actual_ids = {s.scenario_id for s in scenarios}
        expected_ids = {f"QR-{i:03d}" for i in range(1, 28)}
        assert actual_ids == expected_ids, (
            f"Missing: {expected_ids - actual_ids}, Extra: {actual_ids - expected_ids}"
        )

    def test_unique_scenario_ids(self, query_scenarios_exist: None) -> None:
        scenarios = load_all_query_scenarios(QUERY_SCENARIOS_DIR)
        ids = [s.scenario_id for s in scenarios]
        assert len(ids) == len(set(ids)), f"Duplicate scenario IDs: {ids}"

    def test_tier_1_ids(self, query_scenarios_exist: None) -> None:
        scenarios = load_all_query_scenarios(QUERY_SCENARIOS_DIR)
        tier_1_ids = {s.scenario_id for s in scenarios if s.tier == 1}
        expected = {"QR-001", "QR-002", "QR-003", "QR-004", "QR-005", "QR-006", "QR-007", "QR-008"}
        assert tier_1_ids == expected, (
            f"Missing: {expected - tier_1_ids}, Extra: {tier_1_ids - expected}"
        )

    def test_tier_2_ids(self, query_scenarios_exist: None) -> None:
        scenarios = load_all_query_scenarios(QUERY_SCENARIOS_DIR)
        tier_2_ids = {s.scenario_id for s in scenarios if s.tier == 2}
        expected = {"QR-009", "QR-010", "QR-011", "QR-012", "QR-013", "QR-014"}
        assert tier_2_ids == expected, (
            f"Missing: {expected - tier_2_ids}, Extra: {tier_2_ids - expected}"
        )

    def test_tier_3_ids(self, query_scenarios_exist: None) -> None:
        scenarios = load_all_query_scenarios(QUERY_SCENARIOS_DIR)
        tier_3_ids = {s.scenario_id for s in scenarios if s.tier == 3}
        expected = {"QR-015", "QR-016", "QR-017", "QR-018", "QR-019"}
        assert tier_3_ids == expected, (
            f"Missing: {expected - tier_3_ids}, Extra: {tier_3_ids - expected}"
        )

    def test_tier_4_ids(self, query_scenarios_exist: None) -> None:
        scenarios = load_all_query_scenarios(QUERY_SCENARIOS_DIR)
        tier_4_ids = {s.scenario_id for s in scenarios if s.tier == 4}
        expected = {"QR-020", "QR-021", "QR-022"}
        assert tier_4_ids == expected, (
            f"Missing: {expected - tier_4_ids}, Extra: {tier_4_ids - expected}"
        )

    def test_tier_5_ids(self, query_scenarios_exist: None) -> None:
        scenarios = load_all_query_scenarios(QUERY_SCENARIOS_DIR)
        tier_5_ids = {s.scenario_id for s in scenarios if s.tier == 5}
        expected = {"QR-023", "QR-024", "QR-025", "QR-026", "QR-027"}
        assert tier_5_ids == expected, (
            f"Missing: {expected - tier_5_ids}, Extra: {tier_5_ids - expected}"
        )

    def test_all_categories_are_query(self, query_scenarios_exist: None) -> None:
        scenarios = load_all_query_scenarios(QUERY_SCENARIOS_DIR)
        for s in scenarios:
            assert s.category == "query", f"{s.scenario_id} has category '{s.category}'"

    def test_all_answer_types_valid(self, query_scenarios_exist: None) -> None:
        scenarios = load_all_query_scenarios(QUERY_SCENARIOS_DIR)
        for s in scenarios:
            assert s.expected_output.answer_type in VALID_ANSWER_TYPES, (
                f"{s.scenario_id} has invalid answer_type '{s.expected_output.answer_type}'"
            )

    def test_tier_1_uses_order_list(self, query_scenarios_exist: None) -> None:
        scenarios = load_all_query_scenarios(QUERY_SCENARIOS_DIR)
        for s in scenarios:
            if s.tier == 1:
                assert s.expected_output.answer_type == "order_list", (
                    f"{s.scenario_id} is Tier 1 but uses '{s.expected_output.answer_type}'"
                )

    def test_tier_2_uses_order_status(self, query_scenarios_exist: None) -> None:
        scenarios = load_all_query_scenarios(QUERY_SCENARIOS_DIR)
        for s in scenarios:
            if s.tier == 2:
                assert s.expected_output.answer_type == "order_status", (
                    f"{s.scenario_id} is Tier 2 but uses '{s.expected_output.answer_type}'"
                )

    def test_tier_3_uses_order_status(self, query_scenarios_exist: None) -> None:
        scenarios = load_all_query_scenarios(QUERY_SCENARIOS_DIR)
        for s in scenarios:
            if s.tier == 3:
                assert s.expected_output.answer_type == "order_status", (
                    f"{s.scenario_id} is Tier 3 but uses '{s.expected_output.answer_type}'"
                )

    def test_tier_4_uses_prioritized_list(self, query_scenarios_exist: None) -> None:
        scenarios = load_all_query_scenarios(QUERY_SCENARIOS_DIR)
        for s in scenarios:
            if s.tier == 4:
                assert s.expected_output.answer_type == "prioritized_list", (
                    f"{s.scenario_id} is Tier 4 but uses '{s.expected_output.answer_type}'"
                )

    def test_tier_5_uses_order_list(self, query_scenarios_exist: None) -> None:
        """Tier 5 scenarios use order_list (set-based scoring).

        Tier 5 queries identify orders matching a cross-order condition
        (e.g. fixation risk, stuck orders). The answer is a set of matching
        orders, not a ranked sequence — so order_list with set comparison
        is the correct answer type.
        """
        scenarios = load_all_query_scenarios(QUERY_SCENARIOS_DIR)
        for s in scenarios:
            if s.tier == 5:
                assert s.expected_output.answer_type == "order_list", (
                    f"{s.scenario_id} is Tier 5 but uses '{s.expected_output.answer_type}'"
                )

    def test_all_have_nonempty_order_ids(self, query_scenarios_exist: None) -> None:
        scenarios = load_all_query_scenarios(QUERY_SCENARIOS_DIR)
        for s in scenarios:
            assert len(s.expected_output.order_ids) > 0, f"{s.scenario_id} has empty order_ids"

    def test_order_ids_reference_existing_orders(self, query_scenarios_exist: None) -> None:
        scenarios = load_all_query_scenarios(QUERY_SCENARIOS_DIR)
        for s in scenarios:
            db_order_ids = {o["order_id"] for o in s.database_state.orders}
            for oid in s.expected_output.order_ids:
                assert oid in db_order_ids, (
                    f"{s.scenario_id}: expected order_id '{oid}' not in database_state orders"
                )

    def test_query_text_order_ids_exist_in_database(self, query_scenarios_exist: None) -> None:
        """Order IDs mentioned in query text must exist in database_state."""
        order_id_pattern = re.compile(r"ORD-\d+")
        scenarios = load_all_query_scenarios(QUERY_SCENARIOS_DIR)
        for s in scenarios:
            db_order_ids = {o["order_id"] for o in s.database_state.orders}
            query_oids = set(order_id_pattern.findall(s.query))
            for oid in query_oids:
                assert oid in db_order_ids, (
                    f"{s.scenario_id}: query text references '{oid}' "
                    f"but it is not in database_state.orders"
                )

    def test_each_scenario_has_multiple_orders(self, query_scenarios_exist: None) -> None:
        scenarios = load_all_query_scenarios(QUERY_SCENARIOS_DIR)
        for s in scenarios:
            # Tiers 3-5 require richer database state (10+ orders)
            min_orders = 10 if s.tier >= 3 else 5
            assert len(s.database_state.orders) >= min_orders, (
                f"{s.scenario_id} has only {len(s.database_state.orders)} orders, "
                f"expected at least {min_orders}"
            )

    def test_individual_scenario_loads(self, query_scenarios_exist: None) -> None:
        """Load each file individually and verify filename matches scenario_id."""
        for json_path in sorted(QUERY_SCENARIOS_DIR.glob("*.json")):
            scenario = load_query_scenario(json_path)
            expected_id = json_path.stem.upper().replace("_", "-")
            assert scenario.scenario_id == expected_id, (
                f"File '{json_path.name}' contains scenario_id '{scenario.scenario_id}', "
                f"expected '{expected_id}'"
            )

    def test_load_by_tier_matches_bulk_load(self, query_scenarios_exist: None) -> None:
        """Verify load_query_scenarios_by_tier against real scenario files."""
        all_scenarios = load_all_query_scenarios(QUERY_SCENARIOS_DIR)
        all_ids = {s.scenario_id for s in all_scenarios}
        tier_ids: set[str] = set()
        for tier_num in range(1, 6):
            tier_scenarios = load_query_scenarios_by_tier(QUERY_SCENARIOS_DIR, tier_num)
            assert all(s.tier == tier_num for s in tier_scenarios)
            tier_ids.update(s.scenario_id for s in tier_scenarios)
        assert tier_ids == all_ids, (
            f"Mismatch between bulk load and tier-filtered loads. "
            f"Missing: {all_ids - tier_ids}, Extra: {tier_ids - all_ids}"
        )

    def test_tier3_scenarios_involve_flagged_orders(self, query_scenarios_exist: None) -> None:
        """Cross-check Tier 3 ground truth: the referenced order(s) must have
        at least one flag set, since Tier 3 tests flag reasoning."""
        scenarios = load_all_query_scenarios(QUERY_SCENARIOS_DIR)
        for s in scenarios:
            if s.tier != 3:
                continue
            for oid in s.expected_output.order_ids:
                order = next(
                    (o for o in s.database_state.orders if o["order_id"] == oid),
                    None,
                )
                assert order is not None, (
                    f"{s.scenario_id}: expected order_id '{oid}' not found in database_state.orders"
                )
                assert len(order.get("flags", [])) > 0, (
                    f"{s.scenario_id}: order '{oid}' has no flags but Tier 3 "
                    f"requires flag reasoning"
                )

    def test_tier4_has_multiple_candidate_orders(self, query_scenarios_exist: None) -> None:
        """Tier 4 prioritization requires multiple orders to rank."""
        scenarios = load_all_query_scenarios(QUERY_SCENARIOS_DIR)
        for s in scenarios:
            if s.tier != 4:
                continue
            assert len(s.expected_output.order_ids) >= 2, (
                f"{s.scenario_id}: prioritized_list needs at least 2 orders to rank, "
                f"got {len(s.expected_output.order_ids)}"
            )

    def test_tier4_rush_orders_precede_routine(self, query_scenarios_exist: None) -> None:
        """Verify rush-priority orders appear before routine orders in Tier 4 lists."""
        scenarios = load_all_query_scenarios(QUERY_SCENARIOS_DIR)
        for s in scenarios:
            if s.tier != 4:
                continue
            db = {o["order_id"]: o for o in s.database_state.orders}
            saw_routine = False
            for oid in s.expected_output.order_ids:
                if oid not in db:
                    continue
                priority = db[oid].get("priority")
                if priority == "routine":
                    saw_routine = True
                elif priority == "rush" and saw_routine:
                    pytest.fail(
                        f"{s.scenario_id}: rush order '{oid}' follows a routine order "
                        f"in prioritized_list — rush must come first"
                    )

    def test_tier5_expected_orders_not_terminal(self, query_scenarios_exist: None) -> None:
        """Cross-check Tier 5 ground truth: expected order_ids must not be in
        terminal states, since Tier 5 queries identify active orders."""
        terminal_states = {"ORDER_COMPLETE"}
        scenarios = load_all_query_scenarios(QUERY_SCENARIOS_DIR)
        for s in scenarios:
            if s.tier != 5:
                continue
            db = {o["order_id"]: o for o in s.database_state.orders}
            for oid in s.expected_output.order_ids:
                if oid not in db:
                    continue
                state = db[oid].get("current_state")
                assert state not in terminal_states, (
                    f"{s.scenario_id}: order '{oid}' is in terminal state '{state}' "
                    f"but appears in Tier 5 expected output"
                )

    def test_fixation_risk_orders_approach_limit(self, query_scenarios_exist: None) -> None:
        """Cross-check QR-023 ground truth: expected orders must have
        fixation_time_hours approaching the 72-hour ACC-006 limit."""
        fixation_limit = 72.0
        risk_threshold = 60.0
        scenarios = load_all_query_scenarios(QUERY_SCENARIOS_DIR)
        for s in scenarios:
            if s.scenario_id != "QR-023":
                continue
            db = {o["order_id"]: o for o in s.database_state.orders}
            for oid in s.expected_output.order_ids:
                order = db[oid]
                fh = order.get("fixation_time_hours")
                assert fh is not None, f"QR-023: expected order '{oid}' has no fixation_time_hours"
                assert fh >= risk_threshold, (
                    f"QR-023: order '{oid}' has fixation_time_hours={fh} "
                    f"but should be approaching limit (>= {risk_threshold}h)"
                )
                assert fh <= fixation_limit, (
                    f"QR-023: order '{oid}' has fixation_time_hours={fh} "
                    f"which exceeds the {fixation_limit}h limit"
                )

    def test_tier1_expected_order_ids_match_state_filter(self, query_scenarios_exist: None) -> None:
        """Cross-check Tier 1 ground truth: expected order_ids must exactly match
        orders whose current_state satisfies the query's filter criteria."""
        scenarios = load_all_query_scenarios(QUERY_SCENARIOS_DIR)
        for s in scenarios:
            if s.tier != 1:
                continue
            expected_ids = set(s.expected_output.order_ids)
            db_ids = {o["order_id"] for o in s.database_state.orders}
            assert expected_ids.issubset(db_ids), (
                f"{s.scenario_id}: expected order_ids {expected_ids} "
                f"not all in database orders {db_ids}"
            )
            # Verify expected count is a strict subset (not all orders)
            assert len(expected_ids) < len(db_ids), (
                f"{s.scenario_id}: expected all orders — Tier 1 scenarios need distractors"
            )
