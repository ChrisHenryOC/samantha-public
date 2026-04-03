"""Tool-use prompt template for query evaluation.

Renders system and user messages for tool-use mode. Unlike the
context-stuffing prompt, **no database state** is included — the model
must call tools to gather the data it needs before answering.
"""

from __future__ import annotations

from src.models.base import ChatMessage, ChatRole
from src.prediction.query_prompt_template import get_output_format

_SYSTEM_PROMPT = """\
You are a laboratory information system assistant for a breast cancer
histology lab. You help lab workers and pathologists by answering
questions about order status and worklists.

You have access to tools that let you query the lab database. Use them
to gather the information you need before answering.

## Available Tools

- **list_orders** — List orders, optionally filtered by state, priority,
  or flag presence. Call with no arguments to list all orders.
- **get_order** — Get full details for a specific order by ID.
- **get_slides** — Get all slides for a specific order.
- **get_state_info** — Get information about a workflow state (phase,
  description, whether it is terminal).
- **get_flag_info** — Get information about a workflow flag (effect,
  how it is cleared).

## How to Answer

1. Read the question carefully.
2. Call tools to gather the data you need. Start with list_orders to
   see what orders exist, then drill into specific orders as needed.
3. Once you have enough information, respond with your final answer
   as a JSON object (described below).

Do NOT guess or make up data. Always call tools to verify.
"""

_PRIORITIZED_LIST_INSTRUCTIONS = """\
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

"""

_ORDER_LIST_INSTRUCTIONS = """\
Scan EVERY order in the database using list_orders. For each order,
check whether it matches the query criteria based on its current_state
and flags. Use get_state_info and get_flag_info to understand what each
state and flag means. Include all matching orders.

"""

_ANSWER_TYPE_INSTRUCTIONS: dict[str, str] = {
    "prioritized_list": _PRIORITIZED_LIST_INSTRUCTIONS,
    "order_list": _ORDER_LIST_INSTRUCTIONS,
}


def render_tool_use_messages(
    query: str,
    answer_type: str,
) -> tuple[ChatMessage, ChatMessage]:
    """Render system and user messages for tool-use query evaluation.

    Args:
        query: The natural language question.
        answer_type: Expected answer type (order_list, order_status,
            explanation, prioritized_list).

    Returns:
        A tuple of (system_message, user_message) ready for adapter.chat().

    Raises:
        TypeError: If query is not a string.
        ValueError: If query is empty or answer_type is invalid.
    """
    if not isinstance(query, str):
        raise TypeError(f"query must be str, got {type(query).__name__}")
    if not query.strip():
        raise ValueError("query must not be empty")

    output_format = get_output_format(answer_type)
    answer_instructions = _ANSWER_TYPE_INSTRUCTIONS.get(answer_type, "")

    user_content = (
        f"## Question\n\n{query}\n\n"
        f"{answer_instructions}"
        f"Respond with ONLY a JSON object in this exact format, no other text:\n\n"
        f"{output_format}"
    )

    system_msg = ChatMessage(role=ChatRole.SYSTEM, content=_SYSTEM_PROMPT)
    user_msg = ChatMessage(role=ChatRole.USER, content=user_content)
    return system_msg, user_msg
