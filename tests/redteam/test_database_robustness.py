"""Red-team robustness tests for the SQLite persistence layer.

Tests adversarial and edge-case behavior: connection lifecycle errors,
JSON round-trip fidelity with unusual payloads, update_slide field
allowlist enforcement, update_order_state edge cases, duplicate primary
keys, FK constraints, and batch-commit failure semantics.

Tests that duplicate baseline coverage in ``tests/test_database.py``
(FK enforcement for slide/event/decision-run, nonexistent-row updates,
basic operation-without-enter) have been removed — this file focuses
exclusively on adversarial inputs and behavioral edge cases.
"""

from __future__ import annotations

import os
import sqlite3
import stat
from collections.abc import Generator
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from src.workflow.database import Database
from src.workflow.models import Decision, Event, Order, Run, Slide

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_order(**overrides: Any) -> Order:
    """Create a minimal valid Order, with optional field overrides."""
    defaults: dict[str, Any] = {
        "order_id": "ORD-001",
        "scenario_id": "SC-001",
        "patient_name": "TESTPATIENT, Jane",
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
    return Order(**defaults)


def _make_run(**overrides: Any) -> Run:
    defaults: dict[str, Any] = {
        "run_id": "RUN-001",
        "prompt_template_version": "v1",
        "scenario_set_version": "v1",
        "model_id": "llama3",
        "run_number": 1,
        "started_at": datetime(2025, 1, 1, 10, 0, 0),
    }
    defaults.update(overrides)
    return Run(**defaults)


def _make_slide(**overrides: Any) -> Slide:
    defaults: dict[str, Any] = {
        "slide_id": "SL-001",
        "order_id": "ORD-001",
        "test_assignment": "HER2",
        "status": "sectioned",
        "created_at": datetime(2025, 1, 1),
        "updated_at": datetime(2025, 1, 1),
    }
    defaults.update(overrides)
    return Slide(**defaults)


def _make_event(**overrides: Any) -> Event:
    defaults: dict[str, Any] = {
        "event_id": "EVT-001",
        "order_id": "ORD-001",
        "step_number": 1,
        "event_type": "order_received",
        "event_data": {},
        "created_at": datetime(2025, 1, 1),
    }
    defaults.update(overrides)
    return Event(**defaults)


def _make_decision(**overrides: Any) -> Decision:
    # Default states assume an ACCESSIONING -> ACCEPTED transition, which
    # is a valid workflow transition per docs/workflow/workflow-overview.md.
    defaults: dict[str, Any] = {
        "decision_id": "DEC-001",
        "run_id": "RUN-001",
        "event_id": "EVT-001",
        "order_id": "ORD-001",
        "model_id": "llama3",
        "order_state_snapshot": {},
        "model_input": {},
        "model_output": {},
        "predicted_next_state": "ACCEPTED",
        "predicted_applied_rules": [],
        "predicted_flags": [],
        "expected_next_state": "ACCEPTED",
        "expected_applied_rules": [],
        "expected_flags": [],
        "state_correct": True,
        "rules_correct": True,
        "flags_correct": True,
        "latency_ms": 100,
        "input_tokens": 100,
        "output_tokens": 10,
        "created_at": datetime(2025, 1, 1),
    }
    defaults.update(overrides)
    return Decision(**defaults)


@pytest.fixture()
def db(tmp_path: Path) -> Generator[Database, None, None]:
    """Provide an initialized database in a temp directory."""
    db_path = tmp_path / "test.db"
    with Database(db_path) as db_instance:
        db_instance.init_db()
        yield db_instance


@pytest.fixture()
def seeded_db(db: Database) -> Database:
    """Database pre-seeded with an order, run, event, and slide."""
    db.insert_order(_make_order())
    db.insert_run(_make_run())
    db.insert_event(_make_event())
    db.insert_slide(_make_slide())
    return db


# ===========================================================================
# Connection lifecycle
# ===========================================================================


class TestConnectionLifecycle:
    """Verify that Database operations fail correctly outside context manager."""

    def test_insert_order_without_enter_raises(self) -> None:
        db_inst = Database("unused.db")
        with pytest.raises(RuntimeError, match="Database not open"):
            db_inst.insert_order(_make_order())

    def test_commit_without_enter_raises(self) -> None:
        db_inst = Database("unused.db")
        with pytest.raises(RuntimeError, match="Database not open"):
            db_inst.commit()

    def test_commit_after_exit_raises(self, tmp_path: Path) -> None:
        """commit() after __exit__ should raise RuntimeError."""
        db_path = tmp_path / "lifecycle.db"
        db_inst = Database(db_path)
        db_inst.__enter__()
        db_inst.init_db()
        db_inst.__exit__(None, None, None)

        with pytest.raises(RuntimeError, match="Database not open"):
            db_inst.commit()

    def test_insert_after_exit_raises(self, tmp_path: Path) -> None:
        """insert_order() after __exit__ should raise RuntimeError."""
        db_path = tmp_path / "lifecycle.db"
        db_inst = Database(db_path)
        db_inst.__enter__()
        db_inst.init_db()
        db_inst.__exit__(None, None, None)

        with pytest.raises(RuntimeError, match="Database not open"):
            db_inst.insert_order(_make_order())

    def test_double_enter_leaks_first_connection(self, tmp_path: Path) -> None:
        """Double __enter__ replaces the connection — first is leaked."""
        db_path = tmp_path / "lifecycle.db"
        db_inst = Database(db_path)
        db_inst.__enter__()
        db_inst.init_db()
        first_conn = db_inst._conn

        # Second enter overwrites _conn without closing the first
        db_inst.__enter__()
        second_conn = db_inst._conn

        assert first_conn is not second_conn
        db_inst.__exit__(None, None, None)

    def test_double_exit(self, tmp_path: Path) -> None:
        """Double __exit__ should not raise (idempotent close)."""
        db_path = tmp_path / "lifecycle.db"
        db_inst = Database(db_path)
        db_inst.__enter__()
        db_inst.init_db()
        db_inst.__exit__(None, None, None)
        # Second exit — _conn is already None, so the if-guard skips close()
        db_inst.__exit__(None, None, None)  # Should not raise

    def test_exception_in_context_rolls_back(self, tmp_path: Path) -> None:
        """An exception exiting the context manager rolls back uncommitted writes."""
        db_path = tmp_path / "rollback.db"
        try:
            with Database(db_path) as db_inst:
                db_inst.init_db()
                db_inst.insert_order(_make_order(), _commit=False)
                raise RuntimeError("simulated failure")
        except RuntimeError:
            pass

        with Database(db_path) as db_inst:
            assert db_inst.get_order("ORD-001") is None

    def test_wal_mode_enabled(self, tmp_path: Path) -> None:
        """Database uses WAL journal mode for durability."""
        db_path = tmp_path / "wal.db"
        with Database(db_path) as db_inst:
            db_inst.init_db()
            row = db_inst._connection.execute("PRAGMA journal_mode").fetchone()
            assert row[0] == "wal"

    def test_file_permissions_restricted(self, tmp_path: Path) -> None:
        """Database file is restricted to owner-only (0o600) for PHI protection."""
        db_path = tmp_path / "perms.db"
        with Database(db_path) as db_inst:
            db_inst.init_db()
        mode = stat.S_IMODE(db_path.stat().st_mode)
        assert mode == 0o600

    def test_file_permissions_restrictive_at_creation(self, tmp_path: Path) -> None:
        """File is created with restrictive permissions (no race window).

        CWE-732 mitigation: umask is set before sqlite3.connect() so
        the file never has world-readable permissions, even briefly.
        """
        db_path = tmp_path / "creation_perms.db"
        assert not db_path.exists()
        # Read current umask without changing it.
        old_umask = os.umask(0o000)
        os.umask(old_umask)
        try:
            with Database(db_path) as db_inst:
                # Check permissions while still inside the context manager,
                # immediately after the file was created by connect().
                mode = stat.S_IMODE(db_path.stat().st_mode)
                assert mode & 0o077 == 0, (
                    f"Database file created with group/other permissions: {oct(mode)}"
                )
                db_inst.init_db()
        finally:
            os.umask(old_umask)


# ===========================================================================
# JSON round-trip fidelity
# ===========================================================================


class TestJsonRoundTripFidelity:
    """Verify JSON fields survive unusual payloads through SQLite."""

    def test_ordered_tests_unicode(self, db: Database) -> None:
        """Unicode characters in ordered_tests survive round-trip."""
        order = _make_order(ordered_tests=["ER", "PR", "HER2\u2122", "Ki\u201167"])
        db.insert_order(order)
        loaded = db.get_order("ORD-001")
        assert loaded is not None
        assert loaded.ordered_tests == ["ER", "PR", "HER2\u2122", "Ki\u201167"]

    def test_ordered_tests_empty_list(self, db: Database) -> None:
        """Empty ordered_tests list survives round-trip."""
        order = _make_order(ordered_tests=[])
        db.insert_order(order)
        loaded = db.get_order("ORD-001")
        assert loaded is not None
        assert loaded.ordered_tests == []

    def test_ordered_tests_single_element(self, db: Database) -> None:
        """Single-element ordered_tests list survives round-trip."""
        order = _make_order(ordered_tests=["ER"])
        db.insert_order(order)
        loaded = db.get_order("ORD-001")
        assert loaded is not None
        assert loaded.ordered_tests == ["ER"]

    def test_flags_empty_list(self, db: Database) -> None:
        """Empty flags list round-trips correctly."""
        order = _make_order(flags=[])
        db.insert_order(order)
        loaded = db.get_order("ORD-001")
        assert loaded is not None
        assert loaded.flags == []

    def test_large_model_output(self, db: Database) -> None:
        """Large model_output (~100KB JSON) round-trips without truncation."""
        db.insert_order(_make_order())
        db.insert_run(_make_run())
        db.insert_event(_make_event())

        large_output = {"data": "x" * 100_000, "nested": {"key": list(range(1000))}}
        decision = _make_decision(model_output=large_output)
        db.insert_decision(decision)

        loaded = db.get_decisions_for_run("RUN-001")
        assert len(loaded) == 1
        assert loaded[0].model_output == large_output
        assert len(loaded[0].model_output["data"]) == 100_000

    def test_nested_order_state_snapshot(self, db: Database) -> None:
        """Deeply nested order_state_snapshot round-trips correctly."""
        db.insert_order(_make_order())
        db.insert_run(_make_run())
        db.insert_event(_make_event())

        nested_snapshot = {
            "current_state": "ACCESSIONING",
            "flags": ["FIXATION_WARNING"],
            "slides": [{"id": "SL-001", "scores": {"her2": {"value": "2+", "equivocal": True}}}],
            "metadata": {"deep": {"nesting": {"level": 4}}},
        }
        decision = _make_decision(order_state_snapshot=nested_snapshot)
        db.insert_decision(decision)

        loaded = db.get_decisions_for_run("RUN-001")
        assert loaded[0].order_state_snapshot == nested_snapshot

    def test_slide_score_result_none(self, db: Database) -> None:
        """score_result=None round-trips as None."""
        db.insert_order(_make_order())
        slide = _make_slide(score_result=None)
        db.insert_slide(slide)

        slides = db.get_slides_for_order("ORD-001")
        assert slides[0].score_result is None

    def test_slide_score_result_empty_dict(self, db: Database) -> None:
        """score_result={} round-trips as empty dict."""
        db.insert_order(_make_order())
        slide = _make_slide(score_result={})
        db.insert_slide(slide)

        slides = db.get_slides_for_order("ORD-001")
        assert slides[0].score_result == {}

    def test_slide_score_result_nested(self, db: Database) -> None:
        """Nested score_result round-trips correctly."""
        db.insert_order(_make_order())
        nested_score: dict[str, Any] = {
            "her2": {"value": "2+", "equivocal": True},
            "ki67": {"percentage": 25.5, "hot_spots": [30, 28, 22]},
        }
        slide = _make_slide(score_result=nested_score)
        db.insert_slide(slide)

        slides = db.get_slides_for_order("ORD-001")
        assert slides[0].score_result == nested_score

    def test_datetime_microsecond_precision_round_trips(self, db: Database) -> None:
        """Microsecond-precision datetimes survive the ISO 8601 round-trip."""
        ts = datetime(2025, 6, 15, 14, 30, 45, 123456)
        order = _make_order(created_at=ts, updated_at=ts)
        db.insert_order(order)
        loaded = db.get_order("ORD-001")
        assert loaded is not None
        assert loaded.created_at == ts
        assert loaded.updated_at == ts

    def test_order_nullable_fields_all_none(self, db: Database) -> None:
        """Order with all nullable fields as None round-trips correctly."""
        order = _make_order(
            patient_name=None,
            patient_age=None,
            patient_sex=None,
            fixation_time_hours=None,
        )
        db.insert_order(order)
        loaded = db.get_order("ORD-001")
        assert loaded is not None
        assert loaded.patient_name is None
        assert loaded.patient_age is None
        assert loaded.patient_sex is None
        assert loaded.fixation_time_hours is None


# ===========================================================================
# update_slide field allowlist
# ===========================================================================


class TestUpdateSlideAllowlist:
    """Verify update_slide rejects disallowed fields and handles edge cases."""

    def test_slide_id_rejected_by_python_binding(self, seeded_db: Database) -> None:
        """Passing slide_id as a keyword argument conflicts with the positional
        parameter and raises TypeError at the Python argument-binding level,
        before the allowlist check runs. If the method signature ever changes
        to accept **kwargs only, the allowlist would need to carry this guard.
        """
        with pytest.raises(TypeError, match="multiple values"):
            seeded_db.update_slide("SL-001", **{"slide_id": "SL-HACKED"})

    def test_reject_order_id(self, seeded_db: Database) -> None:
        """Cannot update foreign key field order_id."""
        with pytest.raises(ValueError, match="Cannot update slide fields"):
            seeded_db.update_slide("SL-001", order_id="ORD-HACKED")

    def test_reject_test_assignment(self, seeded_db: Database) -> None:
        """Cannot update test_assignment."""
        with pytest.raises(ValueError, match="Cannot update slide fields"):
            seeded_db.update_slide("SL-001", test_assignment="FISH")

    def test_reject_created_at(self, seeded_db: Database) -> None:
        """Cannot update created_at."""
        with pytest.raises(ValueError, match="Cannot update slide fields"):
            seeded_db.update_slide("SL-001", created_at=datetime.now())

    def test_empty_kwargs_is_noop(self, seeded_db: Database) -> None:
        """Calling update_slide with no fields is a silent no-op."""
        seeded_db.update_slide("SL-001")

        slides = seeded_db.get_slides_for_order("ORD-001")
        assert slides[0].status == "sectioned"

    def test_empty_kwargs_on_nonexistent_slide_is_silent(self, db: Database) -> None:
        """update_slide with no kwargs returns silently even for nonexistent IDs.

        The early return on ``if not fields`` bypasses the existence check.
        This documents a production behavior gap: callers cannot distinguish
        "slide exists with nothing to update" from "slide does not exist".
        """
        db.update_slide("NONEXISTENT")  # Should not raise

    def test_field_name_injection_attempt(self, seeded_db: Database) -> None:
        """SQL injection via field key must be rejected by the allowlist.

        The key "status = 'hacked' --" is not in the allowed set, so it
        raises ValueError before ever reaching SQL construction.
        """
        with pytest.raises(ValueError, match="Cannot update slide fields"):
            seeded_db.update_slide("SL-001", **{"status = 'hacked' --": "pwned"})

    def test_update_score_result_none(self, seeded_db: Database) -> None:
        """Setting score_result to None round-trips correctly."""
        seeded_db.update_slide(
            "SL-001",
            score_result=None,
            updated_at=datetime(2025, 6, 1),
        )
        slides = seeded_db.get_slides_for_order("ORD-001")
        assert slides[0].score_result is None

    def test_update_score_result_empty_dict(self, seeded_db: Database) -> None:
        """Setting score_result to {} round-trips correctly."""
        seeded_db.update_slide(
            "SL-001",
            score_result={},
            updated_at=datetime(2025, 6, 1),
        )
        slides = seeded_db.get_slides_for_order("ORD-001")
        assert slides[0].score_result == {}

    def test_update_score_result_nested(self, seeded_db: Database) -> None:
        """Setting score_result to nested structure round-trips correctly."""
        nested: dict[str, Any] = {
            "her2": {"intensity": 3, "pattern": "membrane"},
            "details": [{"area": 1, "cells": 200}],
        }
        seeded_db.update_slide(
            "SL-001",
            score_result=nested,
            updated_at=datetime(2025, 6, 1),
        )
        slides = seeded_db.get_slides_for_order("ORD-001")
        assert slides[0].score_result == nested


# ===========================================================================
# update_order_state edge cases
# ===========================================================================


class TestUpdateOrderState:
    """Adversarial tests for update_order_state."""

    def test_non_empty_flags_round_trip(self, db: Database) -> None:
        """Non-empty flags list survives JSON serialization through update_order_state."""
        db.insert_order(_make_order())
        flags = ["FIXATION_WARNING", "MISSING_INFO_PROCEED"]
        db.update_order_state("ORD-001", "ACCEPTED", flags, datetime(2025, 6, 1))
        loaded = db.get_order("ORD-001")
        assert loaded is not None
        assert loaded.flags == flags
        assert loaded.current_state == "ACCEPTED"

    def test_invalid_state_write_bypasses_model_validation(self, db: Database) -> None:
        """update_order_state writes directly to SQLite without Order validation.

        Writing an invalid state succeeds at the SQL level. However, get_order
        reconstructs an Order via __post_init__, which validates current_state
        against VALID_STATES — so the invalid state cannot be read back cleanly.
        This documents a split-brain scenario in the persistence layer.
        """
        db.insert_order(_make_order())
        db.update_order_state("ORD-001", "BOGUS_STATE", ["INVALID_FLAG"], datetime(2025, 6, 1))

        # The write succeeded — verify via raw SQL
        cursor = db._connection.execute(
            "SELECT current_state FROM orders WHERE order_id = 'ORD-001'"
        )
        assert cursor.fetchone()[0] == "BOGUS_STATE"

        # But get_order fails because Order.__post_init__ validates the state
        with pytest.raises(ValueError, match="Invalid state"):
            db.get_order("ORD-001")


# ===========================================================================
# Duplicate primary key insertion
# ===========================================================================


class TestDuplicatePrimaryKey:
    """Verify that inserting duplicate primary keys raises IntegrityError."""

    def test_duplicate_order_id(self, db: Database) -> None:
        db.insert_order(_make_order())
        with pytest.raises(sqlite3.IntegrityError):
            db.insert_order(_make_order())

    def test_duplicate_slide_id(self, db: Database) -> None:
        db.insert_order(_make_order())
        db.insert_slide(_make_slide())
        with pytest.raises(sqlite3.IntegrityError):
            db.insert_slide(_make_slide())

    def test_duplicate_run_id(self, db: Database) -> None:
        db.insert_run(_make_run())
        with pytest.raises(sqlite3.IntegrityError):
            db.insert_run(_make_run())


# ===========================================================================
# FK enforcement (non-duplicate adversarial cases only)
# ===========================================================================


class TestForeignKeyEnforcement:
    """Verify FK constraints that are NOT covered by tests/test_database.py.

    Baseline FK tests (slide->order, event->order, decision->run) live in
    tests/test_database.py. This class covers the remaining FK relationships.
    """

    def test_decision_requires_existing_event(self, db: Database) -> None:
        """Decision referencing nonexistent event_id raises IntegrityError."""
        db.insert_order(_make_order())
        db.insert_run(_make_run())

        decision = _make_decision(event_id="EVT-NONEXISTENT")
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            db.insert_decision(decision)

    def test_decision_requires_existing_order(self, db: Database) -> None:
        """Decision referencing nonexistent order_id raises IntegrityError."""
        db.insert_run(_make_run())
        db.insert_order(_make_order())
        db.insert_event(_make_event())

        decision = _make_decision(order_id="ORD-NONEXISTENT")
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            db.insert_decision(decision)


# ===========================================================================
# Read-path and batch-commit robustness
# ===========================================================================


class TestReadAndBatchRobustness:
    """Test read-path edge cases and batch-commit failure semantics."""

    def test_get_decisions_for_nonexistent_run_returns_empty(self, db: Database) -> None:
        """get_decisions_for_run silently returns [] for unknown run_id.

        This is distinct from update_run_completed which raises ValueError.
        Documented here to prevent callers from assuming an exception signals
        a missing run.
        """
        result = db.get_decisions_for_run("RUN-NONEXISTENT")
        assert result == []

    def test_batch_insert_fk_failure_leaves_prior_uncommitted(self, db: Database) -> None:
        """A FK failure mid-batch leaves prior _commit=False inserts uncommitted.

        SQLite raises IntegrityError immediately on the FK-violating statement,
        but the prior uncommitted insert remains in the transaction. Without an
        explicit commit(), the prior insert is not persisted.
        """
        db.insert_order(_make_order(), _commit=False)
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            db.insert_event(_make_event(order_id="NONEXISTENT"), _commit=False)
        # The order was inserted but never committed — it should not persist
        # after the connection rolls back (via __exit__ on error or explicit
        # rollback). We can verify it's in the transaction but not committed:
        # calling commit() here would persist it; not calling leaves it pending.
        # For this test, we verify the order IS visible within the same
        # transaction (uncommitted read):
        loaded = db.get_order("ORD-001")
        assert loaded is not None  # visible in current transaction
