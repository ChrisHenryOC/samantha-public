"""Tests for flag lifecycle validation.

Verifies that flag set_at references, cleared_by values, and cross-references
between flags and rules are consistent.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.workflow.models import VALID_FLAGS


@pytest.fixture()
def flags(workflow_data: dict[str, Any]) -> list[dict[str, Any]]:
    return workflow_data["flags"]


@pytest.fixture()
def state_ids(workflow_data: dict[str, Any]) -> set[str]:
    return {s["id"] for s in workflow_data["states"]}


@pytest.fixture()
def rule_steps(workflow_data: dict[str, Any]) -> set[str]:
    return {r["step"] for r in workflow_data["rules"]}


class TestFlagSetAt:
    def test_set_at_references_valid_state_or_step(
        self, flags: list[dict[str, Any]], state_ids: set[str], rule_steps: set[str]
    ) -> None:
        valid_refs = state_ids | rule_steps
        for f in flags:
            set_at = f["set_at"]
            if isinstance(set_at, str):
                set_at = [set_at]
            for ref in set_at:
                assert ref in valid_refs, f"Flag {f['flag_id']} set_at references invalid: {ref}"


class TestFlagClearedBy:
    def test_cleared_by_non_empty(self, flags: list[dict[str, Any]]) -> None:
        for f in flags:
            assert f["cleared_by"], f"Flag {f['flag_id']} has empty cleared_by"


class TestFlagRuleCrossReferences:
    def test_missing_info_proceed_referenced_in_rule_triggers(
        self, workflow_data: dict[str, Any]
    ) -> None:
        """The MISSING_INFO_PROCEED flag should be referenced by at least one rule trigger."""
        triggers = [r["trigger"] for r in workflow_data["rules"]]
        found = any("MISSING_INFO_PROCEED" in t for t in triggers)
        assert found, "No rule trigger references MISSING_INFO_PROCEED"


class TestFlagIDsMatchModel:
    def test_flag_ids_match_valid_flags(self, flags: list[dict[str, Any]]) -> None:
        yaml_flag_ids = {f["flag_id"] for f in flags}
        assert yaml_flag_ids == VALID_FLAGS, (
            f"YAML flags {yaml_flag_ids} != models.VALID_FLAGS {VALID_FLAGS}"
        )


class TestFlagEffects:
    def test_effects_non_empty(self, flags: list[dict[str, Any]]) -> None:
        for f in flags:
            assert f["effect"], f"Flag {f['flag_id']} has empty effect"
