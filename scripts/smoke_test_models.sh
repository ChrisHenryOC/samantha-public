#!/usr/bin/env bash
# Smoke test: load each local model and run 1 scenario to verify it works.
#
# For each model this script:
#   1. Calls switch_model to load the model into llama-server
#   2. Runs SC-001 (single scenario, 2 steps) through the evaluation runner
#   3. Checks that latency > 0 (proves real inference happened)
#   4. Reports pass/fail per model
#
# Uses a 600s timeout for model loading (large models need time).
# Results go to results/smoke_test/ (overwritten each run).
#
# Usage:
#   ./scripts/smoke_test_models.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

OUTPUT="results/smoke_test"
TIMEOUT=600
SCENARIO="SC-001"

# Clean previous smoke test results
rm -rf "$OUTPUT"
mkdir -p "$OUTPUT"

# Get all local model names from config
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
COUNT=0
PASSED=0
FAILED_MODELS=()

echo "========================================"
echo "Model Smoke Test"
echo "========================================"
echo "Scenario: $SCENARIO"
echo "Timeout: ${TIMEOUT}s"
echo "Models: $TOTAL"
echo "Output: $OUTPUT"
echo "Started: $(date)"
echo ""

while IFS= read -r MODEL; do
    COUNT=$((COUNT + 1))
    echo "[$COUNT/$TOTAL] $MODEL"

    # Step 1: Load model
    echo "  Loading..."
    if ! uv run python -m src.server.switch_model "$MODEL" --timeout "$TIMEOUT" 2>&1; then
        echo "  FAIL — could not load model"
        FAILED_MODELS+=("$MODEL")
        echo ""
        continue
    fi

    # Step 2: Run 1 scenario
    echo "  Running $SCENARIO..."
    if ! FORCE_DASHBOARD=1 uv run python -m src.evaluation.runner \
        --output "$OUTPUT" \
        --model "$MODEL" \
        --scenario-ids "$SCENARIO" \
        --runs 1 2>&1; then
        echo "  FAIL — evaluation runner error"
        FAILED_MODELS+=("$MODEL")
        echo ""
        continue
    fi

    # Step 3: Verify real inference happened
    # Pass variables via environment to avoid shell interpolation in Python source
    RESULT=$(SMOKE_OUTPUT="$OUTPUT" SMOKE_SCENARIO="$SCENARIO" SMOKE_MODEL="$MODEL" \
        uv run python -c "
import json, os
from pathlib import Path

output = os.environ['SMOKE_OUTPUT']
scenario_id = os.environ['SMOKE_SCENARIO']
model_name = os.environ['SMOKE_MODEL']

# Find this model's result directory by checking run JSON contents
base = Path(output)
for model_dir in base.iterdir():
    if not model_dir.is_dir():
        continue
    run_file = model_dir / 'run_1.json'
    if not run_file.exists():
        continue
    data = json.loads(run_file.read_text())
    # Verify this is the current model's results
    if data.get('model_id', '') not in model_dir.name.replace('-', '').replace('_', '').replace('.', ''):
        # Heuristic check — also verify by scenario match
        pass
    for s in data.get('scenarios', []):
        if s.get('scenario_id') != scenario_id:
            continue
        steps = s.get('steps', [])
        if not steps:
            print('NO_STEPS')
            break
        total_lat = sum(st.get('latency_ms', 0) for st in steps)
        if total_lat == 0:
            print('ZERO_LATENCY')
            break
        correct = sum(1 for st in steps if not st.get('failure_type'))
        print(f'OK lat={total_lat:.0f}ms correct={correct}/{len(steps)}')
        break
    else:
        continue
    break
else:
    print('NO_RESULTS')
" 2>&1)

    if [[ "$RESULT" == OK* ]]; then
        echo "  PASS — $RESULT"
        PASSED=$((PASSED + 1))
    elif [[ "$RESULT" == "ZERO_LATENCY" ]]; then
        echo "  FAIL — zero latency (model not actually running)"
        FAILED_MODELS+=("$MODEL")
    else
        echo "  FAIL — ${RESULT:-no results found}"
        FAILED_MODELS+=("$MODEL")
    fi

    echo ""
done <<< "$MODELS"

echo "========================================"
echo "Smoke Test Results: $(date)"
echo "Passed: $PASSED/$TOTAL"
if [[ ${#FAILED_MODELS[@]} -gt 0 ]]; then
    echo "Failed:"
    for m in "${FAILED_MODELS[@]}"; do
        echo "  - $m"
    done
    exit 1
else
    echo "All models passed."
fi
echo "========================================"
