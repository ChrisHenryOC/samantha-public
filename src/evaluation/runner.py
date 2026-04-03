"""CLI entry point for the evaluation harness.

Usage::

    uv run python -m src.evaluation.runner [options]

Options::

    --models PATH       Path to models.yaml (default: config/models.yaml)
    --settings PATH     Path to settings.yaml (default: config/settings.yaml)
    --scenarios PATH    Path to scenarios directory (default: scenarios/)
    --output PATH       Override output directory from settings
    --model NAME        Filter to specific model name (repeatable)
    --category CAT      Filter to specific category (repeatable)
    --runs N            Override runs_per_model for all providers
    --cloud-runs N      Override runs for openrouter provider
    --local-runs N      Override runs for llamacpp provider
    --limit N           Limit number of scenarios to run
    --tier T [T ...]    Filter to specific tier(s): 1, 2, 3, ceiling, all
    --max-workers N     Max concurrent cloud models in parallel mode (default: 4)
    --dry-run           Validate config and print plan without running
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from src.evaluation.harness import (
    DEFAULT_MAX_WORKERS,
    LOCAL_PROVIDERS,
    EvaluationHarness,
    load_openrouter_key,
)
from src.evaluation.metrics import ScenarioResult, compute_model_metrics
from src.evaluation.reporter import (
    print_summary_table,
    write_run_results,
    write_summary_report,
)
from src.models.config import (
    EvaluationSettings,
    ModelConfig,
    load_models,
    load_rag_settings,
    load_settings,
    validate_config_consistency,
)
from src.prediction.prompt_template import VALID_PROMPT_EXTRAS
from src.simulator.loader import load_scenario
from src.simulator.schema import Scenario

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Run the evaluation harness against configured models and scenarios.",
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
        help="Path to scenarios directory (default: scenarios/)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Override output directory from settings",
    )
    parser.add_argument(
        "--model",
        action="append",
        dest="model_filter",
        default=None,
        help="Filter to specific model name (repeatable)",
    )
    parser.add_argument(
        "--category",
        action="append",
        dest="category_filter",
        default=None,
        help="Filter to specific category (repeatable)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=None,
        help="Override runs_per_model for all providers (e.g., --runs 1 for smoke test)",
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
        "--scenario-ids",
        type=str,
        default=None,
        help="Comma-separated scenario IDs to run (e.g., SC-001,SC-005,SC-010)",
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
        choices=["full_context", "rag"],
        default="full_context",
        help="Context mode: full_context (default) or rag",
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
    parser.add_argument(
        "--prompt-extras",
        type=str,
        default=None,
        help=(
            "Comma-separated prompt sections to add: "
            "state_sequence, retry_clarification, few_shot, skills"
        ),
    )
    return parser


def _load_routing_scenarios(scenario_dir: Path) -> list[Scenario]:
    """Load routing scenarios, skipping the query/ subdirectory."""
    all_scenarios: list[Scenario] = []
    for subdir in sorted(scenario_dir.iterdir()):
        if not subdir.is_dir():
            continue
        if subdir.name == "query":
            continue
        for json_path in sorted(subdir.rglob("*.json")):
            all_scenarios.append(load_scenario(json_path))
    all_scenarios.sort(key=lambda s: s.scenario_id)
    return all_scenarios


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # Validate path arguments resolve within the project root
    for arg_name, path_value in [
        ("--models", args.models),
        ("--settings", args.settings),
        ("--scenarios", args.scenarios),
    ]:
        if path_value is not None:
            resolved = path_value.resolve()
            if not resolved.is_relative_to(_PROJECT_ROOT):
                print(
                    f"{arg_name} must resolve within the project root, got {path_value}",
                    file=sys.stderr,
                )
                return 1

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

    # Parse and validate --prompt-extras
    prompt_extras: frozenset[str] = frozenset()
    if args.prompt_extras is not None:
        extras = frozenset(s.strip() for s in args.prompt_extras.split(",") if s.strip())
        invalid = extras - VALID_PROMPT_EXTRAS
        if invalid:
            print(
                f"Invalid --prompt-extras: {sorted(invalid)}. "
                f"Valid options: {sorted(VALID_PROMPT_EXTRAS)}",
                file=sys.stderr,
            )
            return 1
        prompt_extras = extras

    # Apply run-count overrides: --runs sets a base, then --cloud-runs and
    # --local-runs refine specific providers.  Provider validation happens
    # *after* --runs creates its base dict so that --runs + --cloud-runs
    # works even when the original config lacks openrouter.
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
            has_local = any(p in runs_per_model for p in LOCAL_PROVIDERS)
            if not has_local:
                print("--local-runs requires a local provider in config", file=sys.stderr)
                return 1
            for p in LOCAL_PROVIDERS:
                if p in runs_per_model:
                    runs_per_model[p] = args.local_runs

        settings = replace(settings, runs_per_model=runs_per_model)

        # CLI run-count flags take precedence over per-model config.runs.
        # Clear config.runs on affected models so the CLI value wins.
        if args.runs is not None:
            models = [replace(m, runs=None) for m in models]
        else:
            affected_providers: set[str] = set()
            if args.cloud_runs is not None:
                affected_providers.add("openrouter")
            if args.local_runs is not None:
                affected_providers.update(LOCAL_PROVIDERS)
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
                f"from --tier filter: {no_tier}",
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

    # Determine output directory (before scenario loading to fail fast)
    if args.output:
        resolved_output = args.output.resolve()
        if not resolved_output.is_relative_to(_PROJECT_ROOT):
            print(
                f"--output must resolve within the project root, got {args.output}",
                file=sys.stderr,
            )
            return 1
        output_dir = resolved_output
    elif args.mode == "rag":
        output_dir = _PROJECT_ROOT / "results" / "routing_rag"
    else:
        output_dir = _PROJECT_ROOT / settings.output_directory

    # Load routing scenarios (exclude query/ directory which has a different schema)
    scenario_dir = args.scenarios or (_PROJECT_ROOT / "scenarios")
    try:
        scenarios = _load_routing_scenarios(scenario_dir)
    except Exception as exc:
        print(f"Scenario error: {exc}", file=sys.stderr)
        return 1

    if not scenarios:
        print(f"No scenarios found in {scenario_dir}", file=sys.stderr)
        return 1

    # Filter categories
    if args.category_filter:
        cats = set(args.category_filter)
        scenarios = [s for s in scenarios if s.category in cats]
        if not scenarios:
            print(f"No scenarios match category filter: {args.category_filter}", file=sys.stderr)
            return 1

    # Filter by specific scenario IDs
    if args.scenario_ids:
        ids = {s.strip() for s in args.scenario_ids.split(",")}
        matched = {s.scenario_id for s in scenarios} & ids
        unmatched = ids - matched
        if unmatched:
            print(
                f"Warning: scenario IDs not found: {sorted(unmatched)}",
                file=sys.stderr,
            )
        scenarios = [s for s in scenarios if s.scenario_id in ids]
        if not scenarios:
            print(f"No scenarios match ID filter: {args.scenario_ids}", file=sys.stderr)
            return 1

    # Apply --limit after all filtering
    if args.limit is not None:
        scenarios = scenarios[: args.limit]

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

    # Dry run: print plan and exit
    if args.dry_run:
        _print_plan(
            models,
            settings,
            scenarios,
            output_dir,
            parallel=args.parallel,
            max_workers=args.max_workers,
            prompt_extras=prompt_extras,
        )
        return 0

    # Pre-flight rate limit check for OpenRouter models
    has_openrouter = any(m.provider == "openrouter" for m in models)
    if has_openrouter:
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
                # Estimate total API calls for this run
                total_steps = sum(len(s.steps) for s in scenarios)
                total_calls = 0
                for m in models:
                    if m.provider == "openrouter":
                        runs = (
                            m.runs
                            if m.runs is not None
                            else settings.runs_per_model.get(m.provider, 1)
                        )
                        total_calls += runs * total_steps
                print(f"Planned API calls: {total_calls}")
                if rate_info.interval_seconds and rate_info.requests_per_interval and args.parallel:
                    rate_per_second = rate_info.requests_per_interval / rate_info.interval_seconds
                    cloud_count = sum(1 for m in models if m.provider == "openrouter")
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

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"Cannot create output directory '{output_dir}': {exc}", file=sys.stderr)
        return 1

    # Incremental write callback — writes JSON after each run completes
    all_results: list[ScenarioResult] = []
    write_failures: list[tuple[str, int, str]] = []

    def _make_timestamps() -> dict[str, str]:
        return {
            "started_at": started_at.isoformat(),
            "completed_at": datetime.now().isoformat(),
        }

    def _on_run_complete(
        model_id: str,
        run_number: int,
        run_results: list[ScenarioResult],
        aborted: bool,
    ) -> None:
        if not aborted:
            all_results.extend(run_results)
        try:
            write_run_results(
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
            # Abort early on repeated write failures — likely a persistent
            # issue (disk full, permission denied) that won't resolve itself.
            if len(write_failures) >= 2:
                raise OSError(
                    f"Aborting: {len(write_failures)} write failures. "
                    f"Check disk space and permissions for {output_dir}"
                ) from exc

    harness = EvaluationHarness(
        models,
        settings,
        scenarios,
        db_path,
        rag_retriever=rag_retriever,
        prompt_extras=prompt_extras,
    )
    extras_label = f", prompt extras: {', '.join(sorted(prompt_extras))}" if prompt_extras else ""
    print(f"Running evaluation: {len(models)} model(s), {len(scenarios)} scenario(s){extras_label}")

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

    # Compute and write metrics
    model_ids = list(dict.fromkeys(m.model_id for m in models))
    all_metrics = [compute_model_metrics(mid, all_results) for mid in model_ids]
    summary_failed = False
    try:
        write_summary_report(output_dir, all_metrics, timestamps)
    except Exception as exc:
        print(f"Failed to write summary report: {exc}", file=sys.stderr)
        summary_failed = True

    # Print summary
    print_summary_table(all_metrics)

    elapsed = (completed_at - started_at).total_seconds()
    print(f"Evaluation complete in {elapsed:.1f}s. Results in {output_dir}")

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
    scenarios: list[Scenario],
    output_dir: Path,
    *,
    parallel: bool = False,
    max_workers: int | None = None,
    prompt_extras: frozenset[str] = frozenset(),
) -> None:
    """Print the evaluation plan without executing."""
    print("Evaluation Plan (dry run)")
    print("=" * 40)
    print(f"Output directory: {output_dir}")
    print(f"Scenarios: {len(scenarios)}")
    if prompt_extras:
        print(f"Prompt extras: {', '.join(sorted(prompt_extras))}")
    if parallel:
        effective = max_workers or DEFAULT_MAX_WORKERS
        cloud_count = sum(1 for m in models if m.provider not in LOCAL_PROVIDERS)
        capped = min(effective, cloud_count) if cloud_count else 0
        print(f"Parallel: yes (max workers: {capped})")
    print()

    total_predictions = 0
    steps = sum(len(s.steps) for s in scenarios)
    for m in models:
        runs = m.runs if m.runs is not None else settings.runs_per_model.get(m.provider, 1)
        predictions = runs * steps
        total_predictions += predictions
        tier_label = f", tier={m.tier}" if m.tier is not None else ""
        print(f"  {m.name} ({m.provider}/{m.model_id}{tier_label})")
        print(f"    Runs: {runs}, Steps per run: {steps}, Total predictions: {predictions}")

    print()
    print(f"Total predictions: {total_predictions}")

    # Category breakdown
    categories: dict[str, int] = {}
    for s in scenarios:
        categories[s.category] = categories.get(s.category, 0) + 1
    print("\nScenarios by category:")
    for cat, count in sorted(categories.items()):
        print(f"  {cat}: {count}")


if __name__ == "__main__":
    sys.exit(main())
