"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from src.models.config import EvaluationSettings, ModelConfig, RagSettings

_YAML_PATH = Path(__file__).resolve().parent.parent / "knowledge_base" / "workflow_states.yaml"


@pytest.fixture(scope="session")
def workflow_data() -> dict[str, Any]:
    """Load the workflow YAML once for the entire test session."""
    with open(_YAML_PATH) as f:
        data: dict[str, Any] = yaml.safe_load(f)
    return data


def make_mock_settings() -> EvaluationSettings:
    return EvaluationSettings(
        runs_per_model={"llamacpp": 1, "openrouter": 1},
        timeout_seconds=120,
        output_directory="results",
    )


def make_mock_model() -> ModelConfig:
    return ModelConfig(
        name="test-model",
        provider="llamacpp",
        model_id="test-model",
        temperature=0.0,
        max_tokens=2048,
        token_limit=8192,
    )


def make_mock_rag_settings() -> RagSettings:
    return RagSettings(top_k=3, similarity_threshold=0.0, index_path="/tmp/test_rag_index")
