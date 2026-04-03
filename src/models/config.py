"""Configuration loading and validation for model definitions and settings.

Reads ``config/models.yaml`` and ``config/settings.yaml``, validates their
structure, and exposes typed frozen dataclasses for the rest of the system.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast, get_args

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_CONFIG_DIR = _PROJECT_ROOT / "config"

Provider = Literal["llamacpp", "ollama", "openrouter"]
Tier = Literal["1", "2", "3", "ceiling"]

_VALID_PROVIDERS: frozenset[str] = frozenset(get_args(Provider))
_VALID_TIERS: frozenset[str] = frozenset(get_args(Tier))


# --- Dataclasses ---


def _validate_model_config(obj: ModelConfig) -> None:
    """Validate ModelConfig field types and values."""
    if not isinstance(obj.name, str) or not obj.name:
        raise ValueError("ModelConfig.name must be a non-empty string")
    if obj.provider not in _VALID_PROVIDERS:
        raise ValueError(
            f"ModelConfig.provider must be one of {sorted(_VALID_PROVIDERS)}, got {obj.provider!r}"
        )
    if not isinstance(obj.model_id, str) or not obj.model_id:
        raise ValueError("ModelConfig.model_id must be a non-empty string")
    if not isinstance(obj.temperature, (int, float)) or isinstance(obj.temperature, bool):
        raise TypeError(
            f"ModelConfig.temperature must be a number, got {type(obj.temperature).__name__}"
        )
    if not (0.0 <= obj.temperature <= 2.0):
        raise ValueError(f"ModelConfig.temperature must be 0.0–2.0, got {obj.temperature}")
    if (
        not isinstance(obj.max_tokens, int)
        or isinstance(obj.max_tokens, bool)
        or obj.max_tokens <= 0
    ):
        raise ValueError(f"ModelConfig.max_tokens must be a positive integer, got {obj.max_tokens}")
    if (
        not isinstance(obj.token_limit, int)
        or isinstance(obj.token_limit, bool)
        or obj.token_limit <= 0
    ):
        raise ValueError(
            f"ModelConfig.token_limit must be a positive integer, got {obj.token_limit}"
        )
    if obj.runs is not None and (
        not isinstance(obj.runs, int) or isinstance(obj.runs, bool) or obj.runs <= 0
    ):
        raise ValueError(f"ModelConfig.runs must be a positive integer or None, got {obj.runs}")
    if obj.tier is not None and (not isinstance(obj.tier, str) or obj.tier not in _VALID_TIERS):
        raise ValueError(
            f"ModelConfig.tier must be one of {sorted(_VALID_TIERS)} or None, got {obj.tier!r}"
        )


@dataclass(frozen=True)
class ModelConfig:
    """Validated configuration for a single model."""

    name: str
    provider: Provider
    model_id: str
    temperature: float
    max_tokens: int
    token_limit: int
    runs: int | None = None
    tier: Tier | None = None

    def __post_init__(self) -> None:
        _validate_model_config(self)


def _validate_settings(obj: EvaluationSettings) -> None:
    """Validate EvaluationSettings field types and values."""
    if not isinstance(obj.runs_per_model, dict):
        raise TypeError("runs_per_model must be a dict")
    for provider, count in obj.runs_per_model.items():
        if provider not in _VALID_PROVIDERS:
            raise ValueError(
                f"runs_per_model key must be one of {sorted(_VALID_PROVIDERS)}, got {provider!r}"
            )
        if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
            raise ValueError(
                f"runs_per_model[{provider!r}] must be a positive integer, got {count}"
            )
    if (
        not isinstance(obj.timeout_seconds, int)
        or isinstance(obj.timeout_seconds, bool)
        or obj.timeout_seconds <= 0
    ):
        raise ValueError(f"timeout_seconds must be a positive integer, got {obj.timeout_seconds}")
    if not isinstance(obj.output_directory, str) or not obj.output_directory:
        raise ValueError("output_directory must be a non-empty string")
    resolved = (_PROJECT_ROOT / obj.output_directory).resolve()
    if not resolved.is_relative_to(_PROJECT_ROOT):
        raise ValueError(
            f"output_directory must resolve within the project root, got {obj.output_directory!r}"
        )


@dataclass(frozen=True)
class EvaluationSettings:
    """Validated evaluation parameters."""

    runs_per_model: dict[str, int]
    timeout_seconds: int
    output_directory: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "runs_per_model", dict(self.runs_per_model))
        _validate_settings(self)


# --- Loaders ---


def load_models(path: Path | None = None) -> list[ModelConfig]:
    """Load and validate model definitions from YAML.

    Parameters
    ----------
    path:
        Path to ``models.yaml``. Defaults to ``config/models.yaml``
        relative to the project root.

    Returns
    -------
    list[ModelConfig]
        Validated model configurations.

    Raises
    ------
    FileNotFoundError
        If the YAML file does not exist.
    ValueError
        If the YAML structure is invalid or a model entry fails validation.
    """
    if path is None:
        path = _CONFIG_DIR / "models.yaml"

    with open(path, encoding="utf-8") as f:
        try:
            raw: Any = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            raise ValueError(f"Failed to parse YAML in {path}: {exc}") from exc

    if not isinstance(raw, dict) or "models" not in raw:
        raise ValueError("models.yaml must contain a top-level 'models' key")

    entries: Any = raw["models"]
    if not isinstance(entries, list):
        raise ValueError("models.yaml 'models' must be a list")
    if len(entries) == 0:
        raise ValueError("models.yaml 'models' must contain at least one entry")

    configs: list[ModelConfig] = []
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"Model entry {i} must be a mapping")
        entry_loc = f"entry {i}"
        required = {"name", "provider", "model_id", "parameters", "token_limit"}
        _require_keys(entry, required, entry_loc)
        params = entry["parameters"]
        if not isinstance(params, dict):
            raise ValueError(f"Model entry {i} 'parameters' must be a mapping")
        _require_keys(params, {"temperature", "max_tokens"}, f"entry {i}.parameters")

        try:
            temperature = float(params["temperature"])
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"Model entry {i} ({entry.get('name', '<unnamed>')!r}): "
                f"invalid temperature value {params['temperature']!r}"
            ) from exc

        if not isinstance(params["max_tokens"], int) or isinstance(params["max_tokens"], bool):
            raise ValueError(
                f"Model entry {i} ({entry.get('name', '<unnamed>')!r}): "
                f"max_tokens must be int, got {type(params['max_tokens']).__name__}"
            )
        if not isinstance(entry["token_limit"], int) or isinstance(entry["token_limit"], bool):
            raise ValueError(
                f"Model entry {i} ({entry.get('name', '<unnamed>')!r}): "
                f"token_limit must be int, got {type(entry['token_limit']).__name__}"
            )

        runs_value: int | None = entry.get("runs")
        if runs_value is not None and (
            not isinstance(runs_value, int) or isinstance(runs_value, bool) or runs_value <= 0
        ):
            raise ValueError(
                f"Model entry {i} ({entry.get('name', '<unnamed>')!r}): "
                f"runs must be a positive int or omitted, got {runs_value!r}"
            )

        tier_raw = entry.get("tier")
        tier_value: str | None = None
        if tier_raw is not None:
            if not isinstance(tier_raw, (int, str)):
                raise ValueError(
                    f"Model entry {i} ({entry.get('name', '<unnamed>')!r}): "
                    f"tier must be int or string, got {type(tier_raw).__name__}"
                )
            tier_value = str(tier_raw)
            if tier_value not in _VALID_TIERS:
                raise ValueError(
                    f"Model entry {i} ({entry.get('name', '<unnamed>')!r}): "
                    f"tier must be one of {sorted(_VALID_TIERS)} or omitted, got {tier_raw!r}"
                )

        configs.append(
            ModelConfig(
                name=entry["name"],
                provider=entry["provider"],
                model_id=entry["model_id"],
                temperature=temperature,
                max_tokens=params["max_tokens"],
                token_limit=entry["token_limit"],
                runs=runs_value,
                tier=cast("Tier | None", tier_value),
            )
        )
    return configs


def load_settings(path: Path | None = None) -> EvaluationSettings:
    """Load and validate evaluation settings from YAML.

    Parameters
    ----------
    path:
        Path to ``settings.yaml``. Defaults to ``config/settings.yaml``
        relative to the project root.

    Returns
    -------
    EvaluationSettings
        Validated evaluation settings.

    Raises
    ------
    FileNotFoundError
        If the YAML file does not exist.
    ValueError
        If the YAML structure is invalid or settings fail validation.
    """
    if path is None:
        path = _CONFIG_DIR / "settings.yaml"

    with open(path, encoding="utf-8") as f:
        try:
            raw: Any = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            raise ValueError(f"Failed to parse YAML in {path}: {exc}") from exc

    if not isinstance(raw, dict) or "evaluation" not in raw:
        raise ValueError("settings.yaml must contain a top-level 'evaluation' key")

    ev: Any = raw["evaluation"]
    if not isinstance(ev, dict):
        raise ValueError("settings.yaml 'evaluation' must be a mapping")

    _require_keys(ev, {"runs_per_model", "timeout_seconds", "output_directory"}, "evaluation")

    runs: Any = ev["runs_per_model"]
    if not isinstance(runs, dict):
        raise ValueError("evaluation.runs_per_model must be a mapping")

    if not isinstance(ev["timeout_seconds"], int) or isinstance(ev["timeout_seconds"], bool):
        raise ValueError(f"timeout_seconds must be int, got {type(ev['timeout_seconds']).__name__}")
    if not isinstance(ev["output_directory"], str) or not ev["output_directory"]:
        raise ValueError(
            "output_directory must be a non-empty string, "
            f"got {type(ev['output_directory']).__name__}"
        )

    return EvaluationSettings(
        runs_per_model=dict(runs),
        timeout_seconds=ev["timeout_seconds"],
        output_directory=ev["output_directory"],
    )


@dataclass(frozen=True)
class RagSettings:
    """Validated RAG pipeline settings."""

    top_k: int
    similarity_threshold: float
    index_path: str

    def __post_init__(self) -> None:
        if not isinstance(self.top_k, int) or isinstance(self.top_k, bool):
            raise TypeError(f"top_k must be int, got {type(self.top_k).__name__}")
        if self.top_k < 1:
            raise ValueError(f"top_k must be >= 1, got {self.top_k}")
        if not isinstance(self.similarity_threshold, (int, float)):
            raise TypeError(
                f"similarity_threshold must be float, "
                f"got {type(self.similarity_threshold).__name__}"
            )
        if not (0.0 <= self.similarity_threshold <= 1.0):
            raise ValueError(
                f"similarity_threshold must be in [0, 1], got {self.similarity_threshold}"
            )
        if not isinstance(self.index_path, str) or not self.index_path:
            raise ValueError("index_path must be a non-empty string")


def load_rag_settings(path: Path | None = None) -> RagSettings:
    """Load RAG pipeline settings from settings.yaml.

    Returns default values if the ``rag`` section is missing.
    """
    if path is None:
        path = _CONFIG_DIR / "settings.yaml"

    with open(path, encoding="utf-8") as f:
        try:
            raw: Any = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            raise ValueError(f"Failed to parse YAML in {path}: {exc}") from exc

    rag_raw = raw.get("rag", {}) if isinstance(raw, dict) else {}
    rag: dict[str, Any] = rag_raw if isinstance(rag_raw, dict) else {}

    return RagSettings(
        top_k=rag.get("top_k", 10),
        similarity_threshold=rag.get("similarity_threshold", 0.3),
        index_path=rag.get("index_path", "data/rag_index"),
    )


def validate_config_consistency(
    models: list[ModelConfig],
    settings: EvaluationSettings,
) -> None:
    """Check that settings cover all providers referenced in the model list.

    Raises
    ------
    ValueError
        If a provider appears in ``models`` but has no entry in
        ``settings.runs_per_model``.
    """
    model_providers: set[str] = {m.provider for m in models}
    settings_providers: set[str] = set(settings.runs_per_model)
    missing = model_providers - settings_providers
    if missing:
        raise ValueError(
            f"runs_per_model is missing entries for providers "
            f"used in models.yaml: {sorted(missing)}"
        )


def _require_keys(
    mapping: dict[str, Any],
    keys: set[str],
    location: str = "mapping",
) -> None:
    """Raise ``ValueError`` if *mapping* is missing any of *keys*."""
    missing = keys - set(mapping)
    if missing:
        raise ValueError(f"Missing required keys in {location}: {sorted(missing)}")
