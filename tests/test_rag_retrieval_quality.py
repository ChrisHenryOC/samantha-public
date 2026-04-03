"""Retrieval quality tests for the RAG pipeline.

Validates that the right knowledge base chunks are retrieved for each
workflow step and rule ID. Requires a built RAG index (marks as integration).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.rag.indexer import RagIndexer
from src.rag.retriever import RagRetriever

_KB_PATH = Path(__file__).resolve().parent.parent / "knowledge_base"
_INDEX_PATH = Path(__file__).resolve().parent.parent / "data" / "rag_index"


@pytest.fixture(scope="module")
def retriever() -> RagRetriever:
    """Build index and create retriever for the real knowledge base."""
    if not _KB_PATH.exists():
        pytest.skip("Knowledge base not found")

    # Build a fresh index in the standard location.
    indexer = RagIndexer(_KB_PATH, _INDEX_PATH)
    indexer.build_index()
    return RagRetriever(_INDEX_PATH, knowledge_base_path=_KB_PATH, top_k=10)


def _source_files(results: list) -> set[str]:
    """Extract unique source files from retrieval results."""
    return {r.source_file for r in results}


def _has_source(results: list, partial: str) -> bool:
    """Check if any result's source_file contains the partial string."""
    return any(partial in r.source_file for r in results)


def _has_section(results: list, partial: str) -> bool:
    """Check if any result's section_title contains the partial string."""
    return any(partial.lower() in r.section_title.lower() for r in results)


def _has_text(results: list, text: str) -> bool:
    """Check if any result's text contains the given text."""
    return any(text in r.text for r in results)


# --- Workflow Step Retrieval Tests ---


@pytest.mark.integration
class TestWorkflowStepRetrieval:
    """Verify relevant SOP sections are retrieved for each workflow step."""

    def test_accessioning_retrieves_accessioning_sop(self, retriever: RagRetriever) -> None:
        results, info = retriever.retrieve_for_routing(
            current_state="ACCESSIONING",
            event_type="order_received",
            event_data={"patient_name": "Test", "ordered_tests": ["H&E"]},
        )
        assert _has_source(results, "accessioning"), (
            f"Expected accessioning SOP in results. Got: {_source_files(results)}"
        )

    def test_sample_prep_retrieves_sample_prep_sop(self, retriever: RagRetriever) -> None:
        results, info = retriever.retrieve_for_routing(
            current_state="SAMPLE_PREP_PROCESSING",
            event_type="processing_complete",
            event_data={"outcome": "pass"},
        )
        assert _has_source(results, "sample_prep"), (
            f"Expected sample_prep SOP in results. Got: {_source_files(results)}"
        )

    def test_he_review_retrieves_he_sop(self, retriever: RagRetriever) -> None:
        results, info = retriever.retrieve_for_routing(
            current_state="PATHOLOGIST_HE_REVIEW",
            event_type="pathologist_review",
            event_data={"diagnosis": "invasive_carcinoma"},
        )
        assert _has_source(results, "he_staining"), (
            f"Expected he_staining SOP in results. Got: {_source_files(results)}"
        )

    def test_ihc_staining_retrieves_ihc_sop(self, retriever: RagRetriever) -> None:
        results, info = retriever.retrieve_for_routing(
            current_state="IHC_STAINING",
            event_type="ihc_staining_complete",
            event_data={},
        )
        assert _has_source(results, "ihc_staining"), (
            f"Expected ihc_staining SOP in results. Got: {_source_files(results)}"
        )

    def test_resulting_retrieves_resulting_sop(self, retriever: RagRetriever) -> None:
        results, info = retriever.retrieve_for_routing(
            current_state="RESULTING",
            event_type="resulting_check",
            event_data={},
        )
        assert _has_source(results, "resulting"), (
            f"Expected resulting SOP in results. Got: {_source_files(results)}"
        )


# --- Rule Retrieval Tests ---


@pytest.mark.integration
class TestRuleRetrieval:
    """Verify specific rules are retrievable with matching event context."""

    @pytest.mark.parametrize(
        "rule_id,query",
        [
            ("ACC-001", "patient name missing accessioning validation"),
            ("ACC-002", "patient sex missing accessioning validation"),
            ("ACC-003", "non-breast anatomic site accessioning reject"),
            ("ACC-004", "invalid specimen type accessioning"),
            ("ACC-005", "wrong fixative HER2 formalin accessioning"),
            ("ACC-006", "fixation time out of tolerance HER2"),
            ("ACC-007", "billing information missing accessioning"),
            ("ACC-008", "all validations pass accepted accessioning"),
            ("ACC-009", "fixation time null missing HER2"),
        ],
    )
    def test_accessioning_rules_retrievable(
        self, retriever: RagRetriever, rule_id: str, query: str
    ) -> None:
        results, _ = retriever.retrieve(query)
        assert _has_text(results, rule_id), (
            f"Expected {rule_id} in retrieved text. Sources: {[r.source_file for r in results]}"
        )

    @pytest.mark.parametrize(
        "rule_id,query",
        [
            ("SP-001", "sample prep step advance processing embedding sectioning"),
            ("SP-002", "sample prep retry equipment malfunction"),
            ("SP-004", "sample prep QC pass route to HE staining"),
            ("SP-005", "sample prep QC fail resectioning"),
        ],
    )
    def test_sample_prep_rules_retrievable(
        self, retriever: RagRetriever, rule_id: str, query: str
    ) -> None:
        results, _ = retriever.retrieve(query)
        assert _has_text(results, rule_id), (
            f"Expected {rule_id} in retrieved text. Sources: {[r.source_file for r in results]}"
        )

    @pytest.mark.parametrize(
        "rule_id,query",
        [
            ("HE-001", "H&E QC pass pathologist review"),
            ("HE-002", "H&E QC fail restain"),
            ("HE-003", "H&E QC fail recut sectioning"),
            ("HE-004", "H&E QC quantity not sufficient QNS"),
        ],
    )
    def test_he_rules_retrievable(self, retriever: RagRetriever, rule_id: str, query: str) -> None:
        results, _ = retriever.retrieve(query)
        assert _has_text(results, rule_id), (
            f"Expected {rule_id} in retrieved text. Sources: {[r.source_file for r in results]}"
        )

    @pytest.mark.parametrize(
        "rule_id,query",
        [
            ("IHC-001", "IHC fixation reject wrong fixative HER2"),
            ("IHC-002", "IHC QC all slides pass"),
            ("IHC-003", "IHC QC slides pending hold"),
            ("IHC-004", "IHC QC stain failed retry"),
            ("IHC-006", "IHC scoring no equivocal resulting"),
            ("IHC-007", "IHC scoring HER2 equivocal FISH reflex"),
        ],
    )
    def test_ihc_rules_retrievable(self, retriever: RagRetriever, rule_id: str, query: str) -> None:
        results, _ = retriever.retrieve(query)
        assert _has_text(results, rule_id), (
            f"Expected {rule_id} in retrieved text. Sources: {[r.source_file for r in results]}"
        )

    @pytest.mark.parametrize(
        "rule_id,query",
        [
            ("RES-001", "resulting flag present hold"),
            ("RES-002", "resulting flag cleared info received"),
            ("RES-003", "resulting complete signout no flags"),
            ("RES-004", "resulting routing rules RES-004 signout reportable tests"),
            ("RES-005", "report generation complete order complete"),
        ],
    )
    def test_resulting_rules_retrievable(
        self, retriever: RagRetriever, rule_id: str, query: str
    ) -> None:
        results, _ = retriever.retrieve(query)
        assert _has_text(results, rule_id), (
            f"Expected {rule_id} in retrieved text. Sources: {[r.source_file for r in results]}"
        )


# --- Top-K Variation Tests ---


@pytest.mark.integration
class TestTopKVariation:
    """Test retrieval at different k values to identify optimal setting."""

    @pytest.mark.parametrize("k", [3, 5, 7, 10])
    def test_accessioning_coverage_at_k(self, retriever: RagRetriever, k: int) -> None:
        """Verify accessioning SOP is in top-k for accessioning queries."""
        results, _ = retriever.retrieve(
            "accessioning order received patient name validation", top_k=k
        )
        assert len(results) <= k
        assert _has_source(results, "accessioning")

    @pytest.mark.parametrize("k", [3, 5, 7, 10])
    def test_fixation_rules_coverage_at_k(self, retriever: RagRetriever, k: int) -> None:
        """Verify fixation rules doc is retrieved for HER2 fixation queries."""
        results, _ = retriever.retrieve(
            "HER2 fixation time formalin ASCO/CAP requirements", top_k=k
        )
        assert len(results) <= k
        if k >= 5:
            assert _has_source(results, "fixation_requirements")
