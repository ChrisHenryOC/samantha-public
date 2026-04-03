#!/usr/bin/env bash
# Phase 2: Full Head-to-Head — Coder 32B vs Llama 70B + cloud models (overnight)
#
# Part A: Screening set (33 scenarios, 111 steps) x 3 runs per local model
# Part B: Accumulated state (10 scenarios, 140 steps) x 1 run per local model
# Part C: Cloud models (Qwen3 32B, Gemma 3 27B via OpenRouter) x 1 run screening + accstate
#
# Estimated runtime: ~8 hours (cloud models add ~15 min)
#
# Results:
#   results/h2h_coder_screening/
#   results/h2h_70b_screening/
#   results/h2h_coder_accstate/
#   results/h2h_70b_accstate/
#   results/h2h_qwen3_32b_screening/
#   results/h2h_gemma_27b_screening/
#
# Usage:
#   ./scripts/run_coder_vs_70b.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Source shared scenario sets
source "$SCRIPT_DIR/scenario_sets.sh"

TIMEOUT=600
PROMPT_EXTRAS="skills,retry_clarification"
LOG_FILE="results/h2h_run.log"

# --- Pre-flight checks ---

# Verify OpenRouter API key is available (needed for Part C cloud models)
KEY_FILE="$PROJECT_ROOT/notes/openrouter-api-key.txt"
if [[ ! -f "$KEY_FILE" ]] && [[ -z "${OPENROUTER_API_KEY:-}" ]]; then
    echo "ERROR: OpenRouter API key not found."
    echo "Place it in notes/openrouter-api-key.txt or set OPENROUTER_API_KEY."
    echo "The cloud model segments (Part C) require this key."
    exit 1
fi

# Set up persistent logging (tee to file + terminal)
mkdir -p results
exec > >(tee "$LOG_FILE") 2>&1

FAILED=()
SEGMENT=0
TOTAL_SEGMENTS=8

echo "========================================"
echo "Phase 2: Full Head-to-Head (Overnight)"
echo "========================================"
echo "Local models grouped to minimize model loads (2 loads instead of 4)"
echo "Coder 32B: screening (3 runs) + accumulated state (1 run)"
echo "Llama 70B: screening (3 runs) + accumulated state (1 run)"
echo "Cloud: Qwen3 32B + Gemma 3 27B — screening + accumulated state (1 run each)"
echo "Prompt extras: $PROMPT_EXTRAS"
echo "Log file:      $LOG_FILE"
echo "Est. time:     ~8 hours"
echo "Started:       $(date)"
echo ""

# --- Coder 32B (all segments) ---

SEGMENT=$((SEGMENT + 1))
echo "========================================"
echo "[$SEGMENT/$TOTAL_SEGMENTS] Coder 32B — Screening (3 runs)"
echo "========================================"
echo "Loading model (timeout ${TIMEOUT}s)..."
if ! uv run python -m src.server.switch_model "Qwen2.5 Coder 32B Local" --timeout "$TIMEOUT" 2>&1; then
    echo "FAILED — could not load Qwen2.5 Coder 32B Local"
    exit 1
fi

mkdir -p results/h2h_coder_screening

if ! FORCE_DASHBOARD=1 uv run python -m src.evaluation.runner \
    --output results/h2h_coder_screening \
    --model "Qwen2.5 Coder 32B Local" \
    --scenario-ids "$SCREENING_SET" \
    --local-runs 3 \
    --prompt-extras "$PROMPT_EXTRAS" 2>&1; then
    echo "FAILED — Coder 32B screening"
    FAILED+=("coder-screening")
fi
echo ""

SEGMENT=$((SEGMENT + 1))
echo "========================================"
echo "[$SEGMENT/$TOTAL_SEGMENTS] Coder 32B — Accumulated State (1 run)"
echo "========================================"

mkdir -p results/h2h_coder_accstate

if ! FORCE_DASHBOARD=1 uv run python -m src.evaluation.runner \
    --output results/h2h_coder_accstate \
    --model "Qwen2.5 Coder 32B Local" \
    --scenario-ids "$ACCSTATE_SET" \
    --local-runs 1 \
    --prompt-extras "$PROMPT_EXTRAS" 2>&1; then
    echo "FAILED — Coder 32B accumulated state"
    FAILED+=("coder-accstate")
fi
echo ""

# --- Llama 70B (all segments) ---

SEGMENT=$((SEGMENT + 1))
echo "========================================"
echo "[$SEGMENT/$TOTAL_SEGMENTS] Llama 70B — Screening (3 runs)"
echo "========================================"
echo "Loading model (timeout ${TIMEOUT}s)..."
if ! uv run python -m src.server.switch_model "Llama 3.3 70B Local" --timeout "$TIMEOUT" 2>&1; then
    echo "FAILED — could not load Llama 3.3 70B Local"
    exit 1
fi

mkdir -p results/h2h_70b_screening

if ! FORCE_DASHBOARD=1 uv run python -m src.evaluation.runner \
    --output results/h2h_70b_screening \
    --model "Llama 3.3 70B Local" \
    --scenario-ids "$SCREENING_SET" \
    --local-runs 3 \
    --prompt-extras "$PROMPT_EXTRAS" 2>&1; then
    echo "FAILED — Llama 70B screening"
    FAILED+=("70b-screening")
fi
echo ""

SEGMENT=$((SEGMENT + 1))
echo "========================================"
echo "[$SEGMENT/$TOTAL_SEGMENTS] Llama 70B — Accumulated State (1 run)"
echo "========================================"

mkdir -p results/h2h_70b_accstate

if ! FORCE_DASHBOARD=1 uv run python -m src.evaluation.runner \
    --output results/h2h_70b_accstate \
    --model "Llama 3.3 70B Local" \
    --scenario-ids "$ACCSTATE_SET" \
    --local-runs 1 \
    --prompt-extras "$PROMPT_EXTRAS" 2>&1; then
    echo "FAILED — Llama 70B accumulated state"
    FAILED+=("70b-accstate")
fi
echo ""

# --- Part C: Cloud Models (OpenRouter) ---

# Qwen3 32B — Screening
SEGMENT=$((SEGMENT + 1))
echo "========================================"
echo "[$SEGMENT/$TOTAL_SEGMENTS] Qwen3 32B (OpenRouter) — Screening (1 run)"
echo "========================================"

mkdir -p results/h2h_qwen3_32b_screening

if ! uv run python -m src.evaluation.runner \
    --output results/h2h_qwen3_32b_screening \
    --model "Qwen3 32B" \
    --scenario-ids "$SCREENING_SET" \
    --cloud-runs 1 \
    --prompt-extras "$PROMPT_EXTRAS" 2>&1; then
    echo "FAILED — Qwen3 32B screening"
    FAILED+=("qwen3-32b-screening")
fi
echo ""

# Gemma 3 27B — Screening
SEGMENT=$((SEGMENT + 1))
echo "========================================"
echo "[$SEGMENT/$TOTAL_SEGMENTS] Gemma 3 27B (OpenRouter) — Screening (1 run)"
echo "========================================"

mkdir -p results/h2h_gemma_27b_screening

if ! uv run python -m src.evaluation.runner \
    --output results/h2h_gemma_27b_screening \
    --model "Gemma 3 27B" \
    --scenario-ids "$SCREENING_SET" \
    --cloud-runs 1 \
    --prompt-extras "$PROMPT_EXTRAS" 2>&1; then
    echo "FAILED — Gemma 3 27B screening"
    FAILED+=("gemma-27b-screening")
fi
echo ""

# Qwen3 32B — Accumulated State
SEGMENT=$((SEGMENT + 1))
echo "========================================"
echo "[$SEGMENT/$TOTAL_SEGMENTS] Qwen3 32B (OpenRouter) — Accumulated State (1 run)"
echo "========================================"

mkdir -p results/h2h_qwen3_32b_accstate

if ! uv run python -m src.evaluation.runner \
    --output results/h2h_qwen3_32b_accstate \
    --model "Qwen3 32B" \
    --scenario-ids "$ACCSTATE_SET" \
    --cloud-runs 1 \
    --prompt-extras "$PROMPT_EXTRAS" 2>&1; then
    echo "FAILED — Qwen3 32B accumulated state"
    FAILED+=("qwen3-32b-accstate")
fi
echo ""

# Gemma 3 27B — Accumulated State
SEGMENT=$((SEGMENT + 1))
echo "========================================"
echo "[$SEGMENT/$TOTAL_SEGMENTS] Gemma 3 27B (OpenRouter) — Accumulated State (1 run)"
echo "========================================"

mkdir -p results/h2h_gemma_27b_accstate

if ! uv run python -m src.evaluation.runner \
    --output results/h2h_gemma_27b_accstate \
    --model "Gemma 3 27B" \
    --scenario-ids "$ACCSTATE_SET" \
    --cloud-runs 1 \
    --prompt-extras "$PROMPT_EXTRAS" 2>&1; then
    echo "FAILED — Gemma 3 27B accumulated state"
    FAILED+=("gemma-27b-accstate")
fi
echo ""

# --- Summary ---
echo "========================================"
echo "Phase 2 Complete"
echo "========================================"
echo "Finished: $(date)"
echo ""
echo "Results:"
echo "  Coder screening:  results/h2h_coder_screening/"
echo "  70B screening:    results/h2h_70b_screening/"
echo "  Coder acc. state: results/h2h_coder_accstate/"
echo "  70B acc. state:   results/h2h_70b_accstate/"
echo "  Qwen3 32B scr:    results/h2h_qwen3_32b_screening/"
echo "  Qwen3 32B acc:    results/h2h_qwen3_32b_accstate/"
echo "  Gemma 27B scr:    results/h2h_gemma_27b_screening/"
echo "  Gemma 27B acc:    results/h2h_gemma_27b_accstate/"
echo "  Log:              $LOG_FILE"

if [[ ${#FAILED[@]} -gt 0 ]]; then
    echo ""
    echo "Failures:"
    for f in "${FAILED[@]}"; do
        echo "  - $f"
    done
    exit 1
fi
