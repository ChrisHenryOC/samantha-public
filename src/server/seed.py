"""Seed the live database with demo orders for development and testing.

Creates 30 orders covering all 24 workflow states, all 5 flags, and multiple
blockage types. Each order has appropriate slides and events to justify its
current state. Idempotent — skips seeding if seed orders already exist.

Patient names use the obviously synthetic TESTPATIENT-NNNN format to avoid
any appearance of real PHI.

Run via: ``uv run python -m src.server.seed``
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, NamedTuple

from src.server.config import load_server_config
from src.workflow.database import Database
from src.workflow.models import Event, Order, Slide, expand_panel

logger = logging.getLogger(__name__)

# Default IHC panel used for all seed orders.
_DEFAULT_PANEL = "Breast IHC Panel"

# Type alias for event/slide generator functions.
type EventsFn = Callable[[str, datetime], tuple[list[Event], list[Slide]]]

# First names cycled across patients (matches order_generator.py style).
_FIRST_NAMES: tuple[str, ...] = (
    "Sarah",
    "Michael",
    "Emily",
    "James",
    "Olivia",
    "Robert",
    "Sophia",
    "William",
    "Emma",
    "David",
    "Patricia",
    "Linda",
    "Elizabeth",
    "Jennifer",
    "Barbara",
    "Susan",
    "Jessica",
    "Karen",
    "Nancy",
    "Lisa",
    "Betty",
    "Dorothy",
    "Sandra",
    "Helen",
    "Ruth",
    "Maria",
    "Margaret",
    "Donna",
    "Carol",
    "Amanda",
)


def _patient_name(index: int) -> str:
    """Generate an obviously synthetic patient name."""
    first = _FIRST_NAMES[index % len(_FIRST_NAMES)]
    return f"TESTPATIENT-{index + 1:04d}, {first}"


class Patient(NamedTuple):
    """Synthetic patient data for seeding."""

    name: str | None
    age: int
    sex: str | None
    specimen_type: str
    anatomic_site: str


class OrderSpec(NamedTuple):
    """Specification for a single seed order."""

    order_id: str
    state: str
    priority: str
    flags: list[str]
    events_fn: EventsFn
    fixation_time_hours: float | None = 12.0
    billing_info_present: bool = True
    fixative: str = "10% NBF"


# --- Synthetic patient data (30 patients) ---

_PATIENTS = [
    # Accessioning phase (ORD-001 to ORD-006)
    Patient(_patient_name(0), 52, "F", "Core Needle Biopsy", "Left Breast"),
    Patient(_patient_name(1), 67, "F", "Core Needle Biopsy", "Right Breast"),
    Patient(
        None, 45, "F", "Core Needle Biopsy", "Left Breast"
    ),  # ORD-003: name=None triggers MISSING_INFO_HOLD
    Patient(_patient_name(3), 58, "F", "FNA", "Left Breast"),  # ORD-004: incompatible specimen
    Patient(_patient_name(4), 41, "F", "Excisional Biopsy", "Right Breast"),
    Patient(_patient_name(5), 63, "F", "Core Needle Biopsy", "Left Breast"),
    # Sample prep phase (ORD-007 to ORD-012)
    Patient(_patient_name(6), 49, "F", "Core Needle Biopsy", "Right Breast"),
    Patient(_patient_name(7), 71, "F", "Core Needle Biopsy", "Left Breast"),
    Patient(_patient_name(8), 38, "F", "Core Needle Biopsy", "Right Breast"),
    Patient(_patient_name(9), 55, "F", "Core Needle Biopsy", "Left Breast"),
    Patient(_patient_name(10), 60, "F", "Excisional Biopsy", "Right Breast"),
    Patient(_patient_name(11), 47, "F", "Core Needle Biopsy", "Left Breast"),
    # H&E phase (ORD-013 to ORD-015)
    Patient(_patient_name(12), 73, "F", "Core Needle Biopsy", "Right Breast"),
    Patient(_patient_name(13), 65, "F", "Core Needle Biopsy", "Left Breast"),
    Patient(_patient_name(14), 50, "F", "Excisional Biopsy", "Left Breast"),
    # IHC phase (ORD-016 to ORD-021)
    Patient(_patient_name(15), 44, "F", "Core Needle Biopsy", "Right Breast"),
    Patient(_patient_name(16), 69, "F", "Core Needle Biopsy", "Left Breast"),
    Patient(_patient_name(17), 53, "F", "Core Needle Biopsy", "Right Breast"),
    Patient(_patient_name(18), 61, "F", "Core Needle Biopsy", "Left Breast"),
    Patient(_patient_name(19), 42, "F", "Core Needle Biopsy", "Right Breast"),
    Patient(_patient_name(20), 57, "F", "Excisional Biopsy", "Left Breast"),
    # Resulting phase (ORD-022 to ORD-026)
    Patient(_patient_name(21), 66, "F", "Core Needle Biopsy", "Right Breast"),
    Patient(_patient_name(22), 48, "F", "Core Needle Biopsy", "Left Breast"),
    Patient(_patient_name(23), 74, "F", "Core Needle Biopsy", "Right Breast"),
    Patient(_patient_name(24), 39, "F", "Excisional Biopsy", "Left Breast"),
    Patient(_patient_name(25), 56, "F", "Core Needle Biopsy", "Right Breast"),
    # Terminal (ORD-027 to ORD-030)
    Patient(_patient_name(26), 70, "F", "Core Needle Biopsy", "Left Breast"),
    Patient(_patient_name(27), 43, "F", "Core Needle Biopsy", "Right Breast"),
    Patient(_patient_name(28), 62, "F", "Core Needle Biopsy", "Left Breast"),
    Patient(_patient_name(29), 51, "F", "Core Needle Biopsy", "Right Breast"),
]


def _uid() -> str:
    return str(uuid.uuid4())


def _make_event(
    order_id: str,
    step: int,
    event_type: str,
    event_data: dict[str, object],
    base_time: datetime,
    hours_offset: float,
) -> Event:
    return Event(
        event_id=_uid(),
        order_id=order_id,
        step_number=step,
        event_type=event_type,
        event_data=event_data,
        created_at=base_time + timedelta(hours=hours_offset),
    )


def _make_slide(
    order_id: str,
    test: str,
    status: str = "sectioned",
    qc_result: str | None = None,
    score_result: dict[str, Any] | None = None,
) -> Slide:
    return Slide(
        slide_id=f"SLD-{uuid.uuid4().hex[:8]}",
        order_id=order_id,
        test_assignment=test,
        status=status,
        qc_result=qc_result,
        score_result=score_result,
    )


# --- Event sequences for each state ---
# Each returns (events, slides) appropriate for the order's target state.


def _events_order_received(order_id: str, base: datetime) -> tuple[list[Event], list[Slide]]:
    """Single order_received event — used for ACCESSIONING, MISSING_INFO_HOLD,
    DO_NOT_PROCESS, and ORDER_TERMINATED states."""
    events = [
        _make_event(order_id, 1, "order_received", {}, base, 0),
    ]
    return events, []


def _events_do_not_process(order_id: str, base: datetime) -> tuple[list[Event], list[Slide]]:
    """Order rejected at accessioning — incompatible specimen."""
    events = [
        _make_event(
            order_id,
            1,
            "order_received",
            {
                "rejection_reason": "incompatible_specimen",
                "detail": "FNA specimen with non-formalin fixative is not processable",
            },
            base,
            0,
        ),
    ]
    return events, []


def _events_accepted(order_id: str, base: datetime) -> tuple[list[Event], list[Slide]]:
    events = [
        _make_event(order_id, 1, "order_received", {}, base, 0),
        _make_event(
            order_id,
            2,
            "order_received",
            {"all_fields_valid": True, "fixation_adequate": True},
            base,
            0.5,
        ),
    ]
    return events, []


def _events_missing_info_proceed(order_id: str, base: datetime) -> tuple[list[Event], list[Slide]]:
    events = [
        _make_event(order_id, 1, "order_received", {}, base, 0),
        _make_event(
            order_id,
            2,
            "order_received",
            {"missing_info": True, "can_proceed": True},
            base,
            0.5,
        ),
    ]
    return events, []


def _events_sample_prep_processing(
    order_id: str, base: datetime
) -> tuple[list[Event], list[Slide]]:
    events = [
        _make_event(order_id, 1, "order_received", {}, base, 0),
        _make_event(
            order_id,
            2,
            "order_received",
            {"all_fields_valid": True, "fixation_adequate": True},
            base,
            0.5,
        ),
        _make_event(
            order_id,
            3,
            "grossing_complete",
            {"tissue_adequate": True, "sections_taken": 4},
            base,
            2,
        ),
    ]
    return events, []


def _events_sample_prep_embedding(order_id: str, base: datetime) -> tuple[list[Event], list[Slide]]:
    events, slides = _events_sample_prep_processing(order_id, base)
    events.append(_make_event(order_id, 4, "processing_complete", {}, base, 6))
    return events, slides


def _events_sample_prep_sectioning(
    order_id: str, base: datetime
) -> tuple[list[Event], list[Slide]]:
    events, slides = _events_sample_prep_embedding(order_id, base)
    events.append(_make_event(order_id, 5, "embedding_complete", {}, base, 8))
    return events, slides


def _events_sample_prep_qc(order_id: str, base: datetime) -> tuple[list[Event], list[Slide]]:
    events, _ = _events_sample_prep_sectioning(order_id, base)
    events.append(_make_event(order_id, 6, "sectioning_complete", {"sections_cut": 4}, base, 10))
    slides = [_make_slide(order_id, "H&E")]
    return events, slides


def _events_he_staining(order_id: str, base: datetime) -> tuple[list[Event], list[Slide]]:
    events, _ = _events_sample_prep_qc(order_id, base)
    events.append(_make_event(order_id, 7, "sample_prep_qc", {"qc_pass": True}, base, 11))
    slides = [_make_slide(order_id, "H&E", status="stain_pending")]
    return events, slides


def _events_he_qc(order_id: str, base: datetime) -> tuple[list[Event], list[Slide]]:
    events, _ = _events_he_staining(order_id, base)
    events.append(_make_event(order_id, 8, "he_staining_complete", {}, base, 13))
    slides = [_make_slide(order_id, "H&E", status="stain_complete")]
    return events, slides


def _events_pathologist_he_review(order_id: str, base: datetime) -> tuple[list[Event], list[Slide]]:
    events, _ = _events_he_qc(order_id, base)
    events.append(_make_event(order_id, 9, "he_qc", {"qc_pass": True}, base, 14))
    slides = [_make_slide(order_id, "H&E", status="qc_pass", qc_result="pass")]
    return events, slides


def _events_ihc_staining(order_id: str, base: datetime) -> tuple[list[Event], list[Slide]]:
    events, _ = _events_pathologist_he_review(order_id, base)
    events.append(
        _make_event(
            order_id,
            10,
            "pathologist_he_review",
            {
                "diagnosis": "Invasive Ductal Carcinoma",
                "ihc_panel": _DEFAULT_PANEL,
            },
            base,
            16,
        ),
    )
    he_slide = _make_slide(order_id, "H&E", status="qc_pass", qc_result="pass")
    ihc_tests = expand_panel(_DEFAULT_PANEL)
    ihc_slides = [_make_slide(order_id, t, status="stain_pending") for t in ihc_tests]
    return events, [he_slide, *ihc_slides]


def _events_ihc_qc(order_id: str, base: datetime) -> tuple[list[Event], list[Slide]]:
    events, _ = _events_ihc_staining(order_id, base)
    events.append(_make_event(order_id, 11, "ihc_staining_complete", {}, base, 20))
    he_slide = _make_slide(order_id, "H&E", status="qc_pass", qc_result="pass")
    ihc_tests = expand_panel(_DEFAULT_PANEL)
    ihc_slides = [_make_slide(order_id, t, status="stain_complete") for t in ihc_tests]
    return events, [he_slide, *ihc_slides]


def _events_ihc_scoring(order_id: str, base: datetime) -> tuple[list[Event], list[Slide]]:
    events, _ = _events_ihc_qc(order_id, base)
    ihc_tests = expand_panel(_DEFAULT_PANEL)
    step = 12
    for test in ihc_tests:
        events.append(
            _make_event(
                order_id,
                step,
                "ihc_qc",
                {"test": test, "qc_pass": True},
                base,
                22 + step * 0.5,
            )
        )
        step += 1
    he_slide = _make_slide(order_id, "H&E", status="qc_pass", qc_result="pass")
    ihc_slides = [_make_slide(order_id, t, status="qc_pass", qc_result="pass") for t in ihc_tests]
    return events, [he_slide, *ihc_slides]


def _events_suggest_fish_reflex(order_id: str, base: datetime) -> tuple[list[Event], list[Slide]]:
    events, _ = _events_ihc_scoring(order_id, base)
    ihc_tests = expand_panel(_DEFAULT_PANEL)
    step = len(events) + 1
    for test in ihc_tests:
        score = "equivocal" if test == "HER2" else "positive"
        events.append(
            _make_event(
                order_id,
                step,
                "ihc_scoring",
                {"test": test, "score": score, "equivocal": test == "HER2"},
                base,
                24 + step * 0.5,
            )
        )
        step += 1
    he_slide = _make_slide(order_id, "H&E", status="qc_pass", qc_result="pass")
    ihc_slides = [
        _make_slide(
            order_id,
            t,
            status="scored",
            qc_result="pass",
            score_result=(
                {"value": "equivocal", "equivocal": True}
                if t == "HER2"
                else {"value": "positive", "equivocal": False}
            ),
        )
        for t in ihc_tests
    ]
    return events, [he_slide, *ihc_slides]


def _events_fish_send_out(order_id: str, base: datetime) -> tuple[list[Event], list[Slide]]:
    events, slides = _events_suggest_fish_reflex(order_id, base)
    step = len(events) + 1
    events.append(
        _make_event(
            order_id,
            step,
            "fish_decision",
            {"approved": True},
            base,
            30,
        )
    )
    return events, slides


def _events_resulting(order_id: str, base: datetime) -> tuple[list[Event], list[Slide]]:
    events, _ = _events_ihc_scoring(order_id, base)
    ihc_tests = expand_panel(_DEFAULT_PANEL)
    step = len(events) + 1
    for test in ihc_tests:
        events.append(
            _make_event(
                order_id,
                step,
                "ihc_scoring",
                {"test": test, "score": "positive"},
                base,
                22 + step * 0.5,
            )
        )
        step += 1
    he_slide = _make_slide(order_id, "H&E", status="qc_pass", qc_result="pass")
    ihc_slides = [
        _make_slide(
            order_id,
            t,
            status="scored",
            qc_result="pass",
            score_result={"value": "positive", "equivocal": False},
        )
        for t in ihc_tests
    ]
    return events, [he_slide, *ihc_slides]


def _events_resulting_hold(order_id: str, base: datetime) -> tuple[list[Event], list[Slide]]:
    events, slides = _events_resulting(order_id, base)
    step = len(events) + 1
    events.append(
        _make_event(
            order_id,
            step,
            "resulting_review",
            {"outcome": "hold"},
            base,
            28,
        )
    )
    return events, slides


def _events_pathologist_signout(order_id: str, base: datetime) -> tuple[list[Event], list[Slide]]:
    events, slides = _events_resulting(order_id, base)
    step = len(events) + 1
    events.append(
        _make_event(
            order_id,
            step,
            "resulting_review",
            {"outcome": "complete"},
            base,
            28,
        )
    )
    return events, slides


def _events_report_generation(order_id: str, base: datetime) -> tuple[list[Event], list[Slide]]:
    events, slides = _events_pathologist_signout(order_id, base)
    step = len(events) + 1
    events.append(
        _make_event(
            order_id,
            step,
            "pathologist_signout",
            {"reportable_tests": expand_panel(_DEFAULT_PANEL)},
            base,
            30,
        )
    )
    return events, slides


def _events_order_complete(order_id: str, base: datetime) -> tuple[list[Event], list[Slide]]:
    events, slides = _events_report_generation(order_id, base)
    step = len(events) + 1
    events.append(_make_event(order_id, step, "report_generated", {}, base, 31))
    return events, slides


def _events_order_terminated_qns(order_id: str, base: datetime) -> tuple[list[Event], list[Slide]]:
    """Order terminated due to insufficient tissue at grossing."""
    events = [
        _make_event(order_id, 1, "order_received", {}, base, 0),
        _make_event(
            order_id,
            2,
            "order_received",
            {"all_fields_valid": True, "fixation_adequate": True},
            base,
            0.5,
        ),
        _make_event(
            order_id,
            3,
            "grossing_complete",
            {"tissue_adequate": False, "outcome": "insufficient_tissue"},
            base,
            2,
        ),
    ]
    return events, []


# --- Order definitions ---

_ORDER_SPECS: list[OrderSpec] = [
    # === Accessioning Phase ===
    OrderSpec("ORD-001", "ACCESSIONING", "routine", [], _events_order_received),
    OrderSpec(
        "ORD-002",
        "ACCESSIONING",
        "rush",
        [],
        _events_order_received,
        fixation_time_hours=None,
    ),
    OrderSpec(
        "ORD-003",
        "MISSING_INFO_HOLD",
        "routine",
        [],
        _events_order_received,
    ),
    OrderSpec(
        "ORD-004",
        "DO_NOT_PROCESS",
        "routine",
        [],
        _events_do_not_process,
        fixative="fresh (unfixed)",
    ),
    OrderSpec("ORD-005", "ACCEPTED", "routine", [], _events_accepted),
    OrderSpec(
        "ORD-006",
        "MISSING_INFO_PROCEED",
        "routine",
        ["MISSING_INFO_PROCEED"],
        _events_missing_info_proceed,
        billing_info_present=False,
    ),
    # === Sample Prep Phase ===
    OrderSpec(
        "ORD-007",
        "SAMPLE_PREP_PROCESSING",
        "routine",
        [],
        _events_sample_prep_processing,
    ),
    OrderSpec(
        "ORD-008",
        "SAMPLE_PREP_EMBEDDING",
        "routine",
        [],
        _events_sample_prep_embedding,
    ),
    OrderSpec(
        "ORD-009",
        "SAMPLE_PREP_SECTIONING",
        "rush",
        [],
        _events_sample_prep_sectioning,
    ),
    OrderSpec(
        "ORD-010",
        "SAMPLE_PREP_SECTIONING",
        "routine",
        [],
        _events_sample_prep_sectioning,
    ),
    OrderSpec(
        "ORD-011",
        "SAMPLE_PREP_QC",
        "routine",
        [],
        _events_sample_prep_qc,
    ),
    OrderSpec(
        "ORD-012",
        "SAMPLE_PREP_QC",
        "routine",
        ["FIXATION_WARNING"],
        _events_sample_prep_qc,
        fixation_time_hours=6.5,  # Borderline — triggers warning, not rejection
    ),
    # === H&E Phase ===
    OrderSpec("ORD-013", "HE_STAINING", "routine", [], _events_he_staining),
    OrderSpec("ORD-014", "HE_QC", "routine", [], _events_he_qc),
    OrderSpec(
        "ORD-015",
        "PATHOLOGIST_HE_REVIEW",
        "rush",
        ["RECUT_REQUESTED"],  # Pathologist requested recut during H&E review
        _events_pathologist_he_review,
    ),
    # === IHC Phase ===
    OrderSpec("ORD-016", "IHC_STAINING", "routine", [], _events_ihc_staining),
    OrderSpec(
        "ORD-017",
        "IHC_STAINING",
        "routine",
        ["HER2_FIXATION_REJECT"],
        _events_ihc_staining,
        fixation_time_hours=4.0,  # Out of tolerance — justifies HER2 rejection
    ),
    OrderSpec("ORD-018", "IHC_QC", "routine", [], _events_ihc_qc),
    OrderSpec("ORD-019", "IHC_SCORING", "routine", [], _events_ihc_scoring),
    OrderSpec(
        "ORD-020",
        "SUGGEST_FISH_REFLEX",
        "routine",
        ["FISH_SUGGESTED"],
        _events_suggest_fish_reflex,
    ),
    OrderSpec(
        "ORD-021",
        "FISH_SEND_OUT",
        "routine",
        ["FISH_SUGGESTED"],
        _events_fish_send_out,
    ),
    # === Resulting Phase ===
    OrderSpec("ORD-022", "RESULTING", "routine", [], _events_resulting),
    OrderSpec(
        "ORD-023",
        "RESULTING_HOLD",
        "routine",
        ["MISSING_INFO_PROCEED"],
        _events_resulting_hold,
        billing_info_present=False,
    ),
    OrderSpec(
        "ORD-024",
        "PATHOLOGIST_SIGNOUT",
        "routine",
        [],
        _events_pathologist_signout,
    ),
    OrderSpec(
        "ORD-025",
        "REPORT_GENERATION",
        "routine",
        [],
        _events_report_generation,
    ),
    OrderSpec("ORD-026", "RESULTING", "rush", [], _events_resulting),
    # === Terminal States ===
    OrderSpec("ORD-027", "ORDER_COMPLETE", "routine", [], _events_order_complete),
    OrderSpec("ORD-028", "ORDER_COMPLETE", "rush", [], _events_order_complete),
    OrderSpec(
        "ORD-029",
        "ORDER_TERMINATED",
        "routine",
        [],
        _events_order_received,
    ),
    OrderSpec(
        "ORD-030",
        "ORDER_TERMINATED_QNS",
        "routine",
        [],
        _events_order_terminated_qns,
    ),
]

assert len(_PATIENTS) == len(_ORDER_SPECS), (
    f"_PATIENTS ({len(_PATIENTS)}) and _ORDER_SPECS ({len(_ORDER_SPECS)}) must have equal length"
)

_SEED_SCENARIO_ID = "seed"
_DEMO_SCENARIO_ID = "demo"


# --- Demo orders for P0 videos ---


_DEMO_PATIENTS = [
    # ORD-DEMO-001: valid order (routes to ACCEPTED)
    Patient(_patient_name(30), 52, "F", "Core Needle Biopsy", "Left Breast"),
    # ORD-DEMO-002: fixation_time=5.0h with HER2 (triggers ACC-006)
    Patient(_patient_name(31), 63, "F", "Core Needle Biopsy", "Right Breast"),
    # ORD-DEMO-003: 5 simultaneous defects (multi-rule scenario)
    # name=None (ACC-001), sex=None (ACC-002), site="Lung" (ACC-003),
    # fixation_time=5.0h+HER2 (ACC-006), billing=False (ACC-007)
    Patient(None, 55, None, "Core Needle Biopsy", "Lung"),
]

_DEMO_ORDER_SPECS: list[OrderSpec] = [
    OrderSpec(
        "ORD-DEMO-001",
        "ACCESSIONING",
        "routine",
        [],
        _events_order_received,
        fixation_time_hours=12.0,
        billing_info_present=True,
        fixative="10% NBF",
    ),
    OrderSpec(
        "ORD-DEMO-002",
        "ACCESSIONING",
        "routine",
        [],
        _events_order_received,
        fixation_time_hours=5.0,
        billing_info_present=True,
        fixative="10% NBF",
    ),
    OrderSpec(
        "ORD-DEMO-003",
        "ACCESSIONING",
        "routine",
        [],
        _events_order_received,
        fixation_time_hours=5.0,
        billing_info_present=False,
        fixative="10% NBF",
    ),
]


def _seed_order_specs(
    db: Database,
    specs: list[OrderSpec],
    patients: list[Patient],
    scenario_id: str,
    base_time: datetime,
) -> int:
    """Insert a batch of order specs into the database. Returns count created."""
    count = 0
    for i, spec in enumerate(specs):
        patient = patients[i]

        order = Order(
            order_id=spec.order_id,
            scenario_id=scenario_id,
            patient_name=patient.name,
            patient_age=patient.age,
            patient_sex=patient.sex,
            specimen_type=patient.specimen_type,
            anatomic_site=patient.anatomic_site,
            fixative=spec.fixative,
            fixation_time_hours=spec.fixation_time_hours,
            ordered_tests=expand_panel(_DEFAULT_PANEL),
            priority=spec.priority,
            billing_info_present=spec.billing_info_present,
            current_state=spec.state,
            flags=spec.flags,
            created_at=base_time + timedelta(hours=i),
            updated_at=base_time + timedelta(hours=i),
        )
        db.insert_order(order, _commit=False)

        order_base = base_time + timedelta(hours=i)
        events, slides = spec.events_fn(spec.order_id, order_base)

        for event in events:
            db.insert_event(event, _commit=False)
        for slide in slides:
            db.insert_slide(slide, _commit=False)

        count += 1
    return count


def seed_database(db: Database) -> int:
    """Seed the database with demo orders. Returns count of orders created.

    Idempotent — skips if seed orders already exist (checks scenario_id).
    Seeds both the 30 standard work-queue orders and 3 demo-specific orders
    for P0 video recordings.
    """
    total = 0

    # Standard seed orders
    cursor = db._connection.execute(
        "SELECT COUNT(*) FROM orders WHERE scenario_id = ?",
        (_SEED_SCENARIO_ID,),
    )
    existing_count: int = cursor.fetchone()[0]
    if existing_count > 0:
        logger.info("Database already has %d seed orders, skipping", existing_count)
    else:
        base_time = datetime.now() - timedelta(days=3)
        total += _seed_order_specs(db, _ORDER_SPECS, _PATIENTS, _SEED_SCENARIO_ID, base_time)
        db.commit()
        logger.info("Seeded %d standard orders", total)

    # Demo orders for P0 videos
    cursor = db._connection.execute(
        "SELECT COUNT(*) FROM orders WHERE scenario_id = ?",
        (_DEMO_SCENARIO_ID,),
    )
    demo_existing: int = cursor.fetchone()[0]
    if demo_existing > 0:
        logger.info("Database already has %d demo orders, skipping", demo_existing)
    else:
        base_time = datetime.now() - timedelta(hours=1)
        demo_count = _seed_order_specs(
            db, _DEMO_ORDER_SPECS, _DEMO_PATIENTS, _DEMO_SCENARIO_ID, base_time
        )
        db.commit()
        total += demo_count
        logger.info("Seeded %d demo orders", demo_count)

    return total


def main() -> None:
    """Entry point for ``python -m src.server.seed``."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    config = load_server_config()
    db_path = Path(config.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with Database(str(db_path)) as db:
        db.init_db()
        count = seed_database(db)

    if count > 0:
        print(f"Seeded {count} demo orders into {db_path}")
    else:
        print(f"Database at {db_path} already has data, skipping")


if __name__ == "__main__":
    main()
