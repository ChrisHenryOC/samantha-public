#!/usr/bin/env bash
# Shared scenario set definitions for evaluation scripts.
# Source this file: source "$(dirname "${BASH_SOURCE[0]}")/scenario_sets.sh"

# Phase 1 screening set: 33 scenarios (111 steps), chosen for max differentiation
SCREENING_SET="${SCREENING_SET:-SC-003,SC-005,SC-006,SC-009,SC-010,SC-011,SC-012,SC-013,SC-014,SC-016,SC-019,SC-020,SC-024,SC-026,SC-028,SC-038,SC-045,SC-081,SC-082,SC-087,SC-088,SC-100,SC-101,SC-102,SC-103,SC-106,SC-107,SC-108,SC-109,SC-110,SC-111,SC-112,SC-113}"

# Accumulated state: 10 scenarios (140 steps), long multi-step workflows
ACCSTATE_SET="${ACCSTATE_SET:-SC-090,SC-091,SC-092,SC-093,SC-094,SC-095,SC-096,SC-097,SC-098,SC-099}"

# Phase 3a subset: 5 scenarios (11 steps) for quick validation
PHASE3A_SET="${PHASE3A_SET:-SC-003,SC-013,SC-019,SC-082,SC-103}"
