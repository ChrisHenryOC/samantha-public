#!/usr/bin/env bash
# Run routing baseline evaluation.
#
# Usage:
#   ./scripts/run_routing_baseline.sh                           # Run all models
#   ./scripts/run_routing_baseline.sh --dry-run                 # Validate config only
#   ./scripts/run_routing_baseline.sh --tier 1                  # Tier 1 only (8B-14B)
#   ./scripts/run_routing_baseline.sh --tier 1 2                # Tiers 1 and 2
#   ./scripts/run_routing_baseline.sh --tier ceiling             # Ceiling benchmarks only
#   ./scripts/run_routing_baseline.sh --tier all                 # All tiers
#   ./scripts/run_routing_baseline.sh --runs 1                  # Smoke test (1 run each)
#   ./scripts/run_routing_baseline.sh --clean                   # Delete old results first
#   ./scripts/run_routing_baseline.sh --parallel                # Cloud models concurrent
#   ./scripts/run_routing_baseline.sh --parallel --max-workers 3 # Limit concurrency
#   ./scripts/run_routing_baseline.sh --model "Qwen3 8B"        # Single model
#
# OpenRouter API key required:
#   export OPENROUTER_API_KEY=$(cat notes/openrouter-api-key.txt)
#
# Typical workflow:
#   1. ./scripts/run_routing_baseline.sh --tier 1 --parallel     # Quick sanity check
#   2. ./scripts/run_routing_baseline.sh --tier 2 --parallel     # Add mid-range data
#   3. ./scripts/run_routing_baseline.sh --tier 3 --parallel     # Add MoE data
#   4. ./scripts/run_routing_baseline.sh --tier ceiling --parallel # Add ceiling benchmarks
#
# Output: results/routing_baseline/
#   - Per-model run JSON files
#   - summary.json with aggregated metrics
#   - evaluation.db (SQLite) with all decisions

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

OUTPUT_DIR="results/routing_baseline"

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
echo "Routing Baseline Evaluation"
echo "========================================"
echo "Output: $OUTPUT_DIR"
echo "Started: $(date)"
echo ""

# Pass through all CLI args (--dry-run, --model, --category, --runs, --tier, etc.)
FORCE_DASHBOARD=1 uv run python -m src.evaluation.runner \
    --output "$OUTPUT_DIR" \
    "${PASSTHROUGH_ARGS[@]}" 2>&1 | tee "$OUTPUT_DIR/run.log"

echo ""
echo "Finished: $(date)"
