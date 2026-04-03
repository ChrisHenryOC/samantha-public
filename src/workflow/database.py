"""SQLite persistence layer for the laboratory workflow routing system.

Provides a Database class with context manager pattern for connection
lifecycle, WAL mode, foreign key enforcement, and CRUD operations for
all 5 entity tables. All SQL uses parameterized queries.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Any

from src.workflow.models import Decision, Event, Order, QueryDecision, Run, Slide

_CREATE_ORDERS = """
CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    scenario_id TEXT NOT NULL,
    patient_name TEXT,
    patient_age INTEGER,
    patient_sex TEXT,
    specimen_type TEXT NOT NULL,
    anatomic_site TEXT NOT NULL,
    fixative TEXT NOT NULL,
    fixation_time_hours REAL,
    ordered_tests TEXT NOT NULL,
    priority TEXT NOT NULL,
    billing_info_present BOOLEAN NOT NULL,
    current_state TEXT NOT NULL,
    flags TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
)
"""

_CREATE_SLIDES = """
CREATE TABLE IF NOT EXISTS slides (
    slide_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    test_assignment TEXT NOT NULL,
    status TEXT NOT NULL,
    qc_result TEXT,
    score_result TEXT,
    reported BOOLEAN NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
)
"""

_CREATE_EVENTS = """
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    step_number INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    event_data TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
)
"""

_CREATE_DECISIONS = """
CREATE TABLE IF NOT EXISTS decisions (
    decision_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    order_state_snapshot TEXT NOT NULL,
    model_input TEXT NOT NULL,
    model_output TEXT NOT NULL,
    predicted_next_state TEXT NOT NULL,
    predicted_applied_rules TEXT NOT NULL,
    predicted_flags TEXT NOT NULL,
    expected_next_state TEXT NOT NULL,
    expected_applied_rules TEXT NOT NULL,
    expected_flags TEXT NOT NULL,
    state_correct BOOLEAN NOT NULL,
    rules_correct BOOLEAN NOT NULL,
    flags_correct BOOLEAN NOT NULL,
    latency_ms INTEGER NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(run_id),
    FOREIGN KEY (event_id) REFERENCES events(event_id),
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
)
"""

_CREATE_QUERY_DECISIONS = """
CREATE TABLE IF NOT EXISTS query_decisions (
    decision_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    tier INTEGER NOT NULL,
    answer_type TEXT NOT NULL,
    database_state_snapshot TEXT NOT NULL,
    model_input TEXT NOT NULL,
    model_output TEXT NOT NULL,
    predicted_order_ids TEXT NOT NULL,
    expected_order_ids TEXT NOT NULL,
    order_ids_correct BOOLEAN NOT NULL,
    precision REAL NOT NULL,
    recall REAL NOT NULL,
    f1 REAL NOT NULL,
    failure_type TEXT,
    latency_ms INTEGER NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
)
"""

_CREATE_ROUTING_DECISIONS = """
CREATE TABLE IF NOT EXISTS routing_decisions (
    decision_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    from_state TEXT NOT NULL,
    to_state TEXT NOT NULL,
    applied_rules TEXT NOT NULL,
    flags TEXT NOT NULL,
    reasoning TEXT,
    transition_valid BOOLEAN NOT NULL,
    applied BOOLEAN NOT NULL,
    latency_ms REAL NOT NULL,
    created_at TIMESTAMP NOT NULL,
    FOREIGN KEY (event_id) REFERENCES events(event_id),
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
)
"""

_CREATE_RUNS = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    prompt_template_version TEXT NOT NULL,
    scenario_set_version TEXT NOT NULL,
    model_id TEXT NOT NULL,
    run_number INTEGER NOT NULL,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    notes TEXT,
    aborted INTEGER NOT NULL DEFAULT 0
)
"""


def _to_iso(dt: datetime | None) -> str | None:
    """Convert a datetime to ISO 8601 string, or None."""
    return dt.isoformat() if dt is not None else None


def _from_iso(value: str | None) -> datetime | None:
    """Parse an ISO 8601 string to datetime, or None."""
    return datetime.fromisoformat(value) if value is not None else None


def _load_string_list(raw: str, field_name: str) -> list[str]:
    """Deserialize a JSON string and validate it is a list of strings."""
    result = json.loads(raw)
    if not isinstance(result, list) or not all(isinstance(v, str) for v in result):
        raise TypeError(f"Expected list[str] for '{field_name}', got {type(result).__name__}")
    return result


def _load_dict(raw: str, field_name: str) -> dict[str, Any]:
    """Deserialize a JSON string and validate it is a dict."""
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise TypeError(f"Expected dict for '{field_name}', got {type(result).__name__}")
    return result


class Database:
    """SQLite database for workflow persistence.

    Uses WAL journal mode and foreign key enforcement.  The following fields
    are serialized to JSON on write and deserialized on read:

    - **orders**: ``ordered_tests``, ``flags``
    - **slides**: ``score_result``
    - **events**: ``event_data``
    - **decisions**: ``order_state_snapshot``, ``model_input``,
      ``model_output``, ``predicted_applied_rules``, ``predicted_flags``,
      ``expected_applied_rules``, ``expected_flags``

    Usage::

        with Database("path/to/db.sqlite") as db:
            db.init_db()
            db.insert_order(order)
    """

    _umask_lock = threading.Lock()

    def __init__(self, db_path: str | Path, *, check_same_thread: bool = True) -> None:
        self._db_path = Path(db_path)
        self._check_same_thread = check_same_thread
        self._conn: sqlite3.Connection | None = None

    def __enter__(self) -> Database:
        """Open connection with restrictive file permissions.

        Uses ``os.umask`` to ensure the database file is created with
        owner-only permissions from the start (CWE-732 mitigation).
        The umask call is guarded by a class-level lock against concurrent
        ``Database`` instantiations. Note: ``os.umask`` is process-global;
        this lock does not protect against non-Database callers in the
        same process.
        """
        with Database._umask_lock:
            old_umask = os.umask(0o077)
            try:
                self._conn = sqlite3.connect(
                    str(self._db_path),
                    check_same_thread=self._check_same_thread,
                )
            finally:
                os.umask(old_umask)

        self._conn.row_factory = sqlite3.Row
        actual_mode = self._conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
        if actual_mode != "wal":
            raise RuntimeError(
                f"Database at {self._db_path!r} does not support WAL journal mode "
                f"(got {actual_mode!r}). WAL is required for concurrent write safety."
            )
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA busy_timeout=5000")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._conn is not None:
            if exc_type is not None:
                self._conn.rollback()
            self._conn.close()
            self._conn = None

    def commit(self) -> None:
        """Explicitly commit the current transaction.

        Use this when batching multiple operations::

            with Database("path.db") as db:
                db.init_db()
                for order in orders:
                    db.insert_order(order, _commit=False)
                db.commit()

        Individual insert/update methods auto-commit by default.
        Pass ``_commit=False`` to defer commits for batch operations.
        """
        self._connection.commit()

    @property
    def _connection(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Database not open. Use 'with Database(path) as db:'")
        return self._conn

    def init_db(self) -> None:
        """Create all tables and indexes if they don't exist."""
        conn = self._connection
        conn.execute(_CREATE_RUNS)
        conn.execute(_CREATE_ORDERS)
        conn.execute(_CREATE_SLIDES)
        conn.execute(_CREATE_EVENTS)
        conn.execute(_CREATE_DECISIONS)
        conn.execute(_CREATE_QUERY_DECISIONS)
        conn.execute(_CREATE_ROUTING_DECISIONS)
        # Indexes on foreign keys and common query columns
        conn.execute("CREATE INDEX IF NOT EXISTS idx_slides_order_id ON slides(order_id)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_order_step ON events(order_id, step_number)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_decisions_run_id ON decisions(run_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_decisions_event_id ON decisions(event_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_decisions_order_id ON decisions(order_id)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_query_decisions_run_id ON query_decisions(run_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_query_decisions_scenario_id "
            "ON query_decisions(scenario_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_routing_decisions_order_id "
            "ON routing_decisions(order_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_routing_decisions_event_id "
            "ON routing_decisions(event_id)"
        )
        conn.commit()

    # --- Orders ---

    def insert_order(self, order: Order, *, _commit: bool = True) -> None:
        """Insert an order row.

        Set ``_commit=False`` to defer commit for batch operations.
        """
        self._connection.execute(
            """INSERT INTO orders (
                order_id, scenario_id, patient_name, patient_age, patient_sex,
                specimen_type, anatomic_site, fixative, fixation_time_hours,
                ordered_tests, priority, billing_info_present, current_state,
                flags, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                order.order_id,
                order.scenario_id,
                order.patient_name,
                order.patient_age,
                order.patient_sex,
                order.specimen_type,
                order.anatomic_site,
                order.fixative,
                order.fixation_time_hours,
                json.dumps(order.ordered_tests),
                order.priority,
                order.billing_info_present,
                order.current_state,
                json.dumps(order.flags),
                _to_iso(order.created_at),
                _to_iso(order.updated_at),
            ),
        )
        if _commit:
            self._connection.commit()

    def get_order(self, order_id: str) -> Order | None:
        """Retrieve an order by ID, or None if not found."""
        cursor = self._connection.execute(
            """SELECT order_id, scenario_id, patient_name, patient_age,
                      patient_sex, specimen_type, anatomic_site, fixative,
                      fixation_time_hours, ordered_tests, priority,
                      billing_info_present, current_state, flags,
                      created_at, updated_at
               FROM orders WHERE order_id = ?""",
            (order_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return Order(
            order_id=row["order_id"],
            scenario_id=row["scenario_id"],
            patient_name=row["patient_name"],
            patient_age=row["patient_age"],
            patient_sex=row["patient_sex"],
            specimen_type=row["specimen_type"],
            anatomic_site=row["anatomic_site"],
            fixative=row["fixative"],
            fixation_time_hours=row["fixation_time_hours"],
            ordered_tests=_load_string_list(row["ordered_tests"], "ordered_tests"),
            priority=row["priority"],
            billing_info_present=bool(row["billing_info_present"]),
            current_state=row["current_state"],
            flags=_load_string_list(row["flags"], "flags"),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def list_orders(
        self,
        *,
        state: str | None = None,
        priority: str | None = None,
        has_flags: bool | None = None,
    ) -> list[Order]:
        """List orders with optional filters.

        Args:
            state: Filter to orders in this workflow state.
            priority: Filter to orders with this priority.
            has_flags: If True, only orders with non-empty flags.
                If False, only orders with no flags.
        """
        clauses: list[str] = []
        params: list[Any] = []
        if state is not None:
            clauses.append("current_state = ?")
            params.append(state)
        if priority is not None:
            clauses.append("priority = ?")
            params.append(priority)
        if has_flags is True:
            clauses.append("flags != '[]'")
        elif has_flags is False:
            clauses.append("flags = '[]'")
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        cursor = self._connection.execute(
            f"""SELECT order_id, scenario_id, patient_name, patient_age,
                      patient_sex, specimen_type, anatomic_site, fixative,
                      fixation_time_hours, ordered_tests, priority,
                      billing_info_present, current_state, flags,
                      created_at, updated_at
               FROM orders{where}
               ORDER BY created_at""",
            params,
        )
        orders: list[Order] = []
        for row in cursor.fetchall():
            orders.append(
                Order(
                    order_id=row["order_id"],
                    scenario_id=row["scenario_id"],
                    patient_name=row["patient_name"],
                    patient_age=row["patient_age"],
                    patient_sex=row["patient_sex"],
                    specimen_type=row["specimen_type"],
                    anatomic_site=row["anatomic_site"],
                    fixative=row["fixative"],
                    fixation_time_hours=row["fixation_time_hours"],
                    ordered_tests=_load_string_list(row["ordered_tests"], "ordered_tests"),
                    priority=row["priority"],
                    billing_info_present=bool(row["billing_info_present"]),
                    current_state=row["current_state"],
                    flags=_load_string_list(row["flags"], "flags"),
                    created_at=datetime.fromisoformat(row["created_at"]),
                    updated_at=datetime.fromisoformat(row["updated_at"]),
                )
            )
        return orders

    def update_order_state(
        self,
        order_id: str,
        new_state: str,
        flags: list[str],
        updated_at: datetime,
        *,
        _commit: bool = True,
    ) -> None:
        """Update an order's current state, flags, and timestamp.

        Set ``_commit=False`` to defer commit for batch/atomic operations.
        Raises ``ValueError`` if the order_id does not exist.
        """
        cursor = self._connection.execute(
            """UPDATE orders
               SET current_state = ?, flags = ?, updated_at = ?
               WHERE order_id = ?""",
            (new_state, json.dumps(flags), _to_iso(updated_at), order_id),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"Order not found: {order_id}")
        if _commit:
            self._connection.commit()

    # --- Slides ---

    def insert_slide(self, slide: Slide, *, _commit: bool = True) -> None:
        """Insert a slide row.

        Set ``_commit=False`` to defer commit for batch operations.
        """
        self._connection.execute(
            """INSERT INTO slides (
                slide_id, order_id, test_assignment, status, qc_result,
                score_result, reported, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                slide.slide_id,
                slide.order_id,
                slide.test_assignment,
                slide.status,
                slide.qc_result,
                json.dumps(slide.score_result) if slide.score_result is not None else None,
                slide.reported,
                _to_iso(slide.created_at),
                _to_iso(slide.updated_at),
            ),
        )
        if _commit:
            self._connection.commit()

    def get_slides_for_order(self, order_id: str) -> list[Slide]:
        """Retrieve all slides for a given order."""
        cursor = self._connection.execute(
            """SELECT slide_id, order_id, test_assignment, status, qc_result,
                      score_result, reported, created_at, updated_at
               FROM slides WHERE order_id = ?""",
            (order_id,),
        )
        slides = []
        for row in cursor.fetchall():
            slides.append(
                Slide(
                    slide_id=row["slide_id"],
                    order_id=row["order_id"],
                    test_assignment=row["test_assignment"],
                    status=row["status"],
                    qc_result=row["qc_result"],
                    score_result=(
                        _load_dict(row["score_result"], "score_result")
                        if row["score_result"] is not None
                        else None
                    ),
                    reported=bool(row["reported"]),
                    created_at=datetime.fromisoformat(row["created_at"]),
                    updated_at=datetime.fromisoformat(row["updated_at"]),
                )
            )
        return slides

    def update_slide(self, slide_id: str, **fields: Any) -> None:
        """Update specific fields on a slide.

        Accepted fields: status, qc_result, score_result, reported, updated_at.
        Raises ``ValueError`` if the slide_id does not exist or if
        disallowed fields are passed.
        """
        # SECURITY: This allowlist is a critical control. Column names from
        # ``fields.keys()`` are interpolated into SQL — only these five names
        # are safe. Do not remove or weaken this check.
        allowed = {"status", "qc_result", "score_result", "reported", "updated_at"}
        invalid = set(fields.keys()) - allowed
        if invalid:
            raise ValueError(f"Cannot update slide fields: {invalid}. Allowed: {sorted(allowed)}")
        if not fields:
            return

        set_clauses = []
        params: list[Any] = []
        for key, value in fields.items():
            set_clauses.append(f"{key} = ?")
            if key == "score_result":
                params.append(json.dumps(value) if value is not None else None)
            elif key == "updated_at" and isinstance(value, datetime):
                params.append(_to_iso(value))
            else:
                params.append(value)
        params.append(slide_id)

        sql = f"UPDATE slides SET {', '.join(set_clauses)} WHERE slide_id = ?"
        cursor = self._connection.execute(sql, params)
        if cursor.rowcount == 0:
            raise ValueError(f"Slide not found: {slide_id}")
        self._connection.commit()

    # --- Events ---

    def get_max_step_number(self, order_id: str) -> int:
        """Return the maximum step_number for an order, or 0 if no events."""
        cursor = self._connection.execute(
            "SELECT COALESCE(MAX(step_number), 0) FROM events WHERE order_id = ?",
            (order_id,),
        )
        result: int = cursor.fetchone()[0]
        return result

    def insert_event(self, event: Event, *, _commit: bool = True) -> None:
        """Insert an event row.

        Set ``_commit=False`` to defer commit for batch operations.
        """
        self._connection.execute(
            """INSERT INTO events (
                event_id, order_id, step_number, event_type, event_data,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?)""",
            (
                event.event_id,
                event.order_id,
                event.step_number,
                event.event_type,
                json.dumps(event.event_data),
                _to_iso(event.created_at),
            ),
        )
        if _commit:
            self._connection.commit()

    def get_events_for_order(self, order_id: str) -> list[Event]:
        """Retrieve all events for a given order, ordered by step number."""
        cursor = self._connection.execute(
            """SELECT event_id, order_id, step_number, event_type,
                      event_data, created_at
               FROM events WHERE order_id = ? ORDER BY step_number""",
            (order_id,),
        )
        events = []
        for row in cursor.fetchall():
            events.append(
                Event(
                    event_id=row["event_id"],
                    order_id=row["order_id"],
                    step_number=row["step_number"],
                    event_type=row["event_type"],
                    event_data=_load_dict(row["event_data"], "event_data"),
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
            )
        return events

    # --- Decisions ---

    def insert_decision(self, decision: Decision, *, _commit: bool = True) -> None:
        """Insert a decision row.

        Set ``_commit=False`` to defer commit for batch operations.
        """
        self._connection.execute(
            """INSERT INTO decisions (
                decision_id, run_id, event_id, order_id, model_id,
                order_state_snapshot, model_input, model_output,
                predicted_next_state, predicted_applied_rules, predicted_flags,
                expected_next_state, expected_applied_rules, expected_flags,
                state_correct, rules_correct, flags_correct,
                latency_ms, input_tokens, output_tokens, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                decision.decision_id,
                decision.run_id,
                decision.event_id,
                decision.order_id,
                decision.model_id,
                json.dumps(decision.order_state_snapshot),
                json.dumps(decision.model_input),
                json.dumps(decision.model_output),
                decision.predicted_next_state,
                json.dumps(decision.predicted_applied_rules),
                json.dumps(decision.predicted_flags),
                decision.expected_next_state,
                json.dumps(decision.expected_applied_rules),
                json.dumps(decision.expected_flags),
                decision.state_correct,
                decision.rules_correct,
                decision.flags_correct,
                decision.latency_ms,
                decision.input_tokens,
                decision.output_tokens,
                _to_iso(decision.created_at),
            ),
        )
        if _commit:
            self._connection.commit()

    def get_decisions_for_run(self, run_id: str) -> list[Decision]:
        """Retrieve all decisions for a given run."""
        cursor = self._connection.execute(
            """SELECT decision_id, run_id, event_id, order_id, model_id,
                      order_state_snapshot, model_input, model_output,
                      predicted_next_state, predicted_applied_rules,
                      predicted_flags, expected_next_state,
                      expected_applied_rules, expected_flags,
                      state_correct, rules_correct, flags_correct,
                      latency_ms, input_tokens, output_tokens, created_at
               FROM decisions WHERE run_id = ?""",
            (run_id,),
        )
        decisions = []
        for row in cursor.fetchall():
            decisions.append(
                Decision(
                    decision_id=row["decision_id"],
                    run_id=row["run_id"],
                    event_id=row["event_id"],
                    order_id=row["order_id"],
                    model_id=row["model_id"],
                    order_state_snapshot=_load_dict(
                        row["order_state_snapshot"],
                        "order_state_snapshot",
                    ),
                    model_input=_load_dict(row["model_input"], "model_input"),
                    model_output=_load_dict(row["model_output"], "model_output"),
                    predicted_next_state=row["predicted_next_state"],
                    predicted_applied_rules=_load_string_list(
                        row["predicted_applied_rules"],
                        "predicted_applied_rules",
                    ),
                    predicted_flags=_load_string_list(
                        row["predicted_flags"],
                        "predicted_flags",
                    ),
                    expected_next_state=row["expected_next_state"],
                    expected_applied_rules=_load_string_list(
                        row["expected_applied_rules"],
                        "expected_applied_rules",
                    ),
                    expected_flags=_load_string_list(
                        row["expected_flags"],
                        "expected_flags",
                    ),
                    state_correct=bool(row["state_correct"]),
                    rules_correct=bool(row["rules_correct"]),
                    flags_correct=bool(row["flags_correct"]),
                    latency_ms=row["latency_ms"],
                    input_tokens=row["input_tokens"],
                    output_tokens=row["output_tokens"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
            )
        return decisions

    # --- Query Decisions ---

    def insert_query_decision(self, decision: QueryDecision, *, _commit: bool = True) -> None:
        """Insert a query decision row.

        Set ``_commit=False`` to defer commit for batch operations.
        """
        self._connection.execute(
            """INSERT INTO query_decisions (
                decision_id, run_id, scenario_id, model_id,
                tier, answer_type,
                database_state_snapshot, model_input, model_output,
                predicted_order_ids, expected_order_ids,
                order_ids_correct, precision, recall, f1,
                failure_type,
                latency_ms, input_tokens, output_tokens, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                decision.decision_id,
                decision.run_id,
                decision.scenario_id,
                decision.model_id,
                decision.tier,
                decision.answer_type,
                json.dumps(decision.database_state_snapshot),
                json.dumps(decision.model_input),
                json.dumps(decision.model_output),
                json.dumps(decision.predicted_order_ids),
                json.dumps(decision.expected_order_ids),
                decision.order_ids_correct,
                decision.precision,
                decision.recall,
                decision.f1,
                decision.failure_type,
                decision.latency_ms,
                decision.input_tokens,
                decision.output_tokens,
                _to_iso(decision.created_at),
            ),
        )
        if _commit:
            self._connection.commit()

    # --- Runs ---

    def insert_run(self, run: Run, *, _commit: bool = True) -> None:
        """Insert a run row.

        Set ``_commit=False`` to defer commit for batch operations.
        """
        self._connection.execute(
            """INSERT INTO runs (
                run_id, prompt_template_version, scenario_set_version,
                model_id, run_number, started_at, completed_at, notes, aborted
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run.run_id,
                run.prompt_template_version,
                run.scenario_set_version,
                run.model_id,
                run.run_number,
                _to_iso(run.started_at),
                _to_iso(run.completed_at),
                run.notes,
                int(run.aborted),
            ),
        )
        if _commit:
            self._connection.commit()

    def get_run(self, run_id: str) -> Run | None:
        """Retrieve a run by ID, or None if not found."""
        cursor = self._connection.execute(
            """SELECT run_id, prompt_template_version, scenario_set_version,
                      model_id, run_number, started_at, completed_at, notes,
                      aborted
               FROM runs WHERE run_id = ?""",
            (run_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return Run(
            run_id=row["run_id"],
            prompt_template_version=row["prompt_template_version"],
            scenario_set_version=row["scenario_set_version"],
            model_id=row["model_id"],
            run_number=row["run_number"],
            started_at=datetime.fromisoformat(row["started_at"]),
            completed_at=_from_iso(row["completed_at"]),
            notes=row["notes"],
            aborted=bool(row["aborted"]),
        )

    def update_run_completed(
        self,
        run_id: str,
        completed_at: datetime,
        *,
        aborted: bool = False,
    ) -> None:
        """Set the completion timestamp on a run.

        Args:
            run_id: The run to update.
            completed_at: Completion timestamp.
            aborted: If True, marks the run as aborted (early-abort).

        Raises ``ValueError`` if the run_id does not exist.
        """
        cursor = self._connection.execute(
            "UPDATE runs SET completed_at = ?, aborted = ? WHERE run_id = ?",
            (_to_iso(completed_at), int(aborted), run_id),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"Run not found: {run_id}")
        self._connection.commit()

    # --- Routing Decisions (live system) ---

    def insert_routing_decision(
        self,
        *,
        decision_id: str,
        event_id: str,
        order_id: str,
        model_id: str,
        from_state: str,
        to_state: str,
        applied_rules: list[str],
        flags: list[str],
        reasoning: str | None,
        transition_valid: bool,
        applied: bool,
        latency_ms: float,
        created_at: datetime,
        _commit: bool = True,
    ) -> None:
        """Insert a routing decision row for the live system.

        Set ``_commit=False`` to defer commit for atomic operations.
        """
        self._connection.execute(
            """INSERT INTO routing_decisions (
                decision_id, event_id, order_id, model_id,
                from_state, to_state, applied_rules, flags,
                reasoning, transition_valid, applied, latency_ms, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                decision_id,
                event_id,
                order_id,
                model_id,
                from_state,
                to_state,
                json.dumps(applied_rules),
                json.dumps(flags),
                reasoning,
                transition_valid,
                applied,
                latency_ms,
                _to_iso(created_at),
            ),
        )
        if _commit:
            self._connection.commit()

    def get_routing_decisions_for_order(self, order_id: str) -> list[dict[str, Any]]:
        """Retrieve all routing decisions for a given order."""
        cursor = self._connection.execute(
            """SELECT decision_id, event_id, order_id, model_id,
                      from_state, to_state, applied_rules, flags,
                      reasoning, transition_valid, applied, latency_ms,
                      created_at
               FROM routing_decisions WHERE order_id = ?
               ORDER BY created_at""",
            (order_id,),
        )
        results: list[dict[str, Any]] = []
        for row in cursor.fetchall():
            results.append(
                {
                    "decision_id": row["decision_id"],
                    "event_id": row["event_id"],
                    "order_id": row["order_id"],
                    "model_id": row["model_id"],
                    "from_state": row["from_state"],
                    "to_state": row["to_state"],
                    "applied_rules": _load_string_list(row["applied_rules"], "applied_rules"),
                    "flags": _load_string_list(row["flags"], "flags"),
                    "reasoning": row["reasoning"],
                    "transition_valid": bool(row["transition_valid"]),
                    "applied": bool(row["applied"]),
                    "latency_ms": row["latency_ms"],
                    "created_at": row["created_at"],
                }
            )
        return results
