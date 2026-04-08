#!/usr/bin/env bash
# Generate RAG vs full-context comparison report.
#
# Usage:
#   ./scripts/generate_rag_comparison.sh
#   ./scripts/generate_rag_comparison.sh --baseline results/routing_baseline --rag results/routing_rag
#
# Prerequisites:
#   - Phase 4 baseline results in results/routing_baseline/
#   - Phase 5 RAG results in results/routing_rag/
#
# Output: results/rag_comparison/

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

BASELINE_DIR="results/routing_baseline"
RAG_DIR="results/routing_rag"
OUTPUT_DIR="results/rag_comparison"

# Parse named arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --baseline)
            BASELINE_DIR="$2"
            shift 2
            ;;
        --rag)
            RAG_DIR="$2"
            shift 2
            ;;
        *)
            # Positional fallback: first is baseline, second is rag
            if [[ "$BASELINE_DIR" == "results/routing_baseline" ]]; then
                BASELINE_DIR="$1"
            else
                RAG_DIR="$1"
            fi
            shift
            ;;
    esac
done

echo "========================================"
echo "RAG Comparison Report"
echo "========================================"
echo "Baseline: $BASELINE_DIR"
echo "RAG:      $RAG_DIR"
echo "Output:   $OUTPUT_DIR"
echo ""

mkdir -p "$OUTPUT_DIR"

uv run python -m src.evaluation.rag_comparison \
    --baseline "$BASELINE_DIR" \
    --rag "$RAG_DIR" \
    --output "$OUTPUT_DIR"
