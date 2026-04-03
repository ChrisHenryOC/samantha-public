#!/usr/bin/env bash
# Phase 3a: Prompt experiments for Llama 3.3 70B and Qwen3 14B (GH Issue #219)
#
# Runs 5 prompt experiments on 5 discriminating scenarios (11 steps) x 3 runs
# per model. Baseline (experiment 0) reuses Phase 2 data.
#
# Experiments:
#   1. +state_sequence      — explicit step ordering
#   2. +retry_clarification — RETRY means stay at current state
#   3. +combined            — experiments 1 + 2 together
#   4. +few_shot            — experiment 3 + worked example
#   5. temp=0.1             — best prompt (experiment 3) + temperature 0.1
#
# Results: results/phase3a_*/
# Estimated runtime: ~3.2 hours total
#
# Usage:
#   ./scripts/run_phase3a.sh              # Run all experiments
#   ./scripts/run_phase3a.sh 1            # Run only experiment 1
#   ./scripts/run_phase3a.sh 3 5          # Run experiments 3 and 5

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

TIMEOUT=600
RUNS=3
SCENARIOS="SC-003,SC-013,SC-019,SC-082,SC-103"

MODELS=(
    "Qwen3 14B Local"
    "Llama 3.3 70B Local"
)

# If arguments provided, use them as experiment numbers; otherwise run all
if [[ $# -gt 0 ]]; then
    EXPERIMENTS=("$@")
else
    EXPERIMENTS=(1 2 3 4 5)
fi

# Map experiment number to output dir, prompt-extras, and description
get_experiment_config() {
    local exp=$1
    case $exp in
        1) echo "phase3a_state_seq|state_sequence|+state_sequence";;
        2) echo "phase3a_retry|retry_clarification|+retry_clarification";;
        3) echo "phase3a_combined|state_sequence,retry_clarification|+combined (state_seq + retry)";;
        4) echo "phase3a_few_shot|state_sequence,retry_clarification,few_shot|+few_shot (combined + example)";;
        5) echo "phase3a_temp01|state_sequence,retry_clarification|+temp=0.1 (combined + temp 0.1)";;
        *) echo ""; return 1;;
    esac
}

echo "========================================"
echo "Phase 3a: Prompt Experiments"
echo "========================================"
echo "Models:      ${#MODELS[@]}"
echo "Scenarios:   5 (11 steps)"
echo "Runs:        $RUNS per model per experiment"
echo "Experiments: ${EXPERIMENTS[*]}"
echo "Timeout:     ${TIMEOUT}s per model load"
echo "Started:     $(date)"
echo ""

TOTAL_EXPERIMENTS=${#EXPERIMENTS[@]}
COMPLETED=0
FAILED=()

for EXP_NUM in "${EXPERIMENTS[@]}"; do
    CONFIG=$(get_experiment_config "$EXP_NUM")
    if [[ -z "$CONFIG" ]]; then
        echo "ERROR: Unknown experiment number: $EXP_NUM"
        FAILED+=("exp$EXP_NUM")
        continue
    fi

    IFS='|' read -r OUTPUT_NAME PROMPT_EXTRAS DESCRIPTION <<< "$CONFIG"
    OUTPUT="results/$OUTPUT_NAME"
    COMPLETED=$((COMPLETED + 1))

    echo "========================================"
    echo "[$COMPLETED/$TOTAL_EXPERIMENTS] Experiment $EXP_NUM: $DESCRIPTION"
    echo "  Prompt extras: $PROMPT_EXTRAS"
    echo "  Output: $OUTPUT"
    echo "========================================"

    rm -rf "$OUTPUT"
    mkdir -p "$OUTPUT"

    for MODEL in "${MODELS[@]}"; do
        echo ""
        echo "--- $MODEL ---"

        echo "Loading model (timeout ${TIMEOUT}s)..."
        if ! uv run python -m src.server.switch_model "$MODEL" --timeout "$TIMEOUT" 2>&1; then
            echo "FAILED — could not load $MODEL"
            FAILED+=("exp${EXP_NUM}:${MODEL}")
            continue
        fi

        EXTRA_ARGS=()
        EXTRA_ARGS+=(--prompt-extras "$PROMPT_EXTRAS")

        # Experiment 5: override temperature to 0.1
        # Temperature is set in models.yaml, so we use a temp config overlay
        if [[ "$EXP_NUM" == "5" ]]; then
            # Create a temporary models.yaml with temperature=0.1
            TEMP_MODELS="$OUTPUT/models_temp01.yaml"
            if [[ ! -f "$TEMP_MODELS" ]]; then
                if ! uv run python -c "
import yaml
from pathlib import Path

config = yaml.safe_load(Path('config/models.yaml').read_text())
for model in config.get('models', []):
    if model.get('name') in ('Llama 3.3 70B Local', 'Qwen3 14B Local'):
        model['parameters']['temperature'] = 0.1
Path('$TEMP_MODELS').write_text(yaml.dump(config, default_flow_style=False))
print('Created temp config with temperature=0.1')
"; then
                    echo "FAILED — could not create temp config for experiment 5"
                    FAILED+=("exp${EXP_NUM}:config")
                    continue
                fi
            fi
            EXTRA_ARGS+=(--models "$TEMP_MODELS")
        fi

        echo "Running 5 scenarios x $RUNS runs (extras: $PROMPT_EXTRAS)..."
        if ! FORCE_DASHBOARD=1 uv run python -m src.evaluation.runner \
            --output "$OUTPUT" \
            --model "$MODEL" \
            --scenario-ids "$SCENARIOS" \
            --runs "$RUNS" \
            "${EXTRA_ARGS[@]}" 2>&1; then
            echo "FAILED — evaluation error for $MODEL"
            FAILED+=("exp${EXP_NUM}:${MODEL}")
            continue
        fi
    done

    echo ""
done

echo ""
echo "========================================"
echo "Phase 3a Complete"
echo "========================================"
echo "Finished:    $(date)"
echo "Completed:   $COMPLETED/$TOTAL_EXPERIMENTS experiments"
echo "Results:     results/phase3a_*/"

if [[ ${#FAILED[@]} -gt 0 ]]; then
    echo ""
    echo "Failures:"
    for f in "${FAILED[@]}"; do
        echo "  - $f"
    done
    exit 1
fi
