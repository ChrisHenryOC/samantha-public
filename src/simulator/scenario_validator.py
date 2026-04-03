"""Scenario ground-truth consistency checker.

Validates that scenario files are internally consistent with the state
machine: transitions follow valid paths, rules exist and are applicable,
flags respect their lifecycle, and event types match expected states.

This validates scenario FILES (ground truth). For validating model OUTPUT
against ground truth, see ``src/workflow/validator.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.simulator.schema import Scenario
from src.workflow.state_machine import StateMachine

# Event types expected at each state. All values are frozensets of valid
# states. Events not listed here are not constrained (e.g.,
# missing_info_received can occur at MISSING_INFO_HOLD or RESULTING_HOLD).
_EVENT_STATE_MAP: dict[str, frozenset[str]] = {
    "order_received": frozenset({"ACCESSIONING"}),
    "grossing_complete": frozenset({"ACCEPTED", "MISSING_INFO_PROCEED"}),
    "processing_complete": frozenset({"SAMPLE_PREP_PROCESSING"}),
    "embedding_complete": frozenset({"SAMPLE_PREP_EMBEDDING"}),
    "sectioning_complete": frozenset({"SAMPLE_PREP_SECTIONING"}),
    "sample_prep_qc": frozenset({"SAMPLE_PREP_QC"}),
    "he_staining_complete": frozenset({"HE_STAINING"}),
    "he_qc": frozenset({"HE_QC"}),
    "pathologist_he_review": frozenset({"PATHOLOGIST_HE_REVIEW"}),
    "ihc_staining_complete": frozenset({"IHC_STAINING"}),
    "ihc_qc": frozenset({"IHC_QC"}),
    "ihc_scoring": frozenset({"IHC_SCORING"}),
    "fish_decision": frozenset({"SUGGEST_FISH_REFLEX"}),
    "fish_result": frozenset({"FISH_SEND_OUT"}),
    "resulting_review": frozenset({"RESULTING"}),
    "pathologist_signout": frozenset({"PATHOLOGIST_SIGNOUT"}),
    "report_generated": frozenset({"REPORT_GENERATION"}),
}

# Severity hierarchy for accessioning rules. Lower rank = higher severity.
# REJECT (0) is the highest severity, ACCEPT (3) is the lowest.
# See docs/workflow/accessioning-logic.md.
_SEVERITY_RANK: dict[str, int] = {
    "REJECT": 0,
    "HOLD": 1,
    "PROCEED": 2,
    "ACCEPT": 3,
}

# Fallback rank for rules with unknown or missing severity.
_UNKNOWN_SEVERITY_RANK = 99

# State that each accessioning severity resolves to.
# See docs/workflow/accessioning-logic.md.
_SEVERITY_STATE: dict[str, str] = {
    "REJECT": "DO_NOT_PROCESS",
    "HOLD": "MISSING_INFO_HOLD",
    "PROCEED": "MISSING_INFO_PROCEED",
    "ACCEPT": "ACCEPTED",
}


@dataclass(frozen=True)
class ScenarioValidationError:
    """A single validation error found in a scenario."""

    scenario_id: str
    step_number: int | None
    error_type: str
    message: str


def validate_scenario(
    scenario: Scenario,
    state_machine: StateMachine,
    *,
    _all_rule_ids: frozenset[str] | None = None,
    _all_flag_ids: frozenset[str] | None = None,
    _flag_vocab: dict[str, dict[str, Any]] | None = None,
) -> list[ScenarioValidationError]:
    """Validate a scenario's ground truth against the state machine.

    Returns ALL errors found (not just the first). Each error is
    independently actionable with clear context.

    Args:
        scenario: The scenario to validate.
        state_machine: The workflow state machine to validate against.
        _all_rule_ids: Pre-fetched rule IDs (used by batch validation).
        _all_flag_ids: Pre-fetched flag IDs (used by batch validation).
        _flag_vocab: Pre-fetched flag vocabulary (used by batch validation).

    Returns:
        All validation errors found, or an empty list if the scenario
        is consistent with the state machine.
    """
    errors: list[ScenarioValidationError] = []
    all_rule_ids = _all_rule_ids or state_machine.get_all_rule_ids()
    all_flag_ids = _all_flag_ids or state_machine.get_all_flag_ids()
    flag_vocab = _flag_vocab or state_machine.get_flag_vocabulary()

    # Check 1: First event must be order_received.
    # (Also enforced by Scenario.__post_init__, but we check here for
    # completeness in case the validator is used on raw data.)
    if scenario.steps[0].event_type != "order_received":
        errors.append(
            ScenarioValidationError(
                scenario_id=scenario.scenario_id,
                step_number=None,
                error_type="first_event",
                message=(
                    f"First step event_type must be 'order_received', "
                    f"got '{scenario.steps[0].event_type}'"
                ),
            )
        )

    # Walk through each step, tracking current state and active flags.
    # Before step 1, the implicit current state is ACCESSIONING.
    current_state = "ACCESSIONING"
    prev_flags: frozenset[str] = frozenset()

    for step in scenario.steps:
        step_num = step.step
        next_state = step.expected_output.next_state

        # Check 2: Transition validity.
        if not state_machine.is_valid_transition(current_state, next_state):
            errors.append(
                ScenarioValidationError(
                    scenario_id=scenario.scenario_id,
                    step_number=step_num,
                    error_type="invalid_transition",
                    message=(f"Invalid transition from '{current_state}' to '{next_state}'"),
                )
            )

        # Check 3: Rule existence.
        for rule_id in step.expected_output.applied_rules:
            if rule_id not in all_rule_ids:
                errors.append(
                    ScenarioValidationError(
                        scenario_id=scenario.scenario_id,
                        step_number=step_num,
                        error_type="rule_not_found",
                        message=f"Rule '{rule_id}' does not exist in the rule catalog",
                    )
                )

        # Check 4: Rule applicability.
        applicable_rules = state_machine.get_rules_for_state(current_state)
        applicable_rule_ids = {r.rule_id for r in applicable_rules}
        for rule_id in step.expected_output.applied_rules:
            if rule_id in all_rule_ids and rule_id not in applicable_rule_ids:
                errors.append(
                    ScenarioValidationError(
                        scenario_id=scenario.scenario_id,
                        step_number=step_num,
                        error_type="rule_not_applicable",
                        message=(f"Rule '{rule_id}' is not applicable at state '{current_state}'"),
                    )
                )

        # Check 5: Flag existence.
        for flag_id in step.expected_output.flags:
            if flag_id not in all_flag_ids:
                errors.append(
                    ScenarioValidationError(
                        scenario_id=scenario.scenario_id,
                        step_number=step_num,
                        error_type="flag_not_found",
                        message=f"Flag '{flag_id}' does not exist in the flag vocabulary",
                    )
                )

        # Check 6: Flag lifecycle — newly added flags must be set at states
        # where they are defined to be set_at. Flags carried forward from
        # a previous step are allowed at any state.
        current_flags = frozenset(step.expected_output.flags)
        newly_added = current_flags - prev_flags
        for flag_id in newly_added:
            if flag_id in flag_vocab:
                valid_set_at = flag_vocab[flag_id]["set_at"]
                if current_state not in valid_set_at and not _state_matches_set_at(
                    current_state, valid_set_at, state_machine
                ):
                    errors.append(
                        ScenarioValidationError(
                            scenario_id=scenario.scenario_id,
                            step_number=step_num,
                            error_type="flag_wrong_state",
                            message=(
                                f"Flag '{flag_id}' can only be set at "
                                f"{valid_set_at}, but current state is "
                                f"'{current_state}'"
                            ),
                        )
                    )

        # Check 7: State reachability — implicitly covered by check 2
        # (transition validity) applied at every step. The walk from
        # ACCESSIONING through each step's next_state ensures the full
        # chain is reachable.

        # Check 8: Terminal state handling — no steps should follow a
        # terminal state.
        if state_machine.is_terminal_state(current_state):
            errors.append(
                ScenarioValidationError(
                    scenario_id=scenario.scenario_id,
                    step_number=step_num,
                    error_type="step_after_terminal",
                    message=(f"Step {step_num} follows terminal state '{current_state}'"),
                )
            )

        # Check 9: Event-state consistency.
        valid_states = _EVENT_STATE_MAP.get(step.event_type)
        if valid_states is not None and current_state not in valid_states:
            errors.append(
                ScenarioValidationError(
                    scenario_id=scenario.scenario_id,
                    step_number=step_num,
                    error_type="event_state_mismatch",
                    message=(
                        f"Event '{step.event_type}' expects state "
                        f"in {sorted(valid_states)}, but current "
                        f"state is '{current_state}'"
                    ),
                )
            )

        # Check 10: Accessioning severity — when accessioning rules fire,
        # next_state must reflect the highest-severity rule.
        if current_state == "ACCESSIONING" and len(step.expected_output.applied_rules) >= 1:
            acc_rules = [
                r for r in applicable_rules if r.rule_id in step.expected_output.applied_rules
            ]
            if acc_rules:
                highest_severity = min(
                    acc_rules,
                    key=lambda r: _SEVERITY_RANK.get(r.severity or "", _UNKNOWN_SEVERITY_RANK),
                )
                expected_acc_state = _SEVERITY_STATE.get(highest_severity.severity or "")
                if expected_acc_state and next_state != expected_acc_state:
                    errors.append(
                        ScenarioValidationError(
                            scenario_id=scenario.scenario_id,
                            step_number=step_num,
                            error_type="accessioning_severity_mismatch",
                            message=(
                                f"Accessioning rule severity mismatch; "
                                f"highest severity is "
                                f"'{highest_severity.severity}' "
                                f"(rule {highest_severity.rule_id}) which "
                                f"requires state '{expected_acc_state}', "
                                f"but next_state is '{next_state}'"
                            ),
                        )
                    )

        # Advance current state and track flags for next step.
        current_state = next_state
        prev_flags = current_flags

    return errors


def _state_matches_set_at(
    current_state: str,
    set_at_values: list[str],
    state_machine: StateMachine,
) -> bool:
    """Check if the current state belongs to a phase listed in set_at.

    The flag vocabulary's ``set_at`` can reference either specific states
    (e.g., ``ACCESSIONING``, ``PATHOLOGIST_HE_REVIEW``, ``IHC_SCORING``)
    or broad phase names (e.g., ``IHC``). For phase names, we check
    whether the current state has rules from that step.

    This function is only called when the direct state match has already
    failed (the caller checks ``current_state not in valid_set_at``
    first), so it focuses on phase-level matching.

    Args:
        current_state: The current workflow state.
        set_at_values: The ``set_at`` list from the flag vocabulary.
        state_machine: The workflow state machine for rule lookups.

    Returns:
        True if the current state matches any phase in set_at_values.
    """
    rules_for_state = state_machine.get_rules_for_state(current_state)
    return any(any(r.step == phase for r in rules_for_state) for phase in set_at_values)


def validate_all_scenarios(
    scenarios: list[Scenario],
    state_machine: StateMachine,
) -> list[ScenarioValidationError]:
    """Validate multiple scenarios and return all errors combined.

    Pre-fetches state machine indexes once for efficiency rather than
    re-fetching them per scenario.

    Args:
        scenarios: The scenarios to validate.
        state_machine: The workflow state machine to validate against.

    Returns:
        All validation errors across all scenarios, or an empty list
        if all scenarios are consistent.
    """
    all_rule_ids = state_machine.get_all_rule_ids()
    all_flag_ids = state_machine.get_all_flag_ids()
    flag_vocab = state_machine.get_flag_vocabulary()

    errors: list[ScenarioValidationError] = []
    for scenario in scenarios:
        errors.extend(
            validate_scenario(
                scenario,
                state_machine,
                _all_rule_ids=all_rule_ids,
                _all_flag_ids=all_flag_ids,
                _flag_vocab=flag_vocab,
            )
        )
    return errors
