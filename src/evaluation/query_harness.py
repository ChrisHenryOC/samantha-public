"""Query evaluation harness: orchestrates query scenario execution across models.

Loads query scenarios, runs predictions through the engine, validates results
with the query validator, computes per-scenario metrics, and persists
QueryDecision rows to SQLite.
"""

from __future__ import annotations

import contextlib
import logging
import os
import sys
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from src.evaluation.dashboard import Dashboard
from src.evaluation.harness import DEFAULT_MAX_WORKERS, LOCAL_PROVIDERS, load_openrouter_key
from src.evaluation.query_metrics import QueryResult
from src.models.config import EvaluationSettings, ModelConfig
from src.models.llamacpp_adapter import LlamaCppAdapter
from src.models.openrouter_adapter import OpenRouterAdapter
from src.prediction.engine import PredictionEngine
from src.prediction.query_prompt_template import render_query_prompt
from src.simulator.schema import QueryScenario
from src.workflow.database import Database
from src.workflow.models import QueryDecision, Run
from src.workflow.query_validator import (
    QueryFailureType,
    QueryValidationResult,
    classify_query_failure,
    validate_query_prediction,
)

if TYPE_CHECKING:
    from src.rag.retriever import RagRetriever

logger = logging.getLogger(__name__)

# Early-abort thresholds — same philosophy as routing harness.
# Query scenario sets are smaller than routing sets, so the minimum
# threshold is lower (15 vs 20 for routing) to trigger abort sooner.
_EARLY_ABORT_THRESHOLD = 0.5
_EARLY_ABORT_MIN_SCENARIOS = 15
_FATAL_FAILURE_TYPES = frozenset(
    {
        QueryFailureType.TIMEOUT,
        QueryFailureType.INVALID_JSON,
        QueryFailureType.EMPTY_RESPONSE,
    }
)


def _should_use_dashboard() -> bool:
    """Return True when the Rich Live dashboard should be used.

    Requires a real TTY on stdout so piped/CI output falls back to
    line-by-line prints automatically.  Set ``FORCE_DASHBOARD=1`` to
    override the TTY check (e.g. when stdout is piped through ``tee``).
    """
    if os.environ.get("FORCE_DASHBOARD") == "1":
        return True
    return sys.stdout.isatty()


def _print_progress(
    run_number: int,
    total_runs: int,
    scenario_idx: int,
    total_scenarios: int,
    scenario_id: str,
    status: str,
    *,
    model_name: str = "",
) -> None:
    """Print a single-line progress update to stdout."""
    ts = datetime.now().strftime("%H:%M:%S")
    prefix = f"  {ts} [{model_name}] " if model_name else f"  {ts} "
    with contextlib.suppress(BrokenPipeError, OSError):
        print(
            f"{prefix}Run {run_number}/{total_runs} | "
            f"{scenario_idx:>3}/{total_scenarios} {scenario_id} [{status}]",
            flush=True,
        )


class QueryEvaluationHarness:
    """Orchestrates query evaluation: runs query scenarios across models.

    Args:
        models: Model configurations to evaluate.
        settings: Evaluation parameters (runs per model, timeouts).
        scenarios: Query scenarios to evaluate.
        db_path: Path to the SQLite database for persisting results.
        rag_retriever: If provided, passes RAG context to query prompts
            instead of the full state/flag definitions (Phase 5 RAG mode).
    """

    def __init__(
        self,
        models: list[ModelConfig],
        settings: EvaluationSettings,
        scenarios: list[QueryScenario],
        db_path: str | Path,
        *,
        rag_retriever: RagRetriever | None = None,
    ) -> None:
        self._models = models
        self._settings = settings
        self._scenarios = scenarios
        self._db_path = Path(db_path)
        self._rag_retriever = rag_retriever

    def run_all(
        self,
        on_run_complete: (Callable[[str, int, list[QueryResult], bool], None] | None) = None,
        *,
        parallel: bool = False,
        max_workers: int | None = None,
    ) -> list[QueryResult]:
        """Run all query scenarios for all models and return results.

        When *on_run_complete* is provided, results are delivered exclusively
        through the callback; the return value will be an empty list.  When
        no callback is provided, results are returned directly.

        Args:
            on_run_complete: Optional callback invoked after each run finishes.
                Called with (model_id, run_number, run_results, aborted).
            parallel: When True, run models concurrently via
                ThreadPoolExecutor. A single local (llamacpp) model runs
                in the pool alongside cloud models (independent resources).
                Multiple local models run sequentially first (shared GPU).
            max_workers: Maximum number of concurrent model threads.
                Defaults to ``DEFAULT_MAX_WORKERS`` (4).
                Ignored when *parallel* is False.
        """
        all_results: list[QueryResult] = []
        total_scenarios = len(self._scenarios)
        callback_lock = threading.Lock() if parallel else None

        with Database(self._db_path) as db:
            db.init_db()

            if not parallel:
                # Sequential path — unchanged behavior
                for model_idx, config in enumerate(self._models, 1):
                    results = self._run_model(
                        config,
                        model_idx,
                        total_scenarios,
                        db,
                        on_run_complete,
                        callback_lock,
                    )
                    all_results.extend(results)
            else:
                # Parallel path: split local vs cloud models
                local_models = [
                    (i, c) for i, c in enumerate(self._models, 1) if c.provider in LOCAL_PROVIDERS
                ]
                cloud_models = [
                    (i, c)
                    for i, c in enumerate(self._models, 1)
                    if c.provider not in LOCAL_PROVIDERS
                ]

                # A single local model can run concurrently with cloud
                # models since they use independent resources (GPU vs API).
                # Multiple local models stay sequential (shared GPU).
                if len(local_models) <= 1:
                    parallel_models = local_models + cloud_models
                    sequential_local: list[tuple[int, ModelConfig]] = []
                else:
                    parallel_models = cloud_models
                    sequential_local = local_models

                for model_idx, config in sequential_local:
                    results = self._run_model(
                        config,
                        model_idx,
                        total_scenarios,
                        db,
                        on_run_complete,
                        callback_lock,
                    )
                    all_results.extend(results)

                # Run models concurrently, each with its own DB connection
                if parallel_models:
                    effective_workers = min(
                        max_workers or DEFAULT_MAX_WORKERS,
                        len(parallel_models),
                    )
                    logger.info(
                        "Parallel mode: %d model(s), %d max worker(s)",
                        len(parallel_models),
                        effective_workers,
                    )
                    total_parallel = len(parallel_models)
                    completion_counter: list[int] = [0]

                    dashboard: Dashboard | None = None
                    if _should_use_dashboard():
                        force = os.environ.get("FORCE_DASHBOARD") == "1"
                        dashboard = Dashboard(
                            model_names=[c.name for _, c in parallel_models],
                            total_scenarios=total_scenarios,
                            total_models=total_parallel,
                            effective_workers=effective_workers,
                            force_terminal=force,
                        )

                    with (
                        dashboard if dashboard is not None else contextlib.nullcontext(),
                        ThreadPoolExecutor(max_workers=effective_workers) as executor,
                    ):
                        futures = [
                            executor.submit(
                                self._run_model_with_own_db,
                                config,
                                model_idx,
                                total_scenarios,
                                on_run_complete,
                                callback_lock,
                                completion_counter,
                                total_parallel,
                                dashboard,
                            )
                            for model_idx, config in parallel_models
                        ]

                        if dashboard is None:
                            ts = datetime.now().strftime("%H:%M:%S")
                            with contextlib.suppress(BrokenPipeError, OSError):
                                print(
                                    f"\n{ts} Queue: {total_parallel} models submitted "
                                    f"({effective_workers} concurrent workers)",
                                    flush=True,
                                )

                        errors: list[BaseException] = []
                        for future in futures:
                            exc = future.exception()
                            if exc is not None:
                                logger.error(
                                    "Model failed in parallel pool",
                                    exc_info=(type(exc), exc, exc.__traceback__),
                                )
                                errors.append(exc)
                            else:
                                all_results.extend(future.result())
                        if errors:
                            if len(errors) == 1:
                                raise errors[0]
                            raise RuntimeError(
                                f"{len(errors)} model(s) failed. First error: {errors[0]}"
                            ) from errors[0]

        return all_results

    def _run_model_with_own_db(
        self,
        config: ModelConfig,
        model_idx: int,
        total_scenarios: int,
        on_run_complete: Callable[[str, int, list[QueryResult], bool], None] | None,
        callback_lock: threading.Lock | None,
        completion_counter: list[int] | None = None,
        total_parallel_models: int | None = None,
        dashboard: Dashboard | None = None,
    ) -> list[QueryResult]:
        """Run a single model with its own Database connection (for thread safety).

        Precondition: ``init_db()`` must have been called on another connection
        before this method runs (tables must already exist).
        """
        with Database(self._db_path) as db:
            try:
                return self._run_model(
                    config,
                    model_idx,
                    total_scenarios,
                    db,
                    on_run_complete,
                    callback_lock,
                    completion_counter=completion_counter,
                    total_parallel_models=total_parallel_models,
                    dashboard=dashboard,
                )
            except Exception as exc:
                raise RuntimeError(
                    f"Model '{config.name}' ({config.model_id}) failed: {exc}"
                ) from exc

    def _run_model(
        self,
        config: ModelConfig,
        model_idx: int,
        total_scenarios: int,
        db: Database,
        on_run_complete: Callable[[str, int, list[QueryResult], bool], None] | None,
        callback_lock: threading.Lock | None,
        completion_counter: list[int] | None = None,
        total_parallel_models: int | None = None,
        dashboard: Dashboard | None = None,
    ) -> list[QueryResult]:
        """Run all query scenarios for a single model and return non-aborted results."""
        model_start = time.monotonic()
        model_results: list[QueryResult] = []
        adapter = None
        try:
            adapter = self._create_adapter(config)
            engine = PredictionEngine(adapter)
            runs_count = (
                config.runs
                if config.runs is not None
                else self._settings.runs_per_model.get(config.provider, 1)
            )
            if dashboard is not None:
                dashboard.model_started(
                    config.name,
                    runs=runs_count,
                    scenarios=total_scenarios,
                )
            else:
                ts = datetime.now().strftime("%H:%M:%S")
                with contextlib.suppress(BrokenPipeError, OSError):
                    print(
                        f"\n{ts} [{model_idx}/{len(self._models)}] {config.name} "
                        f"({runs_count} run(s), {total_scenarios} query scenarios)",
                        flush=True,
                    )

            model_aborted = False
            for run_number in range(1, runs_count + 1):
                if model_aborted:
                    break

                run_id = f"qrun-{config.model_id}-{run_number}-{uuid.uuid4().hex[:8]}"
                run = Run(
                    run_id=run_id,
                    prompt_template_version="v1",
                    scenario_set_version="v1",
                    model_id=config.model_id,
                    run_number=run_number,
                    started_at=datetime.now(),
                )
                db.insert_run(run)

                run_results: list[QueryResult] = []
                fatal_count = 0
                for sc_idx, scenario in enumerate(self._scenarios, 1):
                    sc_start = time.monotonic()
                    result = self._run_query_scenario(engine, scenario, run_id, run_number, db)
                    sc_elapsed = time.monotonic() - sc_start
                    run_results.append(result)
                    if dashboard is not None:
                        dashboard.scenario_completed(
                            config.name,
                            run=run_number,
                            total_runs=runs_count,
                            scenario_idx=sc_idx,
                            total=total_scenarios,
                            scenario_id=scenario.scenario_id,
                            passed=result.all_correct,
                            latency_s=sc_elapsed,
                        )
                    else:
                        status = "OK" if result.all_correct else "FAIL"
                        _print_progress(
                            run_number,
                            runs_count,
                            sc_idx,
                            total_scenarios,
                            scenario.scenario_id,
                            status,
                            model_name=config.name if callback_lock is not None else "",
                        )

                    if result.failure_type in _FATAL_FAILURE_TYPES:
                        fatal_count += 1

                    if (
                        sc_idx >= _EARLY_ABORT_MIN_SCENARIOS
                        and fatal_count > sc_idx * _EARLY_ABORT_THRESHOLD
                    ):
                        msg = (
                            f"{fatal_count}/{sc_idx} scenarios "
                            f"({fatal_count / sc_idx:.0%}) had fatal errors"
                        )
                        if dashboard is not None:
                            dashboard.model_aborted(config.name, msg)
                        else:
                            with contextlib.suppress(BrokenPipeError, OSError):
                                print(
                                    f"\n  WARNING: {config.name} aborted — {msg}",
                                    flush=True,
                                )
                        model_aborted = True
                        break

                try:
                    db.update_run_completed(
                        run_id,
                        datetime.now(),
                        aborted=model_aborted,
                    )
                except Exception:
                    logger.error(
                        "Failed to mark run %s as completed.",
                        run_id,
                        exc_info=True,
                    )
                    raise

                if on_run_complete is not None:
                    with callback_lock if callback_lock is not None else contextlib.nullcontext():
                        on_run_complete(
                            config.model_id,
                            run_number,
                            run_results,
                            model_aborted,
                        )
                elif not model_aborted:
                    model_results.extend(run_results)

        finally:
            if adapter is not None:
                adapter.close()

        if (
            callback_lock is not None
            and completion_counter is not None
            and total_parallel_models is not None
        ):
            elapsed = time.monotonic() - model_start
            with callback_lock:
                completion_counter[0] += 1
                done = completion_counter[0]
            if dashboard is not None:
                dashboard.model_completed(config.name, elapsed_s=elapsed)
            else:
                ts = datetime.now().strftime("%H:%M:%S")
                with contextlib.suppress(BrokenPipeError, OSError):
                    print(
                        f"{ts} [{config.name}] Completed ({elapsed:.1f}s) "
                        f"— {done}/{total_parallel_models} models done",
                        flush=True,
                    )

        return model_results

    def _run_query_scenario(
        self,
        engine: PredictionEngine,
        scenario: QueryScenario,
        run_id: str,
        run_number: int,
        db: Database,
    ) -> QueryResult:
        """Run a single query scenario through the engine."""
        answer_type = scenario.expected_output.answer_type
        expected_ids = list(scenario.expected_output.order_ids)

        # Capture the rendered prompt before prediction for the audit trail
        try:
            rendered_prompt = render_query_prompt(scenario)
        except Exception:
            rendered_prompt = "<prompt rendering failed>"

        prediction = engine.predict_query(scenario, rag_retriever=self._rag_retriever)

        # Build expected dict for validator
        expected_dict = {
            "order_ids": expected_ids,
            "answer_type": answer_type,
        }

        if prediction.error is not None:
            # Prediction failed — force all metrics to incorrect
            validation = QueryValidationResult(
                order_ids_correct=False,
                precision=0.0,
                recall=0.0,
                f1=0.0,
            )
            timed_out = prediction.raw_response.timed_out
            failure_type = classify_query_failure(
                None,
                expected_dict,
                answer_type,
                timed_out=timed_out,
            )
            predicted_ids: list[str] = []
            model_output_dict = {
                "error": prediction.error,
            }
        else:
            parsed = prediction.parsed_output or {}
            predicted_ids = parsed.get("order_ids", [])
            validation = validate_query_prediction(parsed, expected_dict, answer_type)
            if not isinstance(predicted_ids, list):
                # Non-list order_ids is a structural type error — record it
                # rather than silently coercing to empty.
                failure_type = QueryFailureType.WRONG_FIELD_TYPE
                predicted_ids = []
            else:
                failure_type = classify_query_failure(
                    parsed,
                    expected_dict,
                    answer_type,
                )
            model_output_dict = parsed

        # Build database state snapshot dict
        db_state_snapshot = {
            "orders": list(scenario.database_state.orders),
            "slides": list(scenario.database_state.slides),
        }

        decision = QueryDecision(
            decision_id=f"{run_id}-{scenario.scenario_id}",
            run_id=run_id,
            scenario_id=scenario.scenario_id,
            model_id=engine.model_id,
            tier=scenario.tier,
            answer_type=answer_type,
            database_state_snapshot=db_state_snapshot,
            model_input={
                "scenario_id": scenario.scenario_id,
                "query": scenario.query,
                "answer_type": answer_type,
                "rendered_prompt": rendered_prompt,
            },
            model_output=model_output_dict,
            predicted_order_ids=predicted_ids,
            expected_order_ids=expected_ids,
            order_ids_correct=validation.order_ids_correct,
            precision=validation.precision,
            recall=validation.recall,
            f1=validation.f1,
            failure_type=(failure_type.value if failure_type is not None else None),
            latency_ms=int(prediction.raw_response.latency_ms),
            input_tokens=prediction.raw_response.input_tokens,
            output_tokens=prediction.raw_response.output_tokens,
        )
        db.insert_query_decision(decision)

        return QueryResult(
            scenario_id=scenario.scenario_id,
            tier=scenario.tier,
            answer_type=answer_type,
            model_id=engine.model_id,
            run_number=run_number,
            decision=decision,
            validation=validation,
            failure_type=failure_type,
        )

    def _create_adapter(self, config: ModelConfig) -> LlamaCppAdapter | OpenRouterAdapter:
        """Instantiate the appropriate adapter for a model config."""
        timeout = self._settings.timeout_seconds
        if config.provider == "llamacpp":
            return LlamaCppAdapter(config, timeout_seconds=timeout)
        if config.provider == "ollama":
            return LlamaCppAdapter(
                config, base_url="http://localhost:11434", timeout_seconds=timeout
            )
        if config.provider == "openrouter":
            api_key = load_openrouter_key()
            return OpenRouterAdapter(config, timeout_seconds=timeout, api_key=api_key)
        raise ValueError(f"Unknown provider: {config.provider!r}")
