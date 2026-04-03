"""Tests for authored scenario JSON files in scenarios/rule_coverage/.

Loads all 79 scenarios (SC-001 through SC-079) from JSON, validates each
against the scenario validator, and verifies key properties like
applied_rules, next_state, and severity hierarchy.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.simulator.loader import load_scenario, load_scenarios_by_category
from src.simulator.scenario_validator import validate_scenario
from src.simulator.schema import Scenario
from src.workflow.state_machine import StateMachine

SCENARIOS_DIR = Path("scenarios")
RULE_COVERAGE_DIR = SCENARIOS_DIR / "rule_coverage"

# IHC scenario range (SC-048 through SC-069)
IHC_SCENARIO_START = 48
IHC_SCENARIO_END = 70

# Resulting scenario range (SC-070 through SC-079)
RES_SCENARIO_START = 70
RES_SCENARIO_END = 80


@pytest.fixture()
def state_machine() -> StateMachine:
    return StateMachine.get_instance()


# ── Loading and validation ────────────────────────────────────────


class TestScenarioLoading:
    """All 79 JSON scenario files load and validate cleanly."""

    def test_rule_coverage_dir_exists(self) -> None:
        assert RULE_COVERAGE_DIR.exists(), f"{RULE_COVERAGE_DIR} does not exist"

    def test_all_scenarios_present(self) -> None:
        expected_count = 79
        json_files = sorted(RULE_COVERAGE_DIR.glob("*.json"))
        assert len(json_files) == expected_count, (
            f"Expected {expected_count} scenario files, found {len(json_files)}: "
            f"{[f.name for f in json_files]}"
        )

    def test_all_scenarios_load(self) -> None:
        """Every JSON file loads without errors."""
        for json_file in sorted(RULE_COVERAGE_DIR.glob("*.json")):
            scenario = load_scenario(json_file)
            assert isinstance(scenario, Scenario), f"{json_file.name} did not load"

    def test_all_scenarios_validate(self, state_machine: StateMachine) -> None:
        """Every loaded scenario passes validation with zero errors."""
        for json_file in sorted(RULE_COVERAGE_DIR.glob("*.json")):
            scenario = load_scenario(json_file)
            errors = validate_scenario(scenario, state_machine)
            assert errors == [], (
                f"{json_file.name} ({scenario.scenario_id}) validation errors:\n"
                + "\n".join(f"  Step {e.step_number}: [{e.error_type}] {e.message}" for e in errors)
            )

    def test_all_categories_are_rule_coverage(self) -> None:
        """All scenarios have category 'rule_coverage'."""
        scenarios = load_scenarios_by_category(SCENARIOS_DIR, "rule_coverage")
        for scenario in scenarios:
            assert scenario.category == "rule_coverage"

    def test_unique_scenario_ids(self) -> None:
        """All 79 scenarios have unique IDs."""
        ids = set()
        for json_file in sorted(RULE_COVERAGE_DIR.glob("*.json")):
            scenario = load_scenario(json_file)
            ids.add(scenario.scenario_id)
        assert len(ids) == 79

    def test_scenario_ids_sequential(self) -> None:
        """Scenario IDs are SC-001 through SC-079."""
        expected_ids = {f"SC-{i:03d}" for i in range(1, 80)}
        actual_ids = set()
        for json_file in sorted(RULE_COVERAGE_DIR.glob("*.json")):
            scenario = load_scenario(json_file)
            actual_ids.add(scenario.scenario_id)
        assert actual_ids == expected_ids


# ── Helpers ───────────────────────────────────────────────────────


def _load_by_id(scenario_id: str) -> Scenario:
    """Load a specific scenario by ID."""
    for json_file in sorted(RULE_COVERAGE_DIR.glob("*.json")):
        scenario = load_scenario(json_file)
        if scenario.scenario_id == scenario_id:
            return scenario
    raise FileNotFoundError(f"Scenario {scenario_id} not found")


def _first_step_rules(scenario: Scenario) -> tuple[str, ...]:
    """Get applied_rules from the first (accessioning) step."""
    return scenario.steps[0].expected_output.applied_rules


def _first_step_state(scenario: Scenario) -> str:
    """Get next_state from the first (accessioning) step."""
    return scenario.steps[0].expected_output.next_state


def _terminal_state(scenario: Scenario) -> str:
    """Get next_state from the last step."""
    return scenario.steps[-1].expected_output.next_state


def _verify_fish_pathway(scenario: Scenario) -> None:
    """Assert that the FISH pathway rules appear in correct order."""
    fish_rules = ("IHC-007", "IHC-008", "IHC-010")
    rule_indices: dict[str, int] = {}
    for i, step in enumerate(scenario.steps):
        for rule_id in step.expected_output.applied_rules:
            if rule_id in fish_rules:
                rule_indices[rule_id] = i
    for rule_id in fish_rules:
        assert rule_id in rule_indices, f"{scenario.scenario_id} missing FISH rule {rule_id}"
    assert rule_indices["IHC-007"] < rule_indices["IHC-008"] < rule_indices["IHC-010"], (
        f"{scenario.scenario_id} FISH rules out of order: {rule_indices}"
    )


# ── ACC-008 (ACCEPT) scenarios ────────────────────────────────────


class TestACC008Accept:
    """SC-001 and SC-002: All fields valid → ACCEPTED."""

    def test_sc001_accepted(self) -> None:
        s = _load_by_id("SC-001")
        assert _first_step_state(s) == "ACCEPTED"
        assert _first_step_rules(s) == ("ACC-008",)

    def test_sc001_extends_to_processing(self) -> None:
        """SC-001 extends through grossing_complete to SAMPLE_PREP_PROCESSING."""
        s = _load_by_id("SC-001")
        assert len(s.steps) >= 2
        assert s.steps[1].event_type == "grossing_complete"
        assert s.steps[1].expected_output.next_state == "SAMPLE_PREP_PROCESSING"

    def test_sc002_accepted_boundary(self) -> None:
        """SC-002: Fixation at 72.0hr boundary still accepted."""
        s = _load_by_id("SC-002")
        assert _first_step_state(s) == "ACCEPTED"
        assert _first_step_rules(s) == ("ACC-008",)
        assert s.steps[0].event_data["fixation_time_hours"] == 72.0

    def test_sc002_extends_to_processing(self) -> None:
        s = _load_by_id("SC-002")
        assert len(s.steps) >= 2
        assert s.steps[1].event_type == "grossing_complete"
        assert s.steps[1].expected_output.next_state == "SAMPLE_PREP_PROCESSING"


# ── ACC-001 (HOLD — patient name) scenarios ───────────────────────


class TestACC001Hold:
    """SC-003 and SC-004: Patient name missing → MISSING_INFO_HOLD."""

    def test_sc003_hold(self) -> None:
        s = _load_by_id("SC-003")
        assert _first_step_state(s) == "MISSING_INFO_HOLD"
        assert _first_step_rules(s) == ("ACC-001",)
        assert s.steps[0].event_data["patient_name"] is None

    def test_sc004_hold_beats_proceed(self) -> None:
        """SC-004: ACC-001 (HOLD) + ACC-007 (PROCEED); HOLD wins."""
        s = _load_by_id("SC-004")
        assert _first_step_state(s) == "MISSING_INFO_HOLD"
        rules = set(_first_step_rules(s))
        assert "ACC-001" in rules
        assert "ACC-007" in rules


# ── ACC-002 (HOLD — patient sex) scenarios ────────────────────────


class TestACC002Hold:
    """SC-005 and SC-006: Patient sex missing → MISSING_INFO_HOLD."""

    def test_sc005_hold(self) -> None:
        s = _load_by_id("SC-005")
        assert _first_step_state(s) == "MISSING_INFO_HOLD"
        assert _first_step_rules(s) == ("ACC-002",)
        assert s.steps[0].event_data["sex"] is None

    def test_sc006_dual_hold(self) -> None:
        """SC-006: ACC-001 + ACC-002 both fire, both HOLD severity."""
        s = _load_by_id("SC-006")
        assert _first_step_state(s) == "MISSING_INFO_HOLD"
        rules = set(_first_step_rules(s))
        assert "ACC-001" in rules
        assert "ACC-002" in rules


# ── ACC-003 (REJECT — anatomic site) scenarios ───────────────────


class TestACC003Reject:
    """SC-007 and SC-008: Invalid anatomic site → DO_NOT_PROCESS."""

    def test_sc007_reject(self) -> None:
        s = _load_by_id("SC-007")
        assert _first_step_state(s) == "DO_NOT_PROCESS"
        assert _first_step_rules(s) == ("ACC-003",)
        assert _terminal_state(s) == "DO_NOT_PROCESS"

    def test_sc008_reject_beats_hold(self) -> None:
        """SC-008: ACC-003 (REJECT) + ACC-001 (HOLD); REJECT wins."""
        s = _load_by_id("SC-008")
        assert _first_step_state(s) == "DO_NOT_PROCESS"
        rules = set(_first_step_rules(s))
        assert "ACC-001" in rules
        assert "ACC-003" in rules
        assert _terminal_state(s) == "DO_NOT_PROCESS"


# ── ACC-004 (REJECT — specimen type) scenarios ───────────────────


class TestACC004Reject:
    """SC-009 and SC-010: Incompatible specimen → DO_NOT_PROCESS."""

    def test_sc009_reject(self) -> None:
        s = _load_by_id("SC-009")
        assert _first_step_state(s) == "DO_NOT_PROCESS"
        assert _first_step_rules(s) == ("ACC-004",)
        assert s.steps[0].event_data["specimen_type"] == "FNA"

    def test_sc010_multi_reject_incompatible_and_fixative(self) -> None:
        """SC-010: Cytospin + alcohol fixative; both ACC-004 and ACC-005 fire."""
        s = _load_by_id("SC-010")
        assert _first_step_state(s) == "DO_NOT_PROCESS"
        assert _first_step_rules(s) == ("ACC-004", "ACC-005")
        assert s.steps[0].event_data["specimen_type"] == "cytospin"
        assert s.steps[0].event_data["fixative"] == "alcohol"


# ── ACC-005 (REJECT — HER2 fixative) scenarios ──────────────────


class TestACC005Reject:
    """SC-011 and SC-012: HER2 + wrong fixative → DO_NOT_PROCESS."""

    def test_sc011_reject(self) -> None:
        s = _load_by_id("SC-011")
        assert _first_step_state(s) == "DO_NOT_PROCESS"
        assert _first_step_rules(s) == ("ACC-005",)
        assert s.steps[0].event_data["fixative"] == "fresh"

    def test_sc012_alcohol_fixative_generalization(self) -> None:
        """SC-012: Alcohol fixative (different from fresh in SC-011)."""
        s = _load_by_id("SC-012")
        assert _first_step_state(s) == "DO_NOT_PROCESS"
        assert _first_step_rules(s) == ("ACC-005",)
        assert s.steps[0].event_data["fixative"] == "alcohol"
        assert s.steps[0].event_data["fixation_time_hours"] == 48.0


# ── ACC-006 (REJECT — HER2 fixation time) scenarios ─────────────


class TestACC006Reject:
    """SC-013 and SC-014: HER2 + bad fixation time → DO_NOT_PROCESS."""

    def test_sc013_under_fixation(self) -> None:
        s = _load_by_id("SC-013")
        assert _first_step_state(s) == "DO_NOT_PROCESS"
        assert _first_step_rules(s) == ("ACC-006",)
        assert s.steps[0].event_data["fixation_time_hours"] == 5.0

    def test_sc014_over_fixation(self) -> None:
        s = _load_by_id("SC-014")
        assert _first_step_state(s) == "DO_NOT_PROCESS"
        assert _first_step_rules(s) == ("ACC-006",)
        assert s.steps[0].event_data["fixation_time_hours"] == 73.0


# ── ACC-007 (PROCEED) scenarios ──────────────────────────────────


class TestACC007Proceed:
    """SC-015 and SC-016: Billing missing → MISSING_INFO_PROCEED."""

    def test_sc015_proceed_with_flag(self) -> None:
        s = _load_by_id("SC-015")
        assert _first_step_state(s) == "MISSING_INFO_PROCEED"
        assert _first_step_rules(s) == ("ACC-007",)
        assert "MISSING_INFO_PROCEED" in s.steps[0].expected_output.flags
        assert s.steps[0].event_data["billing_info_present"] is False

    def test_sc016_boundary_probe(self) -> None:
        """SC-016: Billing missing + fixation at 6.0hr boundary."""
        s = _load_by_id("SC-016")
        assert _first_step_state(s) == "MISSING_INFO_PROCEED"
        assert _first_step_rules(s) == ("ACC-007",)
        assert s.steps[0].event_data["fixation_time_hours"] == 6.0
        assert s.steps[0].event_data["billing_info_present"] is False


# ── Cross-cutting checks ─────────────────────────────────────────


class TestSeverityHierarchy:
    """Severity resolution across multi-rule scenarios."""

    def test_reject_beats_hold(self) -> None:
        """SC-008: REJECT > HOLD → DO_NOT_PROCESS."""
        s = _load_by_id("SC-008")
        assert _first_step_state(s) == "DO_NOT_PROCESS"

    def test_hold_beats_proceed(self) -> None:
        """SC-004: HOLD > PROCEED → MISSING_INFO_HOLD."""
        s = _load_by_id("SC-004")
        assert _first_step_state(s) == "MISSING_INFO_HOLD"

    def test_dual_hold_resolves_to_hold(self) -> None:
        """SC-006: HOLD + HOLD → MISSING_INFO_HOLD."""
        s = _load_by_id("SC-006")
        assert _first_step_state(s) == "MISSING_INFO_HOLD"


class TestAllMatchSemantics:
    """applied_rules must list ALL matching rules, not just the highest."""

    def test_sc004_has_both_rules(self) -> None:
        s = _load_by_id("SC-004")
        rules = set(_first_step_rules(s))
        assert rules == {"ACC-001", "ACC-007"}

    def test_sc006_has_both_rules(self) -> None:
        s = _load_by_id("SC-006")
        rules = set(_first_step_rules(s))
        assert rules == {"ACC-001", "ACC-002"}

    def test_sc008_has_both_rules(self) -> None:
        s = _load_by_id("SC-008")
        rules = set(_first_step_rules(s))
        assert rules == {"ACC-001", "ACC-003"}


class TestFirstEventIsOrderReceived:
    """All scenarios start with order_received."""

    def test_all_start_with_order_received(self) -> None:
        for json_file in sorted(RULE_COVERAGE_DIR.glob("*.json")):
            scenario = load_scenario(json_file)
            assert scenario.steps[0].event_type == "order_received", (
                f"{scenario.scenario_id} first event is "
                f"'{scenario.steps[0].event_type}', expected 'order_received'"
            )


# ── SP-001 (advance to next step) scenarios ─────────────────────


class TestSP001Advance:
    """SC-017 and SC-018: Step completed successfully → advance."""

    def test_sc017_grossing_to_processing(self) -> None:
        """SC-017: Grossing success → SAMPLE_PREP_PROCESSING."""
        s = _load_by_id("SC-017")
        assert len(s.steps) == 2
        assert s.steps[1].event_type == "grossing_complete"
        assert s.steps[1].expected_output.next_state == "SAMPLE_PREP_PROCESSING"
        assert s.steps[1].expected_output.applied_rules == ("SP-001",)

    def test_sc018_processing_to_embedding(self) -> None:
        """SC-018: Processing success → SAMPLE_PREP_EMBEDDING (mid-chain)."""
        s = _load_by_id("SC-018")
        assert len(s.steps) == 3
        assert s.steps[2].event_type == "processing_complete"
        assert s.steps[2].expected_output.next_state == "SAMPLE_PREP_EMBEDDING"
        assert s.steps[2].expected_output.applied_rules == ("SP-001",)


# ── SP-002 (retry current step) scenarios ────────────────────────


class TestSP002Retry:
    """SC-019, SC-020, SC-029: Step failed, tissue available → self-loop."""

    def test_sc019_processing_self_loop(self) -> None:
        """SC-019: Processing fails (excision) → SAMPLE_PREP_PROCESSING (self-loop)."""
        s = _load_by_id("SC-019")
        last = s.steps[-1]
        assert last.event_type == "processing_complete"
        assert last.event_data["outcome"] == "failure"
        assert last.expected_output.next_state == "SAMPLE_PREP_PROCESSING"
        assert last.expected_output.applied_rules == ("SP-002",)

    def test_sc020_sectioning_self_loop(self) -> None:
        """SC-020: Sectioning fails (excision) → SAMPLE_PREP_SECTIONING (self-loop)."""
        s = _load_by_id("SC-020")
        last = s.steps[-1]
        assert last.event_type == "sectioning_complete"
        assert last.event_data["outcome"] == "failure"
        assert last.expected_output.next_state == "SAMPLE_PREP_SECTIONING"
        assert last.expected_output.applied_rules == ("SP-002",)

    def test_sc029_embedding_self_loop(self) -> None:
        """SC-029: Embedding fails (excision) → SAMPLE_PREP_EMBEDDING (self-loop)."""
        s = _load_by_id("SC-029")
        last = s.steps[-1]
        assert last.event_type == "embedding_complete"
        assert last.event_data["outcome"] == "failure"
        assert last.expected_output.next_state == "SAMPLE_PREP_EMBEDDING"
        assert last.expected_output.applied_rules == ("SP-002",)


# ── SP-003 (step failed, QNS) scenarios ─────────────────────────


class TestSP003QNS:
    """SC-021 and SC-022: Step failed, insufficient tissue → ORDER_TERMINATED_QNS."""

    def test_sc021_processing_qns(self) -> None:
        """SC-021: Processing fails, QNS → ORDER_TERMINATED_QNS."""
        s = _load_by_id("SC-021")
        assert _terminal_state(s) == "ORDER_TERMINATED_QNS"
        last = s.steps[-1]
        assert last.event_data["outcome"] == "failure"
        assert last.expected_output.applied_rules == ("SP-003",)

    def test_sc022_embedding_qns(self) -> None:
        """SC-022: Embedding fails, QNS → ORDER_TERMINATED_QNS (mid-chain)."""
        s = _load_by_id("SC-022")
        assert _terminal_state(s) == "ORDER_TERMINATED_QNS"
        last = s.steps[-1]
        assert last.event_type == "embedding_complete"
        assert last.event_data["outcome"] == "failure"
        assert last.expected_output.applied_rules == ("SP-003",)


# ── SP-004 (QC passes → HE_STAINING) scenarios ──────────────────


class TestSP004QCPass:
    """SC-023 and SC-024: Sample prep QC passes → HE_STAINING."""

    def test_sc023_qc_pass(self) -> None:
        """SC-023: QC passes → HE_STAINING."""
        s = _load_by_id("SC-023")
        assert _terminal_state(s) == "HE_STAINING"
        last = s.steps[-1]
        assert last.event_type == "sample_prep_qc"
        assert last.event_data["outcome"] == "pass"
        assert last.expected_output.applied_rules == ("SP-004",)

    def test_sc024_qc_pass_after_retry(self) -> None:
        """SC-024: QC passes after prior processing retry → HE_STAINING."""
        s = _load_by_id("SC-024")
        assert _terminal_state(s) == "HE_STAINING"
        # Verify a retry occurred earlier in the chain
        retry_rules = [
            step.expected_output.applied_rules
            for step in s.steps
            if "SP-002" in step.expected_output.applied_rules
        ]
        assert len(retry_rules) >= 1


# ── SP-005 (QC fails, tissue → SECTIONING) scenarios ────────────


class TestSP005QCFailRetry:
    """SC-025 and SC-026: QC fails, tissue available → SAMPLE_PREP_SECTIONING."""

    def test_sc025_qc_fail_tissue(self) -> None:
        """SC-025: QC fails, tissue available → SAMPLE_PREP_SECTIONING."""
        s = _load_by_id("SC-025")
        assert _terminal_state(s) == "SAMPLE_PREP_SECTIONING"
        last = s.steps[-1]
        assert last.event_type == "sample_prep_qc"
        assert last.event_data["outcome"] == "fail_tissue_available"
        assert last.expected_output.applied_rules == ("SP-005",)

    def test_sc026_qc_fail_second_time(self) -> None:
        """SC-026: QC fails after prior re-section → SECTIONING (2nd time)."""
        s = _load_by_id("SC-026")
        assert _terminal_state(s) == "SAMPLE_PREP_SECTIONING"
        # Verify two QC failures occurred
        qc_fail_steps = [
            step
            for step in s.steps
            if step.event_type == "sample_prep_qc"
            and step.event_data["outcome"] == "fail_tissue_available"
        ]
        assert len(qc_fail_steps) == 2


# ── SP-006 (QC fails, QNS) scenarios ────────────────────────────


class TestSP006QCFailQNS:
    """SC-027 and SC-028: QC fails, insufficient tissue → ORDER_TERMINATED_QNS."""

    def test_sc027_qc_fail_qns(self) -> None:
        """SC-027: QC fails, QNS → ORDER_TERMINATED_QNS."""
        s = _load_by_id("SC-027")
        assert _terminal_state(s) == "ORDER_TERMINATED_QNS"
        last = s.steps[-1]
        assert last.event_type == "sample_prep_qc"
        assert last.event_data["outcome"] == "fail_qns"
        assert last.expected_output.applied_rules == ("SP-006",)

    def test_sc028_qc_fail_qns_after_retry(self) -> None:
        """SC-028: QC fails, QNS (biopsy), after prior sectioning retry → ORDER_TERMINATED_QNS."""
        s = _load_by_id("SC-028")
        assert _terminal_state(s) == "ORDER_TERMINATED_QNS"
        last = s.steps[-1]
        assert last.event_data["outcome"] == "fail_qns"
        assert last.expected_output.applied_rules == ("SP-006",)
        # Verify a retry occurred earlier
        retry_rules = [
            step.expected_output.applied_rules
            for step in s.steps
            if "SP-002" in step.expected_output.applied_rules
        ]
        assert len(retry_rules) >= 1


# ── Tissue availability inference ────────────────────────────────


class TestTissueAvailabilityInference:
    """Verify specimen_type correlates with retry vs QNS paths.

    Excision specimens have sufficient tissue for retry (SP-002),
    while biopsy specimens have insufficient tissue and terminate (SP-003).
    Same pattern applies for QC: SP-005 (excision) vs SP-006 (biopsy).
    """

    def test_sp002_scenarios_use_excision(self) -> None:
        """All SP-002 retry scenarios use excision specimen type."""
        for sid in ("SC-019", "SC-020", "SC-029"):
            s = _load_by_id(sid)
            assert s.steps[0].event_data["specimen_type"] == "excision", (
                f"{sid} uses SP-002 (retry) but specimen_type is "
                f"'{s.steps[0].event_data['specimen_type']}', expected 'excision'"
            )

    def test_sp003_scenarios_use_biopsy(self) -> None:
        """All SP-003 QNS scenarios use biopsy specimen type."""
        for sid in ("SC-021", "SC-022"):
            s = _load_by_id(sid)
            assert s.steps[0].event_data["specimen_type"] == "biopsy", (
                f"{sid} uses SP-003 (QNS) but specimen_type is "
                f"'{s.steps[0].event_data['specimen_type']}', expected 'biopsy'"
            )

    def test_sp005_scenarios_use_excision(self) -> None:
        """All SP-005 QC retry scenarios use excision specimen type."""
        for sid in ("SC-025", "SC-026"):
            s = _load_by_id(sid)
            assert s.steps[0].event_data["specimen_type"] == "excision", (
                f"{sid} uses SP-005 (QC retry) but specimen_type is "
                f"'{s.steps[0].event_data['specimen_type']}', expected 'excision'"
            )

    def test_sp006_scenarios_use_biopsy(self) -> None:
        """All SP-006 QC QNS scenarios use biopsy specimen type."""
        for sid in ("SC-027", "SC-028"):
            s = _load_by_id(sid)
            assert s.steps[0].event_data["specimen_type"] == "biopsy", (
                f"{sid} uses SP-006 (QC QNS) but specimen_type is "
                f"'{s.steps[0].event_data['specimen_type']}', expected 'biopsy'"
            )


# ── Sample prep flag validation ──────────────────────────────────


class TestSamplePrepFlagsEmpty:
    """Sample prep rules (SP-001..006) should never set flags."""

    _SP_SCENARIO_IDS = [f"SC-{i:03d}" for i in range(17, 30)]

    def test_all_sample_prep_steps_have_empty_flags(self) -> None:
        """Every step in every sample prep scenario has flags == ()."""
        for sid in self._SP_SCENARIO_IDS:
            s = _load_by_id(sid)
            for step in s.steps:
                if any(r.startswith("SP-") for r in step.expected_output.applied_rules):
                    assert step.expected_output.flags == (), (
                        f"{sid} step {step.step}: "
                        f"SP rule sets flags {step.expected_output.flags}, expected ()"
                    )


# ── HE-001 (QC passes → PATHOLOGIST_HE_REVIEW) scenarios ────────


class TestHE001QCPass:
    """SC-030 and SC-031: H&E QC passes → PATHOLOGIST_HE_REVIEW."""

    def test_sc030_qc_pass(self) -> None:
        """SC-030: H&E QC passes → PATHOLOGIST_HE_REVIEW."""
        s = _load_by_id("SC-030")
        assert _terminal_state(s) == "PATHOLOGIST_HE_REVIEW"
        last = s.steps[-1]
        assert last.event_type == "he_qc"
        assert last.event_data["outcome"] == "pass"
        assert last.expected_output.applied_rules == ("HE-001",)

    def test_sc031_qc_pass_after_restain(self) -> None:
        """SC-031: QC passes on second attempt after restain (HE-002 then HE-001)."""
        s = _load_by_id("SC-031")
        assert _terminal_state(s) == "PATHOLOGIST_HE_REVIEW"
        # Find the restain step and validate the full loop sequence
        restain_idx = None
        for i, step in enumerate(s.steps):
            if "HE-002" in step.expected_output.applied_rules:
                restain_idx = i
                break
        assert restain_idx is not None, "No restain step found"
        # Restain transitions back to HE_STAINING
        assert s.steps[restain_idx].expected_output.next_state == "HE_STAINING"
        # Next step is he_staining_complete → HE_QC
        assert s.steps[restain_idx + 1].event_type == "he_staining_complete"
        assert s.steps[restain_idx + 1].expected_output.next_state == "HE_QC"
        # Final QC pass with HE-001
        assert s.steps[restain_idx + 2].event_type == "he_qc"
        assert s.steps[restain_idx + 2].event_data["outcome"] == "pass"
        assert s.steps[restain_idx + 2].expected_output.applied_rules == ("HE-001",)


# ── HE-002 (QC fails, restain) scenarios ────────────────────────


class TestHE002Restain:
    """SC-032 and SC-033: H&E QC fails, restain possible → HE_STAINING."""

    def test_sc032_restain(self) -> None:
        """SC-032: QC fails with fail_restain → HE_STAINING."""
        s = _load_by_id("SC-032")
        assert _terminal_state(s) == "HE_STAINING"
        last = s.steps[-1]
        assert last.event_type == "he_qc"
        assert last.event_data["outcome"] == "fail_restain"
        assert last.expected_output.applied_rules == ("HE-002",)

    def test_sc033_restain_excision(self) -> None:
        """SC-033: Restain preferred over recut for excision specimen."""
        s = _load_by_id("SC-033")
        assert _terminal_state(s) == "HE_STAINING"
        last = s.steps[-1]
        assert last.event_data["outcome"] == "fail_restain"
        assert last.expected_output.applied_rules == ("HE-002",)
        assert s.steps[0].event_data["specimen_type"] == "excision"


# ── HE-003 (QC fails, recut needed) scenarios ───────────────────


class TestHE003Recut:
    """SC-034 and SC-035: H&E QC fails, recut needed → SAMPLE_PREP_SECTIONING."""

    def test_sc034_recut(self) -> None:
        """SC-034: QC fails with fail_recut → SAMPLE_PREP_SECTIONING."""
        s = _load_by_id("SC-034")
        assert _terminal_state(s) == "SAMPLE_PREP_SECTIONING"
        last = s.steps[-1]
        assert last.event_type == "he_qc"
        assert last.event_data["outcome"] == "fail_recut"
        assert last.expected_output.applied_rules == ("HE-003",)

    def test_sc035_recut_from_block(self) -> None:
        """SC-035: No backup slides, tissue available → recut from block."""
        s = _load_by_id("SC-035")
        assert _terminal_state(s) == "SAMPLE_PREP_SECTIONING"
        last = s.steps[-1]
        assert last.event_data["outcome"] == "fail_recut"
        assert last.expected_output.applied_rules == ("HE-003",)
        assert last.event_data["backup_slides_available"] is False


# ── HE-004 (QC fails, QNS) scenarios ────────────────────────────


class TestHE004QNS:
    """SC-036 and SC-037: H&E QC fails, insufficient tissue → ORDER_TERMINATED_QNS."""

    def test_sc036_qns(self) -> None:
        """SC-036: QC fails with fail_qns → ORDER_TERMINATED_QNS."""
        s = _load_by_id("SC-036")
        assert _terminal_state(s) == "ORDER_TERMINATED_QNS"
        last = s.steps[-1]
        assert last.event_type == "he_qc"
        assert last.event_data["outcome"] == "fail_qns"
        assert last.expected_output.applied_rules == ("HE-004",)

    def test_sc037_qns_no_backup(self) -> None:
        """SC-037: No backup slides, no tissue remaining → QNS."""
        s = _load_by_id("SC-037")
        assert _terminal_state(s) == "ORDER_TERMINATED_QNS"
        last = s.steps[-1]
        assert last.event_data["outcome"] == "fail_qns"
        assert last.expected_output.applied_rules == ("HE-004",)
        assert last.event_data["backup_slides_available"] is False
        assert last.event_data["tissue_remaining"] is False


# ── HE-005 (invasive carcinoma → IHC) scenarios ─────────────────


class TestHE005Invasive:
    """SC-038 and SC-039: Pathologist diagnoses invasive carcinoma → IHC_STAINING."""

    def test_sc038_invasive(self) -> None:
        """SC-038: Invasive carcinoma → IHC_STAINING."""
        s = _load_by_id("SC-038")
        assert _terminal_state(s) == "IHC_STAINING"
        last = s.steps[-1]
        assert last.event_type == "pathologist_he_review"
        assert last.event_data["diagnosis"] == "invasive_carcinoma"
        assert last.expected_output.applied_rules == ("HE-005",)
        assert "added_markers" not in last.event_data
        assert "ihc_panel" not in last.event_data

    def test_sc039_invasive_with_ecadherin(self) -> None:
        """SC-039: Invasive + E-cadherin marker added (panel modification)."""
        s = _load_by_id("SC-039")
        assert _terminal_state(s) == "IHC_STAINING"
        last = s.steps[-1]
        assert last.event_data["diagnosis"] == "invasive_carcinoma"
        assert last.expected_output.applied_rules == ("HE-005",)
        assert "E-cadherin" in last.event_data["added_markers"]


# ── HE-006 (DCIS → IHC) scenarios ───────────────────────────────


class TestHE006DCIS:
    """SC-040 and SC-041: Pathologist diagnoses DCIS → IHC_STAINING."""

    def test_sc040_dcis(self) -> None:
        """SC-040: DCIS → IHC_STAINING."""
        s = _load_by_id("SC-040")
        assert _terminal_state(s) == "IHC_STAINING"
        last = s.steps[-1]
        assert last.event_type == "pathologist_he_review"
        assert last.event_data["diagnosis"] == "dcis"
        assert last.expected_output.applied_rules == ("HE-006",)
        assert "added_markers" not in last.event_data

    def test_sc041_dcis_with_her2(self) -> None:
        """SC-041: DCIS + HER2 marker added (panel modification)."""
        s = _load_by_id("SC-041")
        assert _terminal_state(s) == "IHC_STAINING"
        last = s.steps[-1]
        assert last.event_data["diagnosis"] == "dcis"
        assert last.expected_output.applied_rules == ("HE-006",)
        assert "HER2" in last.event_data["added_markers"]


# ── HE-007 (suspicious/atypical → IHC) scenarios ────────────────


class TestHE007Suspicious:
    """SC-042 and SC-043: Pathologist diagnoses suspicious/atypical → IHC_STAINING."""

    def test_sc042_suspicious(self) -> None:
        """SC-042: Suspicious/atypical → IHC_STAINING."""
        s = _load_by_id("SC-042")
        assert _terminal_state(s) == "IHC_STAINING"
        last = s.steps[-1]
        assert last.event_type == "pathologist_he_review"
        assert last.event_data["diagnosis"] == "suspicious_atypical"
        assert last.expected_output.applied_rules == ("HE-007",)
        assert "added_markers" not in last.event_data

    def test_sc043_suspicious_custom_panel(self) -> None:
        """SC-043: Suspicious + custom markers (p63, CK5/6) added."""
        s = _load_by_id("SC-043")
        assert _terminal_state(s) == "IHC_STAINING"
        last = s.steps[-1]
        assert last.event_data["diagnosis"] == "suspicious_atypical"
        assert last.expected_output.applied_rules == ("HE-007",)
        assert "p63" in last.event_data["added_markers"]
        assert "CK5/6" in last.event_data["added_markers"]


# ── HE-008 (benign → RESULTING) scenarios ────────────────────────


class TestHE008Benign:
    """SC-044 and SC-045: Pathologist diagnoses benign → RESULTING."""

    def test_sc044_benign(self) -> None:
        """SC-044: Benign → RESULTING (IHC cancelled)."""
        s = _load_by_id("SC-044")
        assert _terminal_state(s) == "RESULTING"
        last = s.steps[-1]
        assert last.event_type == "pathologist_he_review"
        assert last.event_data["diagnosis"] == "benign"
        assert last.expected_output.applied_rules == ("HE-008",)
        assert last.event_data["ihc_cancelled"] is True
        assert "cancelled_tests" not in last.event_data

    def test_sc045_benign_her2_cancelled(self) -> None:
        """SC-045: Benign + HER2 was ordered → RESULTING (specific test cancelled)."""
        s = _load_by_id("SC-045")
        assert _terminal_state(s) == "RESULTING"
        last = s.steps[-1]
        assert last.event_data["diagnosis"] == "benign"
        assert last.expected_output.applied_rules == ("HE-008",)
        assert "HER2" in last.event_data["cancelled_tests"]


# ── HE-009 (recut requested → SAMPLE_PREP_SECTIONING) scenarios ─


class TestHE009Recuts:
    """SC-046 and SC-047: Pathologist requests recuts → SAMPLE_PREP_SECTIONING."""

    def test_sc046_recut_requested(self) -> None:
        """SC-046: Recut requested → SAMPLE_PREP_SECTIONING with RECUT_REQUESTED flag."""
        s = _load_by_id("SC-046")
        assert _terminal_state(s) == "SAMPLE_PREP_SECTIONING"
        last = s.steps[-1]
        assert last.event_type == "pathologist_he_review"
        assert last.event_data["diagnosis"] == "recut_requested"
        assert last.expected_output.applied_rules == ("HE-009",)
        assert "RECUT_REQUESTED" in last.expected_output.flags
        assert "tissue_limited" not in last.event_data

    def test_sc047_recut_tissue_limited(self) -> None:
        """SC-047: Recut requested, tissue limited (biopsy) → still proceeds."""
        s = _load_by_id("SC-047")
        assert _terminal_state(s) == "SAMPLE_PREP_SECTIONING"
        last = s.steps[-1]
        assert last.event_data["diagnosis"] == "recut_requested"
        assert last.expected_output.applied_rules == ("HE-009",)
        assert "RECUT_REQUESTED" in last.expected_output.flags
        assert last.event_data["tissue_limited"] is True
        assert s.steps[0].event_data["specimen_type"] == "biopsy"


# ── Cross-cutting HE validation ─────────────────────────────────


class TestHEStainingPassthrough:
    """Validate that he_staining_complete transitions have empty applied_rules."""

    def test_he_staining_complete_no_rules(self) -> None:
        """HE_STAINING → HE_QC transitions have no associated rules."""
        for sid in [f"SC-{i:03d}" for i in range(30, 48)]:
            s = _load_by_id(sid)
            staining_steps = [step for step in s.steps if step.event_type == "he_staining_complete"]
            assert len(staining_steps) >= 1, f"{sid} has no he_staining_complete step"
            for step in staining_steps:
                assert step.expected_output.applied_rules == (), (
                    f"{sid} step {step.step}: he_staining_complete should have "
                    f"empty applied_rules, got {step.expected_output.applied_rules}"
                )
                assert step.expected_output.next_state == "HE_QC", (
                    f"{sid} step {step.step}: he_staining_complete should "
                    f"transition to HE_QC, got {step.expected_output.next_state}"
                )


class TestHEFlagIsolation:
    """Validate RECUT_REQUESTED flag only appears in HE-009 scenarios."""

    def test_recut_flag_only_in_he009(self) -> None:
        """RECUT_REQUESTED should only appear in SC-046 and SC-047."""
        recut_scenarios = {"SC-046", "SC-047"}
        for sid in [f"SC-{i:03d}" for i in range(30, 48)]:
            s = _load_by_id(sid)
            all_flags = []
            for step in s.steps:
                all_flags.extend(step.expected_output.flags)
            if sid in recut_scenarios:
                assert "RECUT_REQUESTED" in all_flags, f"{sid} should have RECUT_REQUESTED flag"
            else:
                assert "RECUT_REQUESTED" not in all_flags, (
                    f"{sid} should not have RECUT_REQUESTED flag"
                )


# ── IHC-001 (HER2 fixation reject) scenarios ────────────────────


class TestIHC001FixationReject:
    """SC-048 and SC-049: HER2 added at review + fixation check."""

    def test_sc048_her2_rejected(self) -> None:
        """SC-048: HER2 added, fixation out of tolerance → IHC_STAINING self-loop + flag."""
        s = _load_by_id("SC-048")
        assert _terminal_state(s) == "IHC_STAINING"
        last = s.steps[-1]
        assert last.event_type == "ihc_staining_complete"
        assert last.expected_output.applied_rules == ("IHC-001",)
        assert "HER2_FIXATION_REJECT" in last.expected_output.flags
        # HER2 was added at pathologist review, not originally ordered
        assert "HER2" not in s.steps[0].event_data["ordered_tests"]
        assert s.steps[0].event_data["fixation_time_hours"] == 5.0

    def test_sc049_boundary_no_reject(self) -> None:
        """SC-049: HER2 added, fixation at 6.0hr boundary → IHC_QC (no reject)."""
        s = _load_by_id("SC-049")
        assert _terminal_state(s) == "IHC_QC"
        last = s.steps[-1]
        assert last.event_type == "ihc_staining_complete"
        assert last.expected_output.applied_rules == ()
        assert last.expected_output.flags == ()
        assert s.steps[0].event_data["fixation_time_hours"] == 6.0


# ── IHC-002 (all QC passed → IHC_SCORING) scenarios ─────────────


class TestIHC002AllQCPassed:
    """SC-050 and SC-051: All IHC slides QC passed → IHC_SCORING."""

    def test_sc050_all_pass(self) -> None:
        """SC-050: All slides QC pass → IHC_SCORING."""
        s = _load_by_id("SC-050")
        assert _terminal_state(s) == "IHC_SCORING"
        last = s.steps[-1]
        assert last.event_type == "ihc_qc"
        assert last.expected_output.applied_rules == ("IHC-002",)
        assert last.event_data["all_slides_complete"] is True

    def test_sc051_all_pass_after_retry(self) -> None:
        """SC-051: All slides pass after prior IHC-004 retry → IHC_SCORING."""
        s = _load_by_id("SC-051")
        assert _terminal_state(s) == "IHC_SCORING"
        last = s.steps[-1]
        assert last.expected_output.applied_rules == ("IHC-002",)
        # Verify a prior IHC-004 retry occurred
        retry_steps = [step for step in s.steps if "IHC-004" in step.expected_output.applied_rules]
        assert len(retry_steps) >= 1


# ── IHC-003 (slides pending → IHC_QC hold) scenarios ────────────


class TestIHC003SlidesPending:
    """SC-052 and SC-053: Some slides still pending → IHC_QC self-loop."""

    def test_sc052_pending_hold(self) -> None:
        """SC-052: Some slides pending → hold at IHC_QC."""
        s = _load_by_id("SC-052")
        assert _terminal_state(s) == "IHC_QC"
        last = s.steps[-1]
        assert last.event_type == "ihc_qc"
        assert last.expected_output.applied_rules == ("IHC-003",)
        assert last.event_data["all_slides_complete"] is False

    def test_sc053_partial_completion(self) -> None:
        """SC-053: 3 of 5 slides complete, 2 pending → hold at IHC_QC."""
        s = _load_by_id("SC-053")
        assert _terminal_state(s) == "IHC_QC"
        last = s.steps[-1]
        assert last.expected_output.applied_rules == ("IHC-003",)
        # Verify per-slide data with pending slides
        slides = last.event_data["slides"]
        pending_slides = [s for s in slides if s["qc_result"] == "pending"]
        assert len(pending_slides) == 2, (
            f"Expected 2 pending slides, got {len(pending_slides)}. "
            f"All qc_results: {[s['qc_result'] for s in slides]}"
        )


# ── IHC-004 (staining failed → retry) scenarios ─────────────────


class TestIHC004StainingRetry:
    """SC-054 and SC-055: Staining failed → retry IHC_STAINING."""

    def test_sc054_staining_failed_retry(self) -> None:
        """SC-054: IHC staining failed → IHC_STAINING (retry)."""
        s = _load_by_id("SC-054")
        assert _terminal_state(s) == "IHC_STAINING"
        last = s.steps[-1]
        assert last.event_type == "ihc_qc"
        assert last.expected_output.applied_rules == ("IHC-004",)
        assert last.event_data["staining_failure"] is True
        assert last.event_data["tissue_available"] is True

    def test_sc055_partial_failure_retry(self) -> None:
        """SC-055: Staining failed on specific marker → retry IHC_STAINING."""
        s = _load_by_id("SC-055")
        assert _terminal_state(s) == "IHC_STAINING"
        last = s.steps[-1]
        assert last.expected_output.applied_rules == ("IHC-004",)
        assert last.event_data["failed_marker"] == "HER2"
        assert last.event_data["tissue_available"] is True


# ── IHC-005 (staining failed, QNS) scenarios ────────────────────


class TestIHC005StainingQNS:
    """SC-056 and SC-057: Staining failed, insufficient tissue → ORDER_TERMINATED_QNS."""

    def test_sc056_staining_qns(self) -> None:
        """SC-056: IHC staining failed, QNS → ORDER_TERMINATED_QNS."""
        s = _load_by_id("SC-056")
        assert _terminal_state(s) == "ORDER_TERMINATED_QNS"
        last = s.steps[-1]
        assert last.event_type == "ihc_qc"
        assert last.expected_output.applied_rules == ("IHC-005",)
        assert last.event_data["tissue_available"] is False

    def test_sc057_qns_after_retry(self) -> None:
        """SC-057: Staining failed after retry, no tissue → ORDER_TERMINATED_QNS."""
        s = _load_by_id("SC-057")
        assert _terminal_state(s) == "ORDER_TERMINATED_QNS"
        last = s.steps[-1]
        assert last.expected_output.applied_rules == ("IHC-005",)
        # Verify a prior IHC-004 retry occurred
        retry_steps = [step for step in s.steps if "IHC-004" in step.expected_output.applied_rules]
        assert len(retry_steps) >= 1


# ── IHC-006 (scoring complete → RESULTING) scenarios ─────────────


class TestIHC006ScoringComplete:
    """SC-058 and SC-059: Scoring complete, no equivocal → RESULTING."""

    def test_sc058_scoring_complete(self) -> None:
        """SC-058: Scoring complete, no equivocal → RESULTING."""
        s = _load_by_id("SC-058")
        assert _terminal_state(s) == "RESULTING"
        last = s.steps[-1]
        assert last.event_type == "ihc_scoring"
        assert last.expected_output.applied_rules == ("IHC-006",)
        assert last.event_data["any_equivocal"] is False

    def test_sc059_all_definitive_scores(self) -> None:
        """SC-059: All scores definitive (ER 90%, PR 85%, HER2 3+, Ki-67 20%)."""
        s = _load_by_id("SC-059")
        assert _terminal_state(s) == "RESULTING"
        last = s.steps[-1]
        assert last.expected_output.applied_rules == ("IHC-006",)
        scores = {sc["test"]: sc["value"] for sc in last.event_data["scores"]}
        assert scores["ER"] == "90%"
        assert scores["PR"] == "85%"
        assert scores["HER2"] == "3+"
        assert scores["Ki-67"] == "20%"


# ── IHC-007 (HER2 equivocal → SUGGEST_FISH_REFLEX) scenarios ────


class TestIHC007HER2Equivocal:
    """SC-060 and SC-061: HER2 equivocal (2+) → SUGGEST_FISH_REFLEX."""

    def test_sc060_her2_equivocal(self) -> None:
        """SC-060: HER2 2+ → SUGGEST_FISH_REFLEX, FISH_SUGGESTED flag set."""
        s = _load_by_id("SC-060")
        assert _terminal_state(s) == "SUGGEST_FISH_REFLEX"
        last = s.steps[-1]
        assert last.event_type == "ihc_scoring"
        assert last.expected_output.applied_rules == ("IHC-007",)
        assert "FISH_SUGGESTED" in last.expected_output.flags
        # Verify HER2 is equivocal
        her2_scores = [sc for sc in last.event_data["scores"] if sc["test"] == "HER2"]
        assert len(her2_scores) == 1, f"Expected 1 HER2 score, found {len(her2_scores)}"
        assert her2_scores[0]["value"] == "2+"
        assert her2_scores[0]["equivocal"] is True

    def test_sc061_her2_equivocal_high_ki67(self) -> None:
        """SC-061: HER2 2+ with high Ki-67 → SUGGEST_FISH_REFLEX (Ki-67 doesn't affect)."""
        s = _load_by_id("SC-061")
        assert _terminal_state(s) == "SUGGEST_FISH_REFLEX"
        last = s.steps[-1]
        assert last.expected_output.applied_rules == ("IHC-007",)
        assert "FISH_SUGGESTED" in last.expected_output.flags
        # Verify Ki-67 is high but doesn't affect FISH decision
        ki67_scores = [sc for sc in last.event_data["scores"] if sc["test"] == "Ki-67"]
        assert len(ki67_scores) == 1, f"Expected 1 Ki-67 score, found {len(ki67_scores)}"
        assert ki67_scores[0]["value"] == "45%"
        assert ki67_scores[0]["equivocal"] is False


# ── IHC-008 (approve FISH → FISH_SEND_OUT) scenarios ────────────


class TestIHC008ApproveFISH:
    """SC-062 and SC-063: Pathologist approves FISH → FISH_SEND_OUT."""

    def test_sc062_approve_fish(self) -> None:
        """SC-062: Pathologist approves FISH → FISH_SEND_OUT."""
        s = _load_by_id("SC-062")
        assert _terminal_state(s) == "FISH_SEND_OUT"
        last = s.steps[-1]
        assert last.event_type == "fish_decision"
        assert last.event_data["approved"] is True
        assert last.expected_output.applied_rules == ("IHC-008",)

    def test_sc063_approve_fish_borderline_fixation(self) -> None:
        """SC-063: Approve FISH on borderline fixation case → FISH_SEND_OUT."""
        s = _load_by_id("SC-063")
        assert _terminal_state(s) == "FISH_SEND_OUT"
        last = s.steps[-1]
        assert last.expected_output.applied_rules == ("IHC-008",)
        # Verify borderline fixation time at accessioning (6.0hr = lower boundary)
        assert s.steps[0].event_data["fixation_time_hours"] == 6.0


# ── IHC-009 (decline FISH → RESULTING) scenarios ────────────────


class TestIHC009DeclineFISH:
    """SC-064 and SC-065: Pathologist declines FISH → RESULTING."""

    def test_sc064_decline_fish(self) -> None:
        """SC-064: Pathologist declines FISH → RESULTING."""
        s = _load_by_id("SC-064")
        assert _terminal_state(s) == "RESULTING"
        last = s.steps[-1]
        assert last.event_type == "fish_decision"
        assert last.event_data["approved"] is False
        assert last.expected_output.applied_rules == ("IHC-009",)

    def test_sc065_decline_fish_dcis(self) -> None:
        """SC-065: Decline FISH on DCIS pathway, FISH_SUGGESTED still set → RESULTING."""
        s = _load_by_id("SC-065")
        assert _terminal_state(s) == "RESULTING"
        last = s.steps[-1]
        assert last.expected_output.applied_rules == ("IHC-009",)
        # Verify FISH_SUGGESTED was set at scoring step
        scoring_steps = [
            step for step in s.steps if "IHC-007" in step.expected_output.applied_rules
        ]
        assert len(scoring_steps) == 1
        assert "FISH_SUGGESTED" in scoring_steps[0].expected_output.flags
        # Verify DCIS pathway
        he_reviews = [step for step in s.steps if step.event_type == "pathologist_he_review"]
        assert len(he_reviews) == 1, (
            f"Expected 1 pathologist_he_review step, found {len(he_reviews)}"
        )
        assert he_reviews[0].event_data["diagnosis"] == "dcis"


# ── IHC-010 (FISH result → RESULTING) scenarios ─────────────────


class TestIHC010FISHResult:
    """SC-066 and SC-067: FISH result received → RESULTING."""

    def test_sc066_fish_negative(self) -> None:
        """SC-066: FISH result received (negative) → RESULTING."""
        s = _load_by_id("SC-066")
        assert _terminal_state(s) == "RESULTING"
        last = s.steps[-1]
        assert last.event_type == "fish_result"
        assert last.event_data["result"] == "negative"
        assert last.event_data["status"] == "success"
        assert last.expected_output.applied_rules == ("IHC-010",)

    def test_sc067_fish_amplified(self) -> None:
        """SC-067: FISH amplified (positive) → RESULTING."""
        s = _load_by_id("SC-067")
        assert _terminal_state(s) == "RESULTING"
        last = s.steps[-1]
        assert last.event_type == "fish_result"
        assert last.event_data["result"] == "positive"
        assert last.expected_output.applied_rules == ("IHC-010",)


# ── IHC-011 (FISH QNS → ORDER_TERMINATED_QNS) scenarios ─────────


class TestIHC011FISHQNS:
    """SC-068 and SC-069: FISH external lab QNS → ORDER_TERMINATED_QNS."""

    def test_sc068_fish_qns(self) -> None:
        """SC-068: FISH external lab QNS → ORDER_TERMINATED_QNS."""
        s = _load_by_id("SC-068")
        assert _terminal_state(s) == "ORDER_TERMINATED_QNS"
        last = s.steps[-1]
        assert last.event_type == "fish_result"
        assert last.event_data["status"] == "qns"
        assert last.expected_output.applied_rules == ("IHC-011",)

    def test_sc069_fish_qns_extended(self) -> None:
        """SC-069: FISH QNS after extended processing → ORDER_TERMINATED_QNS."""
        s = _load_by_id("SC-069")
        assert _terminal_state(s) == "ORDER_TERMINATED_QNS"
        last = s.steps[-1]
        assert last.expected_output.applied_rules == ("IHC-011",)
        assert last.event_data["extended_processing"] is True


# ── Cross-cutting IHC validation ─────────────────────────────────


class TestIHCStainingPassthrough:
    """Validate that ihc_staining_complete transitions have empty rules (except IHC-001)."""

    def test_ihc_staining_passthrough(self) -> None:
        """ihc_staining_complete → IHC_QC should have no rules (passthrough)."""
        for sid in [f"SC-{i:03d}" for i in range(IHC_SCENARIO_START, IHC_SCENARIO_END)]:
            s = _load_by_id(sid)
            staining_steps = [
                step
                for step in s.steps
                if step.event_type == "ihc_staining_complete"
                and step.expected_output.next_state == "IHC_QC"
            ]
            for step in staining_steps:
                assert step.expected_output.applied_rules == (), (
                    f"{sid} step {step.step}: ihc_staining_complete → IHC_QC "
                    f"should have empty applied_rules, got {step.expected_output.applied_rules}"
                )


class TestIHCFlagLifecycle:
    """Validate IHC flag lifecycle across scenarios."""

    def test_her2_fixation_reject_only_in_ihc001(self) -> None:
        """HER2_FIXATION_REJECT should only appear in SC-048."""
        for sid in [f"SC-{i:03d}" for i in range(IHC_SCENARIO_START, IHC_SCENARIO_END)]:
            s = _load_by_id(sid)
            all_flags = []
            for step in s.steps:
                all_flags.extend(step.expected_output.flags)
            if sid == "SC-048":
                assert "HER2_FIXATION_REJECT" in all_flags, (
                    f"{sid} should have HER2_FIXATION_REJECT flag"
                )
            else:
                assert "HER2_FIXATION_REJECT" not in all_flags, (
                    f"{sid} should not have HER2_FIXATION_REJECT flag"
                )

    def test_fish_suggested_in_equivocal_scenarios(self) -> None:
        """FISH_SUGGESTED should appear in scenarios with IHC-007."""
        fish_suggested_sids = {
            "SC-060",
            "SC-061",
            "SC-062",
            "SC-063",
            "SC-064",
            "SC-065",
            "SC-066",
            "SC-067",
            "SC-068",
            "SC-069",
        }
        for sid in [f"SC-{i:03d}" for i in range(IHC_SCENARIO_START, IHC_SCENARIO_END)]:
            s = _load_by_id(sid)
            all_flags = []
            for step in s.steps:
                all_flags.extend(step.expected_output.flags)
            if sid in fish_suggested_sids:
                assert "FISH_SUGGESTED" in all_flags, f"{sid} should have FISH_SUGGESTED flag"
            else:
                assert "FISH_SUGGESTED" not in all_flags, (
                    f"{sid} should not have FISH_SUGGESTED flag"
                )


class TestFISHPathway:
    """Validate the full FISH pathway: IHC_SCORING → SUGGEST_FISH → FISH_SEND_OUT → RESULTING."""

    def test_full_fish_positive_path(self) -> None:
        """SC-066: Full path through FISH → RESULTING."""
        s = _load_by_id("SC-066")
        states = [step.expected_output.next_state for step in s.steps]
        # Verify FISH pathway states appear in order
        assert "SUGGEST_FISH_REFLEX" in states
        assert "FISH_SEND_OUT" in states
        fish_idx = states.index("FISH_SEND_OUT")
        suggest_idx = states.index("SUGGEST_FISH_REFLEX")
        assert suggest_idx < fish_idx

    def test_full_fish_qns_path(self) -> None:
        """SC-068: Full path through FISH → ORDER_TERMINATED_QNS."""
        s = _load_by_id("SC-068")
        states = [step.expected_output.next_state for step in s.steps]
        assert "SUGGEST_FISH_REFLEX" in states
        assert "FISH_SEND_OUT" in states
        assert "ORDER_TERMINATED_QNS" in states


class TestIHCPerSlideEventData:
    """Validate per-slide event_data in IHC QC scenarios."""

    VALID_QC_RESULTS = {"pass", "fail", "pending"}

    def test_ihc_qc_events_have_slides(self) -> None:
        """IHC QC events in IHC-002/003 scenarios include per-slide data."""
        for sid in ("SC-050", "SC-052", "SC-053"):
            s = _load_by_id(sid)
            ihc_qc_steps = [
                step
                for step in s.steps
                if step.event_type == "ihc_qc" and "slides" in step.event_data
            ]
            assert len(ihc_qc_steps) >= 1, f"{sid} should have ihc_qc steps with per-slide data"
            for step in ihc_qc_steps:
                slides = step.event_data["slides"]
                assert isinstance(slides, list)
                assert len(slides) >= 4
                for slide in slides:
                    assert "test" in slide
                    assert "qc_result" in slide

    def test_ihc_qc_slide_structure(self) -> None:
        """IHC QC slides must have required fields with valid qc_result values."""
        for sid in [f"SC-{i:03d}" for i in range(IHC_SCENARIO_START, IHC_SCENARIO_END)]:
            s = _load_by_id(sid)
            for step in s.steps:
                if step.event_type != "ihc_qc" or "slides" not in step.event_data:
                    continue
                for i, slide in enumerate(step.event_data["slides"]):
                    assert "test" in slide, f"{sid} step {step.step}: slides[{i}] missing 'test'"
                    assert "qc_result" in slide, (
                        f"{sid} step {step.step}: slides[{i}] missing 'qc_result'"
                    )
                    assert slide["qc_result"] in self.VALID_QC_RESULTS, (
                        f"{sid} step {step.step}: slides[{i}] has invalid "
                        f"qc_result '{slide['qc_result']}', "
                        f"expected one of {self.VALID_QC_RESULTS}"
                    )


class TestIHC001SelfLoop:
    """Validate that IHC-001 causes a self-loop at IHC_STAINING, not a passthrough."""

    def test_ihc001_self_loop_not_passthrough(self) -> None:
        """SC-048: IHC-001 keeps the order at IHC_STAINING (self-loop)."""
        s = _load_by_id("SC-048")
        ihc_staining_loops = [
            step
            for step in s.steps
            if step.event_type == "ihc_staining_complete"
            and step.expected_output.next_state == "IHC_STAINING"
        ]
        assert len(ihc_staining_loops) == 1, "SC-048 should have exactly one IHC_STAINING self-loop"
        step = ihc_staining_loops[0]
        assert "IHC-001" in step.expected_output.applied_rules, (
            "SC-048 IHC_STAINING self-loop must apply IHC-001"
        )
        assert "HER2_FIXATION_REJECT" in step.expected_output.flags, (
            "SC-048 IHC_STAINING self-loop must set HER2_FIXATION_REJECT flag"
        )


class TestFISHSuggestedLifecycle:
    """Validate FISH_SUGGESTED is set exactly once, at the IHC-007 step."""

    def test_fish_suggested_set_at_ihc007(self) -> None:
        """FISH_SUGGESTED should appear only at the IHC-007 scoring step."""
        fish_scenarios = [f"SC-{i:03d}" for i in range(60, 70)]
        for sid in fish_scenarios:
            s = _load_by_id(sid)
            steps_with_flag = [
                step for step in s.steps if "FISH_SUGGESTED" in step.expected_output.flags
            ]
            assert len(steps_with_flag) == 1, (
                f"{sid}: FISH_SUGGESTED set at {len(steps_with_flag)} steps, expected exactly 1"
            )
            assert "IHC-007" in steps_with_flag[0].expected_output.applied_rules, (
                f"{sid}: FISH_SUGGESTED set at step {steps_with_flag[0].step} "
                f"but IHC-007 is not applied"
            )


class TestFISHPathwaySequence:
    """Validate complete FISH pathway state sequences."""

    EXPECTED_SEQUENCES = {
        "SC-066": ["SUGGEST_FISH_REFLEX", "FISH_SEND_OUT", "RESULTING"],
        "SC-067": ["SUGGEST_FISH_REFLEX", "FISH_SEND_OUT", "RESULTING"],
        "SC-068": ["SUGGEST_FISH_REFLEX", "FISH_SEND_OUT", "ORDER_TERMINATED_QNS"],
        "SC-069": ["SUGGEST_FISH_REFLEX", "FISH_SEND_OUT", "ORDER_TERMINATED_QNS"],
    }

    def test_fish_pathway_complete_sequence(self) -> None:
        """FISH pathways must follow exact state sequences."""
        for sid, expected in self.EXPECTED_SEQUENCES.items():
            s = _load_by_id(sid)
            all_states = [step.expected_output.next_state for step in s.steps]
            # Extract FISH-related subsequence
            fish_states = []
            in_fish = False
            for state in all_states:
                if state == "SUGGEST_FISH_REFLEX":
                    in_fish = True
                if in_fish:
                    fish_states.append(state)
                    if state in ("RESULTING", "ORDER_TERMINATED_QNS"):
                        break
            assert fish_states == expected, (
                f"{sid}: FISH pathway is {fish_states}, expected {expected}"
            )


class TestIHC006ScoreCompleteness:
    """Validate that IHC-006 scoring scenarios include all expected markers."""

    def test_all_markers_present(self) -> None:
        """IHC-006 scenarios must have scores for ER, PR, HER2, Ki-67."""
        expected_markers = {"ER", "PR", "HER2", "Ki-67"}
        for sid in ("SC-058", "SC-059"):
            s = _load_by_id(sid)
            scoring_steps = [step for step in s.steps if step.event_type == "ihc_scoring"]
            assert len(scoring_steps) >= 1, f"{sid} has no ihc_scoring step"
            for step in scoring_steps:
                test_names = {sc["test"] for sc in step.event_data["scores"]}
                assert expected_markers.issubset(test_names), (
                    f"{sid} step {step.step}: scores missing markers "
                    f"{expected_markers - test_names}"
                )


class TestIHCRetryLimits:
    """Validate that retry scenarios stay within reasonable bounds."""

    def test_ihc004_retry_count(self) -> None:
        """IHC-004 retry scenarios should have at most 2 retries."""
        for sid in ("SC-051", "SC-057"):
            s = _load_by_id(sid)
            retry_count = sum(
                1 for step in s.steps if "IHC-004" in step.expected_output.applied_rules
            )
            assert retry_count <= 2, f"{sid} has {retry_count} IHC-004 retries, expected <= 2"


class TestIHCEventDataStructure:
    """Validate required event_data fields per event type across IHC scenarios."""

    VALID_STAINING_OUTCOMES = {"success", "partial", "failure"}

    def test_ihc_staining_complete_has_outcome(self) -> None:
        """ihc_staining_complete events must have an outcome field."""
        for sid in [f"SC-{i:03d}" for i in range(IHC_SCENARIO_START, IHC_SCENARIO_END)]:
            s = _load_by_id(sid)
            for step in s.steps:
                if step.event_type != "ihc_staining_complete":
                    continue
                assert "outcome" in step.event_data, (
                    f"{sid} step {step.step}: ihc_staining_complete missing 'outcome'"
                )
                assert step.event_data["outcome"] in self.VALID_STAINING_OUTCOMES, (
                    f"{sid} step {step.step}: outcome '{step.event_data['outcome']}' "
                    f"not in {self.VALID_STAINING_OUTCOMES}"
                )

    def test_ihc_scoring_has_required_fields(self) -> None:
        """ihc_scoring events must have scores and any_equivocal fields."""
        for sid in [f"SC-{i:03d}" for i in range(IHC_SCENARIO_START, IHC_SCENARIO_END)]:
            s = _load_by_id(sid)
            for step in s.steps:
                if step.event_type != "ihc_scoring":
                    continue
                assert "scores" in step.event_data, (
                    f"{sid} step {step.step}: ihc_scoring missing 'scores'"
                )
                assert "any_equivocal" in step.event_data, (
                    f"{sid} step {step.step}: ihc_scoring missing 'any_equivocal'"
                )


# ── RES-001 (MISSING_INFO_PROCEED → RESULTING_HOLD) scenarios ────


class TestRES001Hold:
    """SC-070 and SC-071: MISSING_INFO_PROCEED flag triggers RESULTING_HOLD."""

    def test_sc070_resulting_hold(self) -> None:
        """SC-070: Clean invasive path, MISSING_INFO_PROCEED → RESULTING_HOLD."""
        s = _load_by_id("SC-070")
        assert _terminal_state(s) == "RESULTING_HOLD"
        last = s.steps[-1]
        assert last.event_type == "resulting_review"
        assert last.event_data["outcome"] == "hold"
        assert last.expected_output.applied_rules == ("RES-001",)
        # Verify ACC-007 at step 1 with MISSING_INFO_PROCEED flag
        assert _first_step_rules(s) == ("ACC-007",)
        assert "MISSING_INFO_PROCEED" in s.steps[0].expected_output.flags

    def test_sc071_resulting_hold_after_fish(self) -> None:
        """SC-071: FISH pathway + MISSING_INFO_PROCEED → RESULTING_HOLD."""
        s = _load_by_id("SC-071")
        assert _terminal_state(s) == "RESULTING_HOLD"
        last = s.steps[-1]
        assert last.expected_output.applied_rules == ("RES-001",)
        _verify_fish_pathway(s)


# ── RES-002 (info received → RESULTING) scenarios ────────────────


class TestRES002Resolve:
    """SC-072: flag cleared → RESULTING; SC-073: flag persists → RESULTING_HOLD."""

    def test_sc072_billing_info_resolved(self) -> None:
        """SC-072: billing_info resolved at RESULTING_HOLD → RESULTING."""
        s = _load_by_id("SC-072")
        assert _terminal_state(s) == "RESULTING"
        last = s.steps[-1]
        assert last.event_type == "missing_info_received"
        assert last.expected_output.applied_rules == ("RES-002",)
        assert last.event_data["info_type"] == "billing"

    def test_sc073_irrelevant_info_still_held(self) -> None:
        """SC-073: Irrelevant info received — flag persists, remains RESULTING_HOLD."""
        s = _load_by_id("SC-073")
        assert _terminal_state(s) == "RESULTING_HOLD"
        last = s.steps[-1]
        assert last.event_type == "missing_info_received"
        assert last.expected_output.applied_rules == ("RES-002",)
        assert last.event_data["info_type"] != "billing"


# ── RES-003 (all complete → PATHOLOGIST_SIGNOUT) scenarios ───────


class TestRES003Signout:
    """SC-074 and SC-075: No flags, all complete → PATHOLOGIST_SIGNOUT."""

    def test_sc074_advance_to_signout(self) -> None:
        """SC-074: Clean invasive, resulting_review advance → PATHOLOGIST_SIGNOUT."""
        s = _load_by_id("SC-074")
        assert _terminal_state(s) == "PATHOLOGIST_SIGNOUT"
        last = s.steps[-1]
        assert last.event_type == "resulting_review"
        assert last.event_data["outcome"] == "advance"
        assert last.expected_output.applied_rules == ("RES-003",)

    def test_sc075_advance_after_fish(self) -> None:
        """SC-075: FISH pathway preceded resulting_review advance → PATHOLOGIST_SIGNOUT."""
        s = _load_by_id("SC-075")
        assert _terminal_state(s) == "PATHOLOGIST_SIGNOUT"
        last = s.steps[-1]
        assert last.expected_output.applied_rules == ("RES-003",)
        _verify_fish_pathway(s)


# ── RES-004 (pathologist signout → REPORT_GENERATION) scenarios ──


class TestRES004Report:
    """SC-076 and SC-077: Pathologist selects reportable tests → REPORT_GENERATION."""

    def test_sc076_all_tests_reported(self) -> None:
        """SC-076: All 5 tests in reportable_tests → REPORT_GENERATION."""
        s = _load_by_id("SC-076")
        assert _terminal_state(s) == "REPORT_GENERATION"
        last = s.steps[-1]
        assert last.event_type == "pathologist_signout"
        assert last.expected_output.applied_rules == ("RES-004",)
        assert len(last.event_data["reportable_tests"]) == 5

    def test_sc077_subset_reported(self) -> None:
        """SC-077: Subset (3 tests) in reportable_tests → REPORT_GENERATION."""
        s = _load_by_id("SC-077")
        assert _terminal_state(s) == "REPORT_GENERATION"
        last = s.steps[-1]
        assert last.expected_output.applied_rules == ("RES-004",)
        assert len(last.event_data["reportable_tests"]) == 3


# ── RES-005 (report generated → ORDER_COMPLETE) scenarios ────────


class TestRES005Complete:
    """SC-078 and SC-079: Report generated → ORDER_COMPLETE."""

    def test_sc078_order_complete(self) -> None:
        """SC-078: Clean path, report generated → ORDER_COMPLETE."""
        s = _load_by_id("SC-078")
        assert _terminal_state(s) == "ORDER_COMPLETE"
        last = s.steps[-1]
        assert last.event_type == "report_generated"
        assert last.expected_output.applied_rules == ("RES-005",)

    def test_sc079_full_lifecycle_complete(self) -> None:
        """SC-079: Full lifecycle with all 5 RES rules → ORDER_COMPLETE."""
        s = _load_by_id("SC-079")
        assert _terminal_state(s) == "ORDER_COMPLETE"
        last = s.steps[-1]
        assert last.expected_output.applied_rules == ("RES-005",)


# ── Resulting passthrough validation ──────────────────────────────


class TestResultingPassthrough:
    """Validate passthrough transitions in resulting scenarios have empty rules."""

    def test_he_staining_passthrough(self) -> None:
        """he_staining_complete in resulting scenarios has empty applied_rules."""
        for sid in [f"SC-{i:03d}" for i in range(RES_SCENARIO_START, RES_SCENARIO_END)]:
            s = _load_by_id(sid)
            for step in s.steps:
                if step.event_type == "he_staining_complete":
                    assert step.expected_output.applied_rules == (), (
                        f"{sid} step {step.step}: he_staining_complete should "
                        f"have empty applied_rules"
                    )

    def test_ihc_staining_passthrough(self) -> None:
        """ihc_staining_complete in resulting scenarios has empty applied_rules."""
        for sid in [f"SC-{i:03d}" for i in range(RES_SCENARIO_START, RES_SCENARIO_END)]:
            s = _load_by_id(sid)
            for step in s.steps:
                if step.event_type == "ihc_staining_complete":
                    assert step.expected_output.applied_rules == (), (
                        f"{sid} step {step.step}: ihc_staining_complete should "
                        f"have empty applied_rules"
                    )


# ── Cross-cutting resulting validation ────────────────────────────


class TestResultingReviewOutcomes:
    """Validate resulting_review events have correct outcomes."""

    VALID_RESULTING_REVIEW_OUTCOMES = {"hold", "advance"}

    def test_all_outcomes_valid(self) -> None:
        """Every resulting_review event uses a valid outcome value."""
        for sid in [f"SC-{i:03d}" for i in range(RES_SCENARIO_START, RES_SCENARIO_END)]:
            s = _load_by_id(sid)
            for step in s.steps:
                if step.event_type != "resulting_review":
                    continue
                assert step.event_data["outcome"] in self.VALID_RESULTING_REVIEW_OUTCOMES, (
                    f"{sid} step {step.step}: resulting_review outcome "
                    f"'{step.event_data['outcome']}' not in "
                    f"{self.VALID_RESULTING_REVIEW_OUTCOMES}"
                )

    def test_hold_outcomes(self) -> None:
        """SC-070, SC-071, SC-073 have resulting_review outcome 'hold'."""
        for sid in ("SC-070", "SC-071", "SC-073"):
            s = _load_by_id(sid)
            review_steps = [step for step in s.steps if step.event_type == "resulting_review"]
            assert len(review_steps) >= 1, f"{sid} has no resulting_review step"
            assert review_steps[0].event_data["outcome"] == "hold", (
                f"{sid} resulting_review outcome should be 'hold'"
            )

    def test_advance_outcomes(self) -> None:
        """SC-074..078 have exactly one resulting_review with advance outcome."""
        for sid in ("SC-074", "SC-075", "SC-076", "SC-077", "SC-078"):
            s = _load_by_id(sid)
            review_steps = [step for step in s.steps if step.event_type == "resulting_review"]
            assert len(review_steps) == 1, (
                f"{sid} should have exactly one resulting_review, got {len(review_steps)}"
            )
            assert review_steps[0].event_data["outcome"] == "advance", (
                f"{sid} resulting_review outcome should be 'advance'"
            )

    def test_sc079_mixed_outcomes(self) -> None:
        """SC-079 has both hold and advance outcomes (full lifecycle)."""
        s = _load_by_id("SC-079")
        review_steps = [step for step in s.steps if step.event_type == "resulting_review"]
        outcomes = [step.event_data["outcome"] for step in review_steps]
        assert "hold" in outcomes, "SC-079 should have a 'hold' outcome"
        assert "advance" in outcomes, "SC-079 should have an 'advance' outcome"


class TestMissingInfoProceedAtAccessioning:
    """MISSING_INFO_PROCEED flag set at step 1 (ACCESSIONING) and persists.

    ACC-007 is the only documented trigger for MISSING_INFO_PROCEED
    (billing_info_present=false). Once set, the flag persists until
    cleared by a missing_info_received event with billing info.
    """

    _ACC007_SCENARIOS = ("SC-070", "SC-071", "SC-072", "SC-073", "SC-079")

    def test_flag_set_at_step_1_and_persists(self) -> None:
        """MISSING_INFO_PROCEED is set at step 1 and persists until cleared."""
        for sid in self._ACC007_SCENARIOS:
            s = _load_by_id(sid)
            flag_active = True
            for step in s.steps:
                if step.step == 1:
                    assert "MISSING_INFO_PROCEED" in step.expected_output.flags, (
                        f"{sid} step 1 should have MISSING_INFO_PROCEED flag"
                    )
                elif (
                    step.event_type == "missing_info_received"
                    and step.event_data.get("info_type") == "billing"
                ):
                    flag_active = False
                elif flag_active:
                    assert "MISSING_INFO_PROCEED" in step.expected_output.flags, (
                        f"{sid} step {step.step} should carry MISSING_INFO_PROCEED flag"
                    )

    def test_acc007_is_sole_trigger(self) -> None:
        """ACC-007 is the only rule that first sets MISSING_INFO_PROCEED."""
        for sid in self._ACC007_SCENARIOS:
            s = _load_by_id(sid)
            # The flag must first appear at step 1 with ACC-007
            assert s.steps[0].expected_output.applied_rules == ("ACC-007",), (
                f"{sid} step 1: MISSING_INFO_PROCEED should be "
                f"set by ACC-007, got {s.steps[0].expected_output.applied_rules}"
            )


class TestReportableTestsPresent:
    """pathologist_signout events have valid reportable_tests."""

    VALID_TEST_NAMES = {"H&E", "ER", "PR", "HER2", "Ki-67", "FISH"}

    def test_reportable_tests_structure_and_content(self) -> None:
        """SC-076 through SC-079 have valid, non-empty reportable_tests lists."""
        for sid in ("SC-076", "SC-077", "SC-078", "SC-079"):
            s = _load_by_id(sid)
            signout_steps = [step for step in s.steps if step.event_type == "pathologist_signout"]
            assert len(signout_steps) >= 1, f"{sid} should have a pathologist_signout step"
            for step in signout_steps:
                tests = step.event_data["reportable_tests"]
                assert isinstance(tests, list), (
                    f"{sid} step {step.step}: reportable_tests must be a list, "
                    f"got {type(tests).__name__}"
                )
                assert len(tests) > 0, (
                    f"{sid} step {step.step}: reportable_tests should not be empty"
                )
                for test_name in tests:
                    assert isinstance(test_name, str) and test_name, (
                        f"{sid} step {step.step}: reportable_tests elements "
                        f"must be non-empty strings, got {test_name!r}"
                    )
                    assert test_name in self.VALID_TEST_NAMES, (
                        f"{sid} step {step.step}: unknown test name "
                        f"'{test_name}', expected one of {self.VALID_TEST_NAMES}"
                    )


class TestFullResultingLifecycle:
    """SC-079 contains all 5 RES rules across its steps."""

    def test_sc079_all_res_rules(self) -> None:
        """SC-079 must contain RES-001 through RES-005 in applied_rules."""
        s = _load_by_id("SC-079")
        all_rules: set[str] = set()
        for step in s.steps:
            all_rules.update(step.expected_output.applied_rules)
        expected_res = {"RES-001", "RES-002", "RES-003", "RES-004", "RES-005"}
        assert expected_res.issubset(all_rules), (
            f"SC-079 missing RES rules: {expected_res - all_rules}"
        )
