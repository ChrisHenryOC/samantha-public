"""Skill document loader for skill-based routing prompts.

Loads markdown skill documents from ``knowledge_base/skills/`` and maps
workflow states to the appropriate skill. Skills replace the standard
formatted rule text in the prompt, providing structured step-by-step
instructions that teach the LLM how to evaluate rules.
"""

from __future__ import annotations

import functools
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_SKILL_DIR = Path(__file__).resolve().parent.parent.parent / "knowledge_base" / "skills"

# Maps workflow step names to skill filenames.
# Step names come from the state_machine's _STATE_TO_STEP mapping.
_STEP_TO_SKILL_FILE: dict[str, str] = {
    "ACCESSIONING": "accessioning.md",
    "SAMPLE_PREP": "sample_prep.md",
    "HE_QC": "he_qc.md",
    "PATHOLOGIST_HE_REVIEW": "pathologist_he_review.md",
    "IHC": "ihc.md",
    "RESULTING": "resulting.md",
}

# Maps workflow states to step names for skill lookup.
# Mirrors _STATE_TO_STEP from state_machine.py plus IHC states
# (which use applies_at rather than _STATE_TO_STEP).
_STATE_TO_SKILL_STEP: dict[str, str] = {
    "ACCESSIONING": "ACCESSIONING",
    "ACCEPTED": "SAMPLE_PREP",
    "MISSING_INFO_PROCEED": "SAMPLE_PREP",
    "SAMPLE_PREP_PROCESSING": "SAMPLE_PREP",
    "SAMPLE_PREP_EMBEDDING": "SAMPLE_PREP",
    "SAMPLE_PREP_SECTIONING": "SAMPLE_PREP",
    "SAMPLE_PREP_QC": "SAMPLE_PREP",
    "HE_STAINING": "HE_QC",
    "HE_QC": "HE_QC",
    "PATHOLOGIST_HE_REVIEW": "PATHOLOGIST_HE_REVIEW",
    "IHC_STAINING": "IHC",
    "IHC_QC": "IHC",
    "IHC_SCORING": "IHC",
    "SUGGEST_FISH_REFLEX": "IHC",
    "FISH_SEND_OUT": "IHC",
    "RESULTING": "RESULTING",
    "RESULTING_HOLD": "RESULTING",
    "PATHOLOGIST_SIGNOUT": "RESULTING",
    "REPORT_GENERATION": "RESULTING",
}


@functools.lru_cache(maxsize=8)
def load_skill(step: str) -> str | None:
    """Load a skill markdown file for the given workflow step.

    Returns the file content as a string, or ``None`` if no skill file
    exists for the step. Results are cached for the process lifetime.

    Args:
        step: Workflow step name (e.g., "ACCESSIONING", "SAMPLE_PREP").
    """
    filename = _STEP_TO_SKILL_FILE.get(step)
    if filename is None:
        return None

    skill_path = _SKILL_DIR / filename
    try:
        content = skill_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        logger.warning("Failed to read skill file %s: %s", skill_path, exc)
        return None

    if not content:
        logger.warning("Skill file is empty: %s", skill_path)
        return None

    return content


def get_skill_for_state(state: str) -> str | None:
    """Return the skill text for a workflow state.

    Maps the state to its workflow step, then loads the corresponding
    skill document. Returns ``None`` for states with no skill
    (terminal states, pass-through states like MISSING_INFO_HOLD,
    DO_NOT_PROCESS).

    Args:
        state: Current workflow state (e.g., "ACCESSIONING", "IHC_SCORING").
    """
    step = _STATE_TO_SKILL_STEP.get(state)
    if step is None:
        return None
    return load_skill(step)
