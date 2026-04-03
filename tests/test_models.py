"""Tests for workflow data models and utility functions."""

from datetime import datetime

import pytest

from src.workflow.models import (
    VALID_FLAGS,
    VALID_SLIDE_STATUSES,
    VALID_STATES,
    Decision,
    Event,
    Order,
    Run,
    Slide,
    calculate_slide_count,
    expand_panel,
    sanitize_for_log,
    validate_field_length,
)

# --- Dataclass creation ---


def _make_order(**overrides: object) -> Order:
    defaults: dict[str, object] = {
        "order_id": "ORD-001",
        "scenario_id": "SC-001",
        "patient_name": "TESTPATIENT-0001, Jane",
        "patient_age": 55,
        "patient_sex": "F",
        "specimen_type": "biopsy",
        "anatomic_site": "breast",
        "fixative": "formalin",
        "fixation_time_hours": 24.0,
        "ordered_tests": ["ER", "PR", "HER2", "Ki-67"],
        "priority": "routine",
        "billing_info_present": True,
        "current_state": "ACCESSIONING",
        "flags": [],
        "created_at": datetime(2025, 1, 1, 12, 0, 0),
        "updated_at": datetime(2025, 1, 1, 12, 0, 0),
    }
    defaults.update(overrides)
    return Order(**defaults)  # type: ignore[arg-type]


def test_order_creation() -> None:
    order = _make_order()
    assert order.order_id == "ORD-001"
    assert order.patient_name == "TESTPATIENT-0001, Jane"
    assert order.ordered_tests == ["ER", "PR", "HER2", "Ki-67"]
    assert order.flags == []


def test_slide_creation() -> None:
    slide = Slide(
        slide_id="SL-001",
        order_id="ORD-001",
        test_assignment="ER",
        status="sectioned",
        created_at=datetime(2025, 1, 1),
        updated_at=datetime(2025, 1, 1),
    )
    assert slide.slide_id == "SL-001"
    assert slide.qc_result is None
    assert slide.score_result is None
    assert slide.reported is False


def test_event_creation() -> None:
    event = Event(
        event_id="EVT-001",
        order_id="ORD-001",
        step_number=1,
        event_type="order_received",
        event_data={"source": "lis"},
        created_at=datetime(2025, 1, 1),
    )
    assert event.event_type == "order_received"
    assert event.event_data == {"source": "lis"}


def test_decision_creation() -> None:
    decision = Decision(
        decision_id="DEC-001",
        run_id="RUN-001",
        event_id="EVT-001",
        order_id="ORD-001",
        model_id="llama3",
        order_state_snapshot={"current_state": "ACCESSIONING"},
        model_input={"prompt": "test"},
        model_output={"next_state": "ACCEPTED"},
        predicted_next_state="ACCEPTED",
        predicted_applied_rules=["ACC-008"],
        predicted_flags=[],
        expected_next_state="ACCEPTED",
        expected_applied_rules=["ACC-008"],
        expected_flags=[],
        state_correct=True,
        rules_correct=True,
        flags_correct=True,
        latency_ms=150,
        input_tokens=500,
        output_tokens=50,
        created_at=datetime(2025, 1, 1),
    )
    assert decision.state_correct is True
    assert decision.predicted_applied_rules == ["ACC-008"]


def test_run_creation() -> None:
    run = Run(
        run_id="RUN-001",
        prompt_template_version="v1",
        scenario_set_version="v1",
        model_id="llama3",
        run_number=1,
        started_at=datetime(2025, 1, 1),
    )
    assert run.completed_at is None
    assert run.notes is None


# --- Panel expansion ---


def test_expand_panel_breast_ihc() -> None:
    result = expand_panel("Breast IHC Panel")
    assert result == ["ER", "PR", "HER2", "Ki-67"]


def test_expand_panel_individual_test() -> None:
    assert expand_panel("ER") == ["ER"]
    assert expand_panel("HER2") == ["HER2"]


def test_expand_panel_unknown_test() -> None:
    assert expand_panel("SomeNewTest") == ["SomeNewTest"]


# --- Slide count ---


def test_slide_count_four_tests() -> None:
    assert calculate_slide_count(["ER", "PR", "HER2", "Ki-67"]) == 7


def test_slide_count_two_tests() -> None:
    assert calculate_slide_count(["ER", "PR"]) == 5


def test_slide_count_zero_tests() -> None:
    assert calculate_slide_count([]) == 3


# --- Field length validation ---


def test_validate_field_length_valid() -> None:
    validate_field_length("patient_name", "TESTPATIENT-0001, Jane")


def test_validate_field_length_none_passes() -> None:
    validate_field_length("patient_name", None)


def test_validate_field_length_at_limit() -> None:
    validate_field_length("patient_name", "x" * 200)


def test_validate_field_length_exceeds() -> None:
    with pytest.raises(ValueError, match="exceeds maximum length"):
        validate_field_length("patient_name", "x" * 201)


def test_validate_field_length_unknown_field() -> None:
    # Unknown fields are not checked
    validate_field_length("unknown_field", "x" * 10000)


def test_order_post_init_rejects_long_name() -> None:
    with pytest.raises(ValueError, match="patient_name"):
        _make_order(patient_name="x" * 201)


def test_slide_post_init_rejects_long_id() -> None:
    with pytest.raises(ValueError, match="slide_id"):
        Slide(
            slide_id="x" * 101,
            order_id="ORD-001",
            test_assignment="ER",
            status="sectioned",
        )


# --- Log sanitization ---


def test_sanitize_strips_newlines() -> None:
    assert sanitize_for_log("line1\nline2") == "line1line2"


def test_sanitize_strips_tabs() -> None:
    assert sanitize_for_log("col1\tcol2") == "col1col2"


def test_sanitize_strips_ansi_escapes() -> None:
    assert sanitize_for_log("\x1b[31mred\x1b[0m") == "red"


def test_sanitize_truncates() -> None:
    long_input = "a" * 300
    result = sanitize_for_log(long_input, max_length=50)
    assert len(result) == 53  # 50 + "..."
    assert result.endswith("...")


def test_sanitize_no_truncation_under_limit() -> None:
    result = sanitize_for_log("short string")
    assert result == "short string"


# --- State validation ---


def test_order_rejects_invalid_state() -> None:
    with pytest.raises(ValueError, match="Invalid state"):
        _make_order(current_state="BOGUS_STATE")


def test_order_accepts_all_valid_states() -> None:
    for state in VALID_STATES:
        order = _make_order(current_state=state)
        assert order.current_state == state


# --- Flag validation ---


def test_order_rejects_invalid_flag() -> None:
    with pytest.raises(ValueError, match="Invalid flag"):
        _make_order(flags=["NOT_A_REAL_FLAG"])


def test_order_accepts_valid_flags() -> None:
    order = _make_order(flags=list(VALID_FLAGS))
    assert set(order.flags) == VALID_FLAGS


# --- Slide status validation ---


def test_slide_rejects_invalid_status() -> None:
    with pytest.raises(ValueError, match="Invalid slide status"):
        Slide(
            slide_id="SL-001",
            order_id="ORD-001",
            test_assignment="ER",
            status="BOGUS",
        )


def test_slide_accepts_valid_statuses() -> None:
    for status in VALID_SLIDE_STATUSES:
        slide = Slide(
            slide_id="SL-001",
            order_id="ORD-001",
            test_assignment="ER",
            status=status,
        )
        assert slide.status == status


# --- Panel name guard ---


def test_order_rejects_unexpanded_panel_name() -> None:
    with pytest.raises(ValueError, match="Panel name"):
        _make_order(ordered_tests=["Breast IHC Panel"])


# --- Event validation ---


def test_event_rejects_long_event_id() -> None:
    with pytest.raises(ValueError, match="event_id"):
        Event(
            event_id="x" * 101,
            order_id="ORD-001",
            step_number=1,
            event_type="order_received",
            event_data={},
        )


# --- Decision validation ---


def test_decision_rejects_long_decision_id() -> None:
    with pytest.raises(ValueError, match="decision_id"):
        Decision(
            decision_id="x" * 101,
            run_id="RUN-001",
            event_id="EVT-001",
            order_id="ORD-001",
            model_id="llama3",
            order_state_snapshot={},
            model_input={},
            model_output={},
            predicted_next_state="ACCEPTED",
            predicted_applied_rules=[],
            predicted_flags=[],
            expected_next_state="ACCEPTED",
            expected_applied_rules=[],
            expected_flags=[],
            state_correct=True,
            rules_correct=True,
            flags_correct=True,
            latency_ms=100,
            input_tokens=100,
            output_tokens=10,
        )
