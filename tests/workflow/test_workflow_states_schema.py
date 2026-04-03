"""Schema validation tests for workflow_states.yaml.

Verifies internal consistency of the YAML source of truth: state references
in transitions, rule IDs, severity/priority constraints, and flag references.
"""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture()
def state_ids(workflow_data: dict[str, Any]) -> set[str]:
    return {s["id"] for s in workflow_data["states"]}


@pytest.fixture()
def terminal_ids(workflow_data: dict[str, Any]) -> set[str]:
    return set(workflow_data["terminal_states"])


@pytest.fixture()
def transitions(workflow_data: dict[str, Any]) -> list[dict[str, str]]:
    return workflow_data["transitions"]


@pytest.fixture()
def rules(workflow_data: dict[str, Any]) -> list[dict[str, Any]]:
    return workflow_data["rules"]


# --- State reference integrity ---


class TestStateReferences:
    def test_transition_from_states_exist(
        self, transitions: list[dict[str, str]], state_ids: set[str]
    ) -> None:
        for t in transitions:
            assert t["from"] in state_ids, f"Unknown from-state: {t['from']}"

    def test_transition_to_states_exist(
        self, transitions: list[dict[str, str]], state_ids: set[str]
    ) -> None:
        for t in transitions:
            assert t["to"] in state_ids, f"Unknown to-state: {t['to']}"

    def test_terminal_states_no_outbound_transitions(
        self, transitions: list[dict[str, str]], terminal_ids: set[str]
    ) -> None:
        outbound_from_terminal = [t for t in transitions if t["from"] in terminal_ids]
        assert outbound_from_terminal == [], (
            f"Terminal states have outbound transitions: {outbound_from_terminal}"
        )

    def test_non_terminal_states_have_outbound_transitions(
        self,
        transitions: list[dict[str, str]],
        state_ids: set[str],
        terminal_ids: set[str],
    ) -> None:
        from_states = {t["from"] for t in transitions}
        non_terminal = state_ids - terminal_ids
        missing = non_terminal - from_states
        assert missing == set(), f"Non-terminal states with no outbound transitions: {missing}"

    def test_no_orphaned_states(
        self, transitions: list[dict[str, str]], state_ids: set[str]
    ) -> None:
        """Every state must appear in at least one transition (from or to) or be ACCESSIONING."""
        referenced = set()
        for t in transitions:
            referenced.add(t["from"])
            referenced.add(t["to"])
        orphaned = state_ids - referenced - {"ACCESSIONING"}
        assert orphaned == set(), f"Orphaned states: {orphaned}"


# --- Rule constraints ---


class TestRuleConstraints:
    def test_rule_ids_unique(self, rules: list[dict[str, Any]]) -> None:
        ids = [r["rule_id"] for r in rules]
        assert len(ids) == len(set(ids)), f"Duplicate rule IDs: {ids}"

    def test_accessioning_severities_valid(self, rules: list[dict[str, Any]]) -> None:
        valid_severities = {"REJECT", "HOLD", "PROCEED", "ACCEPT"}
        for r in rules:
            if r["step"] == "ACCESSIONING":
                assert r.get("severity") in valid_severities, (
                    f"{r['rule_id']} has invalid severity: {r.get('severity')}"
                )

    def test_priorities_positive_integers(self, rules: list[dict[str, Any]]) -> None:
        for r in rules:
            if "priority" in r:
                assert isinstance(r["priority"], int) and r["priority"] > 0, (
                    f"{r['rule_id']} has invalid priority: {r['priority']}"
                )

    def test_no_duplicate_priorities_within_step(self, rules: list[dict[str, Any]]) -> None:
        by_step: dict[str, list[int]] = {}
        for r in rules:
            if "priority" in r:
                by_step.setdefault(r["step"], []).append(r["priority"])
        for step, priorities in by_step.items():
            assert len(priorities) == len(set(priorities)), (
                f"Step {step} has duplicate priorities: {priorities}"
            )

    def test_ihc_rules_have_applies_at(self, rules: list[dict[str, Any]]) -> None:
        for r in rules:
            if r["step"] == "IHC":
                assert "applies_at" in r, f"{r['rule_id']} missing applies_at"

    def test_he_step_split(self, rules: list[dict[str, Any]]) -> None:
        """HE_QC and PATHOLOGIST_HE_REVIEW are separate rule steps."""
        he_qc_rules = [r for r in rules if r["step"] == "HE_QC"]
        he_review_rules = [r for r in rules if r["step"] == "PATHOLOGIST_HE_REVIEW"]
        assert len(he_qc_rules) > 0, "No HE_QC rules"
        assert len(he_review_rules) > 0, "No PATHOLOGIST_HE_REVIEW rules"

    def test_rules_reference_valid_steps(self, rules: list[dict[str, Any]]) -> None:
        valid_steps = {
            "ACCESSIONING",
            "SAMPLE_PREP",
            "HE_QC",
            "PATHOLOGIST_HE_REVIEW",
            "IHC",
            "RESULTING",
        }
        for r in rules:
            assert r["step"] in valid_steps, f"{r['rule_id']} references unknown step: {r['step']}"


# --- Flag constraints ---


class TestFlagConstraints:
    def test_flag_set_at_valid(self, workflow_data: dict[str, Any], state_ids: set[str]) -> None:
        """Flag set_at values must reference valid states or rule steps."""
        valid_refs = state_ids | {
            "ACCESSIONING",
            "SAMPLE_PREP",
            "HE_QC",
            "PATHOLOGIST_HE_REVIEW",
            "IHC",
            "RESULTING",
        }
        for f in workflow_data["flags"]:
            set_at = f["set_at"]
            if isinstance(set_at, str):
                set_at = [set_at]
            for ref in set_at:
                assert ref in valid_refs, f"Flag {f['flag_id']} has invalid set_at: {ref}"
