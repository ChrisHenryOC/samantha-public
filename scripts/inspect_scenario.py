"""Inspect a single scenario: run it through a model and dump diagnostic output.

Usage:
    uv run python scripts/inspect_scenario.py --scenario SC-001 --prompt-only
    uv run python scripts/inspect_scenario.py --scenario SC-001 --model "Qwen3 8B" --rag
    uv run python scripts/inspect_scenario.py --scenario QR-001 --prompt-only
    uv run python scripts/inspect_scenario.py --scenario SC-001 --step 2 --show-prompt
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

# Ensure the project root is on sys.path so src imports resolve.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.evaluation.harness import (  # noqa: E402
    advance_order_state,
    advance_slides_state,
    build_event,
    build_order_from_event_data,
    build_slides_for_order,
    load_openrouter_key,
)
from src.models.config import ModelConfig, load_models, load_rag_settings  # noqa: E402
from src.models.llamacpp_adapter import LlamaCppAdapter  # noqa: E402
from src.models.openrouter_adapter import OpenRouterAdapter  # noqa: E402
from src.prediction.engine import PredictionEngine  # noqa: E402
from src.prediction.prompt_template import render_prompt  # noqa: E402
from src.prediction.query_prompt_template import render_query_prompt  # noqa: E402
from src.rag.retriever import RagRetriever  # noqa: E402
from src.simulator.loader import load_query_scenario, load_scenario  # noqa: E402
from src.simulator.schema import QueryScenario, Scenario  # noqa: E402
from src.workflow.models import VALID_FLAGS, VALID_STATES  # noqa: E402
from src.workflow.state_machine import StateMachine  # noqa: E402

_SCENARIOS_DIR = _PROJECT_ROOT / "scenarios"

# Display constants
_DOUBLE_BAR = "\u2550" * 3  # ═══
_SINGLE_BAR = "\u2500" * 2  # ──
_CHECK = "\u2713"  # ✓
_CROSS = "\u2717"  # ✗


def find_scenario(scenario_id: str) -> Scenario | QueryScenario:
    """Find and load a scenario by ID, scanning all category directories."""
    is_query = scenario_id.startswith("QR-")
    for path in sorted(_SCENARIOS_DIR.rglob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"Warning: skipping {path}: {exc}", file=sys.stderr)
            continue
        if data.get("scenario_id") == scenario_id:
            if is_query:
                return load_query_scenario(path)
            return load_scenario(path)
    sys.exit(f"Error: scenario '{scenario_id}' not found in {_SCENARIOS_DIR}")


def resolve_model(model_name: str | None) -> ModelConfig:
    """Resolve a model by name, defaulting to the first ceiling-tier model."""
    models = load_models()
    if model_name is None:
        for m in models:
            if m.tier == "ceiling":
                return m
        sys.exit("Error: no ceiling-tier model found in config/models.yaml")
    name_lower = model_name.lower()
    for m in models:
        if m.name.lower() == name_lower:
            return m
    names = [m.name for m in models]
    sys.exit(f"Error: model '{model_name}' not found. Available: {names}")


def create_adapter(config: ModelConfig) -> LlamaCppAdapter | OpenRouterAdapter:
    """Create the appropriate model adapter for a config."""
    if config.provider == "llamacpp":
        return LlamaCppAdapter(config)
    if config.provider == "openrouter":
        api_key = load_openrouter_key()
        return OpenRouterAdapter(config, api_key=api_key)
    sys.exit(f"Error: unknown provider '{config.provider}'")


def _check(actual: object, expected: object) -> str:
    """Return a check or cross mark for match comparison.

    Uses Counter comparison for tuples to match the harness's
    order-independent validation for applied_rules and flags.
    """
    if isinstance(actual, tuple) and isinstance(expected, tuple):
        return _CHECK if Counter(actual) == Counter(expected) else _CROSS
    return _CHECK if actual == expected else _CROSS


def _format_cost(cost: float | None) -> str:
    """Format cost in USD or 'n/a' for local models."""
    return f"${cost:.4f}" if cost is not None else "n/a"


def _validate_ground_truth(scenario: Scenario) -> None:
    """Validate scenario ground truth against the state machine rule catalog."""
    sm = StateMachine()
    all_rule_ids = frozenset(sm.get_all_rule_ids())
    for step in scenario.steps:
        expected = step.expected_output
        if expected.next_state not in VALID_STATES:
            print(
                f"Warning: step {step.step} has invalid expected state {expected.next_state!r}",
                file=sys.stderr,
            )
        for rule_id in expected.applied_rules:
            if rule_id not in all_rule_ids:
                print(
                    f"Warning: step {step.step} has unknown rule {rule_id!r}",
                    file=sys.stderr,
                )
        for flag in expected.flags:
            if flag not in VALID_FLAGS:
                print(
                    f"Warning: step {step.step} has invalid flag {flag!r}",
                    file=sys.stderr,
                )


def run_routing_steps(
    scenario: Scenario,
    engine: PredictionEngine | None,
    config: ModelConfig,
    *,
    rag_retriever: RagRetriever | None,
    step_filter: int | None,
    show_prompt: bool,
    prompt_only: bool,
) -> None:
    """Run routing scenario steps and print diagnostic output."""
    order = None
    slides: list[Any] = []
    total_steps = len(scenario.steps)

    for idx, step in enumerate(scenario.steps):
        # Build / advance state
        if order is None:
            order = build_order_from_event_data(scenario.scenario_id, step.event_data)
            slides = build_slides_for_order(order)
        else:
            prev_step = scenario.steps[idx - 1]
            order = advance_order_state(order, prev_step.expected_output)
            slides = advance_slides_state(slides, prev_step)

        event = build_event(order.order_id, step)

        # Skip output for steps before the filter target
        if step_filter is not None and step.step != step_filter:
            continue

        # Step header
        hdr = f"{scenario.scenario_id} Step {step.step}/{total_steps}: {step.event_type}"
        print(f"\n{_DOUBLE_BAR} {hdr} {_DOUBLE_BAR}")
        print(scenario.description)

        # Event data
        print(f"\n{_SINGLE_BAR} Event Data {_SINGLE_BAR}")
        print(json.dumps(step.event_data, indent=2))

        # RAG chunks
        rag_context = None
        if rag_retriever is not None:
            try:
                chunks, info = rag_retriever.retrieve_for_routing(
                    order.current_state, event.event_type, event.event_data
                )
            except Exception as exc:
                sys.exit(f"Error: RAG retrieval failed: {exc}")
            rag_context = chunks
            print(f"\n{_SINGLE_BAR} RAG Chunks ({info.chunks_retrieved} retrieved) {_SINGLE_BAR}")
            for i, chunk in enumerate(chunks, 1):
                score = f"[{chunk.similarity_score:.4f}]"
                print(f"  {i}. {score} {chunk.source_file} > {chunk.section_title}")

        # Prompt
        if show_prompt or prompt_only:
            prompt_text = render_prompt(order, slides, event, rag_context=rag_context)
            print(f"\n{_SINGLE_BAR} Prompt {_SINGLE_BAR}")
            print(prompt_text)

        if prompt_only:
            continue

        # Prediction
        if engine is None:
            raise RuntimeError("engine must be set when prompt_only is False")
        prediction = engine.predict_routing(order, slides, event, rag_retriever=rag_retriever)

        # Ground truth
        expected = step.expected_output
        print(f"\n{_SINGLE_BAR} Ground Truth {_SINGLE_BAR}")
        print(f"  next_state:     {expected.next_state}")
        print(f"  applied_rules:  {list(expected.applied_rules)}")
        print(f"  flags:          {list(expected.flags)}")

        # Prediction output
        print(f"\n{_SINGLE_BAR} Prediction {_SINGLE_BAR}")
        if prediction.error is not None:
            print(f"  ERROR: {prediction.error}  {_CROSS}")
        else:
            state_mark = _check(prediction.next_state, expected.next_state)
            rules_mark = _check(prediction.applied_rules, expected.applied_rules)
            flags_mark = _check(prediction.flags, expected.flags)
            print(f"  next_state:     {prediction.next_state}  {state_mark}")
            pred_rules = list(prediction.applied_rules)
            print(f"  applied_rules:  {pred_rules}  {rules_mark}")
            pred_flags = list(prediction.flags)
            print(f"  flags:          {pred_flags}  {flags_mark}")
            if prediction.reasoning:
                print(f"  reasoning:      {prediction.reasoning}")

        # Model stats
        resp = prediction.raw_response
        cost = _format_cost(resp.cost_estimate_usd)
        tokens = f"{resp.input_tokens:,} in / {resp.output_tokens:,} out"
        print(f"\n{_SINGLE_BAR} Model {_SINGLE_BAR}")
        print(f"  {config.name} | {resp.latency_ms:,.0f}ms | {tokens} | {cost}")


def run_query_scenario(
    scenario: QueryScenario,
    engine: PredictionEngine | None,
    config: ModelConfig,
    *,
    rag_retriever: RagRetriever | None,
    show_prompt: bool,
    prompt_only: bool,
) -> None:
    """Run a query scenario and print diagnostic output."""
    print(f"\n{_DOUBLE_BAR} {scenario.scenario_id}: query {_DOUBLE_BAR}")
    print(scenario.description)

    print(f"\n{_SINGLE_BAR} Query {_SINGLE_BAR}")
    print(f"  {scenario.query}")

    print(f"\n{_SINGLE_BAR} Database State {_SINGLE_BAR}")
    print(f"  Orders: {len(scenario.database_state.orders)}")
    print(f"  Slides: {len(scenario.database_state.slides)}")

    # RAG chunks
    rag_context = None
    if rag_retriever is not None:
        try:
            chunks, info = rag_retriever.retrieve_for_query(scenario.query)
        except Exception as exc:
            sys.exit(f"Error: RAG retrieval failed: {exc}")
        rag_context = chunks
        print(f"\n{_SINGLE_BAR} RAG Chunks ({info.chunks_retrieved} retrieved) {_SINGLE_BAR}")
        for i, chunk in enumerate(chunks, 1):
            score = f"[{chunk.similarity_score:.4f}]"
            print(f"  {i}. {score} {chunk.source_file} > {chunk.section_title}")

    # Prompt
    if show_prompt or prompt_only:
        prompt_text = render_query_prompt(scenario, rag_context=rag_context)
        print(f"\n{_SINGLE_BAR} Prompt {_SINGLE_BAR}")
        print(prompt_text)

    if prompt_only:
        return

    # Prediction
    if engine is None:
        raise RuntimeError("engine must be set when prompt_only is False")
    prediction = engine.predict_query(scenario, rag_retriever=rag_retriever)

    # Ground truth
    expected = scenario.expected_output
    print(f"\n{_SINGLE_BAR} Ground Truth {_SINGLE_BAR}")
    print(f"  answer_type:  {expected.answer_type}")
    if expected.order_ids:
        print(f"  order_ids:    {list(expected.order_ids)}")
    print(f"  reasoning:    {expected.reasoning}")

    # Prediction output
    print(f"\n{_SINGLE_BAR} Prediction {_SINGLE_BAR}")
    if prediction.error is not None:
        print(f"  ERROR: {prediction.error}  {_CROSS}")
    elif prediction.parsed_output is not None:
        out = prediction.parsed_output
        answer_mark = _check(out.get("answer_type"), expected.answer_type)
        print(f"  answer_type:  {out.get('answer_type')}  {answer_mark}")
        if expected.order_ids:
            pred_ids = tuple(out.get("order_ids", []))
            ids_mark = _check(pred_ids, expected.order_ids)
            print(f"  order_ids:    {list(pred_ids)}  {ids_mark}")
        if out.get("reasoning"):
            print(f"  reasoning:    {out['reasoning']}")
    else:
        print(f"  (no output)  {_CROSS}")

    # Model stats
    resp = prediction.raw_response
    cost = _format_cost(resp.cost_estimate_usd)
    tokens = f"{resp.input_tokens:,} in / {resp.output_tokens:,} out"
    print(f"\n{_SINGLE_BAR} Model {_SINGLE_BAR}")
    print(f"  {config.name} | {resp.latency_ms:,.0f}ms | {tokens} | {cost}")


def main() -> None:
    """Entry point for the scenario inspector CLI."""
    parser = argparse.ArgumentParser(
        description="Inspect a single scenario through a single model with diagnostic output."
    )
    parser.add_argument(
        "--scenario",
        required=True,
        metavar="ID",
        help="Scenario ID (e.g., SC-001, QR-005)",
    )
    parser.add_argument(
        "--model",
        default=None,
        metavar="NAME",
        help="Model name from config/models.yaml (default: first ceiling model)",
    )
    parser.add_argument(
        "--rag",
        action="store_true",
        help="Enable RAG retrieval for context",
    )
    parser.add_argument(
        "--step",
        type=int,
        default=None,
        metavar="N",
        help="Run only step N (routing scenarios only)",
    )
    parser.add_argument(
        "--show-prompt",
        action="store_true",
        help="Print the full prompt sent to the model",
    )
    parser.add_argument(
        "--prompt-only",
        action="store_true",
        help="Print the prompt without calling the model (no API cost)",
    )
    args = parser.parse_args()

    scenario = find_scenario(args.scenario)
    config = resolve_model(args.model)

    # Validate --step for routing scenarios
    if args.step is not None:
        if isinstance(scenario, QueryScenario):
            print("Warning: --step is ignored for query scenarios", file=sys.stderr)
        elif args.step < 1 or args.step > len(scenario.steps):
            sys.exit(
                f"Error: --step {args.step} out of range (scenario has {len(scenario.steps)} steps)"
            )

    # Header
    rag_label = "on" if args.rag else "off"
    mode_label = " (prompt-only)" if args.prompt_only else ""
    print(f"Scenario: {scenario.scenario_id}")
    print(f"Model:    {config.name}{mode_label}")
    print(f"RAG:      {rag_label}")

    # RAG retriever
    retriever: RagRetriever | None = None
    if args.rag:
        rag_settings = load_rag_settings()
        index_path = _PROJECT_ROOT / rag_settings.index_path
        try:
            retriever = RagRetriever(
                index_path,
                top_k=rag_settings.top_k,
                similarity_threshold=rag_settings.similarity_threshold,
            )
        except Exception as exc:
            sys.exit(f"Error: could not load RAG index at {index_path}: {exc}")

    # Adapter and engine (skip for prompt-only)
    adapter = None
    engine: PredictionEngine | None = None
    if not args.prompt_only:
        adapter = create_adapter(config)
        engine = PredictionEngine(adapter)

    # Validate ground truth for routing scenarios
    if isinstance(scenario, Scenario):
        _validate_ground_truth(scenario)

    try:
        if isinstance(scenario, QueryScenario):
            run_query_scenario(
                scenario,
                engine,
                config,
                rag_retriever=retriever,
                show_prompt=args.show_prompt,
                prompt_only=args.prompt_only,
            )
        else:
            run_routing_steps(
                scenario,
                engine,
                config,
                rag_retriever=retriever,
                step_filter=args.step,
                show_prompt=args.show_prompt,
                prompt_only=args.prompt_only,
            )
    finally:
        if adapter is not None:
            adapter.close()


if __name__ == "__main__":
    main()
