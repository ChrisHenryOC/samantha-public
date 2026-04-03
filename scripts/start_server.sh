#!/bin/bash
set -euo pipefail

echo "=== Samantha Lab Workflow Server ==="

# 1. Detect provider from config
CONFIG="config/server.yaml"
if [ ! -f "$CONFIG" ]; then
    echo "ERROR: Config file not found: $CONFIG"
    exit 1
fi
PROVIDER=$(grep '^provider:' "$CONFIG" | awk '{print $2}' | tr -d '"')
if [ -z "$PROVIDER" ]; then
    echo "ERROR: No 'provider:' key found in $CONFIG"
    exit 1
fi
echo "Provider: $PROVIDER"

# 2. Validate provider backend
if [ "$PROVIDER" = "llamacpp" ]; then
    LLAMACPP_URL=$(grep '^llamacpp_url:' "$CONFIG" | awk '{print $2}' | tr -d '"')
    LLAMACPP_URL="${LLAMACPP_URL:-http://localhost:8080}"
    if ! curl -s "${LLAMACPP_URL}/health" 2>/dev/null | grep -q "ok"; then
        echo "ERROR: llama-server is not running at ${LLAMACPP_URL}"
        echo "Start it with: llama-server -hf <model-repo> --gpu-layers 99 --port 8080"
        exit 1
    fi
    echo "llama-server: running at ${LLAMACPP_URL}"
elif [ "$PROVIDER" = "openrouter" ]; then
    KEY_FILE="notes/openrouter-api-key.txt"
    if [ ! -s "$KEY_FILE" ]; then
        echo "ERROR: OpenRouter API key not found. Create $KEY_FILE with your key."
        exit 1
    fi
    echo "OpenRouter: API key found"
else
    echo "ERROR: Unknown provider '$PROVIDER' in $CONFIG"
    exit 1
fi

# 3. Seed demo data if DB is empty
DB_PATH="data/live.sqlite"
if [ ! -f "$DB_PATH" ]; then
    echo "Seeding demo data..."
    uv run python -m src.server.seed
else
    echo "Database: $DB_PATH exists"
fi

# 4. Start server
echo ""
echo "Starting server at http://localhost:8000"
echo "Open http://localhost:8000 in your browser"
echo ""
uv run uvicorn src.server.app:create_app --host 127.0.0.1 --port 8000 --factory
