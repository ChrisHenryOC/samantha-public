"""Shared fixtures and constants for red-team tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import yaml

if TYPE_CHECKING:
    from src.evaluation.metrics import ScenarioResult, StepResult
    from src.evaluation.query_metrics import QueryResult

# Shared test vocabularies used by validator test modules.
ALL_STATES: frozenset[str] = frozenset(["ACCESSIONING", "ACCEPTED", "ORDER_COMPLETE"])
ALL_RULE_IDS: frozenset[str] = frozenset(["ACC-001", "ACC-008"])
ALL_FLAG_IDS: frozenset[str] = frozenset(["FISH_SUGGESTED", "FIXATION_WARNING"])


def _expected() -> dict[str, object]:
    """Canonical expected prediction for validator tests."""
    return {"next_state": "ACCEPTED", "applied_rules": ["ACC-008"], "flags": []}


@pytest.fixture()
def make_yaml(tmp_path: Path) -> Callable[..., Path]:
    """Factory fixture: write a dict to a temp YAML file, return its Path."""

    def _make(data: Any, filename: str = "workflow.yaml") -> Path:
        p = tmp_path / filename
        p.write_text(yaml.dump(data, default_flow_style=False))
        return p

    return _make


@pytest.fixture()
def minimal_valid_yaml() -> dict[str, Any]:
    """Smallest dict that StateMachine.__init__ accepts.

    One state, no transitions/rules/flags, one terminal state list entry.
    """
    return {
        "states": [
            {
                "id": "ONLY_STATE",
                "phase": "test",
                "description": "the only state",
                "terminal": True,
            }
        ],
        "transitions": [],
        "rules": [],
        "flags": [],
        "terminal_states": ["ONLY_STATE"],
    }


# ---------------------------------------------------------------------------
# Phase 3-4 shared helpers
# ---------------------------------------------------------------------------


def _minimal_valid_model_entry() -> dict[str, Any]:
    """A single valid model entry dict for models.yaml."""
    return {
        "name": "test-model",
        "provider": "llamacpp",
        "model_id": "test/model-1",
        "token_limit": 4096,
        "parameters": {
            "temperature": 0.7,
            "max_tokens": 512,
        },
    }


def _minimal_valid_models_yaml() -> dict[str, Any]:
    """Smallest dict that load_models() accepts."""
    return {"models": [_minimal_valid_model_entry()]}


def _minimal_valid_settings_yaml() -> dict[str, Any]:
    """Smallest dict that load_settings() accepts."""
    return {
        "evaluation": {
            "runs_per_model": {"llamacpp": 3},
            "timeout_seconds": 60,
            "output_directory": "results",
        }
    }


@pytest.fixture()
def make_models_yaml(tmp_path: Path) -> Callable[..., Path]:
    """Factory fixture: write a models YAML file, return its Path."""

    def _make(data: dict[str, Any] | None = None) -> Path:
        if data is None:
            data = _minimal_valid_models_yaml()
        p = tmp_path / "models.yaml"
        p.write_text(yaml.dump(data, default_flow_style=False))
        return p

    return _make


@pytest.fixture()
def make_settings_yaml(tmp_path: Path) -> Callable[..., Path]:
    """Factory fixture: write a settings YAML file, return its Path."""

    def _make(data: dict[str, Any] | None = None) -> Path:
        if data is None:
            data = _minimal_valid_settings_yaml()
        p = tmp_path / "settings.yaml"
        p.write_text(yaml.dump(data, default_flow_style=False))
        return p

    return _make


# ---------------------------------------------------------------------------
# Stub dataclasses for metrics tests
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FakeDecision:
    """Stub satisfying the DecisionLike protocol for routing metrics."""

    predicted_next_state: str = "ACCEPTED"
    expected_next_state: str = "ACCEPTED"
    predicted_flags: list[str] | None = None
    expected_flags: list[str] | None = None
    latency_ms: int = 100
    input_tokens: int = 500
    output_tokens: int = 50

    def __post_init__(self) -> None:
        if self.predicted_flags is None:
            object.__setattr__(self, "predicted_flags", [])
        if self.expected_flags is None:
            object.__setattr__(self, "expected_flags", [])


@dataclass(frozen=True)
class FakeQueryDecision:
    """Stub satisfying the QueryDecisionLike protocol for query metrics."""

    predicted_order_ids: list[str] | None = None
    expected_order_ids: list[str] | None = None
    latency_ms: int = 100
    input_tokens: int = 500
    output_tokens: int = 50

    def __post_init__(self) -> None:
        if self.predicted_order_ids is None:
            object.__setattr__(self, "predicted_order_ids", [])
        if self.expected_order_ids is None:
            object.__setattr__(self, "expected_order_ids", [])


# ---------------------------------------------------------------------------
# Builder helpers for metrics result objects
# ---------------------------------------------------------------------------


def _make_step_result(
    *,
    state_correct: bool = True,
    rules_correct: bool = True,
    flags_correct: bool = True,
    failure_type: Any = None,
    predicted_flags: list[str] | None = None,
    expected_flags: list[str] | None = None,
    latency_ms: int = 100,
    input_tokens: int = 500,
    output_tokens: int = 50,
) -> StepResult:
    """Build a StepResult using real classes."""
    from src.evaluation.metrics import StepResult
    from src.workflow.validator import ValidationResult

    decision = FakeDecision(
        predicted_flags=predicted_flags,
        expected_flags=expected_flags,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    validation = ValidationResult(
        state_correct=state_correct,
        rules_correct=rules_correct,
        flags_correct=flags_correct,
    )
    return StepResult(decision=decision, validation=validation, failure_type=failure_type)


def _make_scenario_result(
    *,
    scenario_id: str = "S-001",
    category: str = "accessioning",
    model_id: str = "test-model",
    run_number: int = 1,
    step_results: tuple[Any, ...] | None = None,
    all_correct: bool | None = None,
) -> ScenarioResult:
    """Build a ScenarioResult using real classes."""
    from src.evaluation.metrics import ScenarioResult

    if step_results is None:
        step_results = (_make_step_result(),)
    if all_correct is None:
        all_correct = all(sr.validation.all_correct for sr in step_results)
    return ScenarioResult(
        scenario_id=scenario_id,
        category=category,
        model_id=model_id,
        run_number=run_number,
        step_results=step_results,
        all_correct=all_correct,
    )


def _make_query_result(
    *,
    scenario_id: str = "Q-001",
    tier: int = 1,
    answer_type: str = "order_list",
    model_id: str = "test-model",
    run_number: int = 1,
    order_ids_correct: bool = True,
    precision: float = 1.0,
    recall: float = 1.0,
    f1: float = 1.0,
    failure_type: Any = None,
    latency_ms: int = 100,
    input_tokens: int = 500,
    output_tokens: int = 50,
) -> QueryResult:
    """Build a QueryResult using real classes."""
    from src.evaluation.query_metrics import QueryResult
    from src.workflow.query_validator import QueryValidationResult

    decision = FakeQueryDecision(
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    validation = QueryValidationResult(
        order_ids_correct=order_ids_correct,
        precision=precision,
        recall=recall,
        f1=f1,
    )
    return QueryResult(
        scenario_id=scenario_id,
        tier=tier,
        answer_type=answer_type,
        model_id=model_id,
        run_number=run_number,
        decision=decision,
        validation=validation,
        failure_type=failure_type,
    )
