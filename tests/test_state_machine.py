"""Tests for the workflow state machine."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.workflow.state_machine import StateMachine


@pytest.fixture(scope="module")
def sm() -> StateMachine:
    return StateMachine()


# --- YAML loading ---


class TestYAMLLoading:
    def test_loads_with_safe_load(self, sm: StateMachine) -> None:
        # If we got here, safe_load succeeded — verify we have states.
        assert len(sm.get_all_states()) > 0

    def test_has_24_states(self, sm: StateMachine) -> None:
        # 24 states as defined in workflow-overview.md.
        assert len(sm.get_all_states()) == 24

    def test_rejects_state_missing_required_key(self, tmp_path: Path) -> None:
        """State entry missing a required key raises ValueError."""
        p = tmp_path / "bad.yaml"
        p.write_text(
            "states:\n"
            "  - phase: test\n"
            "    description: no id\n"
            "    terminal: false\n"
            "transitions: []\n"
            "rules: []\n"
            "flags: []\n"
            "terminal_states: []\n"
        )
        with pytest.raises(ValueError, match="missing required keys"):
            StateMachine(yaml_path=p)

    def test_rejects_transition_missing_required_key(self, tmp_path: Path) -> None:
        """Transition entry missing a required key raises ValueError."""
        p = tmp_path / "bad.yaml"
        p.write_text(
            "states:\n"
            "  - id: S1\n"
            "    phase: test\n"
            "    description: s\n"
            "    terminal: false\n"
            "transitions:\n"
            "  - from: S1\n"
            "    to: S1\n"
            "rules: []\n"
            "flags: []\n"
            "terminal_states: []\n"
        )
        with pytest.raises(ValueError, match="missing required keys"):
            StateMachine(yaml_path=p)

    def test_has_40_rules(self, sm: StateMachine) -> None:
        # 40 rules across all steps as defined in rule-catalog.md.
        all_rules = (
            sm.get_rules_for_step("ACCESSIONING")
            + sm.get_rules_for_step("SAMPLE_PREP")
            + sm.get_rules_for_step("HE_QC")
            + sm.get_rules_for_step("PATHOLOGIST_HE_REVIEW")
            + sm.get_rules_for_step("IHC")
            + sm.get_rules_for_step("RESULTING")
        )
        assert len(all_rules) == 40


# --- Transitions ---


class TestTransitions:
    def test_valid_transition(self, sm: StateMachine) -> None:
        assert sm.is_valid_transition("ACCESSIONING", "ACCEPTED") is True

    def test_invalid_transition(self, sm: StateMachine) -> None:
        assert sm.is_valid_transition("ACCESSIONING", "ORDER_COMPLETE") is False

    def test_self_loop_sample_prep_processing(self, sm: StateMachine) -> None:
        assert sm.is_valid_transition("SAMPLE_PREP_PROCESSING", "SAMPLE_PREP_PROCESSING") is True

    def test_self_loop_sample_prep_embedding(self, sm: StateMachine) -> None:
        assert sm.is_valid_transition("SAMPLE_PREP_EMBEDDING", "SAMPLE_PREP_EMBEDDING") is True

    def test_self_loop_sample_prep_sectioning(self, sm: StateMachine) -> None:
        assert sm.is_valid_transition("SAMPLE_PREP_SECTIONING", "SAMPLE_PREP_SECTIONING") is True

    def test_self_loop_ihc_staining(self, sm: StateMachine) -> None:
        assert sm.is_valid_transition("IHC_STAINING", "IHC_STAINING") is True

    def test_self_loop_ihc_qc(self, sm: StateMachine) -> None:
        assert sm.is_valid_transition("IHC_QC", "IHC_QC") is True

    def test_get_valid_transitions_from_accessioning(self, sm: StateMachine) -> None:
        transitions = sm.get_valid_transitions("ACCESSIONING")
        targets = {t.to_state for t in transitions}
        assert targets == {
            "ACCEPTED",
            "MISSING_INFO_HOLD",
            "MISSING_INFO_PROCEED",
            "DO_NOT_PROCESS",
        }

    def test_get_valid_transitions_unknown_state(self, sm: StateMachine) -> None:
        assert sm.get_valid_transitions("NONEXISTENT") == []


# --- Terminal states ---


class TestTerminalStates:
    def test_three_terminal_states(self, sm: StateMachine) -> None:
        terminal_count = sum(1 for s in sm.get_all_states() if sm.is_terminal_state(s))
        assert terminal_count == 3

    def test_order_complete_is_terminal(self, sm: StateMachine) -> None:
        assert sm.is_terminal_state("ORDER_COMPLETE") is True

    def test_order_terminated_is_terminal(self, sm: StateMachine) -> None:
        assert sm.is_terminal_state("ORDER_TERMINATED") is True

    def test_order_terminated_qns_is_terminal(self, sm: StateMachine) -> None:
        assert sm.is_terminal_state("ORDER_TERMINATED_QNS") is True

    def test_accessioning_not_terminal(self, sm: StateMachine) -> None:
        assert sm.is_terminal_state("ACCESSIONING") is False


# --- Rule ordering ---


class TestRuleOrdering:
    def test_accessioning_rules_sorted_by_severity(self, sm: StateMachine) -> None:
        rules = sm.get_rules_for_step("ACCESSIONING")
        severities = [r.severity for r in rules]
        # REJECT rules first, then HOLD, then PROCEED, then ACCEPT
        assert severities[0] == "REJECT"
        assert severities[-1] == "ACCEPT"

    def test_sample_prep_rules_sorted_by_priority(self, sm: StateMachine) -> None:
        rules = sm.get_rules_for_step("SAMPLE_PREP")
        priorities = [r.priority for r in rules]
        assert all(
            a <= b
            for a, b in zip(priorities, priorities[1:], strict=False)
            if a is not None and b is not None
        )

    def test_ihc_rules_have_applies_at(self, sm: StateMachine) -> None:
        rules = sm.get_rules_for_step("IHC")
        for rule in rules:
            assert rule.applies_at is not None, f"{rule.rule_id} missing applies_at"


# --- get_rules_for_state ---


class TestRulesForState:
    def test_ihc_staining_returns_ihc_rules(self, sm: StateMachine) -> None:
        rules = sm.get_rules_for_state("IHC_STAINING")
        assert len(rules) > 0
        rule_ids = {r.rule_id for r in rules}
        assert "IHC-001" in rule_ids

    def test_ihc_qc_returns_ihc_rules(self, sm: StateMachine) -> None:
        rules = sm.get_rules_for_state("IHC_QC")
        rule_ids = {r.rule_id for r in rules}
        assert "IHC-002" in rule_ids
        assert "IHC-003" in rule_ids

    def test_accessioning_returns_accessioning_rules(self, sm: StateMachine) -> None:
        rules = sm.get_rules_for_state("ACCESSIONING")
        assert len(rules) == 9
        assert all(r.rule_id.startswith("ACC-") for r in rules)

    def test_he_staining_returns_empty(self, sm: StateMachine) -> None:
        # HE_STAINING has no rules — it's a pass-through state.
        rules = sm.get_rules_for_state("HE_STAINING")
        assert rules == []

    def test_terminal_state_returns_empty(self, sm: StateMachine) -> None:
        rules = sm.get_rules_for_state("ORDER_COMPLETE")
        assert rules == []

    def test_unknown_state_raises(self, sm: StateMachine) -> None:
        with pytest.raises(ValueError, match="Unknown state"):
            sm.get_rules_for_state("NONEXISTENT")


# --- Flag vocabulary ---


class TestFlagVocabulary:
    def test_five_flags(self, sm: StateMachine) -> None:
        assert len(sm.get_flag_vocabulary()) == 5

    def test_fixation_warning_set_at_is_list(self, sm: StateMachine) -> None:
        vocab = sm.get_flag_vocabulary()
        set_at = vocab["FIXATION_WARNING"]["set_at"]
        assert isinstance(set_at, list)
        assert len(set_at) == 2


# --- Vocabulary accessors ---


class TestVocabularyAccessors:
    def test_get_all_rule_ids(self, sm: StateMachine) -> None:
        rule_ids = sm.get_all_rule_ids()
        assert isinstance(rule_ids, frozenset)
        assert "ACC-001" in rule_ids
        assert "IHC-001" in rule_ids

    def test_get_all_flag_ids(self, sm: StateMachine) -> None:
        flag_ids = sm.get_all_flag_ids()
        assert isinstance(flag_ids, frozenset)
        assert "FIXATION_WARNING" in flag_ids

    def test_get_all_states_returns_frozenset(self, sm: StateMachine) -> None:
        states = sm.get_all_states()
        assert isinstance(states, frozenset)
        assert "ACCESSIONING" in states


# --- Singleton caching ---


class TestGetInstance:
    def test_returns_same_instance(self) -> None:
        a = StateMachine.get_instance()
        b = StateMachine.get_instance()
        assert a is b

    def test_custom_path_bypasses_cache(self) -> None:
        from pathlib import Path

        default = StateMachine.get_instance()
        yaml_path = (
            Path(__file__).resolve().parent.parent / "knowledge_base" / "workflow_states.yaml"
        )
        custom = StateMachine.get_instance(yaml_path)
        assert custom is not default
