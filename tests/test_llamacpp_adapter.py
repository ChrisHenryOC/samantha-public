"""Tests for the llama.cpp model adapter.

Unit tests use mocked HTTP responses. Integration tests that require a
running llama-server instance are marked with ``@pytest.mark.integration``.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from src.models.base import ModelResponse
from src.models.config import ModelConfig
from src.models.llamacpp_adapter import (
    _SENTINEL_EMPTY_RESPONSE,
    _SENTINEL_TRANSPORT_ERROR,
    LlamaCppAdapter,
)
from src.models.parsing import parse_model_output as _parse_model_output

# --- Fixtures ---


def _make_config(
    *,
    model_id: str = "llama-3.1-8b",
    temperature: float = 0.0,
    max_tokens: int = 1024,
    token_limit: int = 131072,
) -> ModelConfig:
    return ModelConfig(
        name="Test Model",
        provider="llamacpp",
        model_id=model_id,
        temperature=temperature,
        max_tokens=max_tokens,
        token_limit=token_limit,
    )


_FAKE_REQUEST = httpx.Request("POST", "http://localhost:8080/v1/chat/completions")


def _openai_response(
    response_text: str,
    *,
    prompt_tokens: int = 42,
    completion_tokens: int = 18,
) -> dict[str, Any]:
    """Build a realistic llama-server /v1/chat/completions response envelope."""
    return {
        "id": "chatcmpl-test",
        "model": "llama-3.1-8b",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": response_text},
                "finish_reason": "stop",
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
    json: dict[str, Any] | None = None,
    text: str | None = None,
) -> httpx.Response:
    """Create an httpx.Response with a request attached."""
    kwargs: dict[str, Any] = {}
    if json is not None:
        kwargs["json"] = json
    if text is not None:
        kwargs["text"] = text
    resp = httpx.Response(status_code, **kwargs)
    resp._request = _FAKE_REQUEST
    return resp


def _valid_model_json() -> str:
    """Return a valid structured JSON string matching the expected schema."""
    return json.dumps(
        {
            "next_state": "grossing_queue",
            "applied_rules": ["R-001"],
            "flags": [],
            "reasoning": "Standard breast specimen routes to grossing.",
        }
    )


# --- Construction ---


class TestLlamaCppAdapterConstruction:
    def test_valid_config(self) -> None:
        adapter = LlamaCppAdapter(_make_config())
        assert adapter.model_id == "llama-3.1-8b"
        assert adapter.provider == "llamacpp"
        adapter.close()

    def test_rejects_non_llamacpp_provider(self) -> None:
        config = ModelConfig(
            name="Claude",
            provider="openrouter",
            model_id="claude-haiku-4-5-20251001",
            temperature=0.0,
            max_tokens=1024,
            token_limit=200000,
        )
        with pytest.raises(ValueError, match="requires provider='llamacpp'"):
            LlamaCppAdapter(config)

    def test_custom_base_url_and_timeout(self) -> None:
        """Verify custom base_url and timeout are applied to the HTTP client."""
        resp = _mock_response(json=_openai_response(_valid_model_json()))
        adapter = LlamaCppAdapter(
            _make_config(),
            base_url="http://gpu-server:8080/",
            timeout_seconds=300,
        )
        with patch.object(adapter._client, "post", return_value=resp) as mock_post:
            adapter.predict("test")
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs.args[0] == "/v1/chat/completions"
        adapter.close()


# --- Successful prediction ---


class TestLlamaCppAdapterSuccess:
    def test_valid_json_response(self) -> None:
        valid_json = _valid_model_json()
        resp = _mock_response(
            json=_openai_response(valid_json, prompt_tokens=100, completion_tokens=50),
        )
        adapter = LlamaCppAdapter(_make_config())
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.predict("test prompt")

        assert isinstance(result, ModelResponse)
        assert result.raw_text == valid_json
        assert result.parsed_output is not None
        assert result.parsed_output["next_state"] == "grossing_queue"
        assert result.error is None
        assert result.input_tokens == 100
        assert result.output_tokens == 50
        assert result.cost_estimate_usd is None
        assert result.model_id == "llama-3.1-8b"
        assert result.latency_ms >= 0
        adapter.close()

    def test_sends_correct_payload(self) -> None:
        resp = _mock_response(json=_openai_response(_valid_model_json()))
        adapter = LlamaCppAdapter(
            _make_config(temperature=0.5, max_tokens=512),
            base_url="http://myhost:8080",
            timeout_seconds=60,
        )
        with patch.object(adapter._client, "post", return_value=resp) as mock_post:
            adapter.predict("hello world")

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs.args[0] == "/v1/chat/completions"
        payload = call_kwargs.kwargs["json"]
        assert payload["model"] == "llama-3.1-8b"
        assert payload["messages"][0]["content"] == "hello world"
        assert payload["stream"] is False
        assert payload["temperature"] == 0.5
        assert payload["max_tokens"] == 512
        adapter.close()


# --- Failure categorization ---


class TestLlamaCppAdapterConnectionError:
    def test_connection_error(self) -> None:
        adapter = LlamaCppAdapter(_make_config())
        with patch.object(
            adapter._client,
            "post",
            side_effect=httpx.ConnectError("Connection refused"),
        ):
            result = adapter.predict("test")

        assert result.error is not None
        assert "connection_error" in result.error
        assert result.parsed_output is None
        assert result.input_tokens == 0
        assert result.output_tokens == 0
        adapter.close()


class TestLlamaCppAdapterTimeout:
    def test_read_timeout(self) -> None:
        adapter = LlamaCppAdapter(_make_config(), timeout_seconds=30)
        with patch.object(
            adapter._client,
            "post",
            side_effect=httpx.ReadTimeout("timed out"),
        ):
            result = adapter.predict("test")

        assert result.error is not None
        assert "timeout" in result.error
        assert "30s" in result.error
        assert result.parsed_output is None
        adapter.close()

    def test_connect_timeout(self) -> None:
        """ConnectTimeout is also a TimeoutException subclass."""
        adapter = LlamaCppAdapter(_make_config(), timeout_seconds=15)
        with patch.object(
            adapter._client,
            "post",
            side_effect=httpx.ConnectTimeout("connect timed out"),
        ):
            result = adapter.predict("test")

        assert result.error is not None
        assert "timeout" in result.error
        assert "15s" in result.error
        assert result.parsed_output is None
        adapter.close()


class TestLlamaCppAdapterHTTPError:
    def test_http_500(self) -> None:
        err_resp = _mock_response(500, text="Internal Server Error")
        adapter = LlamaCppAdapter(_make_config())
        with patch.object(
            adapter._client,
            "post",
            side_effect=httpx.HTTPStatusError(
                "500 error", request=_FAKE_REQUEST, response=err_resp
            ),
        ):
            result = adapter.predict("test")

        assert result.error is not None
        assert "http_error" in result.error
        assert "500" in result.error
        adapter.close()

    def test_http_404(self) -> None:
        """404 may indicate llama-server endpoint not found."""
        err_resp = _mock_response(404, text="Not Found")
        adapter = LlamaCppAdapter(_make_config())
        with patch.object(
            adapter._client,
            "post",
            side_effect=httpx.HTTPStatusError(
                "404 error", request=_FAKE_REQUEST, response=err_resp
            ),
        ):
            result = adapter.predict("test")

        assert result.error is not None
        assert "http_error" in result.error
        assert "404" in result.error
        adapter.close()


class TestLlamaCppAdapterTransportError:
    """Tests for httpx transport errors beyond ConnectError/Timeout/HTTPStatus."""

    def test_read_error(self) -> None:
        """Connection drops while reading the response body."""
        adapter = LlamaCppAdapter(_make_config())
        with patch.object(
            adapter._client,
            "post",
            side_effect=httpx.ReadError("connection reset"),
        ):
            result = adapter.predict("test")

        assert result.error is not None
        assert "transport_error" in result.error
        assert "ReadError" in result.error
        assert result.raw_text == _SENTINEL_TRANSPORT_ERROR
        assert result.parsed_output is None
        adapter.close()

    def test_remote_protocol_error(self) -> None:
        """llama-server sends a malformed HTTP response."""
        adapter = LlamaCppAdapter(_make_config())
        with patch.object(
            adapter._client,
            "post",
            side_effect=httpx.RemoteProtocolError("malformed response"),
        ):
            result = adapter.predict("test")

        assert result.error is not None
        assert "transport_error" in result.error
        assert "RemoteProtocolError" in result.error
        adapter.close()


class TestLlamaCppAdapterMalformedJSON:
    def test_non_json_api_response(self) -> None:
        """llama-server returns non-JSON (e.g. HTML error page)."""
        resp = _mock_response(text="<html>Not JSON</html>")
        adapter = LlamaCppAdapter(_make_config())
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.predict("test")

        assert result.error is not None
        assert "malformed_json" in result.error
        adapter.close()

    def test_model_output_not_json(self) -> None:
        """Model produces plain text instead of JSON."""
        resp = _mock_response(json=_openai_response("This is plain text, not JSON."))
        adapter = LlamaCppAdapter(_make_config())
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.predict("test")

        assert result.error is not None
        assert "malformed_json" in result.error
        assert result.raw_text == "This is plain text, not JSON."
        adapter.close()


class TestLlamaCppAdapterWrongSchema:
    def test_missing_required_keys(self) -> None:
        """Model returns valid JSON but missing required fields."""
        incomplete = json.dumps({"next_state": "grossing_queue"})
        resp = _mock_response(json=_openai_response(incomplete))
        adapter = LlamaCppAdapter(_make_config())
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.predict("test")

        assert result.error is not None
        assert "wrong_schema" in result.error
        assert "missing required keys" in result.error
        assert result.parsed_output is None
        adapter.close()

    def test_json_array_instead_of_object(self) -> None:
        """Model returns a JSON array instead of an object."""
        resp = _mock_response(json=_openai_response("[1, 2, 3]"))
        adapter = LlamaCppAdapter(_make_config())
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.predict("test")

        assert result.error is not None
        assert "wrong_schema" in result.error
        assert "expected JSON object" in result.error
        adapter.close()


class TestLlamaCppAdapterEdgeCases:
    def test_empty_content(self) -> None:
        """llama-server returns empty content in choices."""
        envelope: dict[str, Any] = {
            "id": "chatcmpl-test",
            "model": "llama-3.1-8b",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": ""}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 0},
        }
        resp = _mock_response(json=envelope)
        adapter = LlamaCppAdapter(_make_config())
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.predict("test")

        assert result.raw_text == _SENTINEL_EMPTY_RESPONSE
        assert result.error is not None
        assert "empty_response" in result.error
        adapter.close()

    def test_empty_choices(self) -> None:
        """llama-server returns no choices."""
        envelope: dict[str, Any] = {
            "id": "chatcmpl-test",
            "model": "llama-3.1-8b",
            "choices": [],
            "usage": {"prompt_tokens": 10, "completion_tokens": 0},
        }
        resp = _mock_response(json=envelope)
        adapter = LlamaCppAdapter(_make_config())
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.predict("test")

        assert result.raw_text == _SENTINEL_EMPTY_RESPONSE
        assert result.error is not None
        assert "empty_response" in result.error
        adapter.close()

    def test_missing_usage(self) -> None:
        """Response missing usage object — tokens default to 0."""
        envelope: dict[str, Any] = {
            "id": "chatcmpl-test",
            "model": "llama-3.1-8b",
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": _valid_model_json()}}
            ],
        }
        resp = _mock_response(json=envelope)
        adapter = LlamaCppAdapter(_make_config())
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.predict("test")

        assert result.input_tokens == 0
        assert result.output_tokens == 0
        assert result.error is None
        adapter.close()


# --- _parse_model_output unit tests ---


class TestParseModelOutput:
    def test_valid_json(self) -> None:
        parsed, error = _parse_model_output(_valid_model_json())
        assert parsed is not None
        assert error is None
        assert parsed["next_state"] == "grossing_queue"

    def test_not_json(self) -> None:
        parsed, error = _parse_model_output("not json at all")
        assert parsed is None
        assert error is not None
        assert "malformed_json" in error

    def test_json_missing_keys(self) -> None:
        parsed, error = _parse_model_output('{"next_state": "x"}')
        assert parsed is None
        assert error is not None
        assert "wrong_schema" in error

    def test_json_array(self) -> None:
        parsed, error = _parse_model_output("[1, 2]")
        assert parsed is None
        assert error is not None
        assert "wrong_schema" in error

    def test_json_in_markdown_fence(self) -> None:
        fenced = (
            '```json\n{"next_state": "x", "applied_rules": [], "flags": [], "reasoning": "y"}\n```'
        )
        parsed, error = _parse_model_output(fenced)
        assert error is None
        assert parsed is not None
        assert parsed["next_state"] == "x"

    def test_json_in_plain_fence(self) -> None:
        fenced = '```\n{"next_state": "x", "applied_rules": [], "flags": [], "reasoning": "y"}\n```'
        parsed, error = _parse_model_output(fenced)
        assert error is None
        assert parsed is not None
        assert parsed["next_state"] == "x"

    def test_wrong_type_next_state(self) -> None:
        bad = json.dumps({"next_state": 42, "applied_rules": [], "flags": [], "reasoning": "test"})
        parsed, error = _parse_model_output(bad)
        assert parsed is None
        assert error is not None
        assert "wrong_schema" in error
        assert "next_state must be a string" in error

    def test_wrong_type_applied_rules(self) -> None:
        bad = json.dumps(
            {
                "next_state": "grossing_queue",
                "applied_rules": "R-001",
                "flags": [],
                "reasoning": "test",
            }
        )
        parsed, error = _parse_model_output(bad)
        assert parsed is None
        assert error is not None
        assert "wrong_schema" in error
        assert "applied_rules must be a list" in error

    def test_wrong_type_flags(self) -> None:
        bad = json.dumps(
            {
                "next_state": "grossing_queue",
                "applied_rules": [],
                "flags": "MISSING_INFO",
                "reasoning": "test",
            }
        )
        parsed, error = _parse_model_output(bad)
        assert parsed is None
        assert error is not None
        assert "wrong_schema" in error
        assert "flags must be a list" in error


# --- Integration tests (require running llama-server) ---


@pytest.mark.integration
class TestLlamaCppAdapterIntegration:
    """Tests that require a running llama-server instance.

    Run with: ``uv run pytest -m integration``
    """

    def test_real_inference(self) -> None:
        config = _make_config(model_id="llama-3.1-8b")
        adapter = LlamaCppAdapter(config, timeout_seconds=120)
        result = adapter.predict('Respond with exactly: {"next_state": "test"}')
        assert isinstance(result, ModelResponse)
        assert result.model_id == "llama-3.1-8b"
        assert result.latency_ms > 0
        if result.error is None:
            assert result.parsed_output is not None
        adapter.close()
