#!/usr/bin/env bash
# Run routing evaluation with RAG context mode.
#
# Usage:
#   ./scripts/run_routing_rag.sh                           # Run all models
#   ./scripts/run_routing_rag.sh --dry-run                 # Validate config only
#   ./scripts/run_routing_rag.sh --model "Llama 3.1 8B"   # Single local model
#   ./scripts/run_routing_rag.sh --runs 1                  # Smoke test (1 run each)
#   ./scripts/run_routing_rag.sh --clean                   # Delete old results first
#
# Prerequisites:
#   ./scripts/build_rag_index.sh   # Build the RAG index first
#
# Output: results/routing_rag/

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

OUTPUT_DIR="results/routing_rag"

# Parse --clean flag (consumed here, not passed to Python)
CLEAN=false
PASSTHROUGH_ARGS=()
for arg in "$@"; do
    if [[ "$arg" == "--clean" ]]; then
        CLEAN=true
    else
        PASSTHROUGH_ARGS+=("$arg")
    fi
done

# Pre-flight check: RAG index must exist
if [[ ! -d "data/rag_index" ]]; then
    echo "ERROR: RAG index not found at data/rag_index/"
    echo "Run ./scripts/build_rag_index.sh first."
    exit 1
fi

if [[ "$CLEAN" == true ]]; then
    echo "Cleaning previous results in $OUTPUT_DIR ..."
    rm -rf "$OUTPUT_DIR"
fi

mkdir -p "$OUTPUT_DIR"

echo "========================================"
echo "Routing RAG Evaluation"
echo "========================================"
echo "Output: $OUTPUT_DIR"
echo "Started: $(date)"
echo ""

FORCE_DASHBOARD=1 uv run python -m src.evaluation.runner \
    --output "$OUTPUT_DIR" \
    --mode rag \
    "${PASSTHROUGH_ARGS[@]}" 2>&1 | tee "$OUTPUT_DIR/run.log"

echo ""
echo "Finished: $(date)"
