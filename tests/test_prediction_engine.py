"""Tests for the prediction engine."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import pytest

from src.models.base import ModelAdapter, ModelResponse
from src.prediction.engine import (
    PredictionEngine,
    PredictionResult,
    QueryPredictionResult,
    parse_query_output,
)
from src.simulator.schema import (
    DatabaseStateSnapshot,
    QueryExpectedOutput,
    QueryScenario,
)
from src.workflow.models import Event, Order, Slide
from src.workflow.state_machine import StateMachine
from src.workflow.validator import FailureType, classify_failure

# --- Mock adapter ---


class _MockAdapter(ModelAdapter):
    """Adapter that returns a preconfigured ModelResponse."""

    def __init__(self, raw_text: str, *, error: str | None = None) -> None:
        self._raw_text = raw_text
        self._error = error

    def predict(self, prompt: str) -> ModelResponse:
        parsed: dict[str, Any] | None = None
        if self._error is None:
            try:
                parsed = json.loads(self._raw_text)
                if not isinstance(parsed, dict):
                    parsed = None
            except (json.JSONDecodeError, ValueError):
                parsed = None

        return ModelResponse(
            raw_text=self._raw_text,
            parsed_output=parsed if self._error is None else None,
            latency_ms=100.0,
            input_tokens=50,
            output_tokens=20,
            cost_estimate_usd=None,
            model_id="mock-model",
            error=self._error,
        )

    @property
    def model_id(self) -> str:
        return "mock-model"

    @property
    def provider(self) -> str:
        return "mock"


# --- Fixtures ---


@pytest.fixture()
def sample_order() -> Order:
    return Order(
        order_id="ORD-001",
        scenario_id="SCN-001",
        patient_name="Jane Doe",
        patient_age=55,
        patient_sex="F",
        specimen_type="Core Needle Biopsy",
        anatomic_site="Left Breast",
        fixative="10% NBF",
        fixation_time_hours=12.0,
        ordered_tests=["ER", "PR", "HER2", "Ki-67"],
        priority="routine",
        billing_info_present=True,
        current_state="ACCESSIONING",
        flags=[],
        created_at=datetime(2025, 1, 15, 10, 0, 0),
        updated_at=datetime(2025, 1, 15, 10, 0, 0),
    )


@pytest.fixture()
def sample_slides() -> list[Slide]:
    return [
        Slide(
            slide_id="SLD-001",
            order_id="ORD-001",
            test_assignment="ER",
            status="sectioned",
            created_at=datetime(2025, 1, 15, 10, 0, 0),
            updated_at=datetime(2025, 1, 15, 10, 0, 0),
        ),
    ]


@pytest.fixture()
def sample_event() -> Event:
    return Event(
        event_id="EVT-001",
        order_id="ORD-001",
        step_number=1,
        event_type="order_received",
        event_data={"specimen_type": "Core Needle Biopsy"},
        created_at=datetime(2025, 1, 15, 10, 0, 0),
    )


_VALID_ROUTING_JSON = json.dumps(
    {
        "next_state": "GROSSING",
        "applied_rules": ["ACC-001", "ACC-002"],
        "flags": [],
        "reasoning": "Order received, accessioning rules applied.",
    }
)

_VALID_QUERY_JSON = json.dumps(
    {
        "order_ids": ["ORD-001"],
        "reasoning": "This order matches the query criteria.",
    }
)


# --- PredictionEngine constructor ---


class TestPredictionEngineInit:
    def test_rejects_non_adapter(self) -> None:
        with pytest.raises(TypeError, match="adapter must be a ModelAdapter"):
            PredictionEngine("not an adapter")  # type: ignore[arg-type]

    def test_exposes_model_properties(self) -> None:
        adapter = _MockAdapter(_VALID_ROUTING_JSON)
        engine = PredictionEngine(adapter)
        assert engine.model_id == "mock-model"
        assert engine.provider == "mock"


# --- predict_routing ---


class TestPredictRouting:
    def test_valid_json_returns_parsed_result(
        self, sample_order: Order, sample_slides: list[Slide], sample_event: Event
    ) -> None:
        engine = PredictionEngine(_MockAdapter(_VALID_ROUTING_JSON))
        result = engine.predict_routing(sample_order, sample_slides, sample_event)

        assert isinstance(result, PredictionResult)
        assert result.next_state == "GROSSING"
        assert result.applied_rules == ("ACC-001", "ACC-002")
        assert result.flags == ()
        assert result.reasoning == "Order received, accessioning rules applied."
        assert result.error is None
        assert isinstance(result.raw_response, ModelResponse)

    def test_malformed_json_returns_error(
        self, sample_order: Order, sample_slides: list[Slide], sample_event: Event
    ) -> None:
        engine = PredictionEngine(_MockAdapter("not json at all{{{"))
        result = engine.predict_routing(sample_order, sample_slides, sample_event)

        assert result.next_state is None
        assert result.applied_rules == ()
        assert result.flags == ()
        assert result.reasoning is None
        assert result.error is not None
        assert "malformed_json" in result.error

    def test_wrong_schema_returns_error(
        self, sample_order: Order, sample_slides: list[Slide], sample_event: Event
    ) -> None:
        wrong_schema = json.dumps({"next_state": "GROSSING"})
        engine = PredictionEngine(_MockAdapter(wrong_schema))
        result = engine.predict_routing(sample_order, sample_slides, sample_event)

        assert result.next_state is None
        assert result.error is not None
        assert "wrong_schema" in result.error

    def test_wrong_types_returns_error(
        self, sample_order: Order, sample_slides: list[Slide], sample_event: Event
    ) -> None:
        wrong_types = json.dumps(
            {
                "next_state": 123,
                "applied_rules": ["ACC-001"],
                "flags": [],
                "reasoning": "test",
            }
        )
        engine = PredictionEngine(_MockAdapter(wrong_types))
        result = engine.predict_routing(sample_order, sample_slides, sample_event)

        assert result.error is not None
        assert "wrong_schema" in result.error

    def test_model_error_returns_error(
        self, sample_order: Order, sample_slides: list[Slide], sample_event: Event
    ) -> None:
        engine = PredictionEngine(_MockAdapter("<connection_error>", error="connection refused"))
        result = engine.predict_routing(sample_order, sample_slides, sample_event)

        assert result.next_state is None
        assert result.error is not None
        assert "model_error" in result.error
        assert "connection refused" in result.error
        assert "order=ORD-001" in result.error
        assert "model=mock-model" in result.error

    def test_full_context_flag_passed(
        self, sample_order: Order, sample_slides: list[Slide], sample_event: Event
    ) -> None:
        engine = PredictionEngine(_MockAdapter(_VALID_ROUTING_JSON))
        result = engine.predict_routing(
            sample_order, sample_slides, sample_event, full_context=True
        )
        assert result.error is None
        assert result.next_state == "GROSSING"


# --- parse_query_output ---


class TestParseQueryOutput:
    def test_valid_order_list(self) -> None:
        raw = json.dumps({"order_ids": ["ORD-001"], "reasoning": "matches"})
        parsed, error = parse_query_output(raw, "order_list")
        assert error is None
        assert parsed is not None
        assert parsed["order_ids"] == ["ORD-001"]

    def test_valid_order_status(self) -> None:
        raw = json.dumps(
            {
                "order_ids": ["ORD-001"],
                "status_summary": "In grossing",
                "reasoning": "State is GROSSING",
            }
        )
        parsed, error = parse_query_output(raw, "order_status")
        assert error is None
        assert parsed is not None
        assert parsed["status_summary"] == "In grossing"

    def test_valid_explanation(self) -> None:
        raw = json.dumps({"explanation": "Because...", "reasoning": "Logic"})
        parsed, error = parse_query_output(raw, "explanation")
        assert error is None
        assert parsed is not None

    def test_valid_prioritized_list(self) -> None:
        raw = json.dumps({"order_ids": ["ORD-002", "ORD-001"], "reasoning": "priority"})
        parsed, error = parse_query_output(raw, "prioritized_list")
        assert error is None
        assert parsed is not None

    def test_malformed_json(self) -> None:
        _, error = parse_query_output("{bad json", "order_list")
        assert error is not None
        assert "malformed_json" in error

    def test_missing_keys(self) -> None:
        raw = json.dumps({"reasoning": "test"})
        _, error = parse_query_output(raw, "order_list")
        assert error is not None
        assert "wrong_schema" in error
        assert "order_ids" in error

    def test_wrong_type_string_field(self) -> None:
        raw = json.dumps({"order_ids": ["ORD-001"], "reasoning": 42})
        _, error = parse_query_output(raw, "order_list")
        assert error is not None
        assert "wrong_schema" in error

    def test_wrong_type_list_field(self) -> None:
        raw = json.dumps({"order_ids": "ORD-001", "reasoning": "test"})
        _, error = parse_query_output(raw, "order_list")
        assert error is not None
        assert "wrong_schema" in error

    def test_list_elements_not_strings(self) -> None:
        raw = json.dumps({"order_ids": [1, 2], "reasoning": "test"})
        _, error = parse_query_output(raw, "order_list")
        assert error is not None
        assert "elements must be strings" in error

    def test_invalid_answer_type(self) -> None:
        _, error = parse_query_output("{}", "invalid_type")
        assert error is not None
        assert "invalid_answer_type" in error

    def test_not_a_dict(self) -> None:
        _, error = parse_query_output(json.dumps([1, 2, 3]), "order_list")
        assert error is not None
        assert "wrong_schema" in error


# --- predict_query ---


@pytest.fixture()
def sample_query_scenario() -> QueryScenario:
    return QueryScenario(
        scenario_id="QR-001",
        category="query",
        tier=1,
        description="Find orders in accessioning",
        database_state=DatabaseStateSnapshot(
            orders=(
                {
                    "order_id": "ORD-001",
                    "current_state": "ACCESSIONING",
                    "specimen_type": "Core Needle Biopsy",
                    "anatomic_site": "Left Breast",
                    "priority": "routine",
                    "flags": [],
                },
            ),
            slides=({"slide_id": "SLD-001", "order_id": "ORD-001", "status": "sectioned"},),
        ),
        query="Which orders are currently in accessioning?",
        expected_output=QueryExpectedOutput(
            answer_type="order_list",
            reasoning="ORD-001 is in ACCESSIONING state",
            order_ids=("ORD-001",),
        ),
    )


class TestPredictQuery:
    def test_valid_query_response(self, sample_query_scenario: QueryScenario) -> None:
        engine = PredictionEngine(_MockAdapter(_VALID_QUERY_JSON))
        result = engine.predict_query(sample_query_scenario)

        assert isinstance(result, QueryPredictionResult)
        assert result.answer_type == "order_list"
        assert result.parsed_output is not None
        assert result.parsed_output["order_ids"] == ["ORD-001"]
        assert result.error is None

    def test_malformed_query_response(self, sample_query_scenario: QueryScenario) -> None:
        engine = PredictionEngine(_MockAdapter("not valid json"))
        result = engine.predict_query(sample_query_scenario)

        assert result.parsed_output is None
        assert result.error is not None
        assert "malformed_json" in result.error

    def test_wrong_schema_query_response(self, sample_query_scenario: QueryScenario) -> None:
        wrong = json.dumps({"unrelated_key": "value"})
        engine = PredictionEngine(_MockAdapter(wrong))
        result = engine.predict_query(sample_query_scenario)

        assert result.parsed_output is None
        assert result.error is not None
        assert "wrong_schema" in result.error

    def test_model_error_query(self, sample_query_scenario: QueryScenario) -> None:
        engine = PredictionEngine(_MockAdapter("<timeout>", error="request timed out"))
        result = engine.predict_query(sample_query_scenario)

        assert result.parsed_output is None
        assert result.error is not None
        assert "model_error" in result.error


class TestPredictQueryFromParts:
    def test_valid_response(self) -> None:
        db_state = DatabaseStateSnapshot(
            orders=(
                {
                    "order_id": "ORD-001",
                    "current_state": "ACCESSIONING",
                    "specimen_type": "Core Needle Biopsy",
                    "anatomic_site": "Left Breast",
                    "priority": "routine",
                    "flags": [],
                },
            ),
            slides=(),
        )
        engine = PredictionEngine(_MockAdapter(_VALID_QUERY_JSON))
        result = engine.predict_query_from_parts(
            db_state, "Which orders are in accessioning?", "order_list"
        )

        assert result.error is None
        assert result.parsed_output is not None
        assert result.answer_type == "order_list"


# --- Integration test ---


class TestIntegration:
    def test_routing_round_trip(
        self, sample_order: Order, sample_slides: list[Slide], sample_event: Event
    ) -> None:
        """Full pipeline: render prompt -> mock model -> parse -> validate."""
        expected_output = {
            "next_state": "GROSSING",
            "applied_rules": ["ACC-001"],
            "flags": [],
            "reasoning": "Specimen accepted, routing to grossing.",
        }
        adapter = _MockAdapter(json.dumps(expected_output))
        engine = PredictionEngine(adapter)
        result = engine.predict_routing(sample_order, sample_slides, sample_event)

        assert result.error is None
        assert result.next_state == expected_output["next_state"]
        assert list(result.applied_rules) == expected_output["applied_rules"]
        assert list(result.flags) == expected_output["flags"]
        assert result.reasoning == expected_output["reasoning"]
        assert result.raw_response.latency_ms >= 0
        assert result.raw_response.model_id == "mock-model"

    def test_query_round_trip(self, sample_query_scenario: QueryScenario) -> None:
        """Full pipeline: render query prompt -> mock model -> parse -> validate."""
        expected_output = {
            "order_ids": ["ORD-001"],
            "reasoning": "ORD-001 is in ACCESSIONING state.",
        }
        adapter = _MockAdapter(json.dumps(expected_output))
        engine = PredictionEngine(adapter)
        result = engine.predict_query(sample_query_scenario)

        assert result.error is None
        assert result.parsed_output is not None
        assert result.parsed_output["order_ids"] == expected_output["order_ids"]
        assert result.raw_response.model_id == "mock-model"


# --- PredictionResult validation ---


class TestPredictionResultValidation:
    def test_rejects_non_model_response(self) -> None:
        with pytest.raises(TypeError, match="raw_response must be ModelResponse"):
            PredictionResult(
                next_state=None,
                applied_rules=(),
                flags=(),
                reasoning=None,
                raw_response="not a response",  # type: ignore[arg-type]
            )

    def test_rejects_non_tuple_applied_rules(self) -> None:
        response = ModelResponse(
            raw_text="test",
            parsed_output=None,
            latency_ms=0,
            input_tokens=0,
            output_tokens=0,
            cost_estimate_usd=None,
            model_id="test",
            error="test error",
        )
        with pytest.raises(TypeError, match="applied_rules must be tuple"):
            PredictionResult(
                next_state=None,
                applied_rules=["ACC-001"],  # type: ignore[arg-type]
                flags=(),
                reasoning=None,
                raw_response=response,
            )


class TestQueryPredictionResultValidation:
    def test_rejects_non_model_response(self) -> None:
        with pytest.raises(TypeError, match="raw_response must be ModelResponse"):
            QueryPredictionResult(
                answer_type="order_list",
                parsed_output=None,
                raw_response="not a response",  # type: ignore[arg-type]
            )

    def test_rejects_invalid_answer_type(self) -> None:
        response = ModelResponse(
            raw_text="test",
            parsed_output=None,
            latency_ms=0,
            input_tokens=0,
            output_tokens=0,
            cost_estimate_usd=None,
            model_id="test",
            error="test error",
        )
        with pytest.raises(ValueError, match="Invalid answer_type"):
            QueryPredictionResult(
                answer_type="bogus",
                parsed_output=None,
                raw_response=response,
            )


# --- Element-level validation tests (#9) ---


class TestPredictionResultElementValidation:
    """Tests for element-level type checks in applied_rules and flags."""

    def _error_response(self) -> ModelResponse:
        return ModelResponse(
            raw_text="test",
            parsed_output=None,
            latency_ms=0,
            input_tokens=0,
            output_tokens=0,
            cost_estimate_usd=None,
            model_id="test",
            error="test error",
        )

    def test_rejects_non_string_in_applied_rules(self) -> None:
        with pytest.raises(TypeError, match=r"applied_rules\[0\] must be str"):
            PredictionResult(
                next_state=None,
                applied_rules=(123,),  # type: ignore[arg-type]
                flags=(),
                reasoning=None,
                raw_response=self._error_response(),
            )

    def test_rejects_non_string_in_flags(self) -> None:
        with pytest.raises(TypeError, match=r"flags\[0\] must be str"):
            PredictionResult(
                next_state=None,
                applied_rules=(),
                flags=(42,),  # type: ignore[arg-type]
                reasoning=None,
                raw_response=self._error_response(),
            )

    def test_rejects_mixed_types_in_applied_rules(self) -> None:
        with pytest.raises(TypeError, match=r"applied_rules\[1\] must be str"):
            PredictionResult(
                next_state=None,
                applied_rules=("ACC-001", None),  # type: ignore[arg-type]
                flags=(),
                reasoning=None,
                raw_response=self._error_response(),
            )


# --- Cross-field validation tests (#4) ---


class TestPredictionResultCrossFieldValidation:
    """Tests for error/prediction field mutual exclusivity."""

    def _success_response(self) -> ModelResponse:
        return ModelResponse(
            raw_text='{"next_state": "GROSSING"}',
            parsed_output={"next_state": "GROSSING"},
            latency_ms=100.0,
            input_tokens=50,
            output_tokens=20,
            cost_estimate_usd=None,
            model_id="test",
        )

    def test_rejects_error_with_populated_next_state(self) -> None:
        with pytest.raises(ValueError, match="next_state must be None when error is set"):
            PredictionResult(
                next_state="GROSSING",
                applied_rules=(),
                flags=(),
                reasoning=None,
                raw_response=self._success_response(),
                error="some error",
            )

    def test_rejects_error_with_populated_applied_rules(self) -> None:
        with pytest.raises(ValueError, match="applied_rules must be empty when error is set"):
            PredictionResult(
                next_state=None,
                applied_rules=("ACC-001",),
                flags=(),
                reasoning=None,
                raw_response=self._success_response(),
                error="some error",
            )

    def test_rejects_error_with_populated_reasoning(self) -> None:
        with pytest.raises(ValueError, match="reasoning must be None when error is set"):
            PredictionResult(
                next_state=None,
                applied_rules=(),
                flags=(),
                reasoning="some reasoning",
                raw_response=self._success_response(),
                error="some error",
            )


# --- Exception handling tests (#1, #2) ---


class _RaisingAdapter(ModelAdapter):
    """Adapter that raises an exception on predict()."""

    def predict(self, prompt: str) -> ModelResponse:
        raise RuntimeError("Adapter exploded!")

    @property
    def model_id(self) -> str:
        return "raising-model"

    @property
    def provider(self) -> str:
        return "raising"


class TestExceptionHandling:
    """Tests for graceful handling of exceptions from adapter and prompt rendering."""

    def test_adapter_exception_routing(
        self, sample_order: Order, sample_slides: list[Slide], sample_event: Event
    ) -> None:
        engine = PredictionEngine(_RaisingAdapter())
        result = engine.predict_routing(sample_order, sample_slides, sample_event)

        assert result.error is not None
        assert "adapter_error" in result.error
        assert "RuntimeError" in result.error
        assert result.next_state is None
        assert result.applied_rules == ()

    def test_adapter_exception_query(self, sample_query_scenario: QueryScenario) -> None:
        engine = PredictionEngine(_RaisingAdapter())
        result = engine.predict_query(sample_query_scenario)

        assert result.error is not None
        assert "adapter_error" in result.error
        assert "RuntimeError" in result.error
        assert result.parsed_output is None


# --- full_context integration test (#10) ---


class _CapturingAdapter(ModelAdapter):
    """Adapter that captures the prompt and returns a valid response."""

    def __init__(self) -> None:
        self.last_prompt: str = ""

    def predict(self, prompt: str) -> ModelResponse:
        self.last_prompt = prompt
        return ModelResponse(
            raw_text=_VALID_ROUTING_JSON,
            parsed_output=json.loads(_VALID_ROUTING_JSON),
            latency_ms=100.0,
            input_tokens=50,
            output_tokens=20,
            cost_estimate_usd=None,
            model_id="capturing-model",
        )

    @property
    def model_id(self) -> str:
        return "capturing-model"

    @property
    def provider(self) -> str:
        return "capturing"


class TestFullContextIntegration:
    def test_full_context_includes_more_rules(
        self, sample_order: Order, sample_slides: list[Slide], sample_event: Event
    ) -> None:
        """Verify that full_context=True includes rules from multiple workflow steps."""
        adapter_filtered = _CapturingAdapter()
        adapter_full = _CapturingAdapter()

        engine_filtered = PredictionEngine(adapter_filtered)
        engine_full = PredictionEngine(adapter_full)

        engine_filtered.predict_routing(sample_order, sample_slides, sample_event)
        engine_full.predict_routing(sample_order, sample_slides, sample_event, full_context=True)

        filtered_prompt = adapter_filtered.last_prompt
        full_prompt = adapter_full.last_prompt

        # full_context prompt should be longer (more rules included).
        assert len(full_prompt) > len(filtered_prompt)
        # full_context should include rules from non-accessioning steps.
        assert "SP-" in full_prompt or "HE-" in full_prompt or "IHC-" in full_prompt


class TestPromptExtrasIntegration:
    """Tests for prompt_extras parameter threading through predict_routing."""

    def test_state_sequence_appears_in_prompt(
        self, sample_order: Order, sample_slides: list[Slide], sample_event: Event
    ) -> None:
        """state_sequence extra appears in the prompt sent to the adapter."""
        adapter = _CapturingAdapter()
        engine = PredictionEngine(adapter)
        engine.predict_routing(
            sample_order,
            sample_slides,
            sample_event,
            prompt_extras=frozenset({"state_sequence"}),
        )
        assert "Workflow Step Sequence" in adapter.last_prompt

    def test_retry_clarification_appears_in_prompt(
        self, sample_order: Order, sample_slides: list[Slide], sample_event: Event
    ) -> None:
        """retry_clarification extra appears in the prompt."""
        adapter = _CapturingAdapter()
        engine = PredictionEngine(adapter)
        engine.predict_routing(
            sample_order,
            sample_slides,
            sample_event,
            prompt_extras=frozenset({"retry_clarification"}),
        )
        assert "RETRY current step" in adapter.last_prompt

    def test_few_shot_appears_in_prompt(
        self, sample_order: Order, sample_slides: list[Slide], sample_event: Event
    ) -> None:
        """few_shot extra appears in the prompt."""
        adapter = _CapturingAdapter()
        engine = PredictionEngine(adapter)
        engine.predict_routing(
            sample_order,
            sample_slides,
            sample_event,
            prompt_extras=frozenset({"few_shot"}),
        )
        assert "## Example" in adapter.last_prompt
        assert "grossing_complete" in adapter.last_prompt

    def test_no_extras_omits_sections(
        self, sample_order: Order, sample_slides: list[Slide], sample_event: Event
    ) -> None:
        """Default (no extras) does not include extra sections."""
        adapter = _CapturingAdapter()
        engine = PredictionEngine(adapter)
        engine.predict_routing(sample_order, sample_slides, sample_event)
        assert "Workflow Step Sequence" not in adapter.last_prompt
        assert "## Example" not in adapter.last_prompt

    def test_all_extras_combined(
        self, sample_order: Order, sample_slides: list[Slide], sample_event: Event
    ) -> None:
        """All three extras appear together."""
        adapter = _CapturingAdapter()
        engine = PredictionEngine(adapter)
        extras = frozenset({"state_sequence", "retry_clarification", "few_shot"})
        engine.predict_routing(
            sample_order,
            sample_slides,
            sample_event,
            prompt_extras=extras,
        )
        assert "Workflow Step Sequence" in adapter.last_prompt
        assert "RETRY current step" in adapter.last_prompt
        assert "## Example" in adapter.last_prompt


# --- predict_query_from_parts invalid answer_type test (#11) ---


class TestPredictQueryFromPartsValidation:
    def test_invalid_answer_type_raises(self) -> None:
        db_state = DatabaseStateSnapshot(
            orders=(
                {
                    "order_id": "ORD-001",
                    "current_state": "ACCESSIONING",
                    "specimen_type": "Core Needle Biopsy",
                    "anatomic_site": "Left Breast",
                    "priority": "routine",
                    "flags": [],
                },
            ),
            slides=(),
        )
        engine = PredictionEngine(_MockAdapter(_VALID_QUERY_JSON))
        with pytest.raises(ValueError, match="Invalid answer_type"):
            engine.predict_query_from_parts(db_state, "Which orders?", "bogus_type")


# --- Vocabulary hallucination integration tests (GH-97) ---


class TestVocabularyHallucinationIntegration:
    """Integration tests proving vocabulary sections reduce hallucination failures.

    Verifies the end-to-end flow:
    1. Prompt includes vocabulary sections (valid states, flags, and rules)
    2. Validator classifies non-vocabulary outputs as HALLUCINATED_STATE/FLAG/RULE
    3. Both use the same vocabulary source (StateMachine)
    """

    @pytest.fixture()
    def sm(self) -> StateMachine:
        return StateMachine.get_instance()

    def test_prompt_includes_valid_state_vocabulary(
        self,
        sm: StateMachine,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """Engine pipeline passes rendered prompt (with all valid states) to adapter."""
        adapter = _CapturingAdapter()
        engine = PredictionEngine(adapter)
        result = engine.predict_routing(sample_order, sample_slides, sample_event)
        assert result.error is None, f"predict_routing failed: {result.error}"

        all_states = sm.get_all_states()

        prompt = adapter.last_prompt
        assert "Valid Workflow States" in prompt
        for state in all_states:
            assert state in prompt, f"State {state!r} missing from prompt"

    def test_prompt_includes_valid_flag_vocabulary(
        self,
        sm: StateMachine,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """Engine pipeline passes rendered prompt (with all valid flags) to adapter."""
        adapter = _CapturingAdapter()
        engine = PredictionEngine(adapter)
        result = engine.predict_routing(sample_order, sample_slides, sample_event)
        assert result.error is None, f"predict_routing failed: {result.error}"

        all_flag_ids = sm.get_all_flag_ids()

        prompt = adapter.last_prompt
        assert "Valid Flags" in prompt
        for flag_id in all_flag_ids:
            assert flag_id in prompt, f"Flag {flag_id!r} missing from prompt"

    def test_hallucinated_state_classified(
        self,
        sm: StateMachine,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """Model output with an invented state is classified as HALLUCINATED_STATE."""
        hallucinated_output = {
            "next_state": "MICRO_ANALYSIS",
            "applied_rules": ["ACC-001"],
            "flags": [],
            "reasoning": "Routing to micro analysis.",
        }
        adapter = _MockAdapter(json.dumps(hallucinated_output))
        engine = PredictionEngine(adapter)
        result = engine.predict_routing(sample_order, sample_slides, sample_event)

        # Prediction parses successfully (valid JSON, correct schema)
        assert result.error is None
        assert result.next_state == "MICRO_ANALYSIS"

        # Validator classifies it as hallucinated using the same vocabulary source
        expected = {"next_state": "ACCEPTED", "applied_rules": ["ACC-001"], "flags": []}

        failure = classify_failure(
            hallucinated_output,
            expected,
            sm.get_all_states(),
            all_rule_ids=sm.get_all_rule_ids(),
            all_flag_ids=sm.get_all_flag_ids(),
        )
        assert failure == FailureType.HALLUCINATED_STATE

    def test_hallucinated_flag_classified(
        self,
        sm: StateMachine,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """Model output with an invented flag is classified as HALLUCINATED_FLAG."""
        hallucinated_output = {
            "next_state": "ACCEPTED",
            "applied_rules": ["ACC-001"],
            "flags": ["URGENT_RUSH_FLAG"],
            "reasoning": "Accepted with rush flag.",
        }
        adapter = _MockAdapter(json.dumps(hallucinated_output))
        engine = PredictionEngine(adapter)
        result = engine.predict_routing(sample_order, sample_slides, sample_event)

        assert result.error is None
        assert result.flags == ("URGENT_RUSH_FLAG",)

        expected = {"next_state": "ACCEPTED", "applied_rules": ["ACC-001"], "flags": []}

        failure = classify_failure(
            hallucinated_output,
            expected,
            sm.get_all_states(),
            all_rule_ids=sm.get_all_rule_ids(),
            all_flag_ids=sm.get_all_flag_ids(),
        )
        assert failure == FailureType.HALLUCINATED_FLAG

    def test_hallucinated_rule_classified(
        self,
        sm: StateMachine,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """Model output with an invented rule is classified as HALLUCINATED_RULE."""
        hallucinated_output = {
            "next_state": "ACCEPTED",
            "applied_rules": ["FANTASY-999"],
            "flags": [],
            "reasoning": "Accepted with fantasy rule.",
        }
        adapter = _MockAdapter(json.dumps(hallucinated_output))
        engine = PredictionEngine(adapter)
        result = engine.predict_routing(sample_order, sample_slides, sample_event)

        assert result.error is None
        assert result.applied_rules == ("FANTASY-999",)

        expected = {"next_state": "ACCEPTED", "applied_rules": ["ACC-001"], "flags": []}

        failure = classify_failure(
            hallucinated_output,
            expected,
            sm.get_all_states(),
            all_rule_ids=sm.get_all_rule_ids(),
            all_flag_ids=sm.get_all_flag_ids(),
        )
        assert failure == FailureType.HALLUCINATED_RULE

    def test_valid_vocabulary_not_classified_as_hallucination(self, sm: StateMachine) -> None:
        """Model output using valid vocabulary is NOT classified as hallucination."""
        # Pick a real state, flag, and rule from the vocabulary
        real_state = sorted(sm.get_all_states())[0]
        real_flag = sorted(sm.get_all_flag_ids())[0]
        real_rule = sorted(sm.get_all_rule_ids())[0]

        valid_output = {
            "next_state": real_state,
            "applied_rules": [real_rule],
            "flags": [real_flag],
            "reasoning": "Valid routing.",
        }
        expected = {
            "next_state": real_state,
            "applied_rules": [real_rule],
            "flags": [real_flag],
        }

        failure = classify_failure(
            valid_output,
            expected,
            sm.get_all_states(),
            all_rule_ids=sm.get_all_rule_ids(),
            all_flag_ids=sm.get_all_flag_ids(),
        )
        assert failure is None

    def test_vocabulary_nonempty_frozensets(self, sm: StateMachine) -> None:
        """StateMachine vocabulary sets are non-empty frozensets (guards misconfiguration)."""
        prompt_states = sm.get_all_states()
        prompt_flags = sm.get_all_flag_ids()
        prompt_rules = sm.get_all_rule_ids()

        assert isinstance(prompt_states, frozenset)
        assert isinstance(prompt_flags, frozenset)
        assert isinstance(prompt_rules, frozenset)
        assert len(prompt_states) > 0
        assert len(prompt_flags) > 0
        assert len(prompt_rules) > 0

        # Hallucinated values used in tests above are always outside the vocabulary
        assert "MICRO_ANALYSIS" not in prompt_states
        assert "URGENT_RUSH_FLAG" not in prompt_flags
        assert "FANTASY-999" not in prompt_rules


# --- RAG path tests (issues #7, #9, #20) ---


class _MockRagRetriever:
    """Fake RagRetriever that returns preconfigured results."""

    def __init__(
        self,
        results: list[Any] | None = None,
        *,
        raise_on_call: Exception | None = None,
    ) -> None:
        from src.rag.retriever import RetrievalResult

        self._results: list[RetrievalResult] = (
            results
            if results is not None
            else [
                RetrievalResult(
                    text="ACC-001: Validate patient name is present.",
                    source_file="sops/accessioning.md",
                    section_title="Validation Checks",
                    doc_type="sop",
                    similarity_score=0.9,
                ),
            ]
        )
        self._raise_on_call = raise_on_call

    def retrieve_for_routing(
        self,
        current_state: str,
        event_type: str,
        event_data: dict[str, object],
    ) -> Any:
        from src.rag.retriever import RetrievalInfo

        if self._raise_on_call:
            raise self._raise_on_call
        info = RetrievalInfo(
            query_text=f"{current_state} {event_type}",
            chunks_retrieved=len(self._results),
            candidates_before_filter=len(self._results),
            scores=tuple(r.similarity_score for r in self._results),
            top_sources=tuple(r.source_file for r in self._results),
        )
        return self._results, info

    def retrieve_for_query(
        self,
        natural_language_query: str,
    ) -> Any:
        from src.rag.retriever import RetrievalInfo

        if self._raise_on_call:
            raise self._raise_on_call
        info = RetrievalInfo(
            query_text=natural_language_query,
            chunks_retrieved=len(self._results),
            candidates_before_filter=len(self._results),
            scores=tuple(r.similarity_score for r in self._results),
            top_sources=tuple(r.source_file for r in self._results),
        )
        return self._results, info


class TestRagRoutingPath:
    """Tests for predict_routing with rag_retriever."""

    def test_rag_routing_returns_retrieval_info(
        self, sample_order: Order, sample_slides: list[Slide], sample_event: Event
    ) -> None:
        engine = PredictionEngine(_MockAdapter(_VALID_ROUTING_JSON))
        mock_rag = _MockRagRetriever()
        result = engine.predict_routing(
            sample_order,
            sample_slides,
            sample_event,
            rag_retriever=mock_rag,  # type: ignore[arg-type]
        )
        assert result.error is None
        assert result.retrieval_info is not None
        assert result.retrieval_info.chunks_retrieved == 1

    def test_rag_retrieval_error_classified_correctly(
        self, sample_order: Order, sample_slides: list[Slide], sample_event: Event
    ) -> None:
        engine = PredictionEngine(_MockAdapter(_VALID_ROUTING_JSON))
        mock_rag = _MockRagRetriever(raise_on_call=RuntimeError("ChromaDB exploded"))
        result = engine.predict_routing(
            sample_order,
            sample_slides,
            sample_event,
            rag_retriever=mock_rag,  # type: ignore[arg-type]
        )
        assert result.error is not None
        assert "rag_retrieval_error" in result.error
        assert "ChromaDB exploded" in result.error

    def test_rag_empty_results_falls_back(
        self, sample_order: Order, sample_slides: list[Slide], sample_event: Event
    ) -> None:
        """Empty RAG results should fall back to rule catalog, not pass empty context."""
        adapter = _CapturingAdapter()
        engine = PredictionEngine(adapter)
        mock_rag = _MockRagRetriever(results=[])
        engine.predict_routing(
            sample_order,
            sample_slides,
            sample_event,
            rag_retriever=mock_rag,  # type: ignore[arg-type]
        )
        # Prompt should include actual rules, not "No relevant context found."
        assert "No relevant context found" not in adapter.last_prompt


class TestRagQueryPath:
    """Tests for predict_query with rag_retriever."""

    def test_rag_query_returns_retrieval_info(self, sample_query_scenario: QueryScenario) -> None:
        engine = PredictionEngine(_MockAdapter(_VALID_QUERY_JSON))
        mock_rag = _MockRagRetriever()
        result = engine.predict_query(
            sample_query_scenario,
            rag_retriever=mock_rag,  # type: ignore[arg-type]
        )
        assert result.error is None
        assert result.retrieval_info is not None
        assert result.retrieval_info.chunks_retrieved == 1

    def test_rag_query_retrieval_error_classified(
        self, sample_query_scenario: QueryScenario
    ) -> None:
        engine = PredictionEngine(_MockAdapter(_VALID_QUERY_JSON))
        mock_rag = _MockRagRetriever(raise_on_call=RuntimeError("DB failure"))
        result = engine.predict_query(
            sample_query_scenario,
            rag_retriever=mock_rag,  # type: ignore[arg-type]
        )
        assert result.error is not None
        assert "rag_retrieval_error" in result.error

    def test_rag_query_empty_results_keeps_flags(
        self, sample_query_scenario: QueryScenario
    ) -> None:
        """Empty RAG results should still include flag definitions."""
        adapter = _CapturingAdapter()
        # Override the capturing adapter to return valid query JSON

        def patched_predict(prompt: str) -> ModelResponse:
            adapter.last_prompt = prompt
            return ModelResponse(
                raw_text=_VALID_QUERY_JSON,
                parsed_output=json.loads(_VALID_QUERY_JSON),
                latency_ms=100.0,
                input_tokens=50,
                output_tokens=20,
                cost_estimate_usd=None,
                model_id="capturing-model",
            )

        adapter.predict = patched_predict  # type: ignore[assignment]
        engine = PredictionEngine(adapter)
        mock_rag = _MockRagRetriever(results=[])
        engine.predict_query(
            sample_query_scenario,
            rag_retriever=mock_rag,  # type: ignore[arg-type]
        )
        # Should not have "No relevant workflow context found" when empty
        assert "No relevant workflow context found" not in adapter.last_prompt


class TestPredictionResultRetrievalInfoValidation:
    """Test that retrieval_info is excluded on error (issue #20)."""

    def test_rejects_error_with_retrieval_info(self) -> None:
        from src.rag.retriever import RetrievalInfo

        response = ModelResponse(
            raw_text="test",
            parsed_output=None,
            latency_ms=0,
            input_tokens=0,
            output_tokens=0,
            cost_estimate_usd=None,
            model_id="test",
            error="test error",
        )
        info = RetrievalInfo(
            query_text="test",
            chunks_retrieved=1,
            candidates_before_filter=1,
            scores=(0.9,),
            top_sources=("a.md",),
        )
        with pytest.raises(ValueError, match="retrieval_info must be None when error is set"):
            PredictionResult(
                next_state=None,
                applied_rules=(),
                flags=(),
                reasoning=None,
                raw_response=response,
                error="some error",
                retrieval_info=info,
            )
