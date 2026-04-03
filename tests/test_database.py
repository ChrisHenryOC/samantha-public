"""Tests for the SQLite persistence layer."""

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from src.workflow.database import Database
from src.workflow.models import Decision, Event, Order, QueryDecision, Run, Slide


@pytest.fixture()
def db(tmp_path: Path) -> Database:
    """Provide an initialized in-memory-like database in a temp directory."""
    db_path = tmp_path / "test.db"
    db_instance = Database(db_path)
    db_instance.__enter__()
    db_instance.init_db()
    yield db_instance  # type: ignore[misc]
    db_instance.__exit__(None, None, None)


def _make_order() -> Order:
    return Order(
        order_id="ORD-001",
        scenario_id="SC-001",
        patient_name="TESTPATIENT-0001, Jane",
        patient_age=55,
        patient_sex="F",
        specimen_type="biopsy",
        anatomic_site="breast",
        fixative="formalin",
        fixation_time_hours=24.0,
        ordered_tests=["ER", "PR", "HER2", "Ki-67"],
        priority="routine",
        billing_info_present=True,
        current_state="ACCESSIONING",
        flags=["MISSING_INFO_PROCEED"],
        created_at=datetime(2025, 1, 1, 12, 0, 0),
        updated_at=datetime(2025, 1, 1, 12, 0, 0),
    )


def _make_run() -> Run:
    return Run(
        run_id="RUN-001",
        prompt_template_version="v1",
        scenario_set_version="v1",
        model_id="llama3",
        run_number=1,
        started_at=datetime(2025, 1, 1, 10, 0, 0),
    )


# --- Table creation ---


def test_init_db_creates_tables(db: Database) -> None:
    cursor = db._connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = sorted(row[0] for row in cursor.fetchall())
    assert tables == [
        "decisions",
        "events",
        "orders",
        "query_decisions",
        "routing_decisions",
        "runs",
        "slides",
    ]


# --- Order round-trip ---


def test_order_round_trip(db: Database) -> None:
    order = _make_order()
    db.insert_order(order)
    loaded = db.get_order("ORD-001")

    assert loaded is not None
    assert loaded.order_id == order.order_id
    assert loaded.scenario_id == order.scenario_id
    assert loaded.patient_name == order.patient_name
    assert loaded.patient_age == order.patient_age
    assert loaded.patient_sex == order.patient_sex
    assert loaded.specimen_type == order.specimen_type
    assert loaded.anatomic_site == order.anatomic_site
    assert loaded.fixative == order.fixative
    assert loaded.fixation_time_hours == order.fixation_time_hours
    assert loaded.ordered_tests == ["ER", "PR", "HER2", "Ki-67"]
    assert loaded.priority == order.priority
    assert loaded.billing_info_present is True
    assert loaded.current_state == order.current_state
    assert loaded.flags == ["MISSING_INFO_PROCEED"]
    assert loaded.created_at == order.created_at
    assert loaded.updated_at == order.updated_at


def test_get_order_not_found(db: Database) -> None:
    assert db.get_order("NONEXISTENT") is None


def test_update_order_state(db: Database) -> None:
    order = _make_order()
    db.insert_order(order)

    new_time = datetime(2025, 1, 2, 8, 0, 0)
    db.update_order_state("ORD-001", "ACCEPTED", [], new_time)

    loaded = db.get_order("ORD-001")
    assert loaded is not None
    assert loaded.current_state == "ACCEPTED"
    assert loaded.flags == []
    assert loaded.updated_at == new_time


# --- Slide round-trip ---


def test_slide_round_trip(db: Database) -> None:
    db.insert_order(_make_order())

    slide = Slide(
        slide_id="SL-001",
        order_id="ORD-001",
        test_assignment="HER2",
        status="sectioned",
        qc_result=None,
        score_result={"score": "2+", "equivocal": True},
        reported=False,
        created_at=datetime(2025, 1, 1),
        updated_at=datetime(2025, 1, 1),
    )
    db.insert_slide(slide)

    slides = db.get_slides_for_order("ORD-001")
    assert len(slides) == 1
    loaded = slides[0]
    assert loaded.slide_id == "SL-001"
    assert loaded.test_assignment == "HER2"
    assert loaded.score_result == {"score": "2+", "equivocal": True}
    assert loaded.reported is False


def test_update_slide(db: Database) -> None:
    db.insert_order(_make_order())
    slide = Slide(
        slide_id="SL-001",
        order_id="ORD-001",
        test_assignment="ER",
        status="sectioned",
        created_at=datetime(2025, 1, 1),
        updated_at=datetime(2025, 1, 1),
    )
    db.insert_slide(slide)

    new_time = datetime(2025, 1, 2)
    db.update_slide(
        "SL-001",
        status="qc_pass",
        qc_result="acceptable",
        reported=True,
        updated_at=new_time,
    )

    slides = db.get_slides_for_order("ORD-001")
    loaded = slides[0]
    assert loaded.status == "qc_pass"
    assert loaded.qc_result == "acceptable"
    assert loaded.reported is True
    assert loaded.updated_at == new_time


def test_update_slide_rejects_invalid_field(db: Database) -> None:
    with pytest.raises(ValueError, match="Cannot update slide fields"):
        db.update_slide("SL-001", order_id="ORD-999")


# --- Event round-trip ---


def test_event_round_trip(db: Database) -> None:
    db.insert_order(_make_order())

    event = Event(
        event_id="EVT-001",
        order_id="ORD-001",
        step_number=1,
        event_type="order_received",
        event_data={"source": "lis", "priority": "routine"},
        created_at=datetime(2025, 1, 1),
    )
    db.insert_event(event)

    events = db.get_events_for_order("ORD-001")
    assert len(events) == 1
    loaded = events[0]
    assert loaded.event_id == "EVT-001"
    assert loaded.event_type == "order_received"
    assert loaded.event_data == {"source": "lis", "priority": "routine"}


def test_events_ordered_by_step_number(db: Database) -> None:
    db.insert_order(_make_order())

    for i in [3, 1, 2]:
        db.insert_event(
            Event(
                event_id=f"EVT-{i:03d}",
                order_id="ORD-001",
                step_number=i,
                event_type="order_received",
                event_data={},
                created_at=datetime(2025, 1, 1),
            )
        )

    events = db.get_events_for_order("ORD-001")
    assert [e.step_number for e in events] == [1, 2, 3]


# --- Decision round-trip ---


def test_decision_round_trip(db: Database) -> None:
    db.insert_order(_make_order())
    db.insert_run(_make_run())
    db.insert_event(
        Event(
            event_id="EVT-001",
            order_id="ORD-001",
            step_number=1,
            event_type="order_received",
            event_data={},
            created_at=datetime(2025, 1, 1),
        )
    )

    decision = Decision(
        decision_id="DEC-001",
        run_id="RUN-001",
        event_id="EVT-001",
        order_id="ORD-001",
        model_id="llama3",
        order_state_snapshot={"current_state": "ACCESSIONING", "flags": []},
        model_input={"prompt": "evaluate order"},
        model_output={"next_state": "ACCEPTED", "applied_rules": ["ACC-008"]},
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
    db.insert_decision(decision)

    decisions = db.get_decisions_for_run("RUN-001")
    assert len(decisions) == 1
    loaded = decisions[0]
    assert loaded.decision_id == "DEC-001"
    assert loaded.order_state_snapshot == {"current_state": "ACCESSIONING", "flags": []}
    assert loaded.predicted_applied_rules == ["ACC-008"]
    assert loaded.expected_applied_rules == ["ACC-008"]
    assert loaded.state_correct is True
    assert loaded.latency_ms == 150


# --- Run round-trip ---


def test_run_round_trip(db: Database) -> None:
    run = _make_run()
    db.insert_run(run)

    loaded = db.get_run("RUN-001")
    assert loaded is not None
    assert loaded.run_id == "RUN-001"
    assert loaded.model_id == "llama3"
    assert loaded.run_number == 1
    assert loaded.completed_at is None
    assert loaded.notes is None


def test_get_run_not_found(db: Database) -> None:
    assert db.get_run("NONEXISTENT") is None


def test_update_run_completed(db: Database) -> None:
    db.insert_run(_make_run())

    done_time = datetime(2025, 1, 1, 11, 30, 0)
    db.update_run_completed("RUN-001", done_time)

    loaded = db.get_run("RUN-001")
    assert loaded is not None
    assert loaded.completed_at == done_time


def test_run_aborted_defaults_to_false(db: Database) -> None:
    """Run without aborted field defaults to False."""
    db.insert_run(_make_run())
    loaded = db.get_run("RUN-001")
    assert loaded is not None
    assert loaded.aborted is False


def test_run_aborted_round_trip(db: Database) -> None:
    """Run with aborted=True persists and retrieves correctly."""
    run = Run(
        run_id="RUN-ABORT",
        prompt_template_version="v1",
        scenario_set_version="v1",
        model_id="test-model",
        run_number=1,
        started_at=datetime(2025, 1, 1, 10, 0, 0),
        aborted=True,
    )
    db.insert_run(run)
    loaded = db.get_run("RUN-ABORT")
    assert loaded is not None
    assert loaded.aborted is True


def test_update_run_completed_with_aborted(db: Database) -> None:
    """update_run_completed can mark a run as aborted."""
    db.insert_run(_make_run())
    done_time = datetime(2025, 1, 1, 11, 30, 0)
    db.update_run_completed("RUN-001", done_time, aborted=True)
    loaded = db.get_run("RUN-001")
    assert loaded is not None
    assert loaded.aborted is True
    assert loaded.completed_at == done_time


# --- JSON round-trip specifics ---


def test_json_list_round_trip(db: Database) -> None:
    """ordered_tests and flags survive as Python lists."""
    order = _make_order()
    db.insert_order(order)
    loaded = db.get_order("ORD-001")
    assert loaded is not None
    assert isinstance(loaded.ordered_tests, list)
    assert isinstance(loaded.flags, list)


def test_json_dict_round_trip(db: Database) -> None:
    """event_data and order_state_snapshot survive as Python dicts."""
    db.insert_order(_make_order())
    db.insert_run(_make_run())

    event = Event(
        event_id="EVT-001",
        order_id="ORD-001",
        step_number=1,
        event_type="order_received",
        event_data={"nested": {"key": "value"}, "list": [1, 2, 3]},
        created_at=datetime(2025, 1, 1),
    )
    db.insert_event(event)

    loaded_events = db.get_events_for_order("ORD-001")
    assert isinstance(loaded_events[0].event_data, dict)
    assert loaded_events[0].event_data["nested"]["key"] == "value"


# --- Foreign key enforcement ---


def test_slide_fk_requires_order(db: Database) -> None:
    """Inserting a slide with a nonexistent order_id should fail."""
    slide = Slide(
        slide_id="SL-999",
        order_id="NONEXISTENT",
        test_assignment="ER",
        status="sectioned",
        created_at=datetime(2025, 1, 1),
        updated_at=datetime(2025, 1, 1),
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.insert_slide(slide)


def test_event_fk_requires_order(db: Database) -> None:
    """Inserting an event with a nonexistent order_id should fail."""
    event = Event(
        event_id="EVT-999",
        order_id="NONEXISTENT",
        step_number=1,
        event_type="order_received",
        event_data={},
        created_at=datetime(2025, 1, 1),
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.insert_event(event)


def test_decision_fk_requires_run(db: Database) -> None:
    """Inserting a decision with a nonexistent run_id should fail."""
    db.insert_order(_make_order())
    db.insert_event(
        Event(
            event_id="EVT-001",
            order_id="ORD-001",
            step_number=1,
            event_type="order_received",
            event_data={},
            created_at=datetime(2025, 1, 1),
        )
    )
    decision = Decision(
        decision_id="DEC-999",
        run_id="NONEXISTENT",
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
        created_at=datetime(2025, 1, 1),
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.insert_decision(decision)


# --- Context manager ---


def test_database_context_manager(tmp_path: Path) -> None:
    db_path = tmp_path / "ctx.db"
    with Database(db_path) as db_inst:
        db_inst.init_db()
        db_inst.insert_run(_make_run())
        loaded = db_inst.get_run("RUN-001")
        assert loaded is not None


def test_database_not_open_raises() -> None:
    db_inst = Database("unused.db")
    with pytest.raises(RuntimeError, match="Database not open"):
        db_inst.init_db()


# --- Empty result sets ---


def test_get_slides_for_order_empty(db: Database) -> None:
    db.insert_order(_make_order())
    assert db.get_slides_for_order("ORD-001") == []


def test_get_events_for_order_empty(db: Database) -> None:
    db.insert_order(_make_order())
    assert db.get_events_for_order("ORD-001") == []


def test_get_decisions_for_run_empty(db: Database) -> None:
    db.insert_run(_make_run())
    assert db.get_decisions_for_run("RUN-001") == []


# --- Duplicate primary key ---


def test_duplicate_order_raises(db: Database) -> None:
    db.insert_order(_make_order())
    with pytest.raises(sqlite3.IntegrityError):
        db.insert_order(_make_order())


def test_duplicate_run_raises(db: Database) -> None:
    db.insert_run(_make_run())
    with pytest.raises(sqlite3.IntegrityError):
        db.insert_run(_make_run())


# --- Update nonexistent rows ---


def test_update_order_state_nonexistent_raises(db: Database) -> None:
    with pytest.raises(ValueError, match="Order not found"):
        db.update_order_state("NONEXISTENT", "ACCEPTED", [], datetime(2025, 1, 1))


def test_update_run_completed_nonexistent_raises(db: Database) -> None:
    with pytest.raises(ValueError, match="Run not found"):
        db.update_run_completed("NONEXISTENT", datetime(2025, 1, 1))


def test_update_slide_nonexistent_raises(db: Database) -> None:
    with pytest.raises(ValueError, match="Slide not found"):
        db.update_slide("NONEXISTENT", status="qc_pass")


# --- Batch commit ---


def test_batch_insert_with_explicit_commit(db: Database) -> None:
    """Verify _commit=False defers and commit() flushes."""
    db.insert_run(_make_run(), _commit=False)
    db.commit()
    assert db.get_run("RUN-001") is not None


# --- QueryDecision round-trip ---


def _make_query_decision() -> QueryDecision:
    return QueryDecision(
        decision_id="QD-001",
        run_id="RUN-001",
        scenario_id="QR-001",
        model_id="llama3",
        tier=1,
        answer_type="order_list",
        database_state_snapshot={
            "orders": [{"order_id": "ORD-101", "current_state": "ACCEPTED"}],
            "slides": [],
        },
        model_input={"scenario_id": "QR-001", "query": "test?", "answer_type": "order_list"},
        model_output={"order_ids": ["ORD-101"], "reasoning": "test"},
        predicted_order_ids=["ORD-101"],
        expected_order_ids=["ORD-101"],
        order_ids_correct=True,
        precision=1.0,
        recall=1.0,
        f1=1.0,
        failure_type=None,
        latency_ms=150,
        input_tokens=100,
        output_tokens=30,
        created_at=datetime(2025, 6, 1, 12, 0, 0),
    )


def test_query_decision_round_trip(db: Database) -> None:
    """QueryDecision insert and read-back preserves JSON-serialized fields."""
    import json

    db.insert_run(_make_run())
    qd = _make_query_decision()
    db.insert_query_decision(qd)

    cursor = db._connection.execute(
        "SELECT predicted_order_ids, expected_order_ids, "
        "database_state_snapshot, model_input, model_output "
        "FROM query_decisions WHERE decision_id = ?",
        (qd.decision_id,),
    )
    row = cursor.fetchone()
    assert row is not None

    predicted = json.loads(row[0])
    expected = json.loads(row[1])
    snapshot = json.loads(row[2])
    model_in = json.loads(row[3])
    model_out = json.loads(row[4])

    assert predicted == ["ORD-101"]
    assert expected == ["ORD-101"]
    assert snapshot["orders"][0]["order_id"] == "ORD-101"
    assert model_in["scenario_id"] == "QR-001"
    assert model_out["order_ids"] == ["ORD-101"]


def test_query_decision_deferred_commit(db: Database) -> None:
    """QueryDecision with _commit=False defers, commit() flushes."""
    db.insert_run(_make_run())
    qd = _make_query_decision()
    db.insert_query_decision(qd, _commit=False)

    # Not yet visible in a separate connection
    cursor = db._connection.execute("SELECT COUNT(*) FROM query_decisions")
    # Still visible within the same connection before commit
    assert cursor.fetchone()[0] == 1

    db.commit()
    cursor = db._connection.execute("SELECT COUNT(*) FROM query_decisions")
    assert cursor.fetchone()[0] == 1
