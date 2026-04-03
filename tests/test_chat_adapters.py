"""Tests for the adapter chat() interface (Phase 7b).

Tests cover ChatMessage/ToolCall/ChatResponse dataclass validation,
LlamaCppAdapter.chat() and OpenRouterAdapter.chat() with mocked HTTP
responses including tool_calls parsing, error handling, and message
format conversion.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from src.models.base import ChatMessage, ChatResponse, ChatRole, ToolCall
from src.models.config import ModelConfig
from src.models.llamacpp_adapter import LlamaCppAdapter
from src.models.openrouter_adapter import OpenRouterAdapter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _llamacpp_config(
    *,
    model_id: str = "llama3.1:8b",
    temperature: float = 0.0,
    max_tokens: int = 1024,
    token_limit: int = 131072,
) -> ModelConfig:
    return ModelConfig(
        name="Test LlamaCpp",
        provider="llamacpp",
        model_id=model_id,
        temperature=temperature,
        max_tokens=max_tokens,
        token_limit=token_limit,
    )


def _openrouter_config(
    *,
    model_id: str = "claude-haiku-4-5-20251001",
    temperature: float = 0.0,
    max_tokens: int = 1024,
) -> ModelConfig:
    return ModelConfig(
        name="Test OpenRouter",
        provider="openrouter",
        model_id=model_id,
        temperature=temperature,
        max_tokens=max_tokens,
        token_limit=200000,
    )


_LLAMACPP_FAKE_REQUEST = httpx.Request("POST", "http://localhost:8080/v1/chat/completions")
_OPENROUTER_FAKE_REQUEST = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")

_SAMPLE_TOOL = {
    "type": "function",
    "function": {
        "name": "get_order",
        "description": "Get order details",
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "Order ID"},
            },
            "required": ["order_id"],
        },
    },
}


def _llamacpp_chat_response(
    *,
    content: str | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
    prompt_tokens: int = 42,
    completion_tokens: int = 18,
) -> dict[str, Any]:
    """Build a realistic llama-server /v1/chat/completions response envelope."""
    message: dict[str, Any] = {"role": "assistant"}
    if content is not None:
        message["content"] = content
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    return {
        "id": "chatcmpl-test",
        "model": "llama-3.1-8b",
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": "tool_calls" if tool_calls else "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def _openai_chat_response(
    *,
    content: str | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
    prompt_tokens: int = 42,
    completion_tokens: int = 18,
) -> dict[str, Any]:
    """Build a realistic OpenAI-compatible chat response with optional tool_calls."""
    message: dict[str, Any] = {"role": "assistant"}
    if content is not None:
        message["content"] = content
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    return {
        "id": "gen-abc123",
        "model": "anthropic/claude-haiku-4-5",
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": "tool_calls" if tool_calls else "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def _mock_response(
    status_code: int = 200,
    *,
    json_data: dict[str, Any] | None = None,
    text: str | None = None,
    request: httpx.Request | None = None,
) -> httpx.Response:
    kwargs: dict[str, Any] = {}
    if json_data is not None:
        kwargs["json"] = json_data
    if text is not None:
        kwargs["text"] = text
    resp = httpx.Response(status_code, **kwargs)
    resp._request = request or _LLAMACPP_FAKE_REQUEST
    return resp


def _sample_messages() -> list[ChatMessage]:
    return [
        ChatMessage(role=ChatRole.SYSTEM, content="You are a lab assistant."),
        ChatMessage(role=ChatRole.USER, content="What is order ORD-101?"),
    ]


# ===========================================================================
# Dataclass validation tests
# ===========================================================================


class TestToolCallValidation:
    def test_valid_tool_call(self) -> None:
        tc = ToolCall(id="call_0", function_name="get_order", arguments={"order_id": "ORD-101"})
        assert tc.id == "call_0"
        assert tc.function_name == "get_order"
        assert tc.arguments == {"order_id": "ORD-101"}

    def test_empty_id_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty string"):
            ToolCall(id="", function_name="get_order", arguments={})

    def test_empty_function_name_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty string"):
            ToolCall(id="call_0", function_name="", arguments={})

    def test_arguments_not_dict_raises(self) -> None:
        with pytest.raises(TypeError, match="must be dict"):
            ToolCall(id="call_0", function_name="get_order", arguments="bad")  # type: ignore[arg-type]


class TestChatMessageValidation:
    def test_valid_user_message(self) -> None:
        msg = ChatMessage(role=ChatRole.USER, content="Hello")
        assert msg.role == ChatRole.USER
        assert msg.content == "Hello"
        assert msg.tool_calls == ()
        assert msg.tool_call_id is None

    def test_valid_assistant_with_tool_calls(self) -> None:
        tc = ToolCall(id="call_0", function_name="get_order", arguments={"order_id": "ORD-101"})
        msg = ChatMessage(role=ChatRole.ASSISTANT, content=None, tool_calls=(tc,))
        assert msg.tool_calls == (tc,)

    def test_valid_tool_response(self) -> None:
        msg = ChatMessage(role=ChatRole.TOOL, content='{"id": "ORD-101"}', tool_call_id="call_0")
        assert msg.role == ChatRole.TOOL
        assert msg.tool_call_id == "call_0"

    def test_invalid_role_raises(self) -> None:
        with pytest.raises(ValueError, match="must be a ChatRole"):
            ChatMessage(role="invalid", content="test")  # type: ignore[arg-type]

    def test_tool_without_tool_call_id_raises(self) -> None:
        with pytest.raises(ValueError, match="must have a non-empty tool_call_id"):
            ChatMessage(role=ChatRole.TOOL, content="result")

    def test_tool_calls_with_content_raises(self) -> None:
        tc = ToolCall(id="call_0", function_name="get_order", arguments={})
        with pytest.raises(ValueError, match="must have content=None"):
            ChatMessage(role=ChatRole.ASSISTANT, content="text", tool_calls=(tc,))

    def test_tool_calls_not_tuple_raises(self) -> None:
        with pytest.raises(TypeError, match="must be a tuple"):
            ChatMessage(role=ChatRole.ASSISTANT, content=None, tool_calls=[])  # type: ignore[arg-type]


class TestChatResponseValidation:
    def test_valid_response(self) -> None:
        msg = ChatMessage(role=ChatRole.ASSISTANT, content="Hello")
        resp = ChatResponse(
            message=msg,
            latency_ms=100.0,
            input_tokens=10,
            output_tokens=5,
            cost_estimate_usd=None,
            model_id="test-model",
        )
        assert resp.error is None
        assert resp.timed_out is False

    def test_valid_error_response(self) -> None:
        msg = ChatMessage(role=ChatRole.ASSISTANT, content=None)
        resp = ChatResponse(
            message=msg,
            latency_ms=50.0,
            input_tokens=0,
            output_tokens=0,
            cost_estimate_usd=None,
            model_id="test-model",
            error="connection_error",
        )
        assert resp.error == "connection_error"
        assert resp.message.content is None

    def test_negative_latency_raises(self) -> None:
        msg = ChatMessage(role=ChatRole.ASSISTANT, content="Hello")
        with pytest.raises(ValueError, match="non-negative"):
            ChatResponse(
                message=msg,
                latency_ms=-1.0,
                input_tokens=0,
                output_tokens=0,
                cost_estimate_usd=None,
                model_id="test-model",
            )

    def test_empty_model_id_raises(self) -> None:
        msg = ChatMessage(role=ChatRole.ASSISTANT, content="Hello")
        with pytest.raises(ValueError, match="non-empty string"):
            ChatResponse(
                message=msg,
                latency_ms=0.0,
                input_tokens=0,
                output_tokens=0,
                cost_estimate_usd=None,
                model_id="",
            )


# ===========================================================================
# LlamaCpp chat() tests
# ===========================================================================


class TestLlamaCppChatSuccess:
    def test_text_response(self) -> None:
        resp = _mock_response(
            json_data=_llamacpp_chat_response(content="The answer is 42."),
        )
        adapter = LlamaCppAdapter(_llamacpp_config())
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.chat(_sample_messages())

        assert isinstance(result, ChatResponse)
        assert result.message.role == ChatRole.ASSISTANT
        assert result.message.content == "The answer is 42."
        assert result.message.tool_calls == ()
        assert result.error is None
        assert result.input_tokens == 42
        assert result.output_tokens == 18
        adapter.close()

    def test_tool_call_response(self) -> None:
        raw_tool_calls = [
            {
                "id": "call_abc123",
                "type": "function",
                "function": {
                    "name": "get_order",
                    "arguments": '{"order_id": "ORD-101"}',
                },
            }
        ]
        resp = _mock_response(
            json_data=_llamacpp_chat_response(tool_calls=raw_tool_calls),
        )
        adapter = LlamaCppAdapter(_llamacpp_config())
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.chat(_sample_messages(), tools=[_SAMPLE_TOOL])

        assert result.error is None
        assert result.message.content is None
        assert len(result.message.tool_calls) == 1
        tc = result.message.tool_calls[0]
        assert tc.function_name == "get_order"
        assert tc.arguments == {"order_id": "ORD-101"}
        assert tc.id == "call_abc123"
        adapter.close()

    def test_multiple_tool_calls(self) -> None:
        raw_tool_calls = [
            {
                "id": "call_0",
                "type": "function",
                "function": {"name": "get_order", "arguments": '{"order_id": "ORD-101"}'},
            },
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "get_slides", "arguments": '{"order_id": "ORD-101"}'},
            },
        ]
        resp = _mock_response(
            json_data=_llamacpp_chat_response(tool_calls=raw_tool_calls),
        )
        adapter = LlamaCppAdapter(_llamacpp_config())
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.chat(_sample_messages(), tools=[_SAMPLE_TOOL])

        assert len(result.message.tool_calls) == 2
        assert result.message.tool_calls[0].id == "call_0"
        assert result.message.tool_calls[1].id == "call_1"
        adapter.close()

    def test_sends_correct_payload(self) -> None:
        resp = _mock_response(
            json_data=_llamacpp_chat_response(content="response"),
        )
        adapter = LlamaCppAdapter(_llamacpp_config(temperature=0.5, max_tokens=512))
        with patch.object(adapter._client, "post", return_value=resp) as mock_post:
            adapter.chat(_sample_messages(), tools=[_SAMPLE_TOOL])

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs.args[0] == "/v1/chat/completions"
        payload = call_kwargs.kwargs["json"]
        assert payload["model"] == "llama3.1:8b"
        assert payload["stream"] is False
        assert payload["temperature"] == 0.5
        assert payload["max_tokens"] == 512
        assert len(payload["messages"]) == 2
        assert payload["messages"][0]["role"] == "system"
        assert payload["tools"] == [_SAMPLE_TOOL]
        adapter.close()

    def test_no_tools_omits_tools_key(self) -> None:
        resp = _mock_response(
            json_data=_llamacpp_chat_response(content="response"),
        )
        adapter = LlamaCppAdapter(_llamacpp_config())
        with patch.object(adapter._client, "post", return_value=resp) as mock_post:
            adapter.chat(_sample_messages())

        payload = mock_post.call_args.kwargs["json"]
        assert "tools" not in payload
        adapter.close()


class TestLlamaCppChatErrors:
    def test_connection_error(self) -> None:
        adapter = LlamaCppAdapter(_llamacpp_config())
        with patch.object(
            adapter._client,
            "post",
            side_effect=httpx.ConnectError("refused"),
        ):
            result = adapter.chat(_sample_messages())

        assert result.error is not None
        assert "connection_error" in result.error
        assert result.input_tokens == 0
        adapter.close()

    def test_timeout(self) -> None:
        adapter = LlamaCppAdapter(_llamacpp_config(), timeout_seconds=30)
        with patch.object(
            adapter._client,
            "post",
            side_effect=httpx.ReadTimeout("timed out"),
        ):
            result = adapter.chat(_sample_messages())

        assert result.error is not None
        assert "timeout" in result.error
        assert "30s" in result.error
        assert result.timed_out is True
        adapter.close()

    def test_http_500(self) -> None:
        err_resp = _mock_response(500, text="Internal Server Error")
        adapter = LlamaCppAdapter(_llamacpp_config())
        with patch.object(
            adapter._client,
            "post",
            side_effect=httpx.HTTPStatusError(
                "500 error",
                request=_LLAMACPP_FAKE_REQUEST,
                response=err_resp,
            ),
        ):
            result = adapter.chat(_sample_messages())

        assert result.error is not None
        assert "http_error" in result.error
        assert "500" in result.error
        adapter.close()

    def test_transport_error(self) -> None:
        adapter = LlamaCppAdapter(_llamacpp_config())
        with patch.object(
            adapter._client,
            "post",
            side_effect=httpx.ReadError("reset"),
        ):
            result = adapter.chat(_sample_messages())

        assert result.error is not None
        assert "transport_error" in result.error
        adapter.close()

    def test_malformed_json_response(self) -> None:
        resp = _mock_response(text="<html>error</html>")
        adapter = LlamaCppAdapter(_llamacpp_config())
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.chat(_sample_messages())

        assert result.error is not None
        assert "malformed_json" in result.error
        adapter.close()

    def test_empty_response(self) -> None:
        resp = _mock_response(json_data=_llamacpp_chat_response())
        adapter = LlamaCppAdapter(_llamacpp_config())
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.chat(_sample_messages())

        assert result.error is not None
        assert "empty_response" in result.error
        adapter.close()


class TestLlamaCppChatMessageFormat:
    def test_tool_response_message_format(self) -> None:
        """Tool result messages are formatted correctly for LlamaCpp."""
        messages = [
            ChatMessage(role=ChatRole.USER, content="Get order ORD-101"),
            ChatMessage(
                role=ChatRole.ASSISTANT,
                content=None,
                tool_calls=(
                    ToolCall(
                        id="call_0",
                        function_name="get_order",
                        arguments={"order_id": "ORD-101"},
                    ),
                ),
            ),
            ChatMessage(
                role=ChatRole.TOOL,
                content='{"id": "ORD-101", "state": "ACCEPTED"}',
                tool_call_id="call_0",
            ),
        ]
        resp = _mock_response(
            json_data=_llamacpp_chat_response(content="Order ORD-101 is ACCEPTED."),
        )
        adapter = LlamaCppAdapter(_llamacpp_config())
        with patch.object(adapter._client, "post", return_value=resp) as mock_post:
            adapter.chat(messages, tools=[_SAMPLE_TOOL])

        payload = mock_post.call_args.kwargs["json"]
        assert len(payload["messages"]) == 3
        # Assistant message should have tool_calls
        assert "tool_calls" in payload["messages"][1]
        assert payload["messages"][1]["tool_calls"][0]["function"]["name"] == "get_order"
        # Tool result message
        assert payload["messages"][2]["role"] == "tool"
        # Verify tool call has id and type fields
        tc = payload["messages"][1]["tool_calls"][0]
        assert "id" in tc
        assert tc["type"] == "function"
        assert isinstance(tc["function"]["arguments"], str)
        adapter.close()


# ===========================================================================
# LlamaCpp chat() additional coverage
# ===========================================================================


class TestLlamaCppChatEmptyChoices:
    """#10: Empty choices list returns error."""

    def test_empty_choices_returns_error(self) -> None:
        envelope: dict[str, Any] = {
            "id": "chatcmpl-test",
            "model": "llama-3.1-8b",
            "choices": [],
            "usage": {"prompt_tokens": 10, "completion_tokens": 0},
        }
        resp = _mock_response(json_data=envelope)
        adapter = LlamaCppAdapter(_llamacpp_config())
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.chat(_sample_messages())

        assert result.error is not None
        assert "empty_response" in result.error
        adapter.close()


class TestLlamaCppMalformedToolCallArgs:
    """#9: Malformed JSON string arguments handled gracefully."""

    def test_unparseable_arguments_returns_empty_dict(self) -> None:
        raw_tool_calls = [
            {
                "id": "call_bad",
                "type": "function",
                "function": {
                    "name": "get_order",
                    "arguments": "{invalid json",
                },
            }
        ]
        resp = _mock_response(
            json_data=_llamacpp_chat_response(tool_calls=raw_tool_calls),
        )
        adapter = LlamaCppAdapter(_llamacpp_config())
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.chat(_sample_messages(), tools=[_SAMPLE_TOOL])

        assert result.error is None
        assert result.message.tool_calls[0].arguments == {}
        adapter.close()


# ===========================================================================
# LlamaCpp chat_stream() tests
# ===========================================================================


def _sse_lines(*data_items: str) -> list[str]:
    """Build SSE-formatted lines from data strings."""
    lines = [f"data: {item}" for item in data_items]
    lines.append("data: [DONE]")
    return lines


class _FakeStreamResponse:
    """Mock for httpx stream context manager."""

    def __init__(self, lines: list[str], status_code: int = 200) -> None:
        self._lines = lines
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"{self.status_code}",
                request=_LLAMACPP_FAKE_REQUEST,
                response=httpx.Response(self.status_code),
            )

    def iter_lines(self) -> Iterator[str]:
        yield from self._lines

    def __enter__(self) -> _FakeStreamResponse:
        return self

    def __exit__(self, *args: Any) -> None:
        pass


def _stream_chunk(
    content: str | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
    usage: dict[str, int] | None = None,
    finish_reason: str | None = None,
) -> str:
    """Build a single SSE chunk JSON string."""
    delta: dict[str, Any] = {}
    if content is not None:
        delta["content"] = content
    if tool_calls is not None:
        delta["tool_calls"] = tool_calls
    chunk: dict[str, Any] = {
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    if usage is not None:
        chunk["usage"] = usage
    return json.dumps(chunk)


class TestLlamaCppChatStreamText:
    """Test streaming text responses."""

    def test_yields_tokens_then_chat_response(self) -> None:
        chunks = [
            _stream_chunk(content="Hello"),
            _stream_chunk(content=" world"),
            _stream_chunk(
                content="",
                finish_reason="stop",
                usage={"prompt_tokens": 10, "completion_tokens": 2},
            ),
        ]
        fake_stream = _FakeStreamResponse(_sse_lines(*chunks))
        adapter = LlamaCppAdapter(_llamacpp_config())
        with patch.object(adapter._client, "stream", return_value=fake_stream):
            results = list(adapter.chat_stream(_sample_messages()))

        # Should yield "Hello", " world", then a ChatResponse
        tokens = [r for r in results if isinstance(r, str)]
        assert tokens == ["Hello", " world"]
        final = results[-1]
        assert isinstance(final, ChatResponse)
        assert final.message.content == "Hello world"
        assert final.error is None
        assert final.input_tokens == 10
        assert final.output_tokens == 2
        adapter.close()


class TestLlamaCppChatStreamToolCalls:
    """Test streaming tool call accumulation."""

    def test_accumulates_tool_calls_across_chunks(self) -> None:
        chunks = [
            _stream_chunk(
                tool_calls=[
                    {
                        "index": 0,
                        "id": "call_abc",
                        "function": {"name": "get_order", "arguments": '{"order'},
                    },
                ]
            ),
            _stream_chunk(
                tool_calls=[
                    {"index": 0, "function": {"arguments": '_id": "ORD-101"}'}},
                ]
            ),
            _stream_chunk(
                finish_reason="tool_calls",
                usage={"prompt_tokens": 20, "completion_tokens": 5},
            ),
        ]
        fake_stream = _FakeStreamResponse(_sse_lines(*chunks))
        adapter = LlamaCppAdapter(_llamacpp_config())
        with patch.object(adapter._client, "stream", return_value=fake_stream):
            results = list(adapter.chat_stream(_sample_messages(), tools=[_SAMPLE_TOOL]))

        # No text tokens yielded
        tokens = [r for r in results if isinstance(r, str)]
        assert tokens == []
        final = results[-1]
        assert isinstance(final, ChatResponse)
        assert final.message.content is None
        assert len(final.message.tool_calls) == 1
        assert final.message.tool_calls[0].id == "call_abc"
        assert final.message.tool_calls[0].function_name == "get_order"
        assert final.message.tool_calls[0].arguments == {"order_id": "ORD-101"}
        adapter.close()


class TestLlamaCppChatStreamErrors:
    """Test streaming error paths."""

    def test_connection_error(self) -> None:
        adapter = LlamaCppAdapter(_llamacpp_config())
        with patch.object(
            adapter._client,
            "stream",
            side_effect=httpx.ConnectError("refused"),
        ):
            results = list(adapter.chat_stream(_sample_messages()))

        assert len(results) == 1
        assert isinstance(results[0], ChatResponse)
        assert "connection_error" in results[0].error
        adapter.close()

    def test_timeout(self) -> None:
        adapter = LlamaCppAdapter(_llamacpp_config())
        with patch.object(
            adapter._client,
            "stream",
            side_effect=httpx.ReadTimeout("timed out"),
        ):
            results = list(adapter.chat_stream(_sample_messages()))

        assert len(results) == 1
        assert isinstance(results[0], ChatResponse)
        assert "timeout" in results[0].error
        adapter.close()

    def test_missing_done_sentinel(self) -> None:
        """Stream ends without [DONE] — should set error on ChatResponse."""
        chunks = [_stream_chunk(content="partial")]
        # No [DONE] sentinel
        lines = [f"data: {c}" for c in chunks]
        fake_stream = _FakeStreamResponse(lines)
        adapter = LlamaCppAdapter(_llamacpp_config())
        with patch.object(adapter._client, "stream", return_value=fake_stream):
            results = list(adapter.chat_stream(_sample_messages()))

        final = results[-1]
        assert isinstance(final, ChatResponse)
        assert final.error is not None
        assert "stream_interrupted" in final.error
        assert final.message.content == "partial"
        adapter.close()


# ===========================================================================
# OpenRouter chat() tests
# ===========================================================================


class TestOpenRouterChatSuccess:
    def test_text_response(self) -> None:
        resp = _mock_response(
            json_data=_openai_chat_response(content="The answer is 42."),
            request=_OPENROUTER_FAKE_REQUEST,
        )
        adapter = OpenRouterAdapter(_openrouter_config(), api_key="sk-or-test")
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.chat(_sample_messages())

        assert isinstance(result, ChatResponse)
        assert result.message.role == ChatRole.ASSISTANT
        assert result.message.content == "The answer is 42."
        assert result.message.tool_calls == ()
        assert result.error is None
        assert result.input_tokens == 42
        assert result.output_tokens == 18
        assert result.cost_estimate_usd is not None
        adapter.close()

    def test_tool_call_response(self) -> None:
        raw_tool_calls = [
            {
                "id": "call_abc123",
                "type": "function",
                "function": {
                    "name": "get_order",
                    "arguments": '{"order_id": "ORD-101"}',
                },
            }
        ]
        resp = _mock_response(
            json_data=_openai_chat_response(tool_calls=raw_tool_calls),
            request=_OPENROUTER_FAKE_REQUEST,
        )
        adapter = OpenRouterAdapter(_openrouter_config(), api_key="sk-or-test")
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.chat(_sample_messages(), tools=[_SAMPLE_TOOL])

        assert result.error is None
        assert result.message.content is None
        assert len(result.message.tool_calls) == 1
        tc = result.message.tool_calls[0]
        assert tc.id == "call_abc123"
        assert tc.function_name == "get_order"
        assert tc.arguments == {"order_id": "ORD-101"}
        adapter.close()

    def test_multiple_tool_calls(self) -> None:
        raw_tool_calls = [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "get_order",
                    "arguments": '{"order_id": "ORD-101"}',
                },
            },
            {
                "id": "call_2",
                "type": "function",
                "function": {
                    "name": "get_slides",
                    "arguments": '{"order_id": "ORD-101"}',
                },
            },
        ]
        resp = _mock_response(
            json_data=_openai_chat_response(tool_calls=raw_tool_calls),
            request=_OPENROUTER_FAKE_REQUEST,
        )
        adapter = OpenRouterAdapter(_openrouter_config(), api_key="sk-or-test")
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.chat(_sample_messages(), tools=[_SAMPLE_TOOL])

        assert len(result.message.tool_calls) == 2
        assert result.message.tool_calls[0].id == "call_1"
        assert result.message.tool_calls[1].id == "call_2"
        adapter.close()

    def test_sends_correct_payload_with_tools(self) -> None:
        resp = _mock_response(
            json_data=_openai_chat_response(content="response"),
            request=_OPENROUTER_FAKE_REQUEST,
        )
        adapter = OpenRouterAdapter(
            _openrouter_config(temperature=0.5, max_tokens=512),
            api_key="sk-or-test",
        )
        with patch.object(adapter._client, "post", return_value=resp) as mock_post:
            adapter.chat(_sample_messages(), tools=[_SAMPLE_TOOL])

        mock_post.assert_called_once()
        payload = mock_post.call_args.kwargs["json"]
        assert payload["model"] == "anthropic/claude-haiku-4-5"
        assert payload["temperature"] == 0.5
        assert payload["max_tokens"] == 512
        assert payload["tools"] == [_SAMPLE_TOOL]
        assert payload["tool_choice"] == "auto"
        assert len(payload["messages"]) == 2
        adapter.close()

    def test_no_tools_omits_tools_and_tool_choice(self) -> None:
        resp = _mock_response(
            json_data=_openai_chat_response(content="response"),
            request=_OPENROUTER_FAKE_REQUEST,
        )
        adapter = OpenRouterAdapter(_openrouter_config(), api_key="sk-or-test")
        with patch.object(adapter._client, "post", return_value=resp) as mock_post:
            adapter.chat(_sample_messages())

        payload = mock_post.call_args.kwargs["json"]
        assert "tools" not in payload
        assert "tool_choice" not in payload
        adapter.close()

    def test_malformed_tool_call_arguments_handled(self) -> None:
        """Malformed JSON in tool_call arguments falls back to empty dict."""
        raw_tool_calls = [
            {
                "id": "call_bad",
                "type": "function",
                "function": {
                    "name": "get_order",
                    "arguments": "not-valid-json",
                },
            }
        ]
        resp = _mock_response(
            json_data=_openai_chat_response(tool_calls=raw_tool_calls),
            request=_OPENROUTER_FAKE_REQUEST,
        )
        adapter = OpenRouterAdapter(_openrouter_config(), api_key="sk-or-test")
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.chat(_sample_messages(), tools=[_SAMPLE_TOOL])

        assert result.error is None
        assert result.message.tool_calls[0].arguments == {}
        adapter.close()


class TestOpenRouterChatErrors:
    def test_connection_error(self) -> None:
        adapter = OpenRouterAdapter(_openrouter_config(), api_key="sk-or-test")
        with patch.object(
            adapter._client,
            "post",
            side_effect=httpx.ConnectError("refused"),
        ):
            result = adapter.chat(_sample_messages())

        assert result.error is not None
        assert "connection_error" in result.error
        adapter.close()

    def test_timeout(self) -> None:
        adapter = OpenRouterAdapter(
            _openrouter_config(),
            api_key="sk-or-test",
            timeout_seconds=30,
        )
        with patch.object(
            adapter._client,
            "post",
            side_effect=httpx.ReadTimeout("timed out"),
        ):
            result = adapter.chat(_sample_messages())

        assert result.error is not None
        assert "timeout" in result.error
        assert result.timed_out is True
        adapter.close()

    def test_auth_error(self) -> None:
        resp = _mock_response(
            401,
            text="Invalid API key",
            request=_OPENROUTER_FAKE_REQUEST,
        )
        adapter = OpenRouterAdapter(_openrouter_config(), api_key="sk-or-bad")
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.chat(_sample_messages())

        assert result.error is not None
        assert "auth_error" in result.error
        adapter.close()

    def test_rate_limit(self) -> None:
        resp = _mock_response(
            429,
            text="Rate limit exceeded",
            request=_OPENROUTER_FAKE_REQUEST,
        )
        adapter = OpenRouterAdapter(_openrouter_config(), api_key="sk-or-test")
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.chat(_sample_messages())

        assert result.error is not None
        assert "rate_limit" in result.error
        adapter.close()

    def test_http_500(self) -> None:
        resp = _mock_response(
            500,
            text="Internal Server Error",
            request=_OPENROUTER_FAKE_REQUEST,
        )
        adapter = OpenRouterAdapter(_openrouter_config(), api_key="sk-or-test")
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.chat(_sample_messages())

        assert result.error is not None
        assert "http_error" in result.error
        assert "500" in result.error
        adapter.close()

    def test_malformed_json_response(self) -> None:
        resp = _mock_response(
            text="<html>error</html>",
            request=_OPENROUTER_FAKE_REQUEST,
        )
        adapter = OpenRouterAdapter(_openrouter_config(), api_key="sk-or-test")
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.chat(_sample_messages())

        assert result.error is not None
        assert "malformed_json" in result.error
        adapter.close()

    def test_empty_choices(self) -> None:
        envelope: dict[str, Any] = {
            "id": "gen-abc",
            "model": "anthropic/claude-haiku-4-5",
            "choices": [],
            "usage": {"prompt_tokens": 10, "completion_tokens": 0},
        }
        resp = _mock_response(
            json_data=envelope,
            request=_OPENROUTER_FAKE_REQUEST,
        )
        adapter = OpenRouterAdapter(_openrouter_config(), api_key="sk-or-test")
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.chat(_sample_messages())

        assert result.error is not None
        assert "empty_response" in result.error
        adapter.close()

    def test_transport_error(self) -> None:
        adapter = OpenRouterAdapter(_openrouter_config(), api_key="sk-or-test")
        with patch.object(
            adapter._client,
            "post",
            side_effect=httpx.ReadError("reset"),
        ):
            result = adapter.chat(_sample_messages())

        assert result.error is not None
        assert "transport_error" in result.error
        adapter.close()


class TestOpenRouterReasoningFallback:
    """Test that reasoning field is used as fallback when content and tool_calls are absent."""

    def test_reasoning_used_as_fallback_content(self) -> None:
        envelope: dict[str, Any] = {
            "id": "gen-abc",
            "model": "qwen/qwen3-8b",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "reasoning": "The user is asking about blocked orders. I should check...",
                    }
                }
            ],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }
        resp = _mock_response(
            json_data=envelope,
            request=_OPENROUTER_FAKE_REQUEST,
        )
        adapter = OpenRouterAdapter(_openrouter_config(), api_key="sk-or-test")
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.chat(_sample_messages())

        assert result.error is None
        assert (
            result.message.content == "The user is asking about blocked orders. I should check..."
        )
        adapter.close()

    def test_empty_reasoning_still_errors(self) -> None:
        envelope: dict[str, Any] = {
            "id": "gen-abc",
            "model": "qwen/qwen3-8b",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "reasoning": "   ",
                    }
                }
            ],
            "usage": {"prompt_tokens": 100, "completion_tokens": 0},
        }
        resp = _mock_response(
            json_data=envelope,
            request=_OPENROUTER_FAKE_REQUEST,
        )
        adapter = OpenRouterAdapter(_openrouter_config(), api_key="sk-or-test")
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.chat(_sample_messages())

        assert result.error is not None
        assert "empty_response" in result.error
        adapter.close()

    def test_no_reasoning_field_still_errors(self) -> None:
        envelope: dict[str, Any] = {
            "id": "gen-abc",
            "model": "qwen/qwen3-8b",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                    }
                }
            ],
            "usage": {"prompt_tokens": 100, "completion_tokens": 0},
        }
        resp = _mock_response(
            json_data=envelope,
            request=_OPENROUTER_FAKE_REQUEST,
        )
        adapter = OpenRouterAdapter(_openrouter_config(), api_key="sk-or-test")
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.chat(_sample_messages())

        assert result.error is not None
        assert "empty_response" in result.error
        adapter.close()

    def test_non_string_reasoning_still_errors(self) -> None:
        envelope: dict[str, Any] = {
            "id": "gen-abc",
            "model": "qwen/qwen3-8b",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "reasoning": 42,
                    }
                }
            ],
            "usage": {"prompt_tokens": 100, "completion_tokens": 0},
        }
        resp = _mock_response(
            json_data=envelope,
            request=_OPENROUTER_FAKE_REQUEST,
        )
        adapter = OpenRouterAdapter(_openrouter_config(), api_key="sk-or-test")
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.chat(_sample_messages())

        assert result.error is not None
        assert "empty_response" in result.error
        adapter.close()


class TestOpenRouterChatMessageFormat:
    def test_tool_response_message_format(self) -> None:
        """Tool result messages include tool_call_id in OpenAI format."""
        messages = [
            ChatMessage(role=ChatRole.USER, content="Get order ORD-101"),
            ChatMessage(
                role=ChatRole.ASSISTANT,
                content=None,
                tool_calls=(
                    ToolCall(
                        id="call_abc",
                        function_name="get_order",
                        arguments={"order_id": "ORD-101"},
                    ),
                ),
            ),
            ChatMessage(
                role=ChatRole.TOOL,
                content='{"id": "ORD-101", "state": "ACCEPTED"}',
                tool_call_id="call_abc",
            ),
        ]
        resp = _mock_response(
            json_data=_openai_chat_response(content="Order ORD-101 is ACCEPTED."),
            request=_OPENROUTER_FAKE_REQUEST,
        )
        adapter = OpenRouterAdapter(_openrouter_config(), api_key="sk-or-test")
        with patch.object(adapter._client, "post", return_value=resp) as mock_post:
            adapter.chat(messages, tools=[_SAMPLE_TOOL])

        payload = mock_post.call_args.kwargs["json"]
        assert len(payload["messages"]) == 3
        # Assistant message should have tool_calls with id and stringified arguments
        assistant_msg = payload["messages"][1]
        assert assistant_msg["tool_calls"][0]["id"] == "call_abc"
        assert assistant_msg["tool_calls"][0]["type"] == "function"
        assert assistant_msg["tool_calls"][0]["function"]["arguments"] == '{"order_id": "ORD-101"}'
        # Tool result message should have tool_call_id
        tool_msg = payload["messages"][2]
        assert tool_msg["role"] == "tool"
        assert tool_msg["tool_call_id"] == "call_abc"
        adapter.close()


# ===========================================================================
# ModelAdapter default chat() raises
# ===========================================================================


class TestDefaultChatRaises:
    def test_default_chat_raises_not_implemented(self) -> None:
        """Adapters that don't override chat() raise NotImplementedError."""
        from src.models.base import ModelAdapter, ModelResponse

        class MinimalAdapter(ModelAdapter):
            def predict(self, prompt: str) -> ModelResponse:
                raise NotImplementedError

            @property
            def model_id(self) -> str:
                return "test-model"

            @property
            def provider(self) -> str:
                return "test"

        adapter = MinimalAdapter()
        with pytest.raises(NotImplementedError, match="test/test-model"):
            adapter.chat([ChatMessage(role=ChatRole.USER, content="hi")])


# ===========================================================================
# Missing tests added from code review (#4-7, #14-16)
# ===========================================================================


class TestParseToolCallsEmptyFunctionName:
    """#4: _parse_tool_calls returns error when function name is missing."""

    def test_llamacpp_missing_function_name_returns_error(self) -> None:
        raw_tool_calls = [{"function": {"arguments": {"x": 1}}}]
        resp = _mock_response(
            json_data=_llamacpp_chat_response(tool_calls=raw_tool_calls),
        )
        adapter = LlamaCppAdapter(_llamacpp_config())
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.chat(_sample_messages(), tools=[_SAMPLE_TOOL])

        assert result.error is not None
        assert "malformed_tool_call" in result.error
        adapter.close()

    def test_openrouter_missing_function_name_returns_error(self) -> None:
        raw_tool_calls = [
            {
                "id": "call_bad",
                "type": "function",
                "function": {"arguments": "{}"},
            }
        ]
        resp = _mock_response(
            json_data=_openai_chat_response(tool_calls=raw_tool_calls),
            request=_OPENROUTER_FAKE_REQUEST,
        )
        adapter = OpenRouterAdapter(_openrouter_config(), api_key="sk-or-test")
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.chat(_sample_messages(), tools=[_SAMPLE_TOOL])

        assert result.error is not None
        assert "malformed_tool_call" in result.error
        adapter.close()


class TestOpenRouterNonDictArguments:
    """#5: OpenRouter _parse_tool_calls with non-string/non-dict arguments."""

    def test_list_arguments_falls_back_to_empty_dict(self) -> None:
        raw_tool_calls = [
            {
                "id": "call_bad",
                "type": "function",
                "function": {
                    "name": "get_order",
                    "arguments": ["list", "not", "dict"],
                },
            }
        ]
        resp = _mock_response(
            json_data=_openai_chat_response(tool_calls=raw_tool_calls),
            request=_OPENROUTER_FAKE_REQUEST,
        )
        adapter = OpenRouterAdapter(_openrouter_config(), api_key="sk-or-test")
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.chat(_sample_messages(), tools=[_SAMPLE_TOOL])

        assert result.error is None
        assert result.message.tool_calls[0].arguments == {}
        adapter.close()


class TestChatResponseBoolTokensRejected:
    """#6: ChatResponse validation rejects bool for token counts."""

    def test_bool_input_tokens_raises(self) -> None:
        msg = ChatMessage(role=ChatRole.ASSISTANT, content="Hello")
        with pytest.raises(TypeError, match="input_tokens must be int"):
            ChatResponse(
                message=msg,
                latency_ms=100.0,
                input_tokens=True,  # type: ignore[arg-type]
                output_tokens=5,
                cost_estimate_usd=None,
                model_id="test-model",
            )

    def test_bool_output_tokens_raises(self) -> None:
        msg = ChatMessage(role=ChatRole.ASSISTANT, content="Hello")
        with pytest.raises(TypeError, match="output_tokens must be int"):
            ChatResponse(
                message=msg,
                latency_ms=100.0,
                input_tokens=5,
                output_tokens=False,  # type: ignore[arg-type]
                cost_estimate_usd=None,
                model_id="test-model",
            )


class TestChatResponseNegativeCost:
    """#7: ChatResponse validation rejects negative cost_estimate_usd."""

    def test_negative_cost_estimate_raises(self) -> None:
        msg = ChatMessage(role=ChatRole.ASSISTANT, content="Hello")
        with pytest.raises(ValueError, match="non-negative"):
            ChatResponse(
                message=msg,
                latency_ms=100.0,
                input_tokens=10,
                output_tokens=5,
                cost_estimate_usd=-0.001,
                model_id="test-model",
            )


class TestChatResponseIntegerCost:
    """#15: ChatResponse validation rejects integer cost_estimate_usd."""

    def test_integer_cost_estimate_raises(self) -> None:
        msg = ChatMessage(role=ChatRole.ASSISTANT, content="Hello")
        with pytest.raises(TypeError, match="cost_estimate_usd must be float"):
            ChatResponse(
                message=msg,
                latency_ms=100.0,
                input_tokens=10,
                output_tokens=5,
                cost_estimate_usd=0,  # type: ignore[arg-type]
                model_id="test-model",
            )


class TestEmptyToolsList:
    """#14: Empty tools list is treated the same as None."""

    def test_ollama_empty_tools_omits_key(self) -> None:
        resp = _mock_response(
            json_data=_llamacpp_chat_response(content="response"),
        )
        adapter = LlamaCppAdapter(_llamacpp_config())
        with patch.object(adapter._client, "post", return_value=resp) as mock_post:
            adapter.chat(_sample_messages(), tools=[])

        payload = mock_post.call_args.kwargs["json"]
        assert "tools" not in payload
        adapter.close()

    def test_openrouter_empty_tools_omits_key(self) -> None:
        resp = _mock_response(
            json_data=_openai_chat_response(content="response"),
            request=_OPENROUTER_FAKE_REQUEST,
        )
        adapter = OpenRouterAdapter(_openrouter_config(), api_key="sk-or-test")
        with patch.object(adapter._client, "post", return_value=resp) as mock_post:
            adapter.chat(_sample_messages(), tools=[])

        payload = mock_post.call_args.kwargs["json"]
        assert "tools" not in payload
        assert "tool_choice" not in payload
        adapter.close()


class TestLlamaCppFormatArgumentsAsJsonString:
    """#16: LlamaCpp _format_messages passes arguments as JSON string (OpenAI format)."""

    def test_tool_call_arguments_are_json_string(self) -> None:
        messages = [
            ChatMessage(role=ChatRole.USER, content="Get order ORD-101"),
            ChatMessage(
                role=ChatRole.ASSISTANT,
                content=None,
                tool_calls=(
                    ToolCall(
                        id="call_0",
                        function_name="get_order",
                        arguments={"order_id": "ORD-101"},
                    ),
                ),
            ),
            ChatMessage(
                role=ChatRole.TOOL,
                content='{"id": "ORD-101"}',
                tool_call_id="call_0",
            ),
        ]
        resp = _mock_response(
            json_data=_llamacpp_chat_response(content="Done."),
        )
        adapter = LlamaCppAdapter(_llamacpp_config())
        with patch.object(adapter._client, "post", return_value=resp) as mock_post:
            adapter.chat(messages, tools=[_SAMPLE_TOOL])

        payload = mock_post.call_args.kwargs["json"]
        # LlamaCpp passes arguments as a JSON string (OpenAI format)
        args = payload["messages"][1]["tool_calls"][0]["function"]["arguments"]
        assert isinstance(args, str)
        assert json.loads(args) == {"order_id": "ORD-101"}
        adapter.close()


class TestOpenRouterErrorBody:
    """#10: OpenRouter 200-with-error-body is correctly classified."""

    def test_error_body_returns_api_error(self) -> None:
        envelope: dict[str, Any] = {
            "error": {
                "code": 429,
                "message": "Rate limit exceeded for model",
            }
        }
        resp = _mock_response(
            json_data=envelope,
            request=_OPENROUTER_FAKE_REQUEST,
        )
        adapter = OpenRouterAdapter(_openrouter_config(), api_key="sk-or-test")
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.chat(_sample_messages())

        assert result.error is not None
        assert "api_error_429" in result.error
        assert "Rate limit" in result.error
        adapter.close()


class TestErrorResponseContentIsNone:
    """#2: Error responses have message.content=None, not error string."""

    def test_ollama_error_response_content_is_none(self) -> None:
        adapter = LlamaCppAdapter(_llamacpp_config())
        with patch.object(
            adapter._client,
            "post",
            side_effect=httpx.ConnectError("refused"),
        ):
            result = adapter.chat(_sample_messages())

        assert result.error is not None
        assert result.message.content is None
        adapter.close()

    def test_openrouter_error_response_content_is_none(self) -> None:
        adapter = OpenRouterAdapter(_openrouter_config(), api_key="sk-or-test")
        with patch.object(
            adapter._client,
            "post",
            side_effect=httpx.ConnectError("refused"),
        ):
            result = adapter.chat(_sample_messages())

        assert result.error is not None
        assert result.message.content is None
        adapter.close()
