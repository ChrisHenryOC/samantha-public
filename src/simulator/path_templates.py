"""Workflow path templates for assembling complete test scenarios.

Three-layer architecture:

1. **assemble_scenario()** — takes step dicts, auto-numbers, creates a
   validated Scenario.
2. **Segment builders** (private) — reusable step-list producers for each
   workflow phase. Return ``list[dict]`` without step numbers.
3. **Template functions** (public) — compose segments into complete
   scenarios via list concatenation + ``assemble_scenario()``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from src.simulator.event_builder import (
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
from src.simulator.order_generator import (
    INVALID_ANATOMIC_SITE,
    MISSING_BILLING,
    MISSING_PATIENT_NAME,
    STANDARD_BENIGN,
    STANDARD_INVASIVE,
    OrderProfile,
)
from src.simulator.scenario_validator import validate_scenario
from src.simulator.schema import ExpectedOutput, Scenario, ScenarioStep
from src.workflow.state_machine import StateMachine

_REACCESSION_SEQ_OFFSET = 100

# ── Helpers ─────────────────────────────────────────────────────────


def _make_step_dict(
    event: dict[str, Any],
    next_state: str,
    applied_rules: tuple[str, ...],
    flags: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Create an unnumbered step dict for segment builders.

    Args:
        event: Dict from an event factory (has ``event_type``, ``event_data``).
        next_state: The expected next workflow state.
        applied_rules: Tuple of rule IDs applied at this step.
        flags: Tuple of flag IDs set at this step.

    Returns:
        Dict with ``event_type``, ``event_data``, and ``expected_output`` keys.
    """
    return {
        "event_type": event["event_type"],
        "event_data": event["event_data"],
        "expected_output": {
            "next_state": next_state,
            "applied_rules": applied_rules,
            "flags": flags,
        },
    }


def assemble_scenario(
    scenario_id: str,
    category: str,
    description: str,
    steps: list[dict[str, Any]],
) -> Scenario:
    """Assemble and validate a Scenario from unnumbered step dicts.

    Auto-numbers steps starting from 1, constructs ``ScenarioStep`` and
    ``ExpectedOutput`` objects, and validates the result against the state
    machine. Raises ``ValueError`` if validation finds errors.

    Args:
        scenario_id: Scenario identifier (format: ``SC-NNN``).
        category: Scenario category.
        description: Human-readable description.
        steps: List of dicts from segment builders (no step numbers).

    Returns:
        A validated ``Scenario`` object.

    Raises:
        ValueError: If validation finds any errors.
    """
    scenario_steps: list[ScenarioStep] = []
    for i, step_dict in enumerate(steps, start=1):
        eo = step_dict["expected_output"]
        expected_output = ExpectedOutput(
            next_state=eo["next_state"],
            applied_rules=eo["applied_rules"],
            flags=eo["flags"],
        )
        scenario_steps.append(
            ScenarioStep(
                step=i,
                event_type=step_dict["event_type"],
                event_data=step_dict["event_data"],
                expected_output=expected_output,
            )
        )

    scenario = Scenario(
        scenario_id=scenario_id,
        category=category,
        description=description,
        steps=tuple(scenario_steps),
    )

    sm = StateMachine.get_instance()
    errors = validate_scenario(scenario, sm)
    if errors:
        error_msgs = [f"  Step {e.step_number}: [{e.error_type}] {e.message}" for e in errors]
        raise ValueError(f"Scenario {scenario_id} validation failed:\n" + "\n".join(error_msgs))

    return scenario


# ── Layer 2: Segment builders (private) ─────────────────────────────


def _accessioning_accept(profile: OrderProfile, seq_num: int) -> list[dict[str, Any]]:
    """Accessioning step that accepts the order (ACC-008)."""
    return [
        _make_step_dict(
            build_order_received(profile, seq_num),
            next_state="ACCEPTED",
            applied_rules=("ACC-008",),
        ),
    ]


def _accessioning_hold(profile: OrderProfile, seq_num: int) -> list[dict[str, Any]]:
    """Accessioning step that holds for missing info (ACC-001)."""
    return [
        _make_step_dict(
            build_order_received(profile, seq_num),
            next_state="MISSING_INFO_HOLD",
            applied_rules=("ACC-001",),
        ),
    ]


def _accessioning_proceed(profile: OrderProfile, seq_num: int) -> list[dict[str, Any]]:
    """Accessioning step that proceeds with flag (ACC-007)."""
    return [
        _make_step_dict(
            build_order_received(profile, seq_num),
            next_state="MISSING_INFO_PROCEED",
            applied_rules=("ACC-007",),
            flags=("MISSING_INFO_PROCEED",),
        ),
    ]


def _accessioning_reject(profile: OrderProfile, seq_num: int) -> list[dict[str, Any]]:
    """Accessioning step that rejects the order."""
    return [
        _make_step_dict(
            build_order_received(profile, seq_num),
            next_state="DO_NOT_PROCESS",
            applied_rules=profile.target_rules,
        ),
    ]


def _hold_receive_reaccession(profile: OrderProfile, seq_num: int) -> list[dict[str, Any]]:
    """Receive missing info and re-accession from MISSING_INFO_HOLD.

    Step 1: missing_info_received → ACCESSIONING (re-evaluate).
    Step 2: order_received → ACCEPTED (ACC-008, all valid now).
    """
    # After info is received, we need a clean profile for re-accessioning.
    return [
        _make_step_dict(
            build_missing_info_received(resolved_fields=["patient_name"]),
            next_state="ACCESSIONING",
            applied_rules=(),
        ),
        _make_step_dict(
            build_order_received(STANDARD_INVASIVE, seq_num + _REACCESSION_SEQ_OFFSET),
            next_state="ACCEPTED",
            applied_rules=("ACC-008",),
        ),
    ]


def _sample_prep_linear() -> list[dict[str, Any]]:
    """Linear sample prep: GROSSING → PROCESSING → EMBEDDING → SECTIONING.

    4 steps, all SP-001 (step completed successfully).
    """
    return [
        _make_step_dict(
            build_grossing_complete(),
            next_state="SAMPLE_PREP_PROCESSING",
            applied_rules=("SP-001",),
        ),
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
    ]


def _sample_prep_processing_retry() -> list[dict[str, Any]]:
    """Sample prep processing fails, tissue available → retry (SP-002)."""
    return [
        _make_step_dict(
            build_processing_complete("failure"),
            next_state="SAMPLE_PREP_PROCESSING",
            applied_rules=("SP-002",),
        ),
    ]


def _sample_prep_qc_fail_retry() -> list[dict[str, Any]]:
    """Sample prep QC fails, tissue available → retry sectioning (SP-005)."""
    return [
        _make_step_dict(
            build_sample_prep_qc("fail_tissue_available"),
            next_state="SAMPLE_PREP_SECTIONING",
            applied_rules=("SP-005",),
        ),
    ]


def _sample_prep_qc_pass() -> list[dict[str, Any]]:
    """Sample prep QC passes (SP-004) → HE_STAINING."""
    return [
        _make_step_dict(
            build_sample_prep_qc("pass"),
            next_state="HE_STAINING",
            applied_rules=("SP-004",),
        ),
    ]


def _sample_prep_qc_fail_qns() -> list[dict[str, Any]]:
    """Sample prep QC fails, insufficient tissue (SP-006)."""
    return [
        _make_step_dict(
            build_sample_prep_qc("fail_qns"),
            next_state="ORDER_TERMINATED_QNS",
            applied_rules=("SP-006",),
        ),
    ]


def _he_staining_to_qc() -> list[dict[str, Any]]:
    """H&E staining completes and goes to QC."""
    return [
        _make_step_dict(
            build_he_staining_complete(),
            next_state="HE_QC",
            applied_rules=(),
        ),
    ]


def _he_qc_pass() -> list[dict[str, Any]]:
    """H&E QC passes (HE-001) → PATHOLOGIST_HE_REVIEW."""
    return [
        _make_step_dict(
            build_he_qc("pass"),
            next_state="PATHOLOGIST_HE_REVIEW",
            applied_rules=("HE-001",),
        ),
    ]


def _he_qc_fail_restain() -> list[dict[str, Any]]:
    """H&E QC fails, restain (HE-002) → HE_STAINING."""
    return [
        _make_step_dict(
            build_he_qc("fail_restain"),
            next_state="HE_STAINING",
            applied_rules=("HE-002",),
        ),
    ]


def _he_qc_fail_qns() -> list[dict[str, Any]]:
    """H&E QC fails, insufficient tissue (HE-004) → ORDER_TERMINATED_QNS."""
    return [
        _make_step_dict(
            build_he_qc("fail_qns"),
            next_state="ORDER_TERMINATED_QNS",
            applied_rules=("HE-004",),
        ),
    ]


def _he_qc_fail_recut() -> list[dict[str, Any]]:
    """H&E QC fails, recut needed (HE-003) → SAMPLE_PREP_SECTIONING."""
    return [
        _make_step_dict(
            build_he_qc("fail_recut"),
            next_state="SAMPLE_PREP_SECTIONING",
            applied_rules=("HE-003",),
        ),
    ]


def _pathologist_he_review_invasive() -> list[dict[str, Any]]:
    """Pathologist diagnoses invasive carcinoma (HE-005) → IHC_STAINING."""
    return [
        _make_step_dict(
            build_pathologist_he_review("invasive_carcinoma"),
            next_state="IHC_STAINING",
            applied_rules=("HE-005",),
        ),
    ]


def _pathologist_he_review_benign() -> list[dict[str, Any]]:
    """Pathologist diagnoses benign (HE-008) → RESULTING."""
    return [
        _make_step_dict(
            build_pathologist_he_review("benign"),
            next_state="RESULTING",
            applied_rules=("HE-008",),
        ),
    ]


def _pathologist_he_review_dcis() -> list[dict[str, Any]]:
    """Pathologist diagnoses DCIS (HE-006) → IHC_STAINING."""
    return [
        _make_step_dict(
            build_pathologist_he_review("dcis"),
            next_state="IHC_STAINING",
            applied_rules=("HE-006",),
        ),
    ]


def _pathologist_he_review_suspicious() -> list[dict[str, Any]]:
    """Pathologist diagnoses suspicious/atypical (HE-007) → IHC_STAINING."""
    return [
        _make_step_dict(
            build_pathologist_he_review("suspicious_atypical"),
            next_state="IHC_STAINING",
            applied_rules=("HE-007",),
        ),
    ]


def _pathologist_he_review_recut() -> list[dict[str, Any]]:
    """Pathologist requests recuts (HE-009) → SAMPLE_PREP_SECTIONING."""
    return [
        _make_step_dict(
            build_pathologist_he_review("recut_requested"),
            next_state="SAMPLE_PREP_SECTIONING",
            applied_rules=("HE-009",),
            flags=("RECUT_REQUESTED",),
        ),
    ]


def _ihc_staining_to_qc() -> list[dict[str, Any]]:
    """IHC staining completes → IHC_QC."""
    return [
        _make_step_dict(
            build_ihc_staining_complete(),
            next_state="IHC_QC",
            applied_rules=(),
        ),
    ]


def _ihc_fixation_reject() -> list[dict[str, Any]]:
    """HER2 fixation reject at IHC_STAINING (IHC-001) → IHC_STAINING (self-loop)."""
    return [
        _make_step_dict(
            build_ihc_staining_complete("fixation_reject"),
            next_state="IHC_STAINING",
            applied_rules=("IHC-001",),
            flags=("HER2_FIXATION_REJECT",),
        ),
    ]


def _ihc_qc_slides_pending() -> list[dict[str, Any]]:
    """IHC QC partial — some slides still pending (IHC-003) → IHC_QC (self-loop)."""
    return [
        _make_step_dict(
            build_ihc_qc("slides_pending"),
            next_state="IHC_QC",
            applied_rules=("IHC-003",),
        ),
    ]


def _ihc_qc_fail_retry() -> list[dict[str, Any]]:
    """IHC QC staining failed, retry (IHC-004) → IHC_STAINING."""
    return [
        _make_step_dict(
            build_ihc_qc("fail"),
            next_state="IHC_STAINING",
            applied_rules=("IHC-004",),
        ),
    ]


def _ihc_qc_fail_qns() -> list[dict[str, Any]]:
    """IHC QC staining failed, insufficient tissue (IHC-005) → ORDER_TERMINATED_QNS."""
    return [
        _make_step_dict(
            build_ihc_qc("fail_qns"),
            next_state="ORDER_TERMINATED_QNS",
            applied_rules=("IHC-005",),
        ),
    ]


def _ihc_qc_pass() -> list[dict[str, Any]]:
    """IHC QC all slides pass (IHC-002) → IHC_SCORING."""
    return [
        _make_step_dict(
            build_ihc_qc("all_pass"),
            next_state="IHC_SCORING",
            applied_rules=("IHC-002",),
        ),
    ]


def _ihc_scoring_complete(scores: dict[str, str]) -> list[dict[str, Any]]:
    """IHC scoring complete, no equivocal (IHC-006) → RESULTING."""
    return [
        _make_step_dict(
            build_ihc_scoring(scores),
            next_state="RESULTING",
            applied_rules=("IHC-006",),
        ),
    ]


def _ihc_scoring_equivocal(scores: dict[str, str]) -> list[dict[str, Any]]:
    """IHC scoring with HER2 equivocal (IHC-007) → SUGGEST_FISH_REFLEX."""
    return [
        _make_step_dict(
            build_ihc_scoring(scores),
            next_state="SUGGEST_FISH_REFLEX",
            applied_rules=("IHC-007",),
            flags=("FISH_SUGGESTED",),
        ),
    ]


def _fish_approved() -> list[dict[str, Any]]:
    """Pathologist approves FISH (IHC-008) → FISH_SEND_OUT."""
    return [
        _make_step_dict(
            build_fish_decision(approved=True),
            next_state="FISH_SEND_OUT",
            applied_rules=("IHC-008",),
        ),
    ]


def _fish_declined() -> list[dict[str, Any]]:
    """Pathologist declines FISH (IHC-009) → RESULTING."""
    return [
        _make_step_dict(
            build_fish_decision(approved=False),
            next_state="RESULTING",
            applied_rules=("IHC-009",),
        ),
    ]


def _fish_result_to_resulting(result: str = "not_amplified") -> list[dict[str, Any]]:
    """FISH result received at FISH_SEND_OUT (IHC-010) → RESULTING."""
    return [
        _make_step_dict(
            build_fish_result(result),
            next_state="RESULTING",
            applied_rules=("IHC-010",),
        ),
    ]


def _fish_result_qns() -> list[dict[str, Any]]:
    """FISH external lab returns QNS (IHC-011) → ORDER_TERMINATED_QNS."""
    return [
        _make_step_dict(
            build_fish_result("qns"),
            next_state="ORDER_TERMINATED_QNS",
            applied_rules=("IHC-011",),
        ),
    ]


def _resulting_no_flags() -> list[dict[str, Any]]:
    """Resulting with no blocking flags (RES-003) → PATHOLOGIST_SIGNOUT."""
    return [
        _make_step_dict(
            build_resulting_review("advance"),
            next_state="PATHOLOGIST_SIGNOUT",
            applied_rules=("RES-003",),
        ),
    ]


def _resulting_hold_and_resolve() -> list[dict[str, Any]]:
    """Resulting with MISSING_INFO_PROCEED flag → hold then resolve.

    Step 1: RESULTING → RESULTING_HOLD (RES-001, flag detected).
    Step 2: RESULTING_HOLD → RESULTING (RES-002, info received).
    Step 3: RESULTING → PATHOLOGIST_SIGNOUT (RES-003, flags cleared).
    """
    return [
        _make_step_dict(
            build_resulting_review("hold"),
            next_state="RESULTING_HOLD",
            applied_rules=("RES-001",),
        ),
        _make_step_dict(
            build_missing_info_received(resolved_fields=["billing_info"]),
            next_state="RESULTING",
            applied_rules=("RES-002",),
        ),
        _make_step_dict(
            build_resulting_review("advance"),
            next_state="PATHOLOGIST_SIGNOUT",
            applied_rules=("RES-003",),
        ),
    ]


def _signout_and_complete(reportable_tests: Sequence[str]) -> list[dict[str, Any]]:
    """Pathologist signout (RES-004) → report generation (RES-005) → complete.

    Args:
        reportable_tests: Tests selected for the final report.
    """
    return [
        _make_step_dict(
            build_pathologist_signout(reportable_tests),
            next_state="REPORT_GENERATION",
            applied_rules=("RES-004",),
        ),
        _make_step_dict(
            build_report_generated(),
            next_state="ORDER_COMPLETE",
            applied_rules=("RES-005",),
        ),
    ]


# ── Recut recovery segment ─────────────────────────────────────────


def _recut_recovery() -> list[dict[str, Any]]:
    """Recovery from recut: SECTIONING → QC → HE_STAINING → HE_QC → REVIEW.

    Entry state: SAMPLE_PREP_SECTIONING.
    Exit state: PATHOLOGIST_HE_REVIEW (via HE-001 QC pass).

    Used by HE-003 recut, HE-009 pathologist recut request, and SP-005
    QC-fail-retry paths.
    """
    return [
        _make_step_dict(
            build_sectioning_complete(),
            next_state="SAMPLE_PREP_QC",
            applied_rules=("SP-001",),
        ),
        *_sample_prep_qc_pass(),
        *_he_staining_to_qc(),
        *_he_qc_pass(),
    ]


# ── Layer 3: Template functions (public) ────────────────────────────

# Standard non-equivocal IHC scores.
_STANDARD_IHC_SCORES: dict[str, str] = {
    "ER": "positive",
    "PR": "positive",
    "HER2": "negative",
    "Ki-67": "high",
}

# Equivocal HER2 scores (triggers FISH).
_EQUIVOCAL_IHC_SCORES: dict[str, str] = {
    "ER": "positive",
    "PR": "positive",
    "HER2": "equivocal",
    "Ki-67": "low",
}

# DCIS IHC scores (ER, PR only — HER2 if ordered).
_DCIS_IHC_SCORES: dict[str, str] = {
    "ER": "positive",
    "PR": "negative",
    "HER2": "negative",
    "Ki-67": "low",
}

# Standard reportable tests for invasive carcinoma.
_INVASIVE_REPORTABLE: tuple[str, ...] = ("H&E", "ER", "PR", "HER2", "Ki-67")

# Benign reportable tests.
_BENIGN_REPORTABLE: tuple[str, ...] = ("H&E",)

# DCIS reportable tests.
_DCIS_REPORTABLE: tuple[str, ...] = ("H&E", "ER", "PR", "HER2", "Ki-67")

# FISH reportable tests.
_FISH_REPORTABLE: tuple[str, ...] = ("H&E", "ER", "PR", "HER2", "Ki-67", "FISH")


def happy_path_invasive() -> Scenario:
    """Full IHC path with invasive carcinoma, HER2 non-equivocal.

    ACCESSIONING → ACCEPTED → PROCESSING → ... → QC → H&E → HE_QC →
    PATHOLOGIST_HE_REVIEW → IHC → IHC_QC → IHC_SCORING → RESULTING →
    SIGNOUT → REPORT → ORDER_COMPLETE
    """
    steps = [
        *_accessioning_accept(STANDARD_INVASIVE, 1),
        *_sample_prep_linear(),
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
    return assemble_scenario(
        scenario_id="PT-001",
        category="rule_coverage",
        description="Happy path: invasive carcinoma with full IHC panel, HER2 non-equivocal",
        steps=steps,
    )


def happy_path_benign() -> Scenario:
    """Benign diagnosis skips IHC → goes directly to RESULTING.

    ACCESSIONING → ACCEPTED → PROCESSING → ... → QC → H&E → HE_QC →
    PATHOLOGIST_HE_REVIEW (benign) → RESULTING → SIGNOUT → REPORT →
    ORDER_COMPLETE
    """
    steps = [
        *_accessioning_accept(STANDARD_BENIGN, 2),
        *_sample_prep_linear(),
        *_sample_prep_qc_pass(),
        *_he_staining_to_qc(),
        *_he_qc_pass(),
        *_pathologist_he_review_benign(),
        *_resulting_no_flags(),
        *_signout_and_complete(_BENIGN_REPORTABLE),
    ]
    return assemble_scenario(
        scenario_id="PT-002",
        category="rule_coverage",
        description="Happy path: benign diagnosis, IHC skipped",
        steps=steps,
    )


def happy_path_dcis() -> Scenario:
    """DCIS diagnosis with IHC scoring.

    ACCESSIONING → ACCEPTED → PROCESSING → ... → QC → H&E → HE_QC →
    PATHOLOGIST_HE_REVIEW (DCIS) → IHC → IHC_QC → IHC_SCORING →
    RESULTING → SIGNOUT → REPORT → ORDER_COMPLETE
    """
    # STANDARD_INVASIVE is correct here: diagnosis (DCIS vs invasive) is
    # determined at pathologist H&E review, not at accessioning.
    steps = [
        *_accessioning_accept(STANDARD_INVASIVE, 3),
        *_sample_prep_linear(),
        *_sample_prep_qc_pass(),
        *_he_staining_to_qc(),
        *_he_qc_pass(),
        *_pathologist_he_review_dcis(),
        *_ihc_staining_to_qc(),
        *_ihc_qc_pass(),
        *_ihc_scoring_complete(_DCIS_IHC_SCORES),
        *_resulting_no_flags(),
        *_signout_and_complete(_DCIS_REPORTABLE),
    ]
    return assemble_scenario(
        scenario_id="PT-003",
        category="rule_coverage",
        description="Happy path: DCIS diagnosis with IHC scoring",
        steps=steps,
    )


def sample_prep_failure_qns() -> Scenario:
    """Sample prep QC fails with insufficient tissue → ORDER_TERMINATED_QNS.

    ACCESSIONING → ACCEPTED → PROCESSING → ... → QC (fail_qns) →
    ORDER_TERMINATED_QNS
    """
    steps = [
        *_accessioning_accept(STANDARD_INVASIVE, 4),
        *_sample_prep_linear(),
        *_sample_prep_qc_fail_qns(),
    ]
    return assemble_scenario(
        scenario_id="PT-004",
        category="rule_coverage",
        description="Sample prep QC failure: insufficient tissue, order terminated QNS",
        steps=steps,
    )


def he_qc_restain() -> Scenario:
    """H&E QC fails → restain → pass on second attempt.

    ACCESSIONING → ACCEPTED → PROCESSING → ... → QC → H&E → HE_QC (fail) →
    HE_STAINING (restain) → HE_QC (pass) → PATHOLOGIST_HE_REVIEW →
    IHC → ... → ORDER_COMPLETE
    """
    steps = [
        *_accessioning_accept(STANDARD_INVASIVE, 5),
        *_sample_prep_linear(),
        *_sample_prep_qc_pass(),
        *_he_staining_to_qc(),
        *_he_qc_fail_restain(),
        # Restain attempt
        *_he_staining_to_qc(),
        *_he_qc_pass(),
        *_pathologist_he_review_invasive(),
        *_ihc_staining_to_qc(),
        *_ihc_qc_pass(),
        *_ihc_scoring_complete(_STANDARD_IHC_SCORES),
        *_resulting_no_flags(),
        *_signout_and_complete(_INVASIVE_REPORTABLE),
    ]
    return assemble_scenario(
        scenario_id="PT-005",
        category="rule_coverage",
        description="H&E QC failure with restain recovery, then normal IHC path",
        steps=steps,
    )


def he_qc_recut() -> Scenario:
    """H&E QC fails → recut from SAMPLE_PREP_SECTIONING → recover.

    ACCESSIONING → ACCEPTED → PROCESSING → ... → QC → H&E → HE_QC (fail) →
    SAMPLE_PREP_SECTIONING (recut) → QC → H&E → HE_QC (pass) →
    PATHOLOGIST_HE_REVIEW → IHC → ... → ORDER_COMPLETE
    """
    steps = [
        *_accessioning_accept(STANDARD_INVASIVE, 6),
        *_sample_prep_linear(),
        *_sample_prep_qc_pass(),
        *_he_staining_to_qc(),
        *_he_qc_fail_recut(),
        # Recut recovery: re-enter at SECTIONING
        *_recut_recovery(),
        *_pathologist_he_review_invasive(),
        *_ihc_staining_to_qc(),
        *_ihc_qc_pass(),
        *_ihc_scoring_complete(_STANDARD_IHC_SCORES),
        *_resulting_no_flags(),
        *_signout_and_complete(_INVASIVE_REPORTABLE),
    ]
    return assemble_scenario(
        scenario_id="PT-006",
        category="rule_coverage",
        description="H&E QC failure with recut from sectioning, then normal IHC path",
        steps=steps,
    )


def ihc_her2_equivocal_fish_approved() -> Scenario:
    """HER2 equivocal → FISH approved → FISH result → ORDER_COMPLETE.

    ACCESSIONING → ... → IHC_SCORING (equivocal) → SUGGEST_FISH_REFLEX →
    FISH_SEND_OUT → RESULTING → SIGNOUT → REPORT → ORDER_COMPLETE
    """
    steps = [
        *_accessioning_accept(STANDARD_INVASIVE, 7),
        *_sample_prep_linear(),
        *_sample_prep_qc_pass(),
        *_he_staining_to_qc(),
        *_he_qc_pass(),
        *_pathologist_he_review_invasive(),
        *_ihc_staining_to_qc(),
        *_ihc_qc_pass(),
        *_ihc_scoring_equivocal(_EQUIVOCAL_IHC_SCORES),
        *_fish_approved(),
        *_fish_result_to_resulting(),
        *_resulting_no_flags(),
        *_signout_and_complete(_FISH_REPORTABLE),
    ]
    return assemble_scenario(
        scenario_id="PT-007",
        category="rule_coverage",
        description="HER2 equivocal with FISH approved, amplification result",
        steps=steps,
    )


def ihc_her2_equivocal_fish_declined() -> Scenario:
    """HER2 equivocal → FISH declined → RESULTING → ORDER_COMPLETE.

    ACCESSIONING → ... → IHC_SCORING (equivocal) → SUGGEST_FISH_REFLEX →
    RESULTING (declined) → SIGNOUT → REPORT → ORDER_COMPLETE
    """
    steps = [
        *_accessioning_accept(STANDARD_INVASIVE, 8),
        *_sample_prep_linear(),
        *_sample_prep_qc_pass(),
        *_he_staining_to_qc(),
        *_he_qc_pass(),
        *_pathologist_he_review_invasive(),
        *_ihc_staining_to_qc(),
        *_ihc_qc_pass(),
        *_ihc_scoring_equivocal(_EQUIVOCAL_IHC_SCORES),
        *_fish_declined(),
        *_resulting_no_flags(),
        *_signout_and_complete(_INVASIVE_REPORTABLE),
    ]
    return assemble_scenario(
        scenario_id="PT-008",
        category="rule_coverage",
        description="HER2 equivocal with FISH declined, proceeds to resulting",
        steps=steps,
    )


def missing_info_hold_then_resolve() -> Scenario:
    """Missing info hold → info received → re-accession → ORDER_COMPLETE.

    ACCESSIONING (hold) → MISSING_INFO_HOLD → ACCESSIONING (re-evaluate) →
    ACCEPTED → PROCESSING → ... → ORDER_COMPLETE
    """
    steps = [
        *_accessioning_hold(MISSING_PATIENT_NAME, 9),
        *_hold_receive_reaccession(MISSING_PATIENT_NAME, 9),
        *_sample_prep_linear(),
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
    return assemble_scenario(
        scenario_id="PT-009",
        category="accumulated_state",
        description="Missing info hold, info received, re-accessioned, then full IHC path",
        steps=steps,
    )


def missing_billing_hold_at_resulting() -> Scenario:
    """Missing billing → proceed with flag → hold at RESULTING.

    ACCESSIONING (proceed w/ flag) → MISSING_INFO_PROCEED → PROCESSING →
    ... → RESULTING → RESULTING_HOLD → RESULTING → SIGNOUT →
    REPORT → ORDER_COMPLETE
    """
    steps = [
        *_accessioning_proceed(MISSING_BILLING, 10),
        *_sample_prep_linear(),
        *_sample_prep_qc_pass(),
        *_he_staining_to_qc(),
        *_he_qc_pass(),
        *_pathologist_he_review_invasive(),
        *_ihc_staining_to_qc(),
        *_ihc_qc_pass(),
        *_ihc_scoring_complete(_STANDARD_IHC_SCORES),
        *_resulting_hold_and_resolve(),
        *_signout_and_complete(_INVASIVE_REPORTABLE),
    ]
    return assemble_scenario(
        scenario_id="PT-010",
        category="accumulated_state",
        description="Missing billing info, proceed with flag, hold at resulting then resolve",
        steps=steps,
    )


def he_qc_fail_qns() -> Scenario:
    """H&E QC fails, insufficient tissue → ORDER_TERMINATED_QNS.

    ACCESSIONING → ACCEPTED → PROCESSING → ... → QC → H&E → HE_QC (fail_qns) →
    ORDER_TERMINATED_QNS

    Exercises: HE-004
    """
    steps = [
        *_accessioning_accept(STANDARD_INVASIVE, 12),
        *_sample_prep_linear(),
        *_sample_prep_qc_pass(),
        *_he_staining_to_qc(),
        *_he_qc_fail_qns(),
    ]
    return assemble_scenario(
        scenario_id="PT-012",
        category="rule_coverage",
        description="H&E QC failure: insufficient tissue, order terminated QNS (HE-004)",
        steps=steps,
    )


def pathologist_suspicious_ihc() -> Scenario:
    """Suspicious/atypical diagnosis → IHC with customized panel.

    ACCESSIONING → ACCEPTED → PROCESSING → ... → QC → H&E → HE_QC →
    PATHOLOGIST_HE_REVIEW (suspicious) → IHC_STAINING → IHC_QC →
    IHC_SCORING → RESULTING → SIGNOUT → REPORT → ORDER_COMPLETE

    Exercises: HE-007
    """
    steps = [
        *_accessioning_accept(STANDARD_INVASIVE, 13),
        *_sample_prep_linear(),
        *_sample_prep_qc_pass(),
        *_he_staining_to_qc(),
        *_he_qc_pass(),
        *_pathologist_he_review_suspicious(),
        *_ihc_staining_to_qc(),
        *_ihc_qc_pass(),
        *_ihc_scoring_complete(_STANDARD_IHC_SCORES),
        *_resulting_no_flags(),
        *_signout_and_complete(_INVASIVE_REPORTABLE),
    ]
    return assemble_scenario(
        scenario_id="PT-013",
        category="rule_coverage",
        description="Suspicious/atypical diagnosis with IHC panel (HE-007)",
        steps=steps,
    )


def pathologist_requests_recuts() -> Scenario:
    """Pathologist requests recuts → SAMPLE_PREP_SECTIONING → recovery.

    ACCESSIONING → ACCEPTED → PROCESSING → ... → QC → H&E → HE_QC →
    PATHOLOGIST_HE_REVIEW (recut) → SAMPLE_PREP_SECTIONING → recovery →
    PATHOLOGIST_HE_REVIEW (invasive) → IHC → ... → ORDER_COMPLETE

    Exercises: HE-009
    """
    steps = [
        *_accessioning_accept(STANDARD_INVASIVE, 14),
        *_sample_prep_linear(),
        *_sample_prep_qc_pass(),
        *_he_staining_to_qc(),
        *_he_qc_pass(),
        *_pathologist_he_review_recut(),
        # Recovery from recut: sectioning → QC → H&E → HE_QC → REVIEW
        *_recut_recovery(),
        *_pathologist_he_review_invasive(),
        *_ihc_staining_to_qc(),
        *_ihc_qc_pass(),
        *_ihc_scoring_complete(_STANDARD_IHC_SCORES),
        *_resulting_no_flags(),
        *_signout_and_complete(_INVASIVE_REPORTABLE),
    ]
    return assemble_scenario(
        scenario_id="PT-014",
        category="rule_coverage",
        description="Pathologist requests recuts, recovery, then full IHC path (HE-009)",
        steps=steps,
    )


def sample_prep_processing_retry() -> Scenario:
    """Sample prep processing fails, tissue available → retry → succeed.

    ACCESSIONING → ACCEPTED → GROSSING → PROCESSING (fail, retry) →
    PROCESSING (success) → EMBEDDING → SECTIONING → QC → H&E →
    ... → ORDER_COMPLETE

    Exercises: SP-002
    """
    steps = [
        *_accessioning_accept(STANDARD_INVASIVE, 15),
        # Grossing succeeds
        _make_step_dict(
            build_grossing_complete(),
            next_state="SAMPLE_PREP_PROCESSING",
            applied_rules=("SP-001",),
        ),
        # Processing fails, retry (SP-002)
        *_sample_prep_processing_retry(),
        # Processing succeeds on retry
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
    return assemble_scenario(
        scenario_id="PT-015",
        category="rule_coverage",
        description="Sample prep processing fails with retry, then normal path (SP-002)",
        steps=steps,
    )


def sample_prep_qc_fail_retry() -> Scenario:
    """Sample prep QC fails, tissue available → retry sectioning → succeed.

    ACCESSIONING → ACCEPTED → PROCESSING → ... → QC (fail, retry) →
    SAMPLE_PREP_SECTIONING → QC (pass) → H&E → ... → ORDER_COMPLETE

    Exercises: SP-005
    """
    steps = [
        *_accessioning_accept(STANDARD_INVASIVE, 16),
        *_sample_prep_linear(),
        # QC fails, tissue available (SP-005) → back to SECTIONING
        *_sample_prep_qc_fail_retry(),
        # Recovery: sectioning → QC → H&E → QC → REVIEW
        *_recut_recovery(),
        *_pathologist_he_review_invasive(),
        *_ihc_staining_to_qc(),
        *_ihc_qc_pass(),
        *_ihc_scoring_complete(_STANDARD_IHC_SCORES),
        *_resulting_no_flags(),
        *_signout_and_complete(_INVASIVE_REPORTABLE),
    ]
    return assemble_scenario(
        scenario_id="PT-016",
        category="rule_coverage",
        description="Sample prep QC fails with retry from sectioning, then normal path (SP-005)",
        steps=steps,
    )


def ihc_fixation_reject() -> Scenario:
    """HER2 fixation reject at IHC_STAINING → self-loop → continue.

    ACCESSIONING → ... → IHC_STAINING (fixation reject, IHC-001) →
    IHC_STAINING (success) → IHC_QC → IHC_SCORING → RESULTING →
    SIGNOUT → REPORT → ORDER_COMPLETE

    Exercises: IHC-001
    """
    steps = [
        *_accessioning_accept(STANDARD_INVASIVE, 17),
        *_sample_prep_linear(),
        *_sample_prep_qc_pass(),
        *_he_staining_to_qc(),
        *_he_qc_pass(),
        *_pathologist_he_review_invasive(),
        # HER2 fixation reject (IHC-001) → stays at IHC_STAINING
        *_ihc_fixation_reject(),
        # Re-stain succeeds
        *_ihc_staining_to_qc(),
        *_ihc_qc_pass(),
        *_ihc_scoring_complete(_STANDARD_IHC_SCORES),
        *_resulting_no_flags(),
        *_signout_and_complete(_INVASIVE_REPORTABLE),
    ]
    return assemble_scenario(
        scenario_id="PT-017",
        category="rule_coverage",
        description="HER2 fixation reject at IHC staining, retry, then normal path (IHC-001)",
        steps=steps,
    )


def ihc_qc_slides_pending() -> Scenario:
    """IHC QC partial — slides pending → hold → all pass → continue.

    ACCESSIONING → ... → IHC_QC (slides_pending, IHC-003) →
    IHC_QC (all_pass) → IHC_SCORING → RESULTING → ... → ORDER_COMPLETE

    Exercises: IHC-003
    """
    steps = [
        *_accessioning_accept(STANDARD_INVASIVE, 18),
        *_sample_prep_linear(),
        *_sample_prep_qc_pass(),
        *_he_staining_to_qc(),
        *_he_qc_pass(),
        *_pathologist_he_review_invasive(),
        *_ihc_staining_to_qc(),
        # Slides pending (IHC-003) → hold at IHC_QC
        *_ihc_qc_slides_pending(),
        # All pass on second check
        *_ihc_qc_pass(),
        *_ihc_scoring_complete(_STANDARD_IHC_SCORES),
        *_resulting_no_flags(),
        *_signout_and_complete(_INVASIVE_REPORTABLE),
    ]
    return assemble_scenario(
        scenario_id="PT-018",
        category="rule_coverage",
        description="IHC QC slides pending, then all pass (IHC-003)",
        steps=steps,
    )


def ihc_qc_staining_fail_retry() -> Scenario:
    """IHC QC staining failed → retry → succeed.

    ACCESSIONING → ... → IHC_QC (fail, IHC-004) → IHC_STAINING →
    IHC_QC (pass) → IHC_SCORING → RESULTING → ... → ORDER_COMPLETE

    Exercises: IHC-004
    """
    steps = [
        *_accessioning_accept(STANDARD_INVASIVE, 19),
        *_sample_prep_linear(),
        *_sample_prep_qc_pass(),
        *_he_staining_to_qc(),
        *_he_qc_pass(),
        *_pathologist_he_review_invasive(),
        *_ihc_staining_to_qc(),
        # Staining failed (IHC-004) → back to IHC_STAINING
        *_ihc_qc_fail_retry(),
        # Retry staining succeeds
        *_ihc_staining_to_qc(),
        *_ihc_qc_pass(),
        *_ihc_scoring_complete(_STANDARD_IHC_SCORES),
        *_resulting_no_flags(),
        *_signout_and_complete(_INVASIVE_REPORTABLE),
    ]
    return assemble_scenario(
        scenario_id="PT-019",
        category="rule_coverage",
        description="IHC staining failed with retry, then normal path (IHC-004)",
        steps=steps,
    )


def ihc_qc_staining_fail_qns() -> Scenario:
    """IHC QC staining failed, insufficient tissue → ORDER_TERMINATED_QNS.

    ACCESSIONING → ... → IHC_QC (fail_qns, IHC-005) → ORDER_TERMINATED_QNS

    Exercises: IHC-005
    """
    steps = [
        *_accessioning_accept(STANDARD_INVASIVE, 20),
        *_sample_prep_linear(),
        *_sample_prep_qc_pass(),
        *_he_staining_to_qc(),
        *_he_qc_pass(),
        *_pathologist_he_review_invasive(),
        *_ihc_staining_to_qc(),
        # Staining failed, QNS (IHC-005) → ORDER_TERMINATED_QNS
        *_ihc_qc_fail_qns(),
    ]
    return assemble_scenario(
        scenario_id="PT-020",
        category="rule_coverage",
        description="IHC staining failed, insufficient tissue, order terminated QNS (IHC-005)",
        steps=steps,
    )


def fish_external_qns() -> Scenario:
    """FISH external lab returns QNS → ORDER_TERMINATED_QNS.

    ACCESSIONING → ... → IHC_SCORING (equivocal) → SUGGEST_FISH_REFLEX →
    FISH_SEND_OUT → ORDER_TERMINATED_QNS

    Exercises: IHC-011
    """
    steps = [
        *_accessioning_accept(STANDARD_INVASIVE, 21),
        *_sample_prep_linear(),
        *_sample_prep_qc_pass(),
        *_he_staining_to_qc(),
        *_he_qc_pass(),
        *_pathologist_he_review_invasive(),
        *_ihc_staining_to_qc(),
        *_ihc_qc_pass(),
        *_ihc_scoring_equivocal(_EQUIVOCAL_IHC_SCORES),
        *_fish_approved(),
        # FISH external lab returns QNS (IHC-011)
        *_fish_result_qns(),
    ]
    return assemble_scenario(
        scenario_id="PT-021",
        category="rule_coverage",
        description="FISH external lab returns QNS, order terminated (IHC-011)",
        steps=steps,
    )


def accessioning_reject() -> Scenario:
    """Invalid anatomic site → REJECT → DO_NOT_PROCESS.

    ACCESSIONING (reject, ACC-003) → DO_NOT_PROCESS
    """
    steps = [
        *_accessioning_reject(INVALID_ANATOMIC_SITE, 11),
    ]
    return assemble_scenario(
        scenario_id="PT-011",
        category="rule_coverage",
        description="Accessioning reject: invalid anatomic site, order terminated",
        steps=steps,
    )


# All template functions for iteration.
ALL_TEMPLATES: tuple[Callable[[], Scenario], ...] = (
    happy_path_invasive,
    happy_path_benign,
    happy_path_dcis,
    sample_prep_failure_qns,
    he_qc_restain,
    he_qc_recut,
    ihc_her2_equivocal_fish_approved,
    ihc_her2_equivocal_fish_declined,
    missing_info_hold_then_resolve,
    missing_billing_hold_at_resulting,
    accessioning_reject,
    he_qc_fail_qns,
    pathologist_suspicious_ihc,
    pathologist_requests_recuts,
    sample_prep_processing_retry,
    sample_prep_qc_fail_retry,
    ihc_fixation_reject,
    ihc_qc_slides_pending,
    ihc_qc_staining_fail_retry,
    ihc_qc_staining_fail_qns,
    fish_external_qns,
)
