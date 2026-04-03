"""Routing prompt template for workflow predictions.

Renders the standardized prompt that all models receive, populating
template variables from order state, slides, events, and the rule catalog.
"""

from __future__ import annotations

import functools
import json
import logging
from dataclasses import asdict
from datetime import datetime
from typing import TYPE_CHECKING, Any

from src.prediction.skill_loader import get_skill_for_state
from src.workflow.models import Event, Order, Slide
from src.workflow.state_machine import Rule, StateMachine

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.rag.retriever import RetrievalResult

_PROMPT_TEMPLATE = """\
You are a laboratory workflow routing system for a breast cancer histology lab.
Your job is to determine what should happen next to a lab order based on an
incoming event. You are a workflow traffic cop — you route orders between steps
and identify issues. You NEVER make clinical decisions.

## Your Rules

The following rules apply to the current workflow step. Evaluate ALL rules
against the current situation. For most workflow steps, apply the first
matching rule. For ACCESSIONING, identify ALL matching rules — multiple
issues can be flagged at once. The highest-severity outcome determines
the next state (REJECT > HOLD > PROCEED > ACCEPT).

If no rule matches, respond with the closest valid state from the vocabulary
below, set applied_rules to an empty list [], and explain the ambiguity in
your reasoning.

{rules_for_current_step}
{additional_context}
{prompt_extras}## Valid Workflow States

You MUST use one of these exact state names for next_state. Do not abbreviate,
shorten, or invent state names.

{valid_states}

## Valid Flags

You MUST only use flags from this list. Do not invent new flag names.

{valid_flags}

## Flag Reference

Flags carry forward across workflow steps. Check the order's existing flags
before making your decision — they may block or alter the expected transition.

{flag_reference}

## Current Order State

{order_state_json}

## Slides

{slides_json}

## New Event

{event_json}

## Instructions

1. Review the current order state and the new event.
2. Check the order's existing flags — they may affect your decision.
3. Evaluate the rules above against the current situation.
4. For ACCESSIONING: identify ALL matching rules. The highest-severity outcome \
determines the next state (REJECT > HOLD > PROCEED > ACCEPT). Report every \
matching rule in applied_rules.
5. For all other steps: identify the FIRST rule whose trigger condition matches \
(by priority order) and apply it to determine the next state and any flags.
6. In applied_rules, use ONLY the formal rule IDs listed under "Your Rules" \
above (e.g., "ACC-001", "SP-002", "HE-005"). Do NOT invent descriptive rule \
names or labels. If no formal rule ID matches, set applied_rules to [].
{retry_clarification}
Respond with ONLY a JSON object in this exact format, no other text:

{{
  "next_state": "<the workflow state the order should transition to>",
  "applied_rules": ["<rule_id(s) that matched>"],
  "flags": ["<ALL active flags — carry forward existing, add new, remove cleared>"],
  "reasoning": "<brief explanation of why this rule applies>"
}}\
"""

# --- Prompt extras: optional sections enabled via --prompt-extras CLI flag ---

VALID_PROMPT_EXTRAS = frozenset({"state_sequence", "retry_clarification", "few_shot", "skills"})

_STATE_SEQUENCE_TEXT = """\
## Workflow Step Sequence

When a rule says "Advance to next step", follow this exact sequence:
- Sample Prep: SAMPLE_PREP_PROCESSING → SAMPLE_PREP_EMBEDDING → \
SAMPLE_PREP_SECTIONING → SAMPLE_PREP_QC → HE_STAINING
- After HE_STAINING: HE_QC → PATHOLOGIST_HE_REVIEW
- After PATHOLOGIST_HE_REVIEW (if IHC needed): IHC_STAINING → IHC_QC → \
IHC_SCORING
- After IHC_SCORING: RESULTING → PATHOLOGIST_SIGNOUT → REPORT_GENERATION → \
ORDER_COMPLETE
"""

_RETRY_CLARIFICATION_TEXT = """\
7. When a rule's action says "RETRY current step" or "RETRY → [step]", output \
the specific workflow state name (e.g., SAMPLE_PREP_PROCESSING), not the word \
"RETRY". "RETRY current step" means the order stays at the same state it was \
in before this event.
"""

_FEW_SHOT_TEXT = """\
## Example

Event: grossing_complete with outcome "success" on an order in ACCEPTED state.
Correct response:
{{"next_state": "SAMPLE_PREP_PROCESSING", "applied_rules": ["SP-001"], \
"flags": [], "reasoning": "Grossing completed successfully, advancing to \
first sample prep step per SP-001."}}
"""


def _json_serializer(obj: Any) -> str:
    """JSON default serializer for datetime objects."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _format_rules(rules: list[Rule]) -> str:
    """Format rules as a numbered list for prompt inclusion.

    Each rule shows its ID, trigger condition, action, and
    priority or severity as applicable.
    """
    if not rules:
        return "No rules apply to the current workflow step."

    lines: list[str] = []
    for i, rule in enumerate(rules, 1):
        order_key = f"Severity: {rule.severity}" if rule.severity else f"Priority: {rule.priority}"
        lines.append(
            f"{i}. **{rule.rule_id}** — {order_key}\n"
            f"   Trigger: {rule.trigger}\n"
            f"   Action: {rule.action}"
        )
    return "\n\n".join(lines)


def _format_valid_states(states: frozenset[str]) -> str:
    """Format valid state names as a comma-separated list.

    Raises:
        ValueError: If states is empty (misconfiguration).
    """
    if not states:
        raise ValueError("State machine returned empty state vocabulary.")
    return ", ".join(sorted(states))


def _format_valid_flags(
    flag_ids: frozenset[str],
    flag_vocabulary: dict[str, dict[str, Any]],
) -> str:
    """Format valid flag IDs with set_at context.

    Each flag is listed with the workflow step(s) where it may be set,
    giving models context for when each flag applies.

    Raises:
        ValueError: If flag_ids is empty (misconfiguration).
    """
    if not flag_ids:
        raise ValueError("State machine returned empty flag vocabulary.")

    lines: list[str] = []
    for flag_id in sorted(flag_ids):
        meta = flag_vocabulary.get(flag_id)
        set_at = ", ".join(meta.get("set_at", [])) if meta else ""
        annotation = f" (set at: {set_at})" if set_at else ""
        lines.append(f"- **{flag_id}**{annotation}")

    return "\n".join(lines)


def _format_flag_reference(
    active_flags: list[str],
    flag_vocabulary: dict[str, dict[str, Any]],
) -> str:
    """Format active flags with their downstream effects.

    Only flags currently set on the order are included.
    Returns a message indicating no flags if the list is empty.
    """
    if not active_flags:
        return "No flags are currently set on this order."

    lines: list[str] = []
    for flag_id in active_flags:
        meta = flag_vocabulary.get(flag_id)
        if meta:
            effect = meta.get("effect", "No effect description")
            cleared_by = meta.get("cleared_by", "Unknown")
            lines.append(f"- **{flag_id}**: {effect} (Cleared by: {cleared_by})")
        else:
            lines.append(f"- **{flag_id}**: Unknown flag")

    return "\n".join(lines)


def _to_json_str(data: Any) -> str:
    """Serialize data to a formatted JSON string."""
    return json.dumps(data, indent=2, default=_json_serializer)


@functools.lru_cache(maxsize=8)
def _format_prompt_extras(extras: frozenset[str]) -> tuple[str, str]:
    """Build the prompt_extras and retry_clarification insertion text.

    Returns a tuple of (prompt_extras_block, retry_clarification_block).
    The prompt_extras_block is inserted after the rules/additional_context
    sections. The retry_clarification_block is inserted in the Instructions
    section (after item 6).

    Raises:
        ValueError: If any extra name is not in VALID_PROMPT_EXTRAS.
    """
    invalid = extras - VALID_PROMPT_EXTRAS
    if invalid:
        raise ValueError(
            f"Invalid prompt extras: {sorted(invalid)}. "
            f"Valid options: {sorted(VALID_PROMPT_EXTRAS)}"
        )

    sections: list[str] = []
    if "state_sequence" in extras:
        sections.append(_STATE_SEQUENCE_TEXT)
    if "few_shot" in extras:
        sections.append(_FEW_SHOT_TEXT)

    prompt_block = "\n".join(s.rstrip("\n") for s in sections) + "\n" if sections else ""
    retry_block = _RETRY_CLARIFICATION_TEXT if "retry_clarification" in extras else ""

    return prompt_block, retry_block


def _format_additional_context(chunks: list[RetrievalResult]) -> str:
    """Format RAG chunks as a supplementary context section.

    Returns an empty string when no chunks are provided (non-RAG modes),
    or a full "Additional Context" section with SOP excerpts and a
    reminder to cite formal rule IDs from the rules section above.
    """
    if not chunks:
        return ""

    lines: list[str] = [
        "## Additional Context (Retrieved from SOPs)",
        "",
        "The following excerpts were retrieved from lab SOPs and may provide",
        'additional detail. Use the formal rule IDs from "Your Rules" above',
        "when citing rules — do NOT invent descriptive labels.",
        "",
    ]
    for i, chunk in enumerate(chunks, 1):
        lines.append(f"### Context {i} (from {chunk.source_file}: {chunk.section_title})")
        lines.append("")
        lines.append(chunk.text)
    return "\n".join(lines)


def render_prompt(
    order: Order,
    slides: list[Slide],
    event: Event,
    *,
    full_context: bool = False,
    rag_context: list[RetrievalResult] | None = None,
    prompt_extras: frozenset[str] = frozenset(),
) -> str:
    """Render the complete routing prompt for a model invocation.

    Three context modes (priority order):

    - ``rag_context`` provided (including empty list): **hybrid mode** —
      step-filtered rules are always included as a structured checklist,
      and RAG chunks appear in a separate "Additional Context" section
      below. ``full_context`` is ignored. Note: hybrid mode adds ~300-500
      tokens per call (the step-filtered rule block) on top of RAG chunks.
      Consider reducing ``top_k`` at the retriever level to offset.
    - ``full_context=True``: include ALL rules regardless of workflow step
      (Phase 4 full-context baseline).
    - Default (``rag_context=None``): rules filtered to current workflow
      step only.

    Args:
        order: Current order state.
        slides: All slides for this order.
        event: The triggering event.
        full_context: If True, include all rules regardless of workflow step.
        rag_context: If provided (even if empty), include these retrieved
            chunks as supplementary context alongside the structured rule
            catalog. Pass ``None`` (default) to disable hybrid mode.
        prompt_extras: Optional set of prompt section names to include.
            Valid values: ``state_sequence``, ``retry_clarification``,
            ``few_shot``, ``skills``. Empty frozenset (default) adds no
            extra sections. When ``skills`` is included, skill documents
            replace the standard rule text for the current workflow step.

    Returns:
        The fully rendered prompt string with all template variables
        populated.
    """
    sm = StateMachine.get_instance()

    # Skill mode: replace formatted rules with a skill document that
    # teaches the LLM how to evaluate step-by-step. When a skill is
    # active, it replaces both the rules text and any RAG context —
    # skills are self-contained.
    use_skills = "skills" in prompt_extras
    skill_text: str | None = None
    if use_skills:
        skill_text = get_skill_for_state(order.current_state)
        if not skill_text:
            logger.debug(
                "Skills mode active but no skill for state %s; falling back to standard rules",
                order.current_state,
            )
            skill_text = None

    if skill_text:
        rules_text = skill_text
        additional_context = ""
    elif rag_context is not None:
        # Hybrid mode: always include structured rules + RAG as supplement
        rules_text = _format_rules(sm.get_rules_for_state(order.current_state))
        additional_ctx = _format_additional_context(rag_context)
        additional_context = f"\n{additional_ctx}" if additional_ctx else ""
    elif full_context:
        rules_text = _format_rules(sm.get_all_rules())
        additional_context = ""
    else:
        rules_text = _format_rules(sm.get_rules_for_state(order.current_state))
        additional_context = ""

    extras_block, retry_block = _format_prompt_extras(prompt_extras)

    flag_vocabulary = sm.get_flag_vocabulary()

    valid_states_text = _format_valid_states(sm.get_all_states())
    valid_flags_text = _format_valid_flags(sm.get_all_flag_ids(), flag_vocabulary)
    flag_text = _format_flag_reference(order.flags, flag_vocabulary)
    order_json = _to_json_str(asdict(order))
    slides_json = _to_json_str([asdict(s) for s in slides])
    event_json = _to_json_str(asdict(event))

    return _PROMPT_TEMPLATE.format(
        rules_for_current_step=rules_text,
        additional_context=additional_context,
        prompt_extras=extras_block,
        retry_clarification=retry_block,
        valid_states=valid_states_text,
        valid_flags=valid_flags_text,
        flag_reference=flag_text,
        order_state_json=order_json,
        slides_json=slides_json,
        event_json=event_json,
    )
