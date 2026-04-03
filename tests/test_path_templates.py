"""Tests for workflow path templates.

Validates that all 21 path templates (PT-001 through PT-021) assemble
correctly, pass scenario validation, and exercise the expected rules
and terminal states.
"""

from __future__ import annotations

import pytest

from src.simulator.event_builder import (
    build_embedding_complete,
    build_grossing_complete,
    build_processing_complete,
    build_sectioning_complete,
)
from src.simulator.order_generator import STANDARD_INVASIVE
from src.simulator.path_templates import (
    _EQUIVOCAL_IHC_SCORES,
    _INVASIVE_REPORTABLE,
    _STANDARD_IHC_SCORES,
    ALL_TEMPLATES,
    _accessioning_accept,
    _fish_approved,
    _fish_result_to_resulting,
    _he_qc_pass,
    _he_staining_to_qc,
    _ihc_fixation_reject,
    _ihc_qc_fail_retry,
    _ihc_qc_pass,
    _ihc_scoring_complete,
    _ihc_scoring_equivocal,
    _ihc_staining_to_qc,
    _make_step_dict,
    _pathologist_he_review_invasive,
    _resulting_no_flags,
    _sample_prep_linear,
    _sample_prep_processing_retry,
    _sample_prep_qc_pass,
    _signout_and_complete,
    accessioning_reject,
    assemble_scenario,
    fish_external_qns,
    happy_path_benign,
    happy_path_dcis,
    happy_path_invasive,
    he_qc_fail_qns,
    he_qc_recut,
    he_qc_restain,
    ihc_fixation_reject,
    ihc_her2_equivocal_fish_approved,
    ihc_her2_equivocal_fish_declined,
    ihc_qc_slides_pending,
    ihc_qc_staining_fail_qns,
    ihc_qc_staining_fail_retry,
    missing_billing_hold_at_resulting,
    missing_info_hold_then_resolve,
    pathologist_requests_recuts,
    pathologist_suspicious_ihc,
    sample_prep_failure_qns,
    sample_prep_processing_retry,
    sample_prep_qc_fail_retry,
)
from src.simulator.scenario_validator import validate_scenario
from src.simulator.schema import Scenario
from src.workflow.state_machine import StateMachine


@pytest.fixture()
def state_machine() -> StateMachine:
    return StateMachine.get_instance()


# ── Helpers ───────────────────────────────────────────────────────


def _all_applied_rules(scenario: Scenario) -> set[str]:
    """Collect all applied rule IDs across every step."""
    rules: set[str] = set()
    for step in scenario.steps:
        rules.update(step.expected_output.applied_rules)
    return rules


def _terminal_state(scenario: Scenario) -> str:
    """Get next_state from the last step."""
    return scenario.steps[-1].expected_output.next_state


def _all_flags(scenario: Scenario) -> set[str]:
    """Collect all flags set across every step."""
    flags: set[str] = set()
    for step in scenario.steps:
        flags.update(step.expected_output.flags)
    return flags


# ── All templates validate ────────────────────────────────────────


class TestAllTemplatesValidate:
    """Every template assembles and validates with zero errors."""

    def test_template_count(self) -> None:
        assert len(ALL_TEMPLATES) == 21

    def test_unique_scenario_ids(self) -> None:
        ids = {fn().scenario_id for fn in ALL_TEMPLATES}
        assert len(ids) == 21

    @pytest.mark.parametrize(
        "template_fn",
        ALL_TEMPLATES,
        ids=[fn.__name__ for fn in ALL_TEMPLATES],
    )
    def test_template_validates(self, template_fn: object, state_machine: StateMachine) -> None:
        scenario = template_fn()  # type: ignore[operator]
        errors = validate_scenario(scenario, state_machine)
        assert errors == [], f"{scenario.scenario_id} validation errors:\n" + "\n".join(
            f"  Step {e.step_number}: [{e.error_type}] {e.message}" for e in errors
        )


# ── HE-004: H&E QC fails, insufficient tissue ────────────────────


class TestHE004:
    """PT-012: H&E QC fail_qns → ORDER_TERMINATED_QNS."""

    def test_terminal_state(self) -> None:
        s = he_qc_fail_qns()
        assert _terminal_state(s) == "ORDER_TERMINATED_QNS"

    def test_applies_he004(self) -> None:
        s = he_qc_fail_qns()
        assert "HE-004" in _all_applied_rules(s)

    def test_qns_outcome_in_event_data(self) -> None:
        s = he_qc_fail_qns()
        qns_step = next(step for step in s.steps if "HE-004" in step.expected_output.applied_rules)
        assert qns_step.event_data["outcome"] == "fail_qns"


# ── HE-007: Suspicious/atypical diagnosis ─────────────────────────


class TestHE007:
    """PT-013: Suspicious/atypical → IHC → ORDER_COMPLETE."""

    def test_terminal_state(self) -> None:
        s = pathologist_suspicious_ihc()
        assert _terminal_state(s) == "ORDER_COMPLETE"

    def test_applies_he007(self) -> None:
        s = pathologist_suspicious_ihc()
        assert "HE-007" in _all_applied_rules(s)

    def test_suspicious_diagnosis_in_event_data(self) -> None:
        s = pathologist_suspicious_ihc()
        review_step = next(
            step for step in s.steps if "HE-007" in step.expected_output.applied_rules
        )
        assert review_step.event_data["diagnosis"] == "suspicious_atypical"

    def test_suspicious_routes_to_ihc(self) -> None:
        s = pathologist_suspicious_ihc()
        he_review_steps = [step for step in s.steps if step.event_type == "pathologist_he_review"]
        assert len(he_review_steps) == 1
        assert he_review_steps[0].expected_output.next_state == "IHC_STAINING"


# ── HE-009: Pathologist requests recuts ───────────────────────────


class TestHE009:
    """PT-014: Pathologist recut → SAMPLE_PREP_SECTIONING → recovery → complete."""

    def test_terminal_state(self) -> None:
        s = pathologist_requests_recuts()
        assert _terminal_state(s) == "ORDER_COMPLETE"

    def test_applies_he009(self) -> None:
        s = pathologist_requests_recuts()
        assert "HE-009" in _all_applied_rules(s)

    def test_recut_requested_flag_set(self) -> None:
        s = pathologist_requests_recuts()
        assert "RECUT_REQUESTED" in _all_flags(s)

    def test_recut_diagnosis_in_event_data(self) -> None:
        s = pathologist_requests_recuts()
        recut_step = next(
            step for step in s.steps if "HE-009" in step.expected_output.applied_rules
        )
        assert recut_step.event_data["diagnosis"] == "recut_requested"

    def test_recut_routes_to_sectioning(self) -> None:
        s = pathologist_requests_recuts()
        recut_steps = [step for step in s.steps if "HE-009" in step.expected_output.applied_rules]
        assert len(recut_steps) == 1
        assert recut_steps[0].expected_output.next_state == "SAMPLE_PREP_SECTIONING"


# ── SP-002: Step failed, tissue available → retry ─────────────────


class TestSP002:
    """PT-015: Processing fails → retry → succeed → ORDER_COMPLETE."""

    def test_terminal_state(self) -> None:
        s = sample_prep_processing_retry()
        assert _terminal_state(s) == "ORDER_COMPLETE"

    def test_applies_sp002(self) -> None:
        s = sample_prep_processing_retry()
        assert "SP-002" in _all_applied_rules(s)

    def test_retry_is_self_loop(self) -> None:
        s = sample_prep_processing_retry()
        retry_steps = [step for step in s.steps if "SP-002" in step.expected_output.applied_rules]
        assert len(retry_steps) == 1
        assert retry_steps[0].expected_output.next_state == "SAMPLE_PREP_PROCESSING"


# ── SP-005: Sample prep QC fails, tissue available → retry ────────


class TestSP005:
    """PT-016: Sample prep QC fails → retry sectioning → ORDER_COMPLETE."""

    def test_terminal_state(self) -> None:
        s = sample_prep_qc_fail_retry()
        assert _terminal_state(s) == "ORDER_COMPLETE"

    def test_applies_sp005(self) -> None:
        s = sample_prep_qc_fail_retry()
        assert "SP-005" in _all_applied_rules(s)

    def test_retry_routes_to_sectioning(self) -> None:
        s = sample_prep_qc_fail_retry()
        retry_steps = [step for step in s.steps if "SP-005" in step.expected_output.applied_rules]
        assert len(retry_steps) == 1
        assert retry_steps[0].expected_output.next_state == "SAMPLE_PREP_SECTIONING"


# ── IHC-001: HER2 fixation reject ────────────────────────────────


class TestIHC001:
    """PT-017: HER2 fixation reject → self-loop → retry → ORDER_COMPLETE."""

    def test_terminal_state(self) -> None:
        s = ihc_fixation_reject()
        assert _terminal_state(s) == "ORDER_COMPLETE"

    def test_applies_ihc001(self) -> None:
        s = ihc_fixation_reject()
        assert "IHC-001" in _all_applied_rules(s)

    def test_fixation_reject_outcome_in_event_data(self) -> None:
        s = ihc_fixation_reject()
        reject_step = next(
            step for step in s.steps if "IHC-001" in step.expected_output.applied_rules
        )
        assert reject_step.event_data["outcome"] == "fixation_reject"

    def test_her2_fixation_reject_flag(self) -> None:
        s = ihc_fixation_reject()
        assert "HER2_FIXATION_REJECT" in _all_flags(s)

    def test_fixation_reject_is_self_loop(self) -> None:
        s = ihc_fixation_reject()
        reject_steps = [step for step in s.steps if "IHC-001" in step.expected_output.applied_rules]
        assert len(reject_steps) == 1
        assert reject_steps[0].expected_output.next_state == "IHC_STAINING"


# ── IHC-003: Slides pending ──────────────────────────────────────


class TestIHC003:
    """PT-018: IHC QC slides pending → hold → all pass → ORDER_COMPLETE."""

    def test_terminal_state(self) -> None:
        s = ihc_qc_slides_pending()
        assert _terminal_state(s) == "ORDER_COMPLETE"

    def test_applies_ihc003(self) -> None:
        s = ihc_qc_slides_pending()
        assert "IHC-003" in _all_applied_rules(s)

    def test_slides_pending_is_self_loop(self) -> None:
        s = ihc_qc_slides_pending()
        pending_steps = [
            step for step in s.steps if "IHC-003" in step.expected_output.applied_rules
        ]
        assert len(pending_steps) == 1
        assert pending_steps[0].expected_output.next_state == "IHC_QC"


# ── IHC-004: Staining failed, retry ──────────────────────────────


class TestIHC004:
    """PT-019: IHC staining failed → retry → ORDER_COMPLETE."""

    def test_terminal_state(self) -> None:
        s = ihc_qc_staining_fail_retry()
        assert _terminal_state(s) == "ORDER_COMPLETE"

    def test_applies_ihc004(self) -> None:
        s = ihc_qc_staining_fail_retry()
        assert "IHC-004" in _all_applied_rules(s)

    def test_fail_routes_to_ihc_staining(self) -> None:
        s = ihc_qc_staining_fail_retry()
        fail_steps = [step for step in s.steps if "IHC-004" in step.expected_output.applied_rules]
        assert len(fail_steps) == 1
        assert fail_steps[0].expected_output.next_state == "IHC_STAINING"


# ── IHC-005: Staining failed, QNS ────────────────────────────────


class TestIHC005:
    """PT-020: IHC staining failed QNS → ORDER_TERMINATED_QNS."""

    def test_terminal_state(self) -> None:
        s = ihc_qc_staining_fail_qns()
        assert _terminal_state(s) == "ORDER_TERMINATED_QNS"

    def test_applies_ihc005(self) -> None:
        s = ihc_qc_staining_fail_qns()
        assert "IHC-005" in _all_applied_rules(s)


# ── IHC-011: FISH external QNS ───────────────────────────────────


class TestIHC011:
    """PT-021: FISH external lab QNS → ORDER_TERMINATED_QNS."""

    def test_terminal_state(self) -> None:
        s = fish_external_qns()
        assert _terminal_state(s) == "ORDER_TERMINATED_QNS"

    def test_applies_ihc011(self) -> None:
        s = fish_external_qns()
        assert "IHC-011" in _all_applied_rules(s)

    def test_qns_result_in_event_data(self) -> None:
        s = fish_external_qns()
        qns_step = next(step for step in s.steps if "IHC-011" in step.expected_output.applied_rules)
        assert qns_step.event_data["result"] == "qns"

    def test_fish_suggested_flag(self) -> None:
        """FISH pathway sets FISH_SUGGESTED flag at equivocal scoring."""
        s = fish_external_qns()
        assert "FISH_SUGGESTED" in _all_flags(s)


# ── Cross-cutting: all original templates still work ──────────────


class TestOriginalTemplatesUnchanged:
    """Existing templates still produce the same terminal states."""

    @pytest.mark.parametrize(
        "template_fn,expected_terminal",
        [
            (happy_path_invasive, "ORDER_COMPLETE"),
            (happy_path_benign, "ORDER_COMPLETE"),
            (happy_path_dcis, "ORDER_COMPLETE"),
            (sample_prep_failure_qns, "ORDER_TERMINATED_QNS"),
            (he_qc_restain, "ORDER_COMPLETE"),
            (he_qc_recut, "ORDER_COMPLETE"),
            (ihc_her2_equivocal_fish_approved, "ORDER_COMPLETE"),
            (ihc_her2_equivocal_fish_declined, "ORDER_COMPLETE"),
            (missing_info_hold_then_resolve, "ORDER_COMPLETE"),
            (missing_billing_hold_at_resulting, "ORDER_COMPLETE"),
            (accessioning_reject, "DO_NOT_PROCESS"),
        ],
        ids=lambda v: v.__name__ if callable(v) else v,
    )
    def test_terminal_state(self, template_fn: object, expected_terminal: str) -> None:
        scenario = template_fn()  # type: ignore[operator]
        assert _terminal_state(scenario) == expected_terminal


# ── Multi-retry self-loop tests ──────────────────────────────────


class TestMultipleRetryCycles:
    """Verify the state machine accepts multiple consecutive self-loop retries."""

    def test_double_processing_retry(self) -> None:
        """Processing fails twice before succeeding (SP-002 x2)."""
        steps = [
            *_accessioning_accept(STANDARD_INVASIVE, 100),
            _make_step_dict(
                build_grossing_complete(),
                next_state="SAMPLE_PREP_PROCESSING",
                applied_rules=("SP-001",),
            ),
            # First failure → self-loop
            *_sample_prep_processing_retry(),
            # Second failure → self-loop again
            *_sample_prep_processing_retry(),
            # Third attempt succeeds
            _make_step_dict(
                build_processing_complete(),
                next_state="SAMPLE_PREP_EMBEDDING",
                applied_rules=("SP-001",),
            ),
            _make_step_dict(
                build_embedding_complete(),
                next_state="SAMPLE_PREP_SECTIONING",
                applied_rules=("SP-001",),
            ),
            _make_step_dict(
                build_sectioning_complete(),
                next_state="SAMPLE_PREP_QC",
                applied_rules=("SP-001",),
            ),
            *_sample_prep_qc_pass(),
            *_he_staining_to_qc(),
            *_he_qc_pass(),
            *_pathologist_he_review_invasive(),
            *_ihc_staining_to_qc(),
            *_ihc_qc_pass(),
            *_ihc_scoring_complete(_STANDARD_IHC_SCORES),
            *_resulting_no_flags(),
            *_signout_and_complete(_INVASIVE_REPORTABLE),
        ]
        scenario = assemble_scenario(
            scenario_id="SC-901",
            category="multi_rule",
            description="Double processing retry (SP-002 x2)",
            steps=steps,
        )
        assert _terminal_state(scenario) == "ORDER_COMPLETE"
        rules = _all_applied_rules(scenario)
        assert "SP-002" in rules
        sp002_steps = [s for s in scenario.steps if "SP-002" in s.expected_output.applied_rules]
        assert len(sp002_steps) == 2

    def test_double_ihc_fixation_reject(self) -> None:
        """IHC fixation rejected twice before succeeding (IHC-001 x2)."""
        steps = [
            *_accessioning_accept(STANDARD_INVASIVE, 101),
            *_sample_prep_linear(),
            *_sample_prep_qc_pass(),
            *_he_staining_to_qc(),
            *_he_qc_pass(),
            *_pathologist_he_review_invasive(),
            # First fixation reject → self-loop
            *_ihc_fixation_reject(),
            # Second fixation reject → self-loop again
            *_ihc_fixation_reject(),
            # Third attempt succeeds
            *_ihc_staining_to_qc(),
            *_ihc_qc_pass(),
            *_ihc_scoring_complete(_STANDARD_IHC_SCORES),
            *_resulting_no_flags(),
            *_signout_and_complete(_INVASIVE_REPORTABLE),
        ]
        scenario = assemble_scenario(
            scenario_id="SC-902",
            category="multi_rule",
            description="Double IHC fixation reject (IHC-001 x2)",
            steps=steps,
        )
        assert _terminal_state(scenario) == "ORDER_COMPLETE"
        ihc001_steps = [s for s in scenario.steps if "IHC-001" in s.expected_output.applied_rules]
        assert len(ihc001_steps) == 2

    def test_double_ihc_qc_staining_fail(self) -> None:
        """IHC QC staining fails twice before succeeding (IHC-004 x2)."""
        steps = [
            *_accessioning_accept(STANDARD_INVASIVE, 102),
            *_sample_prep_linear(),
            *_sample_prep_qc_pass(),
            *_he_staining_to_qc(),
            *_he_qc_pass(),
            *_pathologist_he_review_invasive(),
            *_ihc_staining_to_qc(),
            # First staining fail → back to IHC_STAINING
            *_ihc_qc_fail_retry(),
            *_ihc_staining_to_qc(),
            # Second staining fail → back to IHC_STAINING again
            *_ihc_qc_fail_retry(),
            # Third attempt succeeds
            *_ihc_staining_to_qc(),
            *_ihc_qc_pass(),
            *_ihc_scoring_complete(_STANDARD_IHC_SCORES),
            *_resulting_no_flags(),
            *_signout_and_complete(_INVASIVE_REPORTABLE),
        ]
        scenario = assemble_scenario(
            scenario_id="SC-903",
            category="multi_rule",
            description="Double IHC staining fail retry (IHC-004 x2)",
            steps=steps,
        )
        assert _terminal_state(scenario) == "ORDER_COMPLETE"
        ihc004_steps = [s for s in scenario.steps if "IHC-004" in s.expected_output.applied_rules]
        assert len(ihc004_steps) == 2


# ── Cross-template flag accumulation tests ────────────────────────


class TestFlagAccumulation:
    """Verify correct flag behavior when multiple flag-setting rules fire."""

    def test_fixation_reject_then_fish_suggested(self) -> None:
        """Path with HER2_FIXATION_REJECT and FISH_SUGGESTED flags."""
        steps = [
            *_accessioning_accept(STANDARD_INVASIVE, 103),
            *_sample_prep_linear(),
            *_sample_prep_qc_pass(),
            *_he_staining_to_qc(),
            *_he_qc_pass(),
            *_pathologist_he_review_invasive(),
            # Fixation reject sets HER2_FIXATION_REJECT
            *_ihc_fixation_reject(),
            # Retry succeeds
            *_ihc_staining_to_qc(),
            *_ihc_qc_pass(),
            # Equivocal scoring sets FISH_SUGGESTED
            *_ihc_scoring_equivocal(_EQUIVOCAL_IHC_SCORES),
            *_fish_approved(),
            *_fish_result_to_resulting(),
            *_resulting_no_flags(),
            *_signout_and_complete(_INVASIVE_REPORTABLE),
        ]
        scenario = assemble_scenario(
            scenario_id="SC-904",
            category="multi_rule",
            description="Fixation reject + FISH suggested flags in one path",
            steps=steps,
        )
        flags = _all_flags(scenario)
        assert "HER2_FIXATION_REJECT" in flags
        assert "FISH_SUGGESTED" in flags
        assert _terminal_state(scenario) == "ORDER_COMPLETE"
