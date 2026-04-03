"""Tests for the skill document loader."""

from __future__ import annotations

from src.prediction.skill_loader import (
    _STATE_TO_SKILL_STEP,
    _STEP_TO_SKILL_FILE,
    get_skill_for_state,
    load_skill,
)


class TestLoadSkill:
    """Tests for load_skill() function."""

    def test_loads_accessioning_skill(self) -> None:
        result = load_skill("ACCESSIONING")
        assert result is not None
        assert "Accessioning Evaluation Skill" in result

    def test_loads_sample_prep_skill(self) -> None:
        result = load_skill("SAMPLE_PREP")
        assert result is not None
        assert "Sample Prep" in result

    def test_loads_ihc_skill(self) -> None:
        result = load_skill("IHC")
        assert result is not None
        assert "IHC" in result

    def test_unknown_step_returns_none(self) -> None:
        result = load_skill("NONEXISTENT_STEP")
        assert result is None

    def test_all_referenced_skill_files_exist(self) -> None:
        """Every step in _STEP_TO_SKILL_FILE has a loadable skill."""
        for step in _STEP_TO_SKILL_FILE:
            result = load_skill(step)
            assert result is not None, f"Skill file missing for step: {step}"
            assert len(result) > 50, f"Skill file too short for step: {step}"


class TestGetSkillForState:
    """Tests for get_skill_for_state() function."""

    def test_accessioning_state(self) -> None:
        result = get_skill_for_state("ACCESSIONING")
        assert result is not None
        assert "ACC-001" in result

    def test_sample_prep_states_map_to_same_skill(self) -> None:
        """All SAMPLE_PREP states return the same skill."""
        states = [
            "ACCEPTED",
            "MISSING_INFO_PROCEED",
            "SAMPLE_PREP_PROCESSING",
            "SAMPLE_PREP_EMBEDDING",
            "SAMPLE_PREP_SECTIONING",
            "SAMPLE_PREP_QC",
        ]
        skills = [get_skill_for_state(s) for s in states]
        assert all(s is not None for s in skills)
        assert len(set(id(s) for s in skills)) == 1  # Same cached object

    def test_ihc_states_map_to_ihc_skill(self) -> None:
        """All IHC states return the IHC skill."""
        states = [
            "IHC_STAINING",
            "IHC_QC",
            "IHC_SCORING",
            "SUGGEST_FISH_REFLEX",
            "FISH_SEND_OUT",
        ]
        for state in states:
            result = get_skill_for_state(state)
            assert result is not None, f"No skill for IHC state: {state}"
            assert "IHC" in result

    def test_resulting_states_map_to_resulting_skill(self) -> None:
        for state in ["RESULTING", "RESULTING_HOLD", "PATHOLOGIST_SIGNOUT", "REPORT_GENERATION"]:
            result = get_skill_for_state(state)
            assert result is not None, f"No skill for state: {state}"

    def test_terminal_state_returns_none(self) -> None:
        assert get_skill_for_state("ORDER_COMPLETE") is None
        assert get_skill_for_state("ORDER_TERMINATED") is None
        assert get_skill_for_state("ORDER_TERMINATED_QNS") is None

    def test_pass_through_state_returns_none(self) -> None:
        assert get_skill_for_state("MISSING_INFO_HOLD") is None
        assert get_skill_for_state("DO_NOT_PROCESS") is None

    def test_he_staining_has_skill(self) -> None:
        """HE_STAINING maps to the HE_QC skill (includes pass-through guidance)."""
        result = get_skill_for_state("HE_STAINING")
        assert result is not None
        assert "HE_STAINING" in result

    def test_all_mapped_states_return_content(self) -> None:
        """Every state in _STATE_TO_SKILL_STEP returns non-None content."""
        for state in _STATE_TO_SKILL_STEP:
            result = get_skill_for_state(state)
            assert result is not None, f"No skill for mapped state: {state}"


class TestSkillContentQuality:
    """Verify skill documents contain expected rule references."""

    def test_accessioning_skill_has_all_rule_ids(self) -> None:
        skill = load_skill("ACCESSIONING")
        assert skill is not None
        for rule_id in [
            "ACC-001",
            "ACC-002",
            "ACC-003",
            "ACC-004",
            "ACC-005",
            "ACC-006",
            "ACC-007",
            "ACC-008",
            "ACC-009",
        ]:
            assert rule_id in skill, f"Missing {rule_id} in accessioning skill"

    def test_accessioning_skill_has_numeric_comparison(self) -> None:
        """The skill must decompose the 6-72 range into explicit comparisons."""
        skill = load_skill("ACCESSIONING")
        assert skill is not None
        assert "< 6.0" in skill
        assert "> 72.0" in skill

    def test_accessioning_skill_has_worked_example(self) -> None:
        skill = load_skill("ACCESSIONING")
        assert skill is not None
        assert "5.0 < 6.0" in skill
        assert "Example" in skill

    def test_sample_prep_skill_has_state_sequence(self) -> None:
        skill = load_skill("SAMPLE_PREP")
        assert skill is not None
        assert "SAMPLE_PREP_PROCESSING" in skill
        assert "SAMPLE_PREP_EMBEDDING" in skill
        assert "HE_STAINING" in skill

    def test_ihc_001_self_loops_to_ihc_staining(self) -> None:
        """IHC-001 must route to IHC_STAINING (self-loop), not IHC_QC."""
        skill = load_skill("IHC")
        assert skill is not None
        # Find the IHC-001 row and verify it contains IHC_STAINING
        lines = skill.split("\n")
        ihc_001_lines = [line for line in lines if "IHC-001" in line]
        assert ihc_001_lines, "IHC-001 not found in IHC skill"
        for line in ihc_001_lines:
            assert "IHC_STAINING" in line, f"IHC-001 should self-loop to IHC_STAINING, got: {line}"

    def test_ihc_004_not_at_ihc_staining_section(self) -> None:
        """IHC-004 applies at IHC_QC, not IHC_STAINING."""
        skill = load_skill("IHC")
        assert skill is not None
        # Split by IHC_STAINING and IHC_QC sections
        staining_section = skill.split("### At IHC_STAINING")[1].split("### At IHC_QC")[0]
        assert "IHC-004" not in staining_section, (
            "IHC-004 should not appear in the IHC_STAINING section"
        )

    def test_ihc_skill_has_fish_path(self) -> None:
        skill = load_skill("IHC")
        assert skill is not None
        assert "SUGGEST_FISH_REFLEX" in skill
        assert "FISH_SEND_OUT" in skill

    def test_ihc_qc_has_all_slides_complete_check(self) -> None:
        """IHC QC section must explicitly reference all_slides_complete field."""
        skill = load_skill("IHC")
        assert skill is not None
        assert "all_slides_complete" in skill

    def test_ihc_skill_clears_fish_suggested(self) -> None:
        """FISH_SUGGESTED must be removed when IHC-008 or IHC-009 applies."""
        skill = load_skill("IHC")
        assert skill is not None
        assert "REMOVE FISH_SUGGESTED" in skill

    def test_sample_prep_clears_recut_requested(self) -> None:
        """RECUT_REQUESTED must be removed when recut completes."""
        skill = load_skill("SAMPLE_PREP")
        assert skill is not None
        assert "RECUT_REQUESTED" in skill
        assert "REMOVE RECUT_REQUESTED" in skill

    def test_resulting_clears_missing_info(self) -> None:
        """MISSING_INFO_PROCEED must be removed when RES-002 applies."""
        skill = load_skill("RESULTING")
        assert skill is not None
        assert "REMOVE MISSING_INFO_PROCEED" in skill

    def test_accessioning_has_fixation_warning(self) -> None:
        """Accessioning skill must include FIXATION_WARNING for borderline fixation."""
        skill = load_skill("ACCESSIONING")
        assert skill is not None
        assert "FIXATION_WARNING" in skill
