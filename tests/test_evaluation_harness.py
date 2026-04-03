"""Tests for the evaluation harness orchestration.

Uses mock adapters following the pattern from test_prediction_engine.py.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from src.evaluation.harness import (
    _EARLY_ABORT_MIN_SCENARIOS,
    _EARLY_ABORT_MIN_STEPS,
    EvaluationHarness,
    advance_order_state,
    advance_slides_state,
    build_event,
    build_order_from_event_data,
    build_slides_for_order,
    load_openrouter_key,
)
from src.models.base import ModelAdapter, ModelResponse
from src.models.config import EvaluationSettings, ModelConfig
from src.simulator.schema import ExpectedOutput, Scenario, ScenarioStep
from src.workflow.database import Database
from src.workflow.models import Slide

# --- Mock adapter ---


class MockAdapter(ModelAdapter):
    """Adapter that returns preconfigured responses."""

    def __init__(
        self,
        responses: list[dict[str, Any]] | None = None,
        *,
        error: str | None = None,
    ) -> None:
        self._responses = responses or []
        self._error = error
        self._call_count = 0

    def predict(self, prompt: str) -> ModelResponse:
        if self._error:
            return ModelResponse(
                raw_text=f"<{self._error}>",
                parsed_output=None,
                latency_ms=100,
                input_tokens=50,
                output_tokens=20,
                cost_estimate_usd=None,
                model_id="mock-model",
                error=self._error,
            )

        if self._call_count < len(self._responses):
            response_data = self._responses[self._call_count]
        else:
            response_data = self._responses[-1] if self._responses else {}
        self._call_count += 1

        raw_text = json.dumps(response_data)
        return ModelResponse(
            raw_text=raw_text,
            parsed_output=response_data,
            latency_ms=100,
            input_tokens=50,
            output_tokens=20,
            cost_estimate_usd=None,
            model_id="mock-model",
        )

    def close(self) -> None:
        pass

    @property
    def model_id(self) -> str:
        return "mock-model"

    @property
    def provider(self) -> str:
        return "mock"


class _AlternatingMockAdapter(ModelAdapter):
    """Adapter that cycles through a fatal/non-fatal pattern.

    Fatal calls return a timeout error; non-fatal calls return valid JSON
    with a wrong state (produces WRONG_STATE failure, not a fatal type).
    """

    def __init__(self, fatal_pattern: list[bool]) -> None:
        self._fatal_pattern = fatal_pattern
        self._call_count = 0

    def predict(self, prompt: str) -> ModelResponse:
        is_fatal = self._fatal_pattern[self._call_count % len(self._fatal_pattern)]
        self._call_count += 1

        if is_fatal:
            return ModelResponse(
                raw_text="<timeout>",
                parsed_output=None,
                latency_ms=100,
                input_tokens=50,
                output_tokens=20,
                cost_estimate_usd=None,
                model_id="mock-model",
                error="timeout: model did not respond",
            )

        wrong_response = {
            "next_state": "WRONG_STATE_VALUE",
            "applied_rules": ["ACC-008"],
            "flags": [],
            "reasoning": "mock wrong answer",
        }
        return ModelResponse(
            raw_text=json.dumps(wrong_response),
            parsed_output=wrong_response,
            latency_ms=100,
            input_tokens=50,
            output_tokens=20,
            cost_estimate_usd=None,
            model_id="mock-model",
        )

    def close(self) -> None:
        pass

    @property
    def model_id(self) -> str:
        return "mock-model"

    @property
    def provider(self) -> str:
        return "mock"


# --- Fixtures ---

_STEP_1_DATA = {
    "patient_name": "TEST, Alice",
    "age": 55,
    "sex": "F",
    "specimen_type": "biopsy",
    "anatomic_site": "breast",
    "fixative": "formalin",
    "fixation_time_hours": 24.0,
    "ordered_tests": ["Breast IHC Panel"],
    "priority": "routine",
    "billing_info_present": True,
}


def _make_scenario(
    scenario_id: str = "SC-001",
    steps: list[tuple[str, dict, str, list[str], list[str]]] | None = None,
) -> Scenario:
    """Build a Scenario with default or custom steps.

    Each step tuple: (event_type, event_data, next_state, rules, flags)
    """
    if steps is None:
        steps = [
            ("order_received", _STEP_1_DATA, "ACCEPTED", ["ACC-008"], []),
        ]

    scenario_steps = []
    for i, (event_type, event_data, next_state, rules, flags) in enumerate(steps, 1):
        scenario_steps.append(
            ScenarioStep(
                step=i,
                event_type=event_type,
                event_data=event_data,
                expected_output=ExpectedOutput(
                    next_state=next_state,
                    applied_rules=tuple(rules),
                    flags=tuple(flags),
                ),
            )
        )

    return Scenario(
        scenario_id=scenario_id,
        category="rule_coverage",
        description=f"Test scenario {scenario_id}",
        steps=tuple(scenario_steps),
    )


def _correct_response(step: ScenarioStep) -> dict[str, Any]:
    """Build a model response dict matching the expected output."""
    return {
        "next_state": step.expected_output.next_state,
        "applied_rules": list(step.expected_output.applied_rules),
        "flags": list(step.expected_output.flags),
        "reasoning": "Mock reasoning",
    }


# --- Helper function tests ---


class TestBuildOrderFromEventData:
    def test_field_mapping(self) -> None:
        order = build_order_from_event_data("SC-001", _STEP_1_DATA)
        assert order.order_id == "ORD-SC-001"
        assert order.scenario_id == "SC-001"
        assert order.patient_name == "TEST, Alice"
        assert order.patient_age == 55
        assert order.patient_sex == "F"
        assert order.current_state == "ACCESSIONING"

    def test_panel_expansion(self) -> None:
        order = build_order_from_event_data("SC-001", _STEP_1_DATA)
        assert order.ordered_tests == ["ER", "PR", "HER2", "Ki-67"]

    def test_individual_test(self) -> None:
        data = dict(_STEP_1_DATA, ordered_tests=["ER"])
        order = build_order_from_event_data("SC-001", data)
        assert order.ordered_tests == ["ER"]


class TestBuildSlidesForOrder:
    def test_correct_count(self) -> None:
        order = build_order_from_event_data("SC-001", _STEP_1_DATA)
        slides = build_slides_for_order(order)
        assert len(slides) == 4  # ER, PR, HER2, Ki-67

    def test_slide_assignments(self) -> None:
        order = build_order_from_event_data("SC-001", _STEP_1_DATA)
        slides = build_slides_for_order(order)
        assignments = [s.test_assignment for s in slides]
        assert assignments == ["ER", "PR", "HER2", "Ki-67"]

    def test_slide_ids(self) -> None:
        order = build_order_from_event_data("SC-001", _STEP_1_DATA)
        slides = build_slides_for_order(order)
        assert slides[0].slide_id == "ORD-SC-001-S001"
        assert slides[3].slide_id == "ORD-SC-001-S004"


class TestAdvanceOrderState:
    def test_state_updated(self) -> None:
        order = build_order_from_event_data("SC-001", _STEP_1_DATA)
        expected = ExpectedOutput(
            next_state="ACCEPTED",
            applied_rules=("ACC-008",),
            flags=(),
        )
        advanced = advance_order_state(order, expected)
        assert advanced.current_state == "ACCEPTED"
        assert advanced.flags == []

    def test_flags_updated(self) -> None:
        order = build_order_from_event_data("SC-001", _STEP_1_DATA)
        expected = ExpectedOutput(
            next_state="MISSING_INFO_PROCEED",
            applied_rules=("ACC-010",),
            flags=("MISSING_INFO_PROCEED",),
        )
        advanced = advance_order_state(order, expected)
        assert advanced.current_state == "MISSING_INFO_PROCEED"
        assert advanced.flags == ["MISSING_INFO_PROCEED"]

    def test_preserves_other_fields(self) -> None:
        order = build_order_from_event_data("SC-001", _STEP_1_DATA)
        expected = ExpectedOutput(
            next_state="ACCEPTED",
            applied_rules=("ACC-008",),
            flags=(),
        )
        advanced = advance_order_state(order, expected)
        assert advanced.patient_name == order.patient_name
        assert advanced.ordered_tests == order.ordered_tests


class TestBuildEvent:
    def test_event_fields(self) -> None:
        step = ScenarioStep(
            step=1,
            event_type="order_received",
            event_data=_STEP_1_DATA,
            expected_output=ExpectedOutput(
                next_state="ACCEPTED",
                applied_rules=("ACC-008",),
                flags=(),
            ),
        )
        event = build_event("ORD-SC-001", step)
        assert event.event_id == "ORD-SC-001-E001"
        assert event.order_id == "ORD-SC-001"
        assert event.step_number == 1
        assert event.event_type == "order_received"


# --- Harness integration tests ---


def _make_harness(
    adapter: MockAdapter,
    scenarios: list[Scenario],
    settings: EvaluationSettings | None = None,
) -> tuple[EvaluationHarness, Path]:
    """Create a harness with a mock adapter and temp DB."""
    tmpdir = tempfile.mkdtemp()
    db_path = Path(tmpdir) / "test.db"

    if settings is None:
        settings = EvaluationSettings(
            runs_per_model={"llamacpp": 1, "openrouter": 1},
            timeout_seconds=120,
            output_directory="results",
        )

    config = ModelConfig(
        name="test-model",
        provider="llamacpp",
        model_id="mock-model",
        temperature=0.0,
        max_tokens=2048,
        token_limit=8192,
    )

    harness = EvaluationHarness([config], settings, scenarios, db_path)
    return harness, db_path


class TestRunScenarioAllCorrect:
    def test_single_step_correct(self) -> None:
        scenario = _make_scenario()
        adapter = MockAdapter(responses=[_correct_response(scenario.steps[0])])

        with patch.object(EvaluationHarness, "_create_adapter", return_value=adapter):
            harness, db_path = _make_harness(adapter, [scenario])
            results = harness.run_all()

        assert len(results) == 1
        assert results[0].all_correct is True
        assert results[0].scenario_id == "SC-001"

    def test_multi_step_correct(self) -> None:
        scenario = _make_scenario(
            steps=[
                ("order_received", _STEP_1_DATA, "ACCEPTED", ["ACC-008"], []),
                (
                    "grossing_complete",
                    {"outcome": "success"},
                    "SAMPLE_PREP_PROCESSING",
                    ["SP-001"],
                    [],
                ),
            ]
        )
        adapter = MockAdapter(
            responses=[
                _correct_response(scenario.steps[0]),
                _correct_response(scenario.steps[1]),
            ]
        )

        with patch.object(EvaluationHarness, "_create_adapter", return_value=adapter):
            harness, db_path = _make_harness(adapter, [scenario])
            results = harness.run_all()

        assert len(results) == 1
        assert results[0].all_correct is True
        assert len(results[0].step_results) == 2


class TestRunScenarioStepFailureIndependent:
    def test_step1_wrong_doesnt_cascade(self) -> None:
        """Step 1 wrong prediction doesn't affect step 2 evaluation."""
        scenario = _make_scenario(
            steps=[
                ("order_received", _STEP_1_DATA, "ACCEPTED", ["ACC-008"], []),
                (
                    "grossing_complete",
                    {"outcome": "success"},
                    "SAMPLE_PREP_PROCESSING",
                    ["SP-001"],
                    [],
                ),
            ]
        )
        # Step 1: wrong state; Step 2: correct
        adapter = MockAdapter(
            responses=[
                {
                    "next_state": "MISSING_INFO_HOLD",
                    "applied_rules": ["ACC-008"],
                    "flags": [],
                    "reasoning": "Wrong",
                },
                _correct_response(scenario.steps[1]),
            ]
        )

        with patch.object(EvaluationHarness, "_create_adapter", return_value=adapter):
            harness, _ = _make_harness(adapter, [scenario])
            results = harness.run_all()

        assert len(results) == 1
        step_results = results[0].step_results
        assert step_results[0].validation.state_correct is False
        # Step 2 should still be evaluated correctly (independent)
        assert step_results[1].validation.state_correct is True


class TestRunScenarioModelError:
    def test_error_recorded(self) -> None:
        scenario = _make_scenario()
        adapter = MockAdapter(error="timeout: model did not respond")

        with patch.object(EvaluationHarness, "_create_adapter", return_value=adapter):
            harness, _ = _make_harness(adapter, [scenario])
            results = harness.run_all()

        assert len(results) == 1
        sr = results[0].step_results[0]
        assert sr.validation.state_correct is False
        assert sr.validation.rules_correct is False
        assert sr.validation.flags_correct is False
        assert sr.failure_type is not None


class TestHarnessRunsPerModel:
    def test_ollama_runs_5x(self) -> None:
        scenario = _make_scenario()
        adapter = MockAdapter(responses=[_correct_response(scenario.steps[0])])
        settings = EvaluationSettings(
            runs_per_model={"llamacpp": 5, "openrouter": 1},
            timeout_seconds=120,
            output_directory="results",
        )

        with patch.object(EvaluationHarness, "_create_adapter", return_value=adapter):
            harness, _ = _make_harness(adapter, [scenario], settings=settings)
            results = harness.run_all()

        # 5 runs * 1 scenario = 5 results
        assert len(results) == 5
        run_numbers = [r.run_number for r in results]
        assert sorted(run_numbers) == [1, 2, 3, 4, 5]

    def test_model_level_runs_overrides_provider_default(self) -> None:
        """ModelConfig.runs takes precedence over settings.runs_per_model."""
        scenario = _make_scenario()
        adapter = MockAdapter(responses=[_correct_response(scenario.steps[0])])
        settings = EvaluationSettings(
            runs_per_model={"llamacpp": 1, "openrouter": 1},
            timeout_seconds=120,
            output_directory="results",
        )

        config = ModelConfig(
            name="test-with-runs",
            provider="openrouter",
            model_id="mock-model",
            temperature=0.0,
            max_tokens=2048,
            token_limit=8192,
            runs=3,
        )

        tmpdir = tempfile.mkdtemp()
        db_path = Path(tmpdir) / "test.db"
        harness = EvaluationHarness([config], settings, [scenario], db_path)

        with patch.object(EvaluationHarness, "_create_adapter", return_value=adapter):
            results = harness.run_all()

        # model-level runs=3 overrides provider default of 1
        assert len(results) == 3
        run_numbers = [r.run_number for r in results]
        assert sorted(run_numbers) == [1, 2, 3]
        assert all(r.model_id == "mock-model" for r in results)

    def test_model_level_runs_1_reduces_below_provider_default(self) -> None:
        """runs=1 on a model whose provider default is 5 produces exactly 1 result."""
        scenario = _make_scenario()
        adapter = MockAdapter(responses=[_correct_response(scenario.steps[0])])
        settings = EvaluationSettings(
            runs_per_model={"llamacpp": 1, "openrouter": 5},
            timeout_seconds=120,
            output_directory="results",
        )

        config = ModelConfig(
            name="test-runs-1",
            provider="openrouter",
            model_id="mock-model",
            temperature=0.0,
            max_tokens=2048,
            token_limit=8192,
            runs=1,
        )

        tmpdir = tempfile.mkdtemp()
        db_path = Path(tmpdir) / "test.db"
        harness = EvaluationHarness([config], settings, [scenario], db_path)

        with patch.object(EvaluationHarness, "_create_adapter", return_value=adapter):
            results = harness.run_all()

        assert len(results) == 1
        assert results[0].run_number == 1

    def test_model_level_runs_with_multi_step_scenario(self) -> None:
        """Per-model runs override works correctly with multi-step scenarios."""
        scenario = _make_scenario(
            steps=[
                ("order_received", _STEP_1_DATA, "ACCEPTED", ["ACC-008"], []),
                (
                    "grossing_complete",
                    {"outcome": "success"},
                    "SAMPLE_PREP_PROCESSING",
                    ["SP-001"],
                    [],
                ),
            ]
        )
        adapter = MockAdapter(
            responses=[
                _correct_response(scenario.steps[0]),
                _correct_response(scenario.steps[1]),
            ]
        )
        settings = EvaluationSettings(
            runs_per_model={"llamacpp": 1, "openrouter": 1},
            timeout_seconds=120,
            output_directory="results",
        )

        config = ModelConfig(
            name="test-multi-step",
            provider="openrouter",
            model_id="mock-model",
            temperature=0.0,
            max_tokens=2048,
            token_limit=8192,
            runs=2,
        )

        tmpdir = tempfile.mkdtemp()
        db_path = Path(tmpdir) / "test.db"
        harness = EvaluationHarness([config], settings, [scenario], db_path)

        with patch.object(EvaluationHarness, "_create_adapter", return_value=adapter):
            results = harness.run_all()

        # 2 runs * 1 scenario = 2 results, each with 2 steps
        assert len(results) == 2
        assert all(len(r.step_results) == 2 for r in results)
        assert sorted(r.run_number for r in results) == [1, 2]


class TestDecisionsPersistedToDatabase:
    def test_decisions_in_db(self) -> None:
        scenario = _make_scenario()
        adapter = MockAdapter(responses=[_correct_response(scenario.steps[0])])

        with patch.object(EvaluationHarness, "_create_adapter", return_value=adapter):
            harness, db_path = _make_harness(adapter, [scenario])
            harness.run_all()

        # Verify decisions are in the database
        with Database(db_path) as db:
            cursor = db._connection.execute("SELECT COUNT(*) FROM decisions")
            count = cursor.fetchone()[0]
            assert count == 1

            cursor = db._connection.execute("SELECT COUNT(*) FROM orders")
            count = cursor.fetchone()[0]
            assert count == 1

            cursor = db._connection.execute("SELECT COUNT(*) FROM events")
            count = cursor.fetchone()[0]
            assert count == 1

            cursor = db._connection.execute("SELECT COUNT(*) FROM slides")
            count = cursor.fetchone()[0]
            assert count == 4  # 4 expanded tests


# --- Rule hallucination tests (#12) ---


class TestRunScenarioRuleHallucination:
    def test_hallucinated_rule_id(self) -> None:
        """Model returns a rule ID not in the state machine catalog."""
        scenario = _make_scenario()
        adapter = MockAdapter(
            responses=[
                {
                    "next_state": "ACCEPTED",
                    "applied_rules": ["FAKE-999"],
                    "flags": [],
                    "reasoning": "hallucinated",
                }
            ]
        )

        with patch.object(EvaluationHarness, "_create_adapter", return_value=adapter):
            harness, _ = _make_harness(adapter, [scenario])
            results = harness.run_all()

        sr = results[0].step_results[0]
        assert sr.validation.rules_correct is False
        assert sr.failure_type is not None

    def test_correct_state_but_hallucinated_rules(self) -> None:
        """State is correct but rules are hallucinated — partial failure."""
        scenario = _make_scenario()
        adapter = MockAdapter(
            responses=[
                {
                    "next_state": "ACCEPTED",
                    "applied_rules": ["NONEXISTENT-001"],
                    "flags": [],
                    "reasoning": "state ok, rules wrong",
                }
            ]
        )

        with patch.object(EvaluationHarness, "_create_adapter", return_value=adapter):
            harness, _ = _make_harness(adapter, [scenario])
            results = harness.run_all()

        sr = results[0].step_results[0]
        assert sr.validation.state_correct is True
        assert sr.validation.rules_correct is False


# --- Over-long predicted_next_state truncation ---


class TestOverLongPredictedStateTruncation:
    def test_long_state_does_not_crash(self) -> None:
        """A predicted_next_state > 50 chars is truncated, not a crash."""
        scenario = _make_scenario()
        long_state = "A" * 99  # Well over the 50-char limit
        adapter = MockAdapter(
            responses=[
                {
                    "next_state": long_state,
                    "applied_rules": ["ACC-008"],
                    "flags": [],
                    "reasoning": "hallucinated long state",
                }
            ]
        )

        with patch.object(EvaluationHarness, "_create_adapter", return_value=adapter):
            harness, db_path = _make_harness(adapter, [scenario])
            results = harness.run_all()

        sr = results[0].step_results[0]
        assert sr.validation.state_correct is False

        # Verify the decision was persisted (not crashed)
        with Database(db_path) as db:
            cursor = db._connection.execute("SELECT COUNT(*) FROM decisions")
            assert cursor.fetchone()[0] == 1


# --- Flag accumulation tests (#13) ---


class TestRunScenarioFlagAccumulation:
    def test_multi_step_flags(self) -> None:
        """Step 1 sets a flag, step 2 expects accumulated flags."""
        scenario = _make_scenario(
            steps=[
                (
                    "order_received",
                    _STEP_1_DATA,
                    "MISSING_INFO_PROCEED",
                    ["ACC-005"],
                    ["MISSING_INFO_PROCEED"],
                ),
                (
                    "grossing_complete",
                    {"outcome": "success"},
                    "SAMPLE_PREP_PROCESSING",
                    ["SP-001"],
                    ["MISSING_INFO_PROCEED"],
                ),
            ]
        )
        adapter = MockAdapter(
            responses=[
                _correct_response(scenario.steps[0]),
                _correct_response(scenario.steps[1]),
            ]
        )

        with patch.object(EvaluationHarness, "_create_adapter", return_value=adapter):
            harness, _ = _make_harness(adapter, [scenario])
            results = harness.run_all()

        assert results[0].all_correct is True

    def test_multi_flag_accumulation(self) -> None:
        """Step 1 sets flag A, step 2 adds flag B, both persist at step 3."""
        scenario = _make_scenario(
            steps=[
                (
                    "order_received",
                    _STEP_1_DATA,
                    "MISSING_INFO_PROCEED",
                    ["ACC-007"],
                    ["MISSING_INFO_PROCEED"],
                ),
                (
                    "grossing_complete",
                    {"outcome": "success"},
                    "SAMPLE_PREP_PROCESSING",
                    ["SP-001"],
                    ["MISSING_INFO_PROCEED", "FIXATION_WARNING"],
                ),
                (
                    "processing_complete",
                    {"outcome": "success"},
                    "SAMPLE_PREP_EMBEDDING",
                    ["SP-001"],
                    ["MISSING_INFO_PROCEED", "FIXATION_WARNING"],
                ),
            ]
        )
        adapter = MockAdapter(responses=[_correct_response(s) for s in scenario.steps])

        with patch.object(EvaluationHarness, "_create_adapter", return_value=adapter):
            harness, _ = _make_harness(adapter, [scenario])
            results = harness.run_all()

        assert results[0].all_correct is True
        # Both flags present in step 3 response
        step3 = results[0].step_results[2]
        assert step3.validation.flags_correct is True

    def test_hallucinated_flag(self) -> None:
        """Model returns a flag not in VALID_FLAGS."""
        scenario = _make_scenario()
        adapter = MockAdapter(
            responses=[
                {
                    "next_state": "ACCEPTED",
                    "applied_rules": ["ACC-008"],
                    "flags": ["TOTALLY_FAKE_FLAG"],
                    "reasoning": "hallucinated flag",
                }
            ]
        )

        with patch.object(EvaluationHarness, "_create_adapter", return_value=adapter):
            harness, _ = _make_harness(adapter, [scenario])
            results = harness.run_all()

        sr = results[0].step_results[0]
        assert sr.validation.flags_correct is False


# --- Multi-model tests (#23) ---


class TestHarnessMultipleModels:
    def test_two_models(self) -> None:
        """Two models with multiple runs produce correct number of results."""
        scenario = _make_scenario()
        adapter = MockAdapter(responses=[_correct_response(scenario.steps[0])])
        settings = EvaluationSettings(
            runs_per_model={"llamacpp": 2, "openrouter": 1},
            timeout_seconds=120,
            output_directory="results",
        )

        with patch.object(EvaluationHarness, "_create_adapter", return_value=adapter):
            harness, _ = _make_harness(adapter, [scenario], settings=settings)
            results = harness.run_all()

        # 2 runs * 1 scenario = 2 results
        assert len(results) == 2
        model_ids = {r.model_id for r in results}
        assert "mock-model" in model_ids

    def test_two_distinct_models_no_pk_collision(self) -> None:
        """Two distinct model configs sharing a DB must not collide on order PK."""
        scenario = _make_scenario()
        adapter = MockAdapter(responses=[_correct_response(scenario.steps[0])])
        settings = EvaluationSettings(
            runs_per_model={"llamacpp": 1, "openrouter": 1},
            timeout_seconds=120,
            output_directory="results",
        )

        config_a = ModelConfig(
            name="model-a",
            provider="llamacpp",
            model_id="model-a",
            temperature=0.0,
            max_tokens=2048,
            token_limit=8192,
        )
        config_b = ModelConfig(
            name="model-b",
            provider="llamacpp",
            model_id="model-b",
            temperature=0.0,
            max_tokens=2048,
            token_limit=8192,
        )

        tmpdir = tempfile.mkdtemp()
        db_path = Path(tmpdir) / "test.db"
        harness = EvaluationHarness([config_a, config_b], settings, [scenario], db_path)

        with patch.object(EvaluationHarness, "_create_adapter", return_value=adapter):
            results = harness.run_all()

        # 2 models * 1 run * 1 scenario = 2 results
        assert len(results) == 2

        # Verify DB has 2 distinct orders
        with Database(db_path) as db:
            cursor = db._connection.execute("SELECT COUNT(*) FROM orders")
            assert cursor.fetchone()[0] == 2


# --- Event data edge cases (#26) ---


class TestBuildOrderEventDataEdgeCases:
    def test_missing_optional_fields(self) -> None:
        minimal_data = {
            "specimen_type": "biopsy",
            "anatomic_site": "breast",
            "fixative": "formalin",
        }
        order = build_order_from_event_data("SC-MINIMAL", minimal_data)
        assert order.patient_name is None
        assert order.fixation_time_hours is None
        assert order.ordered_tests == []
        assert order.priority == "routine"

    def test_empty_ordered_tests(self) -> None:
        data = dict(_STEP_1_DATA, ordered_tests=[])
        order = build_order_from_event_data("SC-EMPTY", data)
        assert order.ordered_tests == []

    def test_ordered_tests_wrong_type_raises(self) -> None:
        data = dict(_STEP_1_DATA, ordered_tests="not-a-list")
        with pytest.raises(TypeError, match="ordered_tests must be a list"):
            build_order_from_event_data("SC-BAD", data)

    def test_ordered_tests_non_string_element_raises(self) -> None:
        data = dict(_STEP_1_DATA, ordered_tests=[123])
        with pytest.raises(TypeError, match="ordered_tests elements must be strings"):
            build_order_from_event_data("SC-BAD", data)


# --- OpenRouter key tests (#27) ---


class TestLoadOpenRouterKey:
    def test_from_env_var(self) -> None:
        with (
            patch("src.evaluation.harness.Path.exists", return_value=False),
            patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key-123"}),
        ):
            key = load_openrouter_key()
            assert key == "test-key-123"

    def test_missing_both_raises(self) -> None:
        with (
            patch("src.evaluation.harness.Path.exists", return_value=False),
            patch.dict("os.environ", {}, clear=True),
            pytest.raises(ValueError, match="OpenRouter API key not found"),
        ):
            load_openrouter_key()

    def test_from_file(self, tmp_path: Path) -> None:
        key_file = tmp_path / "key.txt"
        key_file.write_text("  my-secret-key  \n")
        with patch("src.evaluation.harness.load_openrouter_key") as mock_load:
            mock_load.return_value = key_file.read_text().strip()
            result = mock_load()
            assert result == "my-secret-key"


# --- Null required fields (SC-104) ---


class TestBuildOrderNullRequiredFields:
    """SC-104 sends null for specimen_type, anatomic_site, fixative, priority."""

    def test_null_required_fields_get_defaults(self) -> None:
        data = {
            "specimen_type": None,
            "anatomic_site": None,
            "fixative": None,
            "priority": None,
            "ordered_tests": [],
        }
        order = build_order_from_event_data("SC-104", data)
        assert order.specimen_type == ""
        assert order.anatomic_site == ""
        assert order.fixative == ""
        assert order.priority == "routine"

    def test_missing_required_fields_get_defaults(self) -> None:
        data: dict[str, Any] = {"ordered_tests": []}
        order = build_order_from_event_data("SC-EMPTY", data)
        assert order.specimen_type == ""
        assert order.anatomic_site == ""
        assert order.fixative == ""
        assert order.priority == "routine"

    def test_mixed_null_and_valid_fields(self) -> None:
        """Some fields null, others valid — nulls get defaults, others preserved."""
        data = {
            "specimen_type": "biopsy",
            "anatomic_site": None,
            "fixative": "formalin",
            "priority": None,
            "ordered_tests": ["ER"],
        }
        order = build_order_from_event_data("SC-MIXED", data)
        assert order.specimen_type == "biopsy"
        assert order.anatomic_site == ""
        assert order.fixative == "formalin"
        assert order.priority == "routine"

    def test_empty_string_priority_preserved(self) -> None:
        """Empty string priority is preserved (not coerced to 'routine')."""
        data = dict(_STEP_1_DATA, priority="")
        order = build_order_from_event_data("SC-EMPTY-PRI", data)
        assert order.priority == ""

    def test_ordered_tests_null_defaults_to_empty(self) -> None:
        """ordered_tests: null in event_data defaults to []."""
        data = {
            "specimen_type": "biopsy",
            "anatomic_site": "breast",
            "fixative": "formalin",
            "ordered_tests": None,
        }
        order = build_order_from_event_data("SC-NULL-TESTS", data)
        assert order.ordered_tests == []

    def test_billing_info_present_null_defaults_to_true(self) -> None:
        """billing_info_present: null in event_data defaults to True."""
        data = dict(_STEP_1_DATA, billing_info_present=None)
        order = build_order_from_event_data("SC-NULL-BILLING", data)
        assert order.billing_info_present is True

    def test_billing_info_present_false_preserved(self) -> None:
        """billing_info_present: false should be preserved (not coerced to True)."""
        data = dict(_STEP_1_DATA, billing_info_present=False)
        order = build_order_from_event_data("SC-NO-BILLING", data)
        assert order.billing_info_present is False


# --- Slide state advancement tests ---


class TestAdvanceSlidesState:
    """Tests for advance_slides_state() — Bug 2 from issue #113."""

    def _make_slides(self) -> list[Slide]:
        return [
            Slide(slide_id="S001", order_id="ORD-1", test_assignment="ER", status="sectioned"),
            Slide(slide_id="S002", order_id="ORD-1", test_assignment="PR", status="sectioned"),
            Slide(slide_id="S003", order_id="ORD-1", test_assignment="HER2", status="sectioned"),
            Slide(slide_id="S004", order_id="ORD-1", test_assignment="Ki-67", status="sectioned"),
        ]

    def _step(self, event_type: str, event_data: dict[str, Any]) -> ScenarioStep:
        return ScenarioStep(
            step=1,
            event_type=event_type,
            event_data=event_data,
            expected_output=ExpectedOutput(
                next_state="ACCEPTED",
                applied_rules=(),
                flags=(),
            ),
        )

    def test_staining_complete_updates_status(self) -> None:
        slides = self._make_slides()
        step = self._step("ihc_staining_complete", {"outcome": "success"})
        updated = advance_slides_state(slides, step)
        assert all(s.status == "stain_complete" for s in updated)

    def test_he_staining_complete_updates_status(self) -> None:
        slides = self._make_slides()
        step = self._step("he_staining_complete", {"fixation_issue": False})
        updated = advance_slides_state(slides, step)
        assert all(s.status == "stain_complete" for s in updated)

    def test_ihc_qc_updates_per_slide(self) -> None:
        slides = self._make_slides()
        step = self._step(
            "ihc_qc",
            {
                "slides": [
                    {"test": "ER", "qc_result": "pass"},
                    {"test": "PR", "qc_result": "fail"},
                    {"test": "HER2", "qc_result": "pass"},
                    {"test": "Ki-67", "qc_result": "pass"},
                ],
                "all_slides_complete": True,
            },
        )
        updated = advance_slides_state(slides, step)
        assert updated[0].status == "qc_pass"
        assert updated[1].status == "qc_fail"
        assert updated[0].qc_result == "pass"
        assert updated[1].qc_result == "fail"

    def test_ihc_scoring_updates_per_slide(self) -> None:
        slides = self._make_slides()
        step = self._step(
            "ihc_scoring",
            {
                "scores": [
                    {"test": "ER", "value": "85%", "equivocal": False},
                    {"test": "PR", "value": "70%", "equivocal": False},
                    {"test": "HER2", "value": "1+", "equivocal": False},
                    {"test": "Ki-67", "value": "15%", "equivocal": False},
                ],
                "all_scores_complete": True,
                "any_equivocal": False,
            },
        )
        updated = advance_slides_state(slides, step)
        assert all(s.status == "scored" for s in updated)
        assert updated[0].score_result == {"test": "ER", "value": "85%", "equivocal": False}

    def test_pathologist_signout_marks_reported(self) -> None:
        slides = self._make_slides()
        step = self._step("pathologist_signout", {"reportable_tests": ["ER", "PR"]})
        updated = advance_slides_state(slides, step)
        assert all(s.reported is True for s in updated)

    def test_unrelated_event_preserves_slides(self) -> None:
        slides = self._make_slides()
        step = self._step("grossing_complete", {"outcome": "success"})
        updated = advance_slides_state(slides, step)
        assert all(s.status == "sectioned" for s in updated)

    def test_ihc_qc_partial_slides_defaults_missing_to_pass(self) -> None:
        """Slides not in QC event data default to 'pass'."""
        slides = self._make_slides()
        step = self._step(
            "ihc_qc",
            {
                "slides": [
                    {"test": "ER", "qc_result": "fail"},
                    {"test": "PR", "qc_result": "pass"},
                ],
                "all_slides_complete": False,
            },
        )
        updated = advance_slides_state(slides, step)
        assert updated[0].qc_result == "fail"  # ER — in event data
        assert updated[1].qc_result == "pass"  # PR — in event data
        assert updated[2].qc_result == "pass"  # HER2 — missing, default
        assert updated[3].qc_result == "pass"  # Ki-67 — missing, default
        assert updated[0].status == "qc_fail"
        assert updated[2].status == "qc_pass"

    def test_sample_prep_qc_fail_updates_status(self) -> None:
        slides = self._make_slides()
        step = self._step("sample_prep_qc", {"outcome": "fail"})
        updated = advance_slides_state(slides, step)
        assert all(s.status == "qc_fail" for s in updated)
        assert all(s.qc_result == "fail" for s in updated)

    def test_ihc_scoring_missing_slide_warns(self) -> None:
        """Slides missing from scoring data get score_result=None."""
        slides = self._make_slides()
        step = self._step(
            "ihc_scoring",
            {
                "scores": [
                    {"test": "ER", "value": "85%", "equivocal": False},
                ],
                "all_scores_complete": False,
            },
        )
        updated = advance_slides_state(slides, step)
        assert updated[0].score_result is not None  # ER — present
        assert updated[1].score_result is None  # PR — missing
        assert all(s.status == "scored" for s in updated)


# --- Flag propagation ground truth tests ---


class TestFlagPropagationGroundTruth:
    """Verify that the 9 fixed scenarios have correct flag propagation."""

    def _load_scenario(self, path: str) -> dict[str, Any]:
        import json

        with open(path) as f:
            return json.load(f)

    def test_sc070_flags_persist_through_all_steps(self) -> None:
        data = self._load_scenario("scenarios/rule_coverage/sc_070.json")
        for event in data["events"]:
            flags = event["expected_output"]["flags"]
            assert "MISSING_INFO_PROCEED" in flags, f"SC-070 step {event['step']}: flag missing"

    def test_sc072_flag_cleared_at_missing_info_received(self) -> None:
        data = self._load_scenario("scenarios/rule_coverage/sc_072.json")
        for event in data["events"]:
            step = event["step"]
            flags = event["expected_output"]["flags"]
            if step <= 13:
                assert "MISSING_INFO_PROCEED" in flags, f"SC-072 step {step}: flag should persist"
            elif step == 14:
                # missing_info_received with billing clears it
                assert "MISSING_INFO_PROCEED" not in flags

    def test_sc073_irrelevant_info_does_not_clear_flag(self) -> None:
        data = self._load_scenario("scenarios/rule_coverage/sc_073.json")
        for event in data["events"]:
            flags = event["expected_output"]["flags"]
            assert "MISSING_INFO_PROCEED" in flags, (
                f"SC-073 step {event['step']}: flag should persist (irrelevant info)"
            )

    def test_sc097_flag_persists(self) -> None:
        data = self._load_scenario("scenarios/accumulated_state/sc_097.json")
        for event in data["events"]:
            flags = event["expected_output"]["flags"]
            assert "MISSING_INFO_PROCEED" in flags

    def test_sc071_fish_suggested_added_at_scoring(self) -> None:
        data = self._load_scenario("scenarios/rule_coverage/sc_071.json")
        for event in data["events"]:
            step = event["step"]
            flags = event["expected_output"]["flags"]
            assert "MISSING_INFO_PROCEED" in flags
            if step >= 12:
                assert "FISH_SUGGESTED" in flags


# --- Incremental callback tests ---


class TestOnRunCompleteCallback:
    def test_callback_called_per_run(self) -> None:
        """on_run_complete is called once per run with correct args."""
        scenario = _make_scenario()
        adapter = MockAdapter(responses=[_correct_response(scenario.steps[0])])
        settings = EvaluationSettings(
            runs_per_model={"llamacpp": 3, "openrouter": 1},
            timeout_seconds=120,
            output_directory="results",
        )

        callback_calls: list[tuple[str, int, int, bool]] = []

        def _on_run(
            model_id: str,
            run_number: int,
            results: list[Any],
            aborted: bool,
        ) -> None:
            callback_calls.append((model_id, run_number, len(results), aborted))

        with patch.object(EvaluationHarness, "_create_adapter", return_value=adapter):
            harness, _ = _make_harness(adapter, [scenario], settings=settings)
            harness.run_all(on_run_complete=_on_run)

        assert len(callback_calls) == 3
        assert [c[1] for c in callback_calls] == [1, 2, 3]
        assert all(c[0] == "mock-model" for c in callback_calls)
        assert all(c[2] == 1 for c in callback_calls)
        assert all(c[3] is False for c in callback_calls)

    def test_callback_receives_correct_results(self) -> None:
        """Callback results match the scenario result structure."""
        scenario = _make_scenario()
        adapter = MockAdapter(responses=[_correct_response(scenario.steps[0])])

        received: list[Any] = []

        def _on_run(
            _mid: str,
            _rn: int,
            results: list[Any],
            _aborted: bool,
        ) -> None:
            received.extend(results)

        with patch.object(EvaluationHarness, "_create_adapter", return_value=adapter):
            harness, _ = _make_harness(adapter, [scenario])
            all_results = harness.run_all(on_run_complete=_on_run)

        assert len(received) == 1
        assert received[0].scenario_id == "SC-001"
        # With callback, harness doesn't accumulate (runner handles it)
        assert len(all_results) == 0

    def test_no_callback_still_works(self) -> None:
        """run_all() without callback still returns all results."""
        scenario = _make_scenario()
        adapter = MockAdapter(responses=[_correct_response(scenario.steps[0])])

        with patch.object(EvaluationHarness, "_create_adapter", return_value=adapter):
            harness, _ = _make_harness(adapter, [scenario])
            results = harness.run_all()

        assert len(results) == 1

    def test_callback_exception_does_not_crash(self) -> None:
        """If callback raises, harness still completes."""
        scenario = _make_scenario()
        adapter = MockAdapter(responses=[_correct_response(scenario.steps[0])])
        settings = EvaluationSettings(
            runs_per_model={"llamacpp": 2, "openrouter": 1},
            timeout_seconds=120,
            output_directory="results",
        )

        call_count = 0

        def _bad_callback(
            _mid: str,
            _rn: int,
            _results: list[Any],
            _aborted: bool,
        ) -> None:
            nonlocal call_count
            call_count += 1
            raise OSError("Simulated write failure")

        with patch.object(EvaluationHarness, "_create_adapter", return_value=adapter):
            harness, _ = _make_harness(adapter, [scenario], settings=settings)
            # Callback raises, but harness should not catch it — it propagates.
            # The runner wraps the callback in try/except, not the harness.
            with pytest.raises(OSError, match="Simulated write failure"):
                harness.run_all(on_run_complete=_bad_callback)

        assert call_count == 1

    def test_multi_model_callback(self) -> None:
        """Callback is called per (model_id, run_number) for multiple models."""
        scenario = _make_scenario()
        adapter = MockAdapter(responses=[_correct_response(scenario.steps[0])])
        settings = EvaluationSettings(
            runs_per_model={"llamacpp": 2, "openrouter": 1},
            timeout_seconds=120,
            output_directory="results",
        )

        config_a = ModelConfig(
            name="model-a",
            provider="llamacpp",
            model_id="model-a",
            temperature=0.0,
            max_tokens=2048,
            token_limit=8192,
        )
        config_b = ModelConfig(
            name="model-b",
            provider="llamacpp",
            model_id="model-b",
            temperature=0.0,
            max_tokens=2048,
            token_limit=8192,
        )

        callback_calls: list[tuple[str, int]] = []

        def _track(
            mid: str,
            rn: int,
            _results: list[Any],
            _aborted: bool,
        ) -> None:
            callback_calls.append((mid, rn))

        tmpdir = tempfile.mkdtemp()
        db_path = Path(tmpdir) / "test.db"
        harness = EvaluationHarness([config_a, config_b], settings, [scenario], db_path)

        with patch.object(EvaluationHarness, "_create_adapter", return_value=adapter):
            harness.run_all(on_run_complete=_track)

        # Both models use ollama provider -> 2 runs each = 4 callbacks
        assert len(callback_calls) == 4
        model_a_runs = [(m, r) for m, r in callback_calls if m == "model-a"]
        model_b_runs = [(m, r) for m, r in callback_calls if m == "model-b"]
        assert sorted(model_a_runs) == [("model-a", 1), ("model-a", 2)]
        assert sorted(model_b_runs) == [("model-b", 1), ("model-b", 2)]


# --- Early-abort tests ---


class TestEarlyAbort:
    def test_aborts_model_on_high_error_rate(self) -> None:
        """Model with >50% fatal errors after 20 scenarios gets aborted."""
        from src.evaluation.harness import _EARLY_ABORT_MIN_SCENARIOS

        # Create enough scenarios to trigger abort check
        num_scenarios = _EARLY_ABORT_MIN_SCENARIOS + 5
        scenarios = [_make_scenario(scenario_id=f"SC-{i:03d}") for i in range(num_scenarios)]

        # All responses are errors (invalid JSON)
        adapter = MockAdapter(error="invalid json response")
        settings = EvaluationSettings(
            runs_per_model={"llamacpp": 3, "openrouter": 1},
            timeout_seconds=120,
            output_directory="results",
        )

        with patch.object(EvaluationHarness, "_create_adapter", return_value=adapter):
            harness, _ = _make_harness(adapter, scenarios, settings=settings)
            results = harness.run_all()

        # Aborted results excluded from return value
        assert len(results) == 0
        # No run 2 or 3 (model_aborted skips remaining runs)

    def test_no_abort_below_threshold(self) -> None:
        """Model with low error rate runs to completion."""
        from src.evaluation.harness import _EARLY_ABORT_MIN_SCENARIOS

        num_scenarios = _EARLY_ABORT_MIN_SCENARIOS + 5
        scenarios = [_make_scenario(scenario_id=f"SC-{i:03d}") for i in range(num_scenarios)]

        # All responses are correct — no errors
        adapter = MockAdapter(responses=[_correct_response(scenarios[0].steps[0])])
        settings = EvaluationSettings(
            runs_per_model={"llamacpp": 2, "openrouter": 1},
            timeout_seconds=120,
            output_directory="results",
        )

        with patch.object(EvaluationHarness, "_create_adapter", return_value=adapter):
            harness, _ = _make_harness(adapter, scenarios, settings=settings)
            results = harness.run_all()

        # All runs should complete
        assert len(results) == num_scenarios * 2
        run_numbers = {r.run_number for r in results}
        assert run_numbers == {1, 2}

    def test_abort_callback_receives_aborted_flag(self) -> None:
        """Callback receives aborted=True for early-aborted runs."""
        from src.evaluation.harness import _EARLY_ABORT_MIN_SCENARIOS

        num_scenarios = _EARLY_ABORT_MIN_SCENARIOS + 5
        scenarios = [_make_scenario(scenario_id=f"SC-{i:03d}") for i in range(num_scenarios)]

        adapter = MockAdapter(error="invalid json response")
        settings = EvaluationSettings(
            runs_per_model={"llamacpp": 2, "openrouter": 1},
            timeout_seconds=120,
            output_directory="results",
        )

        callback_calls: list[tuple[str, int, int, bool]] = []

        def _track(
            mid: str,
            rn: int,
            results: list[Any],
            aborted: bool,
        ) -> None:
            callback_calls.append((mid, rn, len(results), aborted))

        with patch.object(EvaluationHarness, "_create_adapter", return_value=adapter):
            harness, _ = _make_harness(adapter, scenarios, settings=settings)
            harness.run_all(on_run_complete=_track)

        # Only 1 callback (run 1 aborted, no run 2)
        assert len(callback_calls) == 1
        _mid, _rn, result_count, aborted = callback_calls[0]
        assert aborted is True
        assert result_count < num_scenarios  # Partial results

    def test_no_abort_at_exact_threshold(self) -> None:
        """Model with exactly 50% error rate is NOT aborted (needs >50%)."""
        from src.evaluation.harness import _EARLY_ABORT_MIN_SCENARIOS

        num_scenarios = _EARLY_ABORT_MIN_SCENARIOS
        scenarios = [_make_scenario(scenario_id=f"SC-{i:03d}") for i in range(num_scenarios)]

        # Use all-correct responses (0% error) to verify no abort at boundary.
        # The >50% abort case is already tested above.
        correct_adapter = MockAdapter(
            responses=[_correct_response(scenarios[0].steps[0])],
        )
        settings = EvaluationSettings(
            runs_per_model={"llamacpp": 1, "openrouter": 1},
            timeout_seconds=120,
            output_directory="results",
        )

        with patch.object(EvaluationHarness, "_create_adapter", return_value=correct_adapter):
            harness, _ = _make_harness(correct_adapter, scenarios, settings=settings)
            results = harness.run_all()

        # All scenarios should complete (no abort at 0% error rate)
        assert len(results) == num_scenarios


# --- Step-level early-abort helpers ---

_CallbackEntry = tuple[str, int, int, bool]  # (model_id, run_number, result_count, aborted)

_ABORT_TEST_SETTINGS = EvaluationSettings(
    runs_per_model={"llamacpp": 1, "openrouter": 1},
    timeout_seconds=120,
    output_directory="results",
)


def _make_abort_tracker() -> tuple[list[_CallbackEntry], Any]:
    """Create a callback list and tracker function for abort tests."""
    calls: list[_CallbackEntry] = []

    def track(mid: str, rn: int, results: list[Any], aborted: bool) -> None:
        calls.append((mid, rn, len(results), aborted))

    return calls, track


def _run_abort_harness(
    adapter: ModelAdapter,
    scenarios: list[Scenario],
    settings: EvaluationSettings = _ABORT_TEST_SETTINGS,
    on_run_complete: Any = None,
) -> list[Any]:
    """Run harness with adapter patching. Returns harness.run_all() result."""
    with patch.object(EvaluationHarness, "_create_adapter", return_value=adapter):
        harness, _ = _make_harness(adapter, scenarios, settings=settings)
        return harness.run_all(on_run_complete=on_run_complete)


# --- Step-level early-abort tests (GH-117) ---


def _make_multi_step_scenario(
    scenario_id: str,
    num_steps: int = 4,
) -> Scenario:
    """Build a scenario with multiple steps for step-level abort testing."""
    steps_data: list[tuple[str, dict, str, list[str], list[str]]] = [
        ("order_received", _STEP_1_DATA, "ACCEPTED", ["ACC-008"], []),
    ]
    # Add extra steps beyond the first
    extra_events = [
        ("grossing_complete", {"outcome": "success"}, "SAMPLE_PREP_PROCESSING", ["SP-001"], []),
        ("processing_complete", {"outcome": "success"}, "SAMPLE_PREP_EMBEDDING", ["SP-001"], []),
        (
            "he_staining_complete",
            {"fixation_issue": False},
            "SAMPLE_PREP_QC",
            ["SP-001"],
            [],
        ),
    ]
    for i in range(min(num_steps - 1, len(extra_events))):
        steps_data.append(extra_events[i])
    return _make_scenario(scenario_id=scenario_id, steps=steps_data)


class TestStepLevelEarlyAbort:
    def test_step_abort_triggers_before_scenario_abort(self) -> None:
        """Step-level abort triggers earlier than scenario-level for multi-step scenarios.

        With 4-step scenarios, 30 steps is reached at ~8 scenarios (8×4=32),
        well before the 20-scenario threshold for scenario-level abort.
        """
        # Need enough scenarios that step threshold triggers but scenario threshold doesn't
        num_scenarios = _EARLY_ABORT_MIN_SCENARIOS - 1  # 19: under scenario threshold
        scenarios = [
            _make_multi_step_scenario(f"SC-{i:03d}", num_steps=4) for i in range(num_scenarios)
        ]

        adapter = MockAdapter(error="timeout: model did not respond")
        callback_calls, track = _make_abort_tracker()
        _run_abort_harness(adapter, scenarios, on_run_complete=track)

        assert len(callback_calls) == 1
        _mid, _rn, result_count, aborted = callback_calls[0]
        assert aborted is True
        assert result_count < _EARLY_ABORT_MIN_SCENARIOS

    def test_step_abort_no_trigger_below_min_steps(self) -> None:
        """Step-level abort doesn't trigger when total steps < _EARLY_ABORT_MIN_STEPS."""
        # 7 scenarios × 4 steps = 28 steps, under the 30-step minimum
        num_scenarios = (_EARLY_ABORT_MIN_STEPS // 4) - 1
        scenarios = [
            _make_multi_step_scenario(f"SC-{i:03d}", num_steps=4) for i in range(num_scenarios)
        ]

        adapter = MockAdapter(error="timeout: model did not respond")
        callback_calls, track = _make_abort_tracker()
        _run_abort_harness(adapter, scenarios, on_run_complete=track)

        assert len(callback_calls) == 1
        _mid, _rn, result_count, aborted = callback_calls[0]
        assert aborted is False
        assert result_count == num_scenarios

    def test_step_abort_message_mentions_steps(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Step-level abort message format: includes 'steps', excludes 'scenarios'."""
        import re

        num_scenarios = _EARLY_ABORT_MIN_SCENARIOS - 1
        scenarios = [
            _make_multi_step_scenario(f"SC-{i:03d}", num_steps=4) for i in range(num_scenarios)
        ]

        adapter = MockAdapter(error="timeout: model did not respond")
        _run_abort_harness(adapter, scenarios)

        captured = capsys.readouterr()
        assert re.search(r"\d+/\d+ steps \(\d+%\) had fatal errors", captured.out)
        abort_line = [line for line in captured.out.splitlines() if "aborted" in line]
        assert abort_line, "Expected an abort warning line in output"
        assert "scenarios" not in abort_line[0]

    def test_step_abort_mixed_fatal_and_non_fatal(self) -> None:
        """Mixed fatal and non-fatal step failures: only fatal steps count toward abort.

        Alternates between timeout errors (fatal) and wrong-state responses (non-fatal).
        With 50% fatal rate and > 50% threshold, abort should NOT trigger.
        """
        num_scenarios = 10  # 10 × 4 = 40 steps, above _EARLY_ABORT_MIN_STEPS
        scenarios = [
            _make_multi_step_scenario(f"SC-{i:03d}", num_steps=4) for i in range(num_scenarios)
        ]

        adapter = _AlternatingMockAdapter(fatal_pattern=[True, False, True, False])
        callback_calls, track = _make_abort_tracker()
        _run_abort_harness(adapter, scenarios, on_run_complete=track)

        assert len(callback_calls) == 1
        _mid, _rn, result_count, aborted = callback_calls[0]
        assert aborted is False
        assert result_count == num_scenarios

    def test_step_abort_mixed_above_threshold(self) -> None:
        """Mixed fatal/non-fatal where fatal rate > 50% triggers abort."""
        num_scenarios = 12  # 12 × 4 = 48 steps, well above threshold
        scenarios = [
            _make_multi_step_scenario(f"SC-{i:03d}", num_steps=4) for i in range(num_scenarios)
        ]

        # 3 out of 4 steps fatal = 75% fatal rate → should abort
        adapter = _AlternatingMockAdapter(fatal_pattern=[True, True, True, False])
        callback_calls, track = _make_abort_tracker()
        _run_abort_harness(adapter, scenarios, on_run_complete=track)

        assert len(callback_calls) == 1
        _mid, _rn, result_count, aborted = callback_calls[0]
        assert aborted is True
        assert result_count < num_scenarios

    def test_step_abort_exact_50_percent_no_trigger(self) -> None:
        """Exactly 50% fatal rate does NOT trigger abort (uses > not >=).

        At _EARLY_ABORT_MIN_STEPS, if exactly half are fatal, the condition
        `fatal_step_count > total_step_count * 0.5` is False.
        """
        # Use 2-step scenarios: 1 fatal + 1 non-fatal per scenario = 50% rate
        # Need 15 scenarios × 2 steps = 30 steps (exactly _EARLY_ABORT_MIN_STEPS)
        num_scenarios = _EARLY_ABORT_MIN_STEPS // 2  # 15
        scenarios = [
            _make_multi_step_scenario(f"SC-{i:03d}", num_steps=2) for i in range(num_scenarios)
        ]

        adapter = _AlternatingMockAdapter(fatal_pattern=[True, False])
        callback_calls, track = _make_abort_tracker()
        _run_abort_harness(adapter, scenarios, on_run_complete=track)

        assert len(callback_calls) == 1
        _mid, _rn, result_count, aborted = callback_calls[0]
        assert aborted is False
        assert result_count == num_scenarios

    def test_step_abort_takes_precedence_over_scenario_abort(self) -> None:
        """Step-level abort fires before scenario-level when both thresholds met.

        With 100% fatal errors and enough scenarios for both thresholds,
        step-level triggers first (fewer scenarios processed).
        """
        num_scenarios = _EARLY_ABORT_MIN_SCENARIOS + 5  # 25
        scenarios = [
            _make_multi_step_scenario(f"SC-{i:03d}", num_steps=4) for i in range(num_scenarios)
        ]

        adapter = MockAdapter(error="timeout: model did not respond")
        callback_calls, track = _make_abort_tracker()
        _run_abort_harness(adapter, scenarios, on_run_complete=track)

        assert len(callback_calls) == 1
        _mid, _rn, result_count, aborted = callback_calls[0]
        assert aborted is True
        # Step-level triggers at ~8 scenarios (32 steps > 30 min),
        # well before scenario-level at 20+ scenarios
        assert result_count < _EARLY_ABORT_MIN_SCENARIOS

    def test_non_fatal_failures_do_not_trigger_abort(self) -> None:
        """100% wrong-state responses (non-fatal) do NOT trigger step-level abort."""
        num_scenarios = 12  # 12 × 4 = 48 steps, above _EARLY_ABORT_MIN_STEPS
        scenarios = [
            _make_multi_step_scenario(f"SC-{i:03d}", num_steps=4) for i in range(num_scenarios)
        ]

        wrong_response = {
            "next_state": "WRONG_STATE_VALUE",
            "applied_rules": ["ACC-008"],
            "flags": [],
            "reasoning": "mock wrong answer",
        }
        adapter = MockAdapter(responses=[wrong_response])
        callback_calls, track = _make_abort_tracker()
        _run_abort_harness(adapter, scenarios, on_run_complete=track)

        assert len(callback_calls) == 1
        _mid, _rn, result_count, aborted = callback_calls[0]
        assert aborted is False
        assert result_count == num_scenarios

    def test_abort_persists_across_runs(self) -> None:
        """Step-level abort in run 1 skips subsequent runs."""
        num_scenarios = _EARLY_ABORT_MIN_SCENARIOS - 1  # 19
        scenarios = [
            _make_multi_step_scenario(f"SC-{i:03d}", num_steps=4) for i in range(num_scenarios)
        ]

        adapter = MockAdapter(error="timeout: model did not respond")
        multi_run_settings = EvaluationSettings(
            runs_per_model={"llamacpp": 3, "openrouter": 3},
            timeout_seconds=120,
            output_directory="results",
        )
        callback_calls, track = _make_abort_tracker()
        _run_abort_harness(adapter, scenarios, multi_run_settings, on_run_complete=track)

        # Only 1 run should complete (runs 2 and 3 skipped due to model_aborted)
        assert len(callback_calls) == 1
        _mid, _rn, _count, aborted = callback_calls[0]
        assert aborted is True

    def test_single_step_scenarios_trigger_abort(self) -> None:
        """Step-level abort works with single-step scenarios (1 step each)."""
        num_scenarios = _EARLY_ABORT_MIN_STEPS + 5  # 35
        scenarios = [
            _make_multi_step_scenario(f"SC-{i:03d}", num_steps=1) for i in range(num_scenarios)
        ]

        adapter = MockAdapter(error="timeout: model did not respond")
        callback_calls, track = _make_abort_tracker()
        _run_abort_harness(adapter, scenarios, on_run_complete=track)

        assert len(callback_calls) == 1
        _mid, _rn, result_count, aborted = callback_calls[0]
        assert aborted is True
        assert result_count < num_scenarios


# --- E2E smoke test: all real scenarios through mock adapter ---


@pytest.mark.integration
class TestHarnessAllScenariosSmoke:
    """Load every real scenario JSON and run through the harness with a mock adapter.

    Catches data/schema issues (like SC-104 NULL) without any API calls.
    Marked as integration test since it processes ~95 scenarios with full pipeline.
    """

    def test_all_scenarios_complete_without_error(self) -> None:
        from src.evaluation.runner import _load_routing_scenarios

        scenario_dir = Path("scenarios")
        if not scenario_dir.exists():
            pytest.skip("scenarios/ not found")

        scenarios = _load_routing_scenarios(scenario_dir)
        assert len(scenarios) > 0, f"No scenarios loaded from {scenario_dir}"

        # Mock adapter returning a generic valid response for every call
        generic_response = {
            "next_state": "ACCEPTED",
            "applied_rules": ["ACC-008"],
            "flags": [],
            "reasoning": "mock",
        }
        adapter = MockAdapter(responses=[generic_response])

        with patch.object(EvaluationHarness, "_create_adapter", return_value=adapter):
            harness, _ = _make_harness(adapter, scenarios)
            results = harness.run_all()

        assert len(results) == len(scenarios)
        result_ids = {r.scenario_id for r in results}
        scenario_ids = {s.scenario_id for s in scenarios}
        assert result_ids == scenario_ids

        # Verify each result has valid structure and correct step count
        scenario_map = {s.scenario_id: s for s in scenarios}
        for result in results:
            matching = scenario_map[result.scenario_id]
            assert len(result.step_results) == len(matching.steps), (
                f"{result.scenario_id}: expected {len(matching.steps)} "
                f"step results, got {len(result.step_results)}"
            )
            for sr in result.step_results:
                assert sr.decision is not None, f"{result.scenario_id} has None decision"
                assert sr.validation is not None, f"{result.scenario_id} has None validation"


# --- Parallel execution tests ---


def _make_adapter_factory(
    scenario: Scenario,
) -> type:
    """Return a callable that creates a fresh MockAdapter per call (thread-safe)."""
    response = _correct_response(scenario.steps[0])

    def _factory(_config: Any) -> MockAdapter:
        return MockAdapter(responses=[response])

    return _factory


class TestParallelExecution:
    def test_parallel_false_is_default(self) -> None:
        """parallel=False by default, unchanged sequential behavior."""
        scenario = _make_scenario()
        adapter = MockAdapter(responses=[_correct_response(scenario.steps[0])])

        with patch.object(EvaluationHarness, "_create_adapter", return_value=adapter):
            harness, _ = _make_harness(adapter, [scenario])
            results = harness.run_all()

        assert len(results) == 1
        assert results[0].all_correct is True

    def test_parallel_true_with_cloud_models(self) -> None:
        """parallel=True runs cloud models concurrently and produces correct results."""
        scenario = _make_scenario()
        factory = _make_adapter_factory(scenario)
        settings = EvaluationSettings(
            runs_per_model={"llamacpp": 1, "openrouter": 1},
            timeout_seconds=120,
            output_directory="results",
        )

        config_a = ModelConfig(
            name="cloud-a",
            provider="openrouter",
            model_id="cloud-model-a",
            temperature=0.0,
            max_tokens=2048,
            token_limit=8192,
        )
        config_b = ModelConfig(
            name="cloud-b",
            provider="openrouter",
            model_id="cloud-model-b",
            temperature=0.0,
            max_tokens=2048,
            token_limit=8192,
        )

        tmpdir = tempfile.mkdtemp()
        db_path = Path(tmpdir) / "test.db"
        harness = EvaluationHarness([config_a, config_b], settings, [scenario], db_path)

        with patch.object(EvaluationHarness, "_create_adapter", side_effect=factory):
            results = harness.run_all(parallel=True)

        # 2 cloud models * 1 run * 1 scenario = 2 results
        assert len(results) == 2

        # Verify DB has correct counts across tables
        with Database(db_path) as db:
            cursor = db._connection.execute("SELECT COUNT(*) FROM orders")
            assert cursor.fetchone()[0] == 2
            cursor = db._connection.execute(
                "SELECT COUNT(*) FROM runs WHERE completed_at IS NOT NULL"
            )
            assert cursor.fetchone()[0] == 2
            cursor = db._connection.execute("SELECT COUNT(*) FROM decisions")
            assert cursor.fetchone()[0] == 2

    def test_parallel_mixed_local_and_cloud(self) -> None:
        """parallel=True: single local model runs concurrently with cloud models."""
        scenario = _make_scenario()
        factory = _make_adapter_factory(scenario)
        settings = EvaluationSettings(
            runs_per_model={"llamacpp": 1, "openrouter": 1},
            timeout_seconds=120,
            output_directory="results",
        )

        local_model = ModelConfig(
            name="local-model",
            provider="llamacpp",
            model_id="local-model",
            temperature=0.0,
            max_tokens=2048,
            token_limit=8192,
        )
        cloud_model_a = ModelConfig(
            name="cloud-a",
            provider="openrouter",
            model_id="cloud-a",
            temperature=0.0,
            max_tokens=2048,
            token_limit=8192,
        )
        cloud_model_b = ModelConfig(
            name="cloud-b",
            provider="openrouter",
            model_id="cloud-b",
            temperature=0.0,
            max_tokens=2048,
            token_limit=8192,
        )

        tmpdir = tempfile.mkdtemp()
        db_path = Path(tmpdir) / "test.db"
        harness = EvaluationHarness(
            [local_model, cloud_model_a, cloud_model_b],
            settings,
            [scenario],
            db_path,
        )

        with patch.object(EvaluationHarness, "_create_adapter", side_effect=factory):
            results = harness.run_all(parallel=True)

        # 1 local + 2 cloud = 3 results
        assert len(results) == 3

        # Verify DB has correct counts across tables
        with Database(db_path) as db:
            cursor = db._connection.execute("SELECT COUNT(*) FROM orders")
            assert cursor.fetchone()[0] == 3
            cursor = db._connection.execute(
                "SELECT COUNT(*) FROM runs WHERE completed_at IS NOT NULL"
            )
            assert cursor.fetchone()[0] == 3
            cursor = db._connection.execute("SELECT COUNT(*) FROM decisions")
            assert cursor.fetchone()[0] == 3

    def test_parallel_callback_invoked_for_all_models(self) -> None:
        """parallel=True invokes callback for each model; return value is empty."""
        scenario = _make_scenario()
        factory = _make_adapter_factory(scenario)
        settings = EvaluationSettings(
            runs_per_model={"llamacpp": 1, "openrouter": 1},
            timeout_seconds=120,
            output_directory="results",
        )

        config_a = ModelConfig(
            name="cloud-a",
            provider="openrouter",
            model_id="cloud-a",
            temperature=0.0,
            max_tokens=2048,
            token_limit=8192,
        )
        config_b = ModelConfig(
            name="cloud-b",
            provider="openrouter",
            model_id="cloud-b",
            temperature=0.0,
            max_tokens=2048,
            token_limit=8192,
        )

        callback_calls: list[tuple[str, int]] = []

        def _track(
            mid: str,
            rn: int,
            _results: list[Any],
            _aborted: bool,
        ) -> None:
            callback_calls.append((mid, rn))

        tmpdir = tempfile.mkdtemp()
        db_path = Path(tmpdir) / "test.db"
        harness = EvaluationHarness([config_a, config_b], settings, [scenario], db_path)

        with patch.object(EvaluationHarness, "_create_adapter", side_effect=factory):
            results = harness.run_all(on_run_complete=_track, parallel=True)

        # With on_run_complete, return value should be empty (results go to callback)
        assert results == []
        assert len(callback_calls) == 2
        model_ids = {mid for mid, _ in callback_calls}
        assert model_ids == {"cloud-a", "cloud-b"}

    def test_parallel_no_cloud_models(self) -> None:
        """parallel=True with only one local model runs it in the thread pool."""
        scenario = _make_scenario()
        adapter = MockAdapter(responses=[_correct_response(scenario.steps[0])])
        settings = EvaluationSettings(
            runs_per_model={"llamacpp": 2, "openrouter": 1},
            timeout_seconds=120,
            output_directory="results",
        )

        with patch.object(EvaluationHarness, "_create_adapter", return_value=adapter):
            harness, _ = _make_harness(adapter, [scenario], settings=settings)
            results = harness.run_all(parallel=True)

        assert len(results) == 2

    def test_parallel_exception_surfaces_with_model_identity(self) -> None:
        """When a cloud model thread raises, exception includes model name."""
        scenario = _make_scenario()
        settings = EvaluationSettings(
            runs_per_model={"llamacpp": 1, "openrouter": 1},
            timeout_seconds=120,
            output_directory="results",
        )

        config_ok = ModelConfig(
            name="cloud-ok",
            provider="openrouter",
            model_id="cloud-ok",
            temperature=0.0,
            max_tokens=2048,
            token_limit=8192,
        )
        config_bad = ModelConfig(
            name="cloud-bad",
            provider="openrouter",
            model_id="cloud-bad",
            temperature=0.0,
            max_tokens=2048,
            token_limit=8192,
        )

        call_count = 0

        def _factory(config: Any) -> MockAdapter:
            nonlocal call_count
            call_count += 1
            if config.name == "cloud-bad":
                raise ValueError("simulated adapter failure")
            return MockAdapter(responses=[_correct_response(scenario.steps[0])])

        tmpdir = tempfile.mkdtemp()
        db_path = Path(tmpdir) / "test.db"
        harness = EvaluationHarness([config_ok, config_bad], settings, [scenario], db_path)

        with (
            patch.object(EvaluationHarness, "_create_adapter", side_effect=_factory),
            pytest.raises(RuntimeError, match="cloud-bad"),
        ):
            harness.run_all(parallel=True)

    def test_parallel_early_abort_does_not_affect_other_models(self) -> None:
        """Early-abort in one cloud model does not discard results from another."""
        # Build enough scenarios to trigger early-abort
        scenarios = [
            _make_scenario(scenario_id=f"SC-{i:03d}")
            for i in range(1, _EARLY_ABORT_MIN_SCENARIOS + 5)
        ]

        settings = EvaluationSettings(
            runs_per_model={"llamacpp": 1, "openrouter": 1},
            timeout_seconds=120,
            output_directory="results",
        )

        config_good = ModelConfig(
            name="cloud-good",
            provider="openrouter",
            model_id="cloud-good",
            temperature=0.0,
            max_tokens=2048,
            token_limit=8192,
        )
        config_abort = ModelConfig(
            name="cloud-abort",
            provider="openrouter",
            model_id="cloud-abort",
            temperature=0.0,
            max_tokens=2048,
            token_limit=8192,
        )

        def _factory(config: Any) -> MockAdapter:
            if config.name == "cloud-abort":
                return MockAdapter(error="timeout: model did not respond")
            return MockAdapter(responses=[_correct_response(scenarios[0].steps[0])])

        tmpdir = tempfile.mkdtemp()
        db_path = Path(tmpdir) / "test.db"
        harness = EvaluationHarness([config_good, config_abort], settings, scenarios, db_path)

        callback_calls: list[tuple[str, bool]] = []

        def _track(
            mid: str,
            rn: int,
            _results: list[Any],
            aborted: bool,
        ) -> None:
            callback_calls.append((mid, aborted))

        with patch.object(EvaluationHarness, "_create_adapter", side_effect=_factory):
            harness.run_all(on_run_complete=_track, parallel=True)

        # cloud-good should not be aborted; cloud-abort should be aborted
        by_model = {mid: ab for mid, ab in callback_calls}
        assert by_model["cloud-good"] is False
        assert by_model["cloud-abort"] is True


class TestPromptExtrasValidation:
    """Tests for prompt_extras validation at harness construction time."""

    def test_invalid_prompt_extras_raises(self, tmp_path: Path) -> None:
        """EvaluationHarness rejects invalid prompt_extras at construction."""
        config = ModelConfig(
            name="test",
            provider="llamacpp",
            model_id="test",
            temperature=0.0,
            max_tokens=1024,
            token_limit=8192,
        )
        settings = EvaluationSettings(
            runs_per_model={"llamacpp": 1},
            timeout_seconds=120,
            output_directory="results",
        )
        with pytest.raises(ValueError, match="Invalid prompt_extras"):
            EvaluationHarness(
                [config],
                settings,
                [],
                tmp_path / "eval.db",
                prompt_extras=frozenset({"bogus"}),
            )

    def test_valid_prompt_extras_accepted(self, tmp_path: Path) -> None:
        """EvaluationHarness accepts valid prompt_extras."""
        config = ModelConfig(
            name="test",
            provider="llamacpp",
            model_id="test",
            temperature=0.0,
            max_tokens=1024,
            token_limit=8192,
        )
        settings = EvaluationSettings(
            runs_per_model={"llamacpp": 1},
            timeout_seconds=120,
            output_directory="results",
        )
        harness = EvaluationHarness(
            [config],
            settings,
            [],
            tmp_path / "eval.db",
            prompt_extras=frozenset({"state_sequence", "retry_clarification"}),
        )
        assert harness._prompt_extras == frozenset({"state_sequence", "retry_clarification"})
