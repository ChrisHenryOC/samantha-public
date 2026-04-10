"""Prediction engine: prompt rendering, model invocation, and response parsing.

Ties the prompt template to the model adapter, forming the complete predict
pipeline: render prompt -> call model -> parse response. Supports both routing
predictions (order state transitions) and query predictions (database queries).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypedDict

from src.models.base import (
    ChatMessage,
    ChatResponse,
    ChatRole,
    ModelAdapter,
    ModelResponse,
)
from src.models.parsing import parse_model_output, strip_code_fences
from src.prediction.prompt_template import (
    render_prompt,
    render_routing_tool_lite_messages,
    render_routing_tool_messages,
)
from src.prediction.query_prompt_template import (
    render_query_prompt,
    render_query_prompt_from_parts,
)
from src.prediction.tool_use_prompt import render_tool_use_messages
from src.simulator.schema import (
    VALID_ANSWER_TYPES,
    DatabaseStateSnapshot,
    QueryScenario,
)
from src.workflow.models import Event, Order, Slide

if TYPE_CHECKING:
    from src.rag.retriever import RagRetriever, RetrievalInfo, RetrievalResult
    from src.tools.executor import ToolExecutor

logger = logging.getLogger(__name__)

# --- Query output TypedDicts ---
# These describe the validated JSON structure returned by parse_query_output.
# Use with cast() or isinstance() checks when accessing parsed_output fields.


class OrderListOutput(TypedDict):
    order_ids: list[str]
    reasoning: str


class OrderStatusOutput(TypedDict):
    order_ids: list[str]
    status_summary: str
    reasoning: str


class ExplanationOutput(TypedDict):
    explanation: str
    reasoning: str


class PrioritizedListOutput(TypedDict):
    order_ids: list[str]
    reasoning: str


# --- Query output schema requirements by answer_type ---


@dataclass(frozen=True)
class _QuerySchema:
    """Schema definition for a single query answer type."""

    required_keys: frozenset[str]
    string_fields: tuple[str, ...]
    list_fields: tuple[str, ...]


_QUERY_SCHEMAS: dict[str, _QuerySchema] = {
    "order_list": _QuerySchema(
        required_keys=frozenset({"order_ids", "reasoning"}),
        string_fields=("reasoning",),
        list_fields=("order_ids",),
    ),
    "order_status": _QuerySchema(
        required_keys=frozenset({"order_ids", "status_summary", "reasoning"}),
        string_fields=("status_summary", "reasoning"),
        list_fields=("order_ids",),
    ),
    "explanation": _QuerySchema(
        required_keys=frozenset({"explanation", "reasoning"}),
        string_fields=("explanation", "reasoning"),
        list_fields=(),
    ),
    "prioritized_list": _QuerySchema(
        required_keys=frozenset({"order_ids", "reasoning"}),
        string_fields=("reasoning",),
        list_fields=("order_ids",),
    ),
}

# Verify schema dict covers exactly the valid answer types.
assert set(_QUERY_SCHEMAS) == VALID_ANSWER_TYPES, (
    f"_QUERY_SCHEMAS keys != VALID_ANSWER_TYPES: {set(_QUERY_SCHEMAS)} != {VALID_ANSWER_TYPES}"
)

# --- Query output type alias ---

type QueryParseResult = tuple[dict[str, Any], None] | tuple[None, str]


def parse_query_output(raw_text: str, answer_type: str) -> QueryParseResult:
    """Parse raw model text as a structured query JSON response.

    Validates that the parsed JSON contains the required keys for the given
    answer_type and that values have the correct types.

    Returns
    -------
    QueryParseResult
        ``(parsed_output, None)`` on success or ``(None, error)`` on failure.
    """
    schema = _QUERY_SCHEMAS.get(answer_type)
    if schema is None:
        return None, f"invalid_answer_type: '{answer_type}' is not a valid answer type"

    cleaned = strip_code_fences(raw_text)
    try:
        parsed = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return None, "malformed_json: model output is not valid JSON"

    if not isinstance(parsed, dict):
        return None, f"wrong_schema: expected JSON object, got {type(parsed).__name__}"

    missing = schema.required_keys - set(parsed)
    if missing:
        return None, f"wrong_schema: missing required keys {sorted(missing)}"

    for field in schema.string_fields:
        if not isinstance(parsed[field], str):
            actual = type(parsed[field]).__name__
            return None, f"wrong_schema: {field} must be a string, got {actual}"

    for field in schema.list_fields:
        if not isinstance(parsed[field], list):
            actual = type(parsed[field]).__name__
            return None, f"wrong_schema: {field} must be a list, got {actual}"
        if not all(isinstance(item, str) for item in parsed[field]):
            return None, f"wrong_schema: {field} elements must be strings"

    return parsed, None


# --- Result dataclasses ---


@dataclass(frozen=True)
class PredictionResult:
    """Result of a routing prediction.

    On success, next_state, applied_rules, flags, and reasoning are populated.
    On failure (malformed JSON, wrong schema, model error), error is set and
    the prediction fields contain default empty values.
    """

    next_state: str | None
    applied_rules: tuple[str, ...]
    flags: tuple[str, ...]
    reasoning: str | None
    raw_response: ModelResponse
    error: str | None = None
    retrieval_info: RetrievalInfo | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.raw_response, ModelResponse):
            raise TypeError(
                f"raw_response must be ModelResponse, got {type(self.raw_response).__name__}"
            )
        if self.error is not None and not isinstance(self.error, str):
            raise TypeError(f"error must be str or None, got {type(self.error).__name__}")
        if self.next_state is not None and not isinstance(self.next_state, str):
            raise TypeError(f"next_state must be str or None, got {type(self.next_state).__name__}")
        if not isinstance(self.applied_rules, tuple):
            raise TypeError(f"applied_rules must be tuple, got {type(self.applied_rules).__name__}")
        for i, rule in enumerate(self.applied_rules):
            if not isinstance(rule, str):
                raise TypeError(f"applied_rules[{i}] must be str, got {type(rule).__name__}")
        if not isinstance(self.flags, tuple):
            raise TypeError(f"flags must be tuple, got {type(self.flags).__name__}")
        for i, flag in enumerate(self.flags):
            if not isinstance(flag, str):
                raise TypeError(f"flags[{i}] must be str, got {type(flag).__name__}")
        if self.reasoning is not None and not isinstance(self.reasoning, str):
            raise TypeError(f"reasoning must be str or None, got {type(self.reasoning).__name__}")
        # Cross-field: error and prediction fields are mutually exclusive.
        if self.error is not None:
            if self.next_state is not None:
                raise ValueError("next_state must be None when error is set")
            if self.applied_rules != ():
                raise ValueError("applied_rules must be empty when error is set")
            if self.flags != ():
                raise ValueError("flags must be empty when error is set")
            if self.reasoning is not None:
                raise ValueError("reasoning must be None when error is set")
            if self.retrieval_info is not None:
                raise ValueError("retrieval_info must be None when error is set")


@dataclass(frozen=True)
class QueryPredictionResult:
    """Result of a query prediction.

    On success, parsed_output contains the validated JSON response dict.
    On failure, error is set and parsed_output is None.
    """

    answer_type: str
    parsed_output: dict[str, Any] | None
    raw_response: ModelResponse
    error: str | None = None
    retrieval_info: RetrievalInfo | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.answer_type, str):
            raise TypeError(f"answer_type must be str, got {type(self.answer_type).__name__}")
        if self.answer_type not in VALID_ANSWER_TYPES:
            raise ValueError(
                f"Invalid answer_type '{self.answer_type}'. "
                f"Must be one of: {sorted(VALID_ANSWER_TYPES)}"
            )
        if not isinstance(self.raw_response, ModelResponse):
            raise TypeError(
                f"raw_response must be ModelResponse, got {type(self.raw_response).__name__}"
            )
        if self.parsed_output is not None and not isinstance(self.parsed_output, dict):
            raise TypeError(
                f"parsed_output must be dict or None, got {type(self.parsed_output).__name__}"
            )
        if self.error is not None and not isinstance(self.error, str):
            raise TypeError(f"error must be str or None, got {type(self.error).__name__}")


@dataclass(frozen=True)
class ToolCallRecord:
    """Audit log entry for a single tool call during tool-use evaluation."""

    tool_name: str
    arguments: dict[str, Any]
    result: str
    turn: int

    def __post_init__(self) -> None:
        if not isinstance(self.tool_name, str) or not self.tool_name:
            raise ValueError("ToolCallRecord.tool_name must be a non-empty string")
        if not isinstance(self.arguments, dict):
            raise TypeError(
                f"ToolCallRecord.arguments must be dict, got {type(self.arguments).__name__}"
            )
        if not isinstance(self.result, str):
            raise TypeError(f"ToolCallRecord.result must be str, got {type(self.result).__name__}")
        if not self.result:
            raise ValueError("ToolCallRecord.result must be a non-empty string")
        if not isinstance(self.turn, int) or isinstance(self.turn, bool):
            raise TypeError(f"ToolCallRecord.turn must be int, got {type(self.turn).__name__}")
        if self.turn < 1:
            raise ValueError(f"ToolCallRecord.turn must be >= 1, got {self.turn}")


@dataclass(frozen=True)
class ToolUseQueryResult:
    """Result of a tool-use query prediction.

    Captures the full audit trail of tool calls, accumulated tokens and
    latency across all turns, and the final parsed answer (or error).
    """

    parsed_output: dict[str, Any] | None
    error: str | None
    tool_calls: tuple[ToolCallRecord, ...]
    turns: int
    total_latency_ms: float | int
    total_input_tokens: int
    total_output_tokens: int
    model_id: str

    def __post_init__(self) -> None:
        if self.parsed_output is not None and not isinstance(self.parsed_output, dict):
            raise TypeError(
                f"parsed_output must be dict or None, got {type(self.parsed_output).__name__}"
            )
        if self.error is not None and not isinstance(self.error, str):
            raise TypeError(f"error must be str or None, got {type(self.error).__name__}")
        if self.error is not None and self.parsed_output is not None:
            raise ValueError(
                "parsed_output and error are mutually exclusive; "
                "set parsed_output=None when error is set"
            )
        if not isinstance(self.tool_calls, tuple):
            raise TypeError(f"tool_calls must be tuple, got {type(self.tool_calls).__name__}")
        for i, tc in enumerate(self.tool_calls):
            if not isinstance(tc, ToolCallRecord):
                raise TypeError(f"tool_calls[{i}] must be ToolCallRecord, got {type(tc).__name__}")
        if not isinstance(self.turns, int) or isinstance(self.turns, bool):
            raise TypeError(f"turns must be int, got {type(self.turns).__name__}")
        if self.turns < 0:
            raise ValueError(f"turns must be non-negative, got {self.turns}")
        if not isinstance(self.total_latency_ms, (int, float)) or isinstance(
            self.total_latency_ms, bool
        ):
            raise TypeError(
                f"total_latency_ms must be int or float, got {type(self.total_latency_ms).__name__}"
            )
        if self.total_latency_ms < 0:
            raise ValueError(f"total_latency_ms must be non-negative, got {self.total_latency_ms}")
        if not isinstance(self.total_input_tokens, int) or isinstance(
            self.total_input_tokens, bool
        ):
            raise TypeError(
                f"total_input_tokens must be int, got {type(self.total_input_tokens).__name__}"
            )
        if self.total_input_tokens < 0:
            raise ValueError(
                f"total_input_tokens must be non-negative, got {self.total_input_tokens}"
            )
        if not isinstance(self.total_output_tokens, int) or isinstance(
            self.total_output_tokens, bool
        ):
            raise TypeError(
                f"total_output_tokens must be int, got {type(self.total_output_tokens).__name__}"
            )
        if self.total_output_tokens < 0:
            raise ValueError(
                f"total_output_tokens must be non-negative, got {self.total_output_tokens}"
            )
        if not isinstance(self.model_id, str) or not self.model_id:
            raise ValueError("model_id must be a non-empty string")


@dataclass(frozen=True)
class ToolUseRoutingResult:
    """Result of a tool-assisted routing prediction.

    Extends the standard routing result with tool call audit trail.
    """

    next_state: str | None
    applied_rules: tuple[str, ...]
    flags: tuple[str, ...]
    reasoning: str | None
    error: str | None
    tool_calls: tuple[ToolCallRecord, ...]
    turns: int
    total_latency_ms: float | int
    total_input_tokens: int
    total_output_tokens: int
    model_id: str

    def __post_init__(self) -> None:
        if self.next_state is not None and not isinstance(self.next_state, str):
            raise TypeError(f"next_state must be str or None, got {type(self.next_state).__name__}")
        if not isinstance(self.applied_rules, tuple):
            raise TypeError(f"applied_rules must be tuple, got {type(self.applied_rules).__name__}")
        if not isinstance(self.flags, tuple):
            raise TypeError(f"flags must be tuple, got {type(self.flags).__name__}")
        if self.error is not None and not isinstance(self.error, str):
            raise TypeError(f"error must be str or None, got {type(self.error).__name__}")
        if self.error is not None and self.next_state is not None:
            raise ValueError("error and next_state are mutually exclusive")
        if not isinstance(self.tool_calls, tuple):
            raise TypeError(f"tool_calls must be tuple, got {type(self.tool_calls).__name__}")
        if not isinstance(self.turns, int) or isinstance(self.turns, bool):
            raise TypeError(f"turns must be int, got {type(self.turns).__name__}")
        if self.turns < 0:
            raise ValueError(f"turns must be non-negative, got {self.turns}")
        if not isinstance(self.total_latency_ms, (int, float)) or isinstance(
            self.total_latency_ms, bool
        ):
            raise TypeError(
                f"total_latency_ms must be int or float, got {type(self.total_latency_ms).__name__}"
            )
        if not isinstance(self.model_id, str) or not self.model_id:
            raise ValueError("model_id must be a non-empty string")


# --- Prediction engine ---


class PredictionEngine:
    """Orchestrates the predict pipeline: render prompt, call model, parse response.

    Accepts a ``ModelAdapter`` instance and exposes ``predict_routing`` for
    order state transitions and ``predict_query`` for database queries.
    """

    def __init__(self, adapter: ModelAdapter) -> None:
        if not isinstance(adapter, ModelAdapter):
            raise TypeError(f"adapter must be a ModelAdapter, got {type(adapter).__name__}")
        self._adapter = adapter

    def _make_error_response(self, error: str) -> ModelResponse:
        """Build a ModelResponse for errors that occur before model invocation."""
        return ModelResponse(
            raw_text=f"<{error.split(':')[0]}>",
            parsed_output=None,
            latency_ms=0,
            input_tokens=0,
            output_tokens=0,
            cost_estimate_usd=None,
            model_id=self._adapter.model_id,
            error=error,
        )

    def _routing_error(self, response: ModelResponse, error: str) -> PredictionResult:
        """Build a PredictionResult for any error condition."""
        return PredictionResult(
            next_state=None,
            applied_rules=(),
            flags=(),
            reasoning=None,
            raw_response=response,
            error=error,
        )

    def _query_error(
        self, response: ModelResponse, error: str, answer_type: str
    ) -> QueryPredictionResult:
        """Build a QueryPredictionResult for any error condition."""
        return QueryPredictionResult(
            answer_type=answer_type,
            parsed_output=None,
            raw_response=response,
            error=error,
        )

    @property
    def model_id(self) -> str:
        """Model identifier from the underlying adapter."""
        return self._adapter.model_id

    @property
    def provider(self) -> str:
        """Provider name from the underlying adapter."""
        return self._adapter.provider

    def predict_routing(
        self,
        order: Order,
        slides: list[Slide],
        event: Event,
        *,
        full_context: bool = False,
        rag_retriever: RagRetriever | None = None,
        prompt_extras: frozenset[str] = frozenset(),
    ) -> PredictionResult:
        """Run the routing prediction pipeline.

        Renders the routing prompt, calls the model, and parses the response
        into a structured ``PredictionResult``.

        Three context modes (priority order):

        1. ``rag_retriever`` provided: retrieve relevant chunks and use as
           context (Phase 5 RAG mode). ``full_context`` is ignored.
        2. ``full_context=True``: include all rules (Phase 4 baseline).
        3. Default: rules filtered to current workflow step only.

        Args:
            order: Current order state.
            slides: All slides for this order.
            event: The triggering event.
            full_context: If True, include all rules regardless of workflow
                step. Defaults to False (filtered to current step only).
            rag_retriever: If provided, use RAG retrieval for context.
            prompt_extras: Optional set of extra prompt sections to include
                (e.g., ``state_sequence``, ``retry_clarification``,
                ``few_shot``).

        Returns:
            A ``PredictionResult`` with parsed fields on success or an error
            description on failure. Never raises for model or parse failures.
        """
        ctx = f"(order={order.order_id}, model={self.model_id})"
        retrieval_info: RetrievalInfo | None = None
        rag_context: list[RetrievalResult] | None = None

        try:
            if rag_retriever is not None:
                rag_context, retrieval_info = rag_retriever.retrieve_for_routing(
                    current_state=order.current_state,
                    event_type=event.event_type,
                    event_data=event.event_data,
                )
                if not rag_context:
                    logger.warning(
                        "RAG retrieval returned no chunks for %s %s; "
                        "prompt will contain structured rules only",
                        event.event_type,
                        ctx,
                    )
        except Exception as exc:
            error_msg = f"rag_retrieval_error: {type(exc).__name__}: {exc}"
            return self._routing_error(self._make_error_response(error_msg), f"{error_msg} {ctx}")

        try:
            prompt = render_prompt(
                order,
                slides,
                event,
                full_context=full_context,
                rag_context=rag_context,
                prompt_extras=prompt_extras,
            )
        except Exception as exc:
            error_msg = f"prompt_error: {type(exc).__name__}: {exc}"
            return self._routing_error(self._make_error_response(error_msg), f"{error_msg} {ctx}")

        try:
            response = self._adapter.predict(prompt)
        except Exception as exc:
            error_msg = f"adapter_error: {type(exc).__name__}: {exc}"
            return self._routing_error(self._make_error_response(error_msg), f"{error_msg} {ctx}")

        if response.error is not None:
            return self._routing_error(response, f"model_error: {response.error} {ctx}")

        parsed, error = parse_model_output(response.raw_text)
        if parsed is None:
            return self._routing_error(response, f"{error} {ctx}")

        return PredictionResult(
            next_state=parsed["next_state"],
            applied_rules=tuple(parsed["applied_rules"]),
            flags=tuple(parsed["flags"]),
            reasoning=parsed["reasoning"],
            raw_response=response,
            retrieval_info=retrieval_info,
        )

    def predict_query(
        self,
        scenario: QueryScenario,
        *,
        rag_retriever: RagRetriever | None = None,
    ) -> QueryPredictionResult:
        """Run the query prediction pipeline from a QueryScenario.

        Renders the query prompt, calls the model, and parses the response
        into a structured ``QueryPredictionResult``.

        Args:
            scenario: The query scenario containing database state, query,
                and expected output (used for answer_type).
            rag_retriever: If provided, use RAG retrieval for workflow
                reference context.

        Returns:
            A ``QueryPredictionResult`` with parsed output on success or an
            error description on failure. Never raises for model or parse
            failures.
        """
        answer_type = scenario.expected_output.answer_type
        ctx = f"(scenario={scenario.scenario_id}, model={self.model_id})"
        retrieval_info: RetrievalInfo | None = None
        rag_context: list[RetrievalResult] | None = None

        try:
            if rag_retriever is not None:
                rag_context, retrieval_info = rag_retriever.retrieve_for_query(scenario.query)
        except Exception as exc:
            error_msg = f"rag_retrieval_error: {type(exc).__name__}: {exc}"
            return self._query_error(
                self._make_error_response(error_msg),
                f"{error_msg} {ctx}",
                answer_type,
            )

        try:
            prompt = render_query_prompt(scenario, rag_context=rag_context)
        except Exception as exc:
            error_msg = f"prompt_error: {type(exc).__name__}: {exc}"
            return self._query_error(
                self._make_error_response(error_msg),
                f"{error_msg} {ctx}",
                answer_type,
            )
        return self._predict_query_impl(
            prompt,
            answer_type,
            context=f"scenario={scenario.scenario_id}",
            retrieval_info=retrieval_info,
        )

    def predict_query_from_parts(
        self,
        database_state: DatabaseStateSnapshot,
        query: str,
        answer_type: str,
    ) -> QueryPredictionResult:
        """Run the query prediction pipeline from individual components.

        Unlike ``predict_query``, this method does not support RAG retrieval.
        Use ``predict_query`` with a ``rag_retriever`` parameter for RAG mode.

        Args:
            database_state: Database state snapshot with orders and slides.
            query: The natural language question.
            answer_type: Expected answer type (order_list, order_status,
                explanation, prioritized_list).

        Returns:
            A ``QueryPredictionResult`` with parsed output on success or an
            error description on failure. Never raises for model or parse
            failures.

        Raises:
            ValueError: If answer_type is not a valid answer type or query
                is empty (programming errors, not model failures).
            TypeError: If database_state or query have wrong types.
        """
        if answer_type not in VALID_ANSWER_TYPES:
            valid = ", ".join(f"'{v}'" for v in sorted(VALID_ANSWER_TYPES))
            raise ValueError(f"Invalid answer_type '{answer_type}'. Must be one of: {valid}")
        prompt = render_query_prompt_from_parts(database_state, query, answer_type)
        return self._predict_query_impl(prompt, answer_type, context=None)

    def _predict_query_impl(
        self,
        prompt: str,
        answer_type: str,
        *,
        context: str | None,
        retrieval_info: RetrievalInfo | None = None,
    ) -> QueryPredictionResult:
        """Shared implementation for query prediction."""
        ctx = f"({context}, model={self.model_id})" if context else f"(model={self.model_id})"

        try:
            response = self._adapter.predict(prompt)
        except Exception as exc:
            error_msg = f"adapter_error: {type(exc).__name__}: {exc}"
            return self._query_error(
                self._make_error_response(error_msg),
                f"{error_msg} {ctx}",
                answer_type,
            )

        # The adapter always attempts routing-schema parsing, so
        # wrong_schema errors are expected for query responses. Only treat
        # transport/model-level errors (connection, timeout, HTTP, empty
        # response, auth) as fatal here.
        if response.error is not None and not response.error.startswith("wrong_schema:"):
            return self._query_error(response, f"model_error: {response.error} {ctx}", answer_type)

        parsed, error = parse_query_output(response.raw_text, answer_type)
        if error is not None:
            return self._query_error(response, f"{error} {ctx}", answer_type)

        return QueryPredictionResult(
            answer_type=answer_type,
            parsed_output=parsed,
            raw_response=response,
            retrieval_info=retrieval_info,
        )

    # --- Tool-use prediction ---

    _MAX_QUERY_TOOL_TURNS = 10
    _MAX_ROUTING_TOOL_TURNS = 20

    def _tool_use_result(
        self,
        *,
        parsed_output: dict[str, Any] | None,
        error: str | None,
        tool_calls: list[ToolCallRecord],
        turns: int,
        total_latency_ms: float,
        total_input_tokens: int,
        total_output_tokens: int,
    ) -> ToolUseQueryResult:
        """Build a ToolUseQueryResult with current accumulated state."""
        return ToolUseQueryResult(
            parsed_output=parsed_output,
            error=error,
            tool_calls=tuple(tool_calls),
            turns=turns,
            total_latency_ms=total_latency_ms,
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
            model_id=self._adapter.model_id,
        )

    def predict_query_with_tools(
        self,
        scenario: QueryScenario,
        executor: ToolExecutor,
        tool_defs: list[dict[str, Any]],
    ) -> ToolUseQueryResult:
        """Run the tool-use query prediction pipeline.

        Manages a multi-turn conversation loop: the model calls tools to
        gather data, the engine executes them and feeds results back,
        until the model produces a final text answer or the turn limit
        is reached.

        Args:
            scenario: The query scenario (used for query text and answer_type).
            executor: ToolExecutor operating on the scenario's database state.
            tool_defs: Tool definitions in OpenAI function-calling format.

        Returns:
            A ``ToolUseQueryResult`` with parsed output on success or an
            error description on failure. Never raises for model, parse,
            or executor failures.
        """
        answer_type = scenario.expected_output.answer_type
        ctx = f"(scenario={scenario.scenario_id}, model={self.model_id})"

        try:
            system_msg, user_msg = render_tool_use_messages(scenario.query, answer_type)
        except Exception as exc:
            error_msg = f"prompt_error: {type(exc).__name__}: {exc}"
            return self._tool_use_result(
                parsed_output=None,
                error=f"{error_msg} {ctx}",
                tool_calls=[],
                turns=0,
                total_latency_ms=0,
                total_input_tokens=0,
                total_output_tokens=0,
            )

        messages: list[ChatMessage] = [system_msg, user_msg]
        all_tool_calls: list[ToolCallRecord] = []
        total_latency_ms: float = 0
        total_input_tokens = 0
        total_output_tokens = 0

        for turn in range(1, self._MAX_QUERY_TOOL_TURNS + 1):
            try:
                response: ChatResponse = self._adapter.chat(messages, tools=tool_defs)
            except Exception as exc:
                error_msg = f"adapter_error: {type(exc).__name__}: {exc}"
                return self._tool_use_result(
                    parsed_output=None,
                    error=f"{error_msg} {ctx}",
                    tool_calls=all_tool_calls,
                    turns=turn,
                    total_latency_ms=total_latency_ms,
                    total_input_tokens=total_input_tokens,
                    total_output_tokens=total_output_tokens,
                )

            total_latency_ms += response.latency_ms
            total_input_tokens += response.input_tokens
            total_output_tokens += response.output_tokens

            if response.error is not None:
                return self._tool_use_result(
                    parsed_output=None,
                    error=f"model_error: {response.error} {ctx}",
                    tool_calls=all_tool_calls,
                    turns=turn,
                    total_latency_ms=total_latency_ms,
                    total_input_tokens=total_input_tokens,
                    total_output_tokens=total_output_tokens,
                )

            msg = response.message

            # Model returned tool calls — execute and continue loop
            if msg.tool_calls:
                messages.append(msg)
                for tc in msg.tool_calls:
                    try:
                        result_str = executor.execute(tc.function_name, tc.arguments)
                    except Exception as exc:
                        error_msg = f"executor_error: {type(exc).__name__}: {exc}"
                        logger.warning("Tool execution failed: %s %s", error_msg, ctx)
                        return self._tool_use_result(
                            parsed_output=None,
                            error=f"{error_msg} {ctx}",
                            tool_calls=all_tool_calls,
                            turns=turn,
                            total_latency_ms=total_latency_ms,
                            total_input_tokens=total_input_tokens,
                            total_output_tokens=total_output_tokens,
                        )
                    all_tool_calls.append(
                        ToolCallRecord(
                            tool_name=tc.function_name,
                            arguments=tc.arguments,
                            result=result_str,
                            turn=turn,
                        )
                    )
                    messages.append(
                        ChatMessage(
                            role=ChatRole.TOOL,
                            content=result_str,
                            tool_call_id=tc.id,
                        )
                    )
                continue

            # Model returned text content — parse as final answer
            if msg.content is not None:
                parsed, error = parse_query_output(msg.content, answer_type)
                if error is not None:
                    return self._tool_use_result(
                        parsed_output=None,
                        error=f"{error} {ctx}",
                        tool_calls=all_tool_calls,
                        turns=turn,
                        total_latency_ms=total_latency_ms,
                        total_input_tokens=total_input_tokens,
                        total_output_tokens=total_output_tokens,
                    )
                return self._tool_use_result(
                    parsed_output=parsed,
                    error=None,
                    tool_calls=all_tool_calls,
                    turns=turn,
                    total_latency_ms=total_latency_ms,
                    total_input_tokens=total_input_tokens,
                    total_output_tokens=total_output_tokens,
                )

            # Neither tool calls nor content — empty response
            return self._tool_use_result(
                parsed_output=None,
                error=f"empty_response: model returned no content or tool calls {ctx}",
                tool_calls=all_tool_calls,
                turns=turn,
                total_latency_ms=total_latency_ms,
                total_input_tokens=total_input_tokens,
                total_output_tokens=total_output_tokens,
            )

        # Max turns exceeded
        logger.warning(
            "Tool-use loop reached %d turns without converging %s",
            self._MAX_QUERY_TOOL_TURNS,
            ctx,
        )
        return self._tool_use_result(
            parsed_output=None,
            error=f"max_turns_exceeded: reached {self._MAX_QUERY_TOOL_TURNS} turns {ctx}",
            tool_calls=all_tool_calls,
            turns=self._MAX_QUERY_TOOL_TURNS,
            total_latency_ms=total_latency_ms,
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
        )

    # --- Tool-assisted routing prediction ---

    def _routing_tool_result(
        self,
        *,
        next_state: str | None,
        applied_rules: tuple[str, ...],
        flags: tuple[str, ...],
        reasoning: str | None,
        error: str | None,
        tool_calls: list[ToolCallRecord],
        turns: int,
        total_latency_ms: float,
        total_input_tokens: int,
        total_output_tokens: int,
    ) -> ToolUseRoutingResult:
        return ToolUseRoutingResult(
            next_state=next_state,
            applied_rules=applied_rules,
            flags=flags,
            reasoning=reasoning,
            error=error,
            tool_calls=tuple(tool_calls),
            turns=turns,
            total_latency_ms=total_latency_ms,
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
            model_id=self._adapter.model_id,
        )

    def predict_routing_with_tools(
        self,
        order: Order,
        slides: list[Slide],
        event: Event,
        executor: ToolExecutor,
        tool_defs: list[dict[str, Any]],
        *,
        prompt_extras: frozenset[str] = frozenset(),
    ) -> ToolUseRoutingResult:
        """Run tool-assisted routing prediction.

        Multi-turn loop: the model calls tools for deterministic checks,
        the engine executes them and feeds results back, until the model
        produces a final JSON routing answer.

        Args:
            order: Current order state.
            slides: All slides for this order.
            event: The triggering event.
            executor: ToolExecutor for running tool calls.
            tool_defs: Routing tool definitions in OpenAI format.
            prompt_extras: Prompt extras (skills, etc.).

        Returns:
            A ``ToolUseRoutingResult`` with routing fields + tool audit trail.
        """
        ctx = f"(order={order.order_id}, model={self.model_id})"

        try:
            renderer = (
                render_routing_tool_lite_messages
                if "routing_tools_lite" in prompt_extras
                else render_routing_tool_messages
            )
            system_msg, user_msg = renderer(
                order,
                slides,
                event,
                prompt_extras=prompt_extras,
            )
        except Exception as exc:
            error_msg = f"prompt_error: {type(exc).__name__}: {exc}"
            return self._routing_tool_result(
                next_state=None,
                applied_rules=(),
                flags=(),
                reasoning=None,
                error=f"{error_msg} {ctx}",
                tool_calls=[],
                turns=0,
                total_latency_ms=0,
                total_input_tokens=0,
                total_output_tokens=0,
            )

        # Build allowed tool name set for validation (security: prevent
        # text-parsed tool calls from bypassing tool_defs scope).
        allowed_tools = {
            td["function"]["name"]
            for td in tool_defs
            if "function" in td and "name" in td["function"]
        }

        messages: list[ChatMessage] = [system_msg, user_msg]
        all_tool_calls: list[ToolCallRecord] = []
        total_latency_ms: float = 0
        total_input_tokens = 0
        total_output_tokens = 0

        for turn in range(1, self._MAX_ROUTING_TOOL_TURNS + 1):
            try:
                response: ChatResponse = self._adapter.chat(messages, tools=tool_defs)
            except Exception as exc:
                error_msg = f"adapter_error: {type(exc).__name__}: {exc}"
                return self._routing_tool_result(
                    next_state=None,
                    applied_rules=(),
                    flags=(),
                    reasoning=None,
                    error=f"{error_msg} {ctx}",
                    tool_calls=all_tool_calls,
                    turns=turn,
                    total_latency_ms=total_latency_ms,
                    total_input_tokens=total_input_tokens,
                    total_output_tokens=total_output_tokens,
                )

            total_latency_ms += response.latency_ms
            total_input_tokens += response.input_tokens
            total_output_tokens += response.output_tokens

            if response.error is not None:
                return self._routing_tool_result(
                    next_state=None,
                    applied_rules=(),
                    flags=(),
                    reasoning=None,
                    error=f"model_error: {response.error} {ctx}",
                    tool_calls=all_tool_calls,
                    turns=turn,
                    total_latency_ms=total_latency_ms,
                    total_input_tokens=total_input_tokens,
                    total_output_tokens=total_output_tokens,
                )

            msg = response.message

            # Model returned tool calls — validate, execute, and continue
            if msg.tool_calls:
                messages.append(msg)
                for tc in msg.tool_calls:
                    if tc.function_name not in allowed_tools:
                        logger.warning(
                            "Tool %r not in allowed set %s %s",
                            tc.function_name,
                            sorted(allowed_tools),
                            ctx,
                        )
                        result_str = json.dumps({"error": f"Unknown tool: {tc.function_name}"})
                    else:
                        try:
                            result_str = executor.execute(tc.function_name, tc.arguments)
                        except Exception as exc:
                            error_msg = f"executor_error: {type(exc).__name__}: {exc}"
                            logger.warning("Tool execution failed: %s %s", error_msg, ctx)
                            return self._routing_tool_result(
                                next_state=None,
                                applied_rules=(),
                                flags=(),
                                reasoning=None,
                                error=f"{error_msg} {ctx}",
                                tool_calls=all_tool_calls,
                                turns=turn,
                                total_latency_ms=total_latency_ms,
                                total_input_tokens=total_input_tokens,
                                total_output_tokens=total_output_tokens,
                            )
                    all_tool_calls.append(
                        ToolCallRecord(
                            tool_name=tc.function_name,
                            arguments=tc.arguments,
                            result=result_str,
                            turn=turn,
                        )
                    )
                    messages.append(
                        ChatMessage(
                            role=ChatRole.TOOL,
                            content=result_str,
                            tool_call_id=tc.id,
                        )
                    )
                continue

            # Model returned text — parse as routing JSON
            if msg.content is not None:
                parsed, error = parse_model_output(msg.content)
                if parsed is None:
                    return self._routing_tool_result(
                        next_state=None,
                        applied_rules=(),
                        flags=(),
                        reasoning=None,
                        error=f"{error} {ctx}",
                        tool_calls=all_tool_calls,
                        turns=turn,
                        total_latency_ms=total_latency_ms,
                        total_input_tokens=total_input_tokens,
                        total_output_tokens=total_output_tokens,
                    )
                return self._routing_tool_result(
                    next_state=parsed["next_state"],
                    applied_rules=tuple(parsed["applied_rules"]),
                    flags=tuple(parsed["flags"]),
                    reasoning=parsed["reasoning"],
                    error=None,
                    tool_calls=all_tool_calls,
                    turns=turn,
                    total_latency_ms=total_latency_ms,
                    total_input_tokens=total_input_tokens,
                    total_output_tokens=total_output_tokens,
                )

            # Neither — empty response
            return self._routing_tool_result(
                next_state=None,
                applied_rules=(),
                flags=(),
                reasoning=None,
                error=f"empty_response: no content or tool calls {ctx}",
                tool_calls=all_tool_calls,
                turns=turn,
                total_latency_ms=total_latency_ms,
                total_input_tokens=total_input_tokens,
                total_output_tokens=total_output_tokens,
            )

        # Max turns exceeded
        logger.warning(
            "Routing tool-use loop reached %d turns %s",
            self._MAX_ROUTING_TOOL_TURNS,
            ctx,
        )
        return self._routing_tool_result(
            next_state=None,
            applied_rules=(),
            flags=(),
            reasoning=None,
            error=f"max_turns_exceeded: {self._MAX_ROUTING_TOOL_TURNS} turns {ctx}",
            tool_calls=all_tool_calls,
            turns=self._MAX_ROUTING_TOOL_TURNS,
            total_latency_ms=total_latency_ms,
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
        )
