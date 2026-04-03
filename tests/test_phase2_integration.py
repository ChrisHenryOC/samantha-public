"""Phase 2 integration tests: scenario corpus validation and coverage.

Verifies that all scenarios are valid, all rules are covered, all states
are reachable, and the scenario corpus meets Phase 2 completeness criteria.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from src.simulator.coverage_report import (
    CoverageReport,
    generate_coverage_report,
)
from src.simulator.loader import load_all_scenarios
from src.simulator.scenario_validator import validate_all_scenarios
from src.simulator.schema import _ROUTING_CATEGORIES, Scenario
from src.workflow.state_machine import StateMachine

_SCENARIOS_DIR = Path(__file__).resolve().parent.parent / "scenarios"


@pytest.fixture(scope="module")
def state_machine() -> StateMachine:
    """Shared state machine instance for all tests in this module."""
    return StateMachine()


@pytest.fixture(scope="module")
def all_scenarios() -> list[Scenario]:
    """Load all routing scenarios once for the module."""
    scenarios: list[Scenario] = []
    missing = []
    for category in _ROUTING_CATEGORIES:
        category_dir = _SCENARIOS_DIR / category
        if category_dir.exists():
            scenarios.extend(load_all_scenarios(category_dir))
        else:
            missing.append(category)
    assert not missing, f"Missing routing category directories: {missing}"
    scenarios.sort(key=lambda s: s.scenario_id)
    return scenarios


@pytest.fixture(scope="module")
def coverage_report(
    all_scenarios: list[Scenario],
    state_machine: StateMachine,
) -> CoverageReport:
    """Generate coverage report once for the module.

    Validates all scenarios first to ensure coverage data is computed
    from semantically valid ground truth.
    """
    errors = validate_all_scenarios(all_scenarios, state_machine)
    if errors:
        messages = [
            f"  {e.scenario_id} step {e.step_number}: [{e.error_type}] {e.message}" for e in errors
        ]
        raise ValueError(
            f"Cannot generate coverage report: {len(errors)} validation error(s):\n"
            + "\n".join(messages)
        )
    return generate_coverage_report(all_scenarios, state_machine)


class TestScenarioValidity:
    """All scenarios must pass validation against the state machine."""

    def test_all_scenarios_valid(
        self,
        all_scenarios: list[Scenario],
        state_machine: StateMachine,
    ) -> None:
        """Load ALL scenarios, validate all, assert zero errors."""
        errors = validate_all_scenarios(all_scenarios, state_machine)
        if errors:
            messages = [
                f"  {e.scenario_id} step {e.step_number}: [{e.error_type}] {e.message}"
                for e in errors
            ]
            pytest.fail(f"{len(errors)} validation error(s):\n" + "\n".join(messages))


class TestScenarioCoverage:
    """The scenario corpus must meet coverage targets."""

    def test_rule_coverage_complete(
        self,
        coverage_report: CoverageReport,
        state_machine: StateMachine,
    ) -> None:
        """Assert 40/40 rules covered with 2+ scenarios each."""
        all_rule_ids = state_machine.get_all_rule_ids()
        assert len(coverage_report.rules_covered) == len(all_rule_ids), (
            f"Expected {len(all_rule_ids)} rules covered, "
            f"got {len(coverage_report.rules_covered)}. "
            f"Uncovered: {coverage_report.rules_uncovered}"
        )
        under_covered = {
            rid: len(sids) for rid, sids in coverage_report.rules_covered.items() if len(sids) < 2
        }
        assert not under_covered, f"Rules with fewer than 2 scenarios: {under_covered}"

    def test_total_scenario_count(
        self,
        coverage_report: CoverageReport,
    ) -> None:
        """Assert >= 103 total scenarios."""
        assert coverage_report.total_scenarios >= 103, (
            f"Expected >= 103 scenarios, got {coverage_report.total_scenarios}"
        )

    def test_category_distribution(
        self,
        coverage_report: CoverageReport,
    ) -> None:
        """Assert all four categories are present with expected counts."""
        dist = coverage_report.category_distribution
        assert "rule_coverage" in dist, "Missing 'rule_coverage' category"
        assert "multi_rule" in dist, "Missing 'multi_rule' category"
        assert "accumulated_state" in dist, "Missing 'accumulated_state' category"
        assert "unknown_input" in dist, "Missing 'unknown_input' category"
        assert dist["rule_coverage"] >= 79, (
            f"Expected >= 79 rule_coverage scenarios, got {dist['rule_coverage']}"
        )
        assert dist["multi_rule"] >= 10, (
            f"Expected >= 10 multi_rule scenarios, got {dist['multi_rule']}"
        )
        assert dist["accumulated_state"] >= 10, (
            f"Expected >= 10 accumulated_state scenarios, got {dist['accumulated_state']}"
        )
        assert dist["unknown_input"] >= 5, (
            f"Expected >= 5 unknown_input scenarios, got {dist['unknown_input']}"
        )


class TestStateAndFlagCoverage:
    """States and flags must be adequately exercised."""

    def test_all_states_reachable(
        self,
        coverage_report: CoverageReport,
        state_machine: StateMachine,
    ) -> None:
        """Assert all non-terminal states appear as next_state.

        ACCESSIONING is excluded because it is only the implicit starting
        state — no transition targets it.
        """
        terminal_states = {
            sid for sid in state_machine.get_all_states() if state_machine.is_terminal_state(sid)
        }
        non_terminal = state_machine.get_all_states() - terminal_states - {"ACCESSIONING"}
        missing = non_terminal - coverage_report.states_visited
        assert not missing, f"Non-terminal states never reached as next_state: {sorted(missing)}"

    def test_all_flags_exercised(
        self,
        coverage_report: CoverageReport,
        state_machine: StateMachine,
    ) -> None:
        """Assert all 5 flags are set in at least one scenario."""
        all_flags = state_machine.get_all_flag_ids()
        exercised = set(coverage_report.flag_lifecycles)
        missing = all_flags - exercised
        assert not missing, f"Flags never set in any scenario: {sorted(missing)}"

    def test_terminal_states_reached(
        self,
        coverage_report: CoverageReport,
        state_machine: StateMachine,
    ) -> None:
        """Assert testable terminal states reached in at least one scenario.

        ORDER_TERMINATED is excluded: it is only reachable from
        DO_NOT_PROCESS, which is a pass-through state with no rules and
        no valid triggering event type in the current event schema.  The
        LLM evaluation tests the critical decision (reject at accessioning
        -> DO_NOT_PROCESS) rather than the administrative follow-through.
        """
        terminal_states = {
            sid for sid in state_machine.get_all_states() if state_machine.is_terminal_state(sid)
        }
        # ORDER_TERMINATED has no triggering event type — administrative only.
        testable_terminals = terminal_states - {"ORDER_TERMINATED"}
        reached = testable_terminals & coverage_report.states_visited
        missing = testable_terminals - reached
        assert not missing, f"Terminal states never reached: {sorted(missing)}"


class TestScenarioIdentifiers:
    """Scenario IDs must be unique and sequential."""

    def test_scenario_ids_unique(
        self,
        all_scenarios: list[Scenario],
    ) -> None:
        """Assert no duplicate scenario IDs."""
        ids = [s.scenario_id for s in all_scenarios]
        counts = Counter(ids)
        duplicates = {sid for sid, n in counts.items() if n > 1}
        assert not duplicates, f"Duplicate scenario IDs: {sorted(duplicates)}"

    def test_scenario_ids_sequential(
        self,
        all_scenarios: list[Scenario],
    ) -> None:
        """Assert SC-001 through SC-{N} with no gaps."""
        sc_ids = sorted(s.scenario_id for s in all_scenarios if s.scenario_id.startswith("SC-"))
        if not sc_ids:
            pytest.fail("No SC-prefixed scenario IDs found")

        numbers = [int(sid.split("-")[1]) for sid in sc_ids]
        expected = list(range(1, max(numbers) + 1))
        missing = set(expected) - set(numbers)
        assert not missing, f"Missing scenario numbers: {sorted(f'SC-{n:03d}' for n in missing)}"
