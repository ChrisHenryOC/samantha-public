"""Scenario flag-accumulation linter.

Detects when flags disappear between consecutive scenario steps without
a known clearing rule in ``applied_rules``.  This catches ground-truth
authoring mistakes where a flag is silently dropped instead of being
explicitly cleared.

Run standalone::

    uv run python -m src.simulator.lint_scenarios [--scenarios PATH]

Or call :func:`check_flag_consistency` programmatically from the
evaluation harness.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from src.simulator.loader import load_all_scenarios
from src.simulator.schema import Scenario

# ---------------------------------------------------------------------------
# Flag-clearing whitelist
# ---------------------------------------------------------------------------
# Maps each flag to the set of rule IDs that are known to clear it.
# Derived from knowledge_base/workflow_states.yaml ``cleared_by`` fields
# and confirmed against scenario ground truth.
#
# Flags not listed here (or with an empty set) will always trigger a
# warning when they disappear, because no rule is known to clear them.
FLAG_CLEARING_RULES: dict[str, frozenset[str]] = {
    "MISSING_INFO_PROCEED": frozenset({"RES-002"}),
    "FISH_SUGGESTED": frozenset({"IHC-008", "IHC-009"}),
    # No rule-based clearing; see FLAG_CLEARING_EVENTS for event-based:
    "FIXATION_WARNING": frozenset(),
    "RECUT_REQUESTED": frozenset(),
    "HER2_FIXATION_REJECT": frozenset(),
}

# Maps flags to event types that clear them. Some flags are cleared by
# workflow events rather than explicit rules — e.g., RECUT_REQUESTED is
# fulfilled when sectioning completes after a recut.
FLAG_CLEARING_EVENTS: dict[str, frozenset[str]] = {
    "RECUT_REQUESTED": frozenset({"sectioning_complete"}),
}


@dataclass(frozen=True)
class FlagLintWarning:
    """A single flag-consistency warning found in a scenario."""

    scenario_id: str
    step: int
    flag: str
    message: str


def check_flag_consistency(scenario: Scenario) -> list[FlagLintWarning]:
    """Check a scenario for unexplained flag disappearances.

    Walks consecutive step pairs and reports any flag that was present
    at step *N* but absent at step *N+1* without a known clearing rule
    in the later step's ``applied_rules``.

    Args:
        scenario: The routing scenario to lint.

    Returns:
        List of warnings (empty if the scenario is clean).
    """
    warnings: list[FlagLintWarning] = []

    for i in range(len(scenario.steps) - 1):
        prev_step = scenario.steps[i]
        next_step = scenario.steps[i + 1]

        prev_flags = set(prev_step.expected_output.flags)
        next_flags = set(next_step.expected_output.flags)
        applied_rules = set(next_step.expected_output.applied_rules)

        disappeared = prev_flags - next_flags
        for flag in sorted(disappeared):
            clearing_rules = FLAG_CLEARING_RULES.get(flag, frozenset())
            clearing_events = FLAG_CLEARING_EVENTS.get(flag, frozenset())

            # Check rule-based clearing first, then event-based.
            if clearing_rules & applied_rules:
                continue
            if next_step.event_type in clearing_events:
                continue

            if clearing_rules or clearing_events:
                expected_parts: list[str] = []
                if clearing_rules:
                    expected_parts.append(f"rules {sorted(clearing_rules)}")
                if clearing_events:
                    expected_parts.append(f"events {sorted(clearing_events)}")
                detail = (
                    f"Flag '{flag}' disappeared at step {next_step.step} "
                    f"without a clearing mechanism. Expected "
                    f"{' or '.join(expected_parts)}, "
                    f"got rules {sorted(applied_rules)} "
                    f"event '{next_step.event_type}'."
                )
            else:
                detail = (
                    f"Flag '{flag}' disappeared at step {next_step.step} "
                    f"and has no known clearing rules or events."
                )
            warnings.append(
                FlagLintWarning(
                    scenario_id=scenario.scenario_id,
                    step=next_step.step,
                    flag=flag,
                    message=detail,
                )
            )

    return warnings


def lint_scenarios(scenarios: Sequence[Scenario]) -> list[FlagLintWarning]:
    """Lint multiple scenarios for flag-consistency issues.

    Args:
        scenarios: Routing scenarios to check.

    Returns:
        All warnings across all scenarios.
    """
    warnings: list[FlagLintWarning] = []
    for scenario in scenarios:
        warnings.extend(check_flag_consistency(scenario))
    return warnings


# ---------------------------------------------------------------------------
# Scenario directory constants
# ---------------------------------------------------------------------------
_DEFAULT_SCENARIO_DIRS: tuple[str, ...] = (
    "rule_coverage",
    "multi_rule",
    "accumulated_state",
    "unknown_input",
    "hallucination",
)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for the scenario flag linter.

    Returns:
        0 if no warnings, 1 if warnings were found.
    """
    parser = argparse.ArgumentParser(
        description="Lint routing scenarios for flag-accumulation inconsistencies.",
    )
    parser.add_argument(
        "--scenarios",
        type=Path,
        default=Path("scenarios"),
        help="Root scenarios directory (default: scenarios/)",
    )
    args = parser.parse_args(argv)

    scenarios_root: Path = args.scenarios

    all_scenarios: list[Scenario] = []
    for subdir in _DEFAULT_SCENARIO_DIRS:
        dir_path = scenarios_root / subdir
        if dir_path.exists():
            try:
                all_scenarios.extend(load_all_scenarios(dir_path))
            except (ValueError, TypeError) as exc:
                print(f"Error loading scenarios from {dir_path}: {exc}")
                return 1

    if not all_scenarios:
        print(f"No scenarios found under {scenarios_root}")
        return 1

    all_scenarios.sort(key=lambda s: s.scenario_id)
    warnings = lint_scenarios(all_scenarios)

    if not warnings:
        print(f"OK — {len(all_scenarios)} scenarios checked, no flag issues found.")
        return 0

    print(f"Found {len(warnings)} flag warning(s) in {len(all_scenarios)} scenarios:\n")
    for w in warnings:
        print(f"  [{w.scenario_id}] step {w.step}: {w.message}")
    print()
    return 1


if __name__ == "__main__":
    sys.exit(main())
