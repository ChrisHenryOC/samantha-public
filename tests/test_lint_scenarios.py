"""Tests for the scenario flag-accumulation linter."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.simulator.lint_scenarios import (
    FLAG_CLEARING_EVENTS,
    FLAG_CLEARING_RULES,
    FlagLintWarning,
    check_flag_consistency,
    lint_scenarios,
    main,
)
from src.simulator.schema import ExpectedOutput, Scenario, ScenarioStep


def _make_scenario(
    scenario_id: str,
    steps: list[tuple[str, list[str], list[str], str]],
) -> Scenario:
    """Helper to build a Scenario from compact step tuples.

    Each tuple: (event_type, applied_rules, flags, next_state).
    The first step must be ``order_received``.
    """
    scenario_steps = []
    for i, (event_type, rules, flags, state) in enumerate(steps, start=1):
        scenario_steps.append(
            ScenarioStep(
                step=i,
                event_type=event_type,
                event_data={},
                expected_output=ExpectedOutput(
                    next_state=state,
                    applied_rules=tuple(rules),
                    flags=tuple(flags),
                ),
            )
        )
    return Scenario(
        scenario_id=scenario_id,
        category="rule_coverage",
        description="Test scenario",
        steps=tuple(scenario_steps),
    )


# -----------------------------------------------------------------------
# Core logic tests
# -----------------------------------------------------------------------


class TestCheckFlagConsistency:
    def test_no_flags_no_warnings(self) -> None:
        scenario = _make_scenario(
            "SC-001",
            [
                ("order_received", ["ACC-008"], [], "ACCEPTED"),
                ("grossing_complete", ["SP-001"], [], "SAMPLE_PREP_PROCESSING"),
            ],
        )
        assert check_flag_consistency(scenario) == []

    def test_single_step_no_warnings(self) -> None:
        scenario = _make_scenario(
            "SC-002",
            [("order_received", ["ACC-007"], ["MISSING_INFO_PROCEED"], "MISSING_INFO_PROCEED")],
        )
        assert check_flag_consistency(scenario) == []

    def test_flag_persists_no_warning(self) -> None:
        scenario = _make_scenario(
            "SC-003",
            [
                ("order_received", ["ACC-007"], ["MISSING_INFO_PROCEED"], "MISSING_INFO_PROCEED"),
                (
                    "missing_info_received",
                    ["RES-001"],
                    ["MISSING_INFO_PROCEED"],
                    "MISSING_INFO_PROCEED",
                ),
            ],
        )
        assert check_flag_consistency(scenario) == []

    def test_flag_cleared_by_known_rule_no_warning(self) -> None:
        scenario = _make_scenario(
            "SC-004",
            [
                ("order_received", ["ACC-007"], ["MISSING_INFO_PROCEED"], "MISSING_INFO_PROCEED"),
                ("missing_info_received", ["RES-002"], [], "RESULTING"),
            ],
        )
        assert check_flag_consistency(scenario) == []

    def test_fish_suggested_cleared_by_ihc008_no_warning(self) -> None:
        scenario = _make_scenario(
            "SC-005",
            [
                ("order_received", ["ACC-008"], [], "ACCEPTED"),
                ("ihc_scoring", ["IHC-007"], ["FISH_SUGGESTED"], "SUGGEST_FISH_REFLEX"),
                ("fish_decision", ["IHC-008"], [], "FISH_SEND_OUT"),
            ],
        )
        assert check_flag_consistency(scenario) == []

    def test_fish_suggested_cleared_by_ihc009_no_warning(self) -> None:
        scenario = _make_scenario(
            "SC-006",
            [
                ("order_received", ["ACC-008"], [], "ACCEPTED"),
                ("ihc_scoring", ["IHC-007"], ["FISH_SUGGESTED"], "SUGGEST_FISH_REFLEX"),
                ("fish_decision", ["IHC-009"], [], "RESULTING"),
            ],
        )
        assert check_flag_consistency(scenario) == []

    def test_flag_disappears_without_clearing_rule_warns(self) -> None:
        scenario = _make_scenario(
            "SC-007",
            [
                ("order_received", ["ACC-007"], ["MISSING_INFO_PROCEED"], "MISSING_INFO_PROCEED"),
                ("missing_info_received", ["RES-001"], [], "RESULTING"),
            ],
        )
        warnings = check_flag_consistency(scenario)
        assert len(warnings) == 1
        assert warnings[0].scenario_id == "SC-007"
        assert warnings[0].step == 2
        assert warnings[0].flag == "MISSING_INFO_PROCEED"
        assert "clearing mechanism" in warnings[0].message
        assert "RES-002" in warnings[0].message

    def test_flag_with_no_clearing_rules_warns(self) -> None:
        scenario = _make_scenario(
            "SC-008",
            [
                ("order_received", ["ACC-008"], ["FIXATION_WARNING"], "ACCEPTED"),
                ("grossing_complete", ["SP-001"], [], "SAMPLE_PREP_PROCESSING"),
            ],
        )
        warnings = check_flag_consistency(scenario)
        assert len(warnings) == 1
        assert warnings[0].flag == "FIXATION_WARNING"
        assert "no known clearing rules or events" in warnings[0].message

    def test_multiple_flags_mixed_clearing(self) -> None:
        """One flag cleared legitimately, another disappears without rule."""
        scenario = _make_scenario(
            "SC-009",
            [
                (
                    "order_received",
                    ["ACC-007"],
                    ["MISSING_INFO_PROCEED", "FIXATION_WARNING"],
                    "MISSING_INFO_PROCEED",
                ),
                ("missing_info_received", ["RES-002"], [], "RESULTING"),
            ],
        )
        warnings = check_flag_consistency(scenario)
        assert len(warnings) == 1
        assert warnings[0].flag == "FIXATION_WARNING"

    def test_flag_added_and_removed_mid_scenario(self) -> None:
        scenario = _make_scenario(
            "SC-010",
            [
                ("order_received", ["ACC-008"], [], "ACCEPTED"),
                ("ihc_scoring", ["IHC-007"], ["FISH_SUGGESTED"], "SUGGEST_FISH_REFLEX"),
                ("fish_decision", ["IHC-008"], [], "FISH_SEND_OUT"),
                ("resulting_review", ["RES-001"], [], "PATHOLOGIST_SIGNOUT"),
            ],
        )
        assert check_flag_consistency(scenario) == []

    def test_flag_cleared_by_event_no_warning(self) -> None:
        """RECUT_REQUESTED cleared by sectioning_complete event."""
        scenario = _make_scenario(
            "SC-013",
            [
                ("order_received", ["ACC-008"], [], "ACCEPTED"),
                ("grossing_complete", ["SP-001"], [], "SAMPLE_PREP_PROCESSING"),
                ("processing_complete", ["SP-001"], [], "SAMPLE_PREP_EMBEDDING"),
                ("embedding_complete", ["SP-001"], [], "SAMPLE_PREP_SECTIONING"),
                ("sectioning_complete", ["SP-001"], [], "SAMPLE_PREP_QC"),
                ("sample_prep_qc", ["SP-004"], [], "HE_STAINING"),
                ("he_staining_complete", [], [], "HE_QC"),
                ("he_qc", ["HE-001"], [], "PATHOLOGIST_HE_REVIEW"),
                (
                    "pathologist_he_review",
                    ["HE-009"],
                    ["RECUT_REQUESTED"],
                    "SAMPLE_PREP_SECTIONING",
                ),
                ("sectioning_complete", ["SP-001"], [], "SAMPLE_PREP_QC"),
            ],
        )
        assert check_flag_consistency(scenario) == []

    def test_two_flags_disappear_without_rules_warns_both(self) -> None:
        """Two flags with no clearing rules both disappear at the same step."""
        scenario = _make_scenario(
            "SC-012",
            [
                (
                    "order_received",
                    ["ACC-008"],
                    ["FIXATION_WARNING", "HER2_FIXATION_REJECT"],
                    "ACCEPTED",
                ),
                ("grossing_complete", ["SP-001"], [], "SAMPLE_PREP_PROCESSING"),
            ],
        )
        warnings = check_flag_consistency(scenario)
        assert len(warnings) == 2
        # sorted() ensures deterministic order
        assert warnings[0].flag == "FIXATION_WARNING"
        assert warnings[1].flag == "HER2_FIXATION_REJECT"

    def test_warning_fields_populated(self) -> None:
        scenario = _make_scenario(
            "SC-011",
            [
                ("order_received", ["ACC-007"], ["MISSING_INFO_PROCEED"], "MISSING_INFO_PROCEED"),
                ("missing_info_received", ["RES-001"], [], "RESULTING"),
            ],
        )
        warnings = check_flag_consistency(scenario)
        w = warnings[0]
        assert isinstance(w, FlagLintWarning)
        assert w.scenario_id == "SC-011"
        assert w.step == 2
        assert w.flag == "MISSING_INFO_PROCEED"
        assert len(w.message) > 0


# -----------------------------------------------------------------------
# Batch lint
# -----------------------------------------------------------------------


class TestLintScenarios:
    def test_empty_list(self) -> None:
        assert lint_scenarios([]) == []

    def test_aggregates_warnings_from_multiple_scenarios(self) -> None:
        clean = _make_scenario(
            "SC-020",
            [
                ("order_received", ["ACC-008"], [], "ACCEPTED"),
                ("grossing_complete", ["SP-001"], [], "SAMPLE_PREP_PROCESSING"),
            ],
        )
        dirty = _make_scenario(
            "SC-021",
            [
                ("order_received", ["ACC-007"], ["MISSING_INFO_PROCEED"], "MISSING_INFO_PROCEED"),
                ("missing_info_received", ["RES-001"], [], "RESULTING"),
            ],
        )
        warnings = lint_scenarios([clean, dirty])
        assert len(warnings) == 1
        assert warnings[0].scenario_id == "SC-021"


# -----------------------------------------------------------------------
# Whitelist sanity
# -----------------------------------------------------------------------


class TestFlagClearingRules:
    def test_all_flags_have_entries(self) -> None:
        """Every valid flag should appear in the clearing-rules mapping."""
        from src.workflow.models import VALID_FLAGS

        for flag in VALID_FLAGS:
            assert flag in FLAG_CLEARING_RULES, f"{flag} missing from FLAG_CLEARING_RULES"

    def test_no_stale_flags_in_whitelist(self) -> None:
        """No keys in FLAG_CLEARING_RULES should reference removed flags."""
        from src.workflow.models import VALID_FLAGS

        for flag in FLAG_CLEARING_RULES:
            assert flag in VALID_FLAGS, f"Stale flag '{flag}' in FLAG_CLEARING_RULES"

    def test_clearing_events_use_valid_event_types(self) -> None:
        """All event types in FLAG_CLEARING_EVENTS must be valid."""
        from src.simulator.schema import VALID_EVENT_TYPES

        for flag, events in FLAG_CLEARING_EVENTS.items():
            for event in events:
                assert event in VALID_EVENT_TYPES, (
                    f"Invalid event '{event}' in FLAG_CLEARING_EVENTS['{flag}']"
                )

    def test_rule_ids_match_pattern(self) -> None:
        """All rule IDs in clearing sets must match the canonical pattern."""
        import re

        rule_id_pattern = re.compile(r"^(ACC|SP|HE|IHC|RES)-\d{3}$")
        for flag, rule_ids in FLAG_CLEARING_RULES.items():
            for rule_id in rule_ids:
                assert rule_id_pattern.match(rule_id), (
                    f"Invalid rule ID '{rule_id}' in FLAG_CLEARING_RULES['{flag}']"
                )


# -----------------------------------------------------------------------
# CLI main()
# -----------------------------------------------------------------------


class TestMain:
    def test_no_scenarios_returns_1(self, tmp_path: Path) -> None:
        result = main(["--scenarios", str(tmp_path)])
        assert result == 1

    def test_clean_scenarios_returns_0(self, tmp_path: Path) -> None:
        import json

        subdir = tmp_path / "rule_coverage"
        subdir.mkdir()
        scenario_data = {
            "scenario_id": "SC-090",
            "category": "rule_coverage",
            "description": "Clean scenario",
            "events": [
                {
                    "step": 1,
                    "event_type": "order_received",
                    "event_data": {},
                    "expected_output": {
                        "next_state": "ACCEPTED",
                        "applied_rules": ["ACC-008"],
                        "flags": [],
                    },
                }
            ],
        }
        (subdir / "sc-090.json").write_text(json.dumps(scenario_data))
        result = main(["--scenarios", str(tmp_path)])
        assert result == 0

    def test_malformed_json_returns_1(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        subdir = tmp_path / "rule_coverage"
        subdir.mkdir()
        (subdir / "bad.json").write_text("not valid json")
        result = main(["--scenarios", str(tmp_path)])
        assert result == 1
        captured = capsys.readouterr()
        assert "Error loading" in captured.out

    def test_dirty_scenario_returns_1(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        import json

        subdir = tmp_path / "rule_coverage"
        subdir.mkdir()
        scenario_data = {
            "scenario_id": "SC-091",
            "category": "rule_coverage",
            "description": "Dirty scenario",
            "events": [
                {
                    "step": 1,
                    "event_type": "order_received",
                    "event_data": {},
                    "expected_output": {
                        "next_state": "MISSING_INFO_PROCEED",
                        "applied_rules": ["ACC-007"],
                        "flags": ["MISSING_INFO_PROCEED"],
                    },
                },
                {
                    "step": 2,
                    "event_type": "missing_info_received",
                    "event_data": {},
                    "expected_output": {
                        "next_state": "RESULTING",
                        "applied_rules": ["RES-001"],
                        "flags": [],
                    },
                },
            ],
        }
        (subdir / "sc-091.json").write_text(json.dumps(scenario_data))
        result = main(["--scenarios", str(tmp_path)])
        assert result == 1
        captured = capsys.readouterr()
        assert "SC-091" in captured.out
        assert "MISSING_INFO_PROCEED" in captured.out
        assert "step 2" in captured.out
        assert "1 flag warning(s)" in captured.out
        assert "MISSING_INFO_PROCEED" in captured.out


# -----------------------------------------------------------------------
# Real scenario corpus
# -----------------------------------------------------------------------


class TestRealScenarios:
    """Run the linter against the actual scenario corpus.

    All scenarios should pass cleanly — no warnings expected.
    """

    def test_corpus_no_warnings(self) -> None:
        scenarios_root = Path("scenarios")
        if not scenarios_root.exists():
            pytest.skip("scenarios/ directory not found")

        from src.simulator.lint_scenarios import _DEFAULT_SCENARIO_DIRS
        from src.simulator.loader import load_all_scenarios

        all_scenarios: list[Scenario] = []
        for subdir in _DEFAULT_SCENARIO_DIRS:
            dir_path = scenarios_root / subdir
            if dir_path.exists():
                all_scenarios.extend(load_all_scenarios(dir_path))

        warnings = lint_scenarios(all_scenarios)
        assert not warnings, f"Found {len(warnings)} flag warning(s):\n" + "\n".join(
            f"  [{w.scenario_id}] step {w.step}: {w.message}" for w in warnings
        )
