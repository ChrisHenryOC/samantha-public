"""Tests for the RAG indexer."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.rag.indexer import RagIndexer


def _create_test_kb(tmp_path: Path) -> Path:
    """Create a minimal knowledge base for testing."""
    kb = tmp_path / "knowledge_base"
    sops = kb / "sops"
    sops.mkdir(parents=True)
    rules = kb / "rules"
    rules.mkdir(parents=True)

    (sops / "test_sop.md").write_text(
        "# Test SOP\n\n"
        "## 1. Purpose\n\n"
        "This SOP defines the test procedure for unit testing. " * 5 + "\n\n"
        "## 2. Scope\n\n"
        "This applies to all test scenarios in the system. " * 5 + "\n\n"
        "## 3. Procedure\n\n"
        "Follow these steps to complete the test procedure. " * 5
    )
    (rules / "test_rules.md").write_text(
        "# Test Rules\n\n"
        "## Rule Section A\n\n"
        "Rule A applies when condition X is met. " * 5 + "\n\n"
        "## Rule Section B\n\n"
        "Rule B applies when condition Y is met. " * 5
    )
    return kb


@pytest.mark.integration
class TestRagIndexer:
    """Integration tests requiring sentence-transformers model download."""

    def test_build_index(self, tmp_path: Path) -> None:
        kb = _create_test_kb(tmp_path)
        index_path = tmp_path / "index"

        indexer = RagIndexer(kb, index_path)
        count = indexer.build_index()

        assert count > 0
        assert index_path.exists()

    def test_document_count(self, tmp_path: Path) -> None:
        kb = _create_test_kb(tmp_path)
        index_path = tmp_path / "index"

        indexer = RagIndexer(kb, index_path)
        indexer.build_index()

        collection = indexer.get_collection()
        assert collection.count() > 0

    def test_metadata_stored(self, tmp_path: Path) -> None:
        kb = _create_test_kb(tmp_path)
        index_path = tmp_path / "index"

        indexer = RagIndexer(kb, index_path)
        indexer.build_index()

        collection = indexer.get_collection()
        results = collection.get(include=["metadatas"])
        assert results["metadatas"] is not None
        for meta in results["metadatas"]:
            assert "source_file" in meta
            assert "section_title" in meta
            assert "doc_type" in meta

    def test_rebuild_idempotent(self, tmp_path: Path) -> None:
        kb = _create_test_kb(tmp_path)
        index_path = tmp_path / "index"

        indexer = RagIndexer(kb, index_path)
        count1 = indexer.build_index()
        count2 = indexer.build_index()

        assert count1 == count2
        collection = indexer.get_collection()
        assert collection.count() == count1

    def test_get_collection_before_build_raises(self, tmp_path: Path) -> None:
        kb = _create_test_kb(tmp_path)
        index_path = tmp_path / "index"

        indexer = RagIndexer(kb, index_path)
        with pytest.raises(RuntimeError, match="RAG index not found"):
            indexer.get_collection()

    def test_empty_knowledge_base(self, tmp_path: Path) -> None:
        kb = tmp_path / "empty_kb"
        kb.mkdir()
        index_path = tmp_path / "index"

        indexer = RagIndexer(kb, index_path)
        count = indexer.build_index()
        assert count == 0


class TestRagIndexerUnit:
    """Unit tests that don't require model downloads."""

    def test_nonexistent_kb_raises(self, tmp_path: Path) -> None:
        indexer = RagIndexer(tmp_path / "nonexistent", tmp_path / "index")
        with pytest.raises(FileNotFoundError):
            indexer.build_index()

    def test_index_path_property(self, tmp_path: Path) -> None:
        index_path = tmp_path / "my_index"
        indexer = RagIndexer(tmp_path, index_path)
        assert indexer.index_path == index_path
