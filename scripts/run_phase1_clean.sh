#!/usr/bin/env bash
# Phase 1: Clean run of all 8 local models against 33 screening scenarios.
#
# This script:
#   1. Clears previous phase1 results
#   2. For each model: calls switch_model (600s timeout), then runs evaluation
#   3. Reports pass/fail per model; continues past failures
#
# 33 scenarios (111 steps) × 8 models = 888 total predictions
# Estimated runtime: ~6-8 hours depending on model size
#
# Results: results/phase1_clean/
#
# Usage:
#   ./scripts/run_phase1_clean.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

OUTPUT="results/phase1_clean"
TIMEOUT=600

SCENARIOS="SC-003,SC-005,SC-006,SC-009,SC-010,SC-011,SC-012,SC-013,SC-014,SC-016,SC-019,SC-020,SC-024,SC-026,SC-028,SC-038,SC-045,SC-081,SC-082,SC-087,SC-088,SC-100,SC-101,SC-102,SC-103,SC-106,SC-107,SC-108,SC-109,SC-110,SC-111,SC-112,SC-113"

# Get model names from config
MODELS=$(uv run python -c "
from src.server.model_manager import load_local_models
for m in load_local_models():
    print(m.name)
" 2>&1)

LOAD_EXIT=$?
if [[ $LOAD_EXIT -ne 0 ]] || [[ -z "$MODELS" ]]; then
    echo "ERROR: Failed to load model config:"
    echo "$MODELS"
    exit 1
fi

TOTAL=$(echo "$MODELS" | grep -c .)

# Clean previous results
rm -rf "$OUTPUT"
mkdir -p "$OUTPUT"

echo "========================================"
echo "Phase 1: Clean Model Selection Screen"
echo "========================================"
echo "Models:    $TOTAL"
echo "Scenarios: 33 (111 steps each)"
echo "Timeout:   ${TIMEOUT}s per model load"
echo "Output:    $OUTPUT"
echo "Started:   $(date)"
echo ""

COUNT=0
COMPLETED=0
FAILED_MODELS=()

while IFS= read -r MODEL; do
    COUNT=$((COUNT + 1))
    echo "========================================"
    echo "[$COUNT/$TOTAL] $MODEL"
    echo "========================================"

    # Load model
    echo "Loading model (timeout ${TIMEOUT}s)..."
    if ! uv run python -m src.server.switch_model "$MODEL" --timeout "$TIMEOUT" 2>&1; then
        echo "FAILED — could not load $MODEL"
        FAILED_MODELS+=("$MODEL")
        echo ""
        continue
    fi

    # Run evaluation
    echo "Running 33 scenarios..."
    if ! FORCE_DASHBOARD=1 uv run python -m src.evaluation.runner \
        --output "$OUTPUT" \
        --model "$MODEL" \
        --scenario-ids "$SCENARIOS" \
        --runs 1 2>&1; then
        echo "FAILED — evaluation error for $MODEL"
        FAILED_MODELS+=("$MODEL")
        echo ""
        continue
    fi

    COMPLETED=$((COMPLETED + 1))
    echo ""
done <<< "$MODELS"

# Summary
echo ""
echo "========================================"
echo "Phase 1 Complete"
echo "========================================"
echo "Finished:  $(date)"
echo "Completed: $COMPLETED/$TOTAL models"
echo "Results:   $OUTPUT"

if [[ ${#FAILED_MODELS[@]} -gt 0 ]]; then
    echo ""
    echo "Failed models:"
    for m in "${FAILED_MODELS[@]}"; do
        echo "  - $m"
    done
    exit 1
fi
