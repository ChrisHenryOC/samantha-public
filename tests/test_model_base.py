"""Tests for ModelResponse dataclass and ModelAdapter abstract base class."""

from __future__ import annotations

import pytest

from src.models.base import ModelAdapter, ModelResponse

# ---------------------------------------------------------------------------
# ModelResponse validation
# ---------------------------------------------------------------------------


class TestModelResponse:
    def test_valid_response(self) -> None:
        resp = ModelResponse(
            raw_text='{"next_state": "ACCEPTED"}',
            parsed_output={"next_state": "ACCEPTED"},
            latency_ms=150.5,
            input_tokens=500,
            output_tokens=50,
            cost_estimate_usd=0.001,
            model_id="llama3.1:8b",
        )
        assert resp.error is None
        assert resp.parsed_output == {"next_state": "ACCEPTED"}

    def test_valid_response_with_error(self) -> None:
        resp = ModelResponse(
            raw_text="raw output",
            parsed_output=None,
            latency_ms=100.0,
            input_tokens=200,
            output_tokens=20,
            cost_estimate_usd=None,
            model_id="mistral:7b",
            error="parse failure",
        )
        assert resp.parsed_output is None
        assert resp.cost_estimate_usd is None
        assert resp.error == "parse failure"

    def test_valid_response_with_int_latency(self) -> None:
        resp = ModelResponse(
            raw_text="text",
            parsed_output=None,
            latency_ms=150,
            input_tokens=10,
            output_tokens=5,
            cost_estimate_usd=None,
            model_id="test:7b",
        )
        assert resp.latency_ms == 150

    def test_frozen(self) -> None:
        resp = ModelResponse(
            raw_text="text",
            parsed_output=None,
            latency_ms=1.0,
            input_tokens=10,
            output_tokens=5,
            cost_estimate_usd=None,
            model_id="test",
        )
        with pytest.raises(AttributeError):
            resp.raw_text = "mutated"  # type: ignore[misc]

    def test_invalid_raw_text_type(self) -> None:
        with pytest.raises(TypeError, match="raw_text must be str"):
            ModelResponse(
                raw_text=123,  # type: ignore[arg-type]
                parsed_output=None,
                latency_ms=1.0,
                input_tokens=10,
                output_tokens=5,
                cost_estimate_usd=None,
                model_id="test",
            )

    def test_empty_raw_text_rejected(self) -> None:
        with pytest.raises(ValueError, match="raw_text must be a non-empty string"):
            ModelResponse(
                raw_text="",
                parsed_output=None,
                latency_ms=1.0,
                input_tokens=10,
                output_tokens=5,
                cost_estimate_usd=None,
                model_id="test",
            )

    def test_invalid_parsed_output_type(self) -> None:
        with pytest.raises(TypeError, match="parsed_output must be dict or None"):
            ModelResponse(
                raw_text="text",
                parsed_output="not a dict",  # type: ignore[arg-type]
                latency_ms=1.0,
                input_tokens=10,
                output_tokens=5,
                cost_estimate_usd=None,
                model_id="test",
            )

    def test_negative_latency(self) -> None:
        with pytest.raises(ValueError, match="latency_ms must be non-negative"):
            ModelResponse(
                raw_text="text",
                parsed_output=None,
                latency_ms=-1.0,
                input_tokens=10,
                output_tokens=5,
                cost_estimate_usd=None,
                model_id="test",
            )

    def test_latency_ms_bool_rejected(self) -> None:
        with pytest.raises(TypeError, match="latency_ms must be int or float"):
            ModelResponse(
                raw_text="text",
                parsed_output=None,
                latency_ms=True,  # type: ignore[arg-type]
                input_tokens=10,
                output_tokens=5,
                cost_estimate_usd=None,
                model_id="test",
            )

    def test_invalid_input_tokens_type(self) -> None:
        with pytest.raises(TypeError, match="input_tokens must be int"):
            ModelResponse(
                raw_text="text",
                parsed_output=None,
                latency_ms=1.0,
                input_tokens=10.5,  # type: ignore[arg-type]
                output_tokens=5,
                cost_estimate_usd=None,
                model_id="test",
            )

    def test_input_tokens_bool_rejected(self) -> None:
        with pytest.raises(TypeError, match="input_tokens must be int"):
            ModelResponse(
                raw_text="text",
                parsed_output=None,
                latency_ms=1.0,
                input_tokens=True,  # type: ignore[arg-type]
                output_tokens=5,
                cost_estimate_usd=None,
                model_id="test",
            )

    def test_negative_output_tokens(self) -> None:
        with pytest.raises(ValueError, match="output_tokens must be non-negative"):
            ModelResponse(
                raw_text="text",
                parsed_output=None,
                latency_ms=1.0,
                input_tokens=10,
                output_tokens=-1,
                cost_estimate_usd=None,
                model_id="test",
            )

    def test_negative_cost(self) -> None:
        with pytest.raises(ValueError, match="cost_estimate_usd must be non-negative"):
            ModelResponse(
                raw_text="text",
                parsed_output=None,
                latency_ms=1.0,
                input_tokens=10,
                output_tokens=5,
                cost_estimate_usd=-0.01,
                model_id="test",
            )

    def test_invalid_model_id_type(self) -> None:
        with pytest.raises(TypeError, match="model_id must be str"):
            ModelResponse(
                raw_text="text",
                parsed_output=None,
                latency_ms=1.0,
                input_tokens=10,
                output_tokens=5,
                cost_estimate_usd=None,
                model_id=42,  # type: ignore[arg-type]
            )

    def test_empty_model_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="model_id must be a non-empty string"):
            ModelResponse(
                raw_text="text",
                parsed_output=None,
                latency_ms=1.0,
                input_tokens=10,
                output_tokens=5,
                cost_estimate_usd=None,
                model_id="",
            )

    def test_invalid_error_type(self) -> None:
        with pytest.raises(TypeError, match="error must be str or None"):
            ModelResponse(
                raw_text="text",
                parsed_output=None,
                latency_ms=1.0,
                input_tokens=10,
                output_tokens=5,
                cost_estimate_usd=None,
                model_id="test",
                error=123,  # type: ignore[arg-type]
            )

    def test_error_and_parsed_output_mutually_exclusive(self) -> None:
        with pytest.raises(ValueError, match="mutually exclusive"):
            ModelResponse(
                raw_text="partial output",
                parsed_output={"next_state": "ACCEPTED"},
                latency_ms=1.0,
                input_tokens=10,
                output_tokens=5,
                cost_estimate_usd=None,
                model_id="test",
                error="timeout after 120 s",
            )


# ---------------------------------------------------------------------------
# ModelAdapter abstract contract
# ---------------------------------------------------------------------------


class TestModelAdapter:
    def test_cannot_instantiate_directly(self) -> None:
        with pytest.raises(TypeError):
            ModelAdapter()  # type: ignore[abstract]

    def test_concrete_implementation(self) -> None:
        class FakeAdapter(ModelAdapter):
            def predict(self, prompt: str) -> ModelResponse:
                return ModelResponse(
                    raw_text="fake",
                    parsed_output=None,
                    latency_ms=0.0,
                    input_tokens=0,
                    output_tokens=0,
                    cost_estimate_usd=None,
                    model_id="fake:1b",
                )

            @property
            def model_id(self) -> str:
                return "fake:1b"

            @property
            def provider(self) -> str:
                return "test"

        adapter = FakeAdapter()
        assert adapter.model_id == "fake:1b"
        assert adapter.provider == "test"
        resp = adapter.predict("hello")
        assert resp.raw_text == "fake"

    def test_missing_method_raises(self) -> None:
        class IncompleteAdapter(ModelAdapter):
            @property
            def model_id(self) -> str:
                return "incomplete"

            @property
            def provider(self) -> str:
                return "test"

        with pytest.raises(TypeError):
            IncompleteAdapter()  # type: ignore[abstract]
