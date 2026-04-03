#!/usr/bin/env bash
# Phase 1: Rerun Llama 3.3 70B only (after harness bug fix).
#
# Writes to results/phase1_clean/ alongside existing model results.
# The 70B model's previous partial results will be overwritten.
#
# Estimated runtime: ~2 hours (111 steps × ~60s/step)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

OUTPUT="results/phase1_clean"
TIMEOUT=600
MODEL="Llama 3.3 70B Local"

SCENARIOS="SC-003,SC-005,SC-006,SC-009,SC-010,SC-011,SC-012,SC-013,SC-014,SC-016,SC-019,SC-020,SC-024,SC-026,SC-028,SC-038,SC-045,SC-081,SC-082,SC-087,SC-088,SC-100,SC-101,SC-102,SC-103,SC-106,SC-107,SC-108,SC-109,SC-110,SC-111,SC-112,SC-113"

echo "========================================"
echo "Phase 1: Llama 3.3 70B Rerun"
echo "========================================"
echo "Output:  $OUTPUT"
echo "Timeout: ${TIMEOUT}s"
echo "Started: $(date)"
echo ""

echo "Loading model (timeout ${TIMEOUT}s)..."
if ! uv run python -m src.server.switch_model "$MODEL" --timeout "$TIMEOUT" 2>&1; then
    echo "FAILED — could not load $MODEL"
    exit 1
fi

echo "Running 33 scenarios..."
if ! FORCE_DASHBOARD=1 uv run python -m src.evaluation.runner \
    --output "$OUTPUT" \
    --model "$MODEL" \
    --scenario-ids "$SCENARIOS" \
    --runs 1 2>&1; then
    echo "FAILED — evaluation error"
    exit 1
fi

echo ""
echo "========================================"
echo "Complete: $(date)"
echo "Results: $OUTPUT"
echo "========================================"
