"""Generate a rendered prompt for a specific scenario + step.

Usage:
    uv run python tests/prompt_evaluation/generate_prompt.py SC-070 13
    uv run python tests/prompt_evaluation/generate_prompt.py SC-070 13 \
        > tests/prompt_evaluation/cases/sc070_step13.md

Writes the full prompt the model would see, plus the expected output.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from src.evaluation.harness import (
    advance_order_state,
    advance_slides_state,
    build_event,
    build_order_from_event_data,
    build_slides_for_order,
)
from src.prediction.prompt_template import render_prompt
from src.simulator.loader import load_scenario


def find_scenario(scenario_id: str) -> Path:
    """Find a scenario JSON file by ID."""
    for p in Path("scenarios").rglob("*.json"):
        data = json.loads(p.read_text())
        if data.get("scenario_id") == scenario_id:
            return p
    raise FileNotFoundError(f"Scenario {scenario_id} not found")


def main() -> None:
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <scenario_id> <step_number>", file=sys.stderr)
        sys.exit(1)

    scenario_id = sys.argv[1]
    target_step = int(sys.argv[2])

    scenario_path = find_scenario(scenario_id)
    scenario = load_scenario(scenario_path)

    # Replay the scenario up to the target step
    order = None
    slides = []

    for step in scenario.steps:
        if step.step == target_step:
            # This is the step we want to generate the prompt for
            if order is None:
                order = build_order_from_event_data(scenario_id, step.event_data)
                slides = build_slides_for_order(order)

            event = build_event(order.order_id, step)
            prompt = render_prompt(order, slides, event)

            print(f"# Prompt for {scenario_id} Step {target_step}")
            print()
            print(f"**Scenario**: {scenario.description}")
            print(f"**Event type**: {step.event_type}")
            print(f"**Current state**: {order.current_state}")
            print(f"**Current flags**: {order.flags}")
            print()
            print("## Expected Output")
            print()
            print("```json")
            print(
                json.dumps(
                    {
                        "next_state": step.expected_output.next_state,
                        "applied_rules": list(step.expected_output.applied_rules),
                        "flags": list(step.expected_output.flags),
                    },
                    indent=2,
                )
            )
            print("```")
            print()
            print("## Full Prompt")
            print()
            print("````text")
            print(prompt)
            print("````")
            return

        # Replay: build order at step 1, advance for subsequent steps
        if order is None:
            order = build_order_from_event_data(scenario_id, step.event_data)
            slides = build_slides_for_order(order)
        else:
            order = advance_order_state(order, step.expected_output)
            slides = advance_slides_state(slides, step)

    print(f"Step {target_step} not found in {scenario_id}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
