"""Tests for the tool-use query evaluation harness (Phase 7d).

E2E tests with MockChatAdapter: scenario execution, validation,
decision persistence, early-abort, and callback delivery.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

from src.evaluation.query_metrics import QueryResult
from src.evaluation.tool_use_harness import ToolUseQueryHarness
from src.models.base import (
    ChatMessage,
    ChatResponse,
    ChatRole,
    ModelAdapter,
    ModelResponse,
    ToolCall,
)
from src.models.config import EvaluationSettings, ModelConfig
from src.simulator.schema import (
    DatabaseStateSnapshot,
    QueryExpectedOutput,
    QueryScenario,
)
from src.workflow.database import Database

# --- Mock adapter that supports chat() ---


class MockToolUseAdapter(ModelAdapter):
    """Adapter that returns preconfigured chat responses for tool-use eval."""

    def __init__(
        self,
        chat_responses: list[ChatResponse] | None = None,
        *,
        model_id: str = "mock-tool-model",
    ) -> None:
        self._chat_responses = list(chat_responses or [])
        self._call_count = 0
        self._model_id = model_id

    def predict(self, prompt: str) -> ModelResponse:
        raise NotImplementedError("MockToolUseAdapter only supports chat()")

    def chat(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResponse:
        if self._call_count < len(self._chat_responses):
            resp = self._chat_responses[self._call_count]
        else:
            resp = self._chat_responses[-1] if self._chat_responses else None
            if resp is None:
                raise RuntimeError("No responses configured")
        self._call_count += 1
        return resp

    def close(self) -> None:
        pass

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def provider(self) -> str:
        return "mock"


# --- Fixtures ---


def _make_db_state() -> DatabaseStateSnapshot:
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
        ),
        slides=(),
    )


def _make_scenario(
    scenario_id: str = "QR-001",
    tier: int = 1,
    answer_type: str = "order_list",
    expected_order_ids: tuple[str, ...] = ("ORD-101",),
) -> QueryScenario:
    return QueryScenario(
        scenario_id=scenario_id,
        category="query",
        tier=tier,
        description=f"Test scenario {scenario_id}",
        database_state=_make_db_state(),
        query="Which orders are in ACCEPTED state?",
        expected_output=QueryExpectedOutput(
            answer_type=answer_type,
            reasoning="Test reasoning",
            order_ids=expected_order_ids,
        ),
    )


def _make_config(
    model_id: str = "mock-tool-model",
    name: str = "Mock Tool Model",
) -> ModelConfig:
    return ModelConfig(
        name=name,
        provider="llamacpp",
        model_id=model_id,
        temperature=0.0,
        max_tokens=1024,
        token_limit=131072,
    )


def _make_settings() -> EvaluationSettings:
    return EvaluationSettings(
        runs_per_model={"llamacpp": 1, "openrouter": 1},
        timeout_seconds=30,
        output_directory="results/test",
    )


def _text_chat_response(
    content: str,
    *,
    model_id: str = "mock-tool-model",
) -> ChatResponse:
    return ChatResponse(
        message=ChatMessage(role=ChatRole.ASSISTANT, content=content),
        latency_ms=100.0,
        input_tokens=50,
        output_tokens=30,
        cost_estimate_usd=None,
        model_id=model_id,
    )


def _tool_call_chat_response(
    tool_calls: list[tuple[str, str, dict[str, Any]]],
    *,
    model_id: str = "mock-tool-model",
) -> ChatResponse:
    tcs = tuple(
        ToolCall(id=tc_id, function_name=fn, arguments=args) for tc_id, fn, args in tool_calls
    )
    return ChatResponse(
        message=ChatMessage(role=ChatRole.ASSISTANT, content=None, tool_calls=tcs),
        latency_ms=50.0,
        input_tokens=40,
        output_tokens=20,
        cost_estimate_usd=None,
        model_id=model_id,
    )


# ===========================================================================
# Harness E2E tests
# ===========================================================================


class TestToolUseHarnessCorrectAnswer:
    """Scenario with correct answer validates properly."""

    def test_single_scenario_correct(self) -> None:
        answer = json.dumps({"order_ids": ["ORD-101"], "reasoning": "In ACCEPTED state"})
        adapter_responses = [
            _tool_call_chat_response([("call_0", "list_orders", {})]),
            _text_chat_response(answer),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Patch adapter creation to use our mock
            harness = ToolUseQueryHarness(
                [_make_config()],
                _make_settings(),
                [_make_scenario()],
                db_path,
            )

            with (
                pytest.MonkeyPatch.context() as mp,
            ):
                mp.setattr(
                    harness,
                    "_create_adapter",
                    lambda config: MockToolUseAdapter(adapter_responses),
                )
                results = harness.run_all()

            assert len(results) == 1
            result = results[0]
            assert result.all_correct
            assert result.failure_type is None
            assert result.scenario_id == "QR-001"

            # Verify database persistence
            with Database(db_path) as db:
                rows = db._conn.execute(
                    "SELECT * FROM query_decisions WHERE scenario_id = 'QR-001'"
                ).fetchall()
                assert len(rows) == 1


class TestToolUseHarnessError:
    """Model error is recorded correctly."""

    def test_error_response_recorded(self) -> None:
        error_resp = ChatResponse(
            message=ChatMessage(role=ChatRole.ASSISTANT, content=None),
            latency_ms=10.0,
            input_tokens=0,
            output_tokens=0,
            cost_estimate_usd=None,
            model_id="mock-tool-model",
            error="connection_error: unreachable",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            harness = ToolUseQueryHarness(
                [_make_config()],
                _make_settings(),
                [_make_scenario()],
                db_path,
            )
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(
                    harness,
                    "_create_adapter",
                    lambda config: MockToolUseAdapter([error_resp]),
                )
                results = harness.run_all()

            assert len(results) == 1
            assert not results[0].all_correct
            assert results[0].failure_type is not None


class TestToolUseHarnessToolCallAuditTrail:
    """Tool call metadata is persisted in model_output."""

    def test_tool_calls_in_model_output(self) -> None:
        adapter_responses = [
            _tool_call_chat_response([("call_0", "get_order", {"order_id": "ORD-101"})]),
            _text_chat_response(json.dumps({"order_ids": ["ORD-101"], "reasoning": "found"})),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            harness = ToolUseQueryHarness(
                [_make_config()],
                _make_settings(),
                [_make_scenario()],
                db_path,
            )
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(
                    harness,
                    "_create_adapter",
                    lambda config: MockToolUseAdapter(adapter_responses),
                )
                results = harness.run_all()

            assert len(results) == 1

            # Check model_output has tool_calls and turns
            with Database(db_path) as db:
                row = db._conn.execute(
                    "SELECT model_output FROM query_decisions WHERE scenario_id = 'QR-001'"
                ).fetchone()
                model_output = json.loads(row[0])
                assert "tool_calls" in model_output
                assert len(model_output["tool_calls"]) == 1
                assert model_output["tool_calls"][0]["tool_name"] == "get_order"
                assert "turns" in model_output
                assert model_output["turns"] == 2


class TestToolUseHarnessCallback:
    """Callback is called after each run."""

    def test_callback_receives_results(self) -> None:
        answer = json.dumps({"order_ids": ["ORD-101"], "reasoning": "test"})
        adapter_responses = [_text_chat_response(answer)]

        callback_calls: list[tuple[str, int, int, bool]] = []

        def on_complete(
            model_id: str,
            run_number: int,
            run_results: list[QueryResult],
            aborted: bool,
        ) -> None:
            callback_calls.append((model_id, run_number, len(run_results), aborted))

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            harness = ToolUseQueryHarness(
                [_make_config()],
                _make_settings(),
                [_make_scenario()],
                db_path,
            )
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(
                    harness,
                    "_create_adapter",
                    lambda config: MockToolUseAdapter(adapter_responses),
                )
                results = harness.run_all(on_run_complete=on_complete)

            # Results delivered via callback, not return
            assert results == []
            assert len(callback_calls) == 1
            assert callback_calls[0] == ("mock-tool-model", 1, 1, False)


class TestToolUseHarnessMultiModel:
    """Two distinct models with no PK collisions."""

    def test_two_models_no_pk_collisions(self) -> None:
        answer = json.dumps({"order_ids": ["ORD-101"], "reasoning": "test"})

        config_a = _make_config(model_id="model-a", name="Model A")
        config_b = _make_config(model_id="model-b", name="Model B")

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            harness = ToolUseQueryHarness(
                [config_a, config_b],
                _make_settings(),
                [_make_scenario()],
                db_path,
            )
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(
                    harness,
                    "_create_adapter",
                    lambda config: MockToolUseAdapter(
                        [_text_chat_response(answer, model_id=config.model_id)],
                        model_id=config.model_id,
                    ),
                )
                results = harness.run_all()

            assert len(results) == 2
            model_ids = {r.model_id for r in results}
            assert model_ids == {"model-a", "model-b"}

            with Database(db_path) as db:
                count = db._conn.execute("SELECT COUNT(*) FROM query_decisions").fetchone()[0]
                assert count == 2


# ===========================================================================
# Additional tests from code review (#5, #6, #8)
# ===========================================================================


class TestToolUseHarnessEarlyAbort:
    """#5: Early-abort logic stops run after fatal error threshold."""

    def test_early_abort_on_repeated_errors(self) -> None:
        """Model always returns errors — abort triggers after threshold."""
        error_resp = ChatResponse(
            message=ChatMessage(role=ChatRole.ASSISTANT, content=None),
            latency_ms=10.0,
            input_tokens=0,
            output_tokens=0,
            cost_estimate_usd=None,
            model_id="mock-tool-model",
            error="connection_error: unreachable",
        )
        # Create 20 scenarios to exceed _EARLY_ABORT_MIN_SCENARIOS (15)
        scenarios = [_make_scenario(scenario_id=f"QR-{i:03d}") for i in range(1, 21)]

        callback_calls: list[tuple[str, int, int, bool]] = []

        def on_complete(
            model_id: str,
            run_number: int,
            run_results: list[QueryResult],
            aborted: bool,
        ) -> None:
            callback_calls.append((model_id, run_number, len(run_results), aborted))

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            harness = ToolUseQueryHarness(
                [_make_config()],
                _make_settings(),
                scenarios,
                db_path,
            )
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(
                    harness,
                    "_create_adapter",
                    lambda config: MockToolUseAdapter([error_resp]),
                )
                harness.run_all(on_run_complete=on_complete)

            # Callback should indicate abort
            assert len(callback_calls) == 1
            assert callback_calls[0][3] is True  # aborted=True
            # Should have fewer results than total scenarios (aborted early)
            assert callback_calls[0][2] < 20

            # Run should be marked aborted in DB
            with Database(db_path) as db:
                row = db._conn.execute("SELECT aborted FROM runs LIMIT 1").fetchone()
                assert row[0] == 1  # aborted=True


class TestToolUseHarnessMultiRun:
    """#6: Multi-run execution with runs > 1."""

    def test_two_runs_produce_distinct_results(self) -> None:
        answer = json.dumps({"order_ids": ["ORD-101"], "reasoning": "test"})
        adapter_responses = [_text_chat_response(answer)]

        settings = EvaluationSettings(
            runs_per_model={"llamacpp": 2, "openrouter": 1},
            timeout_seconds=30,
            output_directory="results/test",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            harness = ToolUseQueryHarness(
                [_make_config()],
                settings,
                [_make_scenario()],
                db_path,
            )
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(
                    harness,
                    "_create_adapter",
                    lambda config: MockToolUseAdapter(adapter_responses),
                )
                results = harness.run_all()

            # 2 runs × 1 scenario = 2 results
            assert len(results) == 2
            assert results[0].run_number == 1
            assert results[1].run_number == 2

            # Distinct run_ids in DB
            with Database(db_path) as db:
                run_ids = [r[0] for r in db._conn.execute("SELECT run_id FROM runs").fetchall()]
                assert len(run_ids) == 2
                assert run_ids[0] != run_ids[1]


class TestToolUseHarnessWrongSchema:
    """#8: Wrong schema in model output is classified correctly."""

    def test_scalar_order_ids_classified_as_wrong_schema(self) -> None:
        """Model returns order_ids as a string — parse_query_output catches this
        as wrong_schema, which flows through the error path as INVALID_JSON."""
        answer = json.dumps({"order_ids": "ORD-101", "reasoning": "test"})
        adapter_responses = [_text_chat_response(answer)]

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            harness = ToolUseQueryHarness(
                [_make_config()],
                _make_settings(),
                [_make_scenario()],
                db_path,
            )
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(
                    harness,
                    "_create_adapter",
                    lambda config: MockToolUseAdapter(adapter_responses),
                )
                results = harness.run_all()

            assert len(results) == 1
            # wrong_schema from parse_query_output flows through the error path
            assert not results[0].all_correct
            assert results[0].failure_type is not None


class TestToolUseHarnessErrorClassification:
    """Verify _classify_tool_use_error correctly maps error types."""

    def test_timeout_classified_correctly(self) -> None:
        error_resp = ChatResponse(
            message=ChatMessage(role=ChatRole.ASSISTANT, content=None),
            latency_ms=30000.0,
            input_tokens=0,
            output_tokens=0,
            cost_estimate_usd=None,
            model_id="mock-tool-model",
            error="timeout: model did not respond within 30s",
            timed_out=True,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            harness = ToolUseQueryHarness(
                [_make_config()],
                _make_settings(),
                [_make_scenario()],
                db_path,
            )
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(
                    harness,
                    "_create_adapter",
                    lambda config: MockToolUseAdapter([error_resp]),
                )
                results = harness.run_all()

            from src.workflow.query_validator import QueryFailureType

            assert results[0].failure_type == QueryFailureType.TIMEOUT

    def test_empty_response_classified_correctly(self) -> None:
        """Empty response errors should be EMPTY_RESPONSE, not INVALID_JSON."""
        empty_resp = ChatResponse(
            message=ChatMessage(role=ChatRole.ASSISTANT, content=None),
            latency_ms=50.0,
            input_tokens=10,
            output_tokens=0,
            cost_estimate_usd=None,
            model_id="mock-tool-model",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            harness = ToolUseQueryHarness(
                [_make_config()],
                _make_settings(),
                [_make_scenario()],
                db_path,
            )
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(
                    harness,
                    "_create_adapter",
                    lambda config: MockToolUseAdapter([empty_resp]),
                )
                results = harness.run_all()

            from src.workflow.query_validator import QueryFailureType

            assert results[0].failure_type == QueryFailureType.EMPTY_RESPONSE
