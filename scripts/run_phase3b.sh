#!/usr/bin/env bash
# Phase 3b: Validation run for best prompt variant (GH Issue #219)
#
# Runs the Phase 3a winner (experiment 4: +few_shot) on the full Phase 2
# 10-scenario set with 5 runs. Qwen3 14B dropped due to high variance
# (±14.3%) in Phase 3a — Llama 3.3 70B only (85.7% ±0.0% in Phase 3a).
#
# Results: results/phase3b_validation/
# Estimated runtime: ~1.25 hours
#
# Usage:
#   ./scripts/run_phase3b.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

OUTPUT="results/phase3b_validation"
TIMEOUT=600
RUNS=5

# Phase 3a winner: experiment 4 (+few_shot = all three extras)
PROMPT_EXTRAS="state_sequence,retry_clarification,few_shot"

# Same 10 scenarios as Phase 2
SCENARIOS="SC-003,SC-013,SC-019,SC-024,SC-026,SC-028,SC-082,SC-102,SC-103,SC-108"

# Qwen3 14B dropped: ±14.3% variance in Phase 3a even with best prompt
MODELS=(
    "Llama 3.3 70B Local"
)

rm -rf "$OUTPUT"
mkdir -p "$OUTPUT"

TOTAL=${#MODELS[@]}
COMPLETED=0
FAILED_MODELS=()

echo "========================================"
echo "Phase 3b: Validation"
echo "========================================"
echo "Model:        Llama 3.3 70B Local"
echo "Scenarios:    10 (35 steps)"
echo "Runs:         $RUNS per model"
echo "Prompt extras: $PROMPT_EXTRAS"
echo "Timeout:      ${TIMEOUT}s per model load"
echo "Output:       $OUTPUT"
echo "Started:      $(date)"
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

    echo "Running 10 scenarios x $RUNS runs (extras: $PROMPT_EXTRAS)..."
    if ! FORCE_DASHBOARD=1 uv run python -m src.evaluation.runner \
        --output "$OUTPUT" \
        --model "$MODEL" \
        --scenario-ids "$SCENARIOS" \
        --runs "$RUNS" \
        --prompt-extras "$PROMPT_EXTRAS" 2>&1; then
        echo "FAILED — evaluation error for $MODEL"
        FAILED_MODELS+=("$MODEL")
        echo ""
        continue
    fi

    echo ""
done

echo ""
echo "========================================"
echo "Phase 3b Complete"
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
