"""Shared model output parsing and schema validation.

Both ``LlamaCppAdapter`` and ``OpenRouterAdapter`` expect the same structured
JSON schema from model responses.  This module centralizes the validation
logic so that schema changes are applied uniformly across all providers.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# --- Schema constants ---

REQUIRED_KEYS: frozenset[str] = frozenset({"next_state", "applied_rules", "flags", "reasoning"})
STRING_FIELDS: tuple[str, ...] = ("next_state", "reasoning")
LIST_FIELDS: tuple[str, ...] = ("applied_rules", "flags")

# --- Return type ---

type ParseResult = tuple[dict[str, Any], None] | tuple[None, str]

# Match ```json ... ``` or ``` ... ``` fenced blocks.
_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)

# Match ```json ... ``` blocks specifically (preferred over untagged fences).
_JSON_FENCE_RE = re.compile(r"```json\s*\n?(.*?)\n?\s*```", re.DOTALL)


def strip_code_fences(text: str) -> str:
    """Extract JSON from markdown code fences if present.

    Prefers ````` ```json ``` ````` blocks over untagged fences so that
    thinking/reasoning fences (e.g. ````` ```thinking ``` `````) are
    skipped when a JSON fence is also present.

    As a last resort, extracts text between the first ``{`` and last ``}``
    and validates it with ``json.loads`` before returning.  This handles
    models that emit preamble and/or postamble around bare JSON (observed
    with OpenRouter Llama 3.1 8B — see GH-127).
    """
    # First, try to find a ```json fence specifically.
    json_match = _JSON_FENCE_RE.search(text)
    if json_match:
        return json_match.group(1).strip()
    # Fall back to any code fence.
    match = _CODE_FENCE_RE.search(text)
    if match:
        return match.group(1).strip()
    # Last resort: extract the first valid JSON object delimited by { ... }.
    # json.loads validation prevents returning wrong-bounds candidates when
    # rfind("}") matches a brace in trailing text rather than the JSON close.
    stripped = text.strip()
    brace_start = stripped.find("{")
    brace_end = stripped.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        candidate = stripped[brace_start : brace_end + 1]
        try:
            json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            logger.debug(
                "brace_extraction: candidate (%d chars) did not parse, "
                "returning stripped text (%d chars)",
                len(candidate),
                len(stripped),
            )
        else:
            logger.debug(
                "brace_extraction: rescued %d-char JSON from %d-char response (preamble=%d chars)",
                len(candidate),
                len(stripped),
                brace_start,
            )
            return candidate
    return stripped


def parse_model_output(raw_text: str) -> ParseResult:
    """Try to parse raw model text as structured JSON.

    If the model wraps its output in markdown code fences (e.g.
    ````` ```json ... ``` `````) the fences are stripped before parsing.

    Returns
    -------
    ParseResult
        ``(parsed_output, None)`` on success or ``(None, error)`` on failure.
    """
    cleaned = strip_code_fences(raw_text)
    try:
        parsed = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return None, "malformed_json: model output is not valid JSON"

    if not isinstance(parsed, dict):
        return None, f"wrong_schema: expected JSON object, got {type(parsed).__name__}"

    missing = REQUIRED_KEYS - set(parsed)
    if missing:
        return None, f"wrong_schema: missing required keys {sorted(missing)}"

    for field in STRING_FIELDS:
        if not isinstance(parsed.get(field), str):
            actual = type(parsed[field]).__name__
            return None, f"wrong_schema: {field} must be a string, got {actual}"
    for field in LIST_FIELDS:
        if not isinstance(parsed.get(field), list):
            return None, f"wrong_schema: {field} must be a list, got {type(parsed[field]).__name__}"
        if not all(isinstance(item, str) for item in parsed[field]):
            return None, f"wrong_schema: {field} elements must be strings"

    return parsed, None
