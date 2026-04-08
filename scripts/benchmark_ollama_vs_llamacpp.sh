#!/usr/bin/env bash
# Head-to-head: Ollama MLX vs llama.cpp on Qwen3.5-35B-A3B
# Runs each backend against the same 5 scenarios, 3 runs each.
# Kills each server after its run to avoid memory contention.
set -euo pipefail

SCENARIOS="SC-003,SC-013,SC-019,SC-082,SC-094"
RUNS=3
EXTRAS="skills,retry_clarification"
OLLAMA_OUTPUT="results/benchmark_ollama_mlx"
LLAMACPP_OUTPUT="results/benchmark_llamacpp"
LLAMACPP_TIMEOUT=900  # 15 min — first run may download the GGUF

echo "============================================"
echo "  Ollama MLX vs llama.cpp Benchmark"
echo "  Model: Qwen3.5-35B-A3B"
echo "  Scenarios: $SCENARIOS"
echo "  Runs per backend: $RUNS"
echo "============================================"
echo ""

# --- Phase 1: Kill any existing servers to start clean ---
echo "Cleaning up any running servers..."
uv run python -m src.server.switch_model --stop 2>/dev/null || true
ollama stop qwen3.5:35b-a3b 2>/dev/null || true
sleep 2

# --- Phase 2: Ollama MLX ---
echo ""
echo "=== Phase 1/2: Ollama MLX ==="

# Start Ollama if not running
if ! curl -sf http://localhost:11434/v1/models > /dev/null 2>&1; then
    echo "Starting Ollama..."
    ollama serve &
    OLLAMA_PID=$!
    sleep 5
    if ! curl -sf http://localhost:11434/v1/models > /dev/null 2>&1; then
        echo "ERROR: Ollama failed to start"
        exit 1
    fi
else
    OLLAMA_PID=""
fi

echo "Verifying model is available..."
if ! ollama list | grep -q "qwen3.5"; then
    echo "ERROR: qwen3.5:35b-a3b not found. Pull it with: ollama pull qwen3.5:35b-a3b"
    exit 1
fi

echo "Running Ollama evaluation..."
rm -rf "$OLLAMA_OUTPUT"
uv run python -m src.evaluation.runner \
    --output "$OLLAMA_OUTPUT" \
    --model "Qwen3.5 35B-A3B Ollama MLX" \
    --scenario-ids "$SCENARIOS" \
    --local-runs "$RUNS" \
    --prompt-extras "$EXTRAS"

echo ""
echo "Stopping Ollama to free memory..."
ollama stop qwen3.5:35b-a3b 2>/dev/null || true
if [ -n "${OLLAMA_PID:-}" ]; then
    kill "$OLLAMA_PID" 2>/dev/null || true
fi
pkill -f "ollama" 2>/dev/null || true
sleep 5

# --- Phase 3: llama.cpp ---
echo ""
echo "=== Phase 2/2: llama.cpp ==="
echo "Starting llama-server (timeout ${LLAMACPP_TIMEOUT}s, first run may download GGUF)..."
uv run python -m src.server.switch_model "Qwen3.5 35B-A3B Local" --timeout "$LLAMACPP_TIMEOUT"

echo "Running llama.cpp evaluation..."
rm -rf "$LLAMACPP_OUTPUT"
uv run python -m src.evaluation.runner \
    --output "$LLAMACPP_OUTPUT" \
    --model "Qwen3.5 35B-A3B Local" \
    --scenario-ids "$SCENARIOS" \
    --local-runs "$RUNS" \
    --prompt-extras "$EXTRAS"

echo ""
echo "Stopping llama-server to free memory..."
uv run python -m src.server.switch_model --stop

# --- Phase 4: Summary ---
echo ""
echo "============================================"
echo "  Benchmark Complete"
echo "============================================"
echo "Ollama MLX results:  $OLLAMA_OUTPUT"
echo "llama.cpp results:   $LLAMACPP_OUTPUT"
echo ""
echo "Compare with:"
echo "  uv run python -m src.evaluation.reporter $OLLAMA_OUTPUT $LLAMACPP_OUTPUT"
