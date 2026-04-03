"""llama.cpp adapter for local model inference via llama-server.

Connects to llama-server's OpenAI-compatible HTTP API to run inference
on locally-hosted models. Failures are categorized but never retried —
they are returned as-is for the evaluation harness to score.

Note: ``base_url`` should point to a trusted local endpoint.
Prompts may contain PHI-equivalent specimen metadata transmitted
in plaintext over HTTP.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
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

logger = logging.getLogger(__name__)

# --- Sentinel constants for error raw_text fields ---

_SENTINEL_CONNECTION_ERROR = "<connection_error>"
_SENTINEL_TIMEOUT = "<timeout>"
_SENTINEL_HTTP_ERROR = "<http_error>"
_SENTINEL_TRANSPORT_ERROR = "<transport_error>"
_SENTINEL_INVALID_JSON = "<invalid_json>"
_SENTINEL_EMPTY_RESPONSE = "<empty_response>"


class LlamaCppAdapter(ModelAdapter):
    """Adapter for models served by llama-server (llama.cpp).

    Uses the OpenAI-compatible ``/v1/chat/completions`` endpoint.

    Parameters
    ----------
    config:
        Validated model configuration (provider must be ``"llamacpp"``).
    base_url:
        Base URL for the llama-server API. Defaults to ``http://localhost:8080``.
    timeout_seconds:
        Maximum seconds to wait for a response.
    """

    def __init__(
        self,
        config: ModelConfig,
        *,
        base_url: str = "http://localhost:8080",
        timeout_seconds: int = 120,
    ) -> None:
        if config.provider not in ("llamacpp", "ollama"):
            raise ValueError(
                f"LlamaCppAdapter requires provider='llamacpp' or 'ollama', got {config.provider!r}"
            )
        self._config = config
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=self._timeout_seconds,
        )

    def close(self) -> None:
        """Close the underlying HTTP client and release resources."""
        self._client.close()

    @property
    def model_id(self) -> str:
        return self._config.model_id

    @property
    def provider(self) -> str:
        return "llamacpp"

    def _predict_error_response(
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
        """Send *prompt* to llama-server and return a structured response."""
        # Warn if prompt likely exceeds the configured token limit.
        # Rough heuristic: ~4 chars per token for English text.
        estimated_tokens = len(prompt) // 4
        if estimated_tokens > int(self._config.token_limit * 0.9):
            logger.warning(
                "Prompt may exceed context window: ~%d tokens with token_limit=%d",
                estimated_tokens,
                self._config.token_limit,
            )

        payload: dict[str, Any] = {
            "model": self._config.model_id,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self._config.temperature,
            "max_tokens": self._config.max_tokens,
            "stream": False,
        }

        start = time.monotonic()
        try:
            response = self._client.post("/v1/chat/completions", json=payload)
            response.raise_for_status()
        except httpx.ConnectError:
            latency_ms = (time.monotonic() - start) * 1000
            return self._predict_error_response(
                _SENTINEL_CONNECTION_ERROR,
                latency_ms,
                "connection_error: llama-server is not running or unreachable",
            )
        except httpx.TimeoutException:
            latency_ms = (time.monotonic() - start) * 1000
            return self._predict_error_response(
                _SENTINEL_TIMEOUT,
                latency_ms,
                f"timeout: model did not respond within {self._timeout_seconds}s",
                timed_out=True,
            )
        except httpx.HTTPStatusError as exc:
            latency_ms = (time.monotonic() - start) * 1000
            return self._predict_error_response(
                exc.response.text or _SENTINEL_HTTP_ERROR,
                latency_ms,
                f"http_error: {exc.response.status_code}",
            )
        except httpx.RequestError as exc:
            latency_ms = (time.monotonic() - start) * 1000
            return self._predict_error_response(
                _SENTINEL_TRANSPORT_ERROR,
                latency_ms,
                f"transport_error: {type(exc).__name__}",
            )

        latency_ms = (time.monotonic() - start) * 1000

        # Parse the OpenAI-compatible response envelope.
        try:
            api_response: dict[str, Any] = response.json()
        except (json.JSONDecodeError, ValueError):
            return ModelResponse(
                raw_text=response.text or _SENTINEL_INVALID_JSON,
                parsed_output=None,
                latency_ms=latency_ms,
                input_tokens=0,
                output_tokens=0,
                cost_estimate_usd=None,
                model_id=self._config.model_id,
                error="malformed_json: llama-server returned non-JSON response",
            )

        # Extract text from choices[0].message.content
        # Some models (Qwen3.5 via Ollama) use extended thinking: the
        # reasoning goes into a "reasoning" field and the final answer
        # goes into "content". If the model exhausts max_tokens during
        # thinking, content is empty but reasoning is populated.
        raw_text = _SENTINEL_EMPTY_RESPONSE
        reasoning_text: str | None = None
        choices = api_response.get("choices", [])
        if choices and isinstance(choices[0], dict):
            message = choices[0].get("message", {})
            if isinstance(message, dict):
                content = message.get("content", "")
                if isinstance(content, str) and content:
                    raw_text = content
                # Capture reasoning/thinking tokens if present
                reasoning = message.get("reasoning") or message.get("reasoning_content")
                if isinstance(reasoning, str) and reasoning:
                    reasoning_text = reasoning

        # Extract token counts from usage object
        usage = api_response.get("usage", {})
        try:
            input_tokens = int(usage.get("prompt_tokens") or 0)
            output_tokens = int(usage.get("completion_tokens") or 0)
        except (TypeError, ValueError):
            input_tokens = 0
            output_tokens = 0

        if raw_text == _SENTINEL_EMPTY_RESPONSE:
            # If we have reasoning but no content, the model exhausted
            # max_tokens during thinking before producing its answer.
            if reasoning_text:
                finish_reason = ""
                if choices and isinstance(choices[0], dict):
                    finish_reason = choices[0].get("finish_reason", "")
                logger.warning(
                    "Model %s returned reasoning (%d chars) but no content "
                    "(finish_reason=%s). Increase max_tokens for thinking models.",
                    self._config.model_id,
                    len(reasoning_text),
                    finish_reason,
                )
                return ModelResponse(
                    raw_text=f"<thinking_only>{reasoning_text[:500]}",
                    parsed_output=None,
                    latency_ms=latency_ms,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_estimate_usd=None,
                    model_id=self._config.model_id,
                    error=(
                        "thinking_exhausted: model used all tokens on reasoning "
                        "without producing an answer — increase max_tokens"
                    ),
                )
            return ModelResponse(
                raw_text=_SENTINEL_EMPTY_RESPONSE,
                parsed_output=None,
                latency_ms=latency_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_estimate_usd=None,
                model_id=self._config.model_id,
                error="empty_response: model returned no output",
            )

        parsed_output, error = parse_model_output(raw_text)

        return ModelResponse(
            raw_text=raw_text,
            parsed_output=parsed_output,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_estimate_usd=None,
            model_id=self._config.model_id,
            error=error,
        )

    @staticmethod
    def _format_messages(messages: list[ChatMessage]) -> list[dict[str, Any]]:
        """Convert ChatMessage list to OpenAI message format."""
        formatted: list[dict[str, Any]] = []
        for msg in messages:
            entry: dict[str, Any] = {"role": msg.role.value}
            if msg.content is not None:
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
        """Parse OpenAI-format tool_calls response into ToolCall dataclasses."""
        result: list[ToolCall] = []
        for i, raw_tc in enumerate(raw_tool_calls):
            call_id = raw_tc.get("id", f"call_{i}")
            func = raw_tc.get("function", {})
            name = func.get("name", "")
            raw_args = func.get("arguments", "{}")
            if isinstance(raw_args, str):
                try:
                    arguments = json.loads(raw_args)
                except json.JSONDecodeError:
                    logger.warning(
                        "Tool call %d has unparseable arguments: %s",
                        i,
                        raw_args[:100],
                    )
                    arguments = {}
            elif isinstance(raw_args, dict):
                arguments = raw_args
            else:
                logger.warning(
                    "Tool call %d has unexpected arguments type: %s",
                    i,
                    type(raw_args).__name__,
                )
                arguments = {}
            result.append(ToolCall(id=call_id, function_name=name, arguments=arguments))
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

    def _build_chat_payload(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None = None,
        *,
        stream: bool = False,
    ) -> dict[str, Any]:
        """Build the OpenAI-compatible chat completions request payload."""
        payload: dict[str, Any] = {
            "model": self._config.model_id,
            "messages": self._format_messages(messages),
            "temperature": self._config.temperature,
            "max_tokens": self._config.max_tokens,
            "stream": stream,
        }
        if stream:
            payload["stream_options"] = {"include_usage": True}
        if tools:
            payload["tools"] = tools
        return payload

    def chat(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResponse:
        """Multi-turn chat with optional tool definitions via llama-server."""
        payload = self._build_chat_payload(messages, tools, stream=False)

        start = time.monotonic()
        try:
            response = self._client.post("/v1/chat/completions", json=payload)
            response.raise_for_status()
        except httpx.ConnectError:
            latency_ms = (time.monotonic() - start) * 1000
            return self._chat_error_response(
                latency_ms,
                "connection_error: llama-server is not running or unreachable",
            )
        except httpx.TimeoutException:
            latency_ms = (time.monotonic() - start) * 1000
            return self._chat_error_response(
                latency_ms,
                f"timeout: model did not respond within {self._timeout_seconds}s",
                timed_out=True,
            )
        except httpx.HTTPStatusError as exc:
            latency_ms = (time.monotonic() - start) * 1000
            return self._chat_error_response(
                latency_ms,
                f"http_error: {exc.response.status_code}",
            )
        except httpx.RequestError as exc:
            latency_ms = (time.monotonic() - start) * 1000
            return self._chat_error_response(
                latency_ms,
                f"transport_error: {type(exc).__name__}",
            )

        latency_ms = (time.monotonic() - start) * 1000

        try:
            api_response: dict[str, Any] = response.json()
        except (json.JSONDecodeError, ValueError):
            return self._chat_error_response(
                latency_ms,
                "malformed_json: llama-server returned non-JSON response",
            )

        # Extract token counts from usage object
        usage = api_response.get("usage", {})
        try:
            input_tokens = int(usage.get("prompt_tokens") or 0)
            output_tokens = int(usage.get("completion_tokens") or 0)
        except (TypeError, ValueError) as exc:
            logger.warning(
                "Malformed token counts from llama-server for model %s: %s (response keys=%r)",
                self._config.model_id,
                exc,
                list(api_response.keys()),
            )
            input_tokens = 0
            output_tokens = 0

        # Parse message from choices[0].message
        choices = api_response.get("choices", [])
        if not choices or not isinstance(choices[0], dict):
            return self._chat_error_response(
                latency_ms,
                "empty_response: model returned no choices",
            )

        raw_message = choices[0].get("message", {})
        if not isinstance(raw_message, dict):
            return self._chat_error_response(
                latency_ms,
                "empty_response: model returned no message",
            )

        content = raw_message.get("content")
        if isinstance(content, str) and not content:
            content = None

        # Check for reasoning/thinking tokens (Qwen3.5 via Ollama)
        if content is None:
            reasoning = raw_message.get("reasoning") or raw_message.get("reasoning_content")
            if isinstance(reasoning, str) and reasoning:
                logger.warning(
                    "Model %s returned reasoning but no content in chat(); "
                    "increase max_tokens for thinking models.",
                    self._config.model_id,
                )

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
            content = None

        if content is None and not tool_calls:
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
            cost_estimate_usd=None,
            model_id=self._config.model_id,
        )

    def chat_stream(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None = None,
    ) -> Iterator[str | ChatResponse]:
        """Stream a chat response via SSE, yielding tokens as they arrive.

        Yields:
            str: Individual text tokens as they're generated.
            ChatResponse: Final response at end of stream (may contain
                tool_calls if model requested function calls).
        """
        payload = self._build_chat_payload(messages, tools, stream=True)
        start = time.monotonic()

        try:
            with self._client.stream("POST", "/v1/chat/completions", json=payload) as resp:
                resp.raise_for_status()
                content_parts: list[str] = []
                input_tokens = 0
                output_tokens = 0
                done_received = False
                # Accumulate tool calls across chunks by index
                tool_call_buffers: dict[int, dict[str, Any]] = {}

                for line in resp.iter_lines():
                    if not line:
                        continue
                    # SSE format: lines starting with "data: "
                    data_str = line[6:] if line.startswith("data: ") else line

                    if data_str == "[DONE]":
                        done_received = True
                        break

                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        logger.debug("Skipping non-JSON SSE line: %s", data_str[:100])
                        continue

                    # Extract usage from chunk (may appear in final chunk)
                    chunk_usage = chunk.get("usage")
                    if isinstance(chunk_usage, dict):
                        try:
                            input_tokens = int(chunk_usage.get("prompt_tokens") or 0)
                            output_tokens = int(chunk_usage.get("completion_tokens") or 0)
                        except (TypeError, ValueError) as exc:
                            logger.warning("Malformed stream token counts: %s", exc)

                    choices = chunk.get("choices", [])
                    if not choices:
                        continue

                    delta = choices[0].get("delta", {})

                    # Yield text tokens incrementally
                    token = delta.get("content", "")
                    if token:
                        content_parts.append(token)
                        yield token

                    # Accumulate tool calls incrementally
                    delta_tool_calls = delta.get("tool_calls")
                    if isinstance(delta_tool_calls, list):
                        for tc_delta in delta_tool_calls:
                            idx = tc_delta.get("index", 0)
                            if idx not in tool_call_buffers:
                                tool_call_buffers[idx] = {
                                    "id": tc_delta.get("id", f"call_{idx}"),
                                    "name": "",
                                    "arguments": "",
                                }
                            buf = tool_call_buffers[idx]
                            if tc_delta.get("id"):
                                buf["id"] = tc_delta["id"]
                            func = tc_delta.get("function", {})
                            if func.get("name"):
                                buf["name"] = func["name"]
                            if func.get("arguments"):
                                buf["arguments"] += func["arguments"]

                latency_ms = (time.monotonic() - start) * 1000

                # Build final tool calls from accumulated buffers
                final_tool_calls: tuple[ToolCall, ...] = ()
                if tool_call_buffers:
                    tc_list: list[ToolCall] = []
                    for idx in sorted(tool_call_buffers):
                        buf = tool_call_buffers[idx]
                        try:
                            arguments = json.loads(buf["arguments"]) if buf["arguments"] else {}
                        except json.JSONDecodeError:
                            logger.warning(
                                "Stream tool call %d has unparseable arguments",
                                idx,
                            )
                            arguments = {}
                        tc_list.append(
                            ToolCall(
                                id=buf["id"],
                                function_name=buf["name"] or f"unknown_{idx}",
                                arguments=arguments,
                            )
                        )
                    final_tool_calls = tuple(tc_list)
                    content_parts.clear()

                content = "".join(content_parts) or None
                error = (
                    None
                    if done_received
                    else "stream_interrupted: server closed connection without [DONE]"
                )

                message = ChatMessage(
                    role=ChatRole.ASSISTANT,
                    content=content,
                    tool_calls=final_tool_calls,
                )
                yield ChatResponse(
                    message=message,
                    latency_ms=latency_ms,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_estimate_usd=None,
                    model_id=self._config.model_id,
                    error=error,
                )

        except httpx.ConnectError:
            latency_ms = (time.monotonic() - start) * 1000
            yield self._chat_error_response(
                latency_ms,
                "connection_error: llama-server is not running or unreachable",
            )
        except httpx.HTTPStatusError as exc:
            latency_ms = (time.monotonic() - start) * 1000
            yield self._chat_error_response(
                latency_ms,
                f"http_error: {exc.response.status_code}",
            )
        except httpx.TimeoutException:
            latency_ms = (time.monotonic() - start) * 1000
            yield self._chat_error_response(
                latency_ms,
                f"timeout: model did not respond within {self._timeout_seconds}s",
                timed_out=True,
            )
        except httpx.RequestError as exc:
            latency_ms = (time.monotonic() - start) * 1000
            yield self._chat_error_response(
                latency_ms,
                f"transport_error: {type(exc).__name__}",
            )
