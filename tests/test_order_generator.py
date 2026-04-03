"""Tests for the profile-based order generator."""

from __future__ import annotations

import pytest

from src.simulator.order_generator import (
    ALL_PROFILES,
    BAD_FIXATION_NO_HER2,
    FIXATION_BOUNDARY_HIGH,
    FIXATION_BOUNDARY_LOW,
    HER2_FIXATION_OVER,
    HER2_FIXATION_UNDER,
    HER2_NOT_FORMALIN,
    INCOMPATIBLE_SPECIMEN,
    INVALID_ANATOMIC_SITE,
    MISSING_BILLING,
    MISSING_FIXATION_TIME,
    MISSING_PATIENT_NAME,
    MISSING_PATIENT_SEX,
    MULTI_DEFECT_DUAL_HOLD,
    MULTI_DEFECT_HOLD_PROCEED,
    MULTI_DEFECT_HOLD_REJECT,
    STANDARD_BENIGN,
    STANDARD_INVASIVE,
    OrderProfile,
    generate_order_data,
)
from src.workflow.models import Order, expand_panel

# --- OrderProfile validation ---


class TestOrderProfileValidation:
    def test_frozen(self) -> None:
        with pytest.raises(AttributeError):
            STANDARD_INVASIVE.name = "changed"  # type: ignore[misc]

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-empty string"):
            OrderProfile(
                name="",
                target_rules=("ACC-008",),
                patient_name="present",
                patient_sex="F",
                specimen_type="biopsy",
                anatomic_site="breast",
                fixative="formalin",
                fixation_time_hours=24.0,
                ordered_tests=("Breast IHC Panel",),
                priority="routine",
                billing_info_present=True,
            )

    def test_target_rules_must_be_tuple(self) -> None:
        with pytest.raises(TypeError, match="target_rules must be tuple"):
            OrderProfile(
                name="bad",
                target_rules=["ACC-008"],  # type: ignore[arg-type]
                patient_name="present",
                patient_sex="F",
                specimen_type="biopsy",
                anatomic_site="breast",
                fixative="formalin",
                fixation_time_hours=24.0,
                ordered_tests=("Breast IHC Panel",),
                priority="routine",
                billing_info_present=True,
            )

    def test_target_rules_must_not_be_empty(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            OrderProfile(
                name="empty_rules",
                target_rules=(),
                patient_name="present",
                patient_sex="F",
                specimen_type="biopsy",
                anatomic_site="breast",
                fixative="formalin",
                fixation_time_hours=24.0,
                ordered_tests=("Breast IHC Panel",),
                priority="routine",
                billing_info_present=True,
            )

    def test_ordered_tests_must_be_tuple(self) -> None:
        with pytest.raises(TypeError, match="ordered_tests must be tuple"):
            OrderProfile(
                name="bad",
                target_rules=("ACC-008",),
                patient_name="present",
                patient_sex="F",
                specimen_type="biopsy",
                anatomic_site="breast",
                fixative="formalin",
                fixation_time_hours=24.0,
                ordered_tests=["Breast IHC Panel"],  # type: ignore[arg-type]
                priority="routine",
                billing_info_present=True,
            )

    def test_target_rules_elements_must_be_str(self) -> None:
        with pytest.raises(TypeError, match=r"target_rules\[0\] must be str"):
            OrderProfile(
                name="bad_rules",
                target_rules=(123,),  # type: ignore[arg-type]
                patient_name="present",
                patient_sex="F",
                specimen_type="biopsy",
                anatomic_site="breast",
                fixative="formalin",
                fixation_time_hours=24.0,
                ordered_tests=("Breast IHC Panel",),
                priority="routine",
                billing_info_present=True,
            )

    def test_ordered_tests_elements_must_be_str(self) -> None:
        with pytest.raises(TypeError, match=r"ordered_tests\[0\] must be str"):
            OrderProfile(
                name="bad_tests",
                target_rules=("ACC-008",),
                patient_name="present",
                patient_sex="F",
                specimen_type="biopsy",
                anatomic_site="breast",
                fixative="formalin",
                fixation_time_hours=24.0,
                ordered_tests=(123,),  # type: ignore[arg-type]
                priority="routine",
                billing_info_present=True,
            )

    def test_ordered_tests_must_not_be_empty(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            OrderProfile(
                name="empty_tests",
                target_rules=("ACC-008",),
                patient_name="present",
                patient_sex="F",
                specimen_type="biopsy",
                anatomic_site="breast",
                fixative="formalin",
                fixation_time_hours=24.0,
                ordered_tests=(),
                priority="routine",
                billing_info_present=True,
            )


# --- generate_order_data basic behavior ---


class TestGenerateOrderData:
    def test_returns_dict(self) -> None:
        data = generate_order_data(STANDARD_INVASIVE, 0)
        assert isinstance(data, dict)

    def test_synthetic_patient_name_format(self) -> None:
        data = generate_order_data(STANDARD_INVASIVE, 1)
        assert data["patient_name"] == "TESTPATIENT-0001, Michael"

    def test_patient_name_none_when_missing(self) -> None:
        data = generate_order_data(MISSING_PATIENT_NAME, 0)
        assert data["patient_name"] is None

    def test_sequential_numbering_produces_unique_names(self) -> None:
        names = set()
        for i in range(20):
            data = generate_order_data(STANDARD_INVASIVE, i)
            names.add(data["patient_name"])
        assert len(names) == 20

    def test_first_name_cycles(self) -> None:
        data0 = generate_order_data(STANDARD_INVASIVE, 0)
        data10 = generate_order_data(STANDARD_INVASIVE, 10)
        # Same first name (index 0 and 10 both map to index 0)
        assert "Sarah" in data0["patient_name"]
        assert "Sarah" in data10["patient_name"]
        # But different patient IDs
        assert "0000" in data0["patient_name"]
        assert "0010" in data10["patient_name"]

    def test_negative_seq_num_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            generate_order_data(STANDARD_INVASIVE, -1)

    def test_ordered_tests_not_expanded_in_event_data(self) -> None:
        data = generate_order_data(STANDARD_INVASIVE, 0)
        assert data["ordered_tests"] == ["Breast IHC Panel"]

    def test_non_panel_ordered_tests(self) -> None:
        """Individual test names pass through without expansion."""
        profile = OrderProfile(
            name="individual_tests",
            target_rules=("ACC-008",),
            patient_name="present",
            patient_sex="F",
            specimen_type="biopsy",
            anatomic_site="breast",
            fixative="formalin",
            fixation_time_hours=24.0,
            ordered_tests=("ER", "PR"),
            priority="routine",
            billing_info_present=True,
            age=50,
        )
        data = generate_order_data(profile, 0)
        assert data["ordered_tests"] == ["ER", "PR"]

    def test_event_data_has_all_required_keys(self) -> None:
        required_keys = {
            "patient_name",
            "age",
            "sex",
            "specimen_type",
            "anatomic_site",
            "fixative",
            "fixation_time_hours",
            "ordered_tests",
            "priority",
            "billing_info_present",
        }
        data = generate_order_data(STANDARD_INVASIVE, 0)
        assert set(data.keys()) == required_keys


# --- Type safety of generated data ---


class TestTypeSafety:
    def test_all_profiles_generate_valid_data(self) -> None:
        for i, profile in enumerate(ALL_PROFILES):
            data = generate_order_data(profile, i)
            assert isinstance(data, dict), f"Profile {profile.name} failed"

    def test_field_types(self) -> None:
        data = generate_order_data(STANDARD_INVASIVE, 0)
        assert isinstance(data["patient_name"], str)
        assert isinstance(data["age"], int)
        assert isinstance(data["sex"], str)
        assert isinstance(data["specimen_type"], str)
        assert isinstance(data["anatomic_site"], str)
        assert isinstance(data["fixative"], str)
        assert isinstance(data["fixation_time_hours"], float)
        assert isinstance(data["ordered_tests"], list)
        assert isinstance(data["priority"], str)
        assert isinstance(data["billing_info_present"], bool)

    def test_nullable_fields_when_none(self) -> None:
        data = generate_order_data(MISSING_PATIENT_NAME, 0)
        assert data["patient_name"] is None

        data = generate_order_data(MISSING_PATIENT_SEX, 0)
        assert data["sex"] is None

        data = generate_order_data(MISSING_FIXATION_TIME, 0)
        assert data["fixation_time_hours"] is None

    def test_order_construction_from_event_data(self) -> None:
        """Generated data must successfully construct an Order object."""
        for i, profile in enumerate(ALL_PROFILES):
            data = generate_order_data(profile, i)
            expanded_tests: list[str] = []
            for test in data["ordered_tests"]:
                expanded_tests.extend(expand_panel(test))
            Order(
                order_id=f"ORD-{i:04d}",
                scenario_id="SC-000",
                patient_name=data["patient_name"],
                patient_age=data["age"],
                patient_sex=data["sex"],
                specimen_type=data["specimen_type"],
                anatomic_site=data["anatomic_site"],
                fixative=data["fixative"],
                fixation_time_hours=data["fixation_time_hours"],
                ordered_tests=expanded_tests,
                priority=data["priority"],
                billing_info_present=data["billing_info_present"],
                current_state="ACCESSIONING",
            )


# --- Profile-to-rule mapping verification ---


class TestProfileRuleTriggers:
    """Verify each profile triggers its intended accessioning rules.

    These tests check the order data against rule trigger conditions from
    the rule catalog (knowledge_base/workflow_states.yaml).
    """

    def test_standard_invasive_all_valid(self) -> None:
        data = generate_order_data(STANDARD_INVASIVE, 0)
        assert data["patient_name"] is not None  # ACC-001 not triggered
        assert data["sex"] is not None  # ACC-002 not triggered
        assert data["anatomic_site"] == "breast"  # ACC-003 not triggered
        assert data["specimen_type"] == "biopsy"  # ACC-004 not triggered
        assert data["fixative"] == "formalin"  # ACC-005 not triggered
        assert 6.0 <= data["fixation_time_hours"] <= 72.0  # ACC-006 not triggered
        assert data["billing_info_present"] is True  # ACC-007 not triggered

    def test_standard_benign_all_valid(self) -> None:
        data = generate_order_data(STANDARD_BENIGN, 0)
        assert data["patient_name"] is not None
        assert data["sex"] is not None
        assert data["anatomic_site"] == "breast"
        assert data["specimen_type"] == "resection"
        assert data["fixative"] == "formalin"
        assert 6.0 <= data["fixation_time_hours"] <= 72.0
        assert data["billing_info_present"] is True

    def test_missing_patient_name_triggers_acc001(self) -> None:
        data = generate_order_data(MISSING_PATIENT_NAME, 0)
        assert data["patient_name"] is None
        assert MISSING_PATIENT_NAME.target_rules == ("ACC-001",)

    def test_missing_patient_sex_triggers_acc002(self) -> None:
        data = generate_order_data(MISSING_PATIENT_SEX, 0)
        assert data["sex"] is None
        assert MISSING_PATIENT_SEX.target_rules == ("ACC-002",)

    def test_invalid_anatomic_site_triggers_acc003(self) -> None:
        data = generate_order_data(INVALID_ANATOMIC_SITE, 0)
        assert data["anatomic_site"] == "lung"
        assert INVALID_ANATOMIC_SITE.target_rules == ("ACC-003",)

    def test_incompatible_specimen_triggers_acc004(self) -> None:
        data = generate_order_data(INCOMPATIBLE_SPECIMEN, 0)
        assert data["specimen_type"] == "FNA"
        assert INCOMPATIBLE_SPECIMEN.target_rules == ("ACC-004",)

    def test_her2_not_formalin_triggers_acc005(self) -> None:
        data = generate_order_data(HER2_NOT_FORMALIN, 0)
        # HER2 is in Breast IHC Panel
        expanded = []
        for test in data["ordered_tests"]:
            expanded.extend(expand_panel(test))
        assert "HER2" in expanded
        assert data["fixative"] != "formalin"
        assert HER2_NOT_FORMALIN.target_rules == ("ACC-005",)

    def test_her2_fixation_under_triggers_acc006(self) -> None:
        data = generate_order_data(HER2_FIXATION_UNDER, 0)
        expanded = []
        for test in data["ordered_tests"]:
            expanded.extend(expand_panel(test))
        assert "HER2" in expanded
        assert data["fixation_time_hours"] < 6.0
        assert HER2_FIXATION_UNDER.target_rules == ("ACC-006",)

    def test_her2_fixation_over_triggers_acc006(self) -> None:
        data = generate_order_data(HER2_FIXATION_OVER, 0)
        expanded = []
        for test in data["ordered_tests"]:
            expanded.extend(expand_panel(test))
        assert "HER2" in expanded
        assert data["fixation_time_hours"] > 72.0
        assert HER2_FIXATION_OVER.target_rules == ("ACC-006",)

    def test_missing_billing_triggers_acc007(self) -> None:
        data = generate_order_data(MISSING_BILLING, 0)
        assert data["billing_info_present"] is False
        assert MISSING_BILLING.target_rules == ("ACC-007",)

    def test_multi_defect_hold_reject(self) -> None:
        """ACC-001 (missing name) + ACC-003 (invalid site)."""
        data = generate_order_data(MULTI_DEFECT_HOLD_REJECT, 0)
        assert data["patient_name"] is None  # ACC-001
        assert data["anatomic_site"] == "lung"  # ACC-003
        assert set(MULTI_DEFECT_HOLD_REJECT.target_rules) == {"ACC-001", "ACC-003"}

    def test_multi_defect_dual_hold(self) -> None:
        """ACC-001 (missing name) + ACC-002 (missing sex) — both HOLD."""
        data = generate_order_data(MULTI_DEFECT_DUAL_HOLD, 0)
        assert data["patient_name"] is None  # ACC-001
        assert data["sex"] is None  # ACC-002
        assert set(MULTI_DEFECT_DUAL_HOLD.target_rules) == {"ACC-001", "ACC-002"}

    def test_multi_defect_hold_proceed(self) -> None:
        """ACC-001 (missing name) + ACC-007 (missing billing)."""
        data = generate_order_data(MULTI_DEFECT_HOLD_PROCEED, 0)
        assert data["patient_name"] is None  # ACC-001
        assert data["billing_info_present"] is False  # ACC-007
        assert set(MULTI_DEFECT_HOLD_PROCEED.target_rules) == {"ACC-001", "ACC-007"}

    def test_missing_fixation_time_triggers_acc009(self) -> None:
        """Null fixation time with HER2 ordered → ACC-009."""
        data = generate_order_data(MISSING_FIXATION_TIME, 0)
        expanded: list[str] = []
        for test in data["ordered_tests"]:
            expanded.extend(expand_panel(test))
        assert "HER2" in expanded
        assert data["fixation_time_hours"] is None
        assert MISSING_FIXATION_TIME.target_rules == ("ACC-009",)

    def test_null_fixation_no_her2_does_not_trigger_acc009(self) -> None:
        """Null fixation without HER2 — ACC-009 must NOT fire."""
        profile = OrderProfile(
            name="null_fixation_no_her2",
            target_rules=("ACC-008",),
            patient_name="present",
            patient_sex="F",
            specimen_type="biopsy",
            anatomic_site="breast",
            fixative="formalin",
            fixation_time_hours=None,
            ordered_tests=("ER", "PR"),
            priority="routine",
            billing_info_present=True,
            age=50,
        )
        data = generate_order_data(profile, 0)
        expanded: list[str] = []
        for test in data["ordered_tests"]:
            expanded.extend(expand_panel(test))
        assert "HER2" not in expanded
        assert data["fixation_time_hours"] is None
        assert profile.target_rules == ("ACC-008",)

    def test_valid_fixation_with_her2_does_not_trigger_acc009(self) -> None:
        """Valid fixation time with HER2 — ACC-009 must NOT fire."""
        data = generate_order_data(STANDARD_INVASIVE, 0)
        expanded: list[str] = []
        for test in data["ordered_tests"]:
            expanded.extend(expand_panel(test))
        assert "HER2" in expanded
        assert isinstance(data["fixation_time_hours"], float)
        assert 6.0 <= data["fixation_time_hours"] <= 72.0
        assert STANDARD_INVASIVE.target_rules == ("ACC-008",)

    def test_bad_fixation_no_her2_does_not_trigger_acc005_006(self) -> None:
        """Bad fixation without HER2 — ACC-005/ACC-006 must NOT fire."""
        data = generate_order_data(BAD_FIXATION_NO_HER2, 0)
        expanded: list[str] = []
        for test in data["ordered_tests"]:
            expanded.extend(expand_panel(test))
        assert "HER2" not in expanded  # No HER2 ordered
        assert data["fixative"] != "formalin"  # Bad fixative
        assert data["fixation_time_hours"] < 6.0  # Out-of-range fixation
        # Should be ACCEPTED — only ACC-008 applies
        assert BAD_FIXATION_NO_HER2.target_rules == ("ACC-008",)


# --- Boundary tests ---


class TestBoundaryConditions:
    def test_fixation_boundary_low_at_6_hours(self) -> None:
        data = generate_order_data(FIXATION_BOUNDARY_LOW, 0)
        assert data["fixation_time_hours"] == 6.0
        # 6.0 is within valid range [6, 72] — should NOT trigger ACC-006
        assert FIXATION_BOUNDARY_LOW.target_rules == ("ACC-008",)

    def test_fixation_boundary_high_at_72_hours(self) -> None:
        data = generate_order_data(FIXATION_BOUNDARY_HIGH, 0)
        assert data["fixation_time_hours"] == 72.0
        # 72.0 is within valid range [6, 72] — should NOT trigger ACC-006
        assert FIXATION_BOUNDARY_HIGH.target_rules == ("ACC-008",)

    def test_under_boundary_at_5_hours(self) -> None:
        data = generate_order_data(HER2_FIXATION_UNDER, 0)
        assert data["fixation_time_hours"] == 5.0
        # 5.0 is outside valid range — should trigger ACC-006
        assert HER2_FIXATION_UNDER.target_rules == ("ACC-006",)

    def test_over_boundary_at_73_hours(self) -> None:
        data = generate_order_data(HER2_FIXATION_OVER, 0)
        assert data["fixation_time_hours"] == 73.0
        # 73.0 is outside valid range — should trigger ACC-006
        assert HER2_FIXATION_OVER.target_rules == ("ACC-006",)


# --- ALL_PROFILES collection ---


class TestAllProfiles:
    def test_17_profiles(self) -> None:
        assert len(ALL_PROFILES) == 17

    def test_unique_names(self) -> None:
        names = [p.name for p in ALL_PROFILES]
        assert len(names) == len(set(names))

    def test_all_profiles_have_target_rules(self) -> None:
        for profile in ALL_PROFILES:
            assert len(profile.target_rules) >= 1, f"Profile {profile.name} has no target_rules"

    def test_expand_panel_integration(self) -> None:
        """All profiles with Breast IHC Panel expand correctly."""
        for profile in ALL_PROFILES:
            for test in profile.ordered_tests:
                expanded = expand_panel(test)
                assert isinstance(expanded, list)
                assert len(expanded) >= 1
