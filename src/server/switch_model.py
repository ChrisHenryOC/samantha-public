"""CLI to swap the local model running on llama-server.

Usage:
    uv run python -m src.server.switch_model <model-name>
    uv run python -m src.server.switch_model --list
    uv run python -m src.server.switch_model --stop
"""

from __future__ import annotations

import argparse
import sys

from src.server.model_manager import (
    load_local_models,
    stop_server,
    switch_model,
)


def main(argv: list[str] | None = None) -> int:
    """Entry point for the model-swap CLI."""
    parser = argparse.ArgumentParser(
        description="Swap the local model running on llama-server.",
    )
    parser.add_argument(
        "model",
        nargs="?",
        help="Model name to switch to (from config/models.yaml)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_models",
        help="List available local models",
    )
    parser.add_argument(
        "--stop",
        action="store_true",
        help="Stop the running llama-server without starting a new one",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for llama-server (default: 8080)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120,
        help="Seconds to wait for server readiness (default: 120)",
    )
    args = parser.parse_args(argv)

    if args.list_models:
        models = load_local_models()
        if not models:
            print("No local models configured in config/models.yaml")
            return 1
        print("Available local models:")
        for m in models:
            print(f"  {m.name:<30}  {m.hf_repo}")
        return 0

    if args.stop:
        if stop_server():
            print("llama-server stopped.")
        else:
            print("No llama-server was running.")
        return 0

    if not args.model:
        parser.print_help()
        return 1

    print(f"Switching to model: {args.model}")

    try:
        ready = switch_model(
            args.model,
            port=args.port,
            timeout=args.timeout,
        )
    except (ValueError, FileNotFoundError, RuntimeError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if ready:
        print(f"llama-server is ready with {args.model} on port {args.port}")
        return 0
    else:
        print(f"Error: llama-server did not become ready within {args.timeout}s", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
