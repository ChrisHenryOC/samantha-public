#!/usr/bin/env bash
# Skill vs Baseline A/B Comparison (GH Issue #221)
#
# Runs the same 33-scenario screening set (from Phase 1) with two prompt
# configs, then a 5-scenario variance check on skills.
#
# Run 1: skills + retry_clarification (~74 min)
# Run 2: state_sequence + retry_clarification + few_shot (~74 min)
# Run 3: skills variance check, 3 runs on 5 scenarios (~22 min)
#
# Total estimated runtime: ~2.8 hours
#
# Results:
#   results/skill_vs_baseline_skills/    — skills on 33 scenarios
#   results/skill_vs_baseline_fewshot/   — Phase 3a winner on 33 scenarios
#   results/skill_vs_baseline_variance/  — skills variance on 5 scenarios
#
# Usage:
#   ./scripts/run_skill_vs_baseline.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Source shared scenario sets
source "$SCRIPT_DIR/scenario_sets.sh"

MODEL="Llama 3.3 70B Local"
TIMEOUT=600
VARIANCE_SET="$PHASE3A_SET"

FAILED=()

echo "========================================"
echo "Skill vs Baseline A/B Comparison"
echo "========================================"
echo "Model:     $MODEL"
echo "Screening: 33 scenarios (111 steps)"
echo "Variance:  5 scenarios (11 steps) x 3 runs"
echo "Est. time: ~2.8 hours"
echo "Started:   $(date)"
echo ""

# Ensure model is loaded
echo "Loading model (timeout ${TIMEOUT}s)..."
if ! uv run python -m src.server.switch_model "$MODEL" --timeout "$TIMEOUT" 2>&1; then
    echo "FAILED — could not load $MODEL"
    exit 1
fi
echo ""

# --- Run 1: Skills ---
echo "========================================"
echo "[1/3] Skills on screening set (33 scenarios, 1 run)"
echo "========================================"
rm -rf results/skill_vs_baseline_skills
mkdir -p results/skill_vs_baseline_skills

if ! FORCE_DASHBOARD=1 uv run python -m src.evaluation.runner \
    --output results/skill_vs_baseline_skills \
    --model "$MODEL" \
    --scenario-ids "$SCREENING_SET" \
    --local-runs 1 \
    --prompt-extras skills,retry_clarification 2>&1; then
    echo "FAILED — skills run"
    FAILED+=("skills")
fi
echo ""

# --- Run 2: Phase 3a winner (few_shot) ---
echo "========================================"
echo "[2/3] Phase 3a winner on screening set (33 scenarios, 1 run)"
echo "========================================"
rm -rf results/skill_vs_baseline_fewshot
mkdir -p results/skill_vs_baseline_fewshot

if ! FORCE_DASHBOARD=1 uv run python -m src.evaluation.runner \
    --output results/skill_vs_baseline_fewshot \
    --model "$MODEL" \
    --scenario-ids "$SCREENING_SET" \
    --local-runs 1 \
    --prompt-extras state_sequence,retry_clarification,few_shot 2>&1; then
    echo "FAILED — few_shot run"
    FAILED+=("few_shot")
fi
echo ""

# --- Run 3: Skills variance ---
echo "========================================"
echo "[3/3] Skills variance check (5 scenarios, 3 runs)"
echo "========================================"
rm -rf results/skill_vs_baseline_variance
mkdir -p results/skill_vs_baseline_variance

if ! FORCE_DASHBOARD=1 uv run python -m src.evaluation.runner \
    --output results/skill_vs_baseline_variance \
    --model "$MODEL" \
    --scenario-ids "$VARIANCE_SET" \
    --local-runs 3 \
    --prompt-extras skills,retry_clarification 2>&1; then
    echo "FAILED — variance run"
    FAILED+=("variance")
fi
echo ""

# --- Summary ---
echo "========================================"
echo "A/B Comparison Complete"
echo "========================================"
echo "Finished: $(date)"
echo ""
echo "Results:"
echo "  Skills:    results/skill_vs_baseline_skills/"
echo "  Few-shot:  results/skill_vs_baseline_fewshot/"
echo "  Variance:  results/skill_vs_baseline_variance/"

if [[ ${#FAILED[@]} -gt 0 ]]; then
    echo ""
    echo "Failures:"
    for f in "${FAILED[@]}"; do
        echo "  - $f"
    done
    exit 1
fi
