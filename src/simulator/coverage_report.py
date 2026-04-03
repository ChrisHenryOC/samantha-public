"""Scenario coverage analysis for the rule catalog and state machine.

Analyzes how well the scenario corpus covers the workflow's rules, states,
transitions, and flags.  Produces a structured CoverageReport and a
human-readable text summary with gap detection.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.simulator.schema import VALID_CATEGORIES, Scenario
from src.workflow.state_machine import StateMachine

_INITIAL_STATE = "ACCESSIONING"


@dataclass
class CoverageReport:
    """Structured coverage analysis of scenarios against the state machine."""

    rules_covered: dict[str, list[str]]
    """rule_id -> list of scenario_ids that test it."""

    rules_uncovered: list[str]
    """rule_ids with zero scenario coverage."""

    states_visited: set[str]
    """All states reached as next_state across scenarios."""

    states_unvisited: set[str]
    """States never reached as next_state."""

    transitions_exercised: set[tuple[str, str]]
    """(from_state, to_state) pairs exercised across scenarios."""

    flag_lifecycles: dict[str, list[str]]
    """flag_id -> scenario_ids that exercise it (set the flag)."""

    category_distribution: dict[str, int]
    """category -> count of scenarios."""

    total_scenarios: int
    """Total number of scenarios analyzed."""

    total_steps: int
    """Total number of steps across all scenarios."""


@dataclass(frozen=True)
class CoverageGap:
    """A single coverage gap detected during analysis."""

    gap_type: str
    """One of: under_covered_rule, uncovered_rule, unvisited_state,
    unexercised_flag, missing_category."""

    detail: str
    """Human-readable description of the gap."""


def generate_coverage_report(
    scenarios: list[Scenario],
    state_machine: StateMachine,
) -> CoverageReport:
    """Analyze scenario coverage against the state machine.

    Walks every step of every scenario to collect which rules, states,
    transitions, and flags are exercised.

    Args:
        scenarios: All loaded scenarios.
        state_machine: The workflow state machine.

    Returns:
        A frozen CoverageReport with all coverage data.
    """
    all_rule_ids = state_machine.get_all_rule_ids()
    all_state_ids = state_machine.get_all_states()

    rules_covered: dict[str, list[str]] = {}
    states_visited: set[str] = set()
    transitions_exercised: set[tuple[str, str]] = set()
    flag_lifecycles: dict[str, list[str]] = {}
    category_distribution: dict[str, int] = {}
    total_steps = 0

    for scenario in scenarios:
        # Category distribution.
        category_distribution[scenario.category] = (
            category_distribution.get(scenario.category, 0) + 1
        )

        # Walk steps.
        current_state = _INITIAL_STATE
        for step in scenario.steps:
            total_steps += 1
            next_state = step.expected_output.next_state

            # States visited.
            states_visited.add(next_state)

            # Transitions exercised.
            transitions_exercised.add((current_state, next_state))

            # Rules covered.
            for rule_id in step.expected_output.applied_rules:
                if rule_id not in all_rule_ids:
                    raise ValueError(
                        f"Scenario {scenario.scenario_id} references unknown "
                        f"rule '{rule_id}' not in the rule catalog"
                    )
                rules_covered.setdefault(rule_id, []).append(scenario.scenario_id)

            # Flags exercised.
            for flag_id in step.expected_output.flags:
                scenarios_for_flag = flag_lifecycles.setdefault(flag_id, [])
                if scenario.scenario_id not in scenarios_for_flag:
                    scenarios_for_flag.append(scenario.scenario_id)

            current_state = next_state

    # Uncovered rules.
    rules_uncovered = sorted(rid for rid in all_rule_ids if rid not in rules_covered)

    # Unvisited states.
    states_unvisited = set(all_state_ids - states_visited)

    return CoverageReport(
        rules_covered=rules_covered,
        rules_uncovered=rules_uncovered,
        states_visited=states_visited,
        states_unvisited=states_unvisited,
        transitions_exercised=transitions_exercised,
        flag_lifecycles=flag_lifecycles,
        category_distribution=category_distribution,
        total_scenarios=len(scenarios),
        total_steps=total_steps,
    )


def detect_gaps(
    report: CoverageReport,
    state_machine: StateMachine,
    *,
    excluded_states: set[str] | None = None,
) -> list[CoverageGap]:
    """Detect coverage gaps in a report.

    Checks for:
    - Rules with fewer than 2 scenarios
    - States never visited as next_state
    - Flags never set across all scenarios
    - Missing scenario categories

    Args:
        report: A coverage report to analyze.
        state_machine: The workflow state machine.
        excluded_states: States to exclude from unvisited-state gap detection
            (e.g., ACCESSIONING as implicit start, ORDER_TERMINATED as
            administrative-only terminal).

    Returns:
        List of coverage gaps found, or empty list if none.
    """
    gaps: list[CoverageGap] = []
    all_flag_ids = state_machine.get_all_flag_ids()
    skip_states = excluded_states or set()

    # Rules with < 2 scenarios.
    for rule_id in sorted(report.rules_covered):
        if len(report.rules_covered[rule_id]) < 2:
            gaps.append(
                CoverageGap(
                    gap_type="under_covered_rule",
                    detail=(
                        f"Rule {rule_id} has only {len(report.rules_covered[rule_id])} scenario(s)"
                    ),
                )
            )
    for rule_id in report.rules_uncovered:
        gaps.append(
            CoverageGap(
                gap_type="uncovered_rule",
                detail=f"Rule {rule_id} has zero scenario coverage",
            )
        )

    # States never visited.
    for state_id in sorted(report.states_unvisited):
        if state_id in skip_states:
            continue
        gaps.append(
            CoverageGap(
                gap_type="unvisited_state",
                detail=f"State {state_id} is never reached as next_state",
            )
        )

    # Flags never set.
    for flag_id in sorted(all_flag_ids):
        if flag_id not in report.flag_lifecycles:
            gaps.append(
                CoverageGap(
                    gap_type="unexercised_flag",
                    detail=f"Flag {flag_id} is never set in any scenario",
                )
            )

    # Missing categories.
    for category in sorted(VALID_CATEGORIES):
        if category not in report.category_distribution:
            gaps.append(
                CoverageGap(
                    gap_type="missing_category",
                    detail=f"Category '{category}' has zero scenarios",
                )
            )

    return gaps


def format_coverage_report(
    report: CoverageReport,
    state_machine: StateMachine,
) -> str:
    """Format a coverage report as human-readable text.

    Includes summary statistics, per-section details, and gap detection.

    Args:
        report: The coverage report to format.
        state_machine: The workflow state machine (for gap detection).

    Returns:
        Multi-line human-readable text report.
    """
    lines: list[str] = []
    all_rule_ids = state_machine.get_all_rule_ids()

    # Header.
    lines.append("=" * 60)
    lines.append("SCENARIO COVERAGE REPORT")
    lines.append("=" * 60)
    lines.append("")

    # Summary.
    lines.append("SUMMARY")
    lines.append("-" * 40)
    lines.append(f"Total scenarios: {report.total_scenarios}")
    lines.append(f"Total steps:     {report.total_steps}")
    lines.append(f"Rules covered:   {len(report.rules_covered)}/{len(all_rule_ids)}")
    lines.append(
        f"States visited:  {len(report.states_visited)}"
        f"/{len(report.states_visited) + len(report.states_unvisited)}"
    )
    lines.append(f"Flags exercised: {len(report.flag_lifecycles)}")
    lines.append("")

    # Category distribution.
    lines.append("CATEGORY DISTRIBUTION")
    lines.append("-" * 40)
    for category in sorted(report.category_distribution):
        lines.append(f"  {category}: {report.category_distribution[category]}")
    lines.append("")

    # Rule coverage detail.
    lines.append("RULE COVERAGE")
    lines.append("-" * 40)
    for rule_id in sorted(report.rules_covered):
        scenario_ids = report.rules_covered[rule_id]
        lines.append(f"  {rule_id}: {len(scenario_ids)} scenario(s)")
    if report.rules_uncovered:
        lines.append("")
        lines.append("  UNCOVERED RULES:")
        for rule_id in report.rules_uncovered:
            lines.append(f"    {rule_id}")
    lines.append("")

    # Flag coverage.
    lines.append("FLAG COVERAGE")
    lines.append("-" * 40)
    all_flag_ids = state_machine.get_all_flag_ids()
    for flag_id in sorted(all_flag_ids):
        if flag_id in report.flag_lifecycles:
            count = len(report.flag_lifecycles[flag_id])
            lines.append(f"  {flag_id}: {count} scenario(s)")
        else:
            lines.append(f"  {flag_id}: NOT EXERCISED")
    lines.append("")

    # Unvisited states.
    if report.states_unvisited:
        lines.append("UNVISITED STATES")
        lines.append("-" * 40)
        for state_id in sorted(report.states_unvisited):
            lines.append(f"  {state_id}")
        lines.append("")

    # Gap detection.
    gaps = detect_gaps(report, state_machine)
    if gaps:
        lines.append("COVERAGE GAPS")
        lines.append("-" * 40)
        for gap in gaps:
            lines.append(f"  [{gap.gap_type}] {gap.detail}")
        lines.append("")
    else:
        lines.append("No coverage gaps detected.")
        lines.append("")

    return "\n".join(lines)
