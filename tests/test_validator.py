"""Tests for the prediction validator."""

from __future__ import annotations

import re
from datetime import datetime

import pytest

from src.prediction.prompt_template import render_prompt
from src.workflow.models import Event, Order, Slide
from src.workflow.state_machine import StateMachine
from src.workflow.validator import (
    FailureType,
    ValidationResult,
    classify_failure,
    validate_flags,
    validate_prediction,
    validate_rules,
    validate_state,
)

ALL_STATES: frozenset[str] = frozenset(
    ["ACCESSIONING", "ACCEPTED", "IHC_STAINING", "ORDER_COMPLETE"]
)
ALL_RULE_IDS: frozenset[str] = frozenset(["ACC-001", "ACC-008", "IHC-001"])
ALL_FLAG_IDS: frozenset[str] = frozenset(["FISH_SUGGESTED", "FIXATION_WARNING"])


# --- validate_state ---


class TestValidateState:
    def test_exact_match(self) -> None:
        assert validate_state("ACCEPTED", "ACCEPTED") is True

    def test_mismatch(self) -> None:
        assert validate_state("ACCEPTED", "IHC_STAINING") is False

    def test_non_string_predicted_returns_false(self) -> None:
        assert validate_state(42, "ACCEPTED") is False  # type: ignore[arg-type]

    def test_non_string_expected_returns_false(self) -> None:
        assert validate_state("ACCEPTED", None) is False  # type: ignore[arg-type]


# --- validate_rules ---


class TestValidateRules:
    def test_same_rules_same_order(self) -> None:
        assert validate_rules(["ACC-001", "ACC-002"], ["ACC-001", "ACC-002"]) is True

    def test_same_rules_different_order(self) -> None:
        assert validate_rules(["ACC-002", "ACC-001"], ["ACC-001", "ACC-002"]) is True

    def test_missing_rule(self) -> None:
        assert validate_rules(["ACC-001"], ["ACC-001", "ACC-002"]) is False

    def test_extra_rule(self) -> None:
        assert validate_rules(["ACC-001", "ACC-002"], ["ACC-001"]) is False

    def test_both_empty(self) -> None:
        assert validate_rules([], []) is True

    def test_duplicate_predicted_not_matching_single(self) -> None:
        assert validate_rules(["ACC-001", "ACC-001"], ["ACC-001"]) is False

    def test_duplicate_both_sides_match(self) -> None:
        assert validate_rules(["ACC-001", "ACC-001"], ["ACC-001", "ACC-001"]) is True

    def test_string_predicted_returns_false(self) -> None:
        assert validate_rules("ACC-001", ["ACC-001"]) is False  # type: ignore[arg-type]

    def test_none_predicted_returns_false(self) -> None:
        assert validate_rules(None, ["ACC-001"]) is False  # type: ignore[arg-type]


# --- validate_flags ---


class TestValidateFlags:
    def test_both_empty(self) -> None:
        assert validate_flags([], []) is True

    def test_same_flags(self) -> None:
        assert validate_flags(["FISH_SUGGESTED"], ["FISH_SUGGESTED"]) is True

    def test_missing_flag(self) -> None:
        assert validate_flags([], ["FISH_SUGGESTED"]) is False

    def test_extra_flag(self) -> None:
        assert validate_flags(["FISH_SUGGESTED"], []) is False

    def test_duplicate_predicted_not_matching_single(self) -> None:
        assert validate_flags(["FISH_SUGGESTED", "FISH_SUGGESTED"], ["FISH_SUGGESTED"]) is False

    def test_string_predicted_returns_false(self) -> None:
        assert validate_flags("FISH_SUGGESTED", ["FISH_SUGGESTED"]) is False  # type: ignore[arg-type]

    def test_none_predicted_returns_false(self) -> None:
        assert validate_flags(None, ["FISH_SUGGESTED"]) is False  # type: ignore[arg-type]


# --- validate_prediction ---


class TestValidatePrediction:
    def test_all_correct(self) -> None:
        prediction = {"next_state": "ACCEPTED", "applied_rules": ["ACC-008"], "flags": []}
        expected = {"next_state": "ACCEPTED", "applied_rules": ["ACC-008"], "flags": []}
        result = validate_prediction(prediction, expected)
        assert result.all_correct is True

    def test_partial_correct(self) -> None:
        prediction = {"next_state": "ACCEPTED", "applied_rules": ["ACC-001"], "flags": []}
        expected = {"next_state": "ACCEPTED", "applied_rules": ["ACC-008"], "flags": []}
        result = validate_prediction(prediction, expected)
        assert result.state_correct is True
        assert result.rules_correct is False
        assert result.flags_correct is True
        assert result.all_correct is False

    def test_all_wrong(self) -> None:
        prediction = {
            "next_state": "IHC_STAINING",
            "applied_rules": ["ACC-001"],
            "flags": ["FISH_SUGGESTED"],
        }
        expected = {"next_state": "ACCEPTED", "applied_rules": ["ACC-008"], "flags": []}
        result = validate_prediction(prediction, expected)
        assert result.state_correct is False
        assert result.rules_correct is False
        assert result.flags_correct is False
        assert result.all_correct is False

    def test_validation_result_frozen(self) -> None:
        result = ValidationResult(state_correct=True, rules_correct=True, flags_correct=True)
        assert result.all_correct is True

    def test_missing_prediction_key_raises(self) -> None:
        prediction = {"next_state": "ACCEPTED"}
        expected = {"next_state": "ACCEPTED", "applied_rules": ["ACC-008"], "flags": []}
        with pytest.raises(ValueError, match="prediction missing required keys"):
            validate_prediction(prediction, expected)

    def test_missing_expected_key_raises(self) -> None:
        prediction = {"next_state": "ACCEPTED", "applied_rules": ["ACC-008"], "flags": []}
        expected = {"next_state": "ACCEPTED"}
        with pytest.raises(ValueError, match="expected missing required keys"):
            validate_prediction(prediction, expected)

    def test_non_string_next_state_returns_incorrect(self) -> None:
        """Integer next_state: type guard in validate_state returns False."""
        pred = {"next_state": 42, "applied_rules": ["ACC-008"], "flags": []}
        exp = {"next_state": "ACCEPTED", "applied_rules": ["ACC-008"], "flags": []}
        result = validate_prediction(pred, exp)
        assert result.state_correct is False

    def test_string_applied_rules_returns_incorrect(self) -> None:
        """String applied_rules: type guard in validate_rules returns False."""
        pred = {"next_state": "ACCEPTED", "applied_rules": "ACC-008", "flags": []}
        exp = {"next_state": "ACCEPTED", "applied_rules": ["ACC-008"], "flags": []}
        result = validate_prediction(pred, exp)
        assert result.rules_correct is False

    def test_string_flags_returns_incorrect(self) -> None:
        """String flags: type guard in validate_flags returns False."""
        pred = {"next_state": "ACCEPTED", "applied_rules": ["ACC-008"], "flags": "FISH_SUGGESTED"}
        exp = {"next_state": "ACCEPTED", "applied_rules": ["ACC-008"], "flags": ["FISH_SUGGESTED"]}
        result = validate_prediction(pred, exp)
        assert result.flags_correct is False


# --- classify_failure ---


class TestClassifyFailure:
    def _expected(self) -> dict[str, object]:
        return {"next_state": "ACCEPTED", "applied_rules": ["ACC-008"], "flags": []}

    def test_correct_returns_none(self) -> None:
        prediction = {"next_state": "ACCEPTED", "applied_rules": ["ACC-008"], "flags": []}
        assert classify_failure(prediction, self._expected(), ALL_STATES) is None

    def test_timeout(self) -> None:
        prediction = {"next_state": "ACCEPTED", "applied_rules": ["ACC-008"], "flags": []}
        result = classify_failure(prediction, self._expected(), ALL_STATES, timed_out=True)
        assert result == FailureType.TIMEOUT

    def test_none_prediction(self) -> None:
        result = classify_failure(None, self._expected(), ALL_STATES)
        assert result == FailureType.INVALID_JSON

    def test_empty_prediction(self) -> None:
        result = classify_failure({}, self._expected(), ALL_STATES)
        assert result == FailureType.EMPTY_RESPONSE

    def test_wrong_field_names(self) -> None:
        prediction = {"state": "ACCEPTED", "rules": ["ACC-008"]}
        result = classify_failure(prediction, self._expected(), ALL_STATES)
        assert result == FailureType.WRONG_FIELD_NAMES

    def test_hallucinated_state(self) -> None:
        prediction = {"next_state": "FANTASY_STATE", "applied_rules": ["ACC-008"], "flags": []}
        result = classify_failure(prediction, self._expected(), ALL_STATES)
        assert result == FailureType.HALLUCINATED_STATE

    def test_hallucinated_rule(self) -> None:
        prediction = {
            "next_state": "ACCEPTED",
            "applied_rules": ["FANTASY-001"],
            "flags": [],
        }
        result = classify_failure(
            prediction, self._expected(), ALL_STATES, all_rule_ids=ALL_RULE_IDS
        )
        assert result == FailureType.HALLUCINATED_RULE

    def test_hallucinated_flag(self) -> None:
        prediction = {
            "next_state": "ACCEPTED",
            "applied_rules": ["ACC-008"],
            "flags": ["MADE_UP_FLAG"],
        }
        result = classify_failure(
            prediction, self._expected(), ALL_STATES, all_flag_ids=ALL_FLAG_IDS
        )
        assert result == FailureType.HALLUCINATED_FLAG

    def test_wrong_state(self) -> None:
        prediction = {"next_state": "IHC_STAINING", "applied_rules": ["ACC-008"], "flags": []}
        result = classify_failure(prediction, self._expected(), ALL_STATES)
        assert result == FailureType.WRONG_STATE

    def test_wrong_rules(self) -> None:
        prediction = {"next_state": "ACCEPTED", "applied_rules": ["ACC-001"], "flags": []}
        result = classify_failure(prediction, self._expected(), ALL_STATES)
        assert result == FailureType.WRONG_RULES

    def test_wrong_flags(self) -> None:
        prediction = {
            "next_state": "ACCEPTED",
            "applied_rules": ["ACC-008"],
            "flags": ["FISH_SUGGESTED"],
        }
        result = classify_failure(prediction, self._expected(), ALL_STATES)
        assert result == FailureType.WRONG_FLAGS

    def test_priority_timeout_over_invalid_json(self) -> None:
        """Timeout takes priority even if prediction is None."""
        result = classify_failure(None, self._expected(), ALL_STATES, timed_out=True)
        assert result == FailureType.TIMEOUT

    def test_priority_hallucinated_over_wrong_rules(self) -> None:
        """Hallucinated state takes priority over wrong rules."""
        prediction = {"next_state": "FANTASY", "applied_rules": ["WRONG"], "flags": ["WRONG"]}
        result = classify_failure(prediction, self._expected(), ALL_STATES)
        assert result == FailureType.HALLUCINATED_STATE

    def test_hallucinated_rule_priority_over_wrong_state(self) -> None:
        """Hallucinated state takes priority over hallucinated rule."""
        prediction = {
            "next_state": "ACCEPTED",
            "applied_rules": ["FANTASY-001"],
            "flags": [],
        }
        result = classify_failure(
            prediction, self._expected(), ALL_STATES, all_rule_ids=ALL_RULE_IDS
        )
        assert result == FailureType.HALLUCINATED_RULE

    def test_no_hallucination_check_without_vocabulary(self) -> None:
        """Without all_rule_ids, hallucinated rules fall through to WRONG_RULES."""
        prediction = {
            "next_state": "ACCEPTED",
            "applied_rules": ["FANTASY-001"],
            "flags": [],
        }
        result = classify_failure(prediction, self._expected(), ALL_STATES)
        assert result == FailureType.WRONG_RULES


# --- StateMachine + validator integration ---


class TestIntegration:
    def test_round_trip_correct_prediction(self) -> None:

        sm = StateMachine()
        prediction = {"next_state": "ACCEPTED", "applied_rules": ["ACC-008"], "flags": []}
        expected = {"next_state": "ACCEPTED", "applied_rules": ["ACC-008"], "flags": []}

        result = validate_prediction(prediction, expected)
        assert result.all_correct is True

        failure = classify_failure(
            prediction,
            expected,
            sm.get_all_states(),
            all_rule_ids=sm.get_all_rule_ids(),
            all_flag_ids=sm.get_all_flag_ids(),
        )
        assert failure is None

    def test_round_trip_hallucinated_state(self) -> None:

        sm = StateMachine()
        prediction = {"next_state": "FANTASY", "applied_rules": ["ACC-008"], "flags": []}
        expected = {"next_state": "ACCEPTED", "applied_rules": ["ACC-008"], "flags": []}

        failure = classify_failure(prediction, expected, sm.get_all_states())
        assert failure == FailureType.HALLUCINATED_STATE

    def test_round_trip_hallucinated_rule(self) -> None:

        sm = StateMachine()
        prediction = {"next_state": "ACCEPTED", "applied_rules": ["FANTASY-001"], "flags": []}
        expected = {"next_state": "ACCEPTED", "applied_rules": ["ACC-008"], "flags": []}

        failure = classify_failure(
            prediction, expected, sm.get_all_states(), all_rule_ids=sm.get_all_rule_ids()
        )
        assert failure == FailureType.HALLUCINATED_RULE


# --- Cross-module vocabulary sync (GH-98) ---


def _make_sync_test_data() -> tuple[Order, list[Slide], Event]:
    """Build Order/Slide/Event for vocabulary sync tests.

    Uses ACCESSIONING state because the step-filtered rule tests need a
    known step with rules in the catalog.
    """
    ts = datetime(2025, 1, 15, 10, 0, 0)
    order = Order(
        order_id="ORD-001",
        scenario_id="SCN-001",
        patient_name="Jane Doe",
        patient_age=55,
        patient_sex="F",
        specimen_type="Core Needle Biopsy",
        anatomic_site="Left Breast",
        fixative="10% NBF",
        fixation_time_hours=12.0,
        ordered_tests=["ER", "PR", "HER2", "Ki-67"],
        priority="routine",
        billing_info_present=True,
        current_state="ACCESSIONING",
        flags=[],
        created_at=ts,
        updated_at=ts,
    )
    slides = [
        Slide(
            slide_id="SLD-001",
            order_id="ORD-001",
            test_assignment="ER",
            status="sectioned",
            created_at=ts,
            updated_at=ts,
        ),
    ]
    event = Event(
        event_id="EVT-001",
        order_id="ORD-001",
        step_number=1,
        event_type="order_received",
        event_data={"patient_name": "Jane Doe"},
        created_at=ts,
    )
    return order, slides, event


class TestPromptValidatorVocabularySync:
    """Verify prompt template and validator use identical vocabulary sources.

    Renders a real prompt and extracts the vocabulary sections, then compares
    against StateMachine to ensure divergence is impossible.
    """

    @pytest.fixture()
    def rendered_prompt(self) -> str:
        """Render a step-filtered prompt for ACCESSIONING."""
        order, slides, event = _make_sync_test_data()
        return render_prompt(order, slides, event)

    def test_prompt_states_match_state_machine(self, rendered_prompt: str) -> None:
        """States listed in the prompt exactly match StateMachine.get_all_states()."""
        sm = StateMachine.get_instance()
        expected_states = sm.get_all_states()

        # Extract the comma-separated state list between "Valid Workflow States"
        # and "Valid Flags" sections. The list is a single line of ALL_CAPS words.
        match = re.search(
            r"## Valid Workflow States\n.*?\n\n(.+?)\n\n## Valid Flags",
            rendered_prompt,
            re.DOTALL,
        )
        assert match, "Could not find 'Valid Workflow States' section in prompt"

        prompt_states = frozenset(s.strip() for s in match.group(1).split(","))

        assert prompt_states == expected_states, (
            f"Prompt states {sorted(prompt_states)} "
            f"!= StateMachine states {sorted(expected_states)}"
        )

    def test_prompt_flags_match_state_machine(self, rendered_prompt: str) -> None:
        """Flags listed in the prompt exactly match StateMachine.get_all_flag_ids()."""
        sm = StateMachine.get_instance()
        expected_flags = sm.get_all_flag_ids()

        # Scope extraction to the Valid Flags section only (between
        # "## Valid Flags" and "## Flag Reference") to avoid matching
        # bold identifiers in other sections.
        flags_match = re.search(
            r"## Valid Flags\n(.*?)\n## Flag Reference",
            rendered_prompt,
            re.DOTALL,
        )
        assert flags_match, "Could not find 'Valid Flags' section in prompt"
        flags_section = flags_match.group(1)

        prompt_flag_ids = frozenset(re.findall(r"- \*\*(\w+)\*\*", flags_section))

        assert prompt_flag_ids == expected_flags, (
            f"Prompt flags {sorted(prompt_flag_ids)} != StateMachine flags {sorted(expected_flags)}"
        )

    def test_prompt_rule_ids_match_state_machine(self, rendered_prompt: str) -> None:
        """Step-filtered rule IDs in prompt equal StateMachine ACCESSIONING rules."""
        sm = StateMachine.get_instance()

        prompt_rule_ids = frozenset(re.findall(r"\d+\.\s+\*\*([A-Z]+-\d+)\*\*", rendered_prompt))

        # Compare against the step-specific rules for ACCESSIONING
        expected_rule_ids = frozenset(r.rule_id for r in sm.get_rules_for_state("ACCESSIONING"))
        assert prompt_rule_ids, "No rule IDs found in prompt"
        assert expected_rule_ids, "No ACCESSIONING rules in StateMachine"
        assert prompt_rule_ids == expected_rule_ids, (
            f"Prompt rules {sorted(prompt_rule_ids)} "
            f"!= ACCESSIONING rules {sorted(expected_rule_ids)}"
        )

    def test_full_context_rule_ids_match_state_machine(self) -> None:
        """Full-context prompt includes ALL rule IDs from StateMachine."""
        sm = StateMachine.get_instance()

        order, slides, event = _make_sync_test_data()
        prompt = render_prompt(order, slides, event, full_context=True)

        prompt_rule_ids = frozenset(re.findall(r"\d+\.\s+\*\*([A-Z]+-\d+)\*\*", prompt))
        all_rule_ids = sm.get_all_rule_ids()

        assert prompt_rule_ids, "No rule IDs found in full-context prompt"
        assert all_rule_ids, "No rules in StateMachine catalog"
        assert prompt_rule_ids == all_rule_ids, (
            f"Full-context prompt rules {sorted(prompt_rule_ids)} "
            f"!= StateMachine rules {sorted(all_rule_ids)}"
        )
