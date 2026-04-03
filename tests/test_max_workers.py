"""Tests for --max-workers concurrency cap and pre-flight rate limit check.

Covers:
- CLI argument parsing and validation
- ThreadPoolExecutor worker capping in EvaluationHarness.run_all()
- OpenRouter rate limit check (check_rate_limit)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.evaluation.harness import DEFAULT_MAX_WORKERS, EvaluationHarness
from src.evaluation.runner import build_parser, main
from src.models.openrouter_adapter import RateLimitInfo, check_rate_limit


def _make_test_harness(
    n_models: int = 3,
    *,
    model_id: str = "qwen/qwen3-8b",
) -> EvaluationHarness:
    """Create a minimal EvaluationHarness with *n_models* openrouter configs."""
    from src.models.config import EvaluationSettings, ModelConfig
    from src.simulator.schema import ExpectedOutput, Scenario, ScenarioStep

    models = [
        ModelConfig(
            name=f"Model-{i}",
            provider="openrouter",
            model_id=model_id,
            temperature=0.0,
            max_tokens=1024,
            token_limit=131072,
        )
        for i in range(n_models)
    ]
    settings = EvaluationSettings(
        runs_per_model={"openrouter": 1},
        timeout_seconds=30,
        output_directory="results/test",
    )
    scenario = Scenario(
        scenario_id="SC-900",
        category="rule_coverage",
        description="Test scenario",
        steps=(
            ScenarioStep(
                step=1,
                event_type="order_received",
                event_data={
                    "patient_name": "TEST",
                    "age": 50,
                    "sex": "F",
                    "specimen_type": "biopsy",
                    "anatomic_site": "breast",
                    "fixative": "formalin",
                    "fixation_time_hours": 24.0,
                    "ordered_tests": ["H&E"],
                    "priority": "routine",
                    "billing_info_present": True,
                },
                expected_output=ExpectedOutput(
                    next_state="ACCEPTED",
                    applied_rules=("ACC-008",),
                    flags=(),
                ),
            ),
        ),
    )
    return EvaluationHarness(models, settings, [scenario], ":memory:")


# --- CLI argument parsing ---


class TestMaxWorkersCliArg:
    def test_default_is_none(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        assert args.max_workers is None

    def test_explicit_value(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--max-workers", "6"])
        assert args.max_workers == 6

    def test_zero_rejected(self) -> None:
        """--max-workers 0 should fail validation in main()."""
        result = main(["--max-workers", "0", "--dry-run"])
        assert result == 1

    def test_negative_rejected(self) -> None:
        result = main(["--max-workers", "-1", "--dry-run"])
        assert result == 1

    def test_positive_value_accepted_in_dry_run(self) -> None:
        result = main(["--max-workers", "2", "--dry-run"])
        assert result == 0


# --- EvaluationHarness default constant ---


class TestDefaultMaxWorkers:
    def test_default_is_four(self) -> None:
        assert DEFAULT_MAX_WORKERS == 4


# --- ThreadPoolExecutor capping ---


class TestThreadPoolExecutorCapping:
    """Verify that run_all() passes the correct max_workers to ThreadPoolExecutor."""

    @patch("src.evaluation.harness.EvaluationHarness._run_model_with_own_db")
    @patch("src.evaluation.harness.Database")
    def test_max_workers_caps_executor(
        self,
        mock_db_cls: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        """With 6 models and max_workers=3, ThreadPoolExecutor gets 3."""
        mock_run.return_value = []
        mock_db = MagicMock()
        mock_db_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_cls.return_value.__exit__ = MagicMock(return_value=False)

        harness = _make_test_harness(n_models=6)

        with patch("src.evaluation.harness.ThreadPoolExecutor") as mock_executor_cls:
            mock_executor = MagicMock()
            mock_executor.__enter__ = MagicMock(return_value=mock_executor)
            mock_executor.__exit__ = MagicMock(return_value=False)
            mock_executor.submit.return_value = MagicMock(
                exception=MagicMock(return_value=None),
                result=MagicMock(return_value=[]),
            )
            mock_executor_cls.return_value = mock_executor

            harness.run_all(parallel=True, max_workers=3)

            mock_executor_cls.assert_called_once_with(max_workers=3)

    @patch("src.evaluation.harness.EvaluationHarness._run_model_with_own_db")
    @patch("src.evaluation.harness.Database")
    def test_default_max_workers_when_none(
        self,
        mock_db_cls: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        """With 6 models and max_workers=None, uses default (4)."""
        mock_run.return_value = []
        mock_db = MagicMock()
        mock_db_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_cls.return_value.__exit__ = MagicMock(return_value=False)

        harness = _make_test_harness(n_models=6)

        with patch("src.evaluation.harness.ThreadPoolExecutor") as mock_executor_cls:
            mock_executor = MagicMock()
            mock_executor.__enter__ = MagicMock(return_value=mock_executor)
            mock_executor.__exit__ = MagicMock(return_value=False)
            mock_executor.submit.return_value = MagicMock(
                exception=MagicMock(return_value=None),
                result=MagicMock(return_value=[]),
            )
            mock_executor_cls.return_value = mock_executor

            harness.run_all(parallel=True)

            mock_executor_cls.assert_called_once_with(max_workers=4)

    @patch("src.evaluation.harness.EvaluationHarness._run_model_with_own_db")
    @patch("src.evaluation.harness.Database")
    def test_fewer_models_than_max_workers(
        self,
        mock_db_cls: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        """With 2 models and max_workers=4, capped to 2."""
        mock_run.return_value = []
        mock_db = MagicMock()
        mock_db_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_cls.return_value.__exit__ = MagicMock(return_value=False)

        harness = _make_test_harness(n_models=2)

        with patch("src.evaluation.harness.ThreadPoolExecutor") as mock_executor_cls:
            mock_executor = MagicMock()
            mock_executor.__enter__ = MagicMock(return_value=mock_executor)
            mock_executor.__exit__ = MagicMock(return_value=False)
            mock_executor.submit.return_value = MagicMock(
                exception=MagicMock(return_value=None),
                result=MagicMock(return_value=[]),
            )
            mock_executor_cls.return_value = mock_executor

            harness.run_all(parallel=True, max_workers=4)

            mock_executor_cls.assert_called_once_with(max_workers=2)


# --- Rate limit check ---

_FAKE_KEY_RESPONSE: dict[str, Any] = {
    "data": {
        "label": "samantha-eval",
        "rate_limit": {
            "requests": 200,
            "interval": "10s",
        },
    },
}


class TestCheckRateLimit:
    def test_successful_check(self) -> None:
        resp = httpx.Response(
            200,
            json=_FAKE_KEY_RESPONSE,
            request=httpx.Request("GET", "https://openrouter.ai/api/v1/key"),
        )
        with patch("src.models.openrouter_adapter.httpx.Client") as mock_cls:
            mock_client = MagicMock()
            mock_client.get.return_value = resp
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_cls.return_value = mock_client

            info = check_rate_limit("sk-or-test")

        assert info.requests_per_interval == 200
        assert info.interval_seconds == 10
        assert info.label == "samantha-eval"

    def test_minute_interval_parsing(self) -> None:
        body: dict[str, Any] = {
            "data": {
                "label": "test",
                "rate_limit": {"requests": 50, "interval": "1m"},
            },
        }
        resp = httpx.Response(
            200,
            json=body,
            request=httpx.Request("GET", "https://openrouter.ai/api/v1/key"),
        )
        with patch("src.models.openrouter_adapter.httpx.Client") as mock_cls:
            mock_client = MagicMock()
            mock_client.get.return_value = resp
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_cls.return_value = mock_client

            info = check_rate_limit("sk-or-test")

        assert info.interval_seconds == 60

    def test_connection_failure(self) -> None:
        with patch("src.models.openrouter_adapter.httpx.Client") as mock_cls:
            mock_client = MagicMock()
            mock_client.get.side_effect = httpx.ConnectError("refused")
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_cls.return_value = mock_client

            info = check_rate_limit("sk-or-test")

        assert info.requests_per_interval is None
        assert "unreachable" in info.label

    def test_non_200_status(self) -> None:
        resp = httpx.Response(
            403,
            text="Forbidden",
            request=httpx.Request("GET", "https://openrouter.ai/api/v1/key"),
        )
        with patch("src.models.openrouter_adapter.httpx.Client") as mock_cls:
            mock_client = MagicMock()
            mock_client.get.return_value = resp
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_cls.return_value = mock_client

            info = check_rate_limit("sk-or-test")

        assert info.requests_per_interval is None
        assert "403" in info.label

    def test_invalid_json_response(self) -> None:
        resp = httpx.Response(
            200,
            text="not json",
            request=httpx.Request("GET", "https://openrouter.ai/api/v1/key"),
        )
        with patch("src.models.openrouter_adapter.httpx.Client") as mock_cls:
            mock_client = MagicMock()
            mock_client.get.return_value = resp
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_cls.return_value = mock_client

            info = check_rate_limit("sk-or-test")

        assert info.requests_per_interval is None
        assert "invalid JSON" in info.label

    def test_missing_rate_limit_data(self) -> None:
        body: dict[str, Any] = {"data": {"label": "key-no-limits"}}
        resp = httpx.Response(
            200,
            json=body,
            request=httpx.Request("GET", "https://openrouter.ai/api/v1/key"),
        )
        with patch("src.models.openrouter_adapter.httpx.Client") as mock_cls:
            mock_client = MagicMock()
            mock_client.get.return_value = resp
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_cls.return_value = mock_client

            info = check_rate_limit("sk-or-test")

        assert info.requests_per_interval is None
        assert info.label == "key-no-limits"

    def test_unrecognized_interval_format_returns_none(self) -> None:
        body: dict[str, Any] = {
            "data": {
                "label": "test",
                "rate_limit": {"requests": 10, "interval": "1h"},
            },
        }
        resp = httpx.Response(
            200,
            json=body,
            request=httpx.Request("GET", "https://openrouter.ai/api/v1/key"),
        )
        with patch("src.models.openrouter_adapter.httpx.Client") as mock_cls:
            mock_client = MagicMock()
            mock_client.get.return_value = resp
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_cls.return_value = mock_client

            info = check_rate_limit("sk-or-test")

        assert info.interval_seconds is None
        assert info.requests_per_interval == 10

    def test_timeout_during_rate_check(self) -> None:
        with patch("src.models.openrouter_adapter.httpx.Client") as mock_cls:
            mock_client = MagicMock()
            mock_client.get.side_effect = httpx.TimeoutException("timed out")
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_cls.return_value = mock_client

            info = check_rate_limit("sk-or-test")

        assert info.requests_per_interval is None
        assert "unreachable" in info.label

    def test_float_requests_value(self) -> None:
        body: dict[str, Any] = {
            "data": {
                "label": "test",
                "rate_limit": {"requests": 200.0, "interval": "10s"},
            },
        }
        resp = httpx.Response(
            200,
            json=body,
            request=httpx.Request("GET", "https://openrouter.ai/api/v1/key"),
        )
        with patch("src.models.openrouter_adapter.httpx.Client") as mock_cls:
            mock_client = MagicMock()
            mock_client.get.return_value = resp
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_cls.return_value = mock_client

            info = check_rate_limit("sk-or-test")

        assert info.requests_per_interval == 200

    def test_negative_requests_treated_as_unlimited(self) -> None:
        """OpenRouter returns -1 for unlimited rate limits — normalize to None."""
        body: dict[str, Any] = {
            "data": {
                "label": "unlimited-key",
                "rate_limit": {"requests": -1, "interval": "10s"},
            },
        }
        resp = httpx.Response(
            200,
            json=body,
            request=httpx.Request("GET", "https://openrouter.ai/api/v1/key"),
        )
        with patch("src.models.openrouter_adapter.httpx.Client") as mock_cls:
            mock_client = MagicMock()
            mock_client.get.return_value = resp
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_cls.return_value = mock_client

            info = check_rate_limit("sk-or-test")

        assert info.requests_per_interval is None
        assert info.label == "unlimited-key"

    def test_truthy_non_dict_data_field(self) -> None:
        """API returns truthy non-dict data field — should not crash."""
        body: dict[str, Any] = {"data": "error message"}
        resp = httpx.Response(
            200,
            json=body,
            request=httpx.Request("GET", "https://openrouter.ai/api/v1/key"),
        )
        with patch("src.models.openrouter_adapter.httpx.Client") as mock_cls:
            mock_client = MagicMock()
            mock_client.get.return_value = resp
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_cls.return_value = mock_client

            info = check_rate_limit("sk-or-test")

        assert info.requests_per_interval is None
        assert info.label == "unknown"


class TestRateLimitInfoValidation:
    def test_immutable(self) -> None:
        info = RateLimitInfo(
            requests_per_interval=100,
            interval_seconds=10,
            label="test",
        )
        with pytest.raises(AttributeError):
            info.requests_per_interval = 200  # type: ignore[misc]

    def test_empty_label_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-empty string"):
            RateLimitInfo(requests_per_interval=100, interval_seconds=10, label="")

    def test_bool_requests_rejected(self) -> None:
        with pytest.raises(TypeError, match="must be int or None"):
            RateLimitInfo(requests_per_interval=True, interval_seconds=10, label="test")  # type: ignore[arg-type]

    def test_negative_interval_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            RateLimitInfo(requests_per_interval=100, interval_seconds=-1, label="test")

    def test_zero_requests_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            RateLimitInfo(requests_per_interval=0, interval_seconds=10, label="test")


# --- max_workers=1 boundary ---


class TestMaxWorkersOneBoundary:
    """Verify max_workers=1 forces serial execution via thread pool."""

    @patch("src.evaluation.harness.EvaluationHarness._run_model_with_own_db")
    @patch("src.evaluation.harness.Database")
    def test_max_workers_one_serial_execution(
        self,
        mock_db_cls: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        """With 3 models and max_workers=1, ThreadPoolExecutor gets 1."""
        mock_run.return_value = []
        mock_db = MagicMock()
        mock_db_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_cls.return_value.__exit__ = MagicMock(return_value=False)

        harness = _make_test_harness(n_models=3)

        with patch("src.evaluation.harness.ThreadPoolExecutor") as mock_executor_cls:
            mock_executor = MagicMock()
            mock_executor.__enter__ = MagicMock(return_value=mock_executor)
            mock_executor.__exit__ = MagicMock(return_value=False)
            mock_executor.submit.return_value = MagicMock(
                exception=MagicMock(return_value=None),
                result=MagicMock(return_value=[]),
            )
            mock_executor_cls.return_value = mock_executor

            harness.run_all(parallel=True, max_workers=1)

            mock_executor_cls.assert_called_once_with(max_workers=1)


# --- Parallel queue lifecycle messages ---


class TestParallelQueueLifecycle:
    """Verify queue submitted and model completion messages in parallel mode."""

    @patch("src.evaluation.harness._should_use_dashboard", return_value=False)
    @patch("src.evaluation.harness.EvaluationHarness._run_model")
    @patch("src.evaluation.harness.Database")
    def test_queue_submitted_message(
        self,
        mock_db_cls: MagicMock,
        mock_run_model: MagicMock,
        _mock_dashboard: MagicMock,
        capsys: Any,
    ) -> None:
        """Parallel run_all() prints queue submitted message."""
        mock_run_model.return_value = []
        mock_db = MagicMock()
        mock_db_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_cls.return_value.__exit__ = MagicMock(return_value=False)

        harness = _make_test_harness(n_models=3)
        harness.run_all(parallel=True, max_workers=2)

        captured = capsys.readouterr()
        assert "Queue: 3 models submitted (2 concurrent workers)" in captured.out

    @patch("src.evaluation.harness._should_use_dashboard", return_value=False)
    @patch("src.evaluation.harness.PredictionEngine")
    @patch("src.evaluation.harness.EvaluationHarness._create_adapter")
    @patch("src.evaluation.harness.Database")
    def test_completion_message(
        self,
        mock_db_cls: MagicMock,
        mock_create_adapter: MagicMock,
        mock_engine_cls: MagicMock,
        _mock_dashboard: MagicMock,
        capsys: Any,
    ) -> None:
        """_run_model prints completion message in parallel mode."""
        mock_adapter = MagicMock()
        mock_create_adapter.return_value = mock_adapter
        mock_engine = MagicMock()
        mock_engine.model_id = "test/model-0"
        mock_engine.predict_routing.return_value = MagicMock(
            next_state="ACCEPTED",
            applied_rules=["ACC-008"],
            flags=[],
            reasoning="ok",
            error=None,
            raw_response=MagicMock(
                latency_ms=100, input_tokens=10, output_tokens=20, timed_out=False
            ),
        )
        mock_engine_cls.return_value = mock_engine
        mock_db = MagicMock()
        mock_db_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_cls.return_value.__exit__ = MagicMock(return_value=False)

        harness = _make_test_harness(n_models=2)
        lock = __import__("threading").Lock()
        counter: list[int] = [0]

        harness._run_model(
            harness._models[0],
            1,
            1,
            mock_db,
            None,
            lock,
            completion_counter=counter,
            total_parallel_models=2,
        )

        assert counter[0] == 1
        captured = capsys.readouterr()
        assert "Completed" in captured.out
        assert "1/2 models done" in captured.out

    @patch("src.evaluation.harness.PredictionEngine")
    @patch("src.evaluation.harness.EvaluationHarness._create_adapter")
    @patch("src.evaluation.harness.Database")
    def test_no_completion_message_in_sequential_mode(
        self,
        mock_db_cls: MagicMock,
        mock_create_adapter: MagicMock,
        mock_engine_cls: MagicMock,
        capsys: Any,
    ) -> None:
        """_run_model does NOT print completion message without counter."""
        mock_adapter = MagicMock()
        mock_create_adapter.return_value = mock_adapter
        mock_engine = MagicMock()
        mock_engine.model_id = "test/model-0"
        mock_engine.predict_routing.return_value = MagicMock(
            next_state="ACCEPTED",
            applied_rules=["ACC-008"],
            flags=[],
            reasoning="ok",
            error=None,
            raw_response=MagicMock(
                latency_ms=100, input_tokens=10, output_tokens=20, timed_out=False
            ),
        )
        mock_engine_cls.return_value = mock_engine
        mock_db = MagicMock()
        mock_db_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_cls.return_value.__exit__ = MagicMock(return_value=False)

        harness = _make_test_harness(n_models=1)
        harness._run_model(
            harness._models[0],
            1,
            1,
            mock_db,
            None,
            None,
        )

        captured = capsys.readouterr()
        assert "Completed" not in captured.out
        assert "models done" not in captured.out


# --- Pre-flight rate limit block in runner.main() ---


_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestPreFlightRateLimit:
    """Test the pre-flight rate limit check block in runner.main()."""

    def test_rate_info_printed_on_success(self, capsys: Any) -> None:
        inside_path = str(_PROJECT_ROOT / "results" / "test-run")
        with (
            patch(
                "src.evaluation.runner.load_openrouter_key",
                return_value="sk-test",
            ),
            patch(
                "src.models.openrouter_adapter.check_rate_limit",
                return_value=RateLimitInfo(
                    requests_per_interval=200,
                    interval_seconds=10,
                    label="test-key",
                ),
            ),
            patch("src.evaluation.runner.EvaluationHarness") as mock_h,
        ):
            mock_h.return_value.run_all.return_value = []
            result = main(["--output", inside_path])

        assert result == 0
        captured = capsys.readouterr()
        assert "200 requests" in captured.out

    def test_rate_warning_when_workers_exceed_rate(self, capsys: Any) -> None:
        """Warning fires when effective_workers > requests_per_second."""
        inside_path = str(_PROJECT_ROOT / "results" / "test-run")
        with (
            patch(
                "src.evaluation.runner.load_openrouter_key",
                return_value="sk-test",
            ),
            patch(
                "src.models.openrouter_adapter.check_rate_limit",
                return_value=RateLimitInfo(
                    requests_per_interval=2,
                    interval_seconds=10,
                    label="test-key",
                ),
            ),
            patch("src.evaluation.runner.EvaluationHarness") as mock_h,
        ):
            mock_h.return_value.run_all.return_value = []
            # rate = 2/10s = 0.2 req/s; 5 workers > 0.2 => WARNING
            result = main(["--output", inside_path, "--parallel", "--max-workers", "5"])

        assert result == 0
        captured = capsys.readouterr()
        assert "WARNING" in captured.err

    def test_key_load_failure_is_hard_error(self, capsys: Any) -> None:
        """Missing API key should fail fast (return 1), not be swallowed as a warning."""
        inside_path = str(_PROJECT_ROOT / "results" / "test-run")
        with (
            patch(
                "src.evaluation.runner.load_openrouter_key",
                side_effect=ValueError("no key found"),
            ),
            patch("src.evaluation.runner.EvaluationHarness"),
        ):
            result = main(["--output", inside_path])

        assert result == 1
        captured = capsys.readouterr()
        assert "Error" in captured.err
        assert "no key found" in captured.err

    def test_no_warning_when_workers_below_rate(self, capsys: Any) -> None:
        """No WARNING when effective_workers <= requests_per_second."""
        inside_path = str(_PROJECT_ROOT / "results" / "test-run")
        with (
            patch(
                "src.evaluation.runner.load_openrouter_key",
                return_value="sk-test",
            ),
            patch(
                "src.models.openrouter_adapter.check_rate_limit",
                return_value=RateLimitInfo(
                    requests_per_interval=200,
                    interval_seconds=10,
                    label="test-key",
                ),
            ),
            patch("src.evaluation.runner.EvaluationHarness") as mock_h,
        ):
            mock_h.return_value.run_all.return_value = []
            # rate = 200/10s = 20 req/s; 2 workers < 20 => no WARNING
            result = main(["--output", inside_path, "--parallel", "--max-workers", "2"])

        assert result == 0
        captured = capsys.readouterr()
        assert "WARNING" not in captured.err

    def test_rate_check_skipped_for_local_only(self, capsys: Any) -> None:
        """check_rate_limit should not be called when only ollama models are present."""
        from src.models.config import EvaluationSettings, ModelConfig

        inside_path = str(_PROJECT_ROOT / "results" / "test-run")
        ollama_models = [
            ModelConfig(
                name="local-model",
                provider="llamacpp",
                model_id="test-local",
                temperature=0.0,
                max_tokens=1024,
                token_limit=4096,
            ),
        ]
        settings = EvaluationSettings(
            runs_per_model={"llamacpp": 1},
            timeout_seconds=30,
            output_directory="results/test",
        )
        with (
            patch("src.evaluation.runner.load_models", return_value=ollama_models),
            patch("src.evaluation.runner.load_settings", return_value=settings),
            patch("src.evaluation.runner.validate_config_consistency"),
            patch(
                "src.evaluation.runner.load_openrouter_key",
            ) as mock_load_key,
            patch("src.evaluation.runner.EvaluationHarness") as mock_h,
        ):
            mock_h.return_value.run_all.return_value = []
            result = main(["--output", inside_path])

        assert result == 0
        mock_load_key.assert_not_called()

    def test_key_load_os_error_is_hard_error(self, capsys: Any) -> None:
        """OSError from key load should also fail fast (return 1)."""
        inside_path = str(_PROJECT_ROOT / "results" / "test-run")
        with (
            patch(
                "src.evaluation.runner.load_openrouter_key",
                side_effect=OSError("Permission denied"),
            ),
            patch("src.evaluation.runner.EvaluationHarness"),
        ):
            result = main(["--output", inside_path])

        assert result == 1
        captured = capsys.readouterr()
        assert "Error" in captured.err
        assert "Permission denied" in captured.err


# --- _print_plan parallel output ---


class TestPrintPlanParallelOutput:
    def test_parallel_info_in_dry_run(self, capsys: Any) -> None:
        result = main(["--dry-run", "--parallel", "--max-workers", "2"])
        assert result == 0
        captured = capsys.readouterr()
        assert "Parallel: yes (max workers:" in captured.out

    def test_parallel_absent_without_flag(self, capsys: Any) -> None:
        """Parallel info should NOT appear in dry-run output without --parallel."""
        result = main(["--dry-run"])
        assert result == 0
        captured = capsys.readouterr()
        assert "Parallel:" not in captured.out
