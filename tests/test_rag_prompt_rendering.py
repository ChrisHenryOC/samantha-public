"""Tests for RAG prompt rendering in query templates (issue #7)."""

from __future__ import annotations

from src.prediction.query_prompt_template import _format_rag_workflow_reference
from src.rag.retriever import RetrievalResult


def _make_chunk(
    text: str = "Rule text here.",
    source_file: str = "sops/acc.md",
    section_title: str = "Validation",
    doc_type: str = "sop",
    score: float = 0.9,
) -> RetrievalResult:
    return RetrievalResult(
        text=text,
        source_file=source_file,
        section_title=section_title,
        doc_type=doc_type,
        similarity_score=score,
    )


class TestFormatRagWorkflowReference:
    """Tests for query template's _format_rag_workflow_reference."""

    def test_empty_list_returns_no_context_message(self) -> None:
        result = _format_rag_workflow_reference([])
        assert result == "No relevant workflow context found."

    def test_single_chunk_formatted(self) -> None:
        chunk = _make_chunk(text="Workflow state info.")
        result = _format_rag_workflow_reference([chunk])
        assert "Reference 1" in result
        assert "sops/acc.md" in result
        assert "Workflow state info." in result

    def test_multiple_chunks_numbered(self) -> None:
        chunks = [
            _make_chunk(text="State A info."),
            _make_chunk(text="State B info.", source_file="sops/grossing.md"),
        ]
        result = _format_rag_workflow_reference(chunks)
        assert "Reference 1" in result
        assert "Reference 2" in result
