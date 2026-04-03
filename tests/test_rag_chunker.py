"""Tests for the section-aware markdown document chunker."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from src.rag.chunker import DocumentChunk, chunk_document, chunk_knowledge_base

# --- DocumentChunk dataclass validation ---


class TestDocumentChunk:
    def test_valid_construction(self) -> None:
        chunk = DocumentChunk(
            text="## Section\n\nSome content here.",
            source_file="sops/accessioning.md",
            section_title="Section",
            doc_type="sop",
            char_count=31,
        )
        assert chunk.text == "## Section\n\nSome content here."
        assert chunk.source_file == "sops/accessioning.md"
        assert chunk.section_title == "Section"
        assert chunk.doc_type == "sop"
        assert chunk.char_count == 31

    def test_frozen(self) -> None:
        chunk = DocumentChunk(
            text="## Test\n\nContent.",
            source_file="sops/test.md",
            section_title="Test",
            doc_type="sop",
            char_count=17,
        )
        with pytest.raises(AttributeError):
            chunk.text = "modified"  # type: ignore[misc]

    def test_empty_text_raises(self) -> None:
        with pytest.raises(ValueError, match="text must not be empty"):
            DocumentChunk(
                text="   ",
                source_file="sops/test.md",
                section_title="Test",
                doc_type="sop",
                char_count=3,
            )

    def test_empty_source_file_raises(self) -> None:
        with pytest.raises(ValueError, match="source_file must not be empty"):
            DocumentChunk(
                text="Some text",
                source_file="",
                section_title="Test",
                doc_type="sop",
                char_count=9,
            )

    def test_invalid_doc_type_raises(self) -> None:
        with pytest.raises(ValueError, match="doc_type must be"):
            DocumentChunk(
                text="Some text",
                source_file="test.md",
                section_title="Test",
                doc_type="invalid",
                char_count=9,
            )

    def test_negative_char_count_raises(self) -> None:
        with pytest.raises(ValueError, match="char_count must be non-negative"):
            DocumentChunk(
                text="Some text",
                source_file="test.md",
                section_title="Test",
                doc_type="sop",
                char_count=-1,
            )

    def test_wrong_type_text_raises(self) -> None:
        with pytest.raises(TypeError, match="text must be str"):
            DocumentChunk(
                text=123,  # type: ignore[arg-type]
                source_file="test.md",
                section_title="Test",
                doc_type="sop",
                char_count=3,
            )


# --- chunk_document ---


class TestChunkDocument:
    def test_basic_h2_splitting(self) -> None:
        content = textwrap.dedent("""\
            # Title

            Preamble content that is long enough to exceed the minimum chunk size threshold. {pad}

            ## Section One

            Content of section one that is long enough to be its own chunk. {pad}

            ## Section Two

            Content of section two that is long enough to be its own chunk. {pad}
        """).format(pad="x" * 100)
        chunks = chunk_document(content, "sops/test.md")
        # Preamble + 2 sections
        assert len(chunks) == 3
        assert chunks[0].section_title == "preamble"
        assert chunks[1].section_title == "Section One"
        assert chunks[2].section_title == "Section Two"

    def test_doc_type_inference_sop(self) -> None:
        content = "## Section\n\n" + "x" * 200
        chunks = chunk_document(content, "sops/accessioning.md")
        assert all(c.doc_type == "sop" for c in chunks)

    def test_doc_type_inference_rule(self) -> None:
        content = "## Section\n\n" + "x" * 200
        chunks = chunk_document(content, "rules/fixation_requirements.md")
        assert all(c.doc_type == "rule" for c in chunks)

    def test_doc_type_inference_reference(self) -> None:
        content = "## Section\n\n" + "x" * 200
        chunks = chunk_document(content, "workflow_states.md")
        assert all(c.doc_type == "reference" for c in chunks)

    def test_no_headers_single_chunk(self) -> None:
        content = "Just plain text with no markdown headers at all. " * 10
        chunks = chunk_document(content, "sops/test.md")
        assert len(chunks) == 1
        assert chunks[0].section_title == "preamble"

    def test_single_section(self) -> None:
        content = "## Only Section\n\nContent here. " * 10
        chunks = chunk_document(content, "sops/test.md")
        assert len(chunks) == 1
        assert chunks[0].section_title == "Only Section"

    def test_small_section_merged(self) -> None:
        content = textwrap.dedent("""\
            ## Big Section

            {big_content}

            ## Tiny

            Hi.

            ## Another Big

            {big_content}
        """).format(big_content="x" * 200)
        chunks = chunk_document(content, "sops/test.md", min_chunk_chars=100)
        # "Tiny" section is < 100 chars, should be merged with "Big Section"
        assert len(chunks) == 2
        assert chunks[0].section_title == "Big Section"
        assert "Tiny" in chunks[0].text  # merged into previous
        assert chunks[1].section_title == "Another Big"

    def test_char_count_matches(self) -> None:
        content = "## Test\n\nSome content here."
        chunks = chunk_document(content, "sops/test.md")
        for chunk in chunks:
            assert chunk.char_count == len(chunk.text)

    def test_empty_content_raises(self) -> None:
        with pytest.raises(ValueError, match="content must not be empty"):
            chunk_document("", "sops/test.md")

    def test_whitespace_content_raises(self) -> None:
        with pytest.raises(ValueError, match="content must not be empty"):
            chunk_document("   \n  ", "sops/test.md")

    def test_empty_source_file_raises(self) -> None:
        with pytest.raises(ValueError, match="source_file must not be empty"):
            chunk_document("## Test\n\nContent.", "")

    def test_h3_not_split(self) -> None:
        """H3 headers should NOT create chunk boundaries."""
        content = textwrap.dedent("""\
            ## Main Section

            Introduction.

            ### Subsection A

            Content A.

            ### Subsection B

            Content B.
        """)
        chunks = chunk_document(content, "sops/test.md")
        assert len(chunks) == 1
        assert "Subsection A" in chunks[0].text
        assert "Subsection B" in chunks[0].text

    def test_section_header_preserved_in_text(self) -> None:
        content = "## My Section\n\nContent below the header."
        chunks = chunk_document(content, "sops/test.md")
        assert chunks[0].text.startswith("## My Section")

    def test_preamble_excluded_when_empty(self) -> None:
        content = "## Section One\n\nContent."
        chunks = chunk_document(content, "sops/test.md")
        assert len(chunks) == 1
        assert chunks[0].section_title == "Section One"

    def test_min_chunk_chars_zero_no_merging(self) -> None:
        content = "## A\n\nx\n\n## B\n\ny"
        chunks = chunk_document(content, "sops/test.md", min_chunk_chars=0)
        assert len(chunks) == 2

    def test_source_file_with_subdirectory(self) -> None:
        content = "## Test\n\n" + "x" * 200
        chunks = chunk_document(content, "sops/accessioning.md")
        assert chunks[0].source_file == "sops/accessioning.md"


# --- chunk_knowledge_base ---


class TestChunkKnowledgeBase:
    def test_real_knowledge_base(self) -> None:
        """Smoke test against the actual knowledge base directory."""
        kb_path = Path(__file__).resolve().parent.parent / "knowledge_base"
        if not kb_path.exists():
            pytest.skip("Knowledge base directory not found")

        chunks = chunk_knowledge_base(kb_path)
        assert len(chunks) > 0

        # Every chunk should have valid metadata
        for chunk in chunks:
            assert chunk.text.strip()
            assert chunk.source_file
            assert chunk.doc_type in ("sop", "rule", "reference")
            assert chunk.char_count == len(chunk.text)

    def test_nonexistent_path_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            chunk_knowledge_base(Path("/nonexistent/path"))

    def test_empty_directory(self, tmp_path: Path) -> None:
        chunks = chunk_knowledge_base(tmp_path)
        assert chunks == []

    def test_single_file(self, tmp_path: Path) -> None:
        sops_dir = tmp_path / "sops"
        sops_dir.mkdir()
        (sops_dir / "test.md").write_text(
            "## Section A\n\n" + "Content. " * 30 + "\n\n## Section B\n\n" + "More. " * 30
        )
        chunks = chunk_knowledge_base(tmp_path)
        assert len(chunks) == 2
        assert chunks[0].doc_type == "sop"
        assert chunks[0].source_file == "sops/test.md"

    def test_multiple_files_sorted(self, tmp_path: Path) -> None:
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        (rules_dir / "b_rules.md").write_text("## B Rule\n\n" + "x" * 200)
        (rules_dir / "a_rules.md").write_text("## A Rule\n\n" + "y" * 200)
        chunks = chunk_knowledge_base(tmp_path)
        # Should be sorted by source file
        assert chunks[0].source_file == "rules/a_rules.md"
        assert chunks[1].source_file == "rules/b_rules.md"
