"""Profile-based order generator for synthetic test data.

Produces valid event_data dicts for order_received events. Each
OrderProfile targets specific accessioning rules, enabling systematic
rule coverage testing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.workflow.models import Order, expand_panel

# First names for synthetic patients — cycled by seq_num.
_FIRST_NAMES: tuple[str, ...] = (
    "Sarah",
    "Michael",
    "Emily",
    "James",
    "Olivia",
    "Robert",
    "Sophia",
    "William",
    "Emma",
    "David",
)

# Sentinel value used when patient_name should be present.
# The actual value doesn't matter — only None vs non-None is checked.
_HAS_NAME = "present"


@dataclass(frozen=True)
class OrderProfile:
    """Configuration for generating a specific type of order.

    Each profile targets one or more accessioning rules by setting
    field values that trigger those rules.

    ``patient_name`` accepts ``None`` (field missing — triggers ACC-001)
    or any non-None string. When non-None, ``generate_order_data``
    produces a synthetic name with the ``TESTPATIENT-`` prefix.
    """

    name: str
    target_rules: tuple[str, ...]
    patient_name: str | None
    patient_sex: str | None
    specimen_type: str
    anatomic_site: str
    fixative: str
    fixation_time_hours: float | None
    ordered_tests: tuple[str, ...]
    priority: str
    billing_info_present: bool
    age: int | None = None

    def __post_init__(self) -> None:
        """Validate field types and non-empty constraints.

        Raises:
            ValueError: If name is empty, or target_rules/ordered_tests
                tuples are empty.
            TypeError: If target_rules or ordered_tests are not tuples,
                or contain non-string elements.
        """
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("name must be a non-empty string")
        if not isinstance(self.target_rules, tuple):
            raise TypeError(f"target_rules must be tuple, got {type(self.target_rules).__name__}")
        if len(self.target_rules) == 0:
            raise ValueError("target_rules must not be empty")
        for i, rule in enumerate(self.target_rules):
            if not isinstance(rule, str):
                raise TypeError(f"target_rules[{i}] must be str, got {type(rule).__name__}")
        if not isinstance(self.ordered_tests, tuple):
            raise TypeError(f"ordered_tests must be tuple, got {type(self.ordered_tests).__name__}")
        if len(self.ordered_tests) == 0:
            raise ValueError("ordered_tests must not be empty")
        for i, test in enumerate(self.ordered_tests):
            if not isinstance(test, str):
                raise TypeError(f"ordered_tests[{i}] must be str, got {type(test).__name__}")


def generate_order_data(profile: OrderProfile, seq_num: int) -> dict[str, Any]:
    """Generate an event_data dict for an order_received event.

    Args:
        profile: The order profile defining field values.
        seq_num: Sequence number for unique patient name generation.

    Returns:
        A dict suitable for use as event_data in an order_received
        ScenarioStep. Panel names in ordered_tests are NOT expanded
        here — the event_data mirrors what arrives from the LIS.
        The test harness expands panels when creating Order objects.
    """
    if seq_num < 0:
        raise ValueError(f"seq_num must be non-negative, got {seq_num}")

    first_name = _FIRST_NAMES[seq_num % len(_FIRST_NAMES)]

    # Build patient_name only if the profile specifies one.
    patient_name: str | None = None
    if profile.patient_name is not None:
        patient_name = f"TESTPATIENT-{seq_num:04d}, {first_name}"

    event_data: dict[str, Any] = {
        "patient_name": patient_name,
        "age": profile.age,
        "sex": profile.patient_sex,
        "specimen_type": profile.specimen_type,
        "anatomic_site": profile.anatomic_site,
        "fixative": profile.fixative,
        "fixation_time_hours": profile.fixation_time_hours,
        "ordered_tests": list(profile.ordered_tests),
        "priority": profile.priority,
        "billing_info_present": profile.billing_info_present,
    }

    # Construct a throwaway Order to validate that the generated event_data
    # is compatible with Order's __post_init__ checks (field lengths, allowed
    # values, etc.).  Panels must be expanded first since Order rejects
    # unexpanded panel names.
    expanded_tests: list[str] = []
    for test in profile.ordered_tests:
        expanded_tests.extend(expand_panel(test))

    Order(
        order_id=f"ORD-{seq_num:04d}",
        scenario_id="SC-000",
        patient_name=patient_name,
        patient_age=profile.age,
        patient_sex=profile.patient_sex,
        specimen_type=profile.specimen_type,
        anatomic_site=profile.anatomic_site,
        fixative=profile.fixative,
        fixation_time_hours=profile.fixation_time_hours,
        ordered_tests=expanded_tests,
        priority=profile.priority,
        billing_info_present=profile.billing_info_present,
        current_state="ACCESSIONING",
    )

    return event_data


# ── Pre-defined profiles ────────────────────────────────────────────

STANDARD_INVASIVE = OrderProfile(
    name="standard_invasive",
    target_rules=("ACC-008",),
    patient_name=_HAS_NAME,
    patient_sex="F",
    specimen_type="biopsy",
    anatomic_site="breast",
    fixative="formalin",
    fixation_time_hours=24.0,
    ordered_tests=("Breast IHC Panel",),
    priority="routine",
    billing_info_present=True,
    age=58,
)

STANDARD_BENIGN = OrderProfile(
    name="standard_benign",
    target_rules=("ACC-008",),
    patient_name=_HAS_NAME,
    patient_sex="F",
    specimen_type="resection",
    anatomic_site="breast",
    fixative="formalin",
    fixation_time_hours=24.0,
    ordered_tests=("Breast IHC Panel",),
    priority="routine",
    billing_info_present=True,
    age=62,
)

MISSING_PATIENT_NAME = OrderProfile(
    name="missing_patient_name",
    target_rules=("ACC-001",),
    patient_name=None,
    patient_sex="F",
    specimen_type="biopsy",
    anatomic_site="breast",
    fixative="formalin",
    fixation_time_hours=24.0,
    ordered_tests=("Breast IHC Panel",),
    priority="routine",
    billing_info_present=True,
    age=55,
)

MISSING_PATIENT_SEX = OrderProfile(
    name="missing_patient_sex",
    target_rules=("ACC-002",),
    patient_name=_HAS_NAME,
    patient_sex=None,
    specimen_type="biopsy",
    anatomic_site="breast",
    fixative="formalin",
    fixation_time_hours=24.0,
    ordered_tests=("Breast IHC Panel",),
    priority="routine",
    billing_info_present=True,
    age=48,
)

INVALID_ANATOMIC_SITE = OrderProfile(
    name="invalid_anatomic_site",
    target_rules=("ACC-003",),
    patient_name=_HAS_NAME,
    patient_sex="F",
    specimen_type="biopsy",
    anatomic_site="lung",
    fixative="formalin",
    fixation_time_hours=24.0,
    ordered_tests=("Breast IHC Panel",),
    priority="routine",
    billing_info_present=True,
    age=65,
)

INCOMPATIBLE_SPECIMEN = OrderProfile(
    name="incompatible_specimen",
    target_rules=("ACC-004",),
    patient_name=_HAS_NAME,
    patient_sex="F",
    specimen_type="FNA",
    anatomic_site="breast",
    fixative="formalin",
    fixation_time_hours=24.0,
    ordered_tests=("Breast IHC Panel",),
    priority="routine",
    billing_info_present=True,
    age=52,
)

HER2_NOT_FORMALIN = OrderProfile(
    name="her2_not_formalin",
    target_rules=("ACC-005",),
    patient_name=_HAS_NAME,
    patient_sex="F",
    specimen_type="biopsy",
    anatomic_site="breast",
    fixative="fresh",
    fixation_time_hours=24.0,
    ordered_tests=("Breast IHC Panel",),
    priority="routine",
    billing_info_present=True,
    age=45,
)

INCOMPATIBLE_SPECIMEN_NON_FORMALIN = OrderProfile(
    name="incompatible_specimen_non_formalin",
    target_rules=("ACC-004", "ACC-005"),
    patient_name=_HAS_NAME,
    patient_sex="F",
    specimen_type="cytospin",
    anatomic_site="breast",
    fixative="alcohol",
    fixation_time_hours=24.0,
    ordered_tests=("Breast IHC Panel",),
    priority="routine",
    billing_info_present=True,
    age=58,
)

HER2_NOT_FORMALIN_ALCOHOL = OrderProfile(
    name="her2_not_formalin_alcohol",
    target_rules=("ACC-005",),
    patient_name=_HAS_NAME,
    patient_sex="M",
    specimen_type="biopsy",
    anatomic_site="breast",
    fixative="alcohol",
    fixation_time_hours=48.0,
    ordered_tests=("Breast IHC Panel",),
    priority="routine",
    billing_info_present=True,
    age=62,
)

HER2_FIXATION_UNDER = OrderProfile(
    name="her2_fixation_under",
    target_rules=("ACC-006",),
    patient_name=_HAS_NAME,
    patient_sex="F",
    specimen_type="biopsy",
    anatomic_site="breast",
    fixative="formalin",
    fixation_time_hours=5.0,
    ordered_tests=("Breast IHC Panel",),
    priority="routine",
    billing_info_present=True,
    age=50,
)

HER2_FIXATION_OVER = OrderProfile(
    name="her2_fixation_over",
    target_rules=("ACC-006",),
    patient_name=_HAS_NAME,
    patient_sex="F",
    specimen_type="biopsy",
    anatomic_site="breast",
    fixative="formalin",
    fixation_time_hours=73.0,
    ordered_tests=("Breast IHC Panel",),
    priority="routine",
    billing_info_present=True,
    age=60,
)

MISSING_FIXATION_TIME = OrderProfile(
    name="missing_fixation_time",
    target_rules=("ACC-009",),
    patient_name=_HAS_NAME,
    patient_sex="F",
    specimen_type="biopsy",
    anatomic_site="breast",
    fixative="formalin",
    fixation_time_hours=None,
    ordered_tests=("Breast IHC Panel",),
    priority="routine",
    billing_info_present=True,
    age=51,
)

MISSING_BILLING = OrderProfile(
    name="missing_billing",
    target_rules=("ACC-007",),
    patient_name=_HAS_NAME,
    patient_sex="F",
    specimen_type="biopsy",
    anatomic_site="breast",
    fixative="formalin",
    fixation_time_hours=24.0,
    ordered_tests=("Breast IHC Panel",),
    priority="routine",
    billing_info_present=False,
    age=47,
)

FIXATION_BOUNDARY_LOW = OrderProfile(
    name="fixation_boundary_low",
    target_rules=("ACC-008",),
    patient_name=_HAS_NAME,
    patient_sex="F",
    specimen_type="biopsy",
    anatomic_site="breast",
    fixative="formalin",
    fixation_time_hours=6.0,
    ordered_tests=("Breast IHC Panel",),
    priority="routine",
    billing_info_present=True,
    age=53,
)

FIXATION_BOUNDARY_HIGH = OrderProfile(
    name="fixation_boundary_high",
    target_rules=("ACC-008",),
    patient_name=_HAS_NAME,
    patient_sex="F",
    specimen_type="biopsy",
    anatomic_site="breast",
    fixative="formalin",
    fixation_time_hours=72.0,
    ordered_tests=("Breast IHC Panel",),
    priority="routine",
    billing_info_present=True,
    age=57,
)

# ACC-001 (HOLD) + ACC-003 (REJECT) — REJECT wins → DO_NOT_PROCESS
MULTI_DEFECT_HOLD_REJECT = OrderProfile(
    name="multi_defect_hold_reject",
    target_rules=("ACC-001", "ACC-003"),
    patient_name=None,
    patient_sex="F",
    specimen_type="biopsy",
    anatomic_site="lung",
    fixative="formalin",
    fixation_time_hours=24.0,
    ordered_tests=("Breast IHC Panel",),
    priority="routine",
    billing_info_present=True,
    age=61,
)

# ACC-001 (HOLD) + ACC-002 (HOLD) — both HOLD → MISSING_INFO_HOLD
# Both missing fields flagged and requested simultaneously.
MULTI_DEFECT_DUAL_HOLD = OrderProfile(
    name="multi_defect_dual_hold",
    target_rules=("ACC-001", "ACC-002"),
    patient_name=None,
    patient_sex=None,
    specimen_type="biopsy",
    anatomic_site="breast",
    fixative="formalin",
    fixation_time_hours=24.0,
    ordered_tests=("Breast IHC Panel",),
    priority="routine",
    billing_info_present=True,
    age=50,
)

# ACC-001 (HOLD) + ACC-007 (PROCEED) — HOLD wins → MISSING_INFO_HOLD
MULTI_DEFECT_HOLD_PROCEED = OrderProfile(
    name="multi_defect_hold_proceed",
    target_rules=("ACC-001", "ACC-007"),
    patient_name=None,
    patient_sex="F",
    specimen_type="biopsy",
    anatomic_site="breast",
    fixative="formalin",
    fixation_time_hours=24.0,
    ordered_tests=("Breast IHC Panel",),
    priority="routine",
    billing_info_present=False,
    age=44,
)


# Bad fixation but no HER2 ordered — ACC-005/ACC-006 must NOT fire.
# Verifies false-positive boundary: fixation issues only matter for HER2.
BAD_FIXATION_NO_HER2 = OrderProfile(
    name="bad_fixation_no_her2",
    target_rules=("ACC-008",),
    patient_name=_HAS_NAME,
    patient_sex="F",
    specimen_type="biopsy",
    anatomic_site="breast",
    fixative="fresh",
    fixation_time_hours=5.0,
    ordered_tests=("ER", "PR"),
    priority="routine",
    billing_info_present=True,
    age=55,
)

# All profiles in a tuple for iteration.
ALL_PROFILES: tuple[OrderProfile, ...] = (
    STANDARD_INVASIVE,
    STANDARD_BENIGN,
    MISSING_PATIENT_NAME,
    MISSING_PATIENT_SEX,
    INVALID_ANATOMIC_SITE,
    INCOMPATIBLE_SPECIMEN,
    HER2_NOT_FORMALIN,
    HER2_FIXATION_UNDER,
    HER2_FIXATION_OVER,
    MISSING_FIXATION_TIME,
    MISSING_BILLING,
    FIXATION_BOUNDARY_LOW,
    FIXATION_BOUNDARY_HIGH,
    MULTI_DEFECT_HOLD_REJECT,
    MULTI_DEFECT_DUAL_HOLD,
    MULTI_DEFECT_HOLD_PROCEED,
    BAD_FIXATION_NO_HER2,
)
