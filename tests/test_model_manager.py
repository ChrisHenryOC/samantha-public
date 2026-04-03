"""Tests for the model manager (llama-server swap CLI)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.server.model_manager import (
    LocalModelEntry,
    _build_server_args,
    find_model,
    load_local_models,
    start_server,
    stop_server,
    switch_model,
    wait_for_ready,
)

# --- Fixtures ---


def _write_models_yaml(tmp_path: Path, models: list[dict[str, Any]]) -> Path:
    """Write a models.yaml file and return its path."""
    import yaml

    config_file = tmp_path / "models.yaml"
    config_file.write_text(yaml.dump({"models": models}))
    return config_file


def _local_model_entry(
    name: str = "Test Model",
    model_id: str = "test-model",
    hf_repo: str = "bartowski/Test-GGUF:Q4_K_M",
    **params: Any,
) -> dict[str, Any]:
    """Build a local model YAML entry."""
    entry: dict[str, Any] = {
        "name": name,
        "provider": "llamacpp",
        "model_id": model_id,
        "hf_repo": hf_repo,
        "parameters": {"temperature": 0.0, "max_tokens": 1024},
        "token_limit": 131072,
    }
    if params:
        entry["server_params"] = params
    return entry


# --- LocalModelEntry ---


class TestLocalModelEntry:
    def test_valid_entry(self) -> None:
        entry = LocalModelEntry(
            name="Test",
            model_id="test",
            hf_repo="repo/model:Q4",
            server_params={"gpu_layers": 99},
        )
        assert entry.name == "Test"
        assert entry.hf_repo == "repo/model:Q4"

    def test_empty_name_raises(self) -> None:
        with pytest.raises(ValueError, match="name"):
            LocalModelEntry(name="", model_id="test", hf_repo="repo", server_params={})

    def test_empty_hf_repo_raises(self) -> None:
        with pytest.raises(ValueError, match="hf_repo"):
            LocalModelEntry(name="Test", model_id="test", hf_repo="", server_params={})


# --- load_local_models ---


class TestLoadLocalModels:
    def test_loads_llamacpp_entries(self, tmp_path: Path) -> None:
        config = _write_models_yaml(
            tmp_path,
            [
                _local_model_entry("Model A", hf_repo="repo/a:Q4"),
                _local_model_entry("Model B", hf_repo="repo/b:Q4"),
            ],
        )
        models = load_local_models(config)
        assert len(models) == 2
        assert models[0].name == "Model A"
        assert models[1].name == "Model B"

    def test_skips_openrouter_entries(self, tmp_path: Path) -> None:
        config = _write_models_yaml(
            tmp_path,
            [
                _local_model_entry("Local"),
                {
                    "name": "Cloud Model",
                    "provider": "openrouter",
                    "model_id": "cloud/model",
                    "parameters": {"temperature": 0.0, "max_tokens": 1024},
                    "token_limit": 131072,
                },
            ],
        )
        models = load_local_models(config)
        assert len(models) == 1
        assert models[0].name == "Local"

    def test_skips_entries_without_hf_repo(self, tmp_path: Path) -> None:
        entry = _local_model_entry("No Repo")
        del entry["hf_repo"]
        config = _write_models_yaml(tmp_path, [entry])
        models = load_local_models(config)
        assert len(models) == 0

    def test_applies_default_server_params(self, tmp_path: Path) -> None:
        entry = _local_model_entry("Defaults")
        # No server_params key
        config = _write_models_yaml(tmp_path, [entry])
        models = load_local_models(config)
        assert models[0].server_params["gpu_layers"] == 99
        assert models[0].server_params["threads"] == 6

    def test_custom_server_params_override_defaults(self, tmp_path: Path) -> None:
        entry = _local_model_entry("Custom", threads=10, ctx_size=8192)
        config = _write_models_yaml(tmp_path, [entry])
        models = load_local_models(config)
        assert models[0].server_params["threads"] == 10
        assert models[0].server_params["ctx_size"] == 8192
        # Defaults still apply for unspecified params
        assert models[0].server_params["gpu_layers"] == 99

    def test_invalid_yaml_raises(self, tmp_path: Path) -> None:
        config = tmp_path / "models.yaml"
        config.write_text("not_models: []")
        with pytest.raises(ValueError, match="models"):
            load_local_models(config)


# --- find_model ---


class TestFindModel:
    def test_finds_by_exact_name(self) -> None:
        models = [
            LocalModelEntry("Model A", "a", "repo/a", {}),
            LocalModelEntry("Model B", "b", "repo/b", {}),
        ]
        result = find_model("Model A", models)
        assert result is not None
        assert result.name == "Model A"

    def test_case_insensitive(self) -> None:
        models = [LocalModelEntry("Qwen3 8B Local", "qwen", "repo/q", {})]
        result = find_model("qwen3 8b local", models)
        assert result is not None

    def test_not_found_returns_none(self) -> None:
        models = [LocalModelEntry("Model A", "a", "repo/a", {})]
        assert find_model("Nonexistent", models) is None


# --- _build_server_args ---


class TestBuildServerArgs:
    def test_basic_args(self) -> None:
        model = LocalModelEntry(
            name="Test",
            model_id="test",
            hf_repo="bartowski/Test-GGUF:Q4_K_M",
            server_params={
                "gpu_layers": 99,
                "flash_attn": True,
                "threads": 6,
                "ctx_size": 4096,
            },
        )
        args = _build_server_args("/usr/bin/llama-server", model, 8080)
        assert args[0] == "/usr/bin/llama-server"
        assert "-hf" in args
        assert args[args.index("-hf") + 1] == "bartowski/Test-GGUF:Q4_K_M"
        assert "--port" in args
        assert args[args.index("--port") + 1] == "8080"
        assert "--jinja" in args
        assert "--gpu-layers" in args
        assert "--flash-attn" in args
        assert "--threads" in args
        assert "--ctx-size" in args

    def test_no_flash_attn(self) -> None:
        model = LocalModelEntry("T", "t", "repo", {"flash_attn": False})
        args = _build_server_args("/bin/ls", model, 8080)
        assert "--flash-attn" not in args

    def test_empty_server_params(self) -> None:
        model = LocalModelEntry("T", "t", "repo", {})
        args = _build_server_args("/bin/ls", model, 8080)
        assert "--gpu-layers" not in args
        assert "--flash-attn" not in args
        assert "--threads" not in args
        assert "--ctx-size" not in args
        assert "--jinja" in args


# --- stop_server ---


class TestStopServer:
    def test_no_pid_file(self, tmp_path: Path) -> None:
        pid_file = tmp_path / "nonexistent.pid"
        assert stop_server(pid_file) is False

    def test_stale_pid_file(self, tmp_path: Path) -> None:
        pid_file = tmp_path / "server.pid"
        pid_file.write_text("999999999")  # Non-existent PID
        assert stop_server(pid_file) is False
        assert not pid_file.exists()

    def test_invalid_pid_file(self, tmp_path: Path) -> None:
        pid_file = tmp_path / "server.pid"
        pid_file.write_text("not-a-number")
        assert stop_server(pid_file) is False
        assert not pid_file.exists()

    def test_stops_running_process(self, tmp_path: Path) -> None:
        pid_file = tmp_path / "server.pid"
        pid_file.write_text("12345")
        with patch("os.kill") as mock_kill:
            # First call: SIGTERM. Second call: check if alive raises ProcessLookupError
            mock_kill.side_effect = [None, ProcessLookupError]
            result = stop_server(pid_file, timeout=1.0)

        assert result is True
        assert not pid_file.exists()

    def test_permission_error_cleans_pid_file(self, tmp_path: Path) -> None:
        pid_file = tmp_path / "server.pid"
        pid_file.write_text("12345")
        with patch("os.kill", side_effect=PermissionError("not allowed")):
            result = stop_server(pid_file, timeout=1.0)

        assert result is False
        assert not pid_file.exists()

    def test_sigterm_timeout_escalates_to_sigkill(self, tmp_path: Path) -> None:
        pid_file = tmp_path / "server.pid"
        pid_file.write_text("12345")
        import signal

        calls: list[tuple[int, int]] = []

        def fake_kill(pid: int, sig: int) -> None:
            calls.append((pid, sig))
            if sig == signal.SIGKILL:
                return
            # Process alive for SIGTERM and poll checks
            return

        with patch("os.kill", side_effect=fake_kill):
            result = stop_server(pid_file, timeout=0.1)

        assert result is True
        assert not pid_file.exists()
        # Should have SIGTERM, some poll checks, then SIGKILL
        sigs = [s for _, s in calls]
        assert signal.SIGTERM in sigs
        assert signal.SIGKILL in sigs


# --- start_server ---


class TestStartServer:
    def test_starts_process_and_writes_pid(self, tmp_path: Path) -> None:
        pid_file = tmp_path / "server.pid"
        model = LocalModelEntry("Test", "test", "repo/test:Q4", {"gpu_layers": 99})
        mock_proc = MagicMock()
        mock_proc.pid = 42

        with (
            patch("src.server.model_manager._find_llama_server_binary", return_value="/bin/ls"),
            patch("subprocess.Popen", return_value=mock_proc) as mock_popen,
        ):
            proc = start_server(model, port=9090, pid_file=pid_file)

        assert proc.pid == 42
        assert pid_file.read_text() == "42"
        # Verify the command includes the right flags
        call_args = mock_popen.call_args[0][0]
        assert "-hf" in call_args
        assert "repo/test:Q4" in call_args
        assert "--port" in call_args
        assert "9090" in call_args


# --- wait_for_ready ---


class TestWaitForReady:
    def test_ready_immediately(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "ok"}

        with patch("httpx.get", return_value=mock_resp):
            assert wait_for_ready(timeout=5.0) is True

    def test_ready_after_loading(self) -> None:
        loading_resp = MagicMock()
        loading_resp.status_code = 200
        loading_resp.json.return_value = {"status": "loading"}

        ready_resp = MagicMock()
        ready_resp.status_code = 200
        ready_resp.json.return_value = {"status": "ok"}

        with patch("httpx.get", side_effect=[loading_resp, ready_resp]):
            assert wait_for_ready(timeout=10.0, poll_interval=0.1) is True

    def test_timeout(self) -> None:
        with patch("httpx.get", side_effect=httpx.ConnectError("refused")):
            assert wait_for_ready(timeout=0.5, poll_interval=0.1) is False

    def test_connection_error_retries(self) -> None:
        ready_resp = MagicMock()
        ready_resp.status_code = 200
        ready_resp.json.return_value = {"status": "ok"}

        with patch(
            "httpx.get",
            side_effect=[
                httpx.ConnectError("refused"),
                httpx.ConnectError("refused"),
                ready_resp,
            ],
        ):
            assert wait_for_ready(timeout=10.0, poll_interval=0.1) is True

    def test_dead_process_returns_false_immediately(self) -> None:
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1  # Process exited with code 1
        mock_proc.returncode = 1
        assert wait_for_ready(timeout=10.0, poll_interval=0.1, proc=mock_proc) is False


# --- switch_model ---


class TestSwitchModel:
    def test_unknown_model_raises(self, tmp_path: Path) -> None:
        config = _write_models_yaml(tmp_path, [_local_model_entry("Real Model")])
        with pytest.raises(ValueError, match="not found"):
            switch_model("Nonexistent", config_path=config, pid_file=tmp_path / "pid")

    def test_successful_switch(self, tmp_path: Path) -> None:
        config = _write_models_yaml(tmp_path, [_local_model_entry("Test Model")])
        pid_file = tmp_path / "server.pid"

        mock_proc = MagicMock()
        mock_proc.pid = 99

        with (
            patch("src.server.model_manager.stop_server", return_value=False),
            patch("src.server.model_manager._find_llama_server_binary", return_value="/bin/ls"),
            patch("subprocess.Popen", return_value=mock_proc),
            patch("src.server.model_manager.wait_for_ready", return_value=True),
        ):
            result = switch_model(
                "Test Model",
                config_path=config,
                pid_file=pid_file,
            )

        assert result is True

    def test_server_not_ready(self, tmp_path: Path) -> None:
        config = _write_models_yaml(tmp_path, [_local_model_entry("Test Model")])
        pid_file = tmp_path / "server.pid"

        mock_proc = MagicMock()
        mock_proc.pid = 99

        with (
            patch("src.server.model_manager.stop_server", return_value=False),
            patch("src.server.model_manager._find_llama_server_binary", return_value="/bin/ls"),
            patch("subprocess.Popen", return_value=mock_proc),
            patch("src.server.model_manager.wait_for_ready", return_value=False),
        ):
            result = switch_model(
                "Test Model",
                config_path=config,
                pid_file=pid_file,
            )

        assert result is False


# --- CLI ---


class TestSwitchModelCLI:
    def test_list_models(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        from src.server.switch_model import main

        config = _write_models_yaml(
            tmp_path,
            [
                _local_model_entry("Model A", hf_repo="repo/a:Q4"),
                _local_model_entry("Model B", hf_repo="repo/b:Q4"),
            ],
        )

        with patch("src.server.switch_model.load_local_models") as mock_load:
            mock_load.return_value = load_local_models(config)
            exit_code = main(["--list"])

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Model A" in captured.out
        assert "Model B" in captured.out

    def test_no_args_shows_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        from src.server.switch_model import main

        exit_code = main([])
        assert exit_code == 1

    def test_stop_command(self) -> None:
        from src.server.switch_model import main

        with patch("src.server.switch_model.stop_server", return_value=True):
            exit_code = main(["--stop"])
        assert exit_code == 0

    def test_stop_command_none_running(self, capsys: pytest.CaptureFixture[str]) -> None:
        from src.server.switch_model import main

        with patch("src.server.switch_model.stop_server", return_value=False):
            exit_code = main(["--stop"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "No llama-server" in captured.out

    def test_os_error_returns_1(self, capsys: pytest.CaptureFixture[str]) -> None:
        from src.server.switch_model import main

        with patch("src.server.switch_model.switch_model", side_effect=OSError("exec failed")):
            exit_code = main(["SomeModel"])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "exec failed" in captured.err

    def test_runtime_error_returns_1(self, capsys: pytest.CaptureFixture[str]) -> None:
        from src.server.switch_model import main

        with patch(
            "src.server.switch_model.switch_model",
            side_effect=RuntimeError("Failed to stop"),
        ):
            exit_code = main(["SomeModel"])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "Failed to stop" in captured.err


# --- _find_llama_server_binary ---


class TestFindLlamaServerBinary:
    def test_env_var_takes_precedence(self, tmp_path: Path) -> None:
        from src.server.model_manager import _find_llama_server_binary

        fake_binary = tmp_path / "llama-server"
        fake_binary.touch()
        with patch.dict("os.environ", {"LLAMA_SERVER_PATH": str(fake_binary)}):
            result = _find_llama_server_binary()
        assert result == str(fake_binary)

    def test_falls_back_to_which(self) -> None:
        from src.server.model_manager import _find_llama_server_binary

        with (
            patch.dict("os.environ", {}, clear=True),
            patch("shutil.which", return_value="/usr/bin/llama-server"),
        ):
            result = _find_llama_server_binary()
        assert result == "/usr/bin/llama-server"

    def test_not_found_raises(self) -> None:
        from src.server.model_manager import _find_llama_server_binary

        with (
            patch.dict("os.environ", {}, clear=True),
            patch("shutil.which", return_value=None),
            pytest.raises(FileNotFoundError, match="LLAMA_SERVER_PATH"),
        ):
            _find_llama_server_binary()
