"""Tests for the OpenRouter model adapter.

Unit tests use mocked HTTP responses. Integration tests that require a
valid ``OPENROUTER_API_KEY`` are marked with ``@pytest.mark.integration``.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from src.models.base import ModelResponse
from src.models.config import ModelConfig
from src.models.openrouter_adapter import (
    _SENTINEL_AUTH_ERROR,
    _SENTINEL_CONNECTION_ERROR,
    _SENTINEL_EMPTY_RESPONSE,
    _SENTINEL_HTTP_ERROR,
    _SENTINEL_INVALID_JSON,
    _SENTINEL_RATE_LIMIT,
    _SENTINEL_TRANSPORT_ERROR,
    OpenRouterAdapter,
    _estimate_cost,
    _extract_content,
    _sanitize_error_message,
    resolve_openrouter_model,
)
from src.models.parsing import parse_model_output as _parse_model_output

# --- Fixtures ---


def _make_config(
    *,
    model_id: str = "claude-haiku-4-5-20251001",
    temperature: float = 0.0,
    max_tokens: int = 1024,
) -> ModelConfig:
    return ModelConfig(
        name="Test Claude",
        provider="openrouter",
        model_id=model_id,
        temperature=temperature,
        max_tokens=max_tokens,
        token_limit=200000,
    )


_FAKE_REQUEST = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")


def _openai_response(
    content: str,
    *,
    prompt_tokens: int = 42,
    completion_tokens: int = 18,
) -> dict[str, Any]:
    """Build a realistic OpenAI-compatible chat completions response."""
    return {
        "id": "gen-abc123",
        "model": "anthropic/claude-haiku-4-5",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
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
    json_data: dict[str, Any] | None = None,
    text: str | None = None,
) -> httpx.Response:
    """Create an httpx.Response with a request attached."""
    kwargs: dict[str, Any] = {}
    if json_data is not None:
        kwargs["json"] = json_data
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


# --- Model ID mapping ---


class TestModelIdMapping:
    def test_haiku_mapping(self) -> None:
        assert resolve_openrouter_model("claude-haiku-4-5-20251001") == "anthropic/claude-haiku-4-5"

    def test_sonnet_mapping(self) -> None:
        assert (
            resolve_openrouter_model("claude-sonnet-4-6-20250514") == "anthropic/claude-sonnet-4-6"
        )

    def test_opus_mapping(self) -> None:
        assert resolve_openrouter_model("claude-opus-4-6-20250514") == "anthropic/claude-opus-4-6"

    def test_qwen3_8b_mapping(self) -> None:
        assert resolve_openrouter_model("qwen/qwen3-8b") == "qwen/qwen3-8b"

    def test_phi4_mapping(self) -> None:
        assert resolve_openrouter_model("microsoft/phi-4") == "microsoft/phi-4"

    def test_qwen3_32b_mapping(self) -> None:
        assert resolve_openrouter_model("qwen/qwen3-32b") == "qwen/qwen3-32b"

    def test_mistral_small_mapping(self) -> None:
        assert (
            resolve_openrouter_model("mistralai/mistral-small-3.2-24b-instruct")
            == "mistralai/mistral-small-3.2-24b-instruct"
        )

    def test_gemma3_mapping(self) -> None:
        assert resolve_openrouter_model("google/gemma-3-27b-it") == "google/gemma-3-27b-it"

    def test_qwen35_moe_mapping(self) -> None:
        assert resolve_openrouter_model("qwen/qwen3.5-35b-a3b") == "qwen/qwen3.5-35b-a3b"

    def test_unknown_model_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown model ID"):
            resolve_openrouter_model("gpt-4o-mini")


# --- Construction ---


class TestOpenRouterAdapterConstruction:
    def test_valid_config(self) -> None:
        adapter = OpenRouterAdapter(_make_config(), api_key="sk-or-test")
        assert adapter.model_id == "claude-haiku-4-5-20251001"
        assert adapter.provider == "openrouter"
        adapter.close()

    def test_rejects_non_openrouter_provider(self) -> None:
        config = ModelConfig(
            name="Local Model",
            provider="llamacpp",
            model_id="test:7b",
            temperature=0.0,
            max_tokens=1024,
            token_limit=131072,
        )
        with pytest.raises(ValueError, match="requires provider='openrouter'"):
            OpenRouterAdapter(config, api_key="sk-or-test")

    def test_explicit_api_key(self) -> None:
        adapter = OpenRouterAdapter(_make_config(), api_key="sk-or-explicit")
        assert adapter.model_id == "claude-haiku-4-5-20251001"
        adapter.close()

    def test_env_var_api_key(self) -> None:
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "sk-or-env"}):
            adapter = OpenRouterAdapter(_make_config())
        assert adapter.model_id == "claude-haiku-4-5-20251001"
        adapter.close()

    def test_missing_api_key_raises(self) -> None:
        with (
            patch.dict("os.environ", {}, clear=True),
            pytest.raises(ValueError, match="requires an API key"),
        ):
            OpenRouterAdapter(_make_config())

    def test_missing_pricing_raises(self) -> None:
        config = ModelConfig(
            name="No Pricing",
            provider="openrouter",
            model_id="qwen/qwen3-8b",
            temperature=0.0,
            max_tokens=1024,
            token_limit=131072,
        )
        with (
            patch.dict(
                "src.models.openrouter_adapter._PRICING",
                {},
                clear=True,
            ),
            pytest.raises(ValueError, match="No pricing data"),
        ):
            OpenRouterAdapter(config, api_key="sk-or-test")

    def test_unknown_model_id_raises(self) -> None:
        config = ModelConfig(
            name="Unknown",
            provider="openrouter",
            model_id="unknown-model-id",
            temperature=0.0,
            max_tokens=1024,
            token_limit=200000,
        )
        with pytest.raises(ValueError, match="Unknown model ID"):
            OpenRouterAdapter(config, api_key="sk-or-test")


# --- Successful prediction ---


class TestOpenRouterAdapterSuccess:
    def test_valid_json_response(self) -> None:
        valid_json = _valid_model_json()
        resp = _mock_response(
            json_data=_openai_response(valid_json, prompt_tokens=100, completion_tokens=50),
        )
        adapter = OpenRouterAdapter(_make_config(), api_key="sk-or-test")
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.predict("test prompt")

        assert isinstance(result, ModelResponse)
        assert result.raw_text == valid_json
        assert result.parsed_output is not None
        assert result.parsed_output["next_state"] == "grossing_queue"
        assert result.error is None
        assert result.input_tokens == 100
        assert result.output_tokens == 50
        assert result.cost_estimate_usd is not None
        assert result.cost_estimate_usd > 0
        assert result.model_id == "claude-haiku-4-5-20251001"
        assert result.latency_ms >= 0
        adapter.close()

    def test_sends_correct_payload(self) -> None:
        resp = _mock_response(json_data=_openai_response(_valid_model_json()))
        adapter = OpenRouterAdapter(
            _make_config(temperature=0.5, max_tokens=512),
            api_key="sk-or-test",
        )
        with patch.object(adapter._client, "post", return_value=resp) as mock_post:
            adapter.predict("hello world")

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs.args[0] == "/chat/completions"
        payload = call_kwargs.kwargs["json"]
        assert payload["model"] == "anthropic/claude-haiku-4-5"
        assert payload["messages"] == [{"role": "user", "content": "hello world"}]
        assert payload["temperature"] == 0.5
        assert payload["max_tokens"] == 512
        # Reasoning mode must be disabled for all models (#9)
        assert payload["reasoning"] == {"effort": "none"}
        adapter.close()


# --- Failure categorization ---


class TestOpenRouterAdapterConnectionError:
    def test_connection_error(self) -> None:
        adapter = OpenRouterAdapter(_make_config(), api_key="sk-or-test")
        with patch.object(
            adapter._client,
            "post",
            side_effect=httpx.ConnectError("Connection refused"),
        ):
            result = adapter.predict("test")

        assert result.error is not None
        assert "connection_error" in result.error
        assert result.raw_text == _SENTINEL_CONNECTION_ERROR
        assert result.parsed_output is None
        assert result.input_tokens == 0
        assert result.output_tokens == 0
        adapter.close()


class TestOpenRouterAdapterTimeout:
    def test_read_timeout(self) -> None:
        adapter = OpenRouterAdapter(_make_config(), api_key="sk-or-test", timeout_seconds=30)
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
        adapter = OpenRouterAdapter(_make_config(), api_key="sk-or-test", timeout_seconds=15)
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


class TestOpenRouterAdapterAuthError:
    def test_401_authentication_error(self) -> None:
        resp = _mock_response(401, text="Invalid API key")
        adapter = OpenRouterAdapter(_make_config(), api_key="sk-or-bad")
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.predict("test")

        assert result.error is not None
        assert "auth_error" in result.error
        assert result.raw_text == _SENTINEL_AUTH_ERROR
        assert result.parsed_output is None
        assert result.input_tokens == 0
        assert result.output_tokens == 0
        adapter.close()


class TestOpenRouterAdapterRateLimit:
    def test_429_rate_limit(self) -> None:
        resp = _mock_response(429, text="Rate limit exceeded")
        adapter = OpenRouterAdapter(_make_config(), api_key="sk-or-test")
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.predict("test")

        assert result.error is not None
        assert "rate_limit" in result.error
        assert result.raw_text == _SENTINEL_RATE_LIMIT
        assert result.parsed_output is None
        adapter.close()


class TestOpenRouterAdapterHTTPError:
    def test_http_500(self) -> None:
        resp = _mock_response(500, text="Internal Server Error")
        adapter = OpenRouterAdapter(_make_config(), api_key="sk-or-test")
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.predict("test")

        assert result.error is not None
        assert "http_error" in result.error
        assert "500" in result.error
        assert "Internal Server Error" in result.error
        assert result.raw_text == _SENTINEL_HTTP_ERROR
        adapter.close()

    def test_http_404(self) -> None:
        resp = _mock_response(404, text="Model not found")
        adapter = OpenRouterAdapter(_make_config(), api_key="sk-or-test")
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.predict("test")

        assert result.error is not None
        assert "http_error" in result.error
        assert "404" in result.error
        assert result.raw_text == _SENTINEL_HTTP_ERROR
        adapter.close()

    def test_http_error_empty_body(self) -> None:
        """HTTP error with empty response body uses sentinel."""
        resp = _mock_response(502, text="")
        adapter = OpenRouterAdapter(_make_config(), api_key="sk-or-test")
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.predict("test")

        assert result.error is not None
        assert "http_error" in result.error
        assert result.raw_text == _SENTINEL_HTTP_ERROR
        adapter.close()


class TestOpenRouterAdapterTransportError:
    def test_read_error(self) -> None:
        adapter = OpenRouterAdapter(_make_config(), api_key="sk-or-test")
        with patch.object(
            adapter._client,
            "post",
            side_effect=httpx.ReadError("connection reset"),
        ):
            result = adapter.predict("test")

        assert result.error is not None
        assert "transport_error" in result.error
        assert "ReadError" in result.error
        assert "connection reset" in result.error
        assert result.raw_text == _SENTINEL_TRANSPORT_ERROR
        assert result.parsed_output is None
        adapter.close()


class TestOpenRouterAdapterMalformedJSON:
    def test_non_json_api_response(self) -> None:
        resp = _mock_response(text="<html>Not JSON</html>")
        adapter = OpenRouterAdapter(_make_config(), api_key="sk-or-test")
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.predict("test")

        assert result.error is not None
        assert "malformed_json" in result.error
        assert result.raw_text == _SENTINEL_INVALID_JSON
        adapter.close()

    def test_model_output_not_json(self) -> None:
        resp = _mock_response(
            json_data=_openai_response("This is plain text, not JSON."),
        )
        adapter = OpenRouterAdapter(_make_config(), api_key="sk-or-test")
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.predict("test")

        assert result.error is not None
        assert "malformed_json" in result.error
        assert result.raw_text == "This is plain text, not JSON."
        adapter.close()


class TestOpenRouterAdapterWrongSchema:
    def test_missing_required_keys(self) -> None:
        incomplete = json.dumps({"next_state": "grossing_queue"})
        resp = _mock_response(json_data=_openai_response(incomplete))
        adapter = OpenRouterAdapter(_make_config(), api_key="sk-or-test")
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.predict("test")

        assert result.error is not None
        assert "wrong_schema" in result.error
        assert "missing required keys" in result.error
        assert result.parsed_output is None
        adapter.close()

    def test_json_array_instead_of_object(self) -> None:
        resp = _mock_response(json_data=_openai_response("[1, 2, 3]"))
        adapter = OpenRouterAdapter(_make_config(), api_key="sk-or-test")
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.predict("test")

        assert result.error is not None
        assert "wrong_schema" in result.error
        assert "expected JSON object" in result.error
        adapter.close()


class TestOpenRouterAdapterEdgeCases:
    def test_empty_content(self) -> None:
        """API returns a choice with empty content."""
        resp = _mock_response(json_data=_openai_response(""))
        adapter = OpenRouterAdapter(_make_config(), api_key="sk-or-test")
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.predict("test")

        assert result.raw_text == _SENTINEL_EMPTY_RESPONSE
        assert result.error is not None
        assert "empty_response" in result.error
        adapter.close()

    def test_no_choices(self) -> None:
        """API returns an envelope with empty choices list."""
        envelope: dict[str, Any] = {
            "id": "gen-abc",
            "model": "anthropic/claude-haiku-4-5",
            "choices": [],
            "usage": {"prompt_tokens": 10, "completion_tokens": 0},
        }
        resp = _mock_response(json_data=envelope)
        adapter = OpenRouterAdapter(_make_config(), api_key="sk-or-test")
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.predict("test")

        assert result.raw_text == _SENTINEL_EMPTY_RESPONSE
        assert result.error is not None
        assert "empty_response" in result.error
        adapter.close()

    def test_missing_usage(self) -> None:
        """API response missing usage object."""
        envelope: dict[str, Any] = {
            "id": "gen-abc",
            "model": "anthropic/claude-haiku-4-5",
            "choices": [{"message": {"role": "assistant", "content": _valid_model_json()}}],
        }
        resp = _mock_response(json_data=envelope)
        adapter = OpenRouterAdapter(_make_config(), api_key="sk-or-test")
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.predict("test")

        assert result.input_tokens == 0
        assert result.output_tokens == 0
        assert result.error is None
        adapter.close()

    def test_null_content(self) -> None:
        """API returns null content in the message."""
        envelope: dict[str, Any] = {
            "id": "gen-abc",
            "model": "anthropic/claude-haiku-4-5",
            "choices": [{"message": {"role": "assistant", "content": None}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 0},
        }
        resp = _mock_response(json_data=envelope)
        adapter = OpenRouterAdapter(_make_config(), api_key="sk-or-test")
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.predict("test")

        assert result.raw_text == _SENTINEL_EMPTY_RESPONSE
        assert result.error is not None
        assert "empty_response" in result.error
        adapter.close()


# --- Content extraction ---


class TestExtractContent:
    def test_valid_structure(self) -> None:
        response = _openai_response("Hello, world!")
        assert _extract_content(response) == "Hello, world!"

    def test_missing_choices(self) -> None:
        assert _extract_content({}) == ""

    def test_empty_choices(self) -> None:
        assert _extract_content({"choices": []}) == ""

    def test_choices_not_list(self) -> None:
        assert _extract_content({"choices": "not-a-list"}) == ""

    def test_first_choice_not_dict(self) -> None:
        assert _extract_content({"choices": ["not-a-dict"]}) == ""

    def test_missing_message(self) -> None:
        assert _extract_content({"choices": [{}]}) == ""

    def test_message_not_dict(self) -> None:
        assert _extract_content({"choices": [{"message": "not-a-dict"}]}) == ""

    def test_missing_content(self) -> None:
        assert _extract_content({"choices": [{"message": {}}]}) == ""

    def test_content_not_string(self) -> None:
        assert _extract_content({"choices": [{"message": {"content": 123}}]}) == ""

    def test_null_content(self) -> None:
        assert _extract_content({"choices": [{"message": {"content": None}}]}) == ""


# --- Cost estimation ---


class TestCostEstimation:
    def test_haiku_cost(self) -> None:
        cost = _estimate_cost("claude-haiku-4-5-20251001", 1_000_000, 1_000_000)
        assert cost is not None
        assert cost == pytest.approx(6.0)  # $1 input + $5 output

    def test_sonnet_cost(self) -> None:
        cost = _estimate_cost("claude-sonnet-4-6-20250514", 1_000_000, 1_000_000)
        assert cost is not None
        assert cost == pytest.approx(18.0)  # $3 input + $15 output

    def test_opus_cost(self) -> None:
        cost = _estimate_cost("claude-opus-4-6-20250514", 1_000_000, 1_000_000)
        assert cost is not None
        assert cost == pytest.approx(30.0)  # $5 input + $25 output

    def test_qwen3_8b_cost(self) -> None:
        cost = _estimate_cost("qwen/qwen3-8b", 1_000_000, 1_000_000)
        assert cost is not None
        assert cost == pytest.approx(0.45)  # $0.05 input + $0.40 output

    def test_qwen3_32b_cost(self) -> None:
        cost = _estimate_cost("qwen/qwen3-32b", 1_000_000, 1_000_000)
        assert cost is not None
        assert cost == pytest.approx(0.32)  # $0.08 input + $0.24 output

    def test_mistral_small_cost(self) -> None:
        cost = _estimate_cost("mistralai/mistral-small-3.2-24b-instruct", 1_000_000, 1_000_000)
        assert cost is not None
        assert cost == pytest.approx(0.24)  # $0.06 input + $0.18 output

    def test_phi4_cost(self) -> None:
        cost = _estimate_cost("microsoft/phi-4", 1_000_000, 1_000_000)
        assert cost is not None
        assert cost == pytest.approx(0.21)  # $0.07 input + $0.14 output

    def test_gemma3_cost(self) -> None:
        cost = _estimate_cost("google/gemma-3-27b-it", 1_000_000, 1_000_000)
        assert cost is not None
        assert cost == pytest.approx(0.14)  # $0.03 input + $0.11 output

    def test_qwen35_moe_cost(self) -> None:
        cost = _estimate_cost("qwen/qwen3.5-35b-a3b", 1_000_000, 1_000_000)
        assert cost is not None
        assert cost == pytest.approx(1.46)  # $0.16 input + $1.30 output

    def test_unknown_model_returns_none(self) -> None:
        cost = _estimate_cost("unknown-model-id", 1000, 500)
        assert cost is None

    def test_small_token_count(self) -> None:
        cost = _estimate_cost("claude-haiku-4-5-20251001", 100, 50)
        assert cost is not None
        assert cost == pytest.approx(100 * 1.0 / 1e6 + 50 * 5.0 / 1e6)


# --- parse_model_output schema validation ---


class TestParseModelOutput:
    """Schema validation tests ported from the deleted Anthropic adapter suite."""

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

    def test_wrong_type_next_state(self) -> None:
        bad = json.dumps({"next_state": 42, "applied_rules": [], "flags": [], "reasoning": "test"})
        parsed, error = _parse_model_output(bad)
        assert parsed is None
        assert error is not None
        assert "next_state must be a string" in error

    def test_wrong_type_applied_rules(self) -> None:
        bad = json.dumps(
            {"next_state": "x", "applied_rules": "R-001", "flags": [], "reasoning": "test"}
        )
        parsed, error = _parse_model_output(bad)
        assert parsed is None
        assert error is not None
        assert "applied_rules must be a list" in error

    def test_wrong_type_flags(self) -> None:
        bad = json.dumps(
            {"next_state": "x", "applied_rules": [], "flags": "MISSING", "reasoning": "test"}
        )
        parsed, error = _parse_model_output(bad)
        assert parsed is None
        assert error is not None
        assert "flags must be a list" in error

    def test_wrong_type_reasoning(self) -> None:
        bad = json.dumps({"next_state": "x", "applied_rules": [], "flags": [], "reasoning": 42})
        parsed, error = _parse_model_output(bad)
        assert parsed is None
        assert error is not None
        assert "reasoning must be a string" in error

    def test_non_string_list_elements(self) -> None:
        bad = json.dumps(
            {"next_state": "x", "applied_rules": [1, None, True], "flags": [], "reasoning": "test"}
        )
        parsed, error = _parse_model_output(bad)
        assert parsed is None
        assert error is not None
        assert "elements must be strings" in error

    def test_json_in_markdown_fence(self) -> None:
        """Models occasionally wrap JSON in markdown code fences.

        The parser strips fences before attempting JSON parsing, so
        fenced output is handled correctly.
        """
        fenced = (
            '```json\n{"next_state": "x", "applied_rules": [], "flags": [], "reasoning": "y"}\n```'
        )
        parsed, error = _parse_model_output(fenced)
        assert error is None
        assert parsed is not None
        assert parsed["next_state"] == "x"

    def test_json_fence_preferred_over_thinking_fence(self) -> None:
        """When both thinking and json fences are present, json is extracted."""
        mixed = (
            "```thinking\nLet me analyze this case...\n```\n"
            '```json\n{"next_state": "x", "applied_rules": [], "flags": [], "reasoning": "y"}\n```'
        )
        parsed, error = _parse_model_output(mixed)
        assert error is None
        assert parsed is not None
        assert parsed["next_state"] == "x"

    def test_json_fence_found_regardless_of_order(self) -> None:
        """JSON fence is extracted even when it appears before a thinking fence."""
        valid = '{"next_state": "ACCEPTED", "applied_rules": [], "flags": [], "reasoning": "ok"}'
        json_first = f"```json\n{valid}\n```\n```thinking\nAdditional reasoning...\n```"
        parsed, error = _parse_model_output(json_first)
        assert error is None
        assert parsed is not None
        assert parsed["next_state"] == "ACCEPTED"

    def test_thinking_fence_only_fails(self) -> None:
        """Model output with only a thinking fence and no JSON fails parsing."""
        thinking_only = "```thinking\nThis is reasoning text\n```"
        parsed, error = _parse_model_output(thinking_only)
        assert parsed is None
        assert error is not None


# --- _sanitize_error_message ---


class TestSanitizeErrorMessage:
    def test_short_message_unchanged(self) -> None:
        assert _sanitize_error_message("short") == "short"

    def test_exactly_200_chars_unchanged(self) -> None:
        msg = "x" * 200
        assert _sanitize_error_message(msg) == msg

    def test_long_message_truncated(self) -> None:
        msg = "x" * 300
        assert len(_sanitize_error_message(msg)) == 200

    def test_empty_string(self) -> None:
        assert _sanitize_error_message("") == ""


# --- Additional edge case tests ---


class TestOpenRouterAdapterMalformedTokens:
    def test_malformed_token_counts_default_to_zero(self) -> None:
        """Malformed token values fall back to zero tokens and $0 cost.

        The ModelResponse invariant (error and parsed_output are mutually
        exclusive) prevents attaching a warning to a successful parse.
        Zero tokens on a successful response is anomalous and detectable
        in evaluation reports.
        """
        envelope: dict[str, Any] = {
            "id": "gen-abc",
            "model": "anthropic/claude-haiku-4-5",
            "choices": [{"message": {"role": "assistant", "content": _valid_model_json()}}],
            "usage": {"prompt_tokens": "not-a-number", "completion_tokens": None},
        }
        resp = _mock_response(json_data=envelope)
        adapter = OpenRouterAdapter(_make_config(), api_key="sk-or-test")
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.predict("test")

        assert result.input_tokens == 0
        assert result.output_tokens == 0
        assert result.cost_estimate_usd == 0.0
        assert result.parsed_output is not None
        assert result.error is None
        adapter.close()

    def test_malformed_token_counts_log_warning(self) -> None:
        """Malformed token values log a warning when falling back to zero."""
        envelope: dict[str, Any] = {
            "id": "gen-abc",
            "model": "anthropic/claude-haiku-4-5",
            "choices": [{"message": {"role": "assistant", "content": _valid_model_json()}}],
            "usage": {"prompt_tokens": "not-a-number", "completion_tokens": None},
        }
        resp = _mock_response(json_data=envelope)
        adapter = OpenRouterAdapter(_make_config(), api_key="sk-or-test")
        with (
            patch.object(adapter._client, "post", return_value=resp),
            patch("src.models.openrouter_adapter._logger") as mock_logger,
        ):
            adapter.predict("test")
        mock_logger.warning.assert_called_once()
        adapter.close()


class TestOpenRouterAdapterEmptyJsonResponse:
    def test_empty_response_text_json_failure(self) -> None:
        """JSON decode failure with empty response.text uses sentinel."""
        resp = _mock_response(text="")
        adapter = OpenRouterAdapter(_make_config(), api_key="sk-or-test")
        with patch.object(adapter._client, "post", return_value=resp):
            result = adapter.predict("test")

        assert result.error is not None
        assert "malformed_json" in result.error
        assert result.raw_text == _SENTINEL_INVALID_JSON
        adapter.close()


# --- Integration tests (require valid OPENROUTER_API_KEY) ---


@pytest.mark.integration
class TestOpenRouterAdapterIntegration:
    """Tests that require a valid OpenRouter API key.

    Run with: ``uv run pytest -m integration``
    """

    def test_real_inference(self) -> None:
        config = _make_config(model_id="claude-haiku-4-5-20251001")
        adapter = OpenRouterAdapter(config, timeout_seconds=120)
        result = adapter.predict('Respond with exactly: {"next_state": "test"}')
        assert isinstance(result, ModelResponse)
        assert result.model_id == "claude-haiku-4-5-20251001"
        assert result.latency_ms > 0
        assert result.input_tokens > 0
        assert result.output_tokens > 0
        assert result.cost_estimate_usd is not None
        assert result.cost_estimate_usd > 0
        if result.error is None:
            assert result.parsed_output is not None
        adapter.close()
