"""Tests for the query evaluation harness orchestration.

Uses mock adapters following the pattern from test_evaluation_harness.py.
"""

from __future__ import annotations

import json
import tempfile
import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.evaluation.query_harness import QueryEvaluationHarness
from src.evaluation.query_metrics import QueryResult
from src.models.base import ModelAdapter, ModelResponse
from src.models.config import EvaluationSettings, ModelConfig
from src.simulator.schema import (
    DatabaseStateSnapshot,
    QueryExpectedOutput,
    QueryScenario,
)
from src.workflow.database import Database

# --- Mock adapter ---


class MockQueryAdapter(ModelAdapter):
    """Adapter that returns preconfigured responses for query scenarios."""

    def __init__(
        self,
        responses: list[dict[str, Any]] | None = None,
        *,
        error: str | None = None,
    ) -> None:
        self._responses = responses or []
        self._error = error
        self._call_count = 0

    def predict(self, prompt: str) -> ModelResponse:
        if self._error:
            return ModelResponse(
                raw_text=f"<{self._error}>",
                parsed_output=None,
                latency_ms=100,
                input_tokens=50,
                output_tokens=20,
                cost_estimate_usd=None,
                model_id="mock-query-model",
                error=self._error,
            )

        if self._call_count < len(self._responses):
            response_data = self._responses[self._call_count]
        else:
            response_data = self._responses[-1] if self._responses else {}
        self._call_count += 1

        raw_text = json.dumps(response_data)
        return ModelResponse(
            raw_text=raw_text,
            parsed_output=response_data,
            latency_ms=150,
            input_tokens=100,
            output_tokens=30,
            cost_estimate_usd=None,
            model_id="mock-query-model",
        )

    def close(self) -> None:
        pass

    @property
    def model_id(self) -> str:
        return "mock-query-model"

    @property
    def provider(self) -> str:
        return "mock"


# --- Fixtures ---


def _make_db_state() -> DatabaseStateSnapshot:
    """Build a minimal database state snapshot."""
    return DatabaseStateSnapshot(
        orders=(
            {
                "order_id": "ORD-101",
                "current_state": "ACCEPTED",
                "specimen_type": "biopsy",
                "anatomic_site": "breast",
                "priority": "routine",
                "flags": [],
            },
            {
                "order_id": "ORD-102",
                "current_state": "SAMPLE_PREP_PROCESSING",
                "specimen_type": "excision",
                "anatomic_site": "breast",
                "priority": "routine",
                "flags": [],
            },
        ),
        slides=(),
    )


def _make_query_scenario(
    scenario_id: str = "QR-001",
    tier: int = 1,
    answer_type: str = "order_list",
    expected_order_ids: tuple[str, ...] = ("ORD-101",),
) -> QueryScenario:
    """Build a QueryScenario with default or custom parameters."""
    return QueryScenario(
        scenario_id=scenario_id,
        category="query",
        tier=tier,
        description=f"Test query scenario {scenario_id}",
        database_state=_make_db_state(),
        query="What orders are ready for grossing?",
        expected_output=QueryExpectedOutput(
            answer_type=answer_type,
            reasoning="Orders in ACCEPTED state are ready for grossing.",
            order_ids=expected_order_ids,
        ),
    )


def _correct_query_response(
    scenario: QueryScenario,
) -> dict[str, Any]:
    """Build a model response dict matching the expected output."""
    answer_type = scenario.expected_output.answer_type
    if answer_type == "explanation":
        return {
            "explanation": "Test explanation",
            "reasoning": "Mock reasoning",
        }
    return {
        "order_ids": list(scenario.expected_output.order_ids),
        "reasoning": "Mock reasoning",
    }


def _make_query_harness(
    adapter: MockQueryAdapter,
    scenarios: list[QueryScenario],
    settings: EvaluationSettings | None = None,
) -> tuple[QueryEvaluationHarness, Path]:
    """Create a query harness with a mock adapter and temp DB."""
    tmpdir = tempfile.mkdtemp()
    db_path = Path(tmpdir) / "test_query.db"

    if settings is None:
        settings = EvaluationSettings(
            runs_per_model={"llamacpp": 1, "openrouter": 1},
            timeout_seconds=120,
            output_directory="results",
        )

    config = ModelConfig(
        name="test-query-model",
        provider="llamacpp",
        model_id="mock-query-model",
        temperature=0.0,
        max_tokens=2048,
        token_limit=8192,
    )

    harness = QueryEvaluationHarness([config], settings, scenarios, db_path)
    return harness, db_path


# --- Unit tests: _run_query_scenario ---


class TestRunQueryScenarioCorrect:
    def test_single_scenario_correct(self) -> None:
        """Correct response produces all_correct=True."""
        scenario = _make_query_scenario()
        adapter = MockQueryAdapter(responses=[_correct_query_response(scenario)])

        with patch.object(QueryEvaluationHarness, "_create_adapter", return_value=adapter):
            harness, _ = _make_query_harness(adapter, [scenario])
            results = harness.run_all()

        assert len(results) == 1
        assert results[0].all_correct is True
        assert results[0].scenario_id == "QR-001"
        assert results[0].tier == 1
        assert results[0].answer_type == "order_list"

    def test_wrong_order_ids(self) -> None:
        """Wrong order IDs produce all_correct=False."""
        scenario = _make_query_scenario()
        adapter = MockQueryAdapter(
            responses=[
                {
                    "order_ids": ["ORD-999"],
                    "reasoning": "Wrong answer",
                }
            ]
        )

        with patch.object(QueryEvaluationHarness, "_create_adapter", return_value=adapter):
            harness, _ = _make_query_harness(adapter, [scenario])
            results = harness.run_all()

        assert len(results) == 1
        assert results[0].all_correct is False
        assert results[0].validation.order_ids_correct is False


class TestRunQueryScenarioError:
    def test_model_error_recorded(self) -> None:
        """Model error produces failure_type and all_correct=False."""
        scenario = _make_query_scenario()
        adapter = MockQueryAdapter(error="timeout: model did not respond")

        with patch.object(QueryEvaluationHarness, "_create_adapter", return_value=adapter):
            harness, _ = _make_query_harness(adapter, [scenario])
            results = harness.run_all()

        assert len(results) == 1
        assert results[0].all_correct is False
        assert results[0].failure_type is not None


# --- Integration tests: QueryDecision persisted ---


class TestQueryDecisionsPersistedToDatabase:
    def test_decisions_in_db(self) -> None:
        """QueryDecision rows are persisted to the database."""
        scenario = _make_query_scenario()
        adapter = MockQueryAdapter(responses=[_correct_query_response(scenario)])

        with patch.object(QueryEvaluationHarness, "_create_adapter", return_value=adapter):
            harness, db_path = _make_query_harness(adapter, [scenario])
            harness.run_all()

        with Database(db_path) as db:
            cursor = db._connection.execute("SELECT COUNT(*) FROM query_decisions")
            count = cursor.fetchone()[0]
            assert count == 1

            cursor = db._connection.execute("SELECT COUNT(*) FROM runs")
            count = cursor.fetchone()[0]
            assert count == 1

    def test_two_scenarios_two_decisions(self) -> None:
        """Two scenarios produce two QueryDecision rows."""
        scenarios = [
            _make_query_scenario("QR-001", expected_order_ids=("ORD-101",)),
            _make_query_scenario("QR-002", expected_order_ids=("ORD-102",)),
        ]
        adapter = MockQueryAdapter(
            responses=[
                {"order_ids": ["ORD-101"], "reasoning": "r1"},
                {"order_ids": ["ORD-102"], "reasoning": "r2"},
            ]
        )

        with patch.object(QueryEvaluationHarness, "_create_adapter", return_value=adapter):
            harness, db_path = _make_query_harness(adapter, scenarios)
            results = harness.run_all()

        assert len(results) == 2

        with Database(db_path) as db:
            cursor = db._connection.execute("SELECT COUNT(*) FROM query_decisions")
            assert cursor.fetchone()[0] == 2


# --- QueryResult field validation ---


class TestQueryResultFields:
    def test_result_matches_validation(self) -> None:
        """QueryResult fields match the validation output."""
        scenario = _make_query_scenario()
        adapter = MockQueryAdapter(responses=[_correct_query_response(scenario)])

        with patch.object(QueryEvaluationHarness, "_create_adapter", return_value=adapter):
            harness, _ = _make_query_harness(adapter, [scenario])
            results = harness.run_all()

        result = results[0]
        assert result.validation.order_ids_correct is True
        assert result.validation.precision == 1.0
        assert result.validation.recall == 1.0
        assert result.validation.f1 == 1.0
        assert result.decision.latency_ms == 150
        assert result.decision.input_tokens == 100
        assert result.decision.output_tokens == 30


# --- Multiple models ---


class TestQueryHarnessMultipleModels:
    def test_two_distinct_models_no_pk_collision(self) -> None:
        """Two distinct model configs sharing a DB produce separate decisions."""
        scenario = _make_query_scenario()
        adapter = MockQueryAdapter(responses=[_correct_query_response(scenario)])
        settings = EvaluationSettings(
            runs_per_model={"llamacpp": 1, "openrouter": 1},
            timeout_seconds=120,
            output_directory="results",
        )

        config_a = ModelConfig(
            name="model-a",
            provider="llamacpp",
            model_id="model-a",
            temperature=0.0,
            max_tokens=2048,
            token_limit=8192,
        )
        config_b = ModelConfig(
            name="model-b",
            provider="llamacpp",
            model_id="model-b",
            temperature=0.0,
            max_tokens=2048,
            token_limit=8192,
        )

        tmpdir = tempfile.mkdtemp()
        db_path = Path(tmpdir) / "test.db"
        harness = QueryEvaluationHarness([config_a, config_b], settings, [scenario], db_path)

        with patch.object(QueryEvaluationHarness, "_create_adapter", return_value=adapter):
            results = harness.run_all()

        assert len(results) == 2

        with Database(db_path) as db:
            cursor = db._connection.execute("SELECT COUNT(*) FROM query_decisions")
            assert cursor.fetchone()[0] == 2


# --- Callback tests ---


class TestQueryOnRunCompleteCallback:
    def test_callback_called_per_run(self) -> None:
        """on_run_complete is called once per run with correct args."""
        scenario = _make_query_scenario()
        adapter = MockQueryAdapter(responses=[_correct_query_response(scenario)])
        settings = EvaluationSettings(
            runs_per_model={"llamacpp": 3, "openrouter": 1},
            timeout_seconds=120,
            output_directory="results",
        )

        callback_calls: list[tuple[str, int, int, bool]] = []

        def _on_run(
            model_id: str,
            run_number: int,
            results: list[QueryResult],
            aborted: bool,
        ) -> None:
            callback_calls.append((model_id, run_number, len(results), aborted))

        with patch.object(QueryEvaluationHarness, "_create_adapter", return_value=adapter):
            harness, _ = _make_query_harness(adapter, [scenario], settings=settings)
            harness.run_all(on_run_complete=_on_run)

        assert len(callback_calls) == 3
        assert [c[1] for c in callback_calls] == [1, 2, 3]
        assert all(c[0] == "mock-query-model" for c in callback_calls)
        assert all(c[3] is False for c in callback_calls)


# --- Explanation answer type ---


class TestExplanationAnswerType:
    def test_explanation_scenario_correct(self) -> None:
        """Explanation answer type is always 'correct' if structured properly."""
        scenario = _make_query_scenario(
            scenario_id="QR-003",
            answer_type="explanation",
            expected_order_ids=(),
        )
        adapter = MockQueryAdapter(
            responses=[
                {
                    "explanation": "This is a test explanation.",
                    "reasoning": "Mock reasoning",
                }
            ]
        )

        with patch.object(QueryEvaluationHarness, "_create_adapter", return_value=adapter):
            harness, _ = _make_query_harness(adapter, [scenario])
            results = harness.run_all()

        assert len(results) == 1
        assert results[0].all_correct is True


# --- Wrong field type detection ---


class TestWrongFieldType:
    def test_non_list_order_ids_caught_by_parser(self) -> None:
        """Non-list order_ids is caught by the parser and scored as failure."""
        scenario = _make_query_scenario()
        adapter = MockQueryAdapter(
            responses=[
                {
                    "order_ids": "ORD-101",  # string, not list
                    "reasoning": "Wrong type",
                }
            ]
        )

        with patch.object(QueryEvaluationHarness, "_create_adapter", return_value=adapter):
            harness, _ = _make_query_harness(adapter, [scenario])
            results = harness.run_all()

        assert len(results) == 1
        assert results[0].all_correct is False
        assert results[0].failure_type is not None


# --- Prioritized list answer type ---


class TestPrioritizedListAnswerType:
    def test_correct_order_produces_all_correct(self) -> None:
        """Prioritized list with correct order is all_correct=True."""
        scenario = _make_query_scenario(
            scenario_id="QR-010",
            answer_type="prioritized_list",
            expected_order_ids=("ORD-101", "ORD-102"),
        )
        adapter = MockQueryAdapter(
            responses=[
                {
                    "order_ids": ["ORD-101", "ORD-102"],
                    "reasoning": "Correct order",
                }
            ]
        )

        with patch.object(QueryEvaluationHarness, "_create_adapter", return_value=adapter):
            harness, _ = _make_query_harness(adapter, [scenario])
            results = harness.run_all()

        assert len(results) == 1
        assert results[0].all_correct is True

    def test_wrong_order_produces_incorrect(self) -> None:
        """Prioritized list with wrong order is all_correct=False."""
        scenario = _make_query_scenario(
            scenario_id="QR-011",
            answer_type="prioritized_list",
            expected_order_ids=("ORD-101", "ORD-102"),
        )
        adapter = MockQueryAdapter(
            responses=[
                {
                    "order_ids": ["ORD-102", "ORD-101"],
                    "reasoning": "Wrong order",
                }
            ]
        )

        with patch.object(QueryEvaluationHarness, "_create_adapter", return_value=adapter):
            harness, _ = _make_query_harness(adapter, [scenario])
            results = harness.run_all()

        assert len(results) == 1
        assert results[0].all_correct is False


# --- Order status answer type ---


class TestOrderStatusAnswerType:
    def test_order_status_correct(self) -> None:
        """Order status answer type with correct IDs is all_correct=True."""
        scenario = _make_query_scenario(
            scenario_id="QR-012",
            answer_type="order_status",
            expected_order_ids=("ORD-101",),
        )
        adapter = MockQueryAdapter(
            responses=[
                {
                    "order_ids": ["ORD-101"],
                    "status_summary": "In ACCEPTED state",
                    "reasoning": "Mock reasoning",
                }
            ]
        )

        with patch.object(QueryEvaluationHarness, "_create_adapter", return_value=adapter):
            harness, _ = _make_query_harness(adapter, [scenario])
            results = harness.run_all()

        assert len(results) == 1
        assert results[0].all_correct is True


# --- Early-abort pathway ---


class TestEarlyAbortPathway:
    def test_early_abort_triggers_on_fatal_errors(self) -> None:
        """Early abort fires when >50% of scenarios have fatal errors."""
        # 16 scenarios, all returning errors -> should abort
        scenarios = [_make_query_scenario(f"QR-{i:03d}") for i in range(16)]
        adapter = MockQueryAdapter(error="timeout: model did not respond")

        with patch.object(QueryEvaluationHarness, "_create_adapter", return_value=adapter):
            harness, db_path = _make_query_harness(adapter, scenarios)
            callback_calls: list[tuple[str, int, int, bool]] = []

            def _on_run(
                model_id: str,
                run_number: int,
                results: list[QueryResult],
                aborted: bool,
            ) -> None:
                callback_calls.append((model_id, run_number, len(results), aborted))

            harness.run_all(on_run_complete=_on_run)

        assert len(callback_calls) == 1
        # Should be aborted
        assert callback_calls[0][3] is True
        # Should have fewer results than total scenarios (aborted early)
        assert callback_calls[0][2] < 16

        # Verify run marked as aborted in DB
        with Database(db_path) as db:
            cursor = db._connection.execute("SELECT aborted FROM runs LIMIT 1")
            assert cursor.fetchone()[0] == 1


# --- Timed out path ---


class TestTimedOutPath:
    def test_timed_out_response_classified_as_timeout(self) -> None:
        """Model response with timed_out=True produces TIMEOUT failure."""
        from src.workflow.query_validator import QueryFailureType

        scenario = _make_query_scenario()

        class TimedOutAdapter(MockQueryAdapter):
            def predict(self, prompt: str) -> ModelResponse:
                return ModelResponse(
                    raw_text="<timeout>",
                    parsed_output=None,
                    latency_ms=120000,
                    input_tokens=50,
                    output_tokens=0,
                    cost_estimate_usd=None,
                    model_id="mock-query-model",
                    error="timeout",
                    timed_out=True,
                )

        adapter = TimedOutAdapter()

        with patch.object(QueryEvaluationHarness, "_create_adapter", return_value=adapter):
            harness, _ = _make_query_harness(adapter, [scenario])
            results = harness.run_all()

        assert len(results) == 1
        assert results[0].failure_type == QueryFailureType.TIMEOUT


# --- run_all returns results even with callback ---


class TestRunAllReturnsWithCallback:
    def test_callback_receives_results(self) -> None:
        """When callback is set, results go to callback (not return value)."""
        scenario = _make_query_scenario()
        adapter = MockQueryAdapter(responses=[_correct_query_response(scenario)])

        callback_results: list[list[QueryResult]] = []

        def _on_run(
            model_id: str,
            run_number: int,
            results: list[QueryResult],
            aborted: bool,
        ) -> None:
            callback_results.append(results)

        with patch.object(QueryEvaluationHarness, "_create_adapter", return_value=adapter):
            harness, _ = _make_query_harness(adapter, [scenario])
            returned = harness.run_all(on_run_complete=_on_run)

        assert len(callback_results) == 1
        assert len(callback_results[0]) == 1
        # With callback, return value is empty (consistent with routing harness)
        assert len(returned) == 0


# --- E2E smoke test: all real query scenarios ---


@pytest.mark.integration
class TestQueryHarnessAllScenariosSmoke:
    """Load every real query scenario and run through harness with mock adapter."""

    def test_all_query_scenarios_complete_without_error(self) -> None:
        from src.simulator.loader import load_all_query_scenarios

        scenario_dir = Path("scenarios/query")
        if not scenario_dir.exists():
            pytest.skip("scenarios/query not found")

        scenarios = load_all_query_scenarios(scenario_dir)
        assert len(scenarios) > 0

        # Build per-scenario responses matching each answer_type schema
        responses: list[dict[str, Any]] = []
        for s in scenarios:
            at = s.expected_output.answer_type
            if at == "explanation":
                responses.append({"explanation": "mock", "reasoning": "mock"})
            elif at == "order_status":
                responses.append(
                    {
                        "order_ids": ["ORD-101"],
                        "status_summary": "mock",
                        "reasoning": "mock",
                    }
                )
            else:
                responses.append({"order_ids": ["ORD-101"], "reasoning": "mock"})

        adapter = MockQueryAdapter(responses=responses)

        with patch.object(QueryEvaluationHarness, "_create_adapter", return_value=adapter):
            harness, _ = _make_query_harness(adapter, scenarios)
            results = harness.run_all()

        assert len(results) == len(scenarios)
        result_ids = {r.scenario_id for r in results}
        scenario_ids = {s.scenario_id for s in scenarios}
        assert result_ids == scenario_ids


# --- Parallel execution ---


def _make_adapter_factory(
    scenario: QueryScenario,
) -> Any:
    """Return a factory that creates a fresh MockQueryAdapter per call."""

    def _factory(config: ModelConfig) -> MockQueryAdapter:
        return MockQueryAdapter(responses=[_correct_query_response(scenario)])

    return _factory


class TestParallelExecution:
    def test_parallel_false_is_default(self) -> None:
        """parallel=False by default, unchanged sequential behavior."""
        scenario = _make_query_scenario()
        adapter = MockQueryAdapter(responses=[_correct_query_response(scenario)])

        with patch.object(QueryEvaluationHarness, "_create_adapter", return_value=adapter):
            harness, _ = _make_query_harness(adapter, [scenario])
            results = harness.run_all()

        assert len(results) == 1
        assert results[0].all_correct is True

    def test_parallel_true_with_cloud_models(self, tmp_path: Path) -> None:
        """parallel=True runs cloud models concurrently and produces correct results."""
        scenario = _make_query_scenario()
        factory = _make_adapter_factory(scenario)
        settings = EvaluationSettings(
            runs_per_model={"llamacpp": 1, "openrouter": 1},
            timeout_seconds=120,
            output_directory="results",
        )

        config_a = ModelConfig(
            name="cloud-a",
            provider="openrouter",
            model_id="cloud-model-a",
            temperature=0.0,
            max_tokens=2048,
            token_limit=8192,
        )
        config_b = ModelConfig(
            name="cloud-b",
            provider="openrouter",
            model_id="cloud-model-b",
            temperature=0.0,
            max_tokens=2048,
            token_limit=8192,
        )

        db_path = tmp_path / "test.db"
        harness = QueryEvaluationHarness([config_a, config_b], settings, [scenario], db_path)

        with patch.object(QueryEvaluationHarness, "_create_adapter", side_effect=factory):
            results = harness.run_all(parallel=True)

        # 2 cloud models * 1 run * 1 scenario = 2 results
        assert len(results) == 2

        # Verify DB has correct counts
        with Database(db_path) as db:
            cursor = db._connection.execute("SELECT COUNT(*) FROM query_decisions")
            assert cursor.fetchone()[0] == 2
            cursor = db._connection.execute(
                "SELECT COUNT(*) FROM runs WHERE completed_at IS NOT NULL"
            )
            assert cursor.fetchone()[0] == 2

    def test_parallel_mixed_local_and_cloud(self, tmp_path: Path) -> None:
        """parallel=True: single local model runs concurrently with cloud models."""
        scenario = _make_query_scenario()
        factory = _make_adapter_factory(scenario)
        settings = EvaluationSettings(
            runs_per_model={"llamacpp": 1, "openrouter": 1},
            timeout_seconds=120,
            output_directory="results",
        )

        local_model = ModelConfig(
            name="local-model",
            provider="llamacpp",
            model_id="local-model",
            temperature=0.0,
            max_tokens=2048,
            token_limit=8192,
        )
        cloud_model = ModelConfig(
            name="cloud-a",
            provider="openrouter",
            model_id="cloud-a",
            temperature=0.0,
            max_tokens=2048,
            token_limit=8192,
        )

        db_path = tmp_path / "test.db"
        harness = QueryEvaluationHarness([local_model, cloud_model], settings, [scenario], db_path)

        with patch.object(QueryEvaluationHarness, "_create_adapter", side_effect=factory):
            results = harness.run_all(parallel=True)

        # 1 local + 1 cloud = 2 results
        assert len(results) == 2

        with Database(db_path) as db:
            cursor = db._connection.execute("SELECT COUNT(*) FROM query_decisions")
            assert cursor.fetchone()[0] == 2
            cursor = db._connection.execute(
                "SELECT COUNT(*) FROM runs WHERE completed_at IS NOT NULL"
            )
            assert cursor.fetchone()[0] == 2

    def test_callback_thread_safety(self, tmp_path: Path) -> None:
        """Callbacks under parallel=True are serialized — no concurrent entry."""
        scenario = _make_query_scenario()
        factory = _make_adapter_factory(scenario)
        settings = EvaluationSettings(
            runs_per_model={"openrouter": 1},
            timeout_seconds=120,
            output_directory="results",
        )

        config_a = ModelConfig(
            name="cloud-a",
            provider="openrouter",
            model_id="cloud-a",
            temperature=0.0,
            max_tokens=2048,
            token_limit=8192,
        )
        config_b = ModelConfig(
            name="cloud-b",
            provider="openrouter",
            model_id="cloud-b",
            temperature=0.0,
            max_tokens=2048,
            token_limit=8192,
        )

        db_path = tmp_path / "test.db"
        harness = QueryEvaluationHarness([config_a, config_b], settings, [scenario], db_path)

        in_callback = threading.Event()
        overlap_detected: list[bool] = []
        callback_calls: list[tuple[str, int, bool]] = []

        def _on_run(
            model_id: str,
            run_number: int,
            results: list[QueryResult],
            aborted: bool,
        ) -> None:
            if in_callback.is_set():
                overlap_detected.append(True)
            in_callback.set()
            time.sleep(0.01)
            in_callback.clear()
            callback_calls.append((model_id, run_number, aborted))

        with patch.object(QueryEvaluationHarness, "_create_adapter", side_effect=factory):
            harness.run_all(on_run_complete=_on_run, parallel=True)

        assert len(callback_calls) == 2
        model_ids = {c[0] for c in callback_calls}
        assert model_ids == {"cloud-a", "cloud-b"}
        assert overlap_detected == [], "Callbacks were called concurrently"

    def test_parallel_single_model_failure_reraises(self, tmp_path: Path) -> None:
        """When one cloud model fails, run_all raises that exception."""
        scenario = _make_query_scenario()
        settings = EvaluationSettings(
            runs_per_model={"openrouter": 1},
            timeout_seconds=120,
            output_directory="results",
        )
        config = ModelConfig(
            name="fail-model",
            provider="openrouter",
            model_id="fail-model",
            temperature=0.0,
            max_tokens=2048,
            token_limit=8192,
        )

        db_path = tmp_path / "test.db"
        harness = QueryEvaluationHarness([config], settings, [scenario], db_path)

        def _failing_adapter(_cfg: ModelConfig) -> MockQueryAdapter:
            raise ValueError("adapter init failed")

        with (
            patch.object(QueryEvaluationHarness, "_create_adapter", side_effect=_failing_adapter),
            pytest.raises(RuntimeError, match="Model .* failed"),
        ):
            harness.run_all(parallel=True)

    def test_parallel_multiple_model_failures_wraps(self, tmp_path: Path) -> None:
        """When two cloud models fail, run_all raises RuntimeError with count."""
        scenario = _make_query_scenario()
        settings = EvaluationSettings(
            runs_per_model={"openrouter": 1},
            timeout_seconds=120,
            output_directory="results",
        )
        config_a = ModelConfig(
            name="fail-a",
            provider="openrouter",
            model_id="fail-a",
            temperature=0.0,
            max_tokens=2048,
            token_limit=8192,
        )
        config_b = ModelConfig(
            name="fail-b",
            provider="openrouter",
            model_id="fail-b",
            temperature=0.0,
            max_tokens=2048,
            token_limit=8192,
        )

        db_path = tmp_path / "test.db"
        harness = QueryEvaluationHarness([config_a, config_b], settings, [scenario], db_path)

        def _failing_adapter(_cfg: ModelConfig) -> MockQueryAdapter:
            raise ValueError("adapter init failed")

        with (
            patch.object(QueryEvaluationHarness, "_create_adapter", side_effect=_failing_adapter),
            pytest.raises(RuntimeError, match="2 model"),
        ):
            harness.run_all(parallel=True)

    def test_parallel_multiple_local_models_run_sequentially(self, tmp_path: Path) -> None:
        """With 2+ local models, they run sequentially before cloud models."""
        scenario = _make_query_scenario()
        settings = EvaluationSettings(
            runs_per_model={"llamacpp": 1, "openrouter": 1},
            timeout_seconds=120,
            output_directory="results",
        )
        correct_answer = {"order_ids": ["ORD-101"], "reasoning": "test"}
        local_a = ModelConfig(
            name="Local A",
            provider="llamacpp",
            model_id="local-a",
            temperature=0.0,
            max_tokens=1024,
            token_limit=131072,
        )
        local_b = ModelConfig(
            name="Local B",
            provider="llamacpp",
            model_id="local-b",
            temperature=0.0,
            max_tokens=1024,
            token_limit=131072,
        )

        db_path = tmp_path / "test.db"
        harness = QueryEvaluationHarness([local_a, local_b], settings, [scenario], db_path)

        with patch.object(
            QueryEvaluationHarness,
            "_create_adapter",
            side_effect=lambda config: MockQueryAdapter([correct_answer]),
        ):
            results = harness.run_all(parallel=True)

        # Both local models should produce results (mock returns same model_id)
        assert len(results) == 2


# --- ThreadPoolExecutor worker capping ---


class TestQueryThreadPoolExecutorCapping:
    """Verify that run_all() passes the correct max_workers to ThreadPoolExecutor."""

    @patch("src.evaluation.query_harness.QueryEvaluationHarness._run_model_with_own_db")
    @patch("src.evaluation.query_harness.Database")
    def test_max_workers_caps_executor(
        self,
        mock_db_cls: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        """With 3 models and max_workers=2, ThreadPoolExecutor gets 2."""
        mock_run.return_value = []
        mock_db = MagicMock()
        mock_db_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_cls.return_value.__exit__ = MagicMock(return_value=False)

        configs = [
            ModelConfig(
                name=f"Model-{i}",
                provider="openrouter",
                model_id=f"model-{i}",
                temperature=0.0,
                max_tokens=2048,
                token_limit=8192,
            )
            for i in range(3)
        ]
        settings = EvaluationSettings(
            runs_per_model={"openrouter": 1},
            timeout_seconds=120,
            output_directory="results",
        )
        scenario = _make_query_scenario()
        harness = QueryEvaluationHarness(configs, settings, [scenario], ":memory:")

        with patch("src.evaluation.query_harness.ThreadPoolExecutor") as mock_executor_cls:
            mock_executor = MagicMock()
            mock_executor.__enter__ = MagicMock(return_value=mock_executor)
            mock_executor.__exit__ = MagicMock(return_value=False)
            mock_executor.submit.return_value = MagicMock(
                exception=MagicMock(return_value=None),
                result=MagicMock(return_value=[]),
            )
            mock_executor_cls.return_value = mock_executor

            harness.run_all(parallel=True, max_workers=2)

            mock_executor_cls.assert_called_once_with(max_workers=2)

    @patch("src.evaluation.query_harness.QueryEvaluationHarness._run_model_with_own_db")
    @patch("src.evaluation.query_harness.Database")
    def test_default_max_workers(
        self,
        mock_db_cls: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        """With 6 models and no max_workers, uses DEFAULT_MAX_WORKERS (4)."""
        from src.evaluation.harness import DEFAULT_MAX_WORKERS

        mock_run.return_value = []
        mock_db = MagicMock()
        mock_db_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_cls.return_value.__exit__ = MagicMock(return_value=False)

        configs = [
            ModelConfig(
                name=f"Model-{i}",
                provider="openrouter",
                model_id=f"model-{i}",
                temperature=0.0,
                max_tokens=2048,
                token_limit=8192,
            )
            for i in range(6)
        ]
        settings = EvaluationSettings(
            runs_per_model={"openrouter": 1},
            timeout_seconds=120,
            output_directory="results",
        )
        scenario = _make_query_scenario()
        harness = QueryEvaluationHarness(configs, settings, [scenario], ":memory:")

        with patch("src.evaluation.query_harness.ThreadPoolExecutor") as mock_executor_cls:
            mock_executor = MagicMock()
            mock_executor.__enter__ = MagicMock(return_value=mock_executor)
            mock_executor.__exit__ = MagicMock(return_value=False)
            mock_executor.submit.return_value = MagicMock(
                exception=MagicMock(return_value=None),
                result=MagicMock(return_value=[]),
            )
            mock_executor_cls.return_value = mock_executor

            harness.run_all(parallel=True)

            mock_executor_cls.assert_called_once_with(max_workers=DEFAULT_MAX_WORKERS)

    @patch("src.evaluation.query_harness.QueryEvaluationHarness._run_model_with_own_db")
    @patch("src.evaluation.query_harness.Database")
    def test_fewer_models_than_workers(
        self,
        mock_db_cls: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        """With 2 models and max_workers=8, caps at 2."""
        mock_run.return_value = []
        mock_db = MagicMock()
        mock_db_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_cls.return_value.__exit__ = MagicMock(return_value=False)

        configs = [
            ModelConfig(
                name=f"Model-{i}",
                provider="openrouter",
                model_id=f"model-{i}",
                temperature=0.0,
                max_tokens=2048,
                token_limit=8192,
            )
            for i in range(2)
        ]
        settings = EvaluationSettings(
            runs_per_model={"openrouter": 1},
            timeout_seconds=120,
            output_directory="results",
        )
        scenario = _make_query_scenario()
        harness = QueryEvaluationHarness(configs, settings, [scenario], ":memory:")

        with patch("src.evaluation.query_harness.ThreadPoolExecutor") as mock_executor_cls:
            mock_executor = MagicMock()
            mock_executor.__enter__ = MagicMock(return_value=mock_executor)
            mock_executor.__exit__ = MagicMock(return_value=False)
            mock_executor.submit.return_value = MagicMock(
                exception=MagicMock(return_value=None),
                result=MagicMock(return_value=[]),
            )
            mock_executor_cls.return_value = mock_executor

            harness.run_all(parallel=True, max_workers=8)

            mock_executor_cls.assert_called_once_with(max_workers=2)


# --- Dashboard integration ---


class TestDashboardIntegration:
    def test_dashboard_created_when_tty(self, tmp_path: Path) -> None:
        """Dashboard is instantiated when _should_use_dashboard() returns True."""
        scenario = _make_query_scenario()
        factory = _make_adapter_factory(scenario)
        settings = EvaluationSettings(
            runs_per_model={"openrouter": 1},
            timeout_seconds=120,
            output_directory="results",
        )
        config = ModelConfig(
            name="cloud-a",
            provider="openrouter",
            model_id="cloud-a",
            temperature=0.0,
            max_tokens=2048,
            token_limit=8192,
        )

        db_path = tmp_path / "test.db"
        harness = QueryEvaluationHarness([config], settings, [scenario], db_path)

        with (
            patch.object(QueryEvaluationHarness, "_create_adapter", side_effect=factory),
            patch("src.evaluation.query_harness._should_use_dashboard", return_value=True),
            patch("src.evaluation.query_harness.Dashboard") as mock_dash_cls,
        ):
            mock_dash = MagicMock()
            mock_dash.__enter__ = MagicMock(return_value=mock_dash)
            mock_dash.__exit__ = MagicMock(return_value=False)
            mock_dash_cls.return_value = mock_dash

            results = harness.run_all(parallel=True)

        mock_dash_cls.assert_called_once_with(
            model_names=["cloud-a"],
            total_scenarios=1,
            total_models=1,
            effective_workers=1,
            force_terminal=False,
        )
        mock_dash.model_started.assert_called_once()
        mock_dash.scenario_completed.assert_called_once()
        mock_dash.model_completed.assert_called_once()
        assert len(results) == 1

    def test_no_dashboard_when_not_tty(self, tmp_path: Path) -> None:
        """Falls back to prints when _should_use_dashboard() returns False."""
        scenario = _make_query_scenario()
        factory = _make_adapter_factory(scenario)
        settings = EvaluationSettings(
            runs_per_model={"openrouter": 1},
            timeout_seconds=120,
            output_directory="results",
        )
        config = ModelConfig(
            name="cloud-a",
            provider="openrouter",
            model_id="cloud-a",
            temperature=0.0,
            max_tokens=2048,
            token_limit=8192,
        )

        db_path = tmp_path / "test.db"
        harness = QueryEvaluationHarness([config], settings, [scenario], db_path)

        with (
            patch.object(QueryEvaluationHarness, "_create_adapter", side_effect=factory),
            patch("src.evaluation.query_harness._should_use_dashboard", return_value=False),
            patch("src.evaluation.query_harness.Dashboard") as mock_dash_cls,
        ):
            results = harness.run_all(parallel=True)

        mock_dash_cls.assert_not_called()
        assert len(results) == 1
