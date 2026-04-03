#!/usr/bin/env bash
# Run evaluation on the SC-104 scenario (the null-fields scenario fixed
# in issue #111) with cost-saving defaults from PR #115.
#
# Usage:
#   ./scripts/run_new_scenarios.sh                        # Dry run (default)
#   ./scripts/run_new_scenarios.sh --go                   # Execute for real
#   ./scripts/run_new_scenarios.sh --go --local-runs 3    # Override local runs
#   ./scripts/run_new_scenarios.sh --go --runs 1          # Single run per model
#
# Default configuration:
#   - Category: unknown_input (contains SC-104)
#   - Cloud runs: 1 (ceiling benchmark only)
#   - Local runs: 5 (variance measurement)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

OUTPUT_DIR="results/sc104_validation"

# Parse --go and --clean flags (consumed here, not passed to Python)
GO=false
CLEAN=false
PASSTHROUGH_ARGS=()
for arg in "$@"; do
    if [[ "$arg" == "--go" ]]; then
        GO=true
    elif [[ "$arg" == "--clean" ]]; then
        CLEAN=true
    else
        PASSTHROUGH_ARGS+=("$arg")
    fi
done

if [[ "$CLEAN" == true ]]; then
    echo "Cleaning previous results in $OUTPUT_DIR ..."
    rm -rf "$OUTPUT_DIR"
fi

mkdir -p "$OUTPUT_DIR"

COMMON_ARGS=(
    --output "$OUTPUT_DIR"
    --category unknown_input
    --cloud-runs 1
    --local-runs 5
)

# Default to dry-run unless --go is passed
if [[ "$GO" != true ]]; then
    echo "DRY RUN — pass --go to execute for real"
    echo ""
    uv run python -m src.evaluation.runner \
        "${COMMON_ARGS[@]}" \
        --dry-run \
        ${PASSTHROUGH_ARGS[@]+"${PASSTHROUGH_ARGS[@]}"}
    exit 0
fi

echo "========================================"
echo "SC-104 Validation Run (issue #111)"
echo "  Category: unknown_input"
echo "========================================"
echo "Output: $OUTPUT_DIR"
echo "Started: $(date)"
echo ""

FORCE_DASHBOARD=1 uv run python -m src.evaluation.runner \
    "${COMMON_ARGS[@]}" \
    ${PASSTHROUGH_ARGS[@]+"${PASSTHROUGH_ARGS[@]}"} 2>&1 | tee "$OUTPUT_DIR/run.log"

echo ""
echo "Finished: $(date)"
