"""Base classes for the model abstraction layer.

Defines ``ModelResponse`` (frozen dataclass returned by every adapter),
chat-related dataclasses (``ToolCall``, ``ChatMessage``, ``ChatResponse``)
for multi-turn tool-calling conversations, and ``ModelAdapter`` (abstract
base class that all provider adapters implement).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ChatRole(StrEnum):
    """Valid chat message roles."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


def _validate_model_response(obj: ModelResponse) -> None:
    """Validate types and constraints on ModelResponse fields."""
    if not isinstance(obj.raw_text, str):
        raise TypeError(f"raw_text must be str, got {type(obj.raw_text).__name__}")
    if not obj.raw_text:
        raise ValueError("raw_text must be a non-empty string")
    if obj.parsed_output is not None and not isinstance(obj.parsed_output, dict):
        raise TypeError(
            f"parsed_output must be dict or None, got {type(obj.parsed_output).__name__}"
        )
    if not isinstance(obj.latency_ms, (int, float)) or isinstance(obj.latency_ms, bool):
        raise TypeError(f"latency_ms must be int or float, got {type(obj.latency_ms).__name__}")
    if obj.latency_ms < 0:
        raise ValueError(f"latency_ms must be non-negative, got {obj.latency_ms}")
    if not isinstance(obj.input_tokens, int) or isinstance(obj.input_tokens, bool):
        raise TypeError(f"input_tokens must be int, got {type(obj.input_tokens).__name__}")
    if obj.input_tokens < 0:
        raise ValueError(f"input_tokens must be non-negative, got {obj.input_tokens}")
    if not isinstance(obj.output_tokens, int) or isinstance(obj.output_tokens, bool):
        raise TypeError(f"output_tokens must be int, got {type(obj.output_tokens).__name__}")
    if obj.output_tokens < 0:
        raise ValueError(f"output_tokens must be non-negative, got {obj.output_tokens}")
    if obj.cost_estimate_usd is not None:
        if not isinstance(obj.cost_estimate_usd, float):
            raise TypeError(
                "cost_estimate_usd must be float or None, "
                f"got {type(obj.cost_estimate_usd).__name__}"
            )
        if obj.cost_estimate_usd < 0:
            raise ValueError(f"cost_estimate_usd must be non-negative, got {obj.cost_estimate_usd}")
    if not isinstance(obj.model_id, str):
        raise TypeError(f"model_id must be str, got {type(obj.model_id).__name__}")
    if not obj.model_id:
        raise ValueError("model_id must be a non-empty string")
    if obj.error is not None:
        if not isinstance(obj.error, str):
            raise TypeError(f"error must be str or None, got {type(obj.error).__name__}")
        if obj.parsed_output is not None:
            raise ValueError(
                "ModelResponse.error and ModelResponse.parsed_output are mutually exclusive; "
                "set parsed_output=None when error is set"
            )


@dataclass(frozen=True)
class ModelResponse:
    """Structured response returned by every model adapter.

    Frozen to guarantee immutability — once a response is recorded it must
    not be mutated.
    """

    raw_text: str
    parsed_output: dict[str, Any] | None
    latency_ms: float | int
    input_tokens: int
    output_tokens: int
    cost_estimate_usd: float | None
    model_id: str
    error: str | None = None
    timed_out: bool = False

    def __post_init__(self) -> None:
        _validate_model_response(self)


def _validate_tool_call(obj: ToolCall) -> None:
    """Validate types and constraints on ToolCall fields."""
    if not isinstance(obj.id, str) or not obj.id:
        raise ValueError("ToolCall.id must be a non-empty string")
    if not isinstance(obj.function_name, str) or not obj.function_name:
        raise ValueError("ToolCall.function_name must be a non-empty string")
    if not isinstance(obj.arguments, dict):
        raise TypeError(f"ToolCall.arguments must be dict, got {type(obj.arguments).__name__}")


@dataclass(frozen=True)
class ToolCall:
    """A single tool/function call requested by the model."""

    id: str
    function_name: str
    arguments: dict[str, Any]

    def __post_init__(self) -> None:
        _validate_tool_call(self)


def _validate_chat_message(obj: ChatMessage) -> None:
    """Validate types and constraints on ChatMessage fields."""
    if not isinstance(obj.role, ChatRole):
        raise ValueError(f"ChatMessage.role must be a ChatRole, got {obj.role!r}")
    if obj.content is not None and not isinstance(obj.content, str):
        raise TypeError(
            f"ChatMessage.content must be str or None, got {type(obj.content).__name__}"
        )
    if not isinstance(obj.tool_calls, tuple):
        raise TypeError(
            f"ChatMessage.tool_calls must be a tuple, got {type(obj.tool_calls).__name__}"
        )
    for i, tc in enumerate(obj.tool_calls):
        if not isinstance(tc, ToolCall):
            raise TypeError(
                f"ChatMessage.tool_calls[{i}] must be ToolCall, got {type(tc).__name__}"
            )
    if obj.tool_call_id is not None and not isinstance(obj.tool_call_id, str):
        raise TypeError(
            f"ChatMessage.tool_call_id must be str or None, got {type(obj.tool_call_id).__name__}"
        )
    # tool_call_id is required for role="tool"
    if obj.role == ChatRole.TOOL and not obj.tool_call_id:
        raise ValueError("ChatMessage with role='tool' must have a non-empty tool_call_id")
    # assistant messages with tool_calls should not also have content
    # (some APIs allow it, but we enforce mutual exclusivity for clarity)
    if obj.tool_calls and obj.content is not None:
        raise ValueError("ChatMessage with tool_calls must have content=None")


@dataclass(frozen=True)
class ChatMessage:
    """A single message in a multi-turn chat conversation."""

    role: ChatRole
    content: str | None
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None

    def __post_init__(self) -> None:
        _validate_chat_message(self)


def _validate_chat_response(obj: ChatResponse) -> None:
    """Validate types and constraints on ChatResponse fields."""
    if not isinstance(obj.message, ChatMessage):
        raise TypeError(
            f"ChatResponse.message must be ChatMessage, got {type(obj.message).__name__}"
        )
    if not isinstance(obj.latency_ms, (int, float)) or isinstance(obj.latency_ms, bool):
        raise TypeError(
            f"ChatResponse.latency_ms must be int or float, got {type(obj.latency_ms).__name__}"
        )
    if obj.latency_ms < 0:
        raise ValueError(f"ChatResponse.latency_ms must be non-negative, got {obj.latency_ms}")
    if not isinstance(obj.input_tokens, int) or isinstance(obj.input_tokens, bool):
        raise TypeError(
            f"ChatResponse.input_tokens must be int, got {type(obj.input_tokens).__name__}"
        )
    if obj.input_tokens < 0:
        raise ValueError(f"ChatResponse.input_tokens must be non-negative, got {obj.input_tokens}")
    if not isinstance(obj.output_tokens, int) or isinstance(obj.output_tokens, bool):
        raise TypeError(
            f"ChatResponse.output_tokens must be int, got {type(obj.output_tokens).__name__}"
        )
    if obj.output_tokens < 0:
        raise ValueError(
            f"ChatResponse.output_tokens must be non-negative, got {obj.output_tokens}"
        )
    if obj.cost_estimate_usd is not None:
        if not isinstance(obj.cost_estimate_usd, float):
            raise TypeError(
                "ChatResponse.cost_estimate_usd must be float or None, "
                f"got {type(obj.cost_estimate_usd).__name__}"
            )
        if obj.cost_estimate_usd < 0:
            raise ValueError(
                f"ChatResponse.cost_estimate_usd must be non-negative, got {obj.cost_estimate_usd}"
            )
    if not isinstance(obj.model_id, str):
        raise TypeError(f"ChatResponse.model_id must be str, got {type(obj.model_id).__name__}")
    if not obj.model_id:
        raise ValueError("ChatResponse.model_id must be a non-empty string")
    if obj.error is not None and not isinstance(obj.error, str):
        raise TypeError(f"ChatResponse.error must be str or None, got {type(obj.error).__name__}")


@dataclass(frozen=True)
class ChatResponse:
    """Response from a multi-turn chat call, potentially containing tool calls."""

    message: ChatMessage
    latency_ms: float | int
    input_tokens: int
    output_tokens: int
    cost_estimate_usd: float | None
    model_id: str
    error: str | None = None
    timed_out: bool = False

    def __post_init__(self) -> None:
        _validate_chat_response(self)


class ModelAdapter(ABC):
    """Abstract base class for model provider adapters.

    Every adapter (llamacpp, OpenRouter, etc.) must implement ``predict``
    and expose ``model_id`` and ``provider`` properties.
    """

    @abstractmethod
    def predict(self, prompt: str) -> ModelResponse:
        """Send *prompt* to the model and return a structured response."""

    def chat(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResponse:
        """Multi-turn chat with optional tool definitions.

        Adapters override this to opt in to tool-calling. The default
        raises ``NotImplementedError`` so existing adapters are unaffected.
        """
        raise NotImplementedError(f"{self.provider}/{self.model_id} does not support chat()")

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Identifier of the underlying model (e.g. ``llama3.1:8b``)."""

    @property
    @abstractmethod
    def provider(self) -> str:
        """Provider name (e.g. ``llamacpp``, ``openrouter``)."""
