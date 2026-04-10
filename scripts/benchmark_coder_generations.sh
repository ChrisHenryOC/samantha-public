#!/usr/bin/env bash
# Head-to-head: Qwen2.5 Coder 32B vs Qwen3 Coder 30B-A3B
# Same 5 scenarios, 3 runs each. Kills server between models.
set -euo pipefail

SCENARIOS="SC-003,SC-013,SC-019,SC-082,SC-094"
RUNS=3
EXTRAS="skills,retry_clarification"
CODER25_OUTPUT="results/benchmark_coder25_32b"
CODER3_OUTPUT="results/benchmark_coder3_30b"
TIMEOUT=900  # 15 min — first run may download the GGUF

# --- Helper: ensure no inference servers are running ---
kill_all_servers() {
    echo "Killing all inference servers..."
    uv run python -m src.server.switch_model --stop 2>/dev/null || true
    # Kill any llama-server not tracked by PID file
    pkill -f "llama-server" 2>/dev/null || true
    # Kill Ollama (app and CLI)
    pkill -f "ollama" 2>/dev/null || true
    pkill -f "Ollama" 2>/dev/null || true
    sleep 3
    # Verify ports are clear
    if curl -sf http://localhost:8080/health > /dev/null 2>&1; then
        echo "ERROR: Port 8080 still in use after cleanup. Kill manually."
        exit 1
    fi
    if curl -sf http://localhost:11434/v1/models > /dev/null 2>&1; then
        echo "ERROR: Port 11434 (Ollama) still in use after cleanup. Kill manually."
        exit 1
    fi
    echo "All ports clear."
}

echo "============================================"
echo "  Qwen2.5 Coder 32B vs Qwen3 Coder 30B-A3B"
echo "  Scenarios: $SCENARIOS"
echo "  Runs per model: $RUNS"
echo "============================================"
echo ""

# --- Clean start ---
kill_all_servers

# --- Phase 1: Qwen2.5 Coder 32B (baseline) ---
echo ""
echo "=== Phase 1/2: Qwen2.5 Coder 32B (baseline) ==="
uv run python -m src.server.switch_model "Qwen2.5 Coder 32B Local" --timeout "$TIMEOUT"

# Verify correct model is loaded
LOADED_MODEL=$(curl -sf http://localhost:8080/v1/models 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)['data'][0]['id'])" 2>/dev/null || echo "unknown")
echo "Loaded model: $LOADED_MODEL"
if [[ "$LOADED_MODEL" != *"Coder-32B"* ]]; then
    echo "ERROR: Expected Qwen2.5 Coder 32B but got: $LOADED_MODEL"
    exit 1
fi

rm -rf "$CODER25_OUTPUT"
uv run python -m src.evaluation.runner \
    --output "$CODER25_OUTPUT" \
    --model "Qwen2.5 Coder 32B Local" \
    --scenario-ids "$SCENARIOS" \
    --local-runs "$RUNS" \
    --prompt-extras "$EXTRAS"

# --- Clean between phases ---
echo ""
kill_all_servers

# --- Phase 2: Qwen3 Coder 30B-A3B ---
echo ""
echo "=== Phase 2/2: Qwen3 Coder 30B-A3B ==="
echo "Starting llama-server (timeout ${TIMEOUT}s)..."
uv run python -m src.server.switch_model "Qwen3 Coder 30B-A3B Local" --timeout "$TIMEOUT"

# Verify correct model is loaded
LOADED_MODEL=$(curl -sf http://localhost:8080/v1/models 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)['data'][0]['id'])" 2>/dev/null || echo "unknown")
echo "Loaded model: $LOADED_MODEL"
if [[ "$LOADED_MODEL" != *"Coder-30B"* ]]; then
    echo "ERROR: Expected Qwen3 Coder 30B-A3B but got: $LOADED_MODEL"
    exit 1
fi

rm -rf "$CODER3_OUTPUT"
uv run python -m src.evaluation.runner \
    --output "$CODER3_OUTPUT" \
    --model "Qwen3 Coder 30B-A3B Local" \
    --scenario-ids "$SCENARIOS" \
    --local-runs "$RUNS" \
    --prompt-extras "$EXTRAS"

# --- Cleanup ---
echo ""
kill_all_servers

# --- Summary ---
echo ""
echo "============================================"
echo "  Benchmark Complete"
echo "============================================"
echo "Qwen2.5 Coder 32B: $CODER25_OUTPUT"
echo "Qwen3 Coder 30B-A3B: $CODER3_OUTPUT"
echo ""
echo "Compare with:"
echo "  uv run python -m src.evaluation.reporter $CODER25_OUTPUT $CODER3_OUTPUT"
