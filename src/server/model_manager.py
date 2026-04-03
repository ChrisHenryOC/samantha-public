"""Model manager for swapping local models on llama-server.

Provides functions to look up local model configs, stop a running
llama-server, start a new one with the selected model, and poll
for readiness.
"""

from __future__ import annotations

import logging
import os
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import yaml

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_CONFIG_DIR = _PROJECT_ROOT / "config"
_PID_FILE = _PROJECT_ROOT / "data" / "llama-server.pid"

# gpu_layers=99 means "offload all layers to GPU"
_DEFAULT_SERVER_PARAMS: dict[str, Any] = {
    "gpu_layers": 99,
    "flash_attn": True,
    "threads": 6,
    "ctx_size": 4096,
}


@dataclass(frozen=True)
class LocalModelEntry:
    """A local model entry from models.yaml with llama-server config."""

    name: str
    model_id: str
    hf_repo: str
    server_params: dict[str, Any]

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("LocalModelEntry.name must be non-empty")
        if not self.hf_repo:
            raise ValueError("LocalModelEntry.hf_repo must be non-empty")


def load_local_models(path: Path | None = None) -> list[LocalModelEntry]:
    """Load local (llamacpp) model entries from models.yaml.

    Only returns entries with ``provider: llamacpp`` and a non-empty
    ``hf_repo`` field.
    """
    config_path = path or (_CONFIG_DIR / "models.yaml")
    with open(config_path, encoding="utf-8") as f:
        try:
            raw: Any = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            raise ValueError(f"Failed to parse YAML in {config_path}: {exc}") from exc

    if not isinstance(raw, dict) or "models" not in raw:
        raise ValueError("models.yaml must contain a top-level 'models' key")

    entries: list[LocalModelEntry] = []
    for item in raw["models"]:
        if not isinstance(item, dict):
            continue
        if item.get("provider") != "llamacpp":
            continue
        hf_repo = item.get("hf_repo", "")
        if not hf_repo:
            continue
        params = dict(_DEFAULT_SERVER_PARAMS)
        if isinstance(item.get("server_params"), dict):
            params.update(item["server_params"])
        entries.append(
            LocalModelEntry(
                name=item.get("name", ""),
                model_id=item.get("model_id", ""),
                hf_repo=hf_repo,
                server_params=params,
            )
        )
    return entries


def find_model(name: str, models: list[LocalModelEntry]) -> LocalModelEntry | None:
    """Find a local model by name (case-insensitive)."""
    name_lower = name.lower()
    for m in models:
        if m.name.lower() == name_lower:
            return m
    return None


def _find_llama_server_binary() -> str:
    """Find the llama-server binary path.

    Checks ``LLAMA_SERVER_PATH`` env var first, then falls back to
    ``shutil.which`` for PATH-based discovery.
    """
    env_path = os.environ.get("LLAMA_SERVER_PATH")
    if env_path and Path(env_path).exists():
        return env_path
    found = shutil.which("llama-server")
    if found:
        return found
    raise FileNotFoundError(
        "llama-server not found. Set LLAMA_SERVER_PATH or add llama-server to PATH."
    )


def _build_server_args(binary: str, model: LocalModelEntry, port: int) -> list[str]:
    """Build the llama-server command-line arguments."""
    params = model.server_params
    args = [
        binary,
        "-hf",
        model.hf_repo,
        "--port",
        str(port),
        "--jinja",
    ]
    if params.get("gpu_layers") is not None:
        args.extend(["--gpu-layers", str(params["gpu_layers"])])
    if params.get("flash_attn"):
        args.extend(["--flash-attn", "on"])
    if params.get("threads") is not None:
        args.extend(["--threads", str(params["threads"])])
    if params.get("ctx_size") is not None:
        args.extend(["--ctx-size", str(params["ctx_size"])])
    return args


def stop_server(pid_file: Path = _PID_FILE, timeout: float = 10.0) -> bool:
    """Stop a running llama-server using the stored PID file.

    Returns True if a server was stopped, False if none was running
    or the stop failed.
    """
    if not pid_file.exists():
        return False

    try:
        pid = int(pid_file.read_text().strip())
    except (ValueError, OSError):
        pid_file.unlink(missing_ok=True)
        return False

    try:
        os.kill(pid, signal.SIGTERM)
        logger.info("Sent SIGTERM to llama-server (PID %d)", pid)
    except ProcessLookupError:
        logger.info("llama-server (PID %d) is not running", pid)
        pid_file.unlink(missing_ok=True)
        return False
    except PermissionError:
        logger.error("No permission to stop llama-server (PID %d)", pid)
        pid_file.unlink(missing_ok=True)
        return False

    # Wait for process to exit
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)  # Check if process exists
        except ProcessLookupError:
            pid_file.unlink(missing_ok=True)
            return True
        time.sleep(0.5)

    # SIGTERM timed out — escalate to SIGKILL
    logger.warning(
        "llama-server (PID %d) did not exit within %.0fs, sending SIGKILL",
        pid,
        timeout,
    )
    try:
        os.kill(pid, signal.SIGKILL)
        time.sleep(1.0)
    except ProcessLookupError:
        pass

    pid_file.unlink(missing_ok=True)
    return True


def start_server(
    model: LocalModelEntry,
    *,
    port: int = 8080,
    pid_file: Path = _PID_FILE,
) -> subprocess.Popen[str]:
    """Start llama-server with the given model.

    The server process runs in the background. Its PID is written to
    the PID file for later cleanup.
    """
    binary = _find_llama_server_binary()
    args = _build_server_args(binary, model, port)
    logger.info("Starting llama-server: %s", " ".join(args))

    pid_file.parent.mkdir(parents=True, exist_ok=True)
    log_file = pid_file.parent / "llama-server.log"
    log_handle = open(log_file, "w")  # noqa: SIM115
    try:
        proc = subprocess.Popen(
            args,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
        )
    except OSError:
        log_handle.close()
        raise
    # Close parent's copy — child process inherits the fd
    log_handle.close()
    pid_file.write_text(str(proc.pid))
    logger.info("llama-server PID %d, log: %s", proc.pid, log_file)
    return proc


def wait_for_ready(
    url: str = "http://localhost:8080",
    *,
    timeout: float = 120.0,
    poll_interval: float = 2.0,
    proc: subprocess.Popen[str] | None = None,
) -> bool:
    """Poll llama-server's health endpoint until it reports ready.

    Returns True if the server became ready, False on timeout.
    If *proc* is provided, returns False immediately if the process exits.
    """
    health_url = f"{url.rstrip('/')}/health"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc is not None and proc.poll() is not None:
            logger.error(
                "llama-server exited with code %d before becoming ready",
                proc.returncode,
            )
            return False
        try:
            resp = httpx.get(health_url, timeout=5)
            if resp.status_code == 200:
                body = resp.json()
                if body.get("status") == "ok":
                    return True
        except (httpx.RequestError, ValueError):
            pass
        time.sleep(poll_interval)
    return False


def switch_model(
    model_name: str,
    *,
    port: int = 8080,
    config_path: Path | None = None,
    pid_file: Path = _PID_FILE,
    timeout: float = 120.0,
) -> bool:
    """Switch the running llama-server to a different model.

    Returns True if the server is ready with the new model, False on failure.
    """
    models = load_local_models(config_path)
    model = find_model(model_name, models)
    if model is None:
        available = [m.name for m in models]
        raise ValueError(f"Model {model_name!r} not found. Available: {available}")

    stopped = stop_server(pid_file)
    if not stopped and pid_file.exists():
        raise RuntimeError("Failed to stop the running llama-server")

    proc = start_server(model, port=port, pid_file=pid_file)

    url = f"http://localhost:{port}"
    if not wait_for_ready(url, timeout=timeout, proc=proc):
        logger.error("llama-server did not become ready within %.0fs", timeout)
        return False

    return True
