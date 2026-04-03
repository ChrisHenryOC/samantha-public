"""Query prompt template for context-stuffed evaluation.

Renders a prompt that presents a database state snapshot alongside a
natural language query. The model produces a structured JSON answer.
This template uses context stuffing — the full database state is loaded
into the prompt — to isolate LLM comprehension without tool-use mechanics.
"""

from __future__ import annotations

import functools
import json
from typing import TYPE_CHECKING, Any, TypedDict

from src.simulator.schema import DatabaseStateSnapshot, QueryScenario
from src.workflow.state_machine import StateMachine

if TYPE_CHECKING:
    from src.rag.retriever import RetrievalResult

_QUERY_PROMPT_TEMPLATE = """\
You are a laboratory information system assistant for a breast cancer
histology lab. You help lab workers and pathologists by answering
questions about order status and worklists.

## Current Database State

### Orders

{orders_json}

### Slides

{slides_json}

## Workflow Reference

### State Descriptions

{state_reference}

### Flag Definitions

{flag_reference}

## Question

{query}

## Instructions

Answer the question based on the database state above. Use the workflow
reference to understand what each state and flag means.


{answer_type_instructions}Respond with ONLY a JSON object in this exact format, no other text:

{output_format}\
"""

# Output format templates keyed by answer_type.
_OUTPUT_FORMATS: dict[str, str] = {
    "order_list": """\
{{
  "order_ids": ["<order IDs matching the query>"],
  "reasoning": "<brief explanation of why these orders match>"
}}""",
    "order_status": """\
{{
  "order_ids": ["<order ID(s) the question is about>"],
  "status_summary": "<description of current status and next action>",
  "reasoning": "<brief explanation based on state and flags>"
}}""",
    "explanation": """\
{{
  "explanation": "<answer to the question>",
  "reasoning": "<brief explanation of the logic and relevant workflow rules>"
}}""",
    "prioritized_list": """\
{{
  "order_ids": ["<order IDs in priority order, highest priority first>"],
  "reasoning": "<brief explanation of the ranking criteria applied>"
}}""",
}

# Answer-type-specific instructions injected before the output format directive.
_ANSWER_TYPE_INSTRUCTIONS: dict[str, str] = {
    "prioritized_list": """\
Ranking rules — sort all matching orders by these keys in order:
1. Priority: rush (highest) before routine (lowest)
2. Flags: orders WITH flags before orders WITHOUT flags, within the same priority
3. Age: older orders (earlier created_at) before newer orders, within the same group

Apply all three sort keys. For example, given these orders:
  A: rush, no flags, 2025-01-15T10:00  B: rush, FIXATION_WARNING, 2025-01-15T08:00
  C: rush, no flags, 2025-01-14T14:00  D: routine, no flags, 2025-01-13T10:00
Correct ranking: B, C, A, D
  B first: rush + has flag (key 2) beats C and A who have no flags
  C before A: both rush, no flags, but Jan 14 < Jan 15 (key 3)
  D last: routine (key 1)

IMPORTANT: Compare full dates, not just times. Jan 14 is OLDER than Jan 15.

""",
    "order_list": """\
Scan EVERY order in the database state. For each order, check whether it
matches the query criteria based on its current_state and flags. Use the
state descriptions and flag definitions to determine matches — include all
states that fit the query, not just the most obvious one. Do not omit
orders that match a less common state. Include only matching orders.

""",
}


# Workflow phase ordering for state reference presentation.
_PHASE_ORDER: list[str] = [
    "accessioning",
    "sample_prep",
    "he_review",
    "ihc",
    "resulting",
    "terminal",
]


class _StateAnnotation(TypedDict, total=False):
    """Actor who must act and optional grouping label for a workflow state."""

    actor: str  # required — who must act on this state
    group: str  # optional — bench/station grouping label


# State annotations: actor who must act, and grouping labels for common queries.
# "actor" helps answer "who needs to act?" queries.
# "group" labels help answer "which orders are on bench X?" queries.
_STATE_ANNOTATIONS: dict[str, _StateAnnotation] = {
    "ACCESSIONING": {"actor": "system"},
    "ACCEPTED": {"actor": "lab tech"},
    "MISSING_INFO_HOLD": {"actor": "held — waiting for external info"},
    "MISSING_INFO_PROCEED": {"actor": "system"},
    "DO_NOT_PROCESS": {"actor": "system"},
    "SAMPLE_PREP_PROCESSING": {"actor": "lab tech", "group": "sample prep bench"},
    "SAMPLE_PREP_EMBEDDING": {"actor": "lab tech", "group": "sample prep bench"},
    "SAMPLE_PREP_SECTIONING": {"actor": "lab tech", "group": "sample prep bench"},
    "SAMPLE_PREP_QC": {"actor": "lab tech", "group": "sample prep bench"},
    "HE_STAINING": {"actor": "lab tech", "group": "H&E bench"},
    "HE_QC": {"actor": "lab tech", "group": "H&E bench"},
    "PATHOLOGIST_HE_REVIEW": {"actor": "pathologist"},
    "IHC_STAINING": {"actor": "lab tech", "group": "IHC bench"},
    "IHC_QC": {"actor": "lab tech", "group": "IHC bench"},
    "IHC_SCORING": {"actor": "lab tech", "group": "IHC bench"},
    "SUGGEST_FISH_REFLEX": {"actor": "pathologist"},
    "FISH_SEND_OUT": {"actor": "held — waiting for external lab"},
    "RESULTING": {"actor": "system"},
    "RESULTING_HOLD": {"actor": "held — waiting for external info"},
    "PATHOLOGIST_SIGNOUT": {"actor": "pathologist"},
    "REPORT_GENERATION": {"actor": "system"},
    "ORDER_COMPLETE": {"actor": "terminal"},
    "ORDER_TERMINATED": {"actor": "terminal"},
    "ORDER_TERMINATED_QNS": {"actor": "terminal"},
}


@functools.cache
def _format_state_reference(sm: StateMachine) -> str:
    """Format workflow states as a reference table for the prompt.

    Groups states by phase in workflow progression order and shows each
    state's description with actor and group annotations. Cached because
    the StateMachine is a singleton with static config.

    Args:
        sm: StateMachine singleton instance providing state metadata.

    Returns:
        Markdown-formatted string with states grouped by phase, e.g.
        ``**sample_prep**:\\n  - SAMPLE_PREP_PROCESSING: ...``
        ``[actor: lab tech; group: sample prep bench]``.
    """
    states = sm.get_all_states()

    # Group states by phase using the public API.
    phases: dict[str, list[tuple[str, str]]] = {}
    for state_id in sorted(states):
        state_obj = sm.get_state(state_id)
        phases.setdefault(state_obj.phase, []).append((state_id, state_obj.description))

    # Render phases in workflow progression order.
    lines: list[str] = []
    for phase in _PHASE_ORDER:
        if phase in phases:
            lines.append(f"**{phase}**:")
            for state_id, desc in phases[phase]:
                annotation = _STATE_ANNOTATIONS.get(state_id, {})
                actor = annotation.get("actor", "")
                group = annotation.get("group", "")
                suffix_parts: list[str] = []
                if actor:
                    suffix_parts.append(f"actor: {actor}")
                if group:
                    suffix_parts.append(f"group: {group}")
                suffix = f" [{'; '.join(suffix_parts)}]" if suffix_parts else ""
                lines.append(f"  - {state_id}: {desc}{suffix}")
    return "\n".join(lines)


@functools.cache
def _format_flag_definitions(sm: StateMachine) -> str:
    """Format all flag definitions for the workflow reference section.

    Retrieves flag metadata from ``StateMachine.get_flag_vocabulary()``
    and renders it in markdown with effect and cleared_by information.
    Cached because the StateMachine is a singleton with static config.

    Args:
        sm: StateMachine singleton instance providing flag vocabulary.

    Returns:
        Markdown-formatted string of flags, e.g.
        ``- **FLAG_ID**: effect (Cleared by: event)``.
        Returns ``"No flags defined."`` if vocabulary is empty.
    """
    vocab = sm.get_flag_vocabulary()
    if not vocab:
        return "No flags defined."

    lines: list[str] = []
    for flag_id, meta in sorted(vocab.items()):
        effect = meta.get("effect", "No effect description")
        cleared_by = meta.get("cleared_by", "Unknown")
        lines.append(f"- **{flag_id}**: {effect} (Cleared by: {cleared_by})")
    return "\n".join(lines)


def _to_json_str(data: list[dict[str, Any]] | dict[str, Any]) -> str:
    """Serialize data to a formatted JSON string."""
    return json.dumps(data, indent=2)


def get_output_format(answer_type: str) -> str:
    """Return the expected JSON output format for an answer type.

    Raises:
        ValueError: If the answer_type is not recognized.
    """
    fmt = _OUTPUT_FORMATS.get(answer_type)
    if fmt is None:
        valid = ", ".join(f"'{v}'" for v in sorted(_OUTPUT_FORMATS.keys()))
        raise ValueError(f"Unknown answer_type '{answer_type}'. Must be one of: {valid}")
    return fmt


def _format_rag_workflow_reference(chunks: list[RetrievalResult]) -> str:
    """Format retrieved RAG chunks as workflow reference context.

    Args:
        chunks: Retrieved chunks from the RAG pipeline.

    Returns:
        Formatted multi-section string, or a fallback message if empty.
    """
    if not chunks:
        return "No relevant workflow context found."

    lines: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        lines.append(
            f"### Reference {i} (from {chunk.source_file}: {chunk.section_title})\n\n{chunk.text}"
        )
    return "\n\n".join(lines)


def render_query_prompt(
    scenario: QueryScenario,
    *,
    rag_context: list[RetrievalResult] | None = None,
) -> str:
    """Render the complete query prompt for a model invocation.

    Args:
        scenario: The query scenario containing database state, query,
            and expected output (used for answer_type).
        rag_context: If provided, use retrieved chunks as workflow reference
            instead of full state/flag descriptions.

    Returns:
        The fully rendered prompt string with all template variables
        populated.
    """
    return render_query_prompt_from_parts(
        database_state=scenario.database_state,
        query=scenario.query,
        answer_type=scenario.expected_output.answer_type,
        rag_context=rag_context,
    )


def render_query_prompt_from_parts(
    database_state: DatabaseStateSnapshot,
    query: str,
    answer_type: str,
    *,
    rag_context: list[RetrievalResult] | None = None,
) -> str:
    """Render a query prompt from individual components.

    Useful when the caller has the parts separately rather than a full
    QueryScenario object.

    Args:
        database_state: Database state snapshot with orders and slides.
        query: The natural language question.
        answer_type: Expected answer type (order_list, order_status,
            explanation, prioritized_list).
        rag_context: If provided, use retrieved chunks as workflow reference
            instead of full state/flag descriptions.

    Returns:
        The fully rendered prompt string.

    Raises:
        TypeError: If database_state is not a DatabaseStateSnapshot
            or query is not a string.
        ValueError: If query is empty or answer_type is invalid.
    """
    if not isinstance(database_state, DatabaseStateSnapshot):
        raise TypeError(
            f"database_state must be DatabaseStateSnapshot, got {type(database_state).__name__}"
        )
    if not isinstance(query, str):
        raise TypeError(f"query must be str, got {type(query).__name__}")
    if not query.strip():
        raise ValueError("query must not be empty")

    sm = StateMachine.get_instance()

    # Sort orders by created_at ascending so temporal order is visually
    # obvious to the model (helps with age-based comparisons).
    # Missing or None created_at defaults to "" which sorts before any
    # ISO-8601 timestamp, placing those orders first.
    orders_sorted = sorted(
        database_state.orders,
        key=lambda o: o.get("created_at") or "",
    )
    orders_json = _to_json_str(orders_sorted)
    slides_json = _to_json_str(list(database_state.slides))
    output_format = get_output_format(answer_type)
    answer_type_instructions = _ANSWER_TYPE_INSTRUCTIONS.get(answer_type, "")
    flag_reference = _format_flag_definitions(sm)

    if rag_context:
        state_reference = _format_rag_workflow_reference(rag_context)
    else:
        state_reference = _format_state_reference(sm)

    return _QUERY_PROMPT_TEMPLATE.format(
        orders_json=orders_json,
        slides_json=slides_json,
        state_reference=state_reference,
        flag_reference=flag_reference,
        query=query,
        answer_type_instructions=answer_type_instructions,
        output_format=output_format,
    )
