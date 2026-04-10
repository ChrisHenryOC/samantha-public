"""Connector integration test script.

Exercises the full prediction pipeline — adapter → PredictionEngine → prompt
template → model → response parsing → validation — against real routing and
query scenarios. Produces a scored summary table and JSON results.

Usage:
    uv run python scripts/test_connectors.py                        # all models
    uv run python scripts/test_connectors.py --provider ollama      # local only
    uv run python scripts/test_connectors.py --provider openrouter  # cloud only
    uv run python scripts/test_connectors.py --models "llama3.1:8b" # specific model
    uv run python scripts/test_connectors.py --routing-count 10     # more scenarios
    uv run python scripts/test_connectors.py --query-count 5        # more queries
    uv run python scripts/test_connectors.py --all                  # all scenarios
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Ensure the project root is on sys.path so src imports resolve.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.models.config import ModelConfig, load_models, load_settings  # noqa: E402
from src.models.llamacpp_adapter import LlamaCppAdapter  # noqa: E402
from src.models.openrouter_adapter import OpenRouterAdapter  # noqa: E402
from src.prediction.engine import (  # noqa: E402
    PredictionEngine,
    PredictionResult,
    QueryPredictionResult,
)
from src.simulator.loader import (  # noqa: E402
    load_all_query_scenarios,
    load_all_scenarios,
)
from src.simulator.schema import QueryScenario, Scenario  # noqa: E402
from src.workflow.models import Event, Order, expand_panel  # noqa: E402
from src.workflow.validator import ValidationResult, validate_prediction  # noqa: E402

_SCENARIOS_DIR = _PROJECT_ROOT / "scenarios"
_QUERY_DIR = _SCENARIOS_DIR / "query"
# Routing category subdirectories (everything except query).
_ROUTING_CATEGORIES = ("rule_coverage", "multi_rule", "accumulated_state", "unknown_input")
_RESULTS_DIR = _PROJECT_ROOT / "results" / "connector_tests"

_DEFAULT_ROUTING_COUNT = 5
_DEFAULT_QUERY_COUNT = 3


# --- Order/Event construction from scenario data ---


def build_order_from_scenario(scenario: Scenario) -> Order:
    """Construct an Order from the first step's event_data.

    Sets current_state to ACCESSIONING (the state before the first event
    is evaluated) and expands panel names in ordered_tests.
    """
    step = scenario.steps[0]
    data = step.event_data

    # Expand panels (e.g. "Breast IHC Panel" → individual tests).
    raw_tests: list[str] = data.get("ordered_tests", [])
    expanded_tests: list[str] = []
    for test in raw_tests:
        expanded_tests.extend(expand_panel(test))

    return Order(
        order_id=f"TEST-{scenario.scenario_id}",
        scenario_id=scenario.scenario_id,
        patient_name=data.get("patient_name"),
        patient_age=data.get("age"),
        patient_sex=data.get("sex"),
        specimen_type=data["specimen_type"],
        anatomic_site=data["anatomic_site"],
        fixative=data.get("fixative", "formalin"),
        fixation_time_hours=data.get("fixation_time_hours"),
        ordered_tests=expanded_tests,
        priority=data.get("priority", "routine"),
        billing_info_present=data.get("billing_info_present", True),
        current_state="ACCESSIONING",
        flags=[],
    )


def build_event_from_step(scenario: Scenario, step_index: int, order_id: str) -> Event:
    """Construct an Event from a ScenarioStep."""
    step = scenario.steps[step_index]
    return Event(
        event_id=f"EVT-{uuid.uuid4().hex[:8]}",
        order_id=order_id,
        step_number=step.step,
        event_type=step.event_type,
        event_data=step.event_data,
    )


# --- Adapter factory ---


_API_KEY_FILE = _PROJECT_ROOT / "notes" / "openrouter-api-key.txt"


def _resolve_openrouter_key() -> str | None:
    """Read the OpenRouter API key from env var or local key file."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key
    if _API_KEY_FILE.is_file():
        key = _API_KEY_FILE.read_text().strip()
        if key:
            return key
    return None


def create_adapter(
    config: ModelConfig, settings_timeout: int
) -> LlamaCppAdapter | OpenRouterAdapter:
    """Instantiate the correct adapter for a model config."""
    if config.provider == "llamacpp":
        return LlamaCppAdapter(config, timeout_seconds=settings_timeout)
    if config.provider == "openrouter":
        api_key = _resolve_openrouter_key()
        if not api_key:
            raise ValueError(
                f"OPENROUTER_API_KEY env var (or {_API_KEY_FILE}) required for model {config.name}"
            )
        return OpenRouterAdapter(config, timeout_seconds=settings_timeout, api_key=api_key)
    raise ValueError(f"Unknown provider: {config.provider}")


# --- Routing scenario runner ---


def run_routing_scenarios(
    engine: PredictionEngine,
    scenarios: list[Scenario],
) -> list[dict[str, Any]]:
    """Run step-1 of each routing scenario and validate against ground truth."""
    results: list[dict[str, Any]] = []

    for scenario in scenarios:
        step = scenario.steps[0]
        expected = step.expected_output

        order = build_order_from_scenario(scenario)
        event = build_event_from_step(scenario, 0, order.order_id)

        result: PredictionResult = engine.predict_routing(order, [], event)

        record: dict[str, Any] = {
            "scenario_id": scenario.scenario_id,
            "description": scenario.description,
            "model_id": engine.model_id,
            "provider": engine.provider,
            "latency_ms": result.raw_response.latency_ms,
            "input_tokens": result.raw_response.input_tokens,
            "output_tokens": result.raw_response.output_tokens,
            "cost_estimate_usd": result.raw_response.cost_estimate_usd,
        }

        if result.error is not None:
            record["error"] = result.error
            record["state_correct"] = False
            record["rules_correct"] = False
            record["flags_correct"] = False
        else:
            prediction = {
                "next_state": result.next_state,
                "applied_rules": list(result.applied_rules),
                "flags": list(result.flags),
            }
            expected_dict = {
                "next_state": expected.next_state,
                "applied_rules": list(expected.applied_rules),
                "flags": list(expected.flags),
            }
            validation: ValidationResult = validate_prediction(prediction, expected_dict)
            record["predicted"] = prediction
            record["expected"] = expected_dict
            record["state_correct"] = validation.state_correct
            record["rules_correct"] = validation.rules_correct
            record["flags_correct"] = validation.flags_correct
            record["error"] = None

        results.append(record)
        all_ok = (
            record.get("error") is None
            and record["state_correct"]
            and record["rules_correct"]
            and record["flags_correct"]
        )
        status = "PASS" if all_ok else "FAIL"
        print(f"  {scenario.scenario_id}: {status} ({result.raw_response.latency_ms:.0f}ms)")

    return results


# --- Query scenario runner ---


def run_query_scenarios(
    engine: PredictionEngine,
    scenarios: list[QueryScenario],
) -> list[dict[str, Any]]:
    """Run each query scenario and compare against expected output."""
    results: list[dict[str, Any]] = []

    for scenario in scenarios:
        expected = scenario.expected_output
        result: QueryPredictionResult = engine.predict_query(scenario)

        record: dict[str, Any] = {
            "scenario_id": scenario.scenario_id,
            "description": scenario.description,
            "model_id": engine.model_id,
            "provider": engine.provider,
            "answer_type": expected.answer_type,
            "latency_ms": result.raw_response.latency_ms,
            "input_tokens": result.raw_response.input_tokens,
            "output_tokens": result.raw_response.output_tokens,
            "cost_estimate_usd": result.raw_response.cost_estimate_usd,
        }

        if result.error is not None:
            record["error"] = result.error
            record["order_ids_correct"] = False
        else:
            # Compare order_ids for answer types that return them.
            parsed = result.parsed_output or {}
            predicted_ids = sorted(parsed.get("order_ids", []))
            expected_ids = sorted(expected.order_ids)
            record["predicted_order_ids"] = predicted_ids
            record["expected_order_ids"] = expected_ids
            record["order_ids_correct"] = predicted_ids == expected_ids
            record["error"] = None

        results.append(record)
        q_ok = record.get("error") is None and record.get("order_ids_correct", True)
        status = "PASS" if q_ok else "FAIL"
        print(f"  {scenario.scenario_id}: {status} ({result.raw_response.latency_ms:.0f}ms)")

    return results


# --- Summary output ---


def print_summary(all_results: dict[str, dict[str, Any]]) -> None:
    """Print a markdown-style summary table to stdout."""
    print("\n" + "=" * 80)
    print("CONNECTOR TEST SUMMARY")
    print("=" * 80)

    # Header
    print(
        f"{'Model':<30} {'Provider':<12} {'State':<8} {'Rules':<8} "
        f"{'Flags':<8} {'Query':<8} {'Avg ms':<10} {'Errors':<8}"
    )
    print("-" * 92)

    for model_id, data in all_results.items():
        routing = data.get("routing", [])
        query = data.get("query", [])

        # Routing accuracy
        r_total = len(routing)
        state_ok = sum(1 for r in routing if r["state_correct"])
        rules_ok = sum(1 for r in routing if r["rules_correct"])
        flags_ok = sum(1 for r in routing if r["flags_correct"])
        r_errors = sum(1 for r in routing if r.get("error"))

        state_pct = f"{state_ok}/{r_total}" if r_total else "—"
        rules_pct = f"{rules_ok}/{r_total}" if r_total else "—"
        flags_pct = f"{flags_ok}/{r_total}" if r_total else "—"

        # Query accuracy
        q_total = len(query)
        q_ok = sum(1 for q in query if q.get("order_ids_correct", False))
        q_errors = sum(1 for q in query if q.get("error"))
        query_pct = f"{q_ok}/{q_total}" if q_total else "—"

        # Avg latency across all results
        all_latencies = [r["latency_ms"] for r in routing + query]
        avg_latency = sum(all_latencies) / len(all_latencies) if all_latencies else 0

        total_errors = r_errors + q_errors
        provider = data.get("provider", "?")

        # Truncate model_id for display
        display_id = model_id if len(model_id) <= 28 else model_id[:25] + "..."

        print(
            f"{display_id:<30} {provider:<12} {state_pct:<8} {rules_pct:<8} "
            f"{flags_pct:<8} {query_pct:<8} {avg_latency:<10.0f} {total_errors:<8}"
        )

    print("=" * 92)


# --- Main ---


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test model connectors through the full prediction pipeline."
    )
    parser.add_argument(
        "--provider",
        choices=["llamacpp", "openrouter"],
        help="Only test models from this provider.",
    )
    parser.add_argument(
        "--models",
        help="Comma-separated model IDs to test (e.g. 'llama3.1:8b,mistral:7b').",
    )
    parser.add_argument(
        "--routing-count",
        type=int,
        default=_DEFAULT_ROUTING_COUNT,
        help=f"Number of routing scenarios to run (default: {_DEFAULT_ROUTING_COUNT}).",
    )
    parser.add_argument(
        "--query-count",
        type=int,
        default=_DEFAULT_QUERY_COUNT,
        help=f"Number of query scenarios to run (default: {_DEFAULT_QUERY_COUNT}).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run ALL scenarios (overrides --routing-count and --query-count).",
    )
    args = parser.parse_args()

    # Load configuration.
    model_configs = load_models()
    settings = load_settings()

    # Filter models.
    if args.provider:
        model_configs = [m for m in model_configs if m.provider == args.provider]
    if args.models:
        requested_ids = {m.strip() for m in args.models.split(",")}
        model_configs = [m for m in model_configs if m.model_id in requested_ids]

    if not model_configs:
        print("No models match the filter criteria. Check --provider / --models.")
        sys.exit(1)

    print(f"Models to test: {', '.join(m.name for m in model_configs)}")

    # Load routing scenarios from each category subdirectory (skip query/).
    routing_scenarios: list[Scenario] = []
    for cat in _ROUTING_CATEGORIES:
        cat_dir = _SCENARIOS_DIR / cat
        if cat_dir.exists():
            routing_scenarios.extend(load_all_scenarios(cat_dir))
    routing_scenarios.sort(key=lambda s: s.scenario_id)
    query_scenarios = load_all_query_scenarios(_QUERY_DIR)

    # Select scenario subsets.
    if not args.all:
        # Prefer rule_coverage scenarios for routing tests.
        rc = [s for s in routing_scenarios if s.category == "rule_coverage"]
        pool = rc if rc else routing_scenarios
        routing_scenarios = pool[: args.routing_count]
        # Prefer tier-1 scenarios for query tests.
        t1 = [s for s in query_scenarios if s.tier == 1]
        q_pool = t1 if t1 else query_scenarios
        query_scenarios = q_pool[: args.query_count]

    print(f"Routing scenarios: {len(routing_scenarios)}")
    print(f"Query scenarios: {len(query_scenarios)}")
    print()

    # Run tests per model.
    all_results: dict[str, dict[str, Any]] = {}
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")

    for config in model_configs:
        print(f"--- {config.name} ({config.provider}/{config.model_id}) ---")

        try:
            adapter = create_adapter(config, settings.timeout_seconds)
        except ValueError as exc:
            print(f"  SKIP: {exc}")
            continue

        engine = PredictionEngine(adapter)

        model_data: dict[str, Any] = {"provider": config.provider}

        if routing_scenarios:
            print("  Routing:")
            model_data["routing"] = run_routing_scenarios(engine, routing_scenarios)

        if query_scenarios:
            print("  Query:")
            model_data["query"] = run_query_scenarios(engine, query_scenarios)

        all_results[config.model_id] = model_data

        # Close the adapter's HTTP client.
        adapter.close()
        print()

    if not all_results:
        print("No models were tested successfully.")
        sys.exit(1)

    # Print summary table.
    print_summary(all_results)

    # Write JSON results.
    output_dir = _RESULTS_DIR / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "results.json"

    output_data = {
        "timestamp": timestamp,
        "models_tested": [c.model_id for c in model_configs if c.model_id in all_results],
        "routing_scenario_count": len(routing_scenarios),
        "query_scenario_count": len(query_scenarios),
        "results": all_results,
    }
    output_path.write_text(json.dumps(output_data, indent=2, default=str))
    print(f"\nResults written to: {output_path}")


if __name__ == "__main__":
    main()
