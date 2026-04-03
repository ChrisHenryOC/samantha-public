#!/usr/bin/env bash
# Phase 2: Variance measurement for top 4 models (GH Issue #216)
#
# Runs 5 iterations of 10 discriminating scenarios (35 steps) per model.
# Measures consistency — a model at 70% ±15% is worse than 60% ±2%.
#
# Results: results/phase2_variance/
# Estimated runtime: ~5 hours total
#
# Usage:
#   ./scripts/run_phase2_variance.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

OUTPUT="results/phase2_variance"
TIMEOUT=600
RUNS=5

SCENARIOS="SC-003,SC-013,SC-019,SC-024,SC-026,SC-028,SC-082,SC-102,SC-103,SC-108"

# Top 4 models from Phase 1, ordered fastest to slowest
MODELS=(
    "Mistral Small 3.2 24B Local"
    "Gemma 3 27B Local"
    "Qwen3 14B Local"
    "Llama 3.3 70B Local"
)

rm -rf "$OUTPUT"
mkdir -p "$OUTPUT"

TOTAL=${#MODELS[@]}
COMPLETED=0
FAILED_MODELS=()

echo "========================================"
echo "Phase 2: Variance Measurement"
echo "========================================"
echo "Models:    $TOTAL"
echo "Scenarios: 10 (35 steps each)"
echo "Runs:      $RUNS per model"
echo "Timeout:   ${TIMEOUT}s per model load"
echo "Output:    $OUTPUT"
echo "Started:   $(date)"
echo ""

for MODEL in "${MODELS[@]}"; do
    COMPLETED=$((COMPLETED + 1))
    echo "========================================"
    echo "[$COMPLETED/$TOTAL] $MODEL"
    echo "========================================"

    echo "Loading model (timeout ${TIMEOUT}s)..."
    if ! uv run python -m src.server.switch_model "$MODEL" --timeout "$TIMEOUT" 2>&1; then
        echo "FAILED — could not load $MODEL"
        FAILED_MODELS+=("$MODEL")
        echo ""
        continue
    fi

    echo "Running 10 scenarios x $RUNS runs..."
    if ! FORCE_DASHBOARD=1 uv run python -m src.evaluation.runner \
        --output "$OUTPUT" \
        --model "$MODEL" \
        --scenario-ids "$SCENARIOS" \
        --runs "$RUNS" 2>&1; then
        echo "FAILED — evaluation error for $MODEL"
        FAILED_MODELS+=("$MODEL")
        echo ""
        continue
    fi

    echo ""
done

echo ""
echo "========================================"
echo "Phase 2 Complete"
echo "========================================"
echo "Finished:  $(date)"
echo "Completed: $((TOTAL - ${#FAILED_MODELS[@]}))/$TOTAL models"
echo "Results:   $OUTPUT"

if [[ ${#FAILED_MODELS[@]} -gt 0 ]]; then
    echo ""
    echo "Failed models:"
    for m in "${FAILED_MODELS[@]}"; do
        echo "  - $m"
    done
    exit 1
fi
