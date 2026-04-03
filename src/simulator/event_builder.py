"""Event factory functions for building scenario event dicts.

Each factory returns ``{"event_type": str, "event_data": dict}`` ready for
use in scenario step construction. Input validation uses frozenset constants
to catch invalid arguments early.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from src.simulator.order_generator import OrderProfile, generate_order_data

# ── Validation constants ────────────────────────────────────────────

VALID_OUTCOMES: frozenset[str] = frozenset({"success", "failure"})

VALID_SAMPLE_PREP_QC_OUTCOMES: frozenset[str] = frozenset(
    {"pass", "fail_tissue_available", "fail_qns"}
)

VALID_HE_QC_OUTCOMES: frozenset[str] = frozenset({"pass", "fail_restain", "fail_recut", "fail_qns"})

VALID_IHC_QC_OUTCOMES: frozenset[str] = frozenset(
    {"all_pass", "slides_pending", "fail", "fail_qns"}
)

VALID_DIAGNOSES: frozenset[str] = frozenset(
    {"invasive_carcinoma", "benign", "dcis", "suspicious_atypical", "recut_requested"}
)

VALID_FISH_RESULTS: frozenset[str] = frozenset({"amplified", "not_amplified", "qns"})

VALID_IHC_SCORE_VALUES: frozenset[str] = frozenset(
    {"positive", "negative", "equivocal", "0", "1+", "2+", "3+", "high", "low"}
)

VALID_IHC_MARKERS: frozenset[str] = frozenset({"ER", "PR", "HER2", "Ki-67"})

VALID_RESULTING_REVIEW_OUTCOMES: frozenset[str] = frozenset({"advance", "hold"})

# Pre-computed sorted strings for error messages.
_SORTED_OUTCOMES: str = str(sorted(VALID_OUTCOMES))
_SORTED_SAMPLE_PREP_QC: str = str(sorted(VALID_SAMPLE_PREP_QC_OUTCOMES))
_SORTED_HE_QC: str = str(sorted(VALID_HE_QC_OUTCOMES))
_SORTED_IHC_QC: str = str(sorted(VALID_IHC_QC_OUTCOMES))
_SORTED_DIAGNOSES: str = str(sorted(VALID_DIAGNOSES))
_SORTED_FISH_RESULTS: str = str(sorted(VALID_FISH_RESULTS))
_SORTED_IHC_MARKERS: str = str(sorted(VALID_IHC_MARKERS))
_SORTED_IHC_SCORE_VALUES: str = str(sorted(VALID_IHC_SCORE_VALUES))
_SORTED_RESULTING_REVIEW: str = str(sorted(VALID_RESULTING_REVIEW_OUTCOMES))


# ── Private helpers ─────────────────────────────────────────────────


def _build_event(event_type: str, event_data: dict[str, Any]) -> dict[str, Any]:
    """Build a standardized event dict.

    Args:
        event_type: The event type string.
        event_data: The event payload.

    Returns:
        Dict with ``event_type`` and ``event_data`` keys.
    """
    return {"event_type": event_type, "event_data": event_data}


def _validate_outcome(outcome: str, valid: frozenset[str], sorted_str: str) -> None:
    """Validate an outcome value against an allowlist.

    Args:
        outcome: The outcome value to validate.
        valid: Frozenset of valid values.
        sorted_str: Pre-computed sorted string for error messages.

    Raises:
        ValueError: If outcome is not in the valid set.
    """
    if outcome not in valid:
        raise ValueError(f"Invalid outcome '{outcome}'. Must be one of: {sorted_str}")


# ── Factory functions ───────────────────────────────────────────────


def build_order_received(profile: OrderProfile, seq_num: int) -> dict[str, Any]:
    """Build an order_received event from an OrderProfile.

    Args:
        profile: The order profile to generate data from.
        seq_num: Sequence number for unique patient naming.

    Returns:
        Event dict with type ``order_received``.
    """
    return _build_event("order_received", generate_order_data(profile, seq_num))


def build_grossing_complete(outcome: str = "success") -> dict[str, Any]:
    """Build a grossing_complete event.

    Args:
        outcome: ``"success"`` or ``"failure"``.

    Raises:
        ValueError: If outcome is not valid.
    """
    _validate_outcome(outcome, VALID_OUTCOMES, _SORTED_OUTCOMES)
    return _build_event("grossing_complete", {"outcome": outcome})


def build_processing_complete(outcome: str = "success") -> dict[str, Any]:
    """Build a processing_complete event.

    Args:
        outcome: ``"success"`` or ``"failure"``.

    Raises:
        ValueError: If outcome is not valid.
    """
    _validate_outcome(outcome, VALID_OUTCOMES, _SORTED_OUTCOMES)
    return _build_event("processing_complete", {"outcome": outcome})


def build_embedding_complete(outcome: str = "success") -> dict[str, Any]:
    """Build an embedding_complete event.

    Args:
        outcome: ``"success"`` or ``"failure"``.

    Raises:
        ValueError: If outcome is not valid.
    """
    _validate_outcome(outcome, VALID_OUTCOMES, _SORTED_OUTCOMES)
    return _build_event("embedding_complete", {"outcome": outcome})


def build_sectioning_complete(outcome: str = "success") -> dict[str, Any]:
    """Build a sectioning_complete event.

    Args:
        outcome: ``"success"`` or ``"failure"``.

    Raises:
        ValueError: If outcome is not valid.
    """
    _validate_outcome(outcome, VALID_OUTCOMES, _SORTED_OUTCOMES)
    return _build_event("sectioning_complete", {"outcome": outcome})


def build_sample_prep_qc(outcome: str = "pass") -> dict[str, Any]:
    """Build a sample_prep_qc event.

    Args:
        outcome: ``"pass"``, ``"fail_tissue_available"``, or ``"fail_qns"``.

    Raises:
        ValueError: If outcome is not valid.
    """
    _validate_outcome(outcome, VALID_SAMPLE_PREP_QC_OUTCOMES, _SORTED_SAMPLE_PREP_QC)
    return _build_event("sample_prep_qc", {"outcome": outcome})


def build_he_staining_complete(*, fixation_issue: bool = False) -> dict[str, Any]:
    """Build an he_staining_complete event.

    Args:
        fixation_issue: Whether fixation issues were observed.

    Returns:
        Event dict with type ``he_staining_complete``.
    """
    return _build_event("he_staining_complete", {"fixation_issue": fixation_issue})


def build_he_qc(outcome: str = "pass") -> dict[str, Any]:
    """Build an he_qc event.

    Args:
        outcome: ``"pass"``, ``"fail_restain"``, ``"fail_recut"``,
            or ``"fail_qns"``.

    Raises:
        ValueError: If outcome is not valid.
    """
    _validate_outcome(outcome, VALID_HE_QC_OUTCOMES, _SORTED_HE_QC)
    return _build_event("he_qc", {"outcome": outcome})


def build_pathologist_he_review(diagnosis: str) -> dict[str, Any]:
    """Build a pathologist_he_review event.

    Args:
        diagnosis: One of ``invasive_carcinoma``, ``benign``, ``dcis``,
            ``suspicious_atypical``, or ``recut_requested``.

    Raises:
        ValueError: If diagnosis is not valid.
    """
    if diagnosis not in VALID_DIAGNOSES:
        raise ValueError(f"Invalid diagnosis '{diagnosis}'. Must be one of: {_SORTED_DIAGNOSES}")
    return _build_event("pathologist_he_review", {"diagnosis": diagnosis})


VALID_IHC_STAINING_OUTCOMES: frozenset[str] = frozenset({"success", "fixation_reject"})

_SORTED_IHC_STAINING: str = str(sorted(VALID_IHC_STAINING_OUTCOMES))


def build_ihc_staining_complete(
    outcome: str = "success",
) -> dict[str, Any]:
    """Build an ihc_staining_complete event.

    Args:
        outcome: ``"success"`` or ``"fixation_reject"``.

    Raises:
        ValueError: If outcome is not valid.
    """
    _validate_outcome(outcome, VALID_IHC_STAINING_OUTCOMES, _SORTED_IHC_STAINING)
    return _build_event("ihc_staining_complete", {"outcome": outcome})


def build_ihc_qc(outcome: str = "all_pass") -> dict[str, Any]:
    """Build an ihc_qc event.

    Args:
        outcome: ``"all_pass"``, ``"slides_pending"``, ``"fail"``,
            or ``"fail_qns"``.

    Raises:
        ValueError: If outcome is not valid.
    """
    _validate_outcome(outcome, VALID_IHC_QC_OUTCOMES, _SORTED_IHC_QC)
    return _build_event("ihc_qc", {"outcome": outcome})


def build_ihc_scoring(scores: dict[str, str]) -> dict[str, Any]:
    """Build an ihc_scoring event.

    Args:
        scores: Mapping of marker name to score value, e.g.
            ``{"ER": "positive", "PR": "positive", "HER2": "2+", "Ki-67": "high"}``.

    Raises:
        ValueError: If scores is empty, contains invalid markers,
            or contains invalid score values.
    """
    if not scores:
        raise ValueError("scores must not be empty")
    for marker, value in scores.items():
        if marker not in VALID_IHC_MARKERS:
            raise ValueError(f"Invalid marker '{marker}'. Must be one of: {_SORTED_IHC_MARKERS}")
        if value not in VALID_IHC_SCORE_VALUES:
            raise ValueError(
                f"Invalid score value '{value}' for marker '{marker}'. "
                f"Must be one of: {_SORTED_IHC_SCORE_VALUES}"
            )
    return _build_event("ihc_scoring", {"scores": dict(scores)})


def build_fish_decision(approved: bool) -> dict[str, Any]:
    """Build a fish_decision event.

    Args:
        approved: Whether the pathologist approved FISH reflex testing.

    Returns:
        Event dict with type ``fish_decision``.
    """
    return _build_event("fish_decision", {"approved": approved})


def build_fish_result(result: str) -> dict[str, Any]:
    """Build a fish_result event.

    Args:
        result: ``"amplified"``, ``"not_amplified"``, or ``"qns"``.

    Raises:
        ValueError: If result is not valid.
    """
    if result not in VALID_FISH_RESULTS:
        raise ValueError(f"Invalid result '{result}'. Must be one of: {_SORTED_FISH_RESULTS}")
    return _build_event("fish_result", {"result": result})


def build_missing_info_received(
    resolved_fields: list[str] | None = None,
) -> dict[str, Any]:
    """Build a missing_info_received event.

    Args:
        resolved_fields: List of field names that were resolved, or
            ``None`` for pass-through states where no specific fields
            are relevant.

    Returns:
        Event dict with type ``missing_info_received``.
    """
    data: dict[str, Any] = {}
    if resolved_fields is not None:
        data["resolved_fields"] = list(resolved_fields)
    return _build_event("missing_info_received", data)


def build_resulting_review(outcome: str) -> dict[str, Any]:
    """Build a resulting_review event.

    Args:
        outcome: ``"advance"`` (proceed to signout) or ``"hold"``
            (flag present, hold for resolution).

    Raises:
        ValueError: If outcome is not valid.
    """
    _validate_outcome(outcome, VALID_RESULTING_REVIEW_OUTCOMES, _SORTED_RESULTING_REVIEW)
    return _build_event("resulting_review", {"outcome": outcome})


def build_pathologist_signout(reportable_tests: Sequence[str]) -> dict[str, Any]:
    """Build a pathologist_signout event.

    Args:
        reportable_tests: List of test names selected for the report.

    Raises:
        ValueError: If reportable_tests is empty.
    """
    if not reportable_tests:
        raise ValueError("reportable_tests must not be empty")
    return _build_event("pathologist_signout", {"reportable_tests": list(reportable_tests)})


def build_report_generated() -> dict[str, Any]:
    """Build a report_generated event."""
    return _build_event("report_generated", {"outcome": "success"})
