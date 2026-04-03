"""RAG retriever: query-time retrieval from the ChromaDB vector index.

Provides semantic search over the knowledge base chunks, with helpers
for constructing queries from routing context and natural language queries.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

from chromadb.api.models.Collection import Collection

from src.rag.indexer import _DEFAULT_INDEX_PATH, RagIndexer


@dataclass(frozen=True)
class RetrievalResult:
    """A single retrieved chunk with similarity score.

    Attributes:
        text: The chunk text.
        source_file: Relative path to the source file.
        section_title: The section title from the chunk.
        doc_type: Document type (``"sop"``, ``"rule"``, ``"reference"``).
        similarity_score: Rescaled cosine distance (0–1, higher = more relevant).
            Computed as ``1 - (cosine_distance / 2)``, so values near 1 indicate
            high similarity. Not raw cosine similarity.
    """

    text: str
    source_file: str
    section_title: str
    doc_type: str
    similarity_score: float

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise TypeError(f"text must be str, got {type(self.text).__name__}")
        if not self.text.strip():
            raise ValueError("text must not be empty")
        if not isinstance(self.source_file, str):
            raise TypeError(f"source_file must be str, got {type(self.source_file).__name__}")
        if not isinstance(self.section_title, str):
            raise TypeError(f"section_title must be str, got {type(self.section_title).__name__}")
        if not isinstance(self.doc_type, str):
            raise TypeError(f"doc_type must be str, got {type(self.doc_type).__name__}")
        _VALID_DOC_TYPES = {"sop", "rule", "reference"}
        if self.doc_type not in _VALID_DOC_TYPES:
            raise ValueError(
                f"doc_type must be one of {sorted(_VALID_DOC_TYPES)}, got '{self.doc_type}'"
            )
        if not isinstance(self.similarity_score, (int, float)):
            raise TypeError(
                f"similarity_score must be float, got {type(self.similarity_score).__name__}"
            )


@dataclass(frozen=True)
class RetrievalInfo:
    """Metadata about a retrieval operation for audit/analysis.

    Attributes:
        query_text: The query string sent to the vector store.
        chunks_retrieved: Number of chunks returned (after threshold filtering).
        candidates_before_filter: Number of chunks returned by the vector store
            before similarity threshold filtering. Lets the audit trail
            distinguish "threshold too strict" from "index empty".
        scores: Similarity scores for each retrieved chunk.
        top_sources: Source files of retrieved chunks.
    """

    query_text: str
    chunks_retrieved: int
    candidates_before_filter: int
    scores: tuple[float, ...]
    top_sources: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.query_text, str):
            raise TypeError(f"query_text must be str, got {type(self.query_text).__name__}")
        if not isinstance(self.chunks_retrieved, int):
            raise TypeError(
                f"chunks_retrieved must be int, got {type(self.chunks_retrieved).__name__}"
            )
        if self.chunks_retrieved < 0:
            raise ValueError(f"chunks_retrieved must be >= 0, got {self.chunks_retrieved}")
        if not isinstance(self.candidates_before_filter, int):
            raise TypeError(
                f"candidates_before_filter must be int, "
                f"got {type(self.candidates_before_filter).__name__}"
            )
        if self.candidates_before_filter < 0:
            raise ValueError(
                f"candidates_before_filter must be >= 0, got {self.candidates_before_filter}"
            )
        if self.candidates_before_filter < self.chunks_retrieved:
            raise ValueError(
                f"candidates_before_filter ({self.candidates_before_filter}) "
                f"must be >= chunks_retrieved ({self.chunks_retrieved})"
            )
        if not isinstance(self.scores, tuple):
            raise TypeError(f"scores must be tuple, got {type(self.scores).__name__}")
        for i, score in enumerate(self.scores):
            if not isinstance(score, (int, float)):
                raise TypeError(f"scores[{i}] must be float, got {type(score).__name__}")
            if not (0.0 <= score <= 1.0):
                raise ValueError(f"scores[{i}] must be in [0, 1], got {score}")
        if not isinstance(self.top_sources, tuple):
            raise TypeError(f"top_sources must be tuple, got {type(self.top_sources).__name__}")
        for i, src in enumerate(self.top_sources):
            if not isinstance(src, str):
                raise TypeError(f"top_sources[{i}] must be str, got {type(src).__name__}")
        if len(self.scores) != self.chunks_retrieved:
            raise ValueError(
                f"len(scores) ({len(self.scores)}) != chunks_retrieved ({self.chunks_retrieved})"
            )
        if len(self.top_sources) != self.chunks_retrieved:
            raise ValueError(
                f"len(top_sources) ({len(self.top_sources)}) != "
                f"chunks_retrieved ({self.chunks_retrieved})"
            )


class RagRetriever:
    """Retrieves relevant knowledge base chunks for a query.

    Wraps a ChromaDB collection and provides semantic search with query
    construction helpers for routing and query evaluation.

    Args:
        index_path: Path to the persistent ChromaDB index.
            Defaults to ``data/rag_index/``.
        knowledge_base_path: Path to the knowledge base directory.
            Required for building the index if it doesn't exist.
        top_k: Default number of chunks to retrieve. Defaults to 10.
        similarity_threshold: Minimum similarity score to include a chunk.
            Chunks below this threshold are filtered out. Defaults to 0.3.
    """

    def __init__(
        self,
        index_path: Path = _DEFAULT_INDEX_PATH,
        *,
        knowledge_base_path: Path | None = None,
        top_k: int = 10,
        similarity_threshold: float = 0.3,
        eager_validate: bool = True,
    ) -> None:
        self._index_path = index_path
        self._kb_path = knowledge_base_path
        self._top_k = top_k
        self._similarity_threshold = similarity_threshold
        self._collection: Collection | None = None
        self._cache: dict[tuple[str, int], tuple[list[RetrievalResult], int]] = {}
        self._cache_lock = threading.Lock()
        if eager_validate:
            self._get_collection()

    def _get_collection(self) -> Collection:
        if self._collection is None:
            kb_path = self._kb_path or Path("knowledge_base")
            indexer = RagIndexer(kb_path, self._index_path)
            self._collection = indexer.get_collection()
        return self._collection

    def retrieve(
        self,
        query_text: str,
        top_k: int | None = None,
    ) -> tuple[list[RetrievalResult], int]:
        """Retrieve the most relevant chunks for a query.

        Args:
            query_text: The search query string.
            top_k: Number of results to return. Defaults to the instance-level
                ``top_k`` setting.

        Returns:
            Tuple of (results, candidates_before_filter) where results is a
            list of ``RetrievalResult`` instances sorted by relevance and
            candidates_before_filter is the count returned by the vector
            store before similarity threshold filtering.
        """
        k = top_k if top_k is not None else self._top_k

        cache_key = (query_text, k)
        with self._cache_lock:
            if cache_key in self._cache:
                return self._cache[cache_key]

        collection = self._get_collection()

        results = collection.query(
            query_texts=[query_text],
            n_results=k,
            include=["documents", "metadatas", "distances"],  # type: ignore[list-item]
        )

        # ChromaDB returns nested lists (one per query).
        documents: list[str] = results["documents"][0] if results["documents"] else []
        metadatas = results["metadatas"][0] if results["metadatas"] else []
        distances: list[float] = results["distances"][0] if results["distances"] else []

        candidates_before_filter = len(documents)
        retrieved: list[RetrievalResult] = []
        for doc, meta, dist in zip(documents, metadatas, distances, strict=True):
            # ChromaDB cosine distance: 0 = identical, 2 = opposite.
            # Convert to similarity: 1 - (distance / 2) maps [0,2] → [1,0].
            similarity = 1.0 - (float(dist) / 2.0)

            if similarity < self._similarity_threshold:
                continue

            retrieved.append(
                RetrievalResult(
                    text=doc,
                    source_file=str(meta.get("source_file", "")),
                    section_title=str(meta.get("section_title", "")),
                    doc_type=str(meta.get("doc_type", "reference")) or "reference",
                    similarity_score=round(similarity, 4),
                )
            )

        with self._cache_lock:
            self._cache[cache_key] = (retrieved, candidates_before_filter)
        return retrieved, candidates_before_filter

    @staticmethod
    def _make_retrieval_info(
        query_text: str,
        results: list[RetrievalResult],
        candidates_before_filter: int,
    ) -> RetrievalInfo:
        """Build a ``RetrievalInfo`` from a completed retrieve call."""
        return RetrievalInfo(
            query_text=query_text,
            chunks_retrieved=len(results),
            candidates_before_filter=candidates_before_filter,
            scores=tuple(r.similarity_score for r in results),
            top_sources=tuple(r.source_file for r in results),
        )

    def retrieve_for_routing(
        self,
        current_state: str,
        event_type: str,
        event_data: dict[str, object],
    ) -> tuple[list[RetrievalResult], RetrievalInfo]:
        """Retrieve context relevant to a routing decision.

        Builds a query string from the routing context (current state,
        event type, and key event data fields) and retrieves relevant
        SOP sections and rules.

        Returns:
            Tuple of (results, retrieval_info) for audit trail.
        """
        # Build a rule-biased query from the routing context.
        # Uses rule-specific terms to surface rule definitions and validation
        # checks rather than process overviews (see GH-161 root cause analysis).
        parts = [
            f"workflow rules for {current_state}",
            f"rule triggers for event {event_type}",
            "validation checks routing decision",
        ]

        # Include key event data fields that help retrieval.
        for key in ("outcome", "reason", "result", "qc_result", "diagnosis"):
            if key in event_data:
                parts.append(f"{key}: {event_data[key]}")

        # Include test names if present.
        if "ordered_tests" in event_data:
            tests = event_data["ordered_tests"]
            if isinstance(tests, list):
                parts.append(f"tests: {', '.join(str(t) for t in tests)}")

        query_text = "; ".join(parts)
        results, candidates = self.retrieve(query_text)
        return results, self._make_retrieval_info(query_text, results, candidates)

    def retrieve_for_query(
        self,
        natural_language_query: str,
    ) -> tuple[list[RetrievalResult], RetrievalInfo]:
        """Retrieve context relevant to a natural language query.

        Passes the query directly to the vector store since it's already
        in natural language form.

        Returns:
            Tuple of (results, retrieval_info) for audit trail.
        """
        results, candidates = self.retrieve(natural_language_query)
        return results, self._make_retrieval_info(natural_language_query, results, candidates)
