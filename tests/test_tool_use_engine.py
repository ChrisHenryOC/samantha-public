"""Tests for the tool-use prediction engine (Phase 7c).

Tests cover the multi-turn conversation loop in predict_query_with_tools():
tool call → execute → respond → final answer, max turns exceeded, error
mid-loop, token accumulation, and parse errors on final answer.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from src.models.base import (
    ChatMessage,
    ChatResponse,
    ChatRole,
    ModelAdapter,
    ModelResponse,
    ToolCall,
)
from src.prediction.engine import (
    PredictionEngine,
    ToolCallRecord,
    ToolUseQueryResult,
)
from src.prediction.tool_use_prompt import render_tool_use_messages
from src.simulator.schema import DatabaseStateSnapshot, QueryExpectedOutput, QueryScenario
from src.tools.definitions import get_all_tool_definitions
from src.tools.executor import ToolExecutor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_TOOL_DEFS = get_all_tool_definitions()


def _make_scenario(
    *,
    query: str = "Which orders are in ACCEPTED state?",
    answer_type: str = "order_list",
) -> QueryScenario:
    return QueryScenario(
        scenario_id="QR-999",
        category="query",
        tier=1,
        description="Test scenario",
        database_state=DatabaseStateSnapshot(
            orders=(
                {
                    "order_id": "ORD-101",
                    "current_state": "ACCEPTED",
                    "specimen_type": "breast_biopsy",
                    "anatomic_site": "left_breast",
                    "priority": "routine",
                    "flags": [],
                },
            ),
            slides=(),
        ),
        query=query,
        expected_output=QueryExpectedOutput(
            answer_type=answer_type,
            reasoning="Test",
            order_ids=("ORD-101",),
        ),
    )


def _make_executor(scenario: QueryScenario) -> ToolExecutor:
    return ToolExecutor(scenario.database_state)


def _text_response(
    content: str,
    *,
    latency_ms: float = 100.0,
    input_tokens: int = 50,
    output_tokens: int = 30,
) -> ChatResponse:
    """Build a ChatResponse with text content (final answer)."""
    return ChatResponse(
        message=ChatMessage(role=ChatRole.ASSISTANT, content=content),
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_estimate_usd=None,
        model_id="test-model",
    )


def _tool_call_response(
    tool_calls: list[tuple[str, str, dict[str, Any]]],
    *,
    latency_ms: float = 50.0,
    input_tokens: int = 40,
    output_tokens: int = 20,
) -> ChatResponse:
    """Build a ChatResponse with tool calls.

    Each item in tool_calls is (id, function_name, arguments).
    """
    tcs = tuple(
        ToolCall(id=tc_id, function_name=fn, arguments=args) for tc_id, fn, args in tool_calls
    )
    return ChatResponse(
        message=ChatMessage(role=ChatRole.ASSISTANT, content=None, tool_calls=tcs),
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_estimate_usd=None,
        model_id="test-model",
    )


def _error_response(
    error: str,
    *,
    latency_ms: float = 10.0,
) -> ChatResponse:
    """Build an error ChatResponse."""
    return ChatResponse(
        message=ChatMessage(role=ChatRole.ASSISTANT, content=None),
        latency_ms=latency_ms,
        input_tokens=0,
        output_tokens=0,
        cost_estimate_usd=None,
        model_id="test-model",
        error=error,
    )


class MockChatAdapter(ModelAdapter):
    """Mock adapter that returns predetermined chat responses."""

    def __init__(self, responses: list[ChatResponse]) -> None:
        self._responses = list(responses)
        self._call_count = 0

    def predict(self, prompt: str) -> ModelResponse:
        raise NotImplementedError("MockChatAdapter only supports chat()")

    def chat(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResponse:
        if self._call_count >= len(self._responses):
            raise RuntimeError("MockChatAdapter: no more responses")
        resp = self._responses[self._call_count]
        self._call_count += 1
        return resp

    @property
    def model_id(self) -> str:
        return "test-model"

    @property
    def provider(self) -> str:
        return "mock"


# ===========================================================================
# Tool-use prompt tests
# ===========================================================================


class TestRenderToolUseMessages:
    def test_returns_system_and_user_messages(self) -> None:
        system_msg, user_msg = render_tool_use_messages("Which orders are accepted?", "order_list")
        assert system_msg.role == ChatRole.SYSTEM
        assert user_msg.role == ChatRole.USER
        assert "laboratory information system" in (system_msg.content or "")
        assert "Which orders are accepted?" in (user_msg.content or "")

    def test_includes_output_format(self) -> None:
        _, user_msg = render_tool_use_messages("test", "order_list")
        assert "order_ids" in (user_msg.content or "")

    def test_excludes_database_state(self) -> None:
        system_msg, user_msg = render_tool_use_messages("test", "order_list")
        all_content = (system_msg.content or "") + (user_msg.content or "")
        assert "Current Database State" not in all_content
        assert "Orders\n\n[" not in all_content

    def test_invalid_answer_type_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown answer_type"):
            render_tool_use_messages("test", "invalid_type")

    def test_empty_query_raises(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            render_tool_use_messages("", "order_list")

    def test_prioritized_list_includes_ranking_rules(self) -> None:
        _, user_msg = render_tool_use_messages("test", "prioritized_list")
        assert "Ranking rules" in (user_msg.content or "")


# ===========================================================================
# ToolCallRecord validation tests
# ===========================================================================


class TestToolCallRecord:
    def test_valid_record(self) -> None:
        rec = ToolCallRecord(
            tool_name="get_order",
            arguments={"order_id": "ORD-101"},
            result='{"order_id": "ORD-101"}',
            turn=1,
        )
        assert rec.tool_name == "get_order"
        assert rec.turn == 1

    def test_empty_tool_name_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty string"):
            ToolCallRecord(tool_name="", arguments={}, result="{}", turn=1)

    def test_zero_turn_raises(self) -> None:
        with pytest.raises(ValueError, match=">= 1"):
            ToolCallRecord(tool_name="get_order", arguments={}, result="{}", turn=0)


# ===========================================================================
# ToolUseQueryResult validation tests
# ===========================================================================


class TestToolUseQueryResult:
    def test_valid_success_result(self) -> None:
        result = ToolUseQueryResult(
            parsed_output={"order_ids": ["ORD-101"], "reasoning": "test"},
            error=None,
            tool_calls=(),
            turns=1,
            total_latency_ms=100.0,
            total_input_tokens=50,
            total_output_tokens=30,
            model_id="test-model",
        )
        assert result.parsed_output is not None
        assert result.error is None

    def test_valid_error_result(self) -> None:
        result = ToolUseQueryResult(
            parsed_output=None,
            error="some_error",
            tool_calls=(),
            turns=1,
            total_latency_ms=0,
            total_input_tokens=0,
            total_output_tokens=0,
            model_id="test-model",
        )
        assert result.error == "some_error"

    def test_empty_model_id_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty string"):
            ToolUseQueryResult(
                parsed_output=None,
                error=None,
                tool_calls=(),
                turns=0,
                total_latency_ms=0,
                total_input_tokens=0,
                total_output_tokens=0,
                model_id="",
            )


# ===========================================================================
# predict_query_with_tools() tests
# ===========================================================================


class TestPredictQueryWithToolsSingleTurn:
    """Model answers immediately without tool calls."""

    def test_direct_text_answer(self) -> None:
        answer = json.dumps({"order_ids": ["ORD-101"], "reasoning": "In ACCEPTED state"})
        adapter = MockChatAdapter([_text_response(answer)])
        engine = PredictionEngine(adapter)
        scenario = _make_scenario()
        executor = _make_executor(scenario)

        result = engine.predict_query_with_tools(scenario, executor, _SAMPLE_TOOL_DEFS)

        assert result.error is None
        assert result.parsed_output is not None
        assert result.parsed_output["order_ids"] == ["ORD-101"]
        assert result.turns == 1
        assert result.tool_calls == ()
        assert result.total_latency_ms == 100.0
        assert result.total_input_tokens == 50
        assert result.total_output_tokens == 30


class TestPredictQueryWithToolsMultiTurn:
    """Model calls tools then provides final answer."""

    def test_tool_call_then_answer(self) -> None:
        """Two turns: tool call → final answer."""
        tool_resp = _tool_call_response(
            [("call_0", "list_orders", {})],
            latency_ms=50.0,
            input_tokens=40,
            output_tokens=20,
        )
        answer = json.dumps({"order_ids": ["ORD-101"], "reasoning": "Found in list"})
        text_resp = _text_response(
            answer,
            latency_ms=80.0,
            input_tokens=60,
            output_tokens=25,
        )
        adapter = MockChatAdapter([tool_resp, text_resp])
        engine = PredictionEngine(adapter)
        scenario = _make_scenario()
        executor = _make_executor(scenario)

        result = engine.predict_query_with_tools(scenario, executor, _SAMPLE_TOOL_DEFS)

        assert result.error is None
        assert result.parsed_output is not None
        assert result.turns == 2
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].tool_name == "list_orders"
        assert result.tool_calls[0].turn == 1
        # Verify tool result is valid JSON from executor
        tool_result = json.loads(result.tool_calls[0].result)
        assert isinstance(tool_result, list)
        # Token accumulation
        assert result.total_latency_ms == pytest.approx(130.0)
        assert result.total_input_tokens == 100
        assert result.total_output_tokens == 45

    def test_multiple_tool_calls_in_one_turn(self) -> None:
        """Model requests two tools in a single turn."""
        tool_resp = _tool_call_response(
            [
                ("call_0", "list_orders", {}),
                ("call_1", "get_order", {"order_id": "ORD-101"}),
            ],
        )
        answer = json.dumps({"order_ids": ["ORD-101"], "reasoning": "test"})
        text_resp = _text_response(answer)
        adapter = MockChatAdapter([tool_resp, text_resp])
        engine = PredictionEngine(adapter)
        scenario = _make_scenario()
        executor = _make_executor(scenario)

        result = engine.predict_query_with_tools(scenario, executor, _SAMPLE_TOOL_DEFS)

        assert result.error is None
        assert len(result.tool_calls) == 2
        assert result.tool_calls[0].tool_name == "list_orders"
        assert result.tool_calls[1].tool_name == "get_order"
        assert result.tool_calls[0].turn == 1
        assert result.tool_calls[1].turn == 1


class TestPredictQueryWithToolsErrors:
    """Error handling in the tool-use loop."""

    def test_adapter_error_returns_error_result(self) -> None:
        error_resp = _error_response("connection_error: unreachable")
        adapter = MockChatAdapter([error_resp])
        engine = PredictionEngine(adapter)
        scenario = _make_scenario()
        executor = _make_executor(scenario)

        result = engine.predict_query_with_tools(scenario, executor, _SAMPLE_TOOL_DEFS)

        assert result.error is not None
        assert "model_error" in result.error
        assert "connection_error" in result.error
        assert result.parsed_output is None
        assert result.turns == 1

    def test_error_after_tool_call(self) -> None:
        """Error on second turn after successful tool call."""
        tool_resp = _tool_call_response([("call_0", "list_orders", {})])
        error_resp = _error_response("timeout: 30s")
        adapter = MockChatAdapter([tool_resp, error_resp])
        engine = PredictionEngine(adapter)
        scenario = _make_scenario()
        executor = _make_executor(scenario)

        result = engine.predict_query_with_tools(scenario, executor, _SAMPLE_TOOL_DEFS)

        assert result.error is not None
        assert "timeout" in result.error
        assert result.turns == 2
        assert len(result.tool_calls) == 1  # First turn's tool call is recorded

    def test_parse_error_on_final_answer(self) -> None:
        """Model returns non-JSON text as final answer."""
        adapter = MockChatAdapter([_text_response("I don't know the answer")])
        engine = PredictionEngine(adapter)
        scenario = _make_scenario()
        executor = _make_executor(scenario)

        result = engine.predict_query_with_tools(scenario, executor, _SAMPLE_TOOL_DEFS)

        assert result.error is not None
        assert "malformed_json" in result.error
        assert result.parsed_output is None
        assert result.turns == 1

    def test_wrong_schema_on_final_answer(self) -> None:
        """Model returns JSON missing required keys."""
        adapter = MockChatAdapter([_text_response('{"wrong_key": true}')])
        engine = PredictionEngine(adapter)
        scenario = _make_scenario()
        executor = _make_executor(scenario)

        result = engine.predict_query_with_tools(scenario, executor, _SAMPLE_TOOL_DEFS)

        assert result.error is not None
        assert "wrong_schema" in result.error

    def test_adapter_exception_caught(self) -> None:
        """Unexpected exception from adapter.chat() is caught."""
        adapter = MockChatAdapter([])  # No responses — will raise RuntimeError
        engine = PredictionEngine(adapter)
        scenario = _make_scenario()
        executor = _make_executor(scenario)

        result = engine.predict_query_with_tools(scenario, executor, _SAMPLE_TOOL_DEFS)

        assert result.error is not None
        assert "adapter_error" in result.error


class TestPredictQueryWithToolsMaxTurns:
    """Max turn limit prevents infinite loops."""

    def test_max_turns_exceeded(self) -> None:
        """Model keeps calling tools beyond the turn limit."""
        max_turns = PredictionEngine._MAX_QUERY_TOOL_TURNS
        responses = [
            _tool_call_response(
                [(f"call_{i}", "list_orders", {})],
                latency_ms=10.0,
                input_tokens=5,
                output_tokens=3,
            )
            for i in range(max_turns)
        ]
        adapter = MockChatAdapter(responses)
        engine = PredictionEngine(adapter)
        scenario = _make_scenario()
        executor = _make_executor(scenario)

        result = engine.predict_query_with_tools(scenario, executor, _SAMPLE_TOOL_DEFS)

        assert result.error is not None
        assert "max_turns_exceeded" in result.error
        assert result.turns == max_turns
        assert len(result.tool_calls) == max_turns
        # Token accumulation across all turns
        assert result.total_latency_ms == pytest.approx(max_turns * 10.0)
        assert result.total_input_tokens == max_turns * 5
        assert result.total_output_tokens == max_turns * 3


class TestPredictQueryWithToolsTokenAccumulation:
    """Tokens and latency are correctly accumulated."""

    def test_three_turn_accumulation(self) -> None:
        """Verify token/latency sums across 3 turns."""
        responses = [
            _tool_call_response(
                [("call_0", "list_orders", {})],
                latency_ms=100.0,
                input_tokens=50,
                output_tokens=20,
            ),
            _tool_call_response(
                [("call_1", "get_order", {"order_id": "ORD-101"})],
                latency_ms=80.0,
                input_tokens=60,
                output_tokens=25,
            ),
            _text_response(
                json.dumps({"order_ids": ["ORD-101"], "reasoning": "test"}),
                latency_ms=120.0,
                input_tokens=70,
                output_tokens=35,
            ),
        ]
        adapter = MockChatAdapter(responses)
        engine = PredictionEngine(adapter)
        scenario = _make_scenario()
        executor = _make_executor(scenario)

        result = engine.predict_query_with_tools(scenario, executor, _SAMPLE_TOOL_DEFS)

        assert result.error is None
        assert result.turns == 3
        assert result.total_latency_ms == pytest.approx(300.0)
        assert result.total_input_tokens == 180
        assert result.total_output_tokens == 80
        assert len(result.tool_calls) == 2


class TestPredictQueryWithToolsExecutorIntegration:
    """Verify tool results are actually from ToolExecutor."""

    def test_executor_results_fed_back(self) -> None:
        """Tool call results come from the real executor."""
        tool_resp = _tool_call_response(
            [("call_0", "get_order", {"order_id": "ORD-101"})],
        )
        answer = json.dumps({"order_ids": ["ORD-101"], "reasoning": "found"})
        text_resp = _text_response(answer)
        adapter = MockChatAdapter([tool_resp, text_resp])
        engine = PredictionEngine(adapter)
        scenario = _make_scenario()
        executor = _make_executor(scenario)

        result = engine.predict_query_with_tools(scenario, executor, _SAMPLE_TOOL_DEFS)

        assert result.error is None
        # Verify the tool result contains actual order data
        tool_result = json.loads(result.tool_calls[0].result)
        assert tool_result["order_id"] == "ORD-101"
        assert tool_result["current_state"] == "ACCEPTED"

    def test_unknown_tool_returns_error_in_result(self) -> None:
        """Unknown tool name returns an error JSON, not a crash."""
        tool_resp = _tool_call_response(
            [("call_0", "nonexistent_tool", {})],
        )
        answer = json.dumps({"order_ids": ["ORD-101"], "reasoning": "test"})
        text_resp = _text_response(answer)
        adapter = MockChatAdapter([tool_resp, text_resp])
        engine = PredictionEngine(adapter)
        scenario = _make_scenario()
        executor = _make_executor(scenario)

        result = engine.predict_query_with_tools(scenario, executor, _SAMPLE_TOOL_DEFS)

        assert result.error is None  # Loop continues despite tool error
        tool_result = json.loads(result.tool_calls[0].result)
        assert "error" in tool_result
        assert "Unknown tool" in tool_result["error"]


# ===========================================================================
# Additional tests from code review (#6-8, #12-15)
# ===========================================================================


class TestEmptyResponsePath:
    """#6: empty_response when model returns neither content nor tool_calls."""

    def test_empty_response_returns_error(self) -> None:
        empty_resp = ChatResponse(
            message=ChatMessage(role=ChatRole.ASSISTANT, content=None),
            latency_ms=50.0,
            input_tokens=10,
            output_tokens=0,
            cost_estimate_usd=None,
            model_id="test-model",
        )
        adapter = MockChatAdapter([empty_resp])
        engine = PredictionEngine(adapter)
        scenario = _make_scenario()
        executor = _make_executor(scenario)

        result = engine.predict_query_with_tools(scenario, executor, _SAMPLE_TOOL_DEFS)

        assert result.error is not None
        assert "empty_response" in result.error
        assert result.turns == 1


class TestAnswerTypePromptCoverage:
    """#7: order_status and explanation answer types in render_tool_use_messages."""

    def test_order_status_includes_status_summary(self) -> None:
        _, user_msg = render_tool_use_messages("What is ORD-101?", "order_status")
        assert "status_summary" in (user_msg.content or "")

    def test_explanation_includes_explanation_key(self) -> None:
        _, user_msg = render_tool_use_messages("Why is ORD-101 held?", "explanation")
        assert "explanation" in (user_msg.content or "")


class TestMessageHistoryGrowth:
    """#8: Verify message history passed to adapter.chat() grows correctly."""

    def test_second_call_receives_correct_message_history(self) -> None:
        tool_resp = _tool_call_response(
            [("call_0", "list_orders", {})],
        )
        answer = json.dumps({"order_ids": ["ORD-101"], "reasoning": "test"})
        text_resp = _text_response(answer)

        # Track messages passed to chat()
        recorded_messages: list[list[ChatMessage]] = []
        original_responses = [tool_resp, text_resp]

        class TrackingAdapter(MockChatAdapter):
            def chat(
                self,
                messages: list[ChatMessage],
                tools: list[dict[str, Any]] | None = None,
            ) -> ChatResponse:
                recorded_messages.append(list(messages))
                return super().chat(messages, tools)

        adapter = TrackingAdapter(original_responses)
        engine = PredictionEngine(adapter)
        scenario = _make_scenario()
        executor = _make_executor(scenario)

        result = engine.predict_query_with_tools(scenario, executor, _SAMPLE_TOOL_DEFS)

        assert result.error is None
        # First call: system + user = 2 messages
        assert len(recorded_messages[0]) == 2
        assert recorded_messages[0][0].role == ChatRole.SYSTEM
        assert recorded_messages[0][1].role == ChatRole.USER
        # Second call: system + user + assistant(tool_calls) + tool_result = 4
        assert len(recorded_messages[1]) == 4
        assert recorded_messages[1][2].role == ChatRole.ASSISTANT
        assert recorded_messages[1][2].tool_calls[0].function_name == "list_orders"
        assert recorded_messages[1][3].role == ChatRole.TOOL
        assert recorded_messages[1][3].tool_call_id == "call_0"


class TestPromptErrorPath:
    """#12: prompt_error early-return path in predict_query_with_tools."""

    def test_prompt_error_returns_error_result(self) -> None:
        adapter = MockChatAdapter([])
        engine = PredictionEngine(adapter)
        scenario = _make_scenario()
        executor = _make_executor(scenario)

        # Patch the scenario's answer_type to trigger prompt rendering error
        # by corrupting the frozen field
        object.__setattr__(scenario.expected_output, "answer_type", "invalid_type")

        result = engine.predict_query_with_tools(scenario, executor, _SAMPLE_TOOL_DEFS)

        assert result.error is not None
        assert "prompt_error" in result.error
        assert result.turns == 0
        assert result.tool_calls == ()


class TestValidationNegatives:
    """#13: Additional negative tests for dataclass validation."""

    def test_tool_use_result_negative_turns_raises(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            ToolUseQueryResult(
                parsed_output=None,
                error="test",
                tool_calls=(),
                turns=-1,
                total_latency_ms=0,
                total_input_tokens=0,
                total_output_tokens=0,
                model_id="test",
            )

    def test_tool_use_result_bool_latency_raises(self) -> None:
        with pytest.raises(TypeError, match="total_latency_ms"):
            ToolUseQueryResult(
                parsed_output=None,
                error="test",
                tool_calls=(),
                turns=0,
                total_latency_ms=True,  # type: ignore[arg-type]
                total_input_tokens=0,
                total_output_tokens=0,
                model_id="test",
            )

    def test_tool_use_result_list_tool_calls_raises(self) -> None:
        with pytest.raises(TypeError, match="tool_calls must be tuple"):
            ToolUseQueryResult(
                parsed_output=None,
                error="test",
                tool_calls=[],  # type: ignore[arg-type]
                turns=0,
                total_latency_ms=0,
                total_input_tokens=0,
                total_output_tokens=0,
                model_id="test",
            )

    def test_tool_use_result_invalid_element_raises(self) -> None:
        with pytest.raises(TypeError, match="tool_calls\\[0\\] must be ToolCallRecord"):
            ToolUseQueryResult(
                parsed_output=None,
                error="test",
                tool_calls=("not_a_record",),  # type: ignore[arg-type]
                turns=0,
                total_latency_ms=0,
                total_input_tokens=0,
                total_output_tokens=0,
                model_id="test",
            )

    def test_tool_use_result_mutual_exclusivity_raises(self) -> None:
        with pytest.raises(ValueError, match="mutually exclusive"):
            ToolUseQueryResult(
                parsed_output={"order_ids": ["ORD-101"]},
                error="some_error",
                tool_calls=(),
                turns=1,
                total_latency_ms=0,
                total_input_tokens=0,
                total_output_tokens=0,
                model_id="test",
            )

    def test_tool_use_result_negative_latency_raises(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            ToolUseQueryResult(
                parsed_output=None,
                error="test",
                tool_calls=(),
                turns=0,
                total_latency_ms=-1.0,
                total_input_tokens=0,
                total_output_tokens=0,
                model_id="test",
            )

    def test_tool_call_record_non_dict_arguments_raises(self) -> None:
        with pytest.raises(TypeError, match="must be dict"):
            ToolCallRecord(
                tool_name="get_order",
                arguments="bad",  # type: ignore[arg-type]
                result="{}",
                turn=1,
            )

    def test_tool_call_record_empty_result_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty string"):
            ToolCallRecord(
                tool_name="get_order",
                arguments={},
                result="",
                turn=1,
            )


class TestRenderToolUseMessagesGuards:
    """#14: TypeError and whitespace-only query guards."""

    def test_non_str_query_raises_type_error(self) -> None:
        with pytest.raises(TypeError, match="must be str"):
            render_tool_use_messages(123, "order_list")  # type: ignore[arg-type]

    def test_whitespace_only_query_raises(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            render_tool_use_messages("   ", "order_list")


class TestAdapterExceptionMidLoop:
    """#15: adapter.chat() raises exception on turn > 1."""

    def test_exception_on_second_turn(self) -> None:
        tool_resp = _tool_call_response(
            [("call_0", "list_orders", {})],
        )

        class FailOnSecondCall(MockChatAdapter):
            def chat(
                self,
                messages: list[ChatMessage],
                tools: list[dict[str, Any]] | None = None,
            ) -> ChatResponse:
                if self._call_count >= 1:
                    self._call_count += 1
                    raise RuntimeError("Network failure on second call")
                return super().chat(messages, tools)

        adapter = FailOnSecondCall([tool_resp])
        engine = PredictionEngine(adapter)
        scenario = _make_scenario()
        executor = _make_executor(scenario)

        result = engine.predict_query_with_tools(scenario, executor, _SAMPLE_TOOL_DEFS)

        assert result.error is not None
        assert "adapter_error" in result.error
        assert "RuntimeError" in result.error
        assert result.turns == 2
        assert len(result.tool_calls) == 1  # First turn's tool call recorded
