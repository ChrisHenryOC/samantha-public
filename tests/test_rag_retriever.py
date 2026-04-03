"""Tests for the RAG retriever."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.rag.indexer import RagIndexer
from src.rag.retriever import RagRetriever, RetrievalInfo, RetrievalResult

# --- RetrievalResult dataclass validation ---


class TestRetrievalResult:
    def test_valid_construction(self) -> None:
        r = RetrievalResult(
            text="Some chunk text.",
            source_file="sops/test.md",
            section_title="Section",
            doc_type="sop",
            similarity_score=0.85,
        )
        assert r.similarity_score == 0.85

    def test_frozen(self) -> None:
        r = RetrievalResult(
            text="Test",
            source_file="f.md",
            section_title="S",
            doc_type="sop",
            similarity_score=0.5,
        )
        with pytest.raises(AttributeError):
            r.text = "modified"  # type: ignore[misc]

    def test_empty_text_raises(self) -> None:
        with pytest.raises(ValueError, match="text must not be empty"):
            RetrievalResult(
                text="  ",
                source_file="f.md",
                section_title="S",
                doc_type="sop",
                similarity_score=0.5,
            )

    def test_wrong_type_score_raises(self) -> None:
        with pytest.raises(TypeError, match="similarity_score must be float"):
            RetrievalResult(
                text="text",
                source_file="f.md",
                section_title="S",
                doc_type="sop",
                similarity_score="high",  # type: ignore[arg-type]
            )


class TestRetrievalInfo:
    def test_valid_construction(self) -> None:
        info = RetrievalInfo(
            query_text="test query",
            chunks_retrieved=3,
            candidates_before_filter=5,
            scores=(0.9, 0.8, 0.7),
            top_sources=("sops/a.md", "rules/b.md", "sops/c.md"),
        )
        assert info.chunks_retrieved == 3
        assert info.candidates_before_filter == 5
        assert len(info.scores) == 3

    def test_wrong_type_raises(self) -> None:
        with pytest.raises(TypeError, match="query_text must be str"):
            RetrievalInfo(
                query_text=123,  # type: ignore[arg-type]
                chunks_retrieved=0,
                candidates_before_filter=0,
                scores=(),
                top_sources=(),
            )

    def test_score_out_of_bounds_raises(self) -> None:
        with pytest.raises(ValueError, match=r"scores\[0\] must be in \[0, 1\]"):
            RetrievalInfo(
                query_text="test",
                chunks_retrieved=1,
                candidates_before_filter=1,
                scores=(1.5,),
                top_sources=("a.md",),
            )

    def test_length_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="len\\(scores\\).*!= chunks_retrieved"):
            RetrievalInfo(
                query_text="test",
                chunks_retrieved=2,
                candidates_before_filter=2,
                scores=(0.5,),
                top_sources=("a.md", "b.md"),
            )

    def test_negative_chunks_retrieved_raises(self) -> None:
        with pytest.raises(ValueError, match="chunks_retrieved must be >= 0"):
            RetrievalInfo(
                query_text="test",
                chunks_retrieved=-1,
                candidates_before_filter=0,
                scores=(),
                top_sources=(),
            )

    def test_invalid_doc_type_raises(self) -> None:
        with pytest.raises(ValueError, match="doc_type must be one of"):
            RetrievalResult(
                text="text",
                source_file="f.md",
                section_title="S",
                doc_type="invalid",
                similarity_score=0.5,
            )


# --- RagRetriever integration tests ---


def _build_test_index(tmp_path: Path) -> Path:
    """Create a knowledge base and build an index for testing."""
    kb = tmp_path / "kb"
    sops = kb / "sops"
    sops.mkdir(parents=True)

    (sops / "accessioning.md").write_text(
        "# Accessioning SOP\n\n"
        "## 1. Purpose\n\n"
        "This procedure defines evaluation logic at accessioning. "
        "Patient name, patient sex, specimen type, and anatomic site "
        "are validated. Missing patient name triggers ACC-001. " * 3 + "\n\n"
        "## 2. Validation Checks\n\n"
        "ACC-001 through ACC-009 are evaluated against every order. "
        "Wrong fixative triggers DO_NOT_PROCESS rejection. " * 3
    )
    (sops / "sample_prep.md").write_text(
        "# Sample Prep SOP\n\n"
        "## 1. Processing\n\n"
        "Sample preparation includes processing, embedding, sectioning. "
        "SP-001 advances the sample through each sub-step. " * 3 + "\n\n"
        "## 2. Quality Control\n\n"
        "SP-004 routes samples to HE staining after QC pass. "
        "SP-005 triggers resectioning on QC failure. " * 3
    )

    index_path = tmp_path / "index"
    indexer = RagIndexer(kb, index_path)
    indexer.build_index()
    return index_path


@pytest.mark.integration
class TestRagRetriever:
    def test_retrieve_returns_results(self, tmp_path: Path) -> None:
        index_path = _build_test_index(tmp_path)
        retriever = RagRetriever(index_path, top_k=3, similarity_threshold=0.0)
        results, _ = retriever.retrieve("accessioning validation patient name")
        assert len(results) > 0
        assert len(results) <= 3

    def test_top_k_respected(self, tmp_path: Path) -> None:
        index_path = _build_test_index(tmp_path)
        retriever = RagRetriever(index_path, top_k=2, similarity_threshold=0.0)
        results, _ = retriever.retrieve("sample preparation quality control")
        assert len(results) > 0
        assert len(results) <= 2

    def test_metadata_preserved(self, tmp_path: Path) -> None:
        index_path = _build_test_index(tmp_path)
        retriever = RagRetriever(index_path, top_k=5, similarity_threshold=0.0)
        results, _ = retriever.retrieve("accessioning")
        assert len(results) > 0
        for r in results:
            assert r.source_file
            assert r.section_title
            assert r.doc_type in ("sop", "rule", "reference")
            assert 0.0 <= r.similarity_score <= 1.0

    def test_retrieve_for_routing(self, tmp_path: Path) -> None:
        index_path = _build_test_index(tmp_path)
        retriever = RagRetriever(index_path, top_k=3, similarity_threshold=0.0)
        results, info = retriever.retrieve_for_routing(
            current_state="ACCESSIONING",
            event_type="order_received",
            event_data={"ordered_tests": ["H&E", "HER2"]},
        )
        assert len(results) > 0
        assert isinstance(info, RetrievalInfo)
        assert info.chunks_retrieved == len(results)
        assert "ACCESSIONING" in info.query_text

    def test_routing_query_uses_rule_biased_terms(self, tmp_path: Path) -> None:
        index_path = _build_test_index(tmp_path)
        retriever = RagRetriever(index_path, top_k=3, similarity_threshold=0.0)
        _, info = retriever.retrieve_for_routing(
            current_state="SAMPLE_PREP_QC",
            event_type="qc_complete",
            event_data={"qc_result": "pass"},
        )
        assert "workflow rules for SAMPLE_PREP_QC" in info.query_text
        assert "rule triggers for event qc_complete" in info.query_text
        assert "validation checks routing decision" in info.query_text
        assert "qc_result: pass" in info.query_text

    def test_routing_query_includes_ordered_tests(self, tmp_path: Path) -> None:
        index_path = _build_test_index(tmp_path)
        retriever = RagRetriever(index_path, top_k=3, similarity_threshold=0.0)
        _, info = retriever.retrieve_for_routing(
            current_state="ACCESSIONING",
            event_type="order_received",
            event_data={"ordered_tests": ["H&E", "HER2"]},
        )
        assert "tests: H&E, HER2" in info.query_text

    def test_routing_query_includes_diagnosis(self, tmp_path: Path) -> None:
        index_path = _build_test_index(tmp_path)
        retriever = RagRetriever(index_path, top_k=3, similarity_threshold=0.0)
        _, info = retriever.retrieve_for_routing(
            current_state="HE_REVIEW",
            event_type="pathologist_review_complete",
            event_data={"diagnosis": "invasive ductal carcinoma"},
        )
        assert "diagnosis: invasive ductal carcinoma" in info.query_text

    def test_retrieve_for_query(self, tmp_path: Path) -> None:
        index_path = _build_test_index(tmp_path)
        retriever = RagRetriever(index_path, top_k=3, similarity_threshold=0.0)
        results, info = retriever.retrieve_for_query("What happens when sample prep QC fails?")
        assert len(results) > 0
        assert isinstance(info, RetrievalInfo)

    def test_similarity_threshold_filters(self, tmp_path: Path) -> None:
        index_path = _build_test_index(tmp_path)
        # With no threshold, we get results.
        retriever_no_thresh = RagRetriever(index_path, top_k=10, similarity_threshold=0.0)
        baseline, _ = retriever_no_thresh.retrieve("random unrelated gibberish xyzzy")
        # Very high threshold should filter out more results than no threshold.
        retriever_high = RagRetriever(index_path, top_k=10, similarity_threshold=0.99)
        results, _ = retriever_high.retrieve("random unrelated gibberish xyzzy")
        assert len(results) < len(baseline) or len(baseline) == 0

    def test_threshold_filters_all_returns_empty_with_candidate_count(self, tmp_path: Path) -> None:
        index_path = _build_test_index(tmp_path)
        retriever = RagRetriever(index_path, top_k=5, similarity_threshold=0.99)
        results, info = retriever.retrieve_for_routing(
            current_state="ACCESSIONING",
            event_type="order_received",
            event_data={},
        )
        assert results == []
        assert info.chunks_retrieved == 0
        assert info.candidates_before_filter > 0
