"""Tests verifying that rules and transitions are consistent.

Rules that imply specific routing (retry, hold, reject) must have
corresponding transitions in the YAML.
"""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture()
def transition_pairs(workflow_data: dict[str, Any]) -> set[tuple[str, str]]:
    """Set of (from, to) transition pairs."""
    return {(t["from"], t["to"]) for t in workflow_data["transitions"]}


# --- SP-002 retry self-loops ---


class TestSamplePrepRetry:
    """SP-002 (retry at current step) requires self-loop transitions."""

    @pytest.mark.parametrize(
        "state",
        [
            "SAMPLE_PREP_PROCESSING",
            "SAMPLE_PREP_EMBEDDING",
            "SAMPLE_PREP_SECTIONING",
        ],
    )
    def test_sp002_self_loop(self, state: str, transition_pairs: set[tuple[str, str]]) -> None:
        assert (state, state) in transition_pairs, f"SP-002 requires self-loop at {state}"


# --- IHC self-loops ---


class TestIHCSelfLoops:
    def test_ihc003_hold_self_loop(self, transition_pairs: set[tuple[str, str]]) -> None:
        """IHC-003 (hold, wait for remaining slides) → IHC_QC self-loop."""
        assert ("IHC_QC", "IHC_QC") in transition_pairs

    def test_ihc001_reject_self_loop(self, transition_pairs: set[tuple[str, str]]) -> None:
        """IHC-001 (reject HER2 for fixation) → IHC_STAINING self-loop."""
        assert ("IHC_STAINING", "IHC_STAINING") in transition_pairs


# --- IHC-010 FISH result ---


class TestFISHResult:
    def test_ihc010_routes_from_fish_send_out(self, transition_pairs: set[tuple[str, str]]) -> None:
        """IHC-010 routes from FISH_SEND_OUT to RESULTING."""
        outbound = {to for (frm, to) in transition_pairs if frm == "FISH_SEND_OUT"}
        assert "RESULTING" in outbound


# --- Accessioning rule-transition mapping ---


class TestAccessioningConsistency:
    def test_reject_maps_to_do_not_process(self, transition_pairs: set[tuple[str, str]]) -> None:
        assert ("ACCESSIONING", "DO_NOT_PROCESS") in transition_pairs

    def test_hold_maps_to_missing_info_hold(self, transition_pairs: set[tuple[str, str]]) -> None:
        assert ("ACCESSIONING", "MISSING_INFO_HOLD") in transition_pairs

    def test_proceed_maps_to_missing_info_proceed(
        self, transition_pairs: set[tuple[str, str]]
    ) -> None:
        assert ("ACCESSIONING", "MISSING_INFO_PROCEED") in transition_pairs

    def test_accept_maps_to_accepted(self, transition_pairs: set[tuple[str, str]]) -> None:
        assert ("ACCESSIONING", "ACCEPTED") in transition_pairs


# --- HE_QC rule-transition mapping ---


class TestHEQCConsistency:
    def test_he001_pass_to_pathologist_review(self, transition_pairs: set[tuple[str, str]]) -> None:
        assert ("HE_QC", "PATHOLOGIST_HE_REVIEW") in transition_pairs

    def test_he002_fail_restain_to_he_staining(
        self, transition_pairs: set[tuple[str, str]]
    ) -> None:
        assert ("HE_QC", "HE_STAINING") in transition_pairs

    def test_he003_fail_recut_to_sectioning(self, transition_pairs: set[tuple[str, str]]) -> None:
        assert ("HE_QC", "SAMPLE_PREP_SECTIONING") in transition_pairs

    def test_he004_fail_qns(self, transition_pairs: set[tuple[str, str]]) -> None:
        assert ("HE_QC", "ORDER_TERMINATED_QNS") in transition_pairs


# --- Pathologist H&E review rule-transition mapping ---


class TestPathologistReviewConsistency:
    def test_he005_invasive_to_ihc(self, transition_pairs: set[tuple[str, str]]) -> None:
        """HE-005 (invasive carcinoma) routes to IHC_STAINING."""
        assert ("PATHOLOGIST_HE_REVIEW", "IHC_STAINING") in transition_pairs

    def test_he006_dcis_to_ihc(self, transition_pairs: set[tuple[str, str]]) -> None:
        """HE-006 (DCIS) routes to IHC_STAINING."""
        assert ("PATHOLOGIST_HE_REVIEW", "IHC_STAINING") in transition_pairs

    def test_he007_suspicious_to_ihc(self, transition_pairs: set[tuple[str, str]]) -> None:
        """HE-007 (suspicious/atypical) routes to IHC_STAINING."""
        assert ("PATHOLOGIST_HE_REVIEW", "IHC_STAINING") in transition_pairs

    def test_he008_benign_to_resulting(self, transition_pairs: set[tuple[str, str]]) -> None:
        """HE-008 (benign) cancels IHC and routes to RESULTING."""
        assert ("PATHOLOGIST_HE_REVIEW", "RESULTING") in transition_pairs

    def test_he009_recuts_to_sectioning(self, transition_pairs: set[tuple[str, str]]) -> None:
        """HE-009 (recuts requested) routes back to SAMPLE_PREP_SECTIONING."""
        assert ("PATHOLOGIST_HE_REVIEW", "SAMPLE_PREP_SECTIONING") in transition_pairs


# --- IHC scoring rule-transition mapping ---


class TestIHCScoringConsistency:
    def test_ihc006_no_equivocal_to_resulting(self, transition_pairs: set[tuple[str, str]]) -> None:
        """IHC-006 (scoring complete, no equivocal) routes to RESULTING."""
        assert ("IHC_SCORING", "RESULTING") in transition_pairs

    def test_ihc007_equivocal_to_suggest_fish(self, transition_pairs: set[tuple[str, str]]) -> None:
        """IHC-007 (HER2 equivocal) routes to SUGGEST_FISH_REFLEX."""
        assert ("IHC_SCORING", "SUGGEST_FISH_REFLEX") in transition_pairs


# --- FISH pathway rule-transition mapping ---


class TestFISHPathwayConsistency:
    def test_ihc008_approve_fish_to_send_out(self, transition_pairs: set[tuple[str, str]]) -> None:
        """IHC-008 (pathologist approves FISH) routes to FISH_SEND_OUT."""
        assert ("SUGGEST_FISH_REFLEX", "FISH_SEND_OUT") in transition_pairs

    def test_ihc009_decline_fish_to_resulting(self, transition_pairs: set[tuple[str, str]]) -> None:
        """IHC-009 (pathologist declines FISH) routes to RESULTING."""
        assert ("SUGGEST_FISH_REFLEX", "RESULTING") in transition_pairs

    def test_ihc011_fish_qns(self, transition_pairs: set[tuple[str, str]]) -> None:
        """IHC-011 (FISH external lab QNS) routes to ORDER_TERMINATED_QNS."""
        assert ("FISH_SEND_OUT", "ORDER_TERMINATED_QNS") in transition_pairs


# --- Resulting rule-transition mapping ---


class TestResultingConsistency:
    def test_res001_flag_to_hold(self, transition_pairs: set[tuple[str, str]]) -> None:
        """RES-001 (MISSING_INFO_PROCEED flag) routes to RESULTING_HOLD."""
        assert ("RESULTING", "RESULTING_HOLD") in transition_pairs

    def test_res002_info_received_to_resulting(
        self, transition_pairs: set[tuple[str, str]]
    ) -> None:
        """RES-002 (info received, flag cleared) routes back to RESULTING."""
        assert ("RESULTING_HOLD", "RESULTING") in transition_pairs

    def test_res003_complete_to_signout(self, transition_pairs: set[tuple[str, str]]) -> None:
        """RES-003 (all testing complete) routes to PATHOLOGIST_SIGNOUT."""
        assert ("RESULTING", "PATHOLOGIST_SIGNOUT") in transition_pairs

    def test_res004_signout_to_report(self, transition_pairs: set[tuple[str, str]]) -> None:
        """RES-004 (pathologist selects reportable tests) routes to REPORT_GENERATION."""
        assert ("PATHOLOGIST_SIGNOUT", "REPORT_GENERATION") in transition_pairs

    def test_res005_report_to_complete(self, transition_pairs: set[tuple[str, str]]) -> None:
        """RES-005 (report generated) routes to ORDER_COMPLETE."""
        assert ("REPORT_GENERATION", "ORDER_COMPLETE") in transition_pairs
