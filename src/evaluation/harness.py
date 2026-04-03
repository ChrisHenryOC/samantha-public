"""Evaluation harness: orchestrates scenario execution across models.

Builds orders from scenario event data, runs predictions through the engine,
validates results, and persists decisions. After each step, advances the
order to the *expected* state (not predicted) so each step is evaluated
independently.
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
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.evaluation.dashboard import Dashboard
from src.evaluation.metrics import ScenarioResult, StepResult
from src.models.config import EvaluationSettings, ModelConfig
from src.models.llamacpp_adapter import LlamaCppAdapter
from src.models.openrouter_adapter import OpenRouterAdapter
from src.prediction.engine import PredictionEngine
from src.simulator.schema import ExpectedOutput, Scenario, ScenarioStep
from src.workflow.database import Database
from src.workflow.models import (
    FIELD_MAX_LENGTHS,
    VALID_FLAGS,
    VALID_STATES,
    Decision,
    Event,
    Order,
    Run,
    Slide,
    expand_panel,
)
from src.workflow.validator import (
    FailureType,
    ValidationResult,
    classify_failure,
    validate_prediction,
)

if TYPE_CHECKING:
    from src.rag.retriever import RagRetriever

logger = logging.getLogger(__name__)

# Early-abort: if more than this fraction of scenarios produce fatal errors
# (invalid JSON, timeout, empty response) during run 1, skip the model.
_EARLY_ABORT_THRESHOLD = 0.5
_EARLY_ABORT_MIN_SCENARIOS = 20
_EARLY_ABORT_MIN_STEPS = 30
LOCAL_PROVIDER = "llamacpp"  # Backward compat for imports
LOCAL_PROVIDERS = frozenset({"llamacpp", "ollama"})
DEFAULT_MAX_WORKERS = 4

_FATAL_FAILURE_TYPES = frozenset(
    {
        FailureType.INVALID_JSON,
        FailureType.TIMEOUT,
        FailureType.EMPTY_RESPONSE,
    }
)

# All valid rule IDs for hallucination detection.
# Loaded from the state machine's rule catalog.
_ALL_RULE_IDS: frozenset[str] | None = None


def _should_use_dashboard() -> bool:
    """Return True when the Rich Live dashboard should be used.

    Requires a real TTY on stdout so piped/CI output falls back to
    line-by-line prints automatically.  Set ``FORCE_DASHBOARD=1`` to
    override the TTY check (e.g. when stdout is piped through ``tee``).
    """
    if os.environ.get("FORCE_DASHBOARD") == "1":
        return True
    return sys.stdout.isatty()


def _get_all_rule_ids() -> frozenset[str]:
    """Lazily load all valid rule IDs from the state machine."""
    global _ALL_RULE_IDS  # noqa: PLW0603
    if _ALL_RULE_IDS is None:
        from src.workflow.state_machine import StateMachine

        sm = StateMachine()
        _ALL_RULE_IDS = sm.get_all_rule_ids()
    return _ALL_RULE_IDS


def _validate_scenario_ground_truth(scenario: Scenario) -> None:
    """Validate that scenario ground truth uses valid states, rules, and flags."""
    all_rule_ids = _get_all_rule_ids()
    for step in scenario.steps:
        expected = step.expected_output
        if expected.next_state not in VALID_STATES:
            raise ValueError(
                f"Scenario {scenario.scenario_id} step {step.step}: "
                f"invalid expected state {expected.next_state!r}"
            )
        for rule_id in expected.applied_rules:
            if rule_id not in all_rule_ids:
                raise ValueError(
                    f"Scenario {scenario.scenario_id} step {step.step}: "
                    f"invalid expected rule {rule_id!r}"
                )
        for flag in expected.flags:
            if flag not in VALID_FLAGS:
                raise ValueError(
                    f"Scenario {scenario.scenario_id} step {step.step}: "
                    f"invalid expected flag {flag!r}"
                )


# --- Helper functions ---


def build_order_from_event_data(scenario_id: str, event_data: dict[str, Any]) -> Order:
    """Map scenario event_data fields to an Order.

    Field mapping: age -> patient_age, sex -> patient_sex.
    Expands panels in ordered_tests via expand_panel().

    Missing-data handling:
    - patient_name, patient_sex: None when missing (triggers ACC-001/002 "missing" checks)
    - specimen_type, anatomic_site, fixative: "" when null/missing (triggers ACC-003/004
      "invalid" checks). The distinction maps to rule trigger semantics: missing vs invalid.
    - priority: "routine" when null/missing (no rules trigger on priority value)
    - ordered_tests: [] when null/missing
    """
    # Log null conversions for debugging
    for field in ("specimen_type", "anatomic_site", "fixative", "priority", "billing_info_present"):
        if event_data.get(field) is None:
            logger.debug("Scenario %s: %s is null, using default", scenario_id, field)

    raw_tests = event_data.get("ordered_tests") or []
    if not isinstance(raw_tests, list):
        raise TypeError(f"ordered_tests must be a list, got {type(raw_tests).__name__}")
    expanded: list[str] = []
    for test in raw_tests:
        if not isinstance(test, str):
            raise TypeError(f"ordered_tests elements must be strings, got {type(test).__name__}")
        expanded.extend(expand_panel(test))

    priority_val = event_data.get("priority")
    billing_val = event_data.get("billing_info_present")

    return Order(
        order_id=f"ORD-{scenario_id}",
        scenario_id=scenario_id,
        patient_name=event_data.get("patient_name"),
        patient_age=event_data.get("age"),
        patient_sex=event_data.get("sex"),
        specimen_type=event_data.get("specimen_type") or "",
        anatomic_site=event_data.get("anatomic_site") or "",
        fixative=event_data.get("fixative") or "",
        fixation_time_hours=event_data.get("fixation_time_hours"),
        ordered_tests=expanded,
        priority=priority_val if priority_val is not None else "routine",
        billing_info_present=billing_val if billing_val is not None else True,
        current_state="ACCESSIONING",
        flags=[],
    )


def build_slides_for_order(order: Order) -> list[Slide]:
    """Create one Slide per expanded test, all status='sectioned'."""
    slides: list[Slide] = []
    for i, test in enumerate(order.ordered_tests, 1):
        slides.append(
            Slide(
                slide_id=f"{order.order_id}-S{i:03d}",
                order_id=order.order_id,
                test_assignment=test,
                status="sectioned",
            )
        )
    return slides


def build_event(order_id: str, step: ScenarioStep) -> Event:
    """Wrap a ScenarioStep into an Event dataclass."""
    return Event(
        event_id=f"{order_id}-E{step.step:03d}",
        order_id=order_id,
        step_number=step.step,
        event_type=step.event_type,
        event_data=step.event_data,
    )


def advance_order_state(order: Order, expected: ExpectedOutput) -> Order:
    """Return a new Order with state and flags from expected output.

    Uses expected (not predicted) so each step evaluates independently.
    """
    return replace(
        order,
        current_state=expected.next_state,
        flags=list(expected.flags),
    )


def _qc_status(result: str) -> str:
    """Map a QC result value to a slide status string."""
    return "qc_pass" if result == "pass" else "qc_fail"


def advance_slides_state(
    slides: list[Slide],
    step: ScenarioStep,
) -> list[Slide]:
    """Advance slide state to reflect a completed workflow step.

    Updates slide status, qc_result, and score_result based on event type
    so that slide state stays consistent with order state as the scenario
    replays through steps.

    Supported event types and their effects:

    - ``he_staining_complete``, ``ihc_staining_complete`` — status → stain_complete
    - ``sample_prep_qc`` — status → qc_pass/qc_fail, qc_result updated
    - ``he_qc``, ``ihc_qc`` — per-slide qc_result from event data
    - ``ihc_scoring`` — status → scored, per-slide score_result from event data
    - ``pathologist_signout`` — reported → True

    Unrecognised event types return *slides* unchanged (passthrough).
    """
    event_type = step.event_type
    event_data = step.event_data

    if event_type in ("he_staining_complete", "ihc_staining_complete"):
        return [replace(s, status="stain_complete") for s in slides]

    if event_type == "sample_prep_qc":
        if "outcome" not in event_data:
            logger.warning("sample_prep_qc event missing 'outcome'; defaulting to 'pass'")
        outcome = event_data.get("outcome", "pass")
        return [replace(s, status=_qc_status(outcome), qc_result=outcome) for s in slides]

    if event_type in ("he_qc", "ihc_qc"):
        slide_data = event_data.get("slides", [])
        qc_by_test: dict[str, str] = {
            d["test"]: d.get("qc_result", "pass")
            for d in slide_data
            if isinstance(d, dict) and "test" in d
        }
        updated: list[Slide] = []
        for s in slides:
            if s.test_assignment not in qc_by_test:
                logger.warning(
                    "%s: slide test '%s' not in QC event data; defaulting to 'pass'",
                    event_type,
                    s.test_assignment,
                )
            result = qc_by_test.get(s.test_assignment, "pass")
            updated.append(replace(s, status=_qc_status(result), qc_result=result))
        return updated

    if event_type == "ihc_scoring":
        score_data = event_data.get("scores", [])
        score_by_test: dict[str, dict[str, Any]] = {
            d["test"]: d for d in score_data if isinstance(d, dict) and "test" in d
        }
        result_slides: list[Slide] = []
        for s in slides:
            score = score_by_test.get(s.test_assignment)
            if score is None:
                logger.warning(
                    "ihc_scoring: slide test '%s' not in scoring data; score_result will be None",
                    s.test_assignment,
                )
            result_slides.append(replace(s, status="scored", score_result=score))
        return result_slides

    if event_type == "pathologist_signout":
        return [replace(s, reported=True) for s in slides]

    return slides


def _print_progress(
    run_number: int,
    total_runs: int,
    scenario_idx: int,
    total_scenarios: int,
    scenario_id: str,
    status: str,
    *,
    model_name: str = "",
    latency_s: float | None = None,
) -> None:
    """Print a single-line progress update to stdout."""
    ts = datetime.now().strftime("%H:%M:%S")
    prefix = f"  {ts} [{model_name}] " if model_name else f"  {ts} "
    latency_str = f" ({latency_s:.1f}s)" if latency_s is not None else ""
    with contextlib.suppress(BrokenPipeError, OSError):
        print(
            f"{prefix}Run {run_number}/{total_runs} | "
            f"{scenario_idx:>3}/{total_scenarios} {scenario_id} [{status}]{latency_str}",
            flush=True,
        )


# --- EvaluationHarness ---


class EvaluationHarness:
    """Orchestrates evaluation: runs scenarios across models and persists results.

    Args:
        models: Model configurations to evaluate.
        settings: Evaluation parameters (runs per model, timeouts).
        scenarios: Routing scenarios to evaluate.
        db_path: Path to the SQLite database for persisting results.
        rag_retriever: If provided, passes RAG context to each prediction
            instead of the static rule catalog (Phase 5 RAG mode).
    """

    def __init__(
        self,
        models: list[ModelConfig],
        settings: EvaluationSettings,
        scenarios: list[Scenario],
        db_path: str | Path,
        *,
        rag_retriever: RagRetriever | None = None,
        prompt_extras: frozenset[str] = frozenset(),
    ) -> None:
        from src.prediction.prompt_template import VALID_PROMPT_EXTRAS

        invalid = prompt_extras - VALID_PROMPT_EXTRAS
        if invalid:
            raise ValueError(
                f"Invalid prompt_extras: {sorted(invalid)}. "
                f"Valid options: {sorted(VALID_PROMPT_EXTRAS)}"
            )
        self._models = models
        self._settings = settings
        self._scenarios = scenarios
        self._db_path = Path(db_path)
        self._rag_retriever = rag_retriever
        self._prompt_extras = prompt_extras

    def run_all(
        self,
        on_run_complete: (Callable[[str, int, list[ScenarioResult], bool], None] | None) = None,
        *,
        parallel: bool = False,
        max_workers: int | None = None,
    ) -> list[ScenarioResult]:
        """Run all scenarios for all models and return results.

        Results from early-aborted models are excluded from the return value.
        Use the *on_run_complete* callback to capture partial results from
        aborted runs.

        Args:
            on_run_complete: Optional callback invoked after each run finishes.
                Called with (model_id, run_number, run_results, aborted).
                The aborted flag is True if the run was cut short by early-abort.
            parallel: When True, run models concurrently via
                ThreadPoolExecutor. A single local (llamacpp) model runs
                in the pool alongside cloud models (independent resources).
                Multiple local models run sequentially first (shared GPU).
                The callback is invoked under a lock in parallel mode, so
                callbacks should complete quickly to avoid serializing threads.
            max_workers: Maximum number of concurrent model threads.
                Defaults to the module-level ``DEFAULT_MAX_WORKERS`` (4).
                Ignored when *parallel* is False.
        """
        _get_all_rule_ids()  # Pre-warm cache before timing starts
        for scenario in self._scenarios:
            _validate_scenario_ground_truth(scenario)
        all_results: list[ScenarioResult] = []
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
                    completion_counter: list[int] = [0]
                    total_parallel = len(parallel_models)

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
                                logger.error("Model failed in parallel pool: %s", exc)
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
        on_run_complete: Callable[[str, int, list[ScenarioResult], bool], None] | None,
        callback_lock: threading.Lock | None,
        completion_counter: list[int] | None = None,
        total_parallel_models: int | None = None,
        dashboard: Dashboard | None = None,
    ) -> list[ScenarioResult]:
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
        on_run_complete: Callable[[str, int, list[ScenarioResult], bool], None] | None,
        callback_lock: threading.Lock | None,
        completion_counter: list[int] | None = None,
        total_parallel_models: int | None = None,
        dashboard: Dashboard | None = None,
    ) -> list[ScenarioResult]:
        """Run all scenarios for a single model and return non-aborted results."""
        model_start = time.monotonic()
        model_results: list[ScenarioResult] = []
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
                print(
                    f"\n{ts} [{model_idx}/{len(self._models)}] {config.name} "
                    f"({runs_count} run(s), {total_scenarios} scenarios each)",
                    flush=True,
                )

            model_aborted = False
            for run_number in range(1, runs_count + 1):
                if model_aborted:
                    break

                run_id = f"run-{config.model_id}-{run_number}-{uuid.uuid4().hex[:8]}"
                extras_note = ",".join(sorted(self._prompt_extras)) if self._prompt_extras else None
                run = Run(
                    run_id=run_id,
                    prompt_template_version="v1",
                    scenario_set_version="v1",
                    model_id=config.model_id,
                    run_number=run_number,
                    started_at=datetime.now(),
                    notes=extras_note,
                )
                db.insert_run(run)

                run_results: list[ScenarioResult] = []
                fatal_count = 0
                fatal_step_count = 0
                total_step_count = 0
                for sc_idx, scenario in enumerate(self._scenarios, 1):
                    sc_start = time.monotonic()
                    result = self._run_scenario(engine, scenario, run_id, run_number, db)
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
                            latency_s=sc_elapsed,
                        )

                    # Track fatal failures for early-abort
                    scenario_has_fatal = False
                    for sr in result.step_results:
                        total_step_count += 1
                        if sr.failure_type in _FATAL_FAILURE_TYPES:
                            fatal_step_count += 1
                            scenario_has_fatal = True
                    if scenario_has_fatal:
                        fatal_count += 1

                    # Step-level abort (triggers earlier for multi-step scenarios)
                    if (
                        total_step_count >= _EARLY_ABORT_MIN_STEPS
                        and fatal_step_count > total_step_count * _EARLY_ABORT_THRESHOLD
                    ):
                        msg = (
                            f"{fatal_step_count}/{total_step_count} steps "
                            f"({fatal_step_count / total_step_count:.0%}) "
                            f"had fatal errors"
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

                    # Scenario-level abort
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
                        "Failed to mark run %s as completed. "
                        "Database may be in an inconsistent state.",
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

    def _run_scenario(
        self,
        engine: PredictionEngine,
        scenario: Scenario,
        run_id: str,
        run_number: int,
        db: Database,
    ) -> ScenarioResult:
        """Run a single scenario through the engine, step by step."""
        step_results: list[StepResult] = []
        order: Order | None = None
        slides: list[Slide] = []
        # Use run-unique order ID to avoid PK conflicts across models and runs.
        # run_id already contains model_id + run_number + uuid suffix.
        run_suffix = run_id.rsplit("-", maxsplit=1)[-1]  # uuid hex[:8]
        order_key = f"{scenario.scenario_id}-{run_suffix}"

        for step in scenario.steps:
            # Step 1: build order from event_data; Step 2+: advance to expected state
            if order is None:
                order = build_order_from_event_data(order_key, step.event_data)
                slides = build_slides_for_order(order)
                db.insert_order(order)
                for slide in slides:
                    db.insert_slide(slide, _commit=False)
                db.commit()
            else:
                prev_idx = step.step - 2
                if prev_idx < 0 or prev_idx >= len(scenario.steps):
                    raise ValueError(
                        f"Scenario {scenario.scenario_id}: step {step.step} "
                        f"references invalid previous step index {prev_idx}"
                    )
                prev_step = scenario.steps[prev_idx]
                prev_expected = prev_step.expected_output
                order = advance_order_state(order, prev_expected)
                slides = advance_slides_state(slides, prev_step)
                db.update_order_state(
                    order.order_id,
                    order.current_state,
                    order.flags,
                    datetime.now(),
                )

            event = build_event(order.order_id, step)
            # Commit immediately (not deferred) to avoid holding DB locks
            # during the network call in parallel mode.
            db.insert_event(event)

            # Run prediction
            prediction = engine.predict_routing(
                order,
                slides,
                event,
                rag_retriever=self._rag_retriever,
                prompt_extras=self._prompt_extras,
            )

            # Build validation dicts — convert tuples to lists once
            expected_rules = list(step.expected_output.applied_rules)
            expected_flags = list(step.expected_output.flags)
            expected_dict = {
                "next_state": step.expected_output.next_state,
                "applied_rules": expected_rules,
                "flags": expected_flags,
            }

            if prediction.error is not None:
                validation = ValidationResult(
                    state_correct=False,
                    rules_correct=False,
                    flags_correct=False,
                )
                timed_out = prediction.raw_response.timed_out
                failure_type = classify_failure(
                    None,
                    expected_dict,
                    VALID_STATES,
                    timed_out=timed_out,
                    all_rule_ids=_get_all_rule_ids(),
                    all_flag_ids=VALID_FLAGS,
                )
                predicted_state = ""
                predicted_rules: list[str] = []
                predicted_flags: list[str] = []
            else:
                predicted_rules = list(prediction.applied_rules)
                predicted_flags = list(prediction.flags)
                prediction_dict = {
                    "next_state": prediction.next_state,
                    "applied_rules": predicted_rules,
                    "flags": predicted_flags,
                }
                validation = validate_prediction(prediction_dict, expected_dict)
                failure_type = classify_failure(
                    prediction_dict,
                    expected_dict,
                    VALID_STATES,
                    all_rule_ids=_get_all_rule_ids(),
                    all_flag_ids=VALID_FLAGS,
                )
                predicted_state = prediction.next_state or ""

            # Truncate model outputs to fit database field limits.
            # Over-long values are hallucinated states — score them as wrong,
            # don't crash the harness.
            max_state_len = FIELD_MAX_LENGTHS.get("predicted_next_state", 50)
            if len(predicted_state) > max_state_len:
                logger.warning(
                    "predicted_next_state truncated (%d > %d): %s",
                    len(predicted_state),
                    max_state_len,
                    predicted_state,
                )
                predicted_state = predicted_state[:max_state_len]

            decision = Decision(
                decision_id=f"{run_id}-{scenario.scenario_id}-S{step.step}",
                run_id=run_id,
                event_id=event.event_id,
                order_id=order.order_id,
                model_id=engine.model_id,
                order_state_snapshot=_order_snapshot(order),
                model_input={"prompt": "..."},  # Abbreviated for storage
                model_output={
                    "next_state": predicted_state,
                    "applied_rules": predicted_rules,
                    "flags": predicted_flags,
                    "reasoning": prediction.reasoning,
                    "error": prediction.error,
                },
                predicted_next_state=predicted_state,
                predicted_applied_rules=predicted_rules,
                predicted_flags=predicted_flags,
                expected_next_state=step.expected_output.next_state,
                expected_applied_rules=expected_rules,
                expected_flags=expected_flags,
                state_correct=validation.state_correct,
                rules_correct=validation.rules_correct,
                flags_correct=validation.flags_correct,
                latency_ms=int(prediction.raw_response.latency_ms),
                input_tokens=prediction.raw_response.input_tokens,
                output_tokens=prediction.raw_response.output_tokens,
            )
            db.insert_decision(decision, _commit=False)
            step_results.append(
                StepResult(
                    decision=decision,
                    validation=validation,
                    failure_type=failure_type,
                )
            )

        try:
            db.commit()
        except Exception as exc:
            raise RuntimeError(
                f"Database error committing scenario {scenario.scenario_id}: {exc}"
            ) from exc
        return ScenarioResult(
            scenario_id=scenario.scenario_id,
            category=scenario.category,
            model_id=engine.model_id,
            run_number=run_number,
            step_results=tuple(step_results),
            all_correct=all(sr.validation.all_correct for sr in step_results),
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


def _has_fatal_failure(result: ScenarioResult) -> bool:
    """Check if any step in a scenario result had a fatal failure type."""
    return any(sr.failure_type in _FATAL_FAILURE_TYPES for sr in result.step_results)


def load_openrouter_key() -> str:
    """Load OpenRouter API key from file or environment."""
    key_path = Path(__file__).resolve().parent.parent.parent / "notes" / "openrouter-api-key.txt"
    if key_path.exists():
        return key_path.read_text(encoding="utf-8").strip()
    env_key = os.environ.get("OPENROUTER_API_KEY")
    if env_key:
        return env_key
    raise ValueError(
        "OpenRouter API key not found. Place it in notes/openrouter-api-key.txt "
        "or set the OPENROUTER_API_KEY environment variable."
    )


def _order_snapshot(order: Order) -> dict[str, Any]:
    """Build a serializable snapshot of order state for Decision storage."""
    return {
        "order_id": order.order_id,
        "scenario_id": order.scenario_id,
        "current_state": order.current_state,
        "specimen_type": order.specimen_type,
        "anatomic_site": order.anatomic_site,
        "fixative": order.fixative,
        "fixation_time_hours": order.fixation_time_hours,
        "ordered_tests": order.ordered_tests,
        "priority": order.priority,
        "flags": order.flags,
    }
