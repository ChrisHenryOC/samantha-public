#!/usr/bin/env bash
# Build the RAG vector index from knowledge base documents.
#
# Usage:
#   ./scripts/build_rag_index.sh              # Build index
#   ./scripts/build_rag_index.sh --clean       # Delete and rebuild
#
# Output: data/rag_index/ (persistent ChromaDB collection)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

INDEX_DIR="data/rag_index"

# Parse --clean flag
CLEAN=false
for arg in "$@"; do
    if [[ "$arg" == "--clean" ]]; then
        CLEAN=true
    fi
done

if [[ "$CLEAN" == true ]]; then
    echo "Cleaning existing index at $INDEX_DIR ..."
    rm -rf "$INDEX_DIR"
fi

echo "========================================"
echo "Building RAG Index"
echo "========================================"
echo "Knowledge base: knowledge_base/"
echo "Index output:   $INDEX_DIR"
echo "Started: $(date)"
echo ""

uv run python -c "
from pathlib import Path
from src.rag.indexer import RagIndexer

kb_path = Path('knowledge_base')
index_path = Path('$INDEX_DIR')

indexer = RagIndexer(kb_path, index_path)
count = indexer.build_index()
print(f'Indexed {count} chunks successfully.')
"

echo ""
echo "Finished: $(date)"
