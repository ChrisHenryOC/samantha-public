"""Role-to-state mapping for the live server.

Each role maps to the set of workflow states that constitute that
role's work queue. ``None`` means the role sees all states.
"""

from __future__ import annotations

ROLE_STATES: dict[str, frozenset[str] | None] = {
    "accessioner": frozenset({"ACCESSIONING", "MISSING_INFO_HOLD", "DO_NOT_PROCESS"}),
    "histotech": frozenset(
        {
            "ACCEPTED",
            "MISSING_INFO_PROCEED",
            "SAMPLE_PREP_PROCESSING",
            "SAMPLE_PREP_EMBEDDING",
            "SAMPLE_PREP_SECTIONING",
            "SAMPLE_PREP_QC",
            "HE_STAINING",
            "HE_QC",
            "IHC_STAINING",
            "IHC_QC",
            "REPORT_GENERATION",
        }
    ),
    "pathologist": frozenset(
        {
            "PATHOLOGIST_HE_REVIEW",
            "IHC_SCORING",
            "SUGGEST_FISH_REFLEX",
            "FISH_SEND_OUT",
            "RESULTING",
            "RESULTING_HOLD",
            "PATHOLOGIST_SIGNOUT",
        }
    ),
    "lab_manager": None,
}

VALID_ROLES: frozenset[str] = frozenset(ROLE_STATES)
