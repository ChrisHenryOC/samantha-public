#!/usr/bin/env bash
# Phase 1 (continued): Run remaining 5 models that didn't complete.
#
# Results go to results/model_selection_phase1/ (same dir as prior runs).
# Estimated runtime: ~3.5 hours

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

OUTPUT="results/model_selection_phase1"
mkdir -p "$OUTPUT"

DISC_SCENARIOS="SC-003,SC-005,SC-006,SC-009,SC-010,SC-011,SC-012,SC-013,SC-014,SC-016,SC-019,SC-020,SC-024,SC-026,SC-028,SC-038,SC-045,SC-081,SC-082,SC-087,SC-088,SC-100,SC-101,SC-102,SC-103"

HALL_SCENARIOS="SC-106,SC-107,SC-108,SC-109,SC-110,SC-111,SC-112,SC-113"

ALL_SCENARIOS="${DISC_SCENARIOS},${HALL_SCENARIOS}"

TOTAL_MODELS=4
COMPLETED=0
FAILED_MODELS=()

echo "========================================"
echo "Phase 1 (continued): Remaining 5 models"
echo "========================================"
echo "Output: $OUTPUT"
echo "Started: $(date)"
echo ""

run_model() {
    local MODEL="$1"
    local SCENARIOS="$2"
    local LABEL="$3"

    echo "----------------------------------------"
    echo "Running: $MODEL ($LABEL)"
    echo "----------------------------------------"
    if ! uv run python -m src.server.switch_model "$MODEL"; then
        echo "FAILED to switch to $MODEL — skipping"
        FAILED_MODELS+=("$MODEL")
        echo ""
        return
    fi
    if ! FORCE_DASHBOARD=1 uv run python -m src.evaluation.runner \
        --output "$OUTPUT" \
        --model "$MODEL" \
        --scenario-ids "$SCENARIOS" \
        --runs 1; then
        echo "FAILED evaluation for $MODEL"
        FAILED_MODELS+=("$MODEL")
    else
        COMPLETED=$((COMPLETED + 1))
    fi
    echo ""
}

# --- Models with no prior results: run all 33 scenarios ---

for MODEL in "Qwen3 30B-A3B Local" "Llama 3.3 70B Local"; do
    run_model "$MODEL" "$ALL_SCENARIOS" "all 33 scenarios"
done

# --- Models with OpenRouter results: hallucination only ---

for MODEL in "Mistral Small 3.2 24B Local" "Gemma 3 27B Local"; do
    run_model "$MODEL" "$HALL_SCENARIOS" "8 hallucination scenarios"
done

echo "========================================"
echo "Phase 1 (continued) complete: $(date)"
echo "Results in $OUTPUT"
echo "Completed: $COMPLETED/$TOTAL_MODELS"
if [[ ${#FAILED_MODELS[@]} -gt 0 ]]; then
    echo "Failed: ${FAILED_MODELS[*]}"
    exit 1
fi
echo "========================================"
