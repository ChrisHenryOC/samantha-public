"""Red-team tests for src/models/parsing.py — adversarial code fences and schema attacks."""

from __future__ import annotations

import json

from src.models.parsing import parse_model_output, strip_code_fences

# ---------------------------------------------------------------------------
# strip_code_fences adversarial inputs
# ---------------------------------------------------------------------------


class TestStripCodeFencesAdversarial:
    """Adversarial inputs for the code-fence stripper."""

    def test_nested_fences(self) -> None:
        # The non-greedy regex matches the first ```json ... ``` pair,
        # capturing the empty content between the outer opening and
        # the inner ```json fence's closing ```.
        text = '```json\n```json\n{"a": 1}\n```\n```'
        result = strip_code_fences(text)
        assert result == ""

    def test_empty_json_fence(self) -> None:
        text = "```json\n\n```"
        result = strip_code_fences(text)
        assert result == ""

    def test_empty_untagged_fence(self) -> None:
        text = "```\n\n```"
        result = strip_code_fences(text)
        assert result == ""

    def test_thinking_vs_json_prefers_json(self) -> None:
        text = '```thinking\nI am thinking...\n```\n```json\n{"next_state": "X"}\n```'
        result = strip_code_fences(text)
        assert '"next_state"' in result
        assert "thinking" not in result

    def test_multiple_json_fences_takes_first(self) -> None:
        text = '```json\n{"first": true}\n```\n```json\n{"second": true}\n```'
        result = strip_code_fences(text)
        parsed = json.loads(result)
        assert parsed.get("first") is True

    def test_untagged_fallback_when_no_json_fence(self) -> None:
        text = '```\n{"key": "val"}\n```'
        result = strip_code_fences(text)
        parsed = json.loads(result)
        assert parsed["key"] == "val"

    def test_brace_extraction_valid_json(self) -> None:
        text = 'Some preamble text\n{"next_state": "ACCEPTED"}\nsome postamble'
        result = strip_code_fences(text)
        parsed = json.loads(result)
        assert parsed["next_state"] == "ACCEPTED"

    def test_brace_extraction_invalid_json_returns_stripped(self) -> None:
        text = "prefix { not valid json } suffix"
        result = strip_code_fences(text)
        assert result == text.strip()

    def test_brace_extraction_with_trailing_braces(self) -> None:
        text = '{"a": 1} and then {extra}'
        result = strip_code_fences(text)
        # rfind("}") matches the last brace, producing invalid JSON,
        # so the function falls back to returning stripped text.
        assert result == text.strip()

    def test_huge_preamble(self) -> None:
        preamble = "x" * 10000
        json_obj = '{"key": "value"}'
        text = f"{preamble}\n```json\n{json_obj}\n```"
        result = strip_code_fences(text)
        assert json.loads(result) == {"key": "value"}

    def test_unicode_content(self) -> None:
        text = '```json\n{"reasoning": "\\u00e9\\u00e8\\u00ea"}\n```'
        result = strip_code_fences(text)
        parsed = json.loads(result)
        assert "reasoning" in parsed

    def test_empty_input(self) -> None:
        assert strip_code_fences("") == ""

    def test_whitespace_only(self) -> None:
        assert strip_code_fences("   \n\t  ") == ""

    def test_no_fences_no_braces(self) -> None:
        text = "just plain text"
        assert strip_code_fences(text) == text.strip()

    def test_only_opening_brace(self) -> None:
        text = "text with { only"
        result = strip_code_fences(text)
        assert result == text.strip()


# ---------------------------------------------------------------------------
# parse_model_output adversarial inputs
# ---------------------------------------------------------------------------


class TestParseModelOutputAdversarial:
    """Adversarial inputs for the full model output parser."""

    _VALID = {
        "next_state": "ACCEPTED",
        "applied_rules": ["ACC-001"],
        "flags": [],
        "reasoning": "test",
    }

    def test_missing_next_state(self) -> None:
        d = {k: v for k, v in self._VALID.items() if k != "next_state"}
        _, err = parse_model_output(json.dumps(d))
        assert err is not None and "missing required keys" in err

    def test_missing_applied_rules(self) -> None:
        d = {k: v for k, v in self._VALID.items() if k != "applied_rules"}
        _, err = parse_model_output(json.dumps(d))
        assert err is not None and "missing required keys" in err

    def test_missing_flags(self) -> None:
        d = {k: v for k, v in self._VALID.items() if k != "flags"}
        _, err = parse_model_output(json.dumps(d))
        assert err is not None and "missing required keys" in err

    def test_missing_reasoning(self) -> None:
        d = {k: v for k, v in self._VALID.items() if k != "reasoning"}
        _, err = parse_model_output(json.dumps(d))
        assert err is not None and "missing required keys" in err

    def test_next_state_as_int(self) -> None:
        d = {**self._VALID, "next_state": 42}
        _, err = parse_model_output(json.dumps(d))
        assert err is not None and "next_state must be a string" in err

    def test_next_state_as_list(self) -> None:
        d = {**self._VALID, "next_state": ["ACCEPTED"]}
        _, err = parse_model_output(json.dumps(d))
        assert err is not None and "next_state must be a string" in err

    def test_next_state_as_null(self) -> None:
        d = {**self._VALID, "next_state": None}
        _, err = parse_model_output(json.dumps(d))
        assert err is not None and "next_state must be a string" in err

    def test_reasoning_as_list(self) -> None:
        d = {**self._VALID, "reasoning": ["step1", "step2"]}
        _, err = parse_model_output(json.dumps(d))
        assert err is not None and "reasoning must be a string" in err

    def test_applied_rules_as_string(self) -> None:
        d = {**self._VALID, "applied_rules": "ACC-001"}
        _, err = parse_model_output(json.dumps(d))
        assert err is not None and "applied_rules must be a list" in err

    def test_applied_rules_as_dict(self) -> None:
        d = {**self._VALID, "applied_rules": {"ACC-001": True}}
        _, err = parse_model_output(json.dumps(d))
        assert err is not None and "applied_rules must be a list" in err

    def test_flags_as_string(self) -> None:
        d = {**self._VALID, "flags": "FISH_SUGGESTED"}
        _, err = parse_model_output(json.dumps(d))
        assert err is not None and "flags must be a list" in err

    def test_non_string_list_elements_in_rules(self) -> None:
        d = {**self._VALID, "applied_rules": [1, 2, 3]}
        _, err = parse_model_output(json.dumps(d))
        assert err is not None and "elements must be strings" in err

    def test_non_string_list_elements_in_flags(self) -> None:
        d = {**self._VALID, "flags": [True, False]}
        _, err = parse_model_output(json.dumps(d))
        assert err is not None and "elements must be strings" in err

    def test_nested_lists_in_rules(self) -> None:
        d = {**self._VALID, "applied_rules": [["ACC-001"]]}
        _, err = parse_model_output(json.dumps(d))
        assert err is not None and "elements must be strings" in err

    def test_array_root(self) -> None:
        _, err = parse_model_output(json.dumps([1, 2, 3]))
        assert err is not None and "expected JSON object" in err

    def test_string_root(self) -> None:
        _, err = parse_model_output(json.dumps("just a string"))
        assert err is not None and "expected JSON object" in err

    def test_null_root(self) -> None:
        _, err = parse_model_output(json.dumps(None))
        assert err is not None and "expected JSON object" in err

    def test_extra_keys_accepted(self) -> None:
        d = {**self._VALID, "confidence": 0.95, "extra_field": "ok"}
        parsed, err = parse_model_output(json.dumps(d))
        assert err is None
        assert parsed is not None
        assert parsed["confidence"] == 0.95

    def test_malformed_json(self) -> None:
        _, err = parse_model_output("{not valid json")
        assert err is not None and "malformed_json" in err
