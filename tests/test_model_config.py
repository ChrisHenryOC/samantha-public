"""Tests for config loading and validation (models.yaml, settings.yaml)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from src.models.config import (
    EvaluationSettings,
    ModelConfig,
    load_models,
    load_rag_settings,
    load_settings,
    validate_config_consistency,
)

# ---------------------------------------------------------------------------
# ModelConfig dataclass validation
# ---------------------------------------------------------------------------


class TestModelConfig:
    def test_valid_config(self) -> None:
        cfg = ModelConfig(
            name="Test Model",
            provider="llamacpp",
            model_id="test:7b",
            temperature=0.0,
            max_tokens=1024,
            token_limit=32768,
        )
        assert cfg.name == "Test Model"
        assert cfg.provider == "llamacpp"

    def test_invalid_provider(self) -> None:
        with pytest.raises(ValueError, match="provider must be one of"):
            ModelConfig(
                name="Bad",
                provider="openai",  # type: ignore[arg-type]
                model_id="gpt-4",
                temperature=0.0,
                max_tokens=1024,
                token_limit=128000,
            )

    def test_empty_name(self) -> None:
        with pytest.raises(ValueError, match="name must be a non-empty string"):
            ModelConfig(
                name="",
                provider="llamacpp",
                model_id="test:7b",
                temperature=0.0,
                max_tokens=1024,
                token_limit=32768,
            )

    def test_temperature_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="temperature must be 0.0"):
            ModelConfig(
                name="Hot",
                provider="llamacpp",
                model_id="test:7b",
                temperature=3.0,
                max_tokens=1024,
                token_limit=32768,
            )

    def test_temperature_bool_rejected(self) -> None:
        with pytest.raises(TypeError, match="temperature must be a number"):
            ModelConfig(
                name="Bad",
                provider="llamacpp",
                model_id="test:7b",
                temperature=True,  # type: ignore[arg-type]
                max_tokens=1024,
                token_limit=32768,
            )

    def test_negative_max_tokens(self) -> None:
        with pytest.raises(ValueError, match="max_tokens must be a positive integer"):
            ModelConfig(
                name="Bad",
                provider="llamacpp",
                model_id="test:7b",
                temperature=0.0,
                max_tokens=-1,
                token_limit=32768,
            )

    def test_max_tokens_bool_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_tokens must be a positive integer"):
            ModelConfig(
                name="Bad",
                provider="llamacpp",
                model_id="test:7b",
                temperature=0.0,
                max_tokens=True,  # type: ignore[arg-type]
                token_limit=32768,
            )

    def test_runs_default_none(self) -> None:
        cfg = ModelConfig(
            name="Default",
            provider="llamacpp",
            model_id="test:7b",
            temperature=0.0,
            max_tokens=1024,
            token_limit=32768,
        )
        assert cfg.runs is None

    def test_runs_positive_int(self) -> None:
        cfg = ModelConfig(
            name="WithRuns",
            provider="openrouter",
            model_id="test-model",
            temperature=0.0,
            max_tokens=1024,
            token_limit=32768,
            runs=5,
        )
        assert cfg.runs == 5

    def test_runs_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="runs must be a positive integer"):
            ModelConfig(
                name="Bad",
                provider="llamacpp",
                model_id="test:7b",
                temperature=0.0,
                max_tokens=1024,
                token_limit=32768,
                runs=0,
            )

    def test_runs_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="runs must be a positive integer"):
            ModelConfig(
                name="Bad",
                provider="llamacpp",
                model_id="test:7b",
                temperature=0.0,
                max_tokens=1024,
                token_limit=32768,
                runs=-3,
            )

    def test_runs_bool_rejected(self) -> None:
        with pytest.raises(ValueError, match="runs must be a positive integer"):
            ModelConfig(
                name="Bad",
                provider="llamacpp",
                model_id="test:7b",
                temperature=0.0,
                max_tokens=1024,
                token_limit=32768,
                runs=True,  # type: ignore[arg-type]
            )

    def test_tier_default_none(self) -> None:
        cfg = ModelConfig(
            name="Default",
            provider="llamacpp",
            model_id="test:7b",
            temperature=0.0,
            max_tokens=1024,
            token_limit=32768,
        )
        assert cfg.tier is None

    def test_tier_valid_values(self) -> None:
        for tier in ("1", "2", "3", "ceiling"):
            cfg = ModelConfig(
                name="Tiered",
                provider="openrouter",
                model_id="test-model",
                temperature=0.0,
                max_tokens=1024,
                token_limit=32768,
                tier=tier,
            )
            assert cfg.tier == tier

    def test_tier_invalid_rejected(self) -> None:
        with pytest.raises(ValueError, match="tier must be one of"):
            ModelConfig(
                name="Bad",
                provider="openrouter",
                model_id="test-model",
                temperature=0.0,
                max_tokens=1024,
                token_limit=32768,
                tier="premium",
            )

    def test_frozen(self) -> None:
        cfg = ModelConfig(
            name="Frozen",
            provider="llamacpp",
            model_id="test:7b",
            temperature=0.0,
            max_tokens=1024,
            token_limit=32768,
        )
        with pytest.raises(AttributeError):
            cfg.name = "Mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# EvaluationSettings dataclass validation
# ---------------------------------------------------------------------------


class TestEvaluationSettings:
    def test_valid_settings(self) -> None:
        settings = EvaluationSettings(
            runs_per_model={"llamacpp": 5, "openrouter": 1},
            timeout_seconds=120,
            output_directory="results",
        )
        assert settings.runs_per_model["llamacpp"] == 5

    def test_invalid_provider_in_runs(self) -> None:
        with pytest.raises(ValueError, match="runs_per_model key must be one of"):
            EvaluationSettings(
                runs_per_model={"openai": 1},
                timeout_seconds=120,
                output_directory="results",
            )

    def test_zero_timeout(self) -> None:
        with pytest.raises(ValueError, match="timeout_seconds must be a positive integer"):
            EvaluationSettings(
                runs_per_model={"llamacpp": 5},
                timeout_seconds=0,
                output_directory="results",
            )

    def test_empty_output_directory(self) -> None:
        with pytest.raises(ValueError, match="output_directory must be a non-empty string"):
            EvaluationSettings(
                runs_per_model={"llamacpp": 5},
                timeout_seconds=120,
                output_directory="",
            )

    def test_frozen(self) -> None:
        settings = EvaluationSettings(
            runs_per_model={"llamacpp": 5, "openrouter": 1},
            timeout_seconds=120,
            output_directory="results",
        )
        with pytest.raises(AttributeError):
            settings.timeout_seconds = 999  # type: ignore[misc]

    def test_defensive_copy_of_runs_per_model(self) -> None:
        original: dict[str, int] = {"llamacpp": 5, "openrouter": 1}
        settings = EvaluationSettings(
            runs_per_model=original,
            timeout_seconds=120,
            output_directory="results",
        )
        original["llamacpp"] = 999
        assert settings.runs_per_model["llamacpp"] == 5


# ---------------------------------------------------------------------------
# YAML loaders
# ---------------------------------------------------------------------------


class TestLoadModels:
    def test_load_project_models(self) -> None:
        """Load the real config/models.yaml and verify structure."""
        configs = load_models()
        assert len(configs) > 0
        for cfg in configs:
            assert cfg.provider in ("llamacpp", "ollama", "openrouter")
            assert cfg.max_tokens > 0
            assert cfg.tier is not None, f"Model {cfg.name!r} is missing a tier value"
            assert cfg.tier in ("1", "2", "3", "ceiling"), (
                f"Model {cfg.name!r} has invalid tier {cfg.tier!r}"
            )

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_models(tmp_path / "nonexistent.yaml")

    def test_missing_models_key(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.yaml"
        p.write_text("not_models: []")
        with pytest.raises(ValueError, match="top-level 'models' key"):
            load_models(p)

    def test_missing_required_field(self, tmp_path: Path) -> None:
        data: dict[str, Any] = {"models": [{"name": "Incomplete", "provider": "llamacpp"}]}
        p = tmp_path / "incomplete.yaml"
        p.write_text(yaml.dump(data))
        with pytest.raises(ValueError, match="Missing required keys"):
            load_models(p)

    def test_empty_models_list(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.yaml"
        p.write_text("models: []")
        with pytest.raises(ValueError, match="must contain at least one entry"):
            load_models(p)

    def test_models_key_is_null(self, tmp_path: Path) -> None:
        p = tmp_path / "null_models.yaml"
        p.write_text("models: null")
        with pytest.raises(ValueError, match="'models' must be a list"):
            load_models(p)

    def test_malformed_yaml(self, tmp_path: Path) -> None:
        p = tmp_path / "bad_syntax.yaml"
        p.write_text("models:\n  - name: bad\n    provider: [unterminated")
        with pytest.raises(ValueError, match="Failed to parse YAML"):
            load_models(p)

    def test_load_valid_yaml(self, tmp_path: Path) -> None:
        data = {
            "models": [
                {
                    "name": "Test 7B",
                    "provider": "llamacpp",
                    "model_id": "test:7b",
                    "parameters": {"temperature": 0.0, "max_tokens": 512},
                    "token_limit": 32768,
                }
            ]
        }
        p = tmp_path / "models.yaml"
        p.write_text(yaml.dump(data))
        configs = load_models(p)
        assert len(configs) == 1
        assert configs[0].name == "Test 7B"

    def test_load_yaml_with_runs(self, tmp_path: Path) -> None:
        data = {
            "models": [
                {
                    "name": "With Runs",
                    "provider": "openrouter",
                    "model_id": "test-model",
                    "runs": 5,
                    "parameters": {"temperature": 0.0, "max_tokens": 512},
                    "token_limit": 32768,
                },
                {
                    "name": "Without Runs",
                    "provider": "openrouter",
                    "model_id": "test-model-2",
                    "parameters": {"temperature": 0.0, "max_tokens": 512},
                    "token_limit": 32768,
                },
            ]
        }
        p = tmp_path / "models.yaml"
        p.write_text(yaml.dump(data))
        configs = load_models(p)
        assert configs[0].runs == 5
        assert configs[1].runs is None

    def test_load_yaml_with_invalid_runs_type(self, tmp_path: Path) -> None:
        data = {
            "models": [
                {
                    "name": "Bad Runs",
                    "provider": "openrouter",
                    "model_id": "test-model",
                    "runs": "five",
                    "parameters": {"temperature": 0.0, "max_tokens": 512},
                    "token_limit": 32768,
                }
            ]
        }
        p = tmp_path / "models.yaml"
        p.write_text(yaml.dump(data))
        with pytest.raises(ValueError, match="runs must be a positive int or omitted"):
            load_models(p)

    def test_load_yaml_with_tier(self, tmp_path: Path) -> None:
        data = {
            "models": [
                {
                    "name": "Tiered Model",
                    "provider": "openrouter",
                    "model_id": "test-model",
                    "tier": 1,
                    "parameters": {"temperature": 0.0, "max_tokens": 512},
                    "token_limit": 32768,
                },
                {
                    "name": "Ceiling Model",
                    "provider": "openrouter",
                    "model_id": "test-ceiling",
                    "tier": "ceiling",
                    "parameters": {"temperature": 0.0, "max_tokens": 512},
                    "token_limit": 32768,
                },
                {
                    "name": "No Tier",
                    "provider": "openrouter",
                    "model_id": "test-no-tier",
                    "parameters": {"temperature": 0.0, "max_tokens": 512},
                    "token_limit": 32768,
                },
            ]
        }
        p = tmp_path / "models.yaml"
        p.write_text(yaml.dump(data))
        configs = load_models(p)
        assert configs[0].tier == "1"
        assert configs[1].tier == "ceiling"
        assert configs[2].tier is None

    def test_load_yaml_with_invalid_tier(self, tmp_path: Path) -> None:
        data = {
            "models": [
                {
                    "name": "Bad Tier",
                    "provider": "openrouter",
                    "model_id": "test-model",
                    "tier": "premium",
                    "parameters": {"temperature": 0.0, "max_tokens": 512},
                    "token_limit": 32768,
                }
            ]
        }
        p = tmp_path / "models.yaml"
        p.write_text(yaml.dump(data))
        with pytest.raises(ValueError, match="tier must be one of"):
            load_models(p)

    def test_load_yaml_with_runs_bool(self, tmp_path: Path) -> None:
        data = {
            "models": [
                {
                    "name": "Bool Runs",
                    "provider": "openrouter",
                    "model_id": "test-model",
                    "runs": True,
                    "parameters": {"temperature": 0.0, "max_tokens": 512},
                    "token_limit": 32768,
                }
            ]
        }
        p = tmp_path / "models.yaml"
        p.write_text(yaml.dump(data))
        with pytest.raises(ValueError, match="runs must be a positive int or omitted"):
            load_models(p)


class TestLoadSettings:
    def test_load_project_settings(self) -> None:
        """Load the real config/settings.yaml and verify structure."""
        settings = load_settings()
        assert settings.timeout_seconds > 0
        assert "openrouter" in settings.runs_per_model

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_settings(tmp_path / "nonexistent.yaml")

    def test_missing_evaluation_key(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.yaml"
        p.write_text("wrong_key: {}")
        with pytest.raises(ValueError, match="top-level 'evaluation' key"):
            load_settings(p)

    def test_missing_required_field(self, tmp_path: Path) -> None:
        data = {"evaluation": {"runs_per_model": {"llamacpp": 5}}}
        p = tmp_path / "incomplete.yaml"
        p.write_text(yaml.dump(data))
        with pytest.raises(ValueError, match="Missing required keys"):
            load_settings(p)

    def test_evaluation_value_is_null(self, tmp_path: Path) -> None:
        p = tmp_path / "null_eval.yaml"
        p.write_text("evaluation:")
        with pytest.raises(ValueError, match="'evaluation' must be a mapping"):
            load_settings(p)

    def test_malformed_yaml(self, tmp_path: Path) -> None:
        p = tmp_path / "bad_syntax.yaml"
        p.write_text("evaluation:\n  timeout: [unterminated")
        with pytest.raises(ValueError, match="Failed to parse YAML"):
            load_settings(p)


class TestLoadRagSettings:
    def test_fallback_defaults_when_rag_section_missing(self, tmp_path: Path) -> None:
        p = tmp_path / "no_rag.yaml"
        p.write_text(yaml.dump({"evaluation": {"timeout_seconds": 60}}))
        settings = load_rag_settings(p)
        assert settings.top_k == 10
        assert settings.similarity_threshold == 0.3
        assert settings.index_path == "data/rag_index"


# ---------------------------------------------------------------------------
# output_directory path traversal
# ---------------------------------------------------------------------------


class TestOutputDirectoryPathTraversal:
    def test_relative_path_within_project(self) -> None:
        settings = EvaluationSettings(
            runs_per_model={"llamacpp": 5},
            timeout_seconds=120,
            output_directory="results",
        )
        assert settings.output_directory == "results"

    def test_path_traversal_rejected(self) -> None:
        with pytest.raises(ValueError, match="must resolve within the project root"):
            EvaluationSettings(
                runs_per_model={"llamacpp": 5},
                timeout_seconds=120,
                output_directory="../../tmp/exfil",
            )


# ---------------------------------------------------------------------------
# Cross-validation
# ---------------------------------------------------------------------------


class TestConfigConsistency:
    def test_valid_consistency(self) -> None:
        models = [
            ModelConfig(
                name="Test",
                provider="llamacpp",
                model_id="test:7b",
                temperature=0.0,
                max_tokens=1024,
                token_limit=32768,
            )
        ]
        settings = EvaluationSettings(
            runs_per_model={"llamacpp": 5, "openrouter": 1},
            timeout_seconds=120,
            output_directory="results",
        )
        validate_config_consistency(models, settings)

    def test_missing_provider_in_settings(self) -> None:
        models = [
            ModelConfig(
                name="Test",
                provider="llamacpp",
                model_id="test:7b",
                temperature=0.0,
                max_tokens=1024,
                token_limit=32768,
            ),
            ModelConfig(
                name="Cloud",
                provider="openrouter",
                model_id="claude-haiku-4-5-20251001",
                temperature=0.0,
                max_tokens=1024,
                token_limit=200000,
            ),
        ]
        settings = EvaluationSettings(
            runs_per_model={"llamacpp": 5},
            timeout_seconds=120,
            output_directory="results",
        )
        with pytest.raises(ValueError, match="missing entries for providers"):
            validate_config_consistency(models, settings)
