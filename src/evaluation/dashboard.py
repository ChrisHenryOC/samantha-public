"""Rich Live terminal dashboard for parallel evaluation progress.

Displays a fixed status table (one row per model) and a capped scrolling
event log.  Worker threads call thread-safe update methods; Rich Live
refreshes the display at 4 fps.

Sequential mode and non-TTY output bypass this entirely — the harness
falls back to line-by-line prints.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


class ModelStatus(Enum):
    """Lifecycle status of a model during evaluation."""

    PENDING = "Pending"
    RUNNING = "Running"
    COMPLETE = "Complete"
    ABORTED = "Aborted"


_STATUS_STYLES: dict[ModelStatus, str] = {
    ModelStatus.PENDING: "dim",
    ModelStatus.RUNNING: "yellow",
    ModelStatus.COMPLETE: "green",
    ModelStatus.ABORTED: "red",
}


@dataclass
class ModelState:
    """Mutable per-model state tracked by the dashboard."""

    name: str
    status: ModelStatus = ModelStatus.PENDING
    current_run: int = 0
    total_runs: int = 0
    scenarios_done: int = 0
    total_scenarios: int = 0
    start_time: float | None = None
    elapsed_s: float = 0.0


class Dashboard:
    """Rich Live dashboard for parallel evaluation.

    Context manager that starts/stops a ``rich.live.Live`` display.
    All public update methods are thread-safe.
    """

    _MAX_LOG_LINES = 20

    def __init__(
        self,
        model_names: list[str],
        total_scenarios: int,
        total_models: int,
        effective_workers: int,
        *,
        force_terminal: bool = False,
    ) -> None:
        self._total_scenarios = total_scenarios
        self._total_models = total_models
        self._effective_workers = effective_workers
        self._force_terminal = force_terminal
        self._lock = threading.Lock()
        self._models: dict[str, ModelState] = {name: ModelState(name=name) for name in model_names}
        self._log_lines: list[Text] = []
        self._live: Live | None = None

    # -- Context manager --------------------------------------------------

    def __enter__(self) -> Dashboard:
        console = Console(force_terminal=True) if self._force_terminal else None
        self._live = Live(
            self._build_renderable(),
            console=console,
            refresh_per_second=4,
            transient=False,
        )
        self._live.start()
        return self

    def __exit__(self, *args: Any) -> None:
        if self._live is not None:
            self._live.stop()
            self._live = None

    # -- Thread-safe public API -------------------------------------------

    def model_started(
        self,
        name: str,
        *,
        runs: int,
        scenarios: int,
    ) -> None:
        """Mark a model as running."""
        with self._lock:
            state = self._models[name]
            state.status = ModelStatus.RUNNING
            state.total_runs = runs
            state.total_scenarios = scenarios
            state.start_time = time.monotonic()
        self._refresh()

    def scenario_completed(
        self,
        name: str,
        *,
        run: int,
        total_runs: int,
        scenario_idx: int,
        total: int,
        scenario_id: str,
        passed: bool,
        latency_s: float,
    ) -> None:
        """Record one scenario result and append to the event log."""
        ts = datetime.now().strftime("%H:%M:%S")
        tag = "[green]OK[/green]" if passed else "[red]FAIL[/red]"
        line = Text.from_markup(
            f"{ts} [{name}] Run {run}/{total_runs} | "
            f"{scenario_idx:>3}/{total} {scenario_id} [{tag}] ({latency_s:.1f}s)"
        )
        with self._lock:
            state = self._models[name]
            state.current_run = run
            state.scenarios_done = scenario_idx
            if state.start_time is not None:
                state.elapsed_s = time.monotonic() - state.start_time
            self._log_lines.append(line)
            if len(self._log_lines) > self._MAX_LOG_LINES:
                self._log_lines = self._log_lines[-self._MAX_LOG_LINES :]
        self._refresh()

    def model_aborted(self, name: str, message: str) -> None:
        """Mark a model as aborted and log the reason."""
        ts = datetime.now().strftime("%H:%M:%S")
        line = Text.from_markup(f"{ts} [red][{name}] ABORTED — {message}[/red]")
        with self._lock:
            state = self._models[name]
            state.status = ModelStatus.ABORTED
            if state.start_time is not None:
                state.elapsed_s = time.monotonic() - state.start_time
            self._log_lines.append(line)
            if len(self._log_lines) > self._MAX_LOG_LINES:
                self._log_lines = self._log_lines[-self._MAX_LOG_LINES :]
        self._refresh()

    def model_completed(self, name: str, *, elapsed_s: float) -> None:
        """Mark a model as complete."""
        ts = datetime.now().strftime("%H:%M:%S")
        line = Text.from_markup(f"{ts} [green][{name}] Completed ({elapsed_s:.1f}s)[/green]")
        with self._lock:
            state = self._models[name]
            state.status = ModelStatus.COMPLETE
            state.elapsed_s = elapsed_s
            self._log_lines.append(line)
            if len(self._log_lines) > self._MAX_LOG_LINES:
                self._log_lines = self._log_lines[-self._MAX_LOG_LINES :]
        self._refresh()

    # -- Internal ---------------------------------------------------------

    def _refresh(self) -> None:
        """Push updated renderable to Live (no-op if not started)."""
        if self._live is not None:
            self._live.update(self._build_renderable())

    def _build_renderable(self) -> Group:
        """Build the composite Rich renderable (table + log panel)."""
        with self._lock:
            models_snapshot = list(self._models.values())
            log_snapshot = list(self._log_lines)

        # Status table
        table = Table(
            title=f"Evaluation Progress ({self._effective_workers} concurrent workers)",
            show_lines=True,
        )
        table.add_column("Model", min_width=16)
        table.add_column("Status", min_width=8)
        table.add_column("Progress", min_width=8, justify="center")
        table.add_column("Run", min_width=6, justify="center")
        table.add_column("Elapsed", min_width=7, justify="right")

        for m in models_snapshot:
            style = _STATUS_STYLES.get(m.status, "")
            if m.status == ModelStatus.PENDING:
                progress = "\u2014"
                run_str = "\u2014"
                elapsed_str = "\u2014"
            else:
                progress = f"{m.scenarios_done}/{m.total_scenarios}"
                run_str = f"{m.current_run}/{m.total_runs}"
                elapsed_str = f"{m.elapsed_s:.1f}s"
            table.add_row(
                Text(m.name, style=style),
                Text(m.status.value, style=style),
                Text(progress, style=style),
                Text(run_str, style=style),
                Text(elapsed_str, style=style),
            )

        # Event log panel
        if log_snapshot:
            log_text = Text("\n").join(log_snapshot)
        else:
            log_text = Text("Waiting for results\u2026", style="dim")
        log_panel = Panel(
            log_text,
            title="Event Log",
            border_style="dim",
            height=self._MAX_LOG_LINES + 2,  # +2 for top/bottom border
        )

        return Group(table, log_panel)
