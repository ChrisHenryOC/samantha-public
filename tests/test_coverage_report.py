"""Unit tests for src/simulator/coverage_report.py.

Tests generate_coverage_report, detect_gaps, and format_coverage_report
with controlled inputs to verify edge cases and boundary conditions.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.simulator.coverage_report import (
    CoverageGap,
    CoverageReport,
    detect_gaps,
    format_coverage_report,
    generate_coverage_report,
)
from src.simulator.schema import ExpectedOutput, Scenario, ScenarioStep


def _make_step(
    step_num: int,
    next_state: str,
    *,
    rules: tuple[str, ...] = (),
    flags: tuple[str, ...] = (),
) -> ScenarioStep:
    """Create a ScenarioStep with minimal valid data."""
    return ScenarioStep(
        step=step_num,
        event_type="order_received" if step_num == 1 else "grossing_complete",
        event_data={},
        expected_output=ExpectedOutput(
            next_state=next_state,
            applied_rules=rules,
            flags=flags,
        ),
    )


def _make_scenario(
    scenario_id: str,
    category: str,
    steps: list[ScenarioStep],
) -> Scenario:
    """Create a Scenario from a list of steps."""
    return Scenario(
        scenario_id=scenario_id,
        category=category,
        description=f"Test scenario {scenario_id}",
        steps=tuple(steps),
    )


def _make_state_machine(
    rule_ids: frozenset[str],
    state_ids: frozenset[str],
    flag_ids: frozenset[str],
    terminal_states: frozenset[str] | None = None,
) -> MagicMock:
    """Create a mock StateMachine with the given IDs."""
    sm = MagicMock()
    sm.get_all_rule_ids.return_value = rule_ids
    sm.get_all_states.return_value = state_ids
    sm.get_all_flag_ids.return_value = flag_ids
    _terminals = terminal_states or frozenset()
    sm.is_terminal_state.side_effect = lambda s: s in _terminals
    return sm


class TestGenerateCoverageReport:
    """Tests for generate_coverage_report with controlled inputs."""

    def test_empty_scenarios(self) -> None:
        """Empty scenario list produces a report with all fields empty."""
        sm = _make_state_machine(
            rule_ids=frozenset({"ACC-001", "ACC-002"}),
            state_ids=frozenset({"ACCESSIONING", "ACCEPTED"}),
            flag_ids=frozenset({"FIXATION_WARNING"}),
        )
        report = generate_coverage_report([], sm)
        assert report.total_scenarios == 0
        assert report.total_steps == 0
        assert report.rules_covered == {}
        assert report.rules_uncovered == ["ACC-001", "ACC-002"]
        assert report.states_visited == set()
        assert report.transitions_exercised == set()
        assert report.flag_lifecycles == {}
        assert report.category_distribution == {}

    def test_single_scenario_coverage(self) -> None:
        """A single scenario correctly populates all coverage fields."""
        sm = _make_state_machine(
            rule_ids=frozenset({"ACC-001", "ACC-002"}),
            state_ids=frozenset({"ACCESSIONING", "ACCEPTED", "SAMPLE_PREP_PROCESSING"}),
            flag_ids=frozenset({"FIXATION_WARNING"}),
        )
        scenario = _make_scenario(
            "SC-001",
            "rule_coverage",
            [
                _make_step(1, "ACCEPTED", rules=("ACC-001",), flags=("FIXATION_WARNING",)),
                _make_step(2, "SAMPLE_PREP_PROCESSING", rules=("ACC-002",)),
            ],
        )
        report = generate_coverage_report([scenario], sm)
        assert report.total_scenarios == 1
        assert report.total_steps == 2
        assert set(report.rules_covered.keys()) == {"ACC-001", "ACC-002"}
        assert report.rules_uncovered == []
        assert report.states_visited == {"ACCEPTED", "SAMPLE_PREP_PROCESSING"}
        assert ("ACCESSIONING", "ACCEPTED") in report.transitions_exercised
        assert ("ACCEPTED", "SAMPLE_PREP_PROCESSING") in report.transitions_exercised
        assert report.flag_lifecycles == {"FIXATION_WARNING": ["SC-001"]}
        assert report.category_distribution == {"rule_coverage": 1}

    def test_flag_deduplication_within_scenario(self) -> None:
        """Same flag set at multiple steps in one scenario is counted once."""
        sm = _make_state_machine(
            rule_ids=frozenset({"ACC-001"}),
            state_ids=frozenset({"ACCESSIONING", "ACCEPTED", "SAMPLE_PREP_PROCESSING"}),
            flag_ids=frozenset({"FIXATION_WARNING"}),
        )
        scenario = _make_scenario(
            "SC-001",
            "rule_coverage",
            [
                _make_step(1, "ACCEPTED", rules=("ACC-001",), flags=("FIXATION_WARNING",)),
                _make_step(2, "SAMPLE_PREP_PROCESSING", flags=("FIXATION_WARNING",)),
            ],
        )
        report = generate_coverage_report([scenario], sm)
        assert report.flag_lifecycles["FIXATION_WARNING"] == ["SC-001"]

    def test_multiple_scenarios_accumulate_rules(self) -> None:
        """Multiple scenarios correctly accumulate rule coverage."""
        sm = _make_state_machine(
            rule_ids=frozenset({"ACC-001"}),
            state_ids=frozenset({"ACCESSIONING", "ACCEPTED"}),
            flag_ids=frozenset(),
        )
        s1 = _make_scenario(
            "SC-001",
            "rule_coverage",
            [
                _make_step(1, "ACCEPTED", rules=("ACC-001",)),
            ],
        )
        s2 = _make_scenario(
            "SC-002",
            "rule_coverage",
            [
                _make_step(1, "ACCEPTED", rules=("ACC-001",)),
            ],
        )
        report = generate_coverage_report([s1, s2], sm)
        assert report.rules_covered["ACC-001"] == ["SC-001", "SC-002"]

    def test_transitions_exercised_correct(self) -> None:
        """Transitions track (current_state, next_state) pairs correctly."""
        sm = _make_state_machine(
            rule_ids=frozenset({"ACC-001", "SP-001"}),
            state_ids=frozenset({"ACCESSIONING", "ACCEPTED", "SAMPLE_PREP_PROCESSING"}),
            flag_ids=frozenset(),
        )
        scenario = _make_scenario(
            "SC-001",
            "rule_coverage",
            [
                _make_step(1, "ACCEPTED", rules=("ACC-001",)),
                _make_step(2, "SAMPLE_PREP_PROCESSING", rules=("SP-001",)),
            ],
        )
        report = generate_coverage_report([scenario], sm)
        assert report.transitions_exercised == {
            ("ACCESSIONING", "ACCEPTED"),
            ("ACCEPTED", "SAMPLE_PREP_PROCESSING"),
        }

    def test_unknown_rule_id_raises(self) -> None:
        """A rule ID not in the catalog raises ValueError."""
        sm = _make_state_machine(
            rule_ids=frozenset({"ACC-001"}),
            state_ids=frozenset({"ACCESSIONING", "ACCEPTED"}),
            flag_ids=frozenset(),
        )
        scenario = _make_scenario(
            "SC-001",
            "rule_coverage",
            [
                _make_step(1, "ACCEPTED", rules=("ACC-099",)),
            ],
        )
        with pytest.raises(ValueError, match="unknown rule 'ACC-099'"):
            generate_coverage_report([scenario], sm)


class TestDetectGaps:
    """Tests for detect_gaps with controlled CoverageReport inputs."""

    def test_no_gaps(self) -> None:
        """A fully covered report produces no gaps."""
        sm = _make_state_machine(
            rule_ids=frozenset({"ACC-001"}),
            state_ids=frozenset({"ACCESSIONING", "ACCEPTED"}),
            flag_ids=frozenset({"FIXATION_WARNING"}),
        )
        report = CoverageReport(
            rules_covered={"ACC-001": ["SC-001", "SC-002"]},
            rules_uncovered=[],
            states_visited={"ACCESSIONING", "ACCEPTED"},
            states_unvisited=set(),
            transitions_exercised={("ACCESSIONING", "ACCEPTED")},
            flag_lifecycles={"FIXATION_WARNING": ["SC-001"]},
            category_distribution={
                "rule_coverage": 1,
                "multi_rule": 1,
                "accumulated_state": 1,
                "unknown_input": 1,
                "hallucination": 1,
                "query": 1,
            },
            total_scenarios=6,
            total_steps=6,
        )
        gaps = detect_gaps(report, sm)
        assert gaps == []

    def test_under_covered_rule_boundary(self) -> None:
        """A rule with exactly 1 scenario is under-covered; 2 is not."""
        sm = _make_state_machine(
            rule_ids=frozenset({"ACC-001", "ACC-002"}),
            state_ids=frozenset({"ACCESSIONING"}),
            flag_ids=frozenset(),
        )
        report = CoverageReport(
            rules_covered={
                "ACC-001": ["SC-001"],  # exactly 1 — should be a gap
                "ACC-002": ["SC-001", "SC-002"],  # exactly 2 — not a gap
            },
            rules_uncovered=[],
            states_visited={"ACCESSIONING"},
            states_unvisited=set(),
            transitions_exercised=set(),
            flag_lifecycles={},
            category_distribution={
                "rule_coverage": 1,
                "multi_rule": 1,
                "accumulated_state": 1,
                "unknown_input": 1,
            },
            total_scenarios=2,
            total_steps=2,
        )
        gaps = detect_gaps(report, sm)
        under_covered = [g for g in gaps if g.gap_type == "under_covered_rule"]
        assert len(under_covered) == 1
        assert "ACC-001" in under_covered[0].detail

    def test_uncovered_rule_gap(self) -> None:
        """Rules with zero coverage appear as uncovered_rule gaps."""
        sm = _make_state_machine(
            rule_ids=frozenset({"ACC-001"}),
            state_ids=frozenset({"ACCESSIONING"}),
            flag_ids=frozenset(),
        )
        report = CoverageReport(
            rules_covered={},
            rules_uncovered=["ACC-001"],
            states_visited={"ACCESSIONING"},
            states_unvisited=set(),
            transitions_exercised=set(),
            flag_lifecycles={},
            category_distribution={
                "rule_coverage": 1,
                "multi_rule": 1,
                "accumulated_state": 1,
                "unknown_input": 1,
            },
            total_scenarios=1,
            total_steps=1,
        )
        gaps = detect_gaps(report, sm)
        uncovered = [g for g in gaps if g.gap_type == "uncovered_rule"]
        assert len(uncovered) == 1
        assert "ACC-001" in uncovered[0].detail

    def test_unvisited_state_gap(self) -> None:
        """Unvisited states appear as gaps."""
        sm = _make_state_machine(
            rule_ids=frozenset(),
            state_ids=frozenset({"ACCESSIONING", "ACCEPTED"}),
            flag_ids=frozenset(),
        )
        report = CoverageReport(
            rules_covered={},
            rules_uncovered=[],
            states_visited={"ACCESSIONING"},
            states_unvisited={"ACCEPTED"},
            transitions_exercised=set(),
            flag_lifecycles={},
            category_distribution={
                "rule_coverage": 1,
                "multi_rule": 1,
                "accumulated_state": 1,
                "unknown_input": 1,
            },
            total_scenarios=1,
            total_steps=1,
        )
        gaps = detect_gaps(report, sm)
        state_gaps = [g for g in gaps if g.gap_type == "unvisited_state"]
        assert len(state_gaps) == 1
        assert "ACCEPTED" in state_gaps[0].detail

    def test_excluded_states_not_reported(self) -> None:
        """States in excluded_states are not reported as unvisited gaps."""
        sm = _make_state_machine(
            rule_ids=frozenset(),
            state_ids=frozenset({"ACCESSIONING", "ACCEPTED", "ORDER_TERMINATED"}),
            flag_ids=frozenset(),
        )
        report = CoverageReport(
            rules_covered={},
            rules_uncovered=[],
            states_visited={"ACCEPTED"},
            states_unvisited={"ACCESSIONING", "ORDER_TERMINATED"},
            transitions_exercised=set(),
            flag_lifecycles={},
            category_distribution={
                "rule_coverage": 1,
                "multi_rule": 1,
                "accumulated_state": 1,
                "unknown_input": 1,
            },
            total_scenarios=1,
            total_steps=1,
        )
        gaps = detect_gaps(
            report,
            sm,
            excluded_states={"ACCESSIONING", "ORDER_TERMINATED"},
        )
        state_gaps = [g for g in gaps if g.gap_type == "unvisited_state"]
        assert state_gaps == []

    def test_unexercised_flag_gap(self) -> None:
        """Flags not exercised in any scenario appear as gaps."""
        sm = _make_state_machine(
            rule_ids=frozenset(),
            state_ids=frozenset({"ACCESSIONING"}),
            flag_ids=frozenset({"FIXATION_WARNING", "RECUT_REQUESTED"}),
        )
        report = CoverageReport(
            rules_covered={},
            rules_uncovered=[],
            states_visited={"ACCESSIONING"},
            states_unvisited=set(),
            transitions_exercised=set(),
            flag_lifecycles={"FIXATION_WARNING": ["SC-001"]},
            category_distribution={
                "rule_coverage": 1,
                "multi_rule": 1,
                "accumulated_state": 1,
                "unknown_input": 1,
            },
            total_scenarios=1,
            total_steps=1,
        )
        gaps = detect_gaps(report, sm)
        flag_gaps = [g for g in gaps if g.gap_type == "unexercised_flag"]
        assert len(flag_gaps) == 1
        assert "RECUT_REQUESTED" in flag_gaps[0].detail

    def test_missing_category_gap(self) -> None:
        """Missing scenario categories appear as gaps."""
        sm = _make_state_machine(
            rule_ids=frozenset(),
            state_ids=frozenset({"ACCESSIONING"}),
            flag_ids=frozenset(),
        )
        report = CoverageReport(
            rules_covered={},
            rules_uncovered=[],
            states_visited={"ACCESSIONING"},
            states_unvisited=set(),
            transitions_exercised=set(),
            flag_lifecycles={},
            category_distribution={"rule_coverage": 1},
            total_scenarios=1,
            total_steps=1,
        )
        gaps = detect_gaps(report, sm)
        cat_gaps = [g for g in gaps if g.gap_type == "missing_category"]
        missing_cats = {g.detail for g in cat_gaps}
        assert any("multi_rule" in d for d in missing_cats)
        assert any("accumulated_state" in d for d in missing_cats)
        assert any("unknown_input" in d for d in missing_cats)
        assert any("hallucination" in d for d in missing_cats)


class TestFormatCoverageReport:
    """Tests for format_coverage_report output."""

    def test_contains_header_and_summary(self) -> None:
        """Output includes the header and summary sections."""
        sm = _make_state_machine(
            rule_ids=frozenset({"ACC-001"}),
            state_ids=frozenset({"ACCESSIONING", "ACCEPTED"}),
            flag_ids=frozenset({"FIXATION_WARNING"}),
        )
        report = CoverageReport(
            rules_covered={"ACC-001": ["SC-001", "SC-002"]},
            rules_uncovered=[],
            states_visited={"ACCESSIONING", "ACCEPTED"},
            states_unvisited=set(),
            transitions_exercised={("ACCESSIONING", "ACCEPTED")},
            flag_lifecycles={"FIXATION_WARNING": ["SC-001"]},
            category_distribution={
                "rule_coverage": 1,
                "multi_rule": 1,
                "accumulated_state": 1,
                "unknown_input": 1,
            },
            total_scenarios=4,
            total_steps=4,
        )
        output = format_coverage_report(report, sm)
        assert "SCENARIO COVERAGE REPORT" in output
        assert "Total scenarios: 4" in output
        assert "Rules covered:   1/1" in output

    def test_no_gaps_message(self) -> None:
        """When no gaps exist, output says so."""
        sm = _make_state_machine(
            rule_ids=frozenset({"ACC-001"}),
            state_ids=frozenset({"ACCESSIONING", "ACCEPTED"}),
            flag_ids=frozenset({"FIXATION_WARNING"}),
        )
        report = CoverageReport(
            rules_covered={"ACC-001": ["SC-001", "SC-002"]},
            rules_uncovered=[],
            states_visited={"ACCESSIONING", "ACCEPTED"},
            states_unvisited=set(),
            transitions_exercised={("ACCESSIONING", "ACCEPTED")},
            flag_lifecycles={"FIXATION_WARNING": ["SC-001"]},
            category_distribution={
                "rule_coverage": 1,
                "multi_rule": 1,
                "accumulated_state": 1,
                "unknown_input": 1,
                "hallucination": 1,
                "query": 1,
            },
            total_scenarios=6,
            total_steps=6,
        )
        output = format_coverage_report(report, sm)
        assert "No coverage gaps detected." in output

    def test_gaps_section_appears(self) -> None:
        """When gaps exist, the COVERAGE GAPS section appears."""
        sm = _make_state_machine(
            rule_ids=frozenset({"ACC-001"}),
            state_ids=frozenset({"ACCESSIONING"}),
            flag_ids=frozenset(),
        )
        report = CoverageReport(
            rules_covered={},
            rules_uncovered=["ACC-001"],
            states_visited={"ACCESSIONING"},
            states_unvisited=set(),
            transitions_exercised=set(),
            flag_lifecycles={},
            category_distribution={
                "rule_coverage": 1,
                "multi_rule": 1,
                "accumulated_state": 1,
                "unknown_input": 1,
            },
            total_scenarios=1,
            total_steps=1,
        )
        output = format_coverage_report(report, sm)
        assert "COVERAGE GAPS" in output
        assert "uncovered_rule" in output

    def test_uncovered_rules_listed(self) -> None:
        """Uncovered rules appear in the UNCOVERED RULES subsection."""
        sm = _make_state_machine(
            rule_ids=frozenset({"ACC-001", "ACC-002"}),
            state_ids=frozenset({"ACCESSIONING"}),
            flag_ids=frozenset(),
        )
        report = CoverageReport(
            rules_covered={"ACC-001": ["SC-001", "SC-002"]},
            rules_uncovered=["ACC-002"],
            states_visited={"ACCESSIONING"},
            states_unvisited=set(),
            transitions_exercised=set(),
            flag_lifecycles={},
            category_distribution={
                "rule_coverage": 1,
                "multi_rule": 1,
                "accumulated_state": 1,
                "unknown_input": 1,
            },
            total_scenarios=1,
            total_steps=1,
        )
        output = format_coverage_report(report, sm)
        assert "UNCOVERED RULES:" in output
        assert "ACC-002" in output

    def test_unvisited_states_section(self) -> None:
        """Unvisited states appear in the UNVISITED STATES section."""
        sm = _make_state_machine(
            rule_ids=frozenset(),
            state_ids=frozenset({"ACCESSIONING", "ACCEPTED"}),
            flag_ids=frozenset(),
        )
        report = CoverageReport(
            rules_covered={},
            rules_uncovered=[],
            states_visited={"ACCESSIONING"},
            states_unvisited={"ACCEPTED"},
            transitions_exercised=set(),
            flag_lifecycles={},
            category_distribution={
                "rule_coverage": 1,
                "multi_rule": 1,
                "accumulated_state": 1,
                "unknown_input": 1,
            },
            total_scenarios=1,
            total_steps=1,
        )
        output = format_coverage_report(report, sm)
        assert "UNVISITED STATES" in output
        assert "ACCEPTED" in output


class TestCoverageGapFrozen:
    """CoverageGap should be immutable."""

    def test_frozen(self) -> None:
        gap = CoverageGap(gap_type="test", detail="test detail")
        with pytest.raises(AttributeError):
            gap.gap_type = "modified"  # type: ignore[misc]
