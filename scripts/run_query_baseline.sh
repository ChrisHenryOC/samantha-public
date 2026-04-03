#!/usr/bin/env bash
# Run query baseline evaluation.
#
# Usage:
#   ./scripts/run_query_baseline.sh                           # Run all models
#   ./scripts/run_query_baseline.sh --dry-run                 # Validate config only
#   ./scripts/run_query_baseline.sh --model "Llama 3.1 8B"   # Single local model
#   ./scripts/run_query_baseline.sh --runs 1                  # Smoke test (1 run each)
#   ./scripts/run_query_baseline.sh --clean                   # Delete old results first
#
# Output: results/query_baseline/
#   - Per-model run JSON files
#   - query_summary.json with aggregated metrics
#   - evaluation.db (SQLite) with all query decisions

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

OUTPUT_DIR="results/query_baseline"

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

if [[ "$CLEAN" == true ]]; then
    echo "Cleaning previous results in $OUTPUT_DIR ..."
    rm -rf "$OUTPUT_DIR"
fi

mkdir -p "$OUTPUT_DIR"

echo "========================================"
echo "Query Baseline Evaluation"
echo "========================================"
echo "Output: $OUTPUT_DIR"
echo "Started: $(date)"
echo ""

# Pass through all CLI args (--dry-run, --model, --runs, etc.)
FORCE_DASHBOARD=1 uv run python -m src.evaluation.query_runner \
    --output "$OUTPUT_DIR" \
    "${PASSTHROUGH_ARGS[@]}" 2>&1 | tee "$OUTPUT_DIR/run.log"

echo ""
echo "Finished: $(date)"
