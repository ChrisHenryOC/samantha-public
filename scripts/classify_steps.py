"""Classify scenario steps as deterministic or judgment-requiring.

Reads scenarios from the screening set and classifies each step based on
whether its expected applied_rules contain any judgment-requiring rules
(HE-005 through HE-009, IHC-008, IHC-009).

Outputs data/step_classifications.json with per-step classifications
and summary counts.

Usage:
    uv run python scripts/classify_steps.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SCENARIOS_DIR = _PROJECT_ROOT / "scenarios"
_OUTPUT_PATH = _PROJECT_ROOT / "data" / "step_classifications.json"

# 33-scenario screening set (from scripts/scenario_sets.sh)
SCREENING_SET = [
    "SC-003",
    "SC-005",
    "SC-006",
    "SC-009",
    "SC-010",
    "SC-011",
    "SC-012",
    "SC-013",
    "SC-014",
    "SC-016",
    "SC-019",
    "SC-020",
    "SC-024",
    "SC-026",
    "SC-028",
    "SC-038",
    "SC-045",
    "SC-081",
    "SC-082",
    "SC-087",
    "SC-088",
    "SC-100",
    "SC-101",
    "SC-102",
    "SC-103",
    "SC-106",
    "SC-107",
    "SC-108",
    "SC-109",
    "SC-110",
    "SC-111",
    "SC-112",
    "SC-113",
]

# Rules that require human pathologist judgment (from experiment doc)
JUDGMENT_RULES = frozenset(
    {
        "HE-005",
        "HE-006",
        "HE-007",
        "HE-008",
        "HE-009",
        "IHC-008",
        "IHC-009",
    }
)


def load_scenario(scenario_id: str) -> dict | None:
    """Load a scenario JSON file by ID, searching all subdirectories."""
    # Convert SC-003 -> sc_003.json
    filename = f"sc_{scenario_id.split('-')[1]}.json"
    for subdir in _SCENARIOS_DIR.iterdir():
        if not subdir.is_dir():
            continue
        path = subdir / filename
        if path.exists():
            with open(path) as f:
                data = json.load(f)
            if data.get("scenario_id") == scenario_id:
                return data
    return None


def classify_step(applied_rules: list[str]) -> str:
    """Classify a step as 'deterministic' or 'judgment'."""
    if any(rule in JUDGMENT_RULES for rule in applied_rules):
        return "judgment"
    return "deterministic"


def main() -> int:
    classifications: dict[str, dict] = {}
    deterministic_count = 0
    judgment_count = 0
    total_steps = 0

    for scenario_id in sorted(SCREENING_SET):
        scenario = load_scenario(scenario_id)
        if scenario is None:
            print(f"ERROR: Scenario {scenario_id} not found", file=sys.stderr)
            return 1

        for event in scenario["events"]:
            step = event["step"]
            applied_rules = event["expected_output"]["applied_rules"]
            classification = classify_step(applied_rules)

            key = f"{scenario_id}-S{step}"
            classifications[key] = {
                "scenario_id": scenario_id,
                "step": step,
                "classification": classification,
                "expected_rules": applied_rules,
            }

            if classification == "deterministic":
                deterministic_count += 1
            else:
                judgment_count += 1
            total_steps += 1

    output = {
        "summary": {
            "total_steps": total_steps,
            "deterministic": deterministic_count,
            "judgment": judgment_count,
            "deterministic_pct": round(deterministic_count / total_steps * 100, 1),
            "judgment_pct": round(judgment_count / total_steps * 100, 1),
            "screening_scenarios": len(SCREENING_SET),
            "judgment_rules": sorted(JUDGMENT_RULES),
        },
        "steps": classifications,
    }

    _OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    print(f"Classified {total_steps} steps across {len(SCREENING_SET)} scenarios")
    print(f"  Deterministic: {deterministic_count} ({output['summary']['deterministic_pct']}%)")
    print(f"  Judgment:      {judgment_count} ({output['summary']['judgment_pct']}%)")
    print(f"Output: {_OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
