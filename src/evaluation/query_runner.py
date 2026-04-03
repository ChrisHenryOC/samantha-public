"""CLI entry point for the query evaluation harness.

Usage::

    uv run python -m src.evaluation.query_runner [options]

Options::

    --models PATH       Path to models.yaml (default: config/models.yaml)
    --settings PATH     Path to settings.yaml (default: config/settings.yaml)
    --scenarios PATH    Path to query scenarios directory (default: scenarios/query)
    --output PATH       Override output directory from settings
    --model NAME        Filter to specific model name (repeatable)
    --runs N            Override runs_per_model for all providers
    --cloud-runs N      Override runs for openrouter provider
    --local-runs N      Override runs for llamacpp provider
    --limit N           Limit number of scenarios to run
    --tier T [T ...]    Filter to specific tier(s): 1, 2, 3, ceiling, all
    --parallel          Run cloud models concurrently (local models stay sequential)
    --max-workers N     Max concurrent cloud models in parallel mode (default: 4)
    --dry-run           Validate config and print plan without running
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from src.evaluation.harness import DEFAULT_MAX_WORKERS, LOCAL_PROVIDERS, load_openrouter_key
from src.evaluation.query_harness import QueryEvaluationHarness
from src.evaluation.query_metrics import QueryResult, compute_query_model_metrics
from src.evaluation.reporter import (
    print_query_summary_table,
    print_tool_use_summary_table,
    write_query_run_results,
    write_query_summary_report,
    write_tool_use_run_results,
    write_tool_use_summary_report,
)
from src.evaluation.tool_use_harness import ToolUseQueryHarness
from src.evaluation.tool_use_metrics import compute_tool_use_metrics
from src.models.config import (
    EvaluationSettings,
    ModelConfig,
    load_models,
    load_rag_settings,
    load_settings,
    validate_config_consistency,
)
from src.simulator.loader import load_all_query_scenarios
from src.simulator.schema import QueryScenario

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_MAX_WRITE_FAILURES = 2


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Run the query evaluation harness against configured models.",
    )
    parser.add_argument(
        "--models",
        type=Path,
        default=None,
        help="Path to models.yaml (default: config/models.yaml)",
    )
    parser.add_argument(
        "--settings",
        type=Path,
        default=None,
        help="Path to settings.yaml (default: config/settings.yaml)",
    )
    parser.add_argument(
        "--scenarios",
        type=Path,
        default=None,
        help="Path to query scenarios directory (default: scenarios/query)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Override output directory",
    )
    parser.add_argument(
        "--model",
        action="append",
        dest="model_filter",
        default=None,
        help="Filter to specific model name (repeatable)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=None,
        help="Override runs_per_model for all providers",
    )
    parser.add_argument(
        "--cloud-runs",
        type=int,
        default=None,
        help="Override runs for openrouter provider",
    )
    parser.add_argument(
        "--local-runs",
        type=int,
        default=None,
        help="Override runs for llamacpp provider",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of scenarios to run",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate config and print plan without running",
    )
    parser.add_argument(
        "--mode",
        choices=["full_context", "rag", "tool_use"],
        default="full_context",
        help="Context mode: full_context (default), rag, or tool_use",
    )
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Run cloud models concurrently (local models stay sequential)",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=None,
        help="Max concurrent cloud models in parallel mode (default: 4)",
    )
    parser.add_argument(
        "--tier",
        nargs="+",
        default=None,
        choices=["1", "2", "3", "ceiling", "all"],
        help="Filter to specific tier(s): 1, 2, 3, ceiling, or all (repeatable)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # Load configuration
    try:
        models = load_models(args.models)
        settings = load_settings(args.settings)
        validate_config_consistency(models, settings)
    except Exception as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    # Validate numeric args
    for name, value in [
        ("--runs", args.runs),
        ("--cloud-runs", args.cloud_runs),
        ("--local-runs", args.local_runs),
        ("--limit", args.limit),
        ("--max-workers", args.max_workers),
    ]:
        if value is not None and value <= 0:
            print(f"{name} must be a positive integer", file=sys.stderr)
            return 1

    # Apply run-count overrides
    if args.runs is not None or args.cloud_runs is not None or args.local_runs is not None:
        if args.runs is not None:
            runs_per_model = {provider: args.runs for provider in settings.runs_per_model}
        else:
            runs_per_model = dict(settings.runs_per_model)

        if args.cloud_runs is not None:
            if "openrouter" not in runs_per_model:
                print("--cloud-runs requires openrouter provider in config", file=sys.stderr)
                return 1
            runs_per_model["openrouter"] = args.cloud_runs
        if args.local_runs is not None:
            if "llamacpp" not in runs_per_model:
                print("--local-runs requires llamacpp provider in config", file=sys.stderr)
                return 1
            runs_per_model["llamacpp"] = args.local_runs

        settings = EvaluationSettings(
            runs_per_model=runs_per_model,
            timeout_seconds=settings.timeout_seconds,
            output_directory=settings.output_directory,
        )

        # CLI run-count flags take precedence over per-model config.runs.
        # Clear config.runs on affected models so the CLI value wins.
        if args.runs is not None:
            models = [replace(m, runs=None) for m in models]
        else:
            affected_providers = {
                p
                for p, flag in [("openrouter", args.cloud_runs), ("llamacpp", args.local_runs)]
                if flag is not None
            }
            models = [
                replace(m, runs=None) if m.provider in affected_providers else m for m in models
            ]

    # Filter models by name
    if args.model_filter:
        names = set(args.model_filter)
        models = [m for m in models if m.name in names]
        if not models:
            print(f"No models match filter: {args.model_filter}", file=sys.stderr)
            return 1

    # Filter models by tier
    if args.tier and "all" not in args.tier:
        tiers = set(args.tier)
        no_tier = [m.name for m in models if m.tier is None]
        if no_tier:
            print(
                f"Warning: {len(no_tier)} model(s) have no tier and will be excluded "
                f"from --tier filter: {', '.join(no_tier)}",
                file=sys.stderr,
            )
        models = [m for m in models if m.tier is not None and m.tier in tiers]
        if not models:
            if args.model_filter:
                print(
                    f"No models match combined filters: "
                    f"--model {args.model_filter} --tier {args.tier}",
                    file=sys.stderr,
                )
            else:
                print(f"No models match tier filter: {args.tier}", file=sys.stderr)
            return 1

    # Load query scenarios
    scenario_dir = args.scenarios or (_PROJECT_ROOT / "scenarios" / "query")
    try:
        scenarios = load_all_query_scenarios(scenario_dir)
    except Exception as exc:
        print(f"Scenario error: {exc}", file=sys.stderr)
        return 1

    if not scenarios:
        print(f"No query scenarios found in {scenario_dir}", file=sys.stderr)
        return 1

    # Apply --limit
    if args.limit is not None:
        scenarios = scenarios[: args.limit]

    # Determine output directory
    if args.output:
        output_dir = args.output
    elif args.mode == "rag":
        output_dir = _PROJECT_ROOT / "results" / "query_rag"
    elif args.mode == "tool_use":
        output_dir = _PROJECT_ROOT / "results" / "query_tool_use"
    else:
        output_dir = _PROJECT_ROOT / "results" / "query_baseline"

    # Initialize RAG retriever if mode=rag
    rag_retriever = None
    if args.mode == "rag":
        from src.rag.retriever import RagRetriever

        rag_cfg = load_rag_settings(args.settings)
        index_path = _PROJECT_ROOT / rag_cfg.index_path
        if not index_path.exists():
            print(
                "RAG index not found. Run ./scripts/build_rag_index.sh first.",
                file=sys.stderr,
            )
            return 1
        try:
            rag_retriever = RagRetriever(
                index_path,
                knowledge_base_path=_PROJECT_ROOT / "knowledge_base",
                top_k=rag_cfg.top_k,
                similarity_threshold=rag_cfg.similarity_threshold,
            )
        except Exception as exc:
            print(f"RAG initialization failed: {exc}", file=sys.stderr)
            return 1
        print(f"RAG mode enabled (index: {index_path})")

    # Dry run
    if args.dry_run:
        _print_plan(
            models,
            settings,
            scenarios,
            output_dir,
            parallel=args.parallel,
            max_workers=args.max_workers,
        )
        return 0

    # Pre-flight rate limit check for cloud models
    has_cloud = any(m.provider not in LOCAL_PROVIDERS for m in models)
    if has_cloud:
        from src.models.openrouter_adapter import check_rate_limit

        try:
            api_key = load_openrouter_key()
        except (ValueError, OSError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

        try:
            rate_info = check_rate_limit(api_key)
            if rate_info.requests_per_interval is not None:
                label = rate_info.label[:80]
                print(
                    f"OpenRouter rate limit: {rate_info.requests_per_interval} requests"
                    f" / {rate_info.interval_seconds}s (key label: {label})"
                )
                # Estimate total API calls (1 call per scenario per run)
                total_calls = 0
                for m in models:
                    if m.provider not in LOCAL_PROVIDERS:
                        runs = (
                            m.runs
                            if m.runs is not None
                            else settings.runs_per_model.get(m.provider, 1)
                        )
                        total_calls += runs * len(scenarios)
                print(f"Planned API calls: {total_calls}")
                if rate_info.interval_seconds and rate_info.requests_per_interval and args.parallel:
                    rate_per_second = rate_info.requests_per_interval / rate_info.interval_seconds
                    cloud_count = sum(1 for m in models if m.provider not in LOCAL_PROVIDERS)
                    effective_workers = min(args.max_workers or DEFAULT_MAX_WORKERS, cloud_count)
                    if effective_workers > rate_per_second:
                        print(
                            f"WARNING: {effective_workers} concurrent workers may exceed "
                            f"rate limit of {rate_info.requests_per_interval} req/"
                            f"{rate_info.interval_seconds}s.",
                            file=sys.stderr,
                        )
            else:
                print(f"OpenRouter rate limit: {rate_info.label}")
        except Exception as exc:
            print(
                f"Warning: Could not check rate limit ({type(exc).__name__}): {exc}",
                file=sys.stderr,
            )

    # Run evaluation
    started_at = datetime.now()
    db_path = output_dir / "evaluation.db"
    output_dir.mkdir(parents=True, exist_ok=True)

    all_results: list[QueryResult] = []
    write_failures: list[tuple[str, int, str]] = []

    def _make_timestamps() -> dict[str, str]:
        return {
            "started_at": started_at.isoformat(),
            "completed_at": datetime.now().isoformat(),
        }

    def _on_run_complete(
        model_id: str,
        run_number: int,
        run_results: list[QueryResult],
        aborted: bool,
    ) -> None:
        if not aborted:
            all_results.extend(run_results)
        write_fn = (
            write_tool_use_run_results if args.mode == "tool_use" else write_query_run_results
        )
        try:
            write_fn(
                output_dir,
                model_id,
                run_number,
                run_results,
                _make_timestamps(),
                total_scenarios=len(scenarios),
                aborted=aborted,
            )
        except OSError as exc:
            write_failures.append((model_id, run_number, str(exc)))
            print(
                f"Warning: Failed to write results for {model_id} run {run_number}: {exc}",
                file=sys.stderr,
            )
            if len(write_failures) >= _MAX_WRITE_FAILURES:
                raise OSError(
                    f"Aborting: {len(write_failures)} cumulative write failures. "
                    f"Check disk space and permissions for {output_dir}"
                ) from exc

    if args.mode == "tool_use":
        harness: QueryEvaluationHarness | ToolUseQueryHarness = ToolUseQueryHarness(
            models, settings, scenarios, db_path
        )
        print(
            f"Running tool-use query evaluation: "
            f"{len(models)} model(s), {len(scenarios)} scenario(s)"
        )
    else:
        harness = QueryEvaluationHarness(
            models, settings, scenarios, db_path, rag_retriever=rag_retriever
        )
        print(f"Running query evaluation: {len(models)} model(s), {len(scenarios)} scenario(s)")

    try:
        harness.run_all(
            on_run_complete=_on_run_complete,
            parallel=args.parallel,
            max_workers=args.max_workers,
        )
    except Exception as exc:
        print(f"Evaluation failed: {exc}", file=sys.stderr)
        print(f"Partial results may be in database: {db_path}", file=sys.stderr)
        return 1

    completed_at = datetime.now()
    timestamps = _make_timestamps()

    # Compute and write metrics — only for models that have results
    # (aborted models may have zero results if all runs were aborted)
    model_ids = list(dict.fromkeys(r.model_id for r in all_results))
    if args.mode == "tool_use":
        tool_use_metrics = [compute_tool_use_metrics(mid, all_results) for mid in model_ids]
        all_metrics = [m.standard for m in tool_use_metrics]
    else:
        all_metrics = [compute_query_model_metrics(mid, all_results) for mid in model_ids]
    summary_failed = False
    if args.mode == "tool_use":
        try:
            write_tool_use_summary_report(output_dir, tool_use_metrics, timestamps)
        except Exception as exc:
            print(f"Warning: Failed to write tool-use summary report: {exc}", file=sys.stderr)
            summary_failed = True
    else:
        try:
            write_query_summary_report(output_dir, all_metrics, timestamps)
        except Exception as exc:
            print(f"Warning: Failed to write summary report: {exc}", file=sys.stderr)
            summary_failed = True

    # Print summary
    if args.mode == "tool_use":
        print_tool_use_summary_table(tool_use_metrics)
    else:
        print_query_summary_table(all_metrics)

    elapsed = (completed_at - started_at).total_seconds()
    print(f"Query evaluation complete in {elapsed:.1f}s. Results in {output_dir}")

    if write_failures:
        print(
            f"\n{len(write_failures)} run(s) failed to write JSON output:",
            file=sys.stderr,
        )
        for model_id, run_number, error in write_failures:
            print(f"  - {model_id} run {run_number}: {error}", file=sys.stderr)
        return 1

    if summary_failed:
        return 1

    return 0


def _print_plan(
    models: list[ModelConfig],
    settings: EvaluationSettings,
    scenarios: list[QueryScenario],
    output_dir: Path,
    *,
    parallel: bool = False,
    max_workers: int | None = None,
) -> None:
    """Print the evaluation plan without executing."""
    print("Query Evaluation Plan (dry run)")
    print("=" * 40)
    print(f"Output directory: {output_dir}")
    print(f"Query scenarios: {len(scenarios)}")
    if parallel:
        effective = max_workers or DEFAULT_MAX_WORKERS
        cloud_count = sum(1 for m in models if m.provider not in LOCAL_PROVIDERS)
        capped = min(effective, cloud_count) if cloud_count else 0
        print(f"Parallel: yes (max workers: {capped})")
    print()

    total_predictions = 0
    for m in models:
        runs = m.runs if m.runs is not None else settings.runs_per_model.get(m.provider, 1)
        predictions = runs * len(scenarios)
        total_predictions += predictions
        tier_label = f", tier={m.tier}" if m.tier is not None else ""
        print(f"  {m.name} ({m.provider}/{m.model_id}{tier_label})")
        print(
            f"    Runs: {runs}, Scenarios per run: {len(scenarios)}, "
            f"Total predictions: {predictions}"
        )

    print()
    print(f"Total predictions: {total_predictions}")

    # Tier breakdown
    tiers: dict[int, int] = {}
    for s in scenarios:
        tiers[s.tier] = tiers.get(s.tier, 0) + 1
    print("\nScenarios by tier:")
    for tier, count in sorted(tiers.items()):
        print(f"  Tier {tier}: {count}")

    # Answer type breakdown
    answer_types: dict[str, int] = {}
    for s in scenarios:
        at = s.expected_output.answer_type
        answer_types[at] = answer_types.get(at, 0) + 1
    print("\nScenarios by answer type:")
    for at, count in sorted(answer_types.items()):
        print(f"  {at}: {count}")


if __name__ == "__main__":
    sys.exit(main())
