"""Data models for the laboratory workflow routing system.

Defines dataclasses for all 5 persistence entities (Order, Slide, Event,
Decision, Run) plus utility functions for field validation, log sanitization,
panel expansion, and slide count calculation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# Maximum field lengths for string fields that accept untrusted input.
# These fields will flow into LLM prompts — enforce limits to prevent
# prompt injection via oversized payloads.
FIELD_MAX_LENGTHS: dict[str, int] = {
    "order_id": 100,
    "scenario_id": 100,
    "patient_name": 200,
    "patient_sex": 10,
    "specimen_type": 100,
    "anatomic_site": 100,
    "fixative": 50,
    "priority": 20,
    "current_state": 50,
    "slide_id": 100,
    "test_assignment": 50,
    "status": 50,
    "qc_result": 100,
    "event_id": 100,
    "event_type": 100,
    "decision_id": 100,
    "run_id": 100,
    "model_id": 100,
    "predicted_next_state": 50,
    "expected_next_state": 50,
    "prompt_template_version": 100,
    "scenario_set_version": 100,
}

# Control character pattern: ANSI escapes first (multi-char), then single control chars
_CONTROL_CHAR_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]|[\x00-\x1f\x7f]")

# Panel definitions — only "Breast IHC Panel" is pre-defined. DCIS and
# atypical panels are pathologist-specified via event data, not lookups.
_PANELS: dict[str, list[str]] = {
    "Breast IHC Panel": ["ER", "PR", "HER2", "Ki-67"],
}

# Slide count components (see data-model.md § Slide Count)
_HE_SLIDE_COUNT = 1
_BACKUP_SLIDE_COUNT = 2

# Valid workflow states (see docs/workflow/workflow-overview.md)
VALID_STATES: frozenset[str] = frozenset(
    {
        "ACCESSIONING",
        "ACCEPTED",
        "MISSING_INFO_HOLD",
        "MISSING_INFO_PROCEED",
        "DO_NOT_PROCESS",
        "SAMPLE_PREP_PROCESSING",
        "SAMPLE_PREP_EMBEDDING",
        "SAMPLE_PREP_SECTIONING",
        "SAMPLE_PREP_QC",
        "HE_STAINING",
        "HE_QC",
        "PATHOLOGIST_HE_REVIEW",
        "IHC_STAINING",
        "IHC_QC",
        "IHC_SCORING",
        "SUGGEST_FISH_REFLEX",
        "FISH_SEND_OUT",
        "RESULTING_HOLD",
        "RESULTING",
        "PATHOLOGIST_SIGNOUT",
        "REPORT_GENERATION",
        "ORDER_COMPLETE",
        "ORDER_TERMINATED",
        "ORDER_TERMINATED_QNS",
    }
)

# Valid flags (see docs/workflow/rule-catalog.md § Flags Reference)
VALID_FLAGS: frozenset[str] = frozenset(
    {
        "MISSING_INFO_PROCEED",
        "FIXATION_WARNING",
        "RECUT_REQUESTED",
        "HER2_FIXATION_REJECT",
        "FISH_SUGGESTED",
    }
)

# Valid slide statuses (see docs/technical/data-model.md § Slides Table)
VALID_SLIDE_STATUSES: frozenset[str] = frozenset(
    {
        "sectioned",
        "stain_pending",
        "stain_complete",
        "qc_pass",
        "qc_fail",
        "scored",
        "cancelled",
    }
)


def validate_field_length(field_name: str, value: str | None) -> None:
    """Raise ValueError if a string field exceeds its maximum length.

    Only checks fields listed in FIELD_MAX_LENGTHS. None values are skipped.
    """
    if value is None:
        return
    max_len = FIELD_MAX_LENGTHS.get(field_name)
    if max_len is not None and len(value) > max_len:
        raise ValueError(f"Field '{field_name}' exceeds maximum length ({len(value)} > {max_len})")


def sanitize_for_log(value: str, max_length: int = 200) -> str:
    """Strip control characters and truncate for safe log output.

    These values originate from untrusted input that will flow into LLM
    prompts. Stripping control characters prevents log injection and
    reduces prompt manipulation surface.
    """
    cleaned = _CONTROL_CHAR_RE.sub("", value)
    if len(cleaned) > max_length:
        return cleaned[:max_length] + "..."
    return cleaned


def expand_panel(test_name: str) -> list[str]:
    """Expand a panel name to its constituent tests.

    "Breast IHC Panel" expands to ["ER", "PR", "HER2", "Ki-67"].
    Individual test names pass through as single-element lists.
    """
    return list(_PANELS.get(test_name, [test_name]))


def calculate_slide_count(ordered_tests: list[str]) -> int:
    """Calculate initial slide count at sectioning.

    Slide count = number of ordered tests + 1 (H&E) + 2 (backup).
    """
    return len(ordered_tests) + _HE_SLIDE_COUNT + _BACKUP_SLIDE_COUNT


def _validate_order_fields(obj: Order) -> None:
    """Validate string field lengths, state, and flags on Order."""
    for fname in (
        "order_id",
        "scenario_id",
        "patient_name",
        "patient_sex",
        "specimen_type",
        "anatomic_site",
        "fixative",
        "priority",
        "current_state",
    ):
        validate_field_length(fname, getattr(obj, fname))
    if obj.current_state not in VALID_STATES:
        raise ValueError(
            f"Invalid state '{obj.current_state}'. Must be one of: {sorted(VALID_STATES)}"
        )
    for flag in obj.flags:
        if flag not in VALID_FLAGS:
            raise ValueError(f"Invalid flag '{flag}'. Must be one of: {sorted(VALID_FLAGS)}")
    # Reject unexpanded panel names in ordered_tests (panels must be
    # expanded by the harness at order creation per data-model spec).
    for test in obj.ordered_tests:
        if test in _PANELS:
            raise ValueError(
                f"Panel name '{test}' found in ordered_tests. "
                f"Expand panels before creating Order (use expand_panel())."
            )


def _validate_slide_fields(obj: Slide) -> None:
    """Validate string field lengths and status on Slide."""
    for fname in (
        "slide_id",
        "order_id",
        "test_assignment",
        "status",
        "qc_result",
    ):
        validate_field_length(fname, getattr(obj, fname))
    if obj.status not in VALID_SLIDE_STATUSES:
        raise ValueError(
            f"Invalid slide status '{obj.status}'. Must be one of: {sorted(VALID_SLIDE_STATUSES)}"
        )


@dataclass
class Order:
    """A laboratory order tracking workflow state."""

    order_id: str
    scenario_id: str
    patient_name: str | None
    patient_age: int | None
    patient_sex: str | None
    specimen_type: str
    anatomic_site: str
    fixative: str
    fixation_time_hours: float | None
    ordered_tests: list[str]
    priority: str
    billing_info_present: bool
    current_state: str
    flags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        _validate_order_fields(self)


@dataclass
class Slide:
    """An individual slide in a laboratory order."""

    slide_id: str
    order_id: str
    test_assignment: str
    status: str
    qc_result: str | None = None
    score_result: dict[str, Any] | None = None
    reported: bool = False
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        _validate_slide_fields(self)


def _validate_event_fields(obj: Event) -> None:
    """Validate string field lengths on Event."""
    for fname in ("event_id", "order_id", "event_type"):
        validate_field_length(fname, getattr(obj, fname))


def _validate_decision_fields(obj: Decision) -> None:
    """Validate string field lengths on Decision."""
    for fname in (
        "decision_id",
        "run_id",
        "event_id",
        "order_id",
        "model_id",
        "predicted_next_state",
        "expected_next_state",
    ):
        validate_field_length(fname, getattr(obj, fname))


@dataclass
class Event:
    """An immutable event in the order lifecycle."""

    event_id: str
    order_id: str
    # Sequential position within the order's event stream; used for ordering.
    step_number: int
    # Label for the event (e.g., "order_received", "qc_result_received").
    event_type: str
    # Payload specific to the event type; schema varies by event_type.
    # Stored as JSON in the database; deserialized to dict on read.
    event_data: dict[str, Any]
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        _validate_event_fields(self)


@dataclass
class Decision:
    """A model's decision in response to an event."""

    decision_id: str
    run_id: str
    event_id: str
    order_id: str
    model_id: str
    # Full order state at the time of inference; stored as JSON for audit
    # and reproducibility.  Mirrors Order fields, not a foreign key lookup.
    order_state_snapshot: dict[str, Any]
    # Complete prompt payload sent to the model; stored for replay.
    model_input: dict[str, Any]
    # Raw structured response from the model (next_state, applied_rules,
    # flags, reasoning).
    model_output: dict[str, Any]
    predicted_next_state: str
    # Rule IDs the model claimed to apply (e.g., ["ACC-008", "ACC-010"]).
    predicted_applied_rules: list[str]
    # Flag strings the model claimed to set (e.g., ["FIXATION_WARNING"]).
    predicted_flags: list[str]
    # Ground-truth next state from the scenario definition.
    expected_next_state: str
    # Ground-truth rule IDs from the scenario definition.
    expected_applied_rules: list[str]
    # Ground-truth flags from the scenario definition.
    expected_flags: list[str]
    # Per-dimension scoring booleans computed at evaluation time.
    state_correct: bool
    rules_correct: bool
    flags_correct: bool
    latency_ms: int
    input_tokens: int
    output_tokens: int
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        _validate_decision_fields(self)


def _validate_query_decision_fields(obj: QueryDecision) -> None:
    """Validate string field lengths and list element types on QueryDecision."""
    for fname in ("decision_id", "run_id", "scenario_id", "model_id"):
        validate_field_length(fname, getattr(obj, fname))
    for field_name, id_list in (
        ("predicted_order_ids", obj.predicted_order_ids),
        ("expected_order_ids", obj.expected_order_ids),
    ):
        for order_id in id_list:
            if not isinstance(order_id, str):
                raise TypeError(f"{field_name} must contain strings, got {type(order_id).__name__}")


@dataclass
class QueryDecision:
    """A model's decision in response to a query scenario."""

    decision_id: str
    run_id: str
    scenario_id: str
    model_id: str
    tier: int
    answer_type: str
    database_state_snapshot: dict[str, Any]
    model_input: dict[str, Any]
    model_output: dict[str, Any]
    predicted_order_ids: list[str]
    expected_order_ids: list[str]
    order_ids_correct: bool
    precision: float
    recall: float
    f1: float
    failure_type: str | None
    latency_ms: int
    input_tokens: int
    output_tokens: int
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        _validate_query_decision_fields(self)


@dataclass
class Run:
    """A complete evaluation pass."""

    run_id: str
    prompt_template_version: str
    scenario_set_version: str
    model_id: str
    run_number: int
    started_at: datetime
    completed_at: datetime | None = None
    notes: str | None = None
    aborted: bool = False
