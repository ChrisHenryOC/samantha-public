"""RAG indexer: chunks knowledge base documents and stores embeddings in ChromaDB.

Reads markdown files from the knowledge base directory, chunks them using
the section-aware chunker, embeds chunks with ``all-MiniLM-L6-v2``, and
stores them in a persistent ChromaDB collection.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

# Disable ChromaDB's PostHog telemetry before importing chromadb.
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

import chromadb  # noqa: E402
from chromadb.api.models.Collection import Collection

from src.rag.chunker import DocumentChunk, chunk_knowledge_base

logger = logging.getLogger(__name__)

_COLLECTION_NAME = "knowledge_base"
_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
_DEFAULT_INDEX_PATH = Path("data/rag_index")


class RagIndexer:
    """Builds and manages the RAG vector index.

    Chunks knowledge base documents, embeds them using sentence-transformers,
    and stores the results in a persistent ChromaDB collection.

    Args:
        knowledge_base_path: Path to the knowledge base directory.
        index_path: Path for persistent ChromaDB storage.
            Defaults to ``data/rag_index/``.
        min_chunk_chars: Minimum chunk size for section merging.
    """

    def __init__(
        self,
        knowledge_base_path: Path,
        index_path: Path = _DEFAULT_INDEX_PATH,
        *,
        min_chunk_chars: int = 100,
    ) -> None:
        self._kb_path = knowledge_base_path
        self._index_path = index_path
        self._min_chunk_chars = min_chunk_chars
        self._client: Any = None
        self._collection: Collection | None = None
        self._embedding_fn: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            self._index_path.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(self._index_path))
        return self._client

    def _get_embedding_function(self) -> Any:
        """Return the sentence-transformers embedding function, caching on first call."""
        if self._embedding_fn is None:
            from chromadb.utils.embedding_functions import (  # type: ignore[attr-defined]
                SentenceTransformerEmbeddingFunction,
            )

            self._embedding_fn = SentenceTransformerEmbeddingFunction(model_name=_EMBEDDING_MODEL)
        return self._embedding_fn

    def build_index(self) -> int:
        """Build the vector index from knowledge base documents.

        This is idempotent: it deletes the existing collection (if any)
        and recreates it from scratch.

        Returns:
            The number of chunks indexed.
        """
        chunks = chunk_knowledge_base(self._kb_path, min_chunk_chars=self._min_chunk_chars)
        if not chunks:
            logger.warning("No chunks found in knowledge base at %s", self._kb_path)
            return 0

        client = self._get_client()

        # Delete existing collection for idempotent rebuild.
        try:
            client.delete_collection(_COLLECTION_NAME)
            logger.info("Deleted existing collection '%s'", _COLLECTION_NAME)
        except ValueError as exc:
            if "does not exist" not in str(exc).lower():
                raise
            # Collection doesn't exist yet — nothing to delete.

        ef = self._get_embedding_function()
        collection = client.create_collection(
            name=_COLLECTION_NAME,
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )

        # Add chunks in a single batch.
        ids = [f"chunk-{i:04d}" for i in range(len(chunks))]
        documents = [c.text for c in chunks]
        metadatas = [_chunk_metadata(c) for c in chunks]

        collection.add(ids=ids, documents=documents, metadatas=metadatas)
        self._collection = collection

        logger.info(
            "Indexed %d chunks from %d documents",
            len(chunks),
            len({c.source_file for c in chunks}),
        )
        return len(chunks)

    def get_collection(self) -> Collection:
        """Return the ChromaDB collection, opening it if necessary.

        Raises:
            RuntimeError: If the index has not been built yet.
        """
        if self._collection is not None:
            return self._collection

        client = self._get_client()
        ef = self._get_embedding_function()
        try:
            self._collection = client.get_collection(
                name=_COLLECTION_NAME,
                embedding_function=ef,
            )
        except ValueError as exc:
            if "does not exist" not in str(exc).lower():
                raise
            raise RuntimeError(
                f"RAG index not found at {self._index_path}. Run build_rag_index.sh to build it."
            ) from None
        return self._collection

    @property
    def index_path(self) -> Path:
        return self._index_path


def _chunk_metadata(chunk: DocumentChunk) -> dict[str, str]:
    """Extract metadata dict from a DocumentChunk for ChromaDB storage."""
    return {
        "source_file": chunk.source_file,
        "section_title": chunk.section_title,
        "doc_type": chunk.doc_type,
    }
