"""Tests for src.models.parsing — strip_code_fences and parse_model_output."""

from __future__ import annotations

import json

from src.models.parsing import parse_model_output, strip_code_fences


class TestStripCodeFences:
    """Tests for strip_code_fences extraction logic."""

    def test_json_code_fence(self) -> None:
        text = '```json\n{"key": "value"}\n```'
        assert strip_code_fences(text) == '{"key": "value"}'

    def test_untagged_code_fence(self) -> None:
        text = '```\n{"key": "value"}\n```'
        assert strip_code_fences(text) == '{"key": "value"}'

    def test_json_fence_preferred_over_untagged(self) -> None:
        text = '```thinking\nsome reasoning\n```\n```json\n{"key": "value"}\n```'
        assert strip_code_fences(text) == '{"key": "value"}'

    def test_bare_json_passthrough(self) -> None:
        text = '{"key": "value"}'
        assert strip_code_fences(text) == '{"key": "value"}'

    def test_bare_json_with_whitespace(self) -> None:
        text = '  \n{"key": "value"}\n  '
        assert strip_code_fences(text) == '{"key": "value"}'

    def test_preamble_before_json(self) -> None:
        """Simulates OpenRouter Llama adding text before JSON (GH-127)."""
        text = 'Here is the answer:\n{"order_ids": ["ORD-001"], "reasoning": "test"}'
        result = strip_code_fences(text)
        parsed = json.loads(result)
        assert parsed["order_ids"] == ["ORD-001"]

    def test_preamble_and_postamble(self) -> None:
        text = 'Answer:\n{"key": "value"}\nI hope this helps!'
        result = strip_code_fences(text)
        assert json.loads(result) == {"key": "value"}

    def test_no_json_object_returns_stripped(self) -> None:
        text = "  just plain text  "
        assert strip_code_fences(text) == "just plain text"

    def test_postamble_after_json_rescued(self) -> None:
        """JSON at position 0 with trailing text is rescued via brace extraction."""
        text = '{"key": "value"}\nextra text'
        result = strip_code_fences(text)
        assert json.loads(result) == {"key": "value"}

    def test_single_open_brace_no_close(self) -> None:
        """Input with { but no } returns stripped text unchanged."""
        text = "Here is an incomplete brace { and no close"
        assert strip_code_fences(text) == text.strip()

    def test_empty_braces(self) -> None:
        """Input with {} (brace_end == brace_start + 1) is extracted."""
        text = "prefix {} suffix"
        assert strip_code_fences(text) == "{}"

    def test_trailing_brace_in_postamble_not_extracted(self) -> None:
        """rfind('}') in trailing text doesn't produce wrong extraction bounds."""
        text = 'Preamble: {"order_ids": ["ORD-001"], "reasoning": "ok"} See rule {R-123}'
        result = strip_code_fences(text)
        # The candidate from first { to last } spans across the trailing rule
        # reference and fails json.loads, so stripped text is returned unchanged.
        assert result == text.strip()


class TestParseModelOutput:
    """Tests for parse_model_output with routing schema."""

    def test_valid_routing_json(self) -> None:
        raw = json.dumps(
            {
                "next_state": "IHC_STAINING",
                "applied_rules": ["R-001"],
                "flags": [],
                "reasoning": "test",
            }
        )
        parsed, error = parse_model_output(raw)
        assert error is None
        assert parsed is not None
        assert parsed["next_state"] == "IHC_STAINING"

    def test_malformed_json(self) -> None:
        _, error = parse_model_output("not json at all")
        assert error is not None
        assert "malformed_json" in error

    def test_preamble_json_extraction(self) -> None:
        """Brace extraction rescues JSON with preamble text."""
        inner = {
            "next_state": "ACCEPTED",
            "applied_rules": [],
            "flags": [],
            "reasoning": "test",
        }
        raw = f"Here is the output:\n{json.dumps(inner)}"
        parsed, error = parse_model_output(raw)
        assert error is None
        assert parsed is not None
        assert parsed["next_state"] == "ACCEPTED"
