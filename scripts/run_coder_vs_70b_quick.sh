#!/usr/bin/env bash
# Phase 1: Quick Head-to-Head — Coder 32B vs Llama 70B
#
# Runs the 33-scenario screening set (111 steps) with 1 run per model.
# Validates skills work broadly before the full overnight test.
#
# Estimated runtime: ~2.5 hours
#
# Results:
#   results/quick_coder_screening/
#   results/quick_70b_screening/
#
# Usage:
#   ./scripts/run_coder_vs_70b_quick.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Source shared scenario sets
source "$SCRIPT_DIR/scenario_sets.sh"

TIMEOUT=600
PROMPT_EXTRAS="skills,retry_clarification"

FAILED=()

echo "========================================"
echo "Phase 1: Quick Head-to-Head"
echo "========================================"
echo "Scenarios:     33 (111 steps)"
echo "Runs:          1 per model"
echo "Prompt extras: $PROMPT_EXTRAS"
echo "Est. time:     ~2.5 hours"
echo "Started:       $(date)"
echo ""

# --- Coder 32B ---
echo "========================================"
echo "[1/2] Qwen2.5 Coder 32B Local"
echo "========================================"
echo "Loading model (timeout ${TIMEOUT}s)..."
if ! uv run python -m src.server.switch_model "Qwen2.5 Coder 32B Local" --timeout "$TIMEOUT" 2>&1; then
    echo "FAILED — could not load Qwen2.5 Coder 32B Local"
    exit 1
fi

mkdir -p results/quick_coder_screening

echo "Running 33 scenarios x 1 run..."
if ! FORCE_DASHBOARD=1 uv run python -m src.evaluation.runner \
    --output results/quick_coder_screening \
    --model "Qwen2.5 Coder 32B Local" \
    --scenario-ids "$SCREENING_SET" \
    --local-runs 1 \
    --prompt-extras "$PROMPT_EXTRAS" 2>&1; then
    echo "FAILED — Coder 32B evaluation error"
    FAILED+=("coder-32b")
fi
echo ""

# --- Llama 70B ---
echo "========================================"
echo "[2/2] Llama 3.3 70B Local"
echo "========================================"
echo "Loading model (timeout ${TIMEOUT}s)..."
if ! uv run python -m src.server.switch_model "Llama 3.3 70B Local" --timeout "$TIMEOUT" 2>&1; then
    echo "FAILED — could not load Llama 3.3 70B Local"
    exit 1
fi

mkdir -p results/quick_70b_screening

echo "Running 33 scenarios x 1 run..."
if ! FORCE_DASHBOARD=1 uv run python -m src.evaluation.runner \
    --output results/quick_70b_screening \
    --model "Llama 3.3 70B Local" \
    --scenario-ids "$SCREENING_SET" \
    --local-runs 1 \
    --prompt-extras "$PROMPT_EXTRAS" 2>&1; then
    echo "FAILED — Llama 70B evaluation error"
    FAILED+=("llama-70b")
fi
echo ""

# --- Summary ---
echo "========================================"
echo "Phase 1 Complete"
echo "========================================"
echo "Finished: $(date)"
echo ""
echo "Results:"
echo "  Coder 32B: results/quick_coder_screening/"
echo "  Llama 70B: results/quick_70b_screening/"

if [[ ${#FAILED[@]} -gt 0 ]]; then
    echo ""
    echo "Failures:"
    for f in "${FAILED[@]}"; do
        echo "  - $f"
    done
    exit 1
fi
