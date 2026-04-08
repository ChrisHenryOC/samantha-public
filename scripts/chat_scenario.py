"""Interactive scenario chat: load a scenario and converse with a model about it.

Usage:
    uv run python scripts/chat_scenario.py --scenario SC-001 --model "Llama 3.1 8B"
    uv run python scripts/chat_scenario.py --scenario SC-001 --model "Llama 3.1 8B" --step 2
    uv run python scripts/chat_scenario.py --scenario QR-005 --model "Claude Sonnet 4.6" --rag
"""

from __future__ import annotations

import argparse
import json
import sys
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
from src.models.base import ChatMessage, ChatRole  # noqa: E402
from src.models.config import ModelConfig, load_models, load_rag_settings  # noqa: E402
from src.models.llamacpp_adapter import LlamaCppAdapter  # noqa: E402
from src.models.openrouter_adapter import OpenRouterAdapter  # noqa: E402
from src.prediction.prompt_template import render_prompt  # noqa: E402
from src.prediction.query_prompt_template import render_query_prompt  # noqa: E402
from src.rag.retriever import RagRetriever  # noqa: E402
from src.simulator.loader import load_query_scenario, load_scenario  # noqa: E402
from src.simulator.schema import QueryScenario, Scenario  # noqa: E402

_SCENARIOS_DIR = _PROJECT_ROOT / "scenarios"

# Display constants
_DOUBLE_BAR = "\u2550" * 3  # ═══
_SINGLE_BAR = "\u2500" * 2  # ──

_CHAT_SYSTEM_PREFIX = (
    "You are a laboratory workflow expert. The user wants to discuss "
    "a scenario with you. Answer questions conversationally and explain "
    "your reasoning. Do not respond with JSON unless the user asks for it.\n\n"
    "--- SCENARIO CONTEXT ---\n\n"
)


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


def _build_routing_context(
    scenario: Scenario,
    step_num: int,
    *,
    rag_retriever: RagRetriever | None,
) -> tuple[str, str]:
    """Build system context and summary for a routing scenario step.

    Returns (system_context, summary_text).
    """
    order = None
    slides: list[Any] = []
    target_step = None

    for idx, step in enumerate(scenario.steps):
        if order is None:
            order = build_order_from_event_data(scenario.scenario_id, step.event_data)
            slides = build_slides_for_order(order)
        else:
            prev_step = scenario.steps[idx - 1]
            order = advance_order_state(order, prev_step.expected_output)
            slides = advance_slides_state(slides, prev_step)

        if step.step == step_num:
            target_step = step
            break

    if target_step is None or order is None:
        sys.exit(f"Error: step {step_num} not found in scenario {scenario.scenario_id}")

    event = build_event(order.order_id, target_step)

    # RAG chunks
    rag_context = None
    if rag_retriever is not None:
        try:
            chunks, _info = rag_retriever.retrieve_for_routing(
                order.current_state, event.event_type, event.event_data
            )
            rag_context = chunks
        except Exception as exc:
            sys.exit(f"Error: RAG retrieval failed: {exc}")

    prompt = render_prompt(order, slides, event, rag_context=rag_context)

    # Summary for display
    expected = target_step.expected_output
    summary_lines = [
        f"\n{_DOUBLE_BAR} {scenario.scenario_id} Step {step_num}/{len(scenario.steps)}: "
        f"{target_step.event_type} {_DOUBLE_BAR}",
        scenario.description,
        f"\n{_SINGLE_BAR} Event Data {_SINGLE_BAR}",
        json.dumps(target_step.event_data, indent=2),
        f"\n{_SINGLE_BAR} Ground Truth {_SINGLE_BAR}",
        f"  next_state:     {expected.next_state}",
        f"  applied_rules:  {list(expected.applied_rules)}",
        f"  flags:          {list(expected.flags)}",
    ]
    summary = "\n".join(summary_lines)

    system_context = _CHAT_SYSTEM_PREFIX + prompt
    return system_context, summary


def _build_query_context(
    scenario: QueryScenario,
    *,
    rag_retriever: RagRetriever | None,
) -> tuple[str, str]:
    """Build system context and summary for a query scenario.

    Returns (system_context, summary_text).
    """
    rag_context = None
    if rag_retriever is not None:
        try:
            chunks, _info = rag_retriever.retrieve_for_query(scenario.query)
            rag_context = chunks
        except Exception as exc:
            sys.exit(f"Error: RAG retrieval failed: {exc}")

    prompt = render_query_prompt(scenario, rag_context=rag_context)

    # Summary for display
    expected = scenario.expected_output
    summary_lines = [
        f"\n{_DOUBLE_BAR} {scenario.scenario_id}: query {_DOUBLE_BAR}",
        scenario.description,
        f"\n{_SINGLE_BAR} Query {_SINGLE_BAR}",
        f"  {scenario.query}",
        f"\n{_SINGLE_BAR} Database State {_SINGLE_BAR}",
        f"  Orders: {len(scenario.database_state.orders)}",
        f"  Slides: {len(scenario.database_state.slides)}",
        f"\n{_SINGLE_BAR} Ground Truth {_SINGLE_BAR}",
        f"  answer_type:  {expected.answer_type}",
    ]
    if expected.order_ids:
        summary_lines.append(f"  order_ids:    {list(expected.order_ids)}")
    summary_lines.append(f"  reasoning:    {expected.reasoning}")
    summary = "\n".join(summary_lines)

    system_context = _CHAT_SYSTEM_PREFIX + prompt
    return system_context, summary


def _send_chat(
    adapter: LlamaCppAdapter | OpenRouterAdapter,
    messages: list[dict[str, str]],
) -> str:
    """Send a multi-turn chat request and return the assistant's reply text.

    Uses the adapter's public ``chat()`` method for proper error handling
    and response normalization.
    """
    chat_messages = [
        ChatMessage(role=ChatRole(m["role"]), content=m.get("content")) for m in messages
    ]
    result = adapter.chat(chat_messages)
    if result.error:
        return f"[Error: {result.error}]"
    return result.message.content or ""


def _print_help() -> None:
    """Print available REPL commands."""
    print("\nCommands:")
    print("  quit / exit   end session")
    print("  context       reprint scenario summary")
    print("  history       show conversation history")
    print("  clear         clear conversation (keep context)")
    print("  step N        switch to step N (routing only)")
    print("  help          show this message")
    print()


def chat_loop(
    adapter: LlamaCppAdapter | OpenRouterAdapter,
    system_context: str,
    summary: str,
    config: ModelConfig,
    *,
    scenario: Scenario | QueryScenario,
    rag_retriever: RagRetriever | None,
) -> None:
    """Run the interactive chat loop."""
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_context},
    ]

    print(f"\nChatting with {config.name}. Type 'help' for commands, 'quit' to exit.\n")

    while True:
        try:
            user_input = input("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            continue

        cmd = user_input.lower()

        if cmd in ("quit", "exit"):
            break

        if cmd == "help":
            _print_help()
            continue

        if cmd == "context":
            print(f"\n{summary}\n")
            continue

        if cmd == "history":
            turn = 0
            for msg in messages[1:]:
                if msg["role"] == "user":
                    turn += 1
                    print(f"\n[{turn}] You> {msg['content']}")
                else:
                    print(f"[{turn}] Model> {msg['content']}")
            if turn == 0:
                print("  (no conversation history)")
            print()
            continue

        if cmd == "clear":
            messages[:] = [messages[0]]
            print("  Conversation cleared.\n")
            continue

        # Handle "step N" command for routing scenarios
        if cmd.startswith("step "):
            if isinstance(scenario, QueryScenario):
                print("  'step' is not available for query scenarios.\n")
                continue
            parts = cmd.split()
            if len(parts) != 2 or not parts[1].isdigit():
                print("  Usage: step N\n")
                continue
            new_step = int(parts[1])
            if new_step < 1 or new_step > len(scenario.steps):
                print(f"  Step out of range (1-{len(scenario.steps)}).\n")
                continue
            system_context, summary = _build_routing_context(
                scenario, new_step, rag_retriever=rag_retriever
            )
            messages[:] = [{"role": "system", "content": system_context}]
            print(summary)
            print(f"\n  Switched to step {new_step}. Conversation cleared.\n")
            continue

        # Send to model
        messages.append({"role": "user", "content": user_input})
        try:
            reply = _send_chat(adapter, messages)
        except Exception as exc:
            print(f"\n  Error: {exc}\n")
            messages.pop()
            continue

        if not reply:
            print("\n  (model returned empty response)\n")
            messages.pop()
            continue

        print(f"\n{reply}\n")
        messages.append({"role": "assistant", "content": reply})


def main() -> None:
    """Entry point for the scenario chat CLI."""
    parser = argparse.ArgumentParser(
        description="Load a scenario and chat interactively with a model about it."
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
        help="Step to chat about (routing scenarios only, default: 1)",
    )
    args = parser.parse_args()

    scenario = find_scenario(args.scenario)
    config = resolve_model(args.model)

    # Validate --step
    if args.step is not None and isinstance(scenario, QueryScenario):
        print("Warning: --step is ignored for query scenarios", file=sys.stderr)

    step_num = args.step or 1
    if isinstance(scenario, Scenario) and (step_num < 1 or step_num > len(scenario.steps)):
        sys.exit(
            f"Error: --step {step_num} out of range (scenario has {len(scenario.steps)} steps)"
        )

    # Header
    rag_label = "on" if args.rag else "off"
    print(f"Scenario: {scenario.scenario_id}")
    print(f"Model:    {config.name}")
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

    # Build context
    if isinstance(scenario, QueryScenario):
        system_context, summary = _build_query_context(scenario, rag_retriever=retriever)
    else:
        system_context, summary = _build_routing_context(
            scenario, step_num, rag_retriever=retriever
        )

    # Print scenario summary
    print(summary)

    # Create adapter and start chat
    adapter = create_adapter(config)
    try:
        chat_loop(
            adapter,
            system_context,
            summary,
            config,
            scenario=scenario,
            rag_retriever=retriever,
        )
    finally:
        adapter.close()


if __name__ == "__main__":
    main()
