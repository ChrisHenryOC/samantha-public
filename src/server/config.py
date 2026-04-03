"""Server configuration for the live routing system."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_CONFIG_PATH = _PROJECT_ROOT / "config" / "server.yaml"


@dataclass(frozen=True)
class ServerConfig:
    """Configuration for the live server."""

    model_id: str
    provider: str
    llamacpp_url: str
    db_path: str
    host: str
    port: int
    prompt_extras: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not self.model_id:
            raise ValueError("model_id must be non-empty")
        if self.provider not in ("llamacpp", "openrouter"):
            raise ValueError(f"provider must be 'llamacpp' or 'openrouter', got '{self.provider}'")
        if not self.db_path:
            raise ValueError("db_path must be non-empty")
        from src.prediction.prompt_template import VALID_PROMPT_EXTRAS

        invalid = self.prompt_extras - VALID_PROMPT_EXTRAS
        if invalid:
            raise ValueError(f"Invalid prompt_extras: {invalid}. Valid: {VALID_PROMPT_EXTRAS}")


def load_server_config(path: Path | None = None) -> ServerConfig:
    """Load server configuration from YAML.

    Falls back to ``config/server.yaml`` if no path is provided.
    """
    config_path = path or _DEFAULT_CONFIG_PATH
    with open(config_path) as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Server config must be a YAML mapping, got {type(data).__name__}")
    raw_extras = data.get("prompt_extras", "")
    if isinstance(raw_extras, str):
        extras = frozenset(x.strip() for x in raw_extras.split(",") if x.strip())
    elif isinstance(raw_extras, list):
        extras = frozenset(str(x) for x in raw_extras)
    else:
        extras = frozenset()

    return ServerConfig(
        model_id=data["model_id"],
        provider=data.get("provider", "llamacpp"),
        llamacpp_url=data.get("llamacpp_url", "http://localhost:8080"),
        db_path=data["db_path"],
        host=data.get("host", "0.0.0.0"),
        port=data.get("port", 8000),
        prompt_extras=extras,
    )
