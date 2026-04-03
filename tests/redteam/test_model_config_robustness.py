"""Red-team tests for src/models/config.py — type confusion, boundary values, YAML loading."""

from __future__ import annotations

import math
from collections.abc import Callable
from pathlib import Path

import pytest

from src.models.config import (
    EvaluationSettings,
    ModelConfig,
    load_models,
    load_settings,
    validate_config_consistency,
)

from .conftest import (
    _minimal_valid_model_entry,
    _minimal_valid_settings_yaml,
)

# Common ModelConfig keyword args for tests that need a valid base.
_BASE = dict(
    name="m",
    provider="llamacpp",
    model_id="x",
    temperature=0.7,
    max_tokens=512,
    token_limit=4096,
)


# ---------------------------------------------------------------------------
# ModelConfig type confusion
# ---------------------------------------------------------------------------


class TestModelConfigTypeConfusion:
    """Type confusion attacks on ModelConfig fields."""

    def test_bool_true_as_temperature_rejected(self) -> None:
        with pytest.raises(TypeError, match="temperature must be a number"):
            ModelConfig(**{**_BASE, "temperature": True})

    def test_bool_false_as_temperature_rejected(self) -> None:
        with pytest.raises(TypeError, match="temperature must be a number"):
            ModelConfig(**{**_BASE, "temperature": False})

    def test_bool_true_as_max_tokens_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_tokens must be a positive integer"):
            ModelConfig(**{**_BASE, "max_tokens": True})

    def test_bool_false_as_max_tokens_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_tokens must be a positive integer"):
            ModelConfig(**{**_BASE, "max_tokens": False})

    def test_bool_true_as_token_limit_rejected(self) -> None:
        with pytest.raises(ValueError, match="token_limit must be a positive integer"):
            ModelConfig(**{**_BASE, "token_limit": True})

    def test_bool_false_as_token_limit_rejected(self) -> None:
        with pytest.raises(ValueError, match="token_limit must be a positive integer"):
            ModelConfig(**{**_BASE, "token_limit": False})

    def test_none_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="name must be a non-empty string"):
            ModelConfig(
                **{**_BASE, "name": None},  # type: ignore[arg-type]
            )

    def test_int_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="name must be a non-empty string"):
            ModelConfig(
                **{**_BASE, "name": 42},  # type: ignore[arg-type]
            )

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="name must be a non-empty string"):
            ModelConfig(**{**_BASE, "name": ""})

    def test_invalid_provider_rejected(self) -> None:
        with pytest.raises(ValueError, match="provider must be one of"):
            ModelConfig(
                **{**_BASE, "provider": "invalid"},  # type: ignore[arg-type]
            )

    def test_empty_model_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="model_id must be a non-empty string"):
            ModelConfig(**{**_BASE, "model_id": ""})

    def test_none_model_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="model_id must be a non-empty string"):
            ModelConfig(
                **{**_BASE, "model_id": None},  # type: ignore[arg-type]
            )


# ---------------------------------------------------------------------------
# ModelConfig boundary values
# ---------------------------------------------------------------------------


class TestModelConfigBoundaryValues:
    """Boundary-value attacks on ModelConfig numeric fields."""

    def test_temperature_zero_accepted(self) -> None:
        mc = ModelConfig(**{**_BASE, "temperature": 0.0})
        assert mc.temperature == 0.0

    def test_temperature_two_accepted(self) -> None:
        mc = ModelConfig(**{**_BASE, "temperature": 2.0})
        assert mc.temperature == 2.0

    def test_temperature_below_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="temperature must be 0.0"):
            ModelConfig(**{**_BASE, "temperature": -0.001})

    def test_temperature_above_two_rejected(self) -> None:
        with pytest.raises(ValueError, match="temperature must be 0.0"):
            ModelConfig(**{**_BASE, "temperature": 2.001})

    def test_temperature_nan_rejected(self) -> None:
        with pytest.raises(ValueError, match="temperature must be 0.0"):
            ModelConfig(**{**_BASE, "temperature": float("nan")})

    def test_temperature_inf_rejected(self) -> None:
        with pytest.raises(ValueError, match="temperature must be 0.0"):
            ModelConfig(**{**_BASE, "temperature": math.inf})

    def test_max_tokens_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_tokens must be a positive integer"):
            ModelConfig(**{**_BASE, "max_tokens": 0})

    def test_max_tokens_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_tokens must be a positive integer"):
            ModelConfig(**{**_BASE, "max_tokens": -1})

    def test_runs_float_rejected(self) -> None:
        with pytest.raises(ValueError, match="runs must be a positive integer"):
            ModelConfig(**{**_BASE, "runs": 1.0})  # type: ignore[arg-type]

    def test_runs_list_rejected(self) -> None:
        with pytest.raises(ValueError, match="runs must be a positive integer"):
            ModelConfig(**{**_BASE, "runs": [3]})  # type: ignore[arg-type]

    def test_runs_string_rejected(self) -> None:
        with pytest.raises(ValueError, match="runs must be a positive integer"):
            ModelConfig(**{**_BASE, "runs": "5"})  # type: ignore[arg-type]


class TestLoadModelsRunsYAMLRobustness:
    """YAML-level validation for the runs field via load_models()."""

    def test_runs_float_in_yaml_rejected(
        self,
        make_models_yaml: Callable[..., Path],
    ) -> None:
        entry = _minimal_valid_model_entry()
        entry["runs"] = 1.0
        p = make_models_yaml({"models": [entry]})
        with pytest.raises(ValueError, match="runs must be a positive int"):
            load_models(p)

    def test_runs_bool_in_yaml_rejected(
        self,
        make_models_yaml: Callable[..., Path],
    ) -> None:
        entry = _minimal_valid_model_entry()
        entry["runs"] = True
        p = make_models_yaml({"models": [entry]})
        with pytest.raises(ValueError, match="runs must be a positive int"):
            load_models(p)

    def test_runs_zero_in_yaml_rejected(
        self,
        make_models_yaml: Callable[..., Path],
    ) -> None:
        entry = _minimal_valid_model_entry()
        entry["runs"] = 0
        p = make_models_yaml({"models": [entry]})
        with pytest.raises(ValueError, match="runs must be a positive int"):
            load_models(p)

    def test_runs_negative_in_yaml_rejected(
        self,
        make_models_yaml: Callable[..., Path],
    ) -> None:
        entry = _minimal_valid_model_entry()
        entry["runs"] = -3
        p = make_models_yaml({"models": [entry]})
        with pytest.raises(ValueError, match="runs must be a positive int"):
            load_models(p)


# ---------------------------------------------------------------------------
# EvaluationSettings type confusion
# ---------------------------------------------------------------------------


class TestEvaluationSettingsTypeConfusion:
    """Type confusion attacks on EvaluationSettings."""

    def test_runs_per_model_as_list_rejected(self) -> None:
        with pytest.raises(
            (TypeError, ValueError),
            match=r"runs_per_model|dictionary update sequence",
        ):
            EvaluationSettings(
                runs_per_model=[3, 5],  # type: ignore[arg-type]
                timeout_seconds=60,
                output_directory="results",
            )

    def test_runs_per_model_as_string_rejected(self) -> None:
        with pytest.raises(
            (TypeError, ValueError),
            match=r"runs_per_model|dictionary update sequence",
        ):
            EvaluationSettings(
                runs_per_model="5",  # type: ignore[arg-type]
                timeout_seconds=60,
                output_directory="results",
            )

    def test_bool_count_value_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be a positive integer"):
            EvaluationSettings(
                runs_per_model={"llamacpp": True},
                timeout_seconds=60,
                output_directory="results",
            )

    def test_zero_count_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be a positive integer"):
            EvaluationSettings(
                runs_per_model={"llamacpp": 0},
                timeout_seconds=60,
                output_directory="results",
            )

    def test_negative_count_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be a positive integer"):
            EvaluationSettings(
                runs_per_model={"llamacpp": -1},
                timeout_seconds=60,
                output_directory="results",
            )

    def test_bool_timeout_rejected(self) -> None:
        with pytest.raises(ValueError, match="timeout_seconds must be a positive integer"):
            EvaluationSettings(
                runs_per_model={"llamacpp": 3},
                timeout_seconds=True,
                output_directory="results",
            )

    def test_zero_timeout_rejected(self) -> None:
        with pytest.raises(ValueError, match="timeout_seconds must be a positive integer"):
            EvaluationSettings(
                runs_per_model={"llamacpp": 3},
                timeout_seconds=0,
                output_directory="results",
            )

    def test_invalid_provider_key_rejected(self) -> None:
        with pytest.raises(ValueError, match="runs_per_model key must be one of"):
            EvaluationSettings(
                runs_per_model={"bad_provider": 3},
                timeout_seconds=60,
                output_directory="results",
            )


# ---------------------------------------------------------------------------
# EvaluationSettings path traversal
# ---------------------------------------------------------------------------


class TestEvaluationSettingsPathTraversal:
    """Path traversal attacks on output_directory."""

    def test_traversal_up_rejected(self) -> None:
        with pytest.raises(ValueError, match="must resolve within the project root"):
            EvaluationSettings(
                runs_per_model={"llamacpp": 3},
                timeout_seconds=60,
                output_directory="../../etc",
            )

    def test_absolute_path_rejected(self) -> None:
        with pytest.raises(ValueError, match="must resolve within the project root"):
            EvaluationSettings(
                runs_per_model={"llamacpp": 3},
                timeout_seconds=60,
                output_directory="/tmp/evil",
            )

    def test_dotdot_only_rejected(self) -> None:
        with pytest.raises(ValueError, match="must resolve within the project root"):
            EvaluationSettings(
                runs_per_model={"llamacpp": 3},
                timeout_seconds=60,
                output_directory="..",
            )

    def test_empty_output_directory_rejected(self) -> None:
        with pytest.raises(ValueError, match="output_directory must be a non-empty string"):
            EvaluationSettings(
                runs_per_model={"llamacpp": 3},
                timeout_seconds=60,
                output_directory="",
            )

    def test_int_output_directory_rejected(self) -> None:
        with pytest.raises(ValueError, match="output_directory must be a non-empty string"):
            EvaluationSettings(
                runs_per_model={"llamacpp": 3},
                timeout_seconds=60,
                output_directory=42,  # type: ignore[arg-type]
            )


# ---------------------------------------------------------------------------
# load_models YAML robustness
# ---------------------------------------------------------------------------


class TestLoadModelsYAMLRobustness:
    """Adversarial YAML structures for load_models()."""

    def test_list_root_rejected(
        self,
        make_models_yaml: Callable[..., Path],
    ) -> None:
        p = make_models_yaml([{"models": []}])
        with pytest.raises(ValueError, match="top-level 'models' key"):
            load_models(p)

    def test_scalar_root_rejected(
        self,
        make_models_yaml: Callable[..., Path],
    ) -> None:
        p = make_models_yaml("just a string")
        with pytest.raises(ValueError, match="top-level 'models' key"):
            load_models(p)

    def test_missing_models_key(
        self,
        make_models_yaml: Callable[..., Path],
    ) -> None:
        p = make_models_yaml({"not_models": []})
        with pytest.raises(ValueError, match="top-level 'models' key"):
            load_models(p)

    def test_empty_models_list(
        self,
        make_models_yaml: Callable[..., Path],
    ) -> None:
        p = make_models_yaml({"models": []})
        with pytest.raises(ValueError, match="at least one entry"):
            load_models(p)

    def test_string_entries_rejected(
        self,
        make_models_yaml: Callable[..., Path],
    ) -> None:
        p = make_models_yaml({"models": ["not-a-dict"]})
        with pytest.raises(ValueError, match="must be a mapping"):
            load_models(p)

    def test_bad_parameters_type(
        self,
        make_models_yaml: Callable[..., Path],
    ) -> None:
        entry = _minimal_valid_model_entry()
        entry["parameters"] = "not-a-dict"
        p = make_models_yaml({"models": [entry]})
        with pytest.raises(ValueError, match="'parameters' must be a mapping"):
            load_models(p)

    def test_missing_file_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_models(Path("/nonexistent/models.yaml"))

    def test_valid_yaml_loads(
        self,
        make_models_yaml: Callable[..., Path],
    ) -> None:
        p = make_models_yaml()
        configs = load_models(p)
        assert len(configs) == 1
        assert configs[0].name == "test-model"


# ---------------------------------------------------------------------------
# load_settings YAML robustness
# ---------------------------------------------------------------------------


class TestLoadSettingsYAMLRobustness:
    """Adversarial YAML structures for load_settings()."""

    def test_missing_evaluation_key(
        self,
        make_settings_yaml: Callable[..., Path],
    ) -> None:
        p = make_settings_yaml({"not_evaluation": {}})
        with pytest.raises(ValueError, match="top-level 'evaluation' key"):
            load_settings(p)

    def test_evaluation_as_list(
        self,
        make_settings_yaml: Callable[..., Path],
    ) -> None:
        p = make_settings_yaml({"evaluation": [1, 2]})
        with pytest.raises(ValueError, match="'evaluation' must be a mapping"):
            load_settings(p)

    def test_runs_per_model_as_list(
        self,
        make_settings_yaml: Callable[..., Path],
    ) -> None:
        data = _minimal_valid_settings_yaml()
        data["evaluation"]["runs_per_model"] = [3, 5]
        p = make_settings_yaml(data)
        with pytest.raises(ValueError, match="runs_per_model must be a mapping"):
            load_settings(p)

    def test_missing_file_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_settings(Path("/nonexistent/settings.yaml"))


# ---------------------------------------------------------------------------
# validate_config_consistency
# ---------------------------------------------------------------------------


class TestValidateConfigConsistency:
    """Edge cases for config consistency check."""

    def test_missing_provider_raises(self) -> None:
        models = [
            ModelConfig(
                name="m",
                provider="openrouter",
                model_id="x",
                temperature=0.7,
                max_tokens=512,
                token_limit=4096,
            )
        ]
        settings = EvaluationSettings(
            runs_per_model={"llamacpp": 3},
            timeout_seconds=60,
            output_directory="results",
        )
        with pytest.raises(ValueError, match="missing entries for providers"):
            validate_config_consistency(models, settings)

    def test_empty_models_passes(self) -> None:
        settings = EvaluationSettings(
            runs_per_model={"llamacpp": 3},
            timeout_seconds=60,
            output_directory="results",
        )
        validate_config_consistency([], settings)

    def test_all_providers_covered(self) -> None:
        models = [ModelConfig(**_BASE)]
        settings = EvaluationSettings(
            runs_per_model={"llamacpp": 3},
            timeout_seconds=60,
            output_directory="results",
        )
        validate_config_consistency(models, settings)

    def test_extra_settings_provider_passes(self) -> None:
        models = [ModelConfig(**_BASE)]
        settings = EvaluationSettings(
            runs_per_model={"llamacpp": 3, "openrouter": 1},
            timeout_seconds=60,
            output_directory="results",
        )
        validate_config_consistency(models, settings)
