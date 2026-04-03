"""Tests for evaluation runner CLI logic."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.evaluation.runner import _PROJECT_ROOT, build_parser, main
from src.models.config import EvaluationSettings, ModelConfig
from tests.conftest import make_mock_model, make_mock_rag_settings, make_mock_settings


class TestBuildParser:
    def test_defaults(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        assert args.models is None
        assert args.settings is None
        assert args.scenarios is None
        assert args.dry_run is False

    def test_parser_mode_default(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        assert args.mode == "full_context"

    def test_parser_mode_rag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--mode", "rag"])
        assert args.mode == "rag"

    def test_model_filter_repeatable(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--model", "a", "--model", "b"])
        assert args.model_filter == ["a", "b"]

    def test_limit_parsed(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--limit", "5"])
        assert args.limit == 5

    def test_limit_default_none(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        assert args.limit is None

    def test_cloud_runs_parsed(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--cloud-runs", "2"])
        assert args.cloud_runs == 2

    def test_local_runs_parsed(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--local-runs", "3"])
        assert args.local_runs == 3

    def test_runs_with_provider_overrides(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--runs", "1", "--cloud-runs", "2", "--local-runs", "5"])
        assert args.runs == 1
        assert args.cloud_runs == 2
        assert args.local_runs == 5

    def test_parallel_default_false(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        assert args.parallel is False

    def test_parallel_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--parallel"])
        assert args.parallel is True

    def test_tier_default_none(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        assert args.tier is None

    def test_tier_single(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--tier", "1"])
        assert args.tier == ["1"]

    def test_tier_multiple(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--tier", "1", "2"])
        assert args.tier == ["1", "2"]

    def test_tier_all(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--tier", "all"])
        assert args.tier == ["all"]


class TestMainConfigErrors:
    def test_missing_config_returns_1(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = main(["--models", str(Path(tmpdir) / "missing.yaml")])
            assert result == 1

    def test_missing_scenarios_dir_returns_1(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_scenarios = Path(tmpdir) / "no_such_dir"
            result = main(["--scenarios", str(fake_scenarios)])
            assert result == 1


class TestMainModelFilter:
    def test_no_matching_model_returns_1(self) -> None:
        result = main(["--model", "nonexistent-model-xyz"])
        assert result == 1


class TestMainDryRun:
    def test_dry_run_returns_0(self) -> None:
        result = main(["--dry-run"])
        assert result == 0

    def test_dry_run_with_limit(self, capsys: object) -> None:
        result = main(["--dry-run", "--limit", "3"])
        assert result == 0

    def test_dry_run_with_prompt_extras(self, capsys: pytest.CaptureFixture[str]) -> None:
        result = main(["--dry-run", "--prompt-extras", "state_sequence,retry_clarification"])
        assert result == 0
        captured = capsys.readouterr()
        assert "Prompt extras:" in captured.out
        assert "retry_clarification" in captured.out
        assert "state_sequence" in captured.out


class TestScenarioIdsFilter:
    """Tests for the --scenario-ids CLI filter."""

    def test_parser_accepts_scenario_ids(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--scenario-ids", "SC-001,SC-005"])
        assert args.scenario_ids == "SC-001,SC-005"

    def test_parser_default_none(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        assert args.scenario_ids is None

    def test_dry_run_with_scenario_ids(self) -> None:
        result = main(["--dry-run", "--scenario-ids", "SC-001,SC-005"])
        assert result == 0

    def test_whitespace_stripped(self) -> None:
        result = main(["--dry-run", "--scenario-ids", "SC-001, SC-005"])
        assert result == 0

    def test_no_match_returns_1(self, capsys: pytest.CaptureFixture[str]) -> None:
        result = main(["--dry-run", "--scenario-ids", "SC-999"])
        assert result == 1
        captured = capsys.readouterr()
        assert "No scenarios match ID filter" in captured.err

    def test_partial_match_warns(self, capsys: pytest.CaptureFixture[str]) -> None:
        result = main(["--dry-run", "--scenario-ids", "SC-001,SC-999"])
        assert result == 0
        captured = capsys.readouterr()
        assert "SC-999" in captured.err


class TestMainValidation:
    def test_limit_zero_returns_1(self) -> None:
        result = main(["--limit", "0"])
        assert result == 1

    def test_limit_negative_returns_1(self) -> None:
        result = main(["--limit", "-1"])
        assert result == 1

    def test_runs_zero_returns_1(self) -> None:
        result = main(["--runs", "0"])
        assert result == 1

    def test_cloud_runs_zero_returns_1(self) -> None:
        result = main(["--cloud-runs", "0"])
        assert result == 1

    def test_local_runs_zero_returns_1(self) -> None:
        result = main(["--local-runs", "0"])
        assert result == 1


class TestMainRagMode:
    def test_rag_mode_missing_index_returns_1(self) -> None:
        """--mode rag with missing index prints error and returns 1."""
        with (
            patch("src.evaluation.runner.load_models") as lm,
            patch("src.evaluation.runner.load_settings") as ls,
            patch("src.evaluation.runner.load_rag_settings") as lrs,
            patch("src.evaluation.runner.validate_config_consistency"),
            patch("src.evaluation.runner.Path.exists", return_value=False),
        ):
            lm.return_value = [make_mock_model()]
            ls.return_value = make_mock_settings()
            lrs.return_value = make_mock_rag_settings()
            result = main(["--mode", "rag"])
        assert result == 1

    def test_rag_mode_dry_run_returns_0(self) -> None:
        """--mode rag --dry-run with existing index returns 0."""
        with (
            patch("src.evaluation.runner.load_models") as lm,
            patch("src.evaluation.runner.load_settings") as ls,
            patch("src.evaluation.runner.load_rag_settings") as lrs,
            patch("src.evaluation.runner.validate_config_consistency"),
            patch("src.evaluation.runner.Path.exists", return_value=True),
            patch("src.rag.retriever.RagRetriever"),
        ):
            lm.return_value = [make_mock_model()]
            ls.return_value = make_mock_settings()
            lrs.return_value = make_mock_rag_settings()
            result = main(["--mode", "rag", "--dry-run"])
        assert result == 0

    def test_rag_mode_live_run_invokes_harness(self) -> None:
        """--mode rag without --dry-run wires RagRetriever into the harness."""
        with (
            patch("src.evaluation.runner.load_models") as lm,
            patch("src.evaluation.runner.load_settings") as ls,
            patch("src.evaluation.runner.load_rag_settings") as lrs,
            patch("src.evaluation.runner.validate_config_consistency"),
            patch("src.evaluation.runner.Path.exists", return_value=True),
            patch("src.rag.retriever.RagRetriever") as mock_retriever_cls,
            patch("src.evaluation.runner.EvaluationHarness") as mock_harness_cls,
        ):
            lm.return_value = [make_mock_model()]
            ls.return_value = make_mock_settings()
            lrs.return_value = make_mock_rag_settings()
            mock_harness_cls.return_value.run_all.return_value = []
            result = main(["--mode", "rag"])
        assert result == 0
        mock_retriever_cls.assert_called_once()
        mock_harness_cls.assert_called_once()
        # Verify rag_retriever was passed to the harness constructor
        harness_kwargs = mock_harness_cls.call_args
        assert harness_kwargs.kwargs.get("rag_retriever") is mock_retriever_cls.return_value

    def test_rag_mode_init_failure_returns_1(self) -> None:
        """--mode rag returns 1 when RagRetriever construction fails."""
        with (
            patch("src.evaluation.runner.load_models") as lm,
            patch("src.evaluation.runner.load_settings") as ls,
            patch("src.evaluation.runner.load_rag_settings") as lrs,
            patch("src.evaluation.runner.validate_config_consistency"),
            patch("src.evaluation.runner.Path.exists", return_value=True),
            patch("src.rag.retriever.RagRetriever", side_effect=RuntimeError("corrupt index")),
        ):
            lm.return_value = [make_mock_model()]
            ls.return_value = make_mock_settings()
            lrs.return_value = make_mock_rag_settings()
            result = main(["--mode", "rag"])
        assert result == 1


class TestOutputPathValidation:
    def test_output_outside_project_root_returns_1(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        outside_path = str(_PROJECT_ROOT.parent / "evil-output")
        result = main(["--output", outside_path, "--dry-run"])
        assert result == 1
        assert "--output must resolve within the project root" in capsys.readouterr().err

    def test_output_traversal_returns_1(self, capsys: pytest.CaptureFixture[str]) -> None:
        outside_path = str(_PROJECT_ROOT.parent / "etc" / "passwd")
        result = main(["--output", outside_path, "--dry-run"])
        assert result == 1
        assert "--output must resolve within the project root" in capsys.readouterr().err

    def test_output_symlink_escape_returns_1(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Symlink inside project pointing outside is caught by .resolve()."""
        symlink = _PROJECT_ROOT / ".test-symlink-escape"
        try:
            symlink.symlink_to(tmp_path)
            result = main(["--output", str(symlink), "--dry-run"])
            assert result == 1
            assert "--output must resolve within the project root" in capsys.readouterr().err
        finally:
            symlink.unlink(missing_ok=True)

    def test_models_outside_project_root_returns_1(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        outside_path = str(_PROJECT_ROOT.parent / "evil-models.yaml")
        result = main(["--models", outside_path, "--dry-run"])
        assert result == 1
        assert "--models must resolve within the project root" in capsys.readouterr().err

    def test_settings_outside_project_root_returns_1(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        outside_path = str(_PROJECT_ROOT.parent / "evil-settings.yaml")
        result = main(["--settings", outside_path, "--dry-run"])
        assert result == 1
        assert "--settings must resolve within the project root" in capsys.readouterr().err

    def test_scenarios_outside_project_root_returns_1(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        outside_path = str(_PROJECT_ROOT.parent / "evil-scenarios")
        result = main(["--scenarios", outside_path, "--dry-run"])
        assert result == 1
        assert "--scenarios must resolve within the project root" in capsys.readouterr().err

    def test_output_within_project_returns_0(self) -> None:
        inside_path = str(_PROJECT_ROOT / "results" / "test-run")
        result = main(["--output", inside_path, "--dry-run"])
        assert result == 0

    def test_mkdir_failure_returns_1(self, capsys: pytest.CaptureFixture[str]) -> None:
        """If output_dir.mkdir() raises OSError, main() returns 1."""
        inside_path = str(_PROJECT_ROOT / "results" / "test-run")
        target = Path(inside_path).resolve()
        _real_mkdir = Path.mkdir

        def _failing_mkdir(self: Path, *args: object, **kwargs: object) -> None:
            if self == target:
                raise OSError("disk full")
            _real_mkdir(self, *args, **kwargs)  # type: ignore[arg-type]

        with (
            patch("src.evaluation.runner.EvaluationHarness"),
            patch.object(Path, "mkdir", _failing_mkdir),
        ):
            result = main(["--output", inside_path])
            assert result == 1
            assert "Cannot create output directory" in capsys.readouterr().err


class TestMainEvaluationFailure:
    def test_run_all_failure_returns_1(self) -> None:
        """If run_all() raises, main() should catch it and return 1."""
        inside_path = str(_PROJECT_ROOT / "results" / "test-run")
        with patch("src.evaluation.runner.EvaluationHarness") as mock_harness_cls:
            mock_harness_cls.return_value.run_all.side_effect = RuntimeError("boom")
            result = main(["--output", inside_path])
            assert result == 1


class TestMainParallelWiring:
    def test_parallel_flag_passed_to_run_all(self) -> None:
        """--parallel is wired through main() to harness.run_all(parallel=True)."""
        inside_path = str(_PROJECT_ROOT / "results" / "test-run")
        with patch("src.evaluation.runner.EvaluationHarness") as mock_harness_cls:
            mock_harness_cls.return_value.run_all.return_value = []
            result = main(["--output", inside_path, "--parallel"])
            assert result == 0
            call_kwargs = mock_harness_cls.return_value.run_all.call_args
            assert call_kwargs.kwargs.get("parallel") is True

    def test_no_parallel_flag_defaults_false(self) -> None:
        """Without --parallel, harness.run_all gets parallel=False."""
        inside_path = str(_PROJECT_ROOT / "results" / "test-run")
        with patch("src.evaluation.runner.EvaluationHarness") as mock_harness_cls:
            mock_harness_cls.return_value.run_all.return_value = []
            result = main(["--output", inside_path])
            assert result == 0
            call_kwargs = mock_harness_cls.return_value.run_all.call_args
            assert call_kwargs.kwargs.get("parallel") is False

    def test_max_workers_passed_to_run_all(self) -> None:
        """--max-workers is forwarded to harness.run_all()."""
        inside_path = str(_PROJECT_ROOT / "results" / "test-run")
        with patch("src.evaluation.runner.EvaluationHarness") as mock_harness_cls:
            mock_harness_cls.return_value.run_all.return_value = []
            result = main(["--output", inside_path, "--parallel", "--max-workers", "3"])
            assert result == 0
            call_kwargs = mock_harness_cls.return_value.run_all.call_args
            assert call_kwargs.kwargs.get("max_workers") == 3


class TestMainDryRunCloudLocalRuns:
    def test_cloud_runs_override_in_dry_run(self, capsys: object) -> None:
        result = main(["--dry-run", "--cloud-runs", "1"])
        assert result == 0

    def test_local_runs_with_ollama_in_config_returns_0(self) -> None:
        """--local-runs succeeds when ollama provider is in settings."""
        result = main(["--dry-run", "--local-runs", "3"])
        assert result == 0

    def test_runs_with_cloud_override(self, capsys: object) -> None:
        result = main(["--dry-run", "--runs", "1", "--cloud-runs", "2"])
        assert result == 0


class TestOverridePrecedence:
    """--cloud-runs and --local-runs take precedence over --runs."""

    def test_cloud_runs_overrides_runs(self, capsys: pytest.CaptureFixture[str]) -> None:
        cloud_model = ModelConfig(
            name="CloudModel",
            provider="openrouter",
            model_id="cloud-test",
            temperature=0.0,
            max_tokens=1024,
            token_limit=32768,
            runs=5,
        )
        local_model = ModelConfig(
            name="LocalModel",
            provider="llamacpp",
            model_id="local-test",
            temperature=0.0,
            max_tokens=1024,
            token_limit=32768,
            runs=5,
        )
        settings = EvaluationSettings(
            runs_per_model={"openrouter": 1, "llamacpp": 5},
            timeout_seconds=120,
            output_directory="results",
        )
        with (
            patch("src.evaluation.runner.load_models", return_value=[cloud_model, local_model]),
            patch("src.evaluation.runner.load_settings", return_value=settings),
        ):
            result = main(["--dry-run", "--runs", "2", "--cloud-runs", "1"])
        assert result == 0
        output = capsys.readouterr().out
        lines = output.splitlines()
        run_lines = [line for line in lines if "Runs: " in line]
        # Cloud model should have Runs: 1, local should have Runs: 2
        run_counts = set()
        for line in run_lines:
            part = line.split("Runs: ")[1].split(",")[0]
            run_counts.add(int(part))
        assert 1 in run_counts, f"Expected cloud model with 1 run, got: {run_counts}"
        assert 2 in run_counts, f"Expected local model with 2 runs, got: {run_counts}"


class TestModelLevelRunsWithCLI:
    """CLI --runs flags clear per-model config.runs so CLI wins."""

    def test_print_plan_shows_model_level_runs(self, capsys: pytest.CaptureFixture[str]) -> None:
        """_print_plan displays per-model runs override, not provider default."""
        model_with_runs = ModelConfig(
            name="RunsModel",
            provider="openrouter",
            model_id="test-model-runs",
            temperature=0.0,
            max_tokens=1024,
            token_limit=32768,
            runs=7,
        )
        with patch("src.evaluation.runner.load_models", return_value=[model_with_runs]):
            result = main(["--dry-run"])
        assert result == 0
        output = capsys.readouterr().out
        run_lines = [line for line in output.splitlines() if "Runs: " in line]
        assert any("Runs: 7" in line for line in run_lines), (
            f"Expected 'Runs: 7' in output, got: {run_lines}"
        )

    def test_cli_runs_overrides_model_level_runs(self, capsys: pytest.CaptureFixture[str]) -> None:
        """--runs 1 clears config.runs so the CLI value wins."""
        model_with_runs = ModelConfig(
            name="RunsModel",
            provider="openrouter",
            model_id="test-model-runs",
            temperature=0.0,
            max_tokens=1024,
            token_limit=32768,
            runs=5,
        )
        with patch("src.evaluation.runner.load_models", return_value=[model_with_runs]):
            result = main(["--dry-run", "--runs", "1"])
        assert result == 0
        output = capsys.readouterr().out
        run_lines = [line for line in output.splitlines() if "Runs: " in line]
        assert all("Runs: 1" in line for line in run_lines), (
            f"Expected all 'Runs: 1' in output, got: {run_lines}"
        )

    def test_cloud_runs_overrides_model_level_runs(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--cloud-runs 1 clears config.runs on openrouter models only."""
        cloud_model = ModelConfig(
            name="CloudModel",
            provider="openrouter",
            model_id="cloud-test",
            temperature=0.0,
            max_tokens=1024,
            token_limit=32768,
            runs=5,
        )
        local_model = ModelConfig(
            name="LocalModel",
            provider="llamacpp",
            model_id="local-test",
            temperature=0.0,
            max_tokens=1024,
            token_limit=32768,
            runs=3,
        )
        settings = EvaluationSettings(
            runs_per_model={"openrouter": 1, "llamacpp": 1},
            timeout_seconds=120,
            output_directory="results",
        )
        with (
            patch("src.evaluation.runner.load_models", return_value=[cloud_model, local_model]),
            patch("src.evaluation.runner.load_settings", return_value=settings),
        ):
            result = main(["--dry-run", "--cloud-runs", "1"])
        assert result == 0
        output = capsys.readouterr().out
        lines = output.splitlines()

        # Cloud model should have Runs: 1 (CLI override), local should have Runs: 3 (preserved)
        cloud_runs_line = next(line for line in lines if "CloudModel" in line)
        cloud_runs_detail = lines[lines.index(cloud_runs_line) + 1]
        assert "Runs: 1" in cloud_runs_detail

        local_runs_line = next(line for line in lines if "LocalModel" in line)
        local_runs_detail = lines[lines.index(local_runs_line) + 1]
        assert "Runs: 3" in local_runs_detail


class TestTierFiltering:
    """--tier filters models by their tier field."""

    def test_tier_filters_models(self, capsys: pytest.CaptureFixture[str]) -> None:
        tier1_model = ModelConfig(
            name="Tier1Model",
            provider="openrouter",
            model_id="tier1-test",
            temperature=0.0,
            max_tokens=1024,
            token_limit=32768,
            tier="1",
        )
        tier2_model = ModelConfig(
            name="Tier2Model",
            provider="openrouter",
            model_id="tier2-test",
            temperature=0.0,
            max_tokens=1024,
            token_limit=32768,
            tier="2",
        )
        with patch("src.evaluation.runner.load_models", return_value=[tier1_model, tier2_model]):
            result = main(["--dry-run", "--tier", "1"])
        assert result == 0
        output = capsys.readouterr().out
        assert "Tier1Model" in output
        assert "Tier2Model" not in output

    def test_tier_all_includes_everything(self, capsys: pytest.CaptureFixture[str]) -> None:
        tier1_model = ModelConfig(
            name="Tier1Model",
            provider="openrouter",
            model_id="tier1-test",
            temperature=0.0,
            max_tokens=1024,
            token_limit=32768,
            tier="1",
        )
        ceiling_model = ModelConfig(
            name="CeilingModel",
            provider="openrouter",
            model_id="ceiling-test",
            temperature=0.0,
            max_tokens=1024,
            token_limit=32768,
            tier="ceiling",
        )
        with patch("src.evaluation.runner.load_models", return_value=[tier1_model, ceiling_model]):
            result = main(["--dry-run", "--tier", "all"])
        assert result == 0
        output = capsys.readouterr().out
        assert "Tier1Model" in output
        assert "CeilingModel" in output

    def test_tier_no_match_returns_1(self) -> None:
        tier1_model = ModelConfig(
            name="Tier1Model",
            provider="openrouter",
            model_id="tier1-test",
            temperature=0.0,
            max_tokens=1024,
            token_limit=32768,
            tier="1",
        )
        with patch("src.evaluation.runner.load_models", return_value=[tier1_model]):
            result = main(["--dry-run", "--tier", "3"])
        assert result == 1

    def test_tier_multiple_values(self, capsys: pytest.CaptureFixture[str]) -> None:
        tier1 = ModelConfig(
            name="T1",
            provider="openrouter",
            model_id="t1",
            temperature=0.0,
            max_tokens=1024,
            token_limit=32768,
            tier="1",
        )
        tier2 = ModelConfig(
            name="T2",
            provider="openrouter",
            model_id="t2",
            temperature=0.0,
            max_tokens=1024,
            token_limit=32768,
            tier="2",
        )
        tier3 = ModelConfig(
            name="T3",
            provider="openrouter",
            model_id="t3",
            temperature=0.0,
            max_tokens=1024,
            token_limit=32768,
            tier="3",
        )
        with patch("src.evaluation.runner.load_models", return_value=[tier1, tier2, tier3]):
            result = main(["--dry-run", "--tier", "1", "2"])
        assert result == 0
        output = capsys.readouterr().out
        assert "T1" in output
        assert "T2" in output
        assert "T3" not in output


class TestTierCeilingFiltering:
    """--tier ceiling filters to ceiling-tier models only."""

    def test_tier_ceiling_only(self, capsys: pytest.CaptureFixture[str]) -> None:
        tier1 = ModelConfig(
            name="T1",
            provider="openrouter",
            model_id="t1",
            temperature=0.0,
            max_tokens=1024,
            token_limit=32768,
            tier="1",
        )
        ceiling = ModelConfig(
            name="Ceiling",
            provider="openrouter",
            model_id="ceiling-test",
            temperature=0.0,
            max_tokens=1024,
            token_limit=32768,
            tier="ceiling",
        )
        with patch("src.evaluation.runner.load_models", return_value=[tier1, ceiling]):
            result = main(["--dry-run", "--tier", "ceiling"])
        assert result == 0
        output = capsys.readouterr().out
        assert "Ceiling" in output
        assert "T1" not in output


class TestTierModelInteraction:
    """--tier and --model filters interact correctly."""

    def test_tier_model_mismatch_returns_1(self, capsys: pytest.CaptureFixture[str]) -> None:
        """--model selects a model in tier 1, --tier 2 excludes it."""
        tier1 = ModelConfig(
            name="Tier1Model",
            provider="openrouter",
            model_id="t1",
            temperature=0.0,
            max_tokens=1024,
            token_limit=32768,
            tier="1",
        )
        with patch("src.evaluation.runner.load_models", return_value=[tier1]):
            result = main(["--dry-run", "--model", "Tier1Model", "--tier", "2"])
        assert result == 1
        err = capsys.readouterr().err
        assert "combined filters" in err

    def test_tier_model_match_returns_0(self, capsys: pytest.CaptureFixture[str]) -> None:
        """--model and --tier both select the same model."""
        tier2 = ModelConfig(
            name="Tier2Model",
            provider="openrouter",
            model_id="t2",
            temperature=0.0,
            max_tokens=1024,
            token_limit=32768,
            tier="2",
        )
        with patch("src.evaluation.runner.load_models", return_value=[tier2]):
            result = main(["--dry-run", "--model", "Tier2Model", "--tier", "2"])
        assert result == 0
        output = capsys.readouterr().out
        assert "Tier2Model" in output


class TestTierNoneExclusion:
    """--tier filter warns and excludes models with tier=None."""

    def test_tier_none_excluded_with_warning(self, capsys: pytest.CaptureFixture[str]) -> None:
        tiered = ModelConfig(
            name="Tiered",
            provider="openrouter",
            model_id="t1",
            temperature=0.0,
            max_tokens=1024,
            token_limit=32768,
            tier="1",
        )
        untiered = ModelConfig(
            name="Untiered",
            provider="openrouter",
            model_id="u1",
            temperature=0.0,
            max_tokens=1024,
            token_limit=32768,
        )
        with patch("src.evaluation.runner.load_models", return_value=[tiered, untiered]):
            result = main(["--dry-run", "--tier", "1"])
        assert result == 0
        captured = capsys.readouterr()
        assert "Tiered" in captured.out
        assert "Untiered" not in captured.out
        assert "Warning" in captured.err
        assert "Untiered" in captured.err


class TestPrintPlanTierLabel:
    """_print_plan displays tier labels for tiered models."""

    def test_tier_label_in_dry_run_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        model = ModelConfig(
            name="TieredModel",
            provider="openrouter",
            model_id="test-model",
            temperature=0.0,
            max_tokens=1024,
            token_limit=32768,
            tier="1",
        )
        with patch("src.evaluation.runner.load_models", return_value=[model]):
            result = main(["--dry-run"])
        assert result == 0
        output = capsys.readouterr().out
        assert "tier=1" in output

    def test_no_tier_label_for_none_tier(self, capsys: pytest.CaptureFixture[str]) -> None:
        model = ModelConfig(
            name="NoTierModel",
            provider="openrouter",
            model_id="test-model",
            temperature=0.0,
            max_tokens=1024,
            token_limit=32768,
        )
        with patch("src.evaluation.runner.load_models", return_value=[model]):
            result = main(["--dry-run"])
        assert result == 0
        output = capsys.readouterr().out
        assert "tier=" not in output


class TestProviderValidation:
    """Provider-specific overrides require matching provider in config."""

    def test_cloud_runs_without_openrouter_returns_1(self) -> None:
        ollama_only = EvaluationSettings(
            runs_per_model={"llamacpp": 5},
            timeout_seconds=120,
            output_directory="results",
        )
        with patch("src.evaluation.runner.load_settings", return_value=ollama_only):
            result = main(["--cloud-runs", "1", "--dry-run"])
        assert result == 1

    def test_local_runs_without_ollama_returns_1(self) -> None:
        openrouter_only = EvaluationSettings(
            runs_per_model={"openrouter": 1},
            timeout_seconds=120,
            output_directory="results",
        )
        with patch("src.evaluation.runner.load_settings", return_value=openrouter_only):
            result = main(["--local-runs", "3", "--dry-run"])
        assert result == 1


class TestPromptExtrasCLI:
    """Tests for --prompt-extras CLI argument parsing and validation."""

    def test_parser_prompt_extras_default_none(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        assert args.prompt_extras is None

    def test_parser_prompt_extras_single(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--prompt-extras", "state_sequence"])
        assert args.prompt_extras == "state_sequence"

    def test_parser_prompt_extras_multiple(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--prompt-extras", "state_sequence,retry_clarification"])
        assert args.prompt_extras == "state_sequence,retry_clarification"

    def test_valid_extras_dry_run_returns_0(self) -> None:
        result = main(["--dry-run", "--prompt-extras", "state_sequence"])
        assert result == 0

    def test_invalid_extras_returns_1(self, capsys: pytest.CaptureFixture[str]) -> None:
        result = main(["--dry-run", "--prompt-extras", "bogus"])
        assert result == 1
        captured = capsys.readouterr()
        assert "Invalid --prompt-extras" in captured.err
        assert "bogus" in captured.err

    def test_mixed_valid_invalid_returns_1(self, capsys: pytest.CaptureFixture[str]) -> None:
        result = main(["--dry-run", "--prompt-extras", "state_sequence,bogus"])
        assert result == 1
        captured = capsys.readouterr()
        assert "Invalid --prompt-extras" in captured.err

    def test_whitespace_stripped(self) -> None:
        result = main(["--dry-run", "--prompt-extras", " state_sequence , retry_clarification "])
        assert result == 0

    def test_empty_string_treated_as_no_extras(self, capsys: pytest.CaptureFixture[str]) -> None:
        result = main(["--dry-run", "--prompt-extras", ""])
        assert result == 0
        captured = capsys.readouterr()
        # Empty string should not show prompt extras line
        assert "Prompt extras:" not in captured.out

    def test_all_three_extras_accepted(self) -> None:
        result = main(
            [
                "--dry-run",
                "--prompt-extras",
                "state_sequence,retry_clarification,few_shot",
            ]
        )
        assert result == 0

    def test_prompt_extras_threaded_to_harness(self) -> None:
        """prompt_extras kwarg is passed to EvaluationHarness constructor."""
        with (
            patch("src.evaluation.runner.load_models") as lm,
            patch("src.evaluation.runner.load_settings") as ls,
            patch("src.evaluation.runner.validate_config_consistency"),
            patch("src.evaluation.runner.EvaluationHarness") as mock_harness_cls,
        ):
            lm.return_value = [make_mock_model()]
            ls.return_value = make_mock_settings()
            mock_harness_cls.return_value.run_all.return_value = []
            result = main(["--prompt-extras", "state_sequence,retry_clarification"])
        assert result == 0
        mock_harness_cls.assert_called_once()
        harness_kwargs = mock_harness_cls.call_args
        assert harness_kwargs.kwargs.get("prompt_extras") == frozenset(
            {"state_sequence", "retry_clarification"}
        )

    def test_no_prompt_extras_threads_empty_frozenset(self) -> None:
        """Without --prompt-extras, an empty frozenset is passed to harness."""
        with (
            patch("src.evaluation.runner.load_models") as lm,
            patch("src.evaluation.runner.load_settings") as ls,
            patch("src.evaluation.runner.validate_config_consistency"),
            patch("src.evaluation.runner.EvaluationHarness") as mock_harness_cls,
        ):
            lm.return_value = [make_mock_model()]
            ls.return_value = make_mock_settings()
            mock_harness_cls.return_value.run_all.return_value = []
            result = main([])
        assert result == 0
        harness_kwargs = mock_harness_cls.call_args
        assert harness_kwargs.kwargs.get("prompt_extras") == frozenset()
