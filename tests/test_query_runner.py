"""Tests for the query_runner CLI entry point."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.evaluation.query_runner import build_parser, main
from src.models.config import ModelConfig
from src.models.openrouter_adapter import RateLimitInfo
from tests.conftest import make_mock_model, make_mock_rag_settings, make_mock_settings


class TestBuildParser:
    def test_parser_defaults(self) -> None:
        """Parser returns None defaults for optional args."""
        parser = build_parser()
        args = parser.parse_args([])
        assert args.models is None
        assert args.settings is None
        assert args.dry_run is False
        assert args.runs is None

    def test_parser_mode_default(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        assert args.mode == "full_context"

    def test_parser_mode_rag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--mode", "rag"])
        assert args.mode == "rag"

    def test_dry_run_flag(self) -> None:
        """--dry-run sets the flag."""
        parser = build_parser()
        args = parser.parse_args(["--dry-run"])
        assert args.dry_run is True

    def test_model_filter_repeatable(self) -> None:
        """--model can be repeated."""
        parser = build_parser()
        args = parser.parse_args(["--model", "A", "--model", "B"])
        assert args.model_filter == ["A", "B"]


class TestMainValidation:
    def test_negative_runs_rejected(self) -> None:
        """--runs with negative value returns error."""
        with (
            patch("src.evaluation.query_runner.load_models") as lm,
            patch("src.evaluation.query_runner.load_settings") as ls,
            patch("src.evaluation.query_runner.validate_config_consistency"),
        ):
            lm.return_value = []
            ls.return_value = make_mock_settings()
            result = main(["--runs", "-1"])
        assert result == 1

    def test_zero_limit_rejected(self) -> None:
        """--limit 0 returns error."""
        with (
            patch("src.evaluation.query_runner.load_models") as lm,
            patch("src.evaluation.query_runner.load_settings") as ls,
            patch("src.evaluation.query_runner.validate_config_consistency"),
        ):
            lm.return_value = []
            ls.return_value = make_mock_settings()
            result = main(["--limit", "0"])
        assert result == 1

    def test_no_scenarios_returns_error(self) -> None:
        """Empty scenario directory returns error."""
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch("src.evaluation.query_runner.load_models") as lm,
            patch("src.evaluation.query_runner.load_settings") as ls,
            patch("src.evaluation.query_runner.validate_config_consistency"),
        ):
            lm.return_value = [make_mock_model()]
            ls.return_value = make_mock_settings()
            result = main(["--scenarios", tmpdir])
        assert result == 1

    def test_no_matching_model_filter_returns_error(self) -> None:
        """--model with non-existent name returns error."""
        with (
            patch("src.evaluation.query_runner.load_models") as lm,
            patch("src.evaluation.query_runner.load_settings") as ls,
            patch("src.evaluation.query_runner.validate_config_consistency"),
        ):
            lm.return_value = [make_mock_model()]
            ls.return_value = make_mock_settings()
            result = main(["--model", "nonexistent"])
        assert result == 1


class TestMainRagMode:
    def test_rag_mode_missing_index_returns_1(self) -> None:
        """--mode rag with missing index prints error and returns 1."""
        with (
            patch("src.evaluation.query_runner.load_models") as lm,
            patch("src.evaluation.query_runner.load_settings") as ls,
            patch("src.evaluation.query_runner.load_rag_settings") as lrs,
            patch("src.evaluation.query_runner.validate_config_consistency"),
            patch("src.evaluation.query_runner.load_all_query_scenarios", return_value=[]),
            patch("src.evaluation.query_runner.Path.exists", return_value=False),
        ):
            lm.return_value = [make_mock_model()]
            ls.return_value = make_mock_settings()
            lrs.return_value = make_mock_rag_settings()
            result = main(["--mode", "rag"])
        assert result == 1

    def test_rag_mode_dry_run_returns_0(self) -> None:
        """--mode rag --dry-run with existing index returns 0."""
        with (
            patch("src.evaluation.query_runner.load_models") as lm,
            patch("src.evaluation.query_runner.load_settings") as ls,
            patch("src.evaluation.query_runner.load_rag_settings") as lrs,
            patch("src.evaluation.query_runner.validate_config_consistency"),
            patch("src.evaluation.query_runner.load_all_query_scenarios") as lqs,
            patch("src.evaluation.query_runner.Path.exists", return_value=True),
            patch("src.rag.retriever.RagRetriever"),
        ):
            lm.return_value = [make_mock_model()]
            ls.return_value = make_mock_settings()
            lrs.return_value = make_mock_rag_settings()
            lqs.return_value = [MagicMock(tier=1, scenario_id="test")]
            result = main(["--mode", "rag", "--dry-run"])
        assert result == 0

    def test_rag_mode_live_run_invokes_harness(self) -> None:
        """--mode rag without --dry-run wires RagRetriever into the harness."""
        with (
            patch("src.evaluation.query_runner.load_models") as lm,
            patch("src.evaluation.query_runner.load_settings") as ls,
            patch("src.evaluation.query_runner.load_rag_settings") as lrs,
            patch("src.evaluation.query_runner.validate_config_consistency"),
            patch("src.evaluation.query_runner.load_all_query_scenarios") as lqs,
            patch("src.evaluation.query_runner.Path.exists", return_value=True),
            patch("src.rag.retriever.RagRetriever") as mock_retriever_cls,
            patch("src.evaluation.query_runner.QueryEvaluationHarness") as mock_harness_cls,
        ):
            lm.return_value = [make_mock_model()]
            ls.return_value = make_mock_settings()
            lrs.return_value = make_mock_rag_settings()
            lqs.return_value = [MagicMock(tier=1, scenario_id="test")]
            mock_harness_cls.return_value.run_all.return_value = []
            result = main(["--mode", "rag"])
        assert result == 0
        mock_retriever_cls.assert_called_once()
        mock_harness_cls.assert_called_once()
        harness_kwargs = mock_harness_cls.call_args
        assert harness_kwargs.kwargs.get("rag_retriever") is mock_retriever_cls.return_value

    def test_rag_mode_init_failure_returns_1(self) -> None:
        """--mode rag returns 1 when RagRetriever construction fails."""
        with (
            patch("src.evaluation.query_runner.load_models") as lm,
            patch("src.evaluation.query_runner.load_settings") as ls,
            patch("src.evaluation.query_runner.load_rag_settings") as lrs,
            patch("src.evaluation.query_runner.validate_config_consistency"),
            patch("src.evaluation.query_runner.load_all_query_scenarios") as lqs,
            patch("src.evaluation.query_runner.Path.exists", return_value=True),
            patch("src.rag.retriever.RagRetriever", side_effect=RuntimeError("corrupt index")),
        ):
            lm.return_value = [make_mock_model()]
            ls.return_value = make_mock_settings()
            lrs.return_value = make_mock_rag_settings()
            lqs.return_value = [MagicMock(tier=1, scenario_id="test")]
            result = main(["--mode", "rag"])
        assert result == 1


class TestParallelFlag:
    def test_parallel_default_false(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        assert args.parallel is False

    def test_parallel_flag_set(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--parallel"])
        assert args.parallel is True


class TestMaxWorkersFlag:
    def test_max_workers_default_none(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        assert args.max_workers is None

    def test_max_workers_explicit_value(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--max-workers", "6"])
        assert args.max_workers == 6


class TestTierFlag:
    def test_tier_default_none(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        assert args.tier is None

    def test_tier_single_value(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--tier", "1"])
        assert args.tier == ["1"]

    def test_tier_multiple_values(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--tier", "1", "2"])
        assert args.tier == ["1", "2"]


class TestMaxWorkersValidation:
    def test_max_workers_zero_rejected(self) -> None:
        """--max-workers 0 returns error."""
        with (
            patch("src.evaluation.query_runner.load_models") as lm,
            patch("src.evaluation.query_runner.load_settings") as ls,
            patch("src.evaluation.query_runner.validate_config_consistency"),
        ):
            lm.return_value = []
            ls.return_value = make_mock_settings()
            result = main(["--max-workers", "0"])
        assert result == 1

    def test_max_workers_negative_rejected(self) -> None:
        """--max-workers -1 returns error."""
        with (
            patch("src.evaluation.query_runner.load_models") as lm,
            patch("src.evaluation.query_runner.load_settings") as ls,
            patch("src.evaluation.query_runner.validate_config_consistency"),
        ):
            lm.return_value = []
            ls.return_value = make_mock_settings()
            result = main(["--max-workers", "-1"])
        assert result == 1


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
        models = [tier1_model, tier2_model]
        with patch("src.evaluation.query_runner.load_models", return_value=models):
            result = main(["--dry-run", "--tier", "1"])
        assert result == 0
        output = capsys.readouterr().out
        assert "Tier1Model" in output
        assert "Tier2Model" not in output

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
        with patch("src.evaluation.query_runner.load_models", return_value=[tier1_model]):
            result = main(["--dry-run", "--tier", "3"])
        assert result == 1

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
        models = [tier1_model, ceiling_model]
        with patch("src.evaluation.query_runner.load_models", return_value=models):
            result = main(["--dry-run", "--tier", "all"])
        assert result == 0
        output = capsys.readouterr().out
        assert "Tier1Model" in output
        assert "CeilingModel" in output

    def test_combined_model_and_tier(self, capsys: pytest.CaptureFixture[str]) -> None:
        """--model and --tier both select the same model."""
        tier1 = ModelConfig(
            name="T1",
            provider="openrouter",
            model_id="t1",
            temperature=0.0,
            max_tokens=1024,
            token_limit=32768,
            tier="1",
        )
        with patch("src.evaluation.query_runner.load_models", return_value=[tier1]):
            result = main(["--dry-run", "--model", "T1", "--tier", "1"])
        assert result == 0
        output = capsys.readouterr().out
        assert "T1" in output

    def test_combined_model_and_tier_mismatch_returns_1(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--model selects a tier 1 model, --tier 2 excludes it."""
        tier1 = ModelConfig(
            name="Tier1Model",
            provider="openrouter",
            model_id="t1",
            temperature=0.0,
            max_tokens=1024,
            token_limit=32768,
            tier="1",
        )
        with patch("src.evaluation.query_runner.load_models", return_value=[tier1]):
            result = main(["--dry-run", "--model", "Tier1Model", "--tier", "2"])
        assert result == 1
        err = capsys.readouterr().err
        assert "combined filters" in err


class TestMainParallelWiring:
    """parallel and max_workers are passed through to harness.run_all()."""

    def test_parallel_passed_to_harness(self) -> None:
        with (
            patch("src.evaluation.query_runner.load_models") as lm,
            patch("src.evaluation.query_runner.load_settings") as ls,
            patch("src.evaluation.query_runner.validate_config_consistency"),
            patch("src.evaluation.query_runner.load_all_query_scenarios") as lqs,
            patch("src.evaluation.query_runner.QueryEvaluationHarness") as mock_harness_cls,
        ):
            lm.return_value = [make_mock_model()]
            ls.return_value = make_mock_settings()
            lqs.return_value = [MagicMock(tier=1, scenario_id="test")]
            mock_harness_cls.return_value.run_all.return_value = []
            result = main(["--parallel", "--max-workers", "2"])
        assert result == 0
        call_kwargs = mock_harness_cls.return_value.run_all.call_args
        assert call_kwargs.kwargs.get("parallel") is True
        assert call_kwargs.kwargs.get("max_workers") == 2

    def test_sequential_default(self) -> None:
        with (
            patch("src.evaluation.query_runner.load_models") as lm,
            patch("src.evaluation.query_runner.load_settings") as ls,
            patch("src.evaluation.query_runner.validate_config_consistency"),
            patch("src.evaluation.query_runner.load_all_query_scenarios") as lqs,
            patch("src.evaluation.query_runner.QueryEvaluationHarness") as mock_harness_cls,
        ):
            lm.return_value = [make_mock_model()]
            ls.return_value = make_mock_settings()
            lqs.return_value = [MagicMock(tier=1, scenario_id="test")]
            mock_harness_cls.return_value.run_all.return_value = []
            result = main([])
        assert result == 0
        call_kwargs = mock_harness_cls.return_value.run_all.call_args
        assert call_kwargs.kwargs.get("parallel") is False
        assert call_kwargs.kwargs.get("max_workers") is None


# --- Pre-flight rate limit tests (issue #7) ---

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestQueryRunnerPreFlightRateLimit:
    """Test the pre-flight rate limit check block in query_runner.main()."""

    def test_rate_info_printed_on_success(self, capsys: Any) -> None:
        output_path = str(_PROJECT_ROOT / "results" / "query-test-run")
        with (
            patch(
                "src.evaluation.query_runner.load_openrouter_key",
                return_value="sk-test",
            ),
            patch(
                "src.models.openrouter_adapter.check_rate_limit",
                return_value=RateLimitInfo(
                    requests_per_interval=200,
                    interval_seconds=10,
                    label="test-key",
                ),
            ),
            patch("src.evaluation.query_runner.QueryEvaluationHarness") as mock_h,
        ):
            mock_h.return_value.run_all.return_value = []
            result = main(["--output", output_path])

        assert result == 0
        captured = capsys.readouterr()
        assert "200 requests" in captured.out

    def test_rate_warning_when_workers_exceed_rate(self, capsys: Any) -> None:
        """Warning fires when effective_workers > requests_per_second."""
        output_path = str(_PROJECT_ROOT / "results" / "query-test-run")
        with (
            patch(
                "src.evaluation.query_runner.load_openrouter_key",
                return_value="sk-test",
            ),
            patch(
                "src.models.openrouter_adapter.check_rate_limit",
                return_value=RateLimitInfo(
                    requests_per_interval=2,
                    interval_seconds=10,
                    label="test-key",
                ),
            ),
            patch("src.evaluation.query_runner.QueryEvaluationHarness") as mock_h,
        ):
            mock_h.return_value.run_all.return_value = []
            # rate = 2/10s = 0.2 req/s; 5 workers > 0.2 => WARNING
            result = main(
                [
                    "--output",
                    output_path,
                    "--parallel",
                    "--max-workers",
                    "5",
                ]
            )

        assert result == 0
        captured = capsys.readouterr()
        assert "WARNING" in captured.err

    def test_key_load_failure_is_hard_error(self, capsys: Any) -> None:
        """Missing API key should fail fast (return 1)."""
        output_path = str(_PROJECT_ROOT / "results" / "query-test-run")
        with (
            patch(
                "src.evaluation.query_runner.load_openrouter_key",
                side_effect=ValueError("no key found"),
            ),
            patch("src.evaluation.query_runner.QueryEvaluationHarness"),
        ):
            result = main(["--output", output_path])

        assert result == 1
        captured = capsys.readouterr()
        assert "Error" in captured.err
        assert "no key found" in captured.err

    def test_no_warning_when_workers_below_rate(self, capsys: Any) -> None:
        """No WARNING when effective_workers <= requests_per_second."""
        output_path = str(_PROJECT_ROOT / "results" / "query-test-run")
        with (
            patch(
                "src.evaluation.query_runner.load_openrouter_key",
                return_value="sk-test",
            ),
            patch(
                "src.models.openrouter_adapter.check_rate_limit",
                return_value=RateLimitInfo(
                    requests_per_interval=200,
                    interval_seconds=10,
                    label="test-key",
                ),
            ),
            patch("src.evaluation.query_runner.QueryEvaluationHarness") as mock_h,
        ):
            mock_h.return_value.run_all.return_value = []
            # rate = 200/10s = 20 req/s; 2 workers < 20 => no WARNING
            result = main(
                [
                    "--output",
                    output_path,
                    "--parallel",
                    "--max-workers",
                    "2",
                ]
            )

        assert result == 0
        captured = capsys.readouterr()
        assert "WARNING" not in captured.err

    def test_rate_check_skipped_for_local_only(self) -> None:
        """check_rate_limit should not be called with only ollama models."""
        from src.models.config import EvaluationSettings

        output_path = str(_PROJECT_ROOT / "results" / "query-test-run")
        ollama_model = ModelConfig(
            name="local-model",
            provider="llamacpp",
            model_id="test-local",
            temperature=0.0,
            max_tokens=1024,
            token_limit=4096,
        )
        settings = EvaluationSettings(
            runs_per_model={"llamacpp": 1},
            timeout_seconds=30,
            output_directory="results/test",
        )
        with (
            patch(
                "src.evaluation.query_runner.load_models",
                return_value=[ollama_model],
            ),
            patch(
                "src.evaluation.query_runner.load_settings",
                return_value=settings,
            ),
            patch("src.evaluation.query_runner.validate_config_consistency"),
            patch(
                "src.evaluation.query_runner.load_openrouter_key",
            ) as mock_load_key,
            patch("src.evaluation.query_runner.QueryEvaluationHarness") as mock_h,
        ):
            mock_h.return_value.run_all.return_value = []
            result = main(["--output", output_path])

        assert result == 0
        mock_load_key.assert_not_called()

    def test_key_load_os_error_is_hard_error(self, capsys: Any) -> None:
        """OSError from key load should also fail fast (return 1)."""
        output_path = str(_PROJECT_ROOT / "results" / "query-test-run")
        with (
            patch(
                "src.evaluation.query_runner.load_openrouter_key",
                side_effect=OSError("Permission denied"),
            ),
            patch("src.evaluation.query_runner.QueryEvaluationHarness"),
        ):
            result = main(["--output", output_path])

        assert result == 1
        captured = capsys.readouterr()
        assert "Error" in captured.err
        assert "Permission denied" in captured.err


# --- Tier warning for untiered models (issue #16) ---


class TestTierWarningForUntieredModels:
    """--tier with models that have tier=None prints a warning."""

    def test_untiered_models_warning(self, capsys: pytest.CaptureFixture[str]) -> None:
        tiered = ModelConfig(
            name="TieredModel",
            provider="openrouter",
            model_id="tiered",
            temperature=0.0,
            max_tokens=1024,
            token_limit=32768,
            tier="1",
        )
        untiered = ModelConfig(
            name="UntieredModel",
            provider="openrouter",
            model_id="untiered",
            temperature=0.0,
            max_tokens=1024,
            token_limit=32768,
            tier=None,
        )
        models = [tiered, untiered]
        with patch("src.evaluation.query_runner.load_models", return_value=models):
            result = main(["--dry-run", "--tier", "1"])
        assert result == 0
        err = capsys.readouterr().err
        assert "UntieredModel" in err
        assert "no tier" in err


# --- _print_plan parallel output (issue #17) ---


class TestQueryPrintPlanParallelOutput:
    def test_parallel_info_in_dry_run(self, capsys: Any) -> None:
        result = main(["--dry-run", "--parallel", "--max-workers", "2"])
        assert result == 0
        captured = capsys.readouterr()
        assert "Parallel: yes (max workers:" in captured.out

    def test_parallel_absent_without_flag(self, capsys: Any) -> None:
        """Parallel info should NOT appear without --parallel."""
        result = main(["--dry-run"])
        assert result == 0
        captured = capsys.readouterr()
        assert "Parallel:" not in captured.out
