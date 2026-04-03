"""Section-aware markdown document chunker for RAG pipeline.

Splits knowledge base documents (SOPs, rules, workflow states) into chunks
at H2 (``##``) section boundaries. Each chunk retains its section header
and metadata for downstream retrieval.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Regex matching a markdown H2 header line (## Title).
_H2_PATTERN = re.compile(r"^##\s+(.+)$", re.MULTILINE)

# Document type inference from file path.
_DOC_TYPE_MAP: dict[str, str] = {
    "sops": "sop",
    "rules": "rule",
}


@dataclass(frozen=True)
class DocumentChunk:
    """A single chunk from a knowledge base document.

    Attributes:
        text: The full text of the chunk including the section header.
        source_file: Relative path to the source file (e.g. ``sops/accessioning.md``).
        section_title: The H2 section title (e.g. ``"3. Validation Checks"``).
        doc_type: Document type: ``"sop"``, ``"rule"``, or ``"reference"``.
        char_count: Number of characters in ``text``.
    """

    text: str
    source_file: str
    section_title: str
    doc_type: str
    char_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise TypeError(f"text must be str, got {type(self.text).__name__}")
        if not self.text.strip():
            raise ValueError("text must not be empty or whitespace-only")
        if not isinstance(self.source_file, str):
            raise TypeError(f"source_file must be str, got {type(self.source_file).__name__}")
        if not self.source_file:
            raise ValueError("source_file must not be empty")
        if not isinstance(self.section_title, str):
            raise TypeError(f"section_title must be str, got {type(self.section_title).__name__}")
        if not isinstance(self.doc_type, str):
            raise TypeError(f"doc_type must be str, got {type(self.doc_type).__name__}")
        if self.doc_type not in ("sop", "rule", "reference"):
            raise ValueError(
                f"doc_type must be 'sop', 'rule', or 'reference', got {self.doc_type!r}"
            )
        if not isinstance(self.char_count, int):
            raise TypeError(f"char_count must be int, got {type(self.char_count).__name__}")
        if self.char_count < 0:
            raise ValueError(f"char_count must be non-negative, got {self.char_count}")


def _infer_doc_type(source_file: str) -> str:
    """Infer document type from source file path.

    Files under ``sops/`` → ``"sop"``, under ``rules/`` → ``"rule"``,
    everything else → ``"reference"``.
    """
    parts = Path(source_file).parts
    for part in parts:
        if part in _DOC_TYPE_MAP:
            return _DOC_TYPE_MAP[part]
    return "reference"


def _split_sections(content: str) -> list[tuple[str, str]]:
    """Split markdown content into (section_title, section_text) pairs at H2 boundaries.

    Content before the first H2 header is grouped under a ``"preamble"`` title.
    Each section includes its ``## Title`` line.
    """
    matches = list(_H2_PATTERN.finditer(content))

    if not matches:
        # No H2 headers — entire document is one chunk.
        return [("preamble", content)]

    sections: list[tuple[str, str]] = []

    # Content before the first H2.
    preamble = content[: matches[0].start()].strip()
    if preamble:
        sections.append(("preamble", preamble))

    # Each H2 section spans from this match to the next (or end of content).
    for i, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        text = content[start:end].strip()
        if text:
            sections.append((title, text))

    return sections


def chunk_document(
    content: str,
    source_file: str,
    *,
    min_chunk_chars: int = 100,
) -> list[DocumentChunk]:
    """Chunk a markdown document into sections at H2 boundaries.

    Args:
        content: The full markdown text of the document.
        source_file: Relative path to the source file within the knowledge base
            (e.g. ``"sops/accessioning.md"``).
        min_chunk_chars: Minimum character count for a chunk. Sections smaller
            than this are merged with the previous chunk. Defaults to 100.

    Returns:
        List of ``DocumentChunk`` instances, one per section (after merging).

    Raises:
        ValueError: If content is empty or source_file is empty.
    """
    if not content.strip():
        raise ValueError("content must not be empty")
    if not source_file:
        raise ValueError("source_file must not be empty")

    doc_type = _infer_doc_type(source_file)
    sections = _split_sections(content)

    if not sections:
        return []

    # Merge small sections with the previous chunk.
    merged: list[tuple[str, str]] = []
    for title, text in sections:
        if merged and len(text) < min_chunk_chars:
            # Append to previous chunk's text, keep previous title.
            prev_title, prev_text = merged[-1]
            merged[-1] = (prev_title, prev_text + "\n\n" + text)
        else:
            merged.append((title, text))

    return [
        DocumentChunk(
            text=text,
            source_file=source_file,
            section_title=title,
            doc_type=doc_type,
            char_count=len(text),
        )
        for title, text in merged
    ]


def chunk_knowledge_base(
    knowledge_base_path: Path,
    *,
    min_chunk_chars: int = 100,
) -> list[DocumentChunk]:
    """Chunk all markdown files in the knowledge base directory.

    Walks the knowledge base directory, reads each ``.md`` file, and chunks
    it using ``chunk_document()``.

    Args:
        knowledge_base_path: Path to the knowledge base root directory.
        min_chunk_chars: Minimum chunk size for section merging.

    Returns:
        All chunks from all documents, sorted by source file then section order.

    Raises:
        FileNotFoundError: If knowledge_base_path does not exist.
    """
    if not knowledge_base_path.exists():
        raise FileNotFoundError(f"Knowledge base path does not exist: {knowledge_base_path}")

    all_chunks: list[DocumentChunk] = []
    for md_file in sorted(knowledge_base_path.rglob("*.md")):
        content = md_file.read_text(encoding="utf-8")
        relative = str(md_file.relative_to(knowledge_base_path))
        chunks = chunk_document(content, relative, min_chunk_chars=min_chunk_chars)
        all_chunks.extend(chunks)

    return all_chunks
