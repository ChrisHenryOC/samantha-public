"""Tests for event_builder and path_templates modules."""

from __future__ import annotations

import pytest

from src.simulator.event_builder import (
    VALID_DIAGNOSES,
    VALID_FISH_RESULTS,
    VALID_HE_QC_OUTCOMES,
    VALID_IHC_QC_OUTCOMES,
    VALID_RESULTING_REVIEW_OUTCOMES,
    VALID_SAMPLE_PREP_QC_OUTCOMES,
    build_embedding_complete,
    build_fish_decision,
    build_fish_result,
    build_grossing_complete,
    build_he_qc,
    build_he_staining_complete,
    build_ihc_qc,
    build_ihc_scoring,
    build_ihc_staining_complete,
    build_missing_info_received,
    build_order_received,
    build_pathologist_he_review,
    build_pathologist_signout,
    build_processing_complete,
    build_report_generated,
    build_resulting_review,
    build_sample_prep_qc,
    build_sectioning_complete,
)
from src.simulator.order_generator import STANDARD_INVASIVE
from src.simulator.path_templates import (
    ALL_TEMPLATES,
    accessioning_reject,
    assemble_scenario,
    happy_path_benign,
    happy_path_dcis,
    happy_path_invasive,
    he_qc_recut,
    he_qc_restain,
    ihc_her2_equivocal_fish_approved,
    ihc_her2_equivocal_fish_declined,
    missing_billing_hold_at_resulting,
    missing_info_hold_then_resolve,
    sample_prep_failure_qns,
)
from src.simulator.scenario_validator import validate_scenario
from src.simulator.schema import VALID_EVENT_TYPES, Scenario
from src.workflow.state_machine import StateMachine

# ── TestEventFactoryStructure ───────────────────────────────────────


class TestEventFactoryStructure:
    """All factories return {"event_type": str, "event_data": dict}."""

    @pytest.mark.parametrize(
        "factory_call",
        [
            lambda: build_order_received(STANDARD_INVASIVE, 0),
            lambda: build_grossing_complete(),
            lambda: build_processing_complete(),
            lambda: build_embedding_complete(),
            lambda: build_sectioning_complete(),
            lambda: build_sample_prep_qc(),
            lambda: build_he_staining_complete(),
            lambda: build_he_qc(),
            lambda: build_pathologist_he_review("invasive_carcinoma"),
            lambda: build_ihc_staining_complete(),
            lambda: build_ihc_qc(),
            lambda: build_ihc_scoring({"ER": "positive"}),
            lambda: build_fish_decision(True),
            lambda: build_fish_result("amplified"),
            lambda: build_missing_info_received(),
            lambda: build_resulting_review("advance"),
            lambda: build_pathologist_signout(["H&E"]),
            lambda: build_report_generated(),
        ],
        ids=[
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
        ],
    )
    def test_returns_event_dict(self, factory_call: object) -> None:
        result = factory_call()  # type: ignore[operator]
        assert isinstance(result, dict)
        assert "event_type" in result
        assert "event_data" in result
        assert isinstance(result["event_type"], str)
        assert isinstance(result["event_data"], dict)
        assert result["event_type"] in VALID_EVENT_TYPES


# ── TestEventFactoryContracts ───────────────────────────────────────


class TestEventFactoryContracts:
    """Specific event_data values match expectations."""

    def test_order_received_has_patient_name(self) -> None:
        event = build_order_received(STANDARD_INVASIVE, 0)
        assert "patient_name" in event["event_data"]

    def test_grossing_complete_default_success(self) -> None:
        event = build_grossing_complete()
        assert event["event_data"]["outcome"] == "success"

    def test_grossing_complete_failure(self) -> None:
        event = build_grossing_complete("failure")
        assert event["event_data"]["outcome"] == "failure"

    def test_he_staining_fixation_issue(self) -> None:
        event = build_he_staining_complete(fixation_issue=True)
        assert event["event_data"]["fixation_issue"] is True

    def test_he_staining_no_fixation_issue(self) -> None:
        event = build_he_staining_complete()
        assert event["event_data"]["fixation_issue"] is False

    def test_pathologist_he_review_diagnosis(self) -> None:
        for diagnosis in VALID_DIAGNOSES:
            event = build_pathologist_he_review(diagnosis)
            assert event["event_data"]["diagnosis"] == diagnosis

    def test_ihc_staining_default_success(self) -> None:
        event = build_ihc_staining_complete()
        assert event["event_data"]["outcome"] == "success"

    def test_ihc_staining_fixation_reject(self) -> None:
        event = build_ihc_staining_complete("fixation_reject")
        assert event["event_data"]["outcome"] == "fixation_reject"

    def test_pathologist_he_review_recut_requested(self) -> None:
        event = build_pathologist_he_review("recut_requested")
        assert event["event_data"]["diagnosis"] == "recut_requested"

    def test_fish_result_qns(self) -> None:
        event = build_fish_result("qns")
        assert event["event_data"]["result"] == "qns"

    def test_ihc_scoring_scores_preserved(self) -> None:
        scores = {"ER": "positive", "PR": "negative", "HER2": "2+", "Ki-67": "high"}
        event = build_ihc_scoring(scores)
        assert event["event_data"]["scores"] == scores

    def test_ihc_scoring_returns_copy(self) -> None:
        scores = {"ER": "positive"}
        event = build_ihc_scoring(scores)
        event["event_data"]["scores"]["ER"] = "changed"
        assert scores["ER"] == "positive"

    def test_fish_decision_approved(self) -> None:
        event = build_fish_decision(True)
        assert event["event_data"]["approved"] is True

    def test_fish_decision_declined(self) -> None:
        event = build_fish_decision(False)
        assert event["event_data"]["approved"] is False

    def test_fish_result_values(self) -> None:
        for result in VALID_FISH_RESULTS:
            event = build_fish_result(result)
            assert event["event_data"]["result"] == result

    def test_resulting_review_outcomes(self) -> None:
        for outcome in VALID_RESULTING_REVIEW_OUTCOMES:
            event = build_resulting_review(outcome)
            assert event["event_data"]["outcome"] == outcome

    def test_missing_info_received_no_fields(self) -> None:
        event = build_missing_info_received()
        assert event["event_data"] == {}

    def test_missing_info_received_with_fields(self) -> None:
        event = build_missing_info_received(["patient_name", "billing"])
        assert event["event_data"]["resolved_fields"] == ["patient_name", "billing"]

    def test_pathologist_signout_tests(self) -> None:
        event = build_pathologist_signout(["H&E", "ER"])
        assert event["event_data"]["reportable_tests"] == ["H&E", "ER"]

    def test_report_generated_outcome(self) -> None:
        event = build_report_generated()
        assert event["event_data"]["outcome"] == "success"

    def test_ihc_qc_outcomes(self) -> None:
        for outcome in VALID_IHC_QC_OUTCOMES:
            event = build_ihc_qc(outcome)
            assert event["event_data"]["outcome"] == outcome

    def test_sample_prep_qc_outcomes(self) -> None:
        for outcome in VALID_SAMPLE_PREP_QC_OUTCOMES:
            event = build_sample_prep_qc(outcome)
            assert event["event_data"]["outcome"] == outcome

    def test_he_qc_outcomes(self) -> None:
        for outcome in VALID_HE_QC_OUTCOMES:
            event = build_he_qc(outcome)
            assert event["event_data"]["outcome"] == outcome


# ── TestEventFactoryValidation ──────────────────────────────────────


class TestEventFactoryValidation:
    """Invalid inputs raise ValueError."""

    def test_grossing_invalid_outcome(self) -> None:
        with pytest.raises(ValueError, match="Invalid outcome"):
            build_grossing_complete("bad")

    def test_processing_invalid_outcome(self) -> None:
        with pytest.raises(ValueError, match="Invalid outcome"):
            build_processing_complete("bad")

    def test_embedding_invalid_outcome(self) -> None:
        with pytest.raises(ValueError, match="Invalid outcome"):
            build_embedding_complete("bad")

    def test_sectioning_invalid_outcome(self) -> None:
        with pytest.raises(ValueError, match="Invalid outcome"):
            build_sectioning_complete("bad")

    def test_sample_prep_qc_invalid_outcome(self) -> None:
        with pytest.raises(ValueError, match="Invalid outcome"):
            build_sample_prep_qc("bad")

    def test_he_qc_invalid_outcome(self) -> None:
        with pytest.raises(ValueError, match="Invalid outcome"):
            build_he_qc("bad")

    def test_ihc_qc_invalid_outcome(self) -> None:
        with pytest.raises(ValueError, match="Invalid outcome"):
            build_ihc_qc("bad")

    def test_pathologist_he_review_invalid_diagnosis(self) -> None:
        with pytest.raises(ValueError, match="Invalid diagnosis"):
            build_pathologist_he_review("cancer")

    def test_ihc_scoring_empty_scores(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            build_ihc_scoring({})

    def test_ihc_scoring_invalid_marker(self) -> None:
        with pytest.raises(ValueError, match="Invalid marker"):
            build_ihc_scoring({"BRCA1": "positive"})

    def test_ihc_scoring_invalid_value(self) -> None:
        with pytest.raises(ValueError, match="Invalid score value"):
            build_ihc_scoring({"ER": "unknown"})

    def test_ihc_staining_invalid_outcome(self) -> None:
        with pytest.raises(ValueError, match="Invalid outcome"):
            build_ihc_staining_complete("bad")

    def test_fish_result_invalid(self) -> None:
        with pytest.raises(ValueError, match="Invalid result"):
            build_fish_result("indeterminate")

    def test_resulting_review_invalid_outcome(self) -> None:
        with pytest.raises(ValueError, match="Invalid outcome"):
            build_resulting_review("bad")

    def test_pathologist_signout_empty_tests(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            build_pathologist_signout([])

    def test_outcome_factories_reject_qc_values(self) -> None:
        """Outcome factories (success/failure) reject QC values (pass/fail)."""
        for factory in [
            build_grossing_complete,
            build_processing_complete,
            build_embedding_complete,
            build_sectioning_complete,
        ]:
            with pytest.raises(ValueError, match="Invalid outcome"):
                factory("pass")


# ── TestAssembleScenario ────────────────────────────────────────────


class TestAssembleScenario:
    """Tests for assemble_scenario auto-numbering and validation."""

    def test_auto_numbering(self) -> None:
        """Steps are auto-numbered starting from 1."""
        scenario = happy_path_invasive()
        step_nums = [s.step for s in scenario.steps]
        assert step_nums == list(range(1, len(scenario.steps) + 1))

    def test_first_step_is_order_received(self) -> None:
        scenario = happy_path_invasive()
        assert scenario.steps[0].event_type == "order_received"

    def test_validation_error_raises(self) -> None:
        """assemble_scenario raises ValueError on invalid transitions."""
        bad_steps = [
            {
                "event_type": "order_received",
                "event_data": {},
                "expected_output": {
                    "next_state": "ACCEPTED",
                    "applied_rules": ("ACC-008",),
                    "flags": (),
                },
            },
            {
                "event_type": "missing_info_received",
                "event_data": {},
                "expected_output": {
                    "next_state": "ORDER_COMPLETE",
                    "applied_rules": (),
                    "flags": (),
                },
            },
        ]
        with pytest.raises(ValueError, match="validation failed"):
            assemble_scenario("SC-099", "rule_coverage", "Bad scenario", bad_steps)

    def test_returns_scenario_object(self) -> None:
        scenario = happy_path_invasive()
        assert isinstance(scenario, Scenario)
        assert scenario.scenario_id == "PT-001"
        assert scenario.category == "rule_coverage"


# ── TestPathTemplatesValidation ─────────────────────────────────────


class TestPathTemplatesValidation:
    """All 10 templates pass validate_scenario() with zero errors."""

    @pytest.fixture()
    def state_machine(self) -> StateMachine:
        return StateMachine.get_instance()

    @pytest.mark.parametrize(
        "template_fn",
        ALL_TEMPLATES,
        ids=[fn.__name__ for fn in ALL_TEMPLATES],
    )
    def test_template_validates_clean(
        self, template_fn: object, state_machine: StateMachine
    ) -> None:
        scenario = template_fn()  # type: ignore[operator]
        errors = validate_scenario(scenario, state_machine)
        assert errors == [], (
            f"{template_fn.__name__} validation errors:\n"  # type: ignore[union-attr]
            + "\n".join(f"  Step {e.step_number}: [{e.error_type}] {e.message}" for e in errors)
        )


# ── TestPathTemplateSpecifics ───────────────────────────────────────


class TestPathTemplateSpecifics:
    """Verify terminal states, event presence, and flag behavior."""

    def test_happy_path_invasive_terminal(self) -> None:
        scenario = happy_path_invasive()
        assert scenario.steps[-1].expected_output.next_state == "ORDER_COMPLETE"

    def test_happy_path_benign_terminal(self) -> None:
        scenario = happy_path_benign()
        assert scenario.steps[-1].expected_output.next_state == "ORDER_COMPLETE"

    def test_happy_path_dcis_terminal(self) -> None:
        scenario = happy_path_dcis()
        assert scenario.steps[-1].expected_output.next_state == "ORDER_COMPLETE"

    def test_sample_prep_failure_terminal(self) -> None:
        scenario = sample_prep_failure_qns()
        assert scenario.steps[-1].expected_output.next_state == "ORDER_TERMINATED_QNS"

    def test_he_qc_restain_terminal(self) -> None:
        scenario = he_qc_restain()
        assert scenario.steps[-1].expected_output.next_state == "ORDER_COMPLETE"

    def test_he_qc_recut_terminal(self) -> None:
        scenario = he_qc_recut()
        assert scenario.steps[-1].expected_output.next_state == "ORDER_COMPLETE"

    def test_fish_approved_terminal(self) -> None:
        scenario = ihc_her2_equivocal_fish_approved()
        assert scenario.steps[-1].expected_output.next_state == "ORDER_COMPLETE"

    def test_fish_declined_terminal(self) -> None:
        scenario = ihc_her2_equivocal_fish_declined()
        assert scenario.steps[-1].expected_output.next_state == "ORDER_COMPLETE"

    def test_missing_info_hold_terminal(self) -> None:
        scenario = missing_info_hold_then_resolve()
        assert scenario.steps[-1].expected_output.next_state == "ORDER_COMPLETE"

    def test_missing_billing_hold_terminal(self) -> None:
        scenario = missing_billing_hold_at_resulting()
        assert scenario.steps[-1].expected_output.next_state == "ORDER_COMPLETE"

    def test_benign_has_no_ihc_events(self) -> None:
        """Benign path should skip IHC entirely."""
        scenario = happy_path_benign()
        ihc_types = {"ihc_staining_complete", "ihc_qc", "ihc_scoring"}
        ihc_events = [s for s in scenario.steps if s.event_type in ihc_types]
        assert ihc_events == []

    def test_invasive_has_ihc_events(self) -> None:
        """Invasive path must include IHC events."""
        scenario = happy_path_invasive()
        event_types = {s.event_type for s in scenario.steps}
        assert "ihc_staining_complete" in event_types
        assert "ihc_qc" in event_types
        assert "ihc_scoring" in event_types

    def test_fish_approved_has_fish_events(self) -> None:
        """FISH-approved template must include fish_decision and fish_result."""
        scenario = ihc_her2_equivocal_fish_approved()
        event_types = {s.event_type for s in scenario.steps}
        assert "fish_decision" in event_types
        assert "fish_result" in event_types

    def test_fish_declined_has_no_fish_result(self) -> None:
        """FISH-declined template must not include fish_result."""
        scenario = ihc_her2_equivocal_fish_declined()
        event_types = {s.event_type for s in scenario.steps}
        assert "fish_decision" in event_types
        assert "fish_result" not in event_types

    def test_fish_approved_has_fish_suggested_flag(self) -> None:
        """FISH template should set FISH_SUGGESTED flag at IHC_SCORING."""
        scenario = ihc_her2_equivocal_fish_approved()
        fish_flag_steps = [s for s in scenario.steps if "FISH_SUGGESTED" in s.expected_output.flags]
        assert len(fish_flag_steps) >= 1

    def test_missing_billing_has_proceed_flag(self) -> None:
        """Missing billing template sets MISSING_INFO_PROCEED flag."""
        scenario = missing_billing_hold_at_resulting()
        flag_steps = [
            s for s in scenario.steps if "MISSING_INFO_PROCEED" in s.expected_output.flags
        ]
        assert len(flag_steps) >= 1

    def test_he_restain_has_duplicate_he_events(self) -> None:
        """Restain template has H&E staining appear twice."""
        scenario = he_qc_restain()
        he_stain_events = [s for s in scenario.steps if s.event_type == "he_staining_complete"]
        assert len(he_stain_events) == 2

    def test_he_recut_revisits_sectioning(self) -> None:
        """Recut template revisits sectioning_complete."""
        scenario = he_qc_recut()
        sect_events = [s for s in scenario.steps if s.event_type == "sectioning_complete"]
        assert len(sect_events) >= 2

    def test_missing_info_hold_re_accessions(self) -> None:
        """Missing info hold template has two order_received events."""
        scenario = missing_info_hold_then_resolve()
        order_events = [s for s in scenario.steps if s.event_type == "order_received"]
        assert len(order_events) == 2

    def test_sample_prep_failure_has_sp006(self) -> None:
        """Sample prep failure applies SP-006."""
        scenario = sample_prep_failure_qns()
        rules = set()
        for step in scenario.steps:
            rules.update(step.expected_output.applied_rules)
        assert "SP-006" in rules

    def test_accessioning_reject_terminal(self) -> None:
        scenario = accessioning_reject()
        assert scenario.steps[-1].expected_output.next_state == "DO_NOT_PROCESS"

    def test_accessioning_reject_has_acc003(self) -> None:
        """Reject template applies ACC-003."""
        scenario = accessioning_reject()
        rules = set()
        for step in scenario.steps:
            rules.update(step.expected_output.applied_rules)
        assert "ACC-003" in rules

    def test_resulting_hold_has_res001_and_res002(self) -> None:
        """Resulting hold template applies RES-001 and RES-002."""
        scenario = missing_billing_hold_at_resulting()
        rules = set()
        for step in scenario.steps:
            rules.update(step.expected_output.applied_rules)
        assert "RES-001" in rules
        assert "RES-002" in rules


# ── TestTemplateComposition ─────────────────────────────────────────


class TestTemplateComposition:
    """Related templates share common prefixes."""

    def test_invasive_and_dcis_share_prefix(self) -> None:
        """Invasive and DCIS share the same prefix through H&E QC."""
        inv = happy_path_invasive()
        dcis = happy_path_dcis()
        # Both have same structure through H&E QC pass (step where HE-001 applied)
        he_qc_idx_inv = next(
            i for i, s in enumerate(inv.steps) if "HE-001" in s.expected_output.applied_rules
        )
        he_qc_idx_dcis = next(
            i for i, s in enumerate(dcis.steps) if "HE-001" in s.expected_output.applied_rules
        )
        # Same number of steps before pathologist review
        assert he_qc_idx_inv == he_qc_idx_dcis
        # Same event types up through H&E QC
        for i in range(he_qc_idx_inv + 1):
            assert inv.steps[i].event_type == dcis.steps[i].event_type

    def test_fish_approved_and_declined_share_prefix(self) -> None:
        """FISH approved and declined diverge only at fish_decision."""
        approved = ihc_her2_equivocal_fish_approved()
        declined = ihc_her2_equivocal_fish_declined()
        # Find divergence point (fish_decision step)
        fish_idx_a = next(
            i for i, s in enumerate(approved.steps) if s.event_type == "fish_decision"
        )
        fish_idx_d = next(
            i for i, s in enumerate(declined.steps) if s.event_type == "fish_decision"
        )
        assert fish_idx_a == fish_idx_d
        # Same event types before the divergence
        for i in range(fish_idx_a):
            assert approved.steps[i].event_type == declined.steps[i].event_type
