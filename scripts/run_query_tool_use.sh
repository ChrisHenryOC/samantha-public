#!/usr/bin/env bash
# Run query evaluation with tool-use mode.
#
# Usage:
#   ./scripts/run_query_tool_use.sh                           # Run all models
#   ./scripts/run_query_tool_use.sh --dry-run                 # Validate config only
#   ./scripts/run_query_tool_use.sh --model "Qwen3 8B"        # Single local model
#   ./scripts/run_query_tool_use.sh --runs 1 --limit 5        # Smoke test
#   ./scripts/run_query_tool_use.sh --parallel                # Run cloud models concurrently
#   ./scripts/run_query_tool_use.sh --parallel --max-workers 2 # Limit concurrency
#   ./scripts/run_query_tool_use.sh --tier 1                  # Only tier 1 models
#   ./scripts/run_query_tool_use.sh --clean                   # Delete old results first
#
# Output: results/query_tool_use/

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

OUTPUT_DIR="results/query_tool_use"

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
echo "Query Tool-Use Evaluation"
echo "========================================"
echo "Output: $OUTPUT_DIR"
echo "Started: $(date)"
echo ""

FORCE_DASHBOARD=1 uv run python -m src.evaluation.query_runner \
    --output "$OUTPUT_DIR" \
    --mode tool_use \
    "${PASSTHROUGH_ARGS[@]}" 2>&1 | tee "$OUTPUT_DIR/run.log"

echo ""
echo "Finished: $(date)"
