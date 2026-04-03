"""Tool-use query evaluation harness.

Mirrors ``QueryEvaluationHarness`` but uses the tool-use prediction path:
creates a ``ToolExecutor`` per scenario, calls ``predict_query_with_tools()``,
and validates the final answer with the same ``validate_query_prediction()``
used by the context-stuffing harness for apples-to-apples comparison.

Tool-use metadata (tool call audit log, turns) is stored in the
``QueryDecision.model_output`` JSON column alongside the raw model response.
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
from typing import Any

from src.evaluation.dashboard import Dashboard
from src.evaluation.harness import DEFAULT_MAX_WORKERS, LOCAL_PROVIDERS, load_openrouter_key
from src.evaluation.query_metrics import QueryResult
from src.models.config import EvaluationSettings, ModelConfig
from src.models.llamacpp_adapter import LlamaCppAdapter
from src.models.openrouter_adapter import OpenRouterAdapter
from src.prediction.engine import PredictionEngine, ToolUseQueryResult
from src.simulator.schema import QueryScenario
from src.tools.definitions import get_all_tool_definitions
from src.tools.executor import ToolExecutor
from src.workflow.database import Database
from src.workflow.models import QueryDecision, Run
from src.workflow.query_validator import (
    QueryFailureType,
    QueryValidationResult,
    classify_query_failure,
    validate_query_prediction,
)

logger = logging.getLogger(__name__)

_EARLY_ABORT_THRESHOLD = 0.5
_EARLY_ABORT_MIN_SCENARIOS = 15
_FATAL_FAILURE_TYPES = frozenset(
    {
        QueryFailureType.TIMEOUT,
        QueryFailureType.INVALID_JSON,
        QueryFailureType.EMPTY_RESPONSE,
    }
)


def _classify_tool_use_error(error: str) -> QueryFailureType:
    """Map a tool-use prediction error string to a QueryFailureType.

    Uses the error prefix to classify into the correct category rather
    than passing None to classify_query_failure (which always returns
    INVALID_JSON for non-timeout errors).
    """
    error_lower = error.lower()
    if "timeout" in error_lower:
        return QueryFailureType.TIMEOUT
    if "empty_response" in error_lower or "max_turns_exceeded" in error_lower:
        return QueryFailureType.EMPTY_RESPONSE
    # All other errors (adapter_error, executor_error, prompt_error,
    # malformed_json, wrong_schema) → INVALID_JSON
    return QueryFailureType.INVALID_JSON


def _should_use_dashboard() -> bool:
    """Return True when the Rich Live dashboard should be used."""
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


class ToolUseQueryHarness:
    """Orchestrates tool-use query evaluation: runs scenarios with tool calling.

    Structurally mirrors ``QueryEvaluationHarness`` but uses the tool-use
    prediction path. The model calls tools to gather data rather than
    receiving it in the prompt.

    Args:
        models: Model configurations to evaluate.
        settings: Evaluation parameters (runs per model, timeouts).
        scenarios: Query scenarios to evaluate.
        db_path: Path to the SQLite database for persisting results.
    """

    def __init__(
        self,
        models: list[ModelConfig],
        settings: EvaluationSettings,
        scenarios: list[QueryScenario],
        db_path: str | Path,
    ) -> None:
        self._models = models
        self._settings = settings
        self._scenarios = scenarios
        self._db_path = Path(db_path)
        # get_all_tool_definitions() returns list[ToolDefinition] (TypedDict),
        # but PredictionEngine.predict_query_with_tools() expects list[dict[str, Any]].
        # TypedDicts are dicts at runtime; cast for mypy.
        tool_defs = get_all_tool_definitions()
        self._tool_defs: list[dict[str, Any]] = tool_defs  # type: ignore[assignment]

    def run_all(
        self,
        on_run_complete: (Callable[[str, int, list[QueryResult], bool], None] | None) = None,
        *,
        parallel: bool = False,
        max_workers: int | None = None,
    ) -> list[QueryResult]:
        """Run all query scenarios for all models using tool-use flow.

        Same interface as ``QueryEvaluationHarness.run_all()``.
        """
        all_results: list[QueryResult] = []
        total_scenarios = len(self._scenarios)
        callback_lock = threading.Lock() if parallel else None

        with Database(self._db_path) as db:
            db.init_db()

            if not parallel:
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
        """Run a single model with its own Database connection (thread safety)."""
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
        """Run all query scenarios for a single model using tool-use flow."""
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
                        f"({runs_count} run(s), {total_scenarios} tool-use query scenarios)",
                        flush=True,
                    )

            model_aborted = False
            for run_number in range(1, runs_count + 1):
                if model_aborted:
                    break

                run_id = f"turun-{config.model_id}-{run_number}-{uuid.uuid4().hex[:8]}"
                run = Run(
                    run_id=run_id,
                    prompt_template_version="v1-tool-use",
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
        """Run a single query scenario through the tool-use engine."""
        answer_type = scenario.expected_output.answer_type
        expected_ids = list(scenario.expected_output.order_ids)

        executor = ToolExecutor(scenario.database_state)
        prediction: ToolUseQueryResult = engine.predict_query_with_tools(
            scenario, executor, self._tool_defs
        )

        expected_dict: dict[str, Any] = {
            "order_ids": expected_ids,
            "answer_type": answer_type,
        }

        # Serialize tool call audit trail for model_output
        tool_calls_log = [
            {
                "tool_name": tc.tool_name,
                "arguments": tc.arguments,
                "result": tc.result,
                "turn": tc.turn,
            }
            for tc in prediction.tool_calls
        ]

        if prediction.error is not None:
            validation = QueryValidationResult(
                order_ids_correct=False,
                precision=0.0,
                recall=0.0,
                f1=0.0,
            )
            # Map tool-use error prefixes to query failure types directly,
            # rather than delegating to classify_query_failure(None, ...) which
            # always returns INVALID_JSON for non-timeout errors.
            failure_type: QueryFailureType | None = _classify_tool_use_error(prediction.error)
            predicted_ids: list[str] = []
            model_output_dict: dict[str, Any] = {
                "error": prediction.error,
                "tool_calls": tool_calls_log,
                "turns": prediction.turns,
            }
        else:
            parsed = prediction.parsed_output or {}
            predicted_ids = parsed.get("order_ids", [])
            validation = validate_query_prediction(parsed, expected_dict, answer_type)
            if not isinstance(predicted_ids, list):
                failure_type = QueryFailureType.WRONG_FIELD_TYPE
                predicted_ids = []
            else:
                failure_type = classify_query_failure(
                    parsed,
                    expected_dict,
                    answer_type,
                )
            model_output_dict = {
                **parsed,
                "tool_calls": tool_calls_log,
                "turns": prediction.turns,
            }

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
                "mode": "tool_use",
            },
            model_output=model_output_dict,
            predicted_order_ids=predicted_ids,
            expected_order_ids=expected_ids,
            order_ids_correct=validation.order_ids_correct,
            precision=validation.precision,
            recall=validation.recall,
            f1=validation.f1,
            failure_type=(failure_type.value if failure_type is not None else None),
            latency_ms=int(prediction.total_latency_ms),
            input_tokens=prediction.total_input_tokens,
            output_tokens=prediction.total_output_tokens,
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
