"""Tests for the Rich Live evaluation dashboard.

Covers:
- ModelState dataclass defaults and field assignment
- Dashboard state transitions via public API (no Live rendering)
- Thread safety with concurrent updates
- Context manager start/stop lifecycle
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

from src.evaluation.dashboard import Dashboard, ModelState, ModelStatus

# --- ModelState defaults ---


class TestModelState:
    def test_defaults(self) -> None:
        state = ModelState(name="test-model")
        assert state.status == ModelStatus.PENDING
        assert state.current_run == 0
        assert state.total_runs == 0
        assert state.scenarios_done == 0
        assert state.total_scenarios == 0
        assert state.start_time is None
        assert state.elapsed_s == 0.0

    def test_field_assignment(self) -> None:
        state = ModelState(name="m1")
        state.status = ModelStatus.RUNNING
        state.current_run = 2
        assert state.status == ModelStatus.RUNNING
        assert state.current_run == 2


# --- Dashboard state transitions ---


class TestDashboardState:
    """Test state transitions via public API without Live rendering."""

    def _make_dashboard(self, names: list[str] | None = None) -> Dashboard:
        if names is None:
            names = ["ModelA", "ModelB"]
        return Dashboard(
            model_names=names,
            total_scenarios=10,
            total_models=len(names),
            effective_workers=2,
        )

    def test_initial_state_all_pending(self) -> None:
        d = self._make_dashboard()
        for state in d._models.values():
            assert state.status == ModelStatus.PENDING

    def test_model_started_sets_running(self) -> None:
        d = self._make_dashboard()
        d.model_started("ModelA", runs=3, scenarios=10)
        assert d._models["ModelA"].status == ModelStatus.RUNNING
        assert d._models["ModelA"].total_runs == 3
        assert d._models["ModelA"].total_scenarios == 10
        assert d._models["ModelA"].start_time is not None
        # ModelB still pending
        assert d._models["ModelB"].status == ModelStatus.PENDING

    def test_scenario_completed_updates_progress(self) -> None:
        d = self._make_dashboard()
        d.model_started("ModelA", runs=1, scenarios=10)
        d.scenario_completed(
            "ModelA",
            run=1,
            total_runs=1,
            scenario_idx=5,
            total=10,
            scenario_id="SC-005",
            passed=True,
            latency_s=1.2,
        )
        assert d._models["ModelA"].scenarios_done == 5
        assert d._models["ModelA"].current_run == 1
        assert len(d._log_lines) == 1

    def test_model_aborted_sets_status(self) -> None:
        d = self._make_dashboard()
        d.model_started("ModelA", runs=1, scenarios=10)
        d.model_aborted("ModelA", "too many fatal errors")
        assert d._models["ModelA"].status == ModelStatus.ABORTED
        assert len(d._log_lines) == 1

    def test_model_completed_sets_status(self) -> None:
        d = self._make_dashboard()
        d.model_started("ModelA", runs=1, scenarios=10)
        d.model_completed("ModelA", elapsed_s=42.5)
        assert d._models["ModelA"].status == ModelStatus.COMPLETE
        assert d._models["ModelA"].elapsed_s == 42.5
        assert len(d._log_lines) == 1

    def test_log_capped_at_max_lines(self) -> None:
        d = self._make_dashboard(["M1"])
        d.model_started("M1", runs=1, scenarios=30)
        for i in range(25):
            d.scenario_completed(
                "M1",
                run=1,
                total_runs=1,
                scenario_idx=i + 1,
                total=30,
                scenario_id=f"SC-{i + 1:03d}",
                passed=True,
                latency_s=0.5,
            )
        assert len(d._log_lines) == Dashboard._MAX_LOG_LINES

    def test_build_renderable_returns_group(self) -> None:
        from rich.console import Group

        d = self._make_dashboard()
        result = d._build_renderable()
        assert isinstance(result, Group)


# --- Thread safety ---


class TestDashboardThreadSafety:
    """Verify no crashes when 5 threads do concurrent updates."""

    def test_concurrent_updates_no_crash(self) -> None:
        names = [f"Model-{i}" for i in range(5)]
        d = Dashboard(
            model_names=names,
            total_scenarios=20,
            total_models=5,
            effective_workers=5,
        )
        barrier = threading.Barrier(5)

        def worker(name: str) -> None:
            barrier.wait()
            d.model_started(name, runs=1, scenarios=20)
            for i in range(20):
                d.scenario_completed(
                    name,
                    run=1,
                    total_runs=1,
                    scenario_idx=i + 1,
                    total=20,
                    scenario_id=f"SC-{i + 1:03d}",
                    passed=i % 3 != 0,
                    latency_s=0.1,
                )
            d.model_completed(name, elapsed_s=2.0)

        threads = [threading.Thread(target=worker, args=(n,)) for n in names]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        # All models should be complete
        for name in names:
            assert d._models[name].status == ModelStatus.COMPLETE
        # Log should be capped
        assert len(d._log_lines) <= Dashboard._MAX_LOG_LINES


# --- Context manager lifecycle ---


class TestDashboardContextManager:
    """Verify Live.start() and Live.stop() are called."""

    @patch("src.evaluation.dashboard.Live")
    def test_start_and_stop_called(self, mock_live_cls: MagicMock) -> None:
        mock_live = MagicMock()
        mock_live_cls.return_value = mock_live

        d = Dashboard(
            model_names=["M1"],
            total_scenarios=5,
            total_models=1,
            effective_workers=1,
        )
        with d:
            mock_live.start.assert_called_once()
        mock_live.stop.assert_called_once()

    @patch("src.evaluation.dashboard.Live")
    def test_stop_called_on_exception(self, mock_live_cls: MagicMock) -> None:
        mock_live = MagicMock()
        mock_live_cls.return_value = mock_live

        d = Dashboard(
            model_names=["M1"],
            total_scenarios=5,
            total_models=1,
            effective_workers=1,
        )
        try:
            with d:
                raise ValueError("boom")
        except ValueError:
            pass
        mock_live.stop.assert_called_once()
