#!/usr/bin/env bash
# Download all local GGUF models defined in config/models.yaml.
#
# Checks the llama.cpp cache (~/Library/Caches/llama.cpp/) and skips
# models that are already downloaded. Downloads missing models using
# hf download to the HF cache, where llama-server -hf will find them.
#
# Usage:
#   ./scripts/download_models.sh           # Download missing models
#   ./scripts/download_models.sh --dry-run # Show what would be downloaded

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG="$PROJECT_ROOT/config/models.yaml"

# llama-server -hf caches here on macOS
LLAMA_CACHE="$HOME/Library/Caches/llama.cpp"

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
fi

if [ ! -f "$CONFIG" ]; then
    echo "ERROR: Config file not found: $CONFIG"
    exit 1
fi

# Extract hf_repo values from models.yaml (lines like:   hf_repo: "owner/repo:quant")
# Filter out comment lines to avoid picking up examples.
REPOS=$(grep -E '^\s+hf_repo:' "$CONFIG" | sed 's/.*hf_repo: *"//' | sed 's/".*//')

if [[ -z "$REPOS" ]]; then
    echo "No hf_repo entries found in $CONFIG"
    exit 0
fi

TOTAL=$(echo "$REPOS" | grep -c .)
echo "========================================"
echo "GGUF Model Downloader"
echo "========================================"
echo "Models in config: $TOTAL"
echo "Cache: $LLAMA_CACHE"
echo ""

COUNT=0
SKIPPED=0
DOWNLOADED=0
FAILED=0

while IFS= read -r ENTRY; do
    COUNT=$((COUNT + 1))

    # Split "owner/repo:quantization" into repo and quant
    REPO="${ENTRY%%:*}"
    QUANT="${ENTRY##*:}"

    # Derive the GGUF filename
    # e.g. "bartowski/google_gemma-3-12b-it-GGUF" + "Q4_K_M" -> "google_gemma-3-12b-it-Q4_K_M.gguf"
    REPO_NAME="${REPO##*/}"

    # Guard: repo name must end in -GGUF for filename derivation to work
    if [[ "$REPO_NAME" != *-GGUF ]]; then
        echo "[$COUNT/$TOTAL] $REPO"
        echo "         WARNING: repo name does not end in '-GGUF', skipping"
        echo ""
        FAILED=$((FAILED + 1))
        continue
    fi

    MODEL_BASE="${REPO_NAME%-GGUF}"
    FILENAME="${MODEL_BASE}-${QUANT}.gguf"

    # llama-server -hf flattens the cache path: owner_repo_filename.gguf
    CACHE_NAME="${REPO//\//_}_${FILENAME}"

    echo "[$COUNT/$TOTAL] $REPO"
    echo "         File: $FILENAME"

    # Check llama.cpp cache
    if [[ -f "$LLAMA_CACHE/$CACHE_NAME" ]]; then
        SIZE=$(du -h "$LLAMA_CACHE/$CACHE_NAME" | cut -f1 | tr -d ' ')
        echo "         CACHED ($SIZE) — skipping"
        SKIPPED=$((SKIPPED + 1))
        echo ""
        continue
    fi

    if [[ "$DRY_RUN" == true ]]; then
        echo "         MISSING — would download"
        echo ""
        continue
    fi

    echo "         Downloading..."
    if uv run hf download "$REPO" "$FILENAME" 2>&1; then
        echo "         Done"
        DOWNLOADED=$((DOWNLOADED + 1))
    else
        echo "         FAILED"
        FAILED=$((FAILED + 1))
    fi
    echo ""
done <<< "$REPOS"

echo "========================================"
echo "Cached:     $SKIPPED"
if [[ "$DRY_RUN" == true ]]; then
    echo "To download: $((TOTAL - SKIPPED))"
else
    echo "Downloaded: $DOWNLOADED"
    if [[ $FAILED -gt 0 ]]; then
        echo "Failed:     $FAILED"
        exit 1
    fi
fi
