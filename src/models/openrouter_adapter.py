"""OpenRouter adapter for cloud model inference.

Connects to the OpenRouter chat completions API (OpenAI-compatible) to run
inference on Claude models. Cloud models serve as ceiling benchmarks to
contextualize local model performance. Failures are categorized but never
retried — they are returned as-is for the evaluation harness to score.

Note: This adapter transmits prompts to OpenRouter's cloud API over HTTPS.
Prompts may contain PHI-equivalent specimen metadata. Use only with
synthetic test data for benchmarking — never with real patient data.

Requires the ``OPENROUTER_API_KEY`` environment variable to be set.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import time
from typing import Any

import httpx

from src.models.base import (
    ChatMessage,
    ChatResponse,
    ChatRole,
    ModelAdapter,
    ModelResponse,
    ToolCall,
)
from src.models.config import ModelConfig
from src.models.parsing import parse_model_output

_logger = logging.getLogger(__name__)

_BASE_URL = "https://openrouter.ai/api/v1"

# --- Sentinel constants for error raw_text fields ---

_SENTINEL_AUTH_ERROR = "<auth_error>"
_SENTINEL_CONNECTION_ERROR = "<connection_error>"
_SENTINEL_RATE_LIMIT = "<rate_limit>"
_SENTINEL_TIMEOUT = "<timeout>"
_SENTINEL_HTTP_ERROR = "<http_error>"
_SENTINEL_TRANSPORT_ERROR = "<transport_error>"
_SENTINEL_INVALID_JSON = "<invalid_json>"
_SENTINEL_EMPTY_RESPONSE = "<empty_response>"

# --- Model ID mapping ---
#
# Claude models need translation from Anthropic-native IDs to OpenRouter
# slugs. Open-weight models already use OpenRouter's slug format and are
# listed in _KNOWN_SLUGS as a whitelist. resolve_openrouter_model()
# rejects any model ID not in either collection.

_MODEL_ID_TRANSLATIONS: dict[str, str] = {
    # Claude ceiling benchmarks (Anthropic-native IDs → OpenRouter slugs)
    "claude-haiku-4-5-20251001": "anthropic/claude-haiku-4-5",
    "claude-sonnet-4-5-20250929": "anthropic/claude-sonnet-4-5",
    "claude-sonnet-4-6-20250514": "anthropic/claude-sonnet-4-6",
    "claude-opus-4-5-20250514": "anthropic/claude-opus-4-5",
    "claude-opus-4-6-20250514": "anthropic/claude-opus-4-6",
}

_KNOWN_SLUGS: frozenset[str] = frozenset(
    {
        # Tier 1: 16GB VRAM candidates
        "qwen/qwen3-8b",
        "microsoft/phi-4",
        # Tier 2: 24GB VRAM candidates
        "qwen/qwen3-32b",
        "mistralai/mistral-small-3.2-24b-instruct",
        "google/gemma-3-27b-it",
        # Tier 3: MoE
        "qwen/qwen3.5-35b-a3b",
    }
)

# --- Cost estimation (USD per million tokens) ---
#
# OpenRouter pricing for all supported models. Claude rates match
# Anthropic's published pricing. Open-weight model rates are from
# OpenRouter's pricing page.

_PRICING: dict[str, tuple[float, float]] = {
    # model_id prefix -> (input_per_mtok, output_per_mtok)
    # Claude ceiling benchmarks
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-opus-4-6": (5.0, 25.0),
    "claude-opus-4-5": (5.0, 25.0),
    # Tier 1
    "qwen/qwen3-8b": (0.05, 0.40),
    "microsoft/phi-4": (0.07, 0.14),
    # Tier 2
    "qwen/qwen3-32b": (0.08, 0.24),
    "mistralai/mistral-small-3.2-24b-instruct": (0.06, 0.18),
    "google/gemma-3-27b-it": (0.03, 0.11),
    # Tier 3
    "qwen/qwen3.5-35b-a3b": (0.16, 1.30),
}

_MAX_ERROR_MSG_LEN = 200


@dataclasses.dataclass(frozen=True)
class RateLimitInfo:
    """Rate limit status from the OpenRouter ``/api/v1/key`` endpoint.

    On success, ``requests_per_interval`` and ``interval_seconds`` are both
    populated (or both ``None`` if the API omits rate limit data). On any
    error (unreachable, non-200, invalid JSON), all optional fields are
    ``None`` and ``label`` describes the failure.
    """

    requests_per_interval: int | None
    interval_seconds: int | None
    label: str

    def __post_init__(self) -> None:
        if not isinstance(self.label, str) or not self.label:
            raise ValueError("RateLimitInfo.label must be a non-empty string")
        for field_name in ("requests_per_interval", "interval_seconds"):
            val = getattr(self, field_name)
            if val is not None:
                if not isinstance(val, int) or isinstance(val, bool):
                    raise TypeError(
                        f"RateLimitInfo.{field_name} must be int or None, got {type(val).__name__}"
                    )
                if val <= 0:
                    raise ValueError(
                        f"RateLimitInfo.{field_name} must be positive or None, got {val}"
                    )


def _parse_int_field(value: Any) -> int | None:
    """Safely convert an API value to int, returning None for non-numeric types."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    if value is not None:
        _logger.warning(
            "Unexpected type for rate limit field: %s (%r)", type(value).__name__, value
        )
    return None


def check_rate_limit(api_key: str) -> RateLimitInfo:
    """Query the OpenRouter key endpoint to get current rate limit status.

    Returns a ``RateLimitInfo`` with parsed rate limit data on success, or a
    fallback with all optional fields ``None`` if the endpoint is unreachable,
    returns HTTP non-200, or returns invalid/unexpected JSON. Callers should
    check ``requests_per_interval is not None`` to detect success.
    """
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(
                f"{_BASE_URL}/key",
                headers={"Authorization": f"Bearer {api_key}"},
            )
    except httpx.HTTPError as exc:
        _logger.warning("Rate limit check failed: %s", exc)
        return RateLimitInfo(
            requests_per_interval=None,
            interval_seconds=None,
            label="unknown (API unreachable)",
        )

    if resp.status_code != 200:
        _logger.warning("Rate limit check returned HTTP %d", resp.status_code)
        return RateLimitInfo(
            requests_per_interval=None,
            interval_seconds=None,
            label=f"unknown (HTTP {resp.status_code})",
        )

    try:
        body: dict[str, Any] = resp.json()
    except (json.JSONDecodeError, ValueError):
        return RateLimitInfo(
            requests_per_interval=None,
            interval_seconds=None,
            label="unknown (invalid JSON)",
        )

    # The /key endpoint returns {"data": {"label": ..., "rate_limit": ..., ...}}
    raw_data = body.get("data")
    data: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}
    raw_rate = data.get("rate_limit")
    rate_limit: dict[str, Any] = raw_rate if isinstance(raw_rate, dict) else {}

    requests_val = rate_limit.get("requests")
    interval_val = rate_limit.get("interval")
    label = data.get("label") if isinstance(data.get("label"), str) else "unknown"

    # Parse interval string (e.g. "10s", "1m") to seconds
    interval_seconds: int | None = None
    if isinstance(interval_val, str):
        interval_val = interval_val.strip()
        if interval_val.endswith("s") and interval_val[:-1].isdigit():
            interval_seconds = int(interval_val[:-1])
        elif interval_val.endswith("m") and interval_val[:-1].isdigit():
            interval_seconds = int(interval_val[:-1]) * 60
        else:
            _logger.warning(
                "Unrecognized rate limit interval format %r — rate warning disabled",
                interval_val,
            )

    # OpenRouter uses -1 to mean "unlimited / no cap".  Normalise negative
    # values to None so downstream callers treat it as "no limit info".
    parsed_requests = _parse_int_field(requests_val)
    if parsed_requests is not None and parsed_requests <= 0:
        parsed_requests = None

    return RateLimitInfo(
        requests_per_interval=parsed_requests,
        interval_seconds=interval_seconds,
        label=label or "unknown",
    )


def _sanitize_error_message(message: str) -> str:
    """Truncate error messages to avoid leaking sensitive details."""
    return message[:_MAX_ERROR_MSG_LEN]


def _estimate_cost(
    model_id: str,
    input_tokens: int,
    output_tokens: int,
) -> float | None:
    """Estimate USD cost based on published per-million-token pricing.

    Returns ``None`` if the model ID is not in the pricing table.
    """
    for prefix, (input_rate, output_rate) in _PRICING.items():
        if model_id.startswith(prefix):
            return input_tokens * input_rate / 1_000_000 + output_tokens * output_rate / 1_000_000
    return None


def resolve_openrouter_model(model_id: str) -> str:
    """Map a config model ID to the OpenRouter model slug.

    Raises ``ValueError`` if the model ID is not recognized.
    """
    if not isinstance(model_id, str) or not model_id:
        raise ValueError(f"model_id must be a non-empty string, got {model_id!r}")
    # Check translation dict first (Claude models), then pass-through whitelist.
    slug = _MODEL_ID_TRANSLATIONS.get(model_id)
    if slug is not None:
        return slug
    if model_id in _KNOWN_SLUGS:
        return model_id
    known = sorted({*_MODEL_ID_TRANSLATIONS, *_KNOWN_SLUGS})
    raise ValueError(f"Unknown model ID for OpenRouter: {model_id!r}. Known IDs: {known}")


def _extract_content(api_response: dict[str, Any]) -> str:
    """Extract message content from OpenAI-compatible response envelope.

    Returns an empty string if the structure is unexpected or content is missing.
    """
    choices = api_response.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return ""

    message = first_choice.get("message")
    if not isinstance(message, dict):
        return ""

    content = message.get("content")
    return content if isinstance(content, str) else ""


class OpenRouterAdapter(ModelAdapter):
    """Adapter for models served by the OpenRouter chat completions API.

    Parameters
    ----------
    config:
        Validated model configuration (provider must be ``"openrouter"``).
    timeout_seconds:
        Maximum seconds to wait for a response.
    api_key:
        OpenRouter API key. Defaults to ``OPENROUTER_API_KEY`` env var.
    """

    def __init__(
        self,
        config: ModelConfig,
        *,
        timeout_seconds: int = 120,
        api_key: str | None = None,
    ) -> None:
        if config.provider != "openrouter":
            raise ValueError(
                f"OpenRouterAdapter requires provider='openrouter', got {config.provider!r}"
            )
        self._config = config
        self._timeout_seconds = timeout_seconds
        self._openrouter_model = resolve_openrouter_model(config.model_id)

        if _estimate_cost(config.model_id, 1, 1) is None:
            raise ValueError(
                f"No pricing data for model {config.model_id!r}. "
                "Add an entry to _PRICING in openrouter_adapter.py."
            )

        resolved_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not resolved_key:
            raise ValueError(
                "OpenRouterAdapter requires an API key: pass api_key= or "
                "set the OPENROUTER_API_KEY environment variable"
            )
        self._client = httpx.Client(
            base_url=_BASE_URL,
            timeout=float(timeout_seconds),
            headers={
                "Authorization": f"Bearer {resolved_key}",
                "Content-Type": "application/json",
            },
        )

    def close(self) -> None:
        """Close the underlying HTTP client and release resources."""
        self._client.close()

    @property
    def model_id(self) -> str:
        return self._config.model_id

    @property
    def provider(self) -> str:
        return "openrouter"

    def _error_response(
        self,
        raw_text: str,
        latency_ms: float,
        error: str,
        *,
        timed_out: bool = False,
    ) -> ModelResponse:
        """Build a zero-token error ModelResponse."""
        return ModelResponse(
            raw_text=raw_text,
            parsed_output=None,
            latency_ms=latency_ms,
            input_tokens=0,
            output_tokens=0,
            cost_estimate_usd=None,
            model_id=self._config.model_id,
            error=error,
            timed_out=timed_out,
        )

    def predict(self, prompt: str) -> ModelResponse:
        """Send *prompt* to OpenRouter and return a structured response."""
        payload: dict[str, Any] = {
            "model": self._openrouter_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self._config.temperature,
            "max_tokens": self._config.max_tokens,
            # Disable thinking/reasoning mode so models return only the
            # requested JSON output. Without this, models like Qwen 3.5
            # generate verbose reasoning tokens that break JSON parsing.
            # Applied globally — OpenRouter ignores this for non-reasoning models.
            "reasoning": {"effort": "none"},
        }

        start = time.monotonic()
        try:
            response = self._client.post("/chat/completions", json=payload)
        except httpx.ConnectError:
            latency_ms = (time.monotonic() - start) * 1000
            return self._error_response(
                _SENTINEL_CONNECTION_ERROR,
                latency_ms,
                "connection_error: OpenRouter API is unreachable",
            )
        except httpx.TimeoutException:
            latency_ms = (time.monotonic() - start) * 1000
            return self._error_response(
                _SENTINEL_TIMEOUT,
                latency_ms,
                f"timeout: model did not respond within {self._timeout_seconds}s",
                timed_out=True,
            )
        except httpx.RequestError as exc:
            latency_ms = (time.monotonic() - start) * 1000
            return self._error_response(
                _SENTINEL_TRANSPORT_ERROR,
                latency_ms,
                f"transport_error: {type(exc).__name__}: {_sanitize_error_message(str(exc))}",
            )

        latency_ms = (time.monotonic() - start) * 1000

        # Handle HTTP-level errors before parsing the body.
        if response.status_code == 401:
            return self._error_response(
                _SENTINEL_AUTH_ERROR,
                latency_ms,
                f"auth_error: {_sanitize_error_message(response.text)}",
            )
        if response.status_code == 429:
            return self._error_response(
                _SENTINEL_RATE_LIMIT,
                latency_ms,
                f"rate_limit: {_sanitize_error_message(response.text)}",
            )
        if response.status_code >= 400:
            return self._error_response(
                _SENTINEL_HTTP_ERROR,
                latency_ms,
                f"http_error: {response.status_code}: {_sanitize_error_message(response.text)}",
            )

        # Parse the OpenAI-compatible response envelope.
        try:
            api_response: dict[str, Any] = response.json()
        except (json.JSONDecodeError, ValueError):
            return self._error_response(
                _SENTINEL_INVALID_JSON,
                latency_ms,
                f"malformed_json: {_sanitize_error_message(response.text or 'empty response')}",
            )

        # Extract token counts from the usage object.  When the API returns
        # malformed values (e.g. strings instead of ints), tokens fall back to
        # zero — evaluation reports will show $0 cost for these responses.
        usage = api_response.get("usage") or {}
        try:
            input_tokens = int(usage.get("prompt_tokens") or 0)
            output_tokens = int(usage.get("completion_tokens") or 0)
        except (TypeError, ValueError) as exc:
            _logger.warning(
                "Malformed token counts from OpenRouter for model %s: %s (usage=%r)",
                self._config.model_id,
                exc,
                usage,
            )
            input_tokens = 0
            output_tokens = 0

        cost = _estimate_cost(self._config.model_id, input_tokens, output_tokens)

        # Extract the model's text from choices[0].message.content.
        raw_text = _extract_content(api_response)

        if not raw_text:
            return ModelResponse(
                raw_text=_SENTINEL_EMPTY_RESPONSE,
                parsed_output=None,
                latency_ms=latency_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_estimate_usd=cost,
                model_id=self._config.model_id,
                error="empty_response: model returned no output",
            )

        # Attempt to parse the model's output as structured JSON.
        parsed_output, error = parse_model_output(raw_text)

        return ModelResponse(
            raw_text=raw_text,
            parsed_output=parsed_output,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_estimate_usd=cost,
            model_id=self._config.model_id,
            error=error,
        )

    @staticmethod
    def _format_chat_messages(messages: list[ChatMessage]) -> list[dict[str, Any]]:
        """Convert ChatMessage list to OpenAI-compatible message format."""
        formatted: list[dict[str, Any]] = []
        for msg in messages:
            entry: dict[str, Any] = {"role": msg.role.value}
            # OpenAI API requires content key even if null
            entry["content"] = msg.content
            if msg.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function_name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in msg.tool_calls
                ]
            if msg.tool_call_id is not None:
                entry["tool_call_id"] = msg.tool_call_id
            formatted.append(entry)
        return formatted

    @staticmethod
    def _parse_tool_calls(raw_tool_calls: list[dict[str, Any]]) -> tuple[ToolCall, ...]:
        """Parse OpenAI-format tool_calls into ToolCall dataclasses."""
        result: list[ToolCall] = []
        for i, raw_tc in enumerate(raw_tool_calls):
            tc_id = raw_tc.get("id", f"call_{i}")
            func = raw_tc.get("function", {})
            name = func.get("name", "")
            raw_args = func.get("arguments", "{}")
            if isinstance(raw_args, str):
                try:
                    arguments = json.loads(raw_args)
                except (json.JSONDecodeError, ValueError):
                    _logger.warning(
                        "Tool call %d has unparseable arguments string, using empty dict",
                        i,
                    )
                    arguments = {}
            elif isinstance(raw_args, dict):
                arguments = raw_args
            else:
                _logger.warning(
                    "Tool call %d has non-string/non-dict arguments (got %s), using empty dict",
                    i,
                    type(raw_args).__name__,
                )
                arguments = {}
            result.append(
                ToolCall(
                    id=tc_id if isinstance(tc_id, str) and tc_id else f"call_{i}",
                    function_name=name,
                    arguments=arguments,
                )
            )
        return tuple(result)

    def _chat_error_response(
        self,
        latency_ms: float,
        error: str,
        *,
        timed_out: bool = False,
    ) -> ChatResponse:
        """Build a zero-token error ChatResponse."""
        return ChatResponse(
            message=ChatMessage(role=ChatRole.ASSISTANT, content=None),
            latency_ms=latency_ms,
            input_tokens=0,
            output_tokens=0,
            cost_estimate_usd=None,
            model_id=self._config.model_id,
            error=error,
            timed_out=timed_out,
        )

    def chat(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResponse:
        """Multi-turn chat with optional tool definitions via OpenRouter."""
        payload: dict[str, Any] = {
            "model": self._openrouter_model,
            "messages": self._format_chat_messages(messages),
            "temperature": self._config.temperature,
            "max_tokens": self._config.max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        start = time.monotonic()
        try:
            response = self._client.post("/chat/completions", json=payload)
        except httpx.ConnectError:
            latency_ms = (time.monotonic() - start) * 1000
            return self._chat_error_response(
                latency_ms,
                "connection_error: OpenRouter API is unreachable",
            )
        except httpx.TimeoutException:
            latency_ms = (time.monotonic() - start) * 1000
            return self._chat_error_response(
                latency_ms,
                f"timeout: model did not respond within {self._timeout_seconds}s",
                timed_out=True,
            )
        except httpx.RequestError as exc:
            latency_ms = (time.monotonic() - start) * 1000
            return self._chat_error_response(
                latency_ms,
                f"transport_error: {type(exc).__name__}: {_sanitize_error_message(str(exc))}",
            )

        latency_ms = (time.monotonic() - start) * 1000

        # Handle HTTP-level errors
        if response.status_code == 401:
            return self._chat_error_response(
                latency_ms,
                f"auth_error: {_sanitize_error_message(response.text)}",
            )
        if response.status_code == 429:
            return self._chat_error_response(
                latency_ms,
                f"rate_limit: {_sanitize_error_message(response.text)}",
            )
        if response.status_code >= 400:
            return self._chat_error_response(
                latency_ms,
                f"http_error: {response.status_code}: {_sanitize_error_message(response.text)}",
            )

        # Parse response envelope
        try:
            api_response: dict[str, Any] = response.json()
        except (json.JSONDecodeError, ValueError):
            return self._chat_error_response(
                latency_ms,
                f"malformed_json: {_sanitize_error_message(response.text or 'empty response')}",
            )

        # Extract token counts
        usage = api_response.get("usage") or {}
        try:
            input_tokens = int(usage.get("prompt_tokens") or 0)
            output_tokens = int(usage.get("completion_tokens") or 0)
        except (TypeError, ValueError) as exc:
            _logger.warning(
                "Malformed token counts from OpenRouter for model %s: %s (usage=%r)",
                self._config.model_id,
                exc,
                usage,
            )
            input_tokens = 0
            output_tokens = 0

        cost = _estimate_cost(self._config.model_id, input_tokens, output_tokens)

        # Check for error body returned with HTTP 200
        api_error = api_response.get("error")
        if isinstance(api_error, dict):
            code = api_error.get("code") or api_error.get("status") or "unknown"
            msg = api_error.get("message") or str(api_error)
            return self._chat_error_response(
                latency_ms,
                f"api_error_{code}: {_sanitize_error_message(str(msg))}",
            )

        # Extract message from choices
        choices = api_response.get("choices")
        if not isinstance(choices, list) or not choices:
            return self._chat_error_response(
                latency_ms,
                "empty_response: model returned no choices",
            )

        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            return self._chat_error_response(
                latency_ms,
                "empty_response: malformed choice",
            )

        raw_message = first_choice.get("message")
        if not isinstance(raw_message, dict):
            return self._chat_error_response(
                latency_ms,
                "empty_response: missing message in choice",
            )

        content = raw_message.get("content")
        if not isinstance(content, str) or not content:
            content = None

        raw_tool_calls = raw_message.get("tool_calls")
        tool_calls: tuple[ToolCall, ...] = ()

        if isinstance(raw_tool_calls, list) and raw_tool_calls:
            try:
                tool_calls = self._parse_tool_calls(raw_tool_calls)
            except (ValueError, TypeError) as exc:
                return self._chat_error_response(
                    latency_ms,
                    f"malformed_tool_call: {exc}",
                )
            # When model returns tool_calls, content should be None
            content = None

        if content is None and not tool_calls:
            # Some models (e.g. Qwen3) return a reasoning field when using
            # thinking mode. Use it as fallback content so the user sees
            # something rather than an empty_response error.
            reasoning = raw_message.get("reasoning")
            if isinstance(reasoning, str) and reasoning.strip():
                _logger.info(
                    "Using reasoning field as fallback content for %s",
                    self._config.model_id,
                )
                content = reasoning.strip()
            else:
                _logger.warning(
                    "Empty response from %s: raw_message keys=%s",
                    self._config.model_id,
                    list(raw_message.keys()),
                )
                return self._chat_error_response(
                    latency_ms,
                    "empty_response: model returned no content or tool calls",
                )

        message = ChatMessage(
            role=ChatRole.ASSISTANT,
            content=content,
            tool_calls=tool_calls,
        )

        return ChatResponse(
            message=message,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_estimate_usd=cost,
            model_id=self._config.model_id,
        )
