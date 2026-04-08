"""Tests for the routing prompt template."""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from src.prediction.prompt_template import (
    VALID_PROMPT_EXTRAS,
    _format_additional_context,
    _format_flag_reference,
    _format_prompt_extras,
    _format_rules,
    _format_valid_flags,
    _format_valid_states,
    _json_serializer,
    _to_json_str,
    render_prompt,
)
from src.rag.retriever import RetrievalResult
from src.workflow.models import Event, Order, Slide
from src.workflow.state_machine import Rule, StateMachine

# --- Fixtures ---


@pytest.fixture()
def sample_order() -> Order:
    """An order in ACCESSIONING state for template tests."""
    return Order(
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
        created_at=datetime(2025, 1, 15, 10, 0, 0),
        updated_at=datetime(2025, 1, 15, 10, 0, 0),
    )


@pytest.fixture()
def sample_slides() -> list[Slide]:
    """Slides for the sample order."""
    return [
        Slide(
            slide_id="SLD-001",
            order_id="ORD-001",
            test_assignment="ER",
            status="sectioned",
            created_at=datetime(2025, 1, 15, 10, 0, 0),
            updated_at=datetime(2025, 1, 15, 10, 0, 0),
        ),
        Slide(
            slide_id="SLD-002",
            order_id="ORD-001",
            test_assignment="PR",
            status="sectioned",
            created_at=datetime(2025, 1, 15, 10, 0, 0),
            updated_at=datetime(2025, 1, 15, 10, 0, 0),
        ),
    ]


@pytest.fixture()
def sample_event() -> Event:
    """An order_received event for template tests."""
    return Event(
        event_id="EVT-001",
        order_id="ORD-001",
        step_number=1,
        event_type="order_received",
        event_data={
            "patient_name": "Jane Doe",
            "specimen_type": "Core Needle Biopsy",
        },
        created_at=datetime(2025, 1, 15, 10, 0, 0),
    )


# --- Template Rendering ---


class TestRenderPrompt:
    """Tests for the main render_prompt function."""

    def test_renders_accessioning_scenario(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """Template renders correctly for an accessioning scenario."""
        prompt = render_prompt(sample_order, sample_slides, sample_event)

        assert "laboratory workflow routing system" in prompt
        assert "breast cancer histology lab" in prompt
        assert "ACC-" in prompt
        assert "ORD-001" in prompt
        assert "Jane Doe" in prompt
        assert "order_received" in prompt

    def test_no_unrendered_placeholders(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """All template variables are populated — no raw {placeholders}."""
        prompt = render_prompt(sample_order, sample_slides, sample_event)

        # The only curly braces should be in the JSON output format example
        # and the serialized JSON data. Check that template variables are gone.
        for var in [
            "{rules_for_current_step}",
            "{additional_context}",
            "{valid_states}",
            "{valid_flags}",
            "{flag_reference}",
            "{order_state_json}",
            "{slides_json}",
            "{event_json}",
        ]:
            assert var not in prompt, f"Unrendered placeholder found: {var}"

    def test_contains_json_output_format(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """The prompt includes the expected JSON output format."""
        prompt = render_prompt(sample_order, sample_slides, sample_event)

        assert '"next_state"' in prompt
        assert '"applied_rules"' in prompt
        assert '"flags"' in prompt
        assert '"reasoning"' in prompt

    def test_order_json_is_valid(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """Order state JSON in the prompt is valid and parseable."""
        prompt = render_prompt(sample_order, sample_slides, sample_event)

        # Extract the JSON block after "## Current Order State"
        order_section = prompt.split("## Current Order State")[1]
        order_section = order_section.split("## Slides")[0].strip()
        parsed = json.loads(order_section)
        assert parsed["order_id"] == "ORD-001"
        assert parsed["current_state"] == "ACCESSIONING"

    def test_slides_json_is_valid(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """Slides JSON in the prompt is valid and parseable."""
        prompt = render_prompt(sample_order, sample_slides, sample_event)

        slides_section = prompt.split("## Slides")[1]
        slides_section = slides_section.split("## New Event")[0].strip()
        parsed = json.loads(slides_section)
        assert len(parsed) == 2
        assert parsed[0]["slide_id"] == "SLD-001"

    def test_event_json_is_valid(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """Event JSON in the prompt is valid and parseable."""
        prompt = render_prompt(sample_order, sample_slides, sample_event)

        event_section = prompt.split("## New Event")[1]
        event_section = event_section.split("## Instructions")[0].strip()
        parsed = json.loads(event_section)
        assert parsed["event_type"] == "order_received"

    def test_empty_slides_list(
        self,
        sample_order: Order,
        sample_event: Event,
    ) -> None:
        """Prompt renders with an empty slides list."""
        prompt = render_prompt(sample_order, [], sample_event)
        assert "[]" in prompt


# --- Rule Filtering ---


class TestRuleFiltering:
    """Tests for rule filtering by workflow step."""

    def test_accessioning_rules_returned_for_accessioning_state(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """Accessioning state gets ACC-* rules."""
        prompt = render_prompt(sample_order, sample_slides, sample_event)
        assert "ACC-001" in prompt
        assert "ACC-008" in prompt

    def test_sample_prep_rules_for_accepted_state(
        self,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """ACCEPTED state maps to SAMPLE_PREP rules."""
        order = Order(
            order_id="ORD-002",
            scenario_id="SCN-002",
            patient_name="John Smith",
            patient_age=60,
            patient_sex="M",
            specimen_type="Core Needle Biopsy",
            anatomic_site="Left Breast",
            fixative="10% NBF",
            fixation_time_hours=12.0,
            ordered_tests=["ER", "PR"],
            priority="routine",
            billing_info_present=True,
            current_state="ACCEPTED",
            flags=[],
            created_at=datetime(2025, 1, 15, 10, 0, 0),
            updated_at=datetime(2025, 1, 15, 10, 0, 0),
        )
        prompt = render_prompt(order, sample_slides, sample_event)
        assert "SP-" in prompt

    def test_no_rules_for_terminal_state(
        self,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """Terminal states return no rules."""
        sm = StateMachine.get_instance()
        rules = sm.get_rules_for_state("ORDER_COMPLETE")
        assert rules == []

    def test_ihc_rules_use_applies_at(
        self,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """IHC states use applies_at field for rule matching."""
        sm = StateMachine.get_instance()
        rules = sm.get_rules_for_state("IHC_STAINING")
        rule_ids = [r.rule_id for r in rules]
        # IHC_STAINING should get rules with applies_at=IHC_STAINING
        assert any(rid.startswith("IHC-") for rid in rule_ids)


# --- Flag Reference ---


class TestFlagReference:
    """Tests for flag reference formatting."""

    def test_no_flags_message(self) -> None:
        """Empty flag list renders a 'no flags' message."""
        result = _format_flag_reference([], {})
        assert "No flags" in result

    def test_active_flags_rendered(self) -> None:
        """Active flags include effect and cleared_by info."""
        sm = StateMachine.get_instance()
        vocab = sm.get_flag_vocabulary()
        result = _format_flag_reference(["MISSING_INFO_PROCEED"], vocab)
        assert "MISSING_INFO_PROCEED" in result
        assert "Cleared by:" in result

    def test_only_active_flags_shown(
        self,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """Only flags on the order appear in the flag reference."""
        order = Order(
            order_id="ORD-003",
            scenario_id="SCN-003",
            patient_name="Test Patient",
            patient_age=50,
            patient_sex="F",
            specimen_type="Core Needle Biopsy",
            anatomic_site="Left Breast",
            fixative="10% NBF",
            fixation_time_hours=12.0,
            ordered_tests=["ER"],
            priority="routine",
            billing_info_present=True,
            current_state="ACCESSIONING",
            flags=["FIXATION_WARNING"],
            created_at=datetime(2025, 1, 15, 10, 0, 0),
            updated_at=datetime(2025, 1, 15, 10, 0, 0),
        )
        prompt = render_prompt(order, sample_slides, sample_event)
        # FIXATION_WARNING should appear in flag reference
        flag_section = prompt.split("## Flag Reference")[1].split("## Current Order State")[0]
        assert "FIXATION_WARNING" in flag_section
        # Other flags should NOT appear in the flag reference section
        assert "RECUT_REQUESTED" not in flag_section


# --- Valid State and Flag Vocabularies ---


class TestValidStatesVocabulary:
    """Tests for the valid states vocabulary section."""

    def test_valid_states_in_prompt(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """Prompt includes Valid Workflow States section with known states."""
        prompt = render_prompt(sample_order, sample_slides, sample_event)
        assert "## Valid Workflow States" in prompt
        states_section = prompt.split("## Valid Workflow States")[1].split("## Valid Flags")[0]
        assert "ACCEPTED" in states_section
        assert "MISSING_INFO_HOLD" in states_section
        assert "ACCESSIONING" in states_section

    def test_valid_states_constraint_text(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """Valid states section includes constraint language."""
        prompt = render_prompt(sample_order, sample_slides, sample_event)
        assert "MUST use one of these exact state names" in prompt

    def test_format_valid_states_sorted(self) -> None:
        """_format_valid_states returns sorted, comma-separated list."""
        states = frozenset({"ZEBRA", "ALPHA", "MIDDLE"})
        result = _format_valid_states(states)
        assert result == "ALPHA, MIDDLE, ZEBRA"

    def test_format_valid_states_empty_raises(self) -> None:
        """Empty frozenset raises ValueError."""
        with pytest.raises(ValueError, match="empty state vocabulary"):
            _format_valid_states(frozenset())


class TestValidFlagsVocabulary:
    """Tests for the valid flags vocabulary section."""

    def test_valid_flags_in_prompt(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """Prompt includes Valid Flags section with known flag IDs and set_at context."""
        prompt = render_prompt(sample_order, sample_slides, sample_event)
        assert "## Valid Flags" in prompt
        flags_section = prompt.split("## Valid Flags")[1].split("## Flag Reference")[0]
        assert "FIXATION_WARNING" in flags_section
        assert "MISSING_INFO_PROCEED" in flags_section
        assert "(set at:" in flags_section

    def test_valid_flags_constraint_text(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """Valid flags section includes constraint language."""
        prompt = render_prompt(sample_order, sample_slides, sample_event)
        assert "MUST only use flags from this list" in prompt

    def test_format_valid_flags_sorted_with_context(self) -> None:
        """_format_valid_flags returns sorted list with set_at annotations."""
        flags = frozenset({"ZEBRA_FLAG", "ALPHA_FLAG"})
        vocab = {
            "ALPHA_FLAG": {"set_at": ["ACCESSIONING"], "effect": "test", "cleared_by": "none"},
            "ZEBRA_FLAG": {
                "set_at": ["SAMPLE_PREP", "IHC"],
                "effect": "test",
                "cleared_by": "none",
            },
        }
        result = _format_valid_flags(flags, vocab)
        assert "ALPHA_FLAG" in result
        assert "ZEBRA_FLAG" in result
        assert "(set at: ACCESSIONING)" in result
        assert "(set at: SAMPLE_PREP, IHC)" in result
        # ALPHA before ZEBRA (sorted)
        assert result.index("ALPHA_FLAG") < result.index("ZEBRA_FLAG")

    def test_format_valid_flags_empty_raises(self) -> None:
        """Empty frozenset raises ValueError."""
        with pytest.raises(ValueError, match="empty flag vocabulary"):
            _format_valid_flags(frozenset(), {})

    def test_valid_flags_shown_regardless_of_active_flags(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """Valid flags vocabulary is shown even when no flags are active."""
        assert sample_order.flags == []
        prompt = render_prompt(sample_order, sample_slides, sample_event)
        flags_section = prompt.split("## Valid Flags")[1].split("## Flag Reference")[0]
        # Full vocabulary is always shown
        sm = StateMachine.get_instance()
        for flag_id in sm.get_all_flag_ids():
            assert flag_id in flags_section


# --- Full Context Mode ---


class TestFullContextMode:
    """Tests for full-context mode (all rules included)."""

    def test_full_context_includes_all_rules(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """Full-context mode includes rules from all steps."""
        prompt = render_prompt(sample_order, sample_slides, sample_event, full_context=True)
        # Should include rules from multiple steps
        assert "ACC-" in prompt
        assert "SP-" in prompt
        assert "HE-" in prompt
        assert "IHC-" in prompt
        assert "RES-" in prompt

    def test_full_context_includes_vocabularies(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """Full-context mode includes state and flag vocabularies."""
        prompt = render_prompt(sample_order, sample_slides, sample_event, full_context=True)
        assert "## Valid Workflow States" in prompt
        assert "MUST use one of these exact state names" in prompt
        assert "## Valid Flags" in prompt
        assert "MUST only use flags from this list" in prompt

    def test_vocabulary_sections_appear_in_correct_order(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """Vocabularies appear between rules and data sections."""
        prompt = render_prompt(sample_order, sample_slides, sample_event)

        rules_idx = prompt.index("## Your Rules")
        states_idx = prompt.index("## Valid Workflow States")
        flags_idx = prompt.index("## Valid Flags")
        flag_ref_idx = prompt.index("## Flag Reference")
        order_idx = prompt.index("## Current Order State")

        assert rules_idx < states_idx < flags_idx < flag_ref_idx < order_idx

    def test_filtered_mode_excludes_other_steps(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """Default filtered mode only includes current step rules."""
        prompt = render_prompt(sample_order, sample_slides, sample_event)
        # Accessioning state should NOT include SP, HE, IHC, RES rules
        rules_section = prompt.split("## Your Rules")[1].split("## Valid Workflow States")[0]
        assert "SP-" not in rules_section
        assert "RES-" not in rules_section


# --- Rule Formatting ---


class TestFormatRules:
    """Tests for the _format_rules helper."""

    def test_empty_rules(self) -> None:
        """No rules returns a descriptive message."""
        result = _format_rules([])
        assert "No rules apply" in result

    def test_severity_displayed_for_accessioning(self) -> None:
        """Accessioning rules show severity instead of priority."""
        rule = Rule(
            rule_id="ACC-001",
            step="ACCESSIONING",
            trigger="Patient name missing",
            action="MISSING_INFO_HOLD",
            source="SOP 3.1",
            severity="HOLD",
        )
        result = _format_rules([rule])
        assert "Severity: HOLD" in result
        assert "ACC-001" in result

    def test_priority_displayed_for_non_accessioning(self) -> None:
        """Non-accessioning rules show priority."""
        rule = Rule(
            rule_id="SP-001",
            step="SAMPLE_PREP",
            trigger="Grossing complete",
            action="Proceed to processing",
            source="SOP 4.1",
            priority=1,
        )
        result = _format_rules([rule])
        assert "Priority: 1" in result


# --- JSON Serialization Helpers ---


class TestJsonSerializer:
    """Tests for _json_serializer and _to_json_str helpers."""

    def test_datetime_serializes_to_iso_format(self) -> None:
        """Datetime objects serialize to ISO 8601 format."""
        dt = datetime(2025, 3, 15, 14, 30, 0)
        result = _json_serializer(dt)
        assert result == "2025-03-15T14:30:00"

    def test_unsupported_type_raises_type_error(self) -> None:
        """Non-datetime types raise TypeError."""
        with pytest.raises(TypeError, match="not JSON serializable"):
            _json_serializer({"nested": "dict"})

    def test_to_json_str_handles_datetime_in_dict(self) -> None:
        """_to_json_str correctly serializes dicts containing datetimes."""
        data = {"created_at": datetime(2025, 1, 15, 10, 0, 0), "name": "test"}
        result = _to_json_str(data)
        parsed = json.loads(result)
        assert parsed["created_at"] == "2025-01-15T10:00:00"
        assert parsed["name"] == "test"

    def test_to_json_str_formats_with_indent(self) -> None:
        """_to_json_str produces indented JSON."""
        result = _to_json_str({"a": 1})
        assert "\n" in result


# --- Unknown and Multiple Flags ---


class TestFlagEdgeCases:
    """Tests for flag edge cases: unknown flags and multiple active flags."""

    def test_unknown_flag_renders_as_unknown(self) -> None:
        """Flags not in vocabulary render as 'Unknown flag'."""
        result = _format_flag_reference(["NONEXISTENT_FLAG"], {})
        assert "NONEXISTENT_FLAG" in result
        assert "Unknown flag" in result

    def test_multiple_active_flags(self) -> None:
        """Multiple active flags all render with their metadata."""
        sm = StateMachine.get_instance()
        vocab = sm.get_flag_vocabulary()
        # Pick two flags that exist in the vocabulary
        flag_ids = list(vocab.keys())[:2]
        assert len(flag_ids) >= 2, "Need at least 2 flags in vocabulary"
        result = _format_flag_reference(flag_ids, vocab)
        for fid in flag_ids:
            assert fid in result
        assert result.count("Cleared by:") == 2

    def test_mix_of_known_and_unknown_flags(self) -> None:
        """Known and unknown flags render correctly together."""
        sm = StateMachine.get_instance()
        vocab = sm.get_flag_vocabulary()
        known_flag = next(iter(vocab.keys()))
        result = _format_flag_reference([known_flag, "BOGUS_FLAG"], vocab)
        assert "Cleared by:" in result
        assert "Unknown flag" in result


# --- Section-Specific Assertions ---


class TestPromptSections:
    """Tests that content appears in the correct prompt section."""

    def test_rules_appear_in_rules_section(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """ACC rules appear in Your Rules section, not elsewhere."""
        prompt = render_prompt(sample_order, sample_slides, sample_event)
        rules_section = prompt.split("## Your Rules")[1].split("## Valid Workflow States")[0]
        assert "ACC-001" in rules_section

    def test_flags_appear_in_flag_section(
        self,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """Active flags appear in Flag Reference section specifically."""
        order = Order(
            order_id="ORD-004",
            scenario_id="SCN-004",
            patient_name="Test",
            patient_age=50,
            patient_sex="F",
            specimen_type="Core Needle Biopsy",
            anatomic_site="Left Breast",
            fixative="10% NBF",
            fixation_time_hours=12.0,
            ordered_tests=["ER"],
            priority="routine",
            billing_info_present=True,
            current_state="ACCESSIONING",
            flags=["FIXATION_WARNING"],
            created_at=datetime(2025, 1, 15, 10, 0, 0),
            updated_at=datetime(2025, 1, 15, 10, 0, 0),
        )
        prompt = render_prompt(order, sample_slides, sample_event)
        flag_section = prompt.split("## Flag Reference")[1].split("## Current Order State")[0]
        assert "FIXATION_WARNING" in flag_section
        # Verify it's NOT in the rules section
        rules_section = prompt.split("## Your Rules")[1].split("## Valid Workflow States")[0]
        assert "FIXATION_WARNING" not in rules_section

    def test_order_json_in_order_section(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """Order JSON appears between Order State and Slides headers."""
        prompt = render_prompt(sample_order, sample_slides, sample_event)
        order_section = prompt.split("## Current Order State")[1].split("## Slides")[0]
        parsed = json.loads(order_section.strip())
        assert parsed["order_id"] == "ORD-001"

    def test_datetime_fields_are_iso_format_in_prompt(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """Datetime fields in rendered JSON use ISO 8601 format."""
        prompt = render_prompt(sample_order, sample_slides, sample_event)
        order_section = prompt.split("## Current Order State")[1].split("## Slides")[0]
        parsed = json.loads(order_section.strip())
        assert parsed["created_at"] == "2025-01-15T10:00:00"


# --- RAG Hybrid Mode ---


def _make_rag_chunks() -> list[RetrievalResult]:
    """Create sample RAG chunks for testing."""
    return [
        RetrievalResult(
            text="All accessioning rules use severity-based evaluation.",
            source_file="sops/accessioning.md",
            section_title="Accessioning Evaluation Logic",
            doc_type="sop",
            similarity_score=0.787,
        ),
        RetrievalResult(
            text="Orders reaching the resulting phase may terminate.",
            source_file="sops/resulting.md",
            section_title="7. Terminal States",
            doc_type="sop",
            similarity_score=0.735,
        ),
    ]


class TestRagHybridMode:
    """Tests for RAG hybrid mode: structured rules + RAG context."""

    def test_rag_mode_includes_structured_rules(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """RAG mode still includes formal rule IDs from the structured catalog."""
        chunks = _make_rag_chunks()
        prompt = render_prompt(sample_order, sample_slides, sample_event, rag_context=chunks)
        # Structured rules must be present (ACC-001 through ACC-009 for ACCESSIONING)
        assert "ACC-001" in prompt
        assert "ACC-008" in prompt
        # Rules should appear in the "Your Rules" section with structured format
        rules_section = prompt.split("## Your Rules")[1].split("## Additional Context")[0]
        assert "**ACC-001**" in rules_section
        assert "Trigger:" in rules_section
        assert "Action:" in rules_section

    def test_rag_mode_includes_additional_context_section(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """RAG mode adds an Additional Context section with retrieved chunks."""
        chunks = _make_rag_chunks()
        prompt = render_prompt(sample_order, sample_slides, sample_event, rag_context=chunks)
        assert "## Additional Context (Retrieved from SOPs)" in prompt
        assert "sops/accessioning.md" in prompt
        assert "severity-based evaluation" in prompt
        assert "Context 1" in prompt
        assert "Context 2" in prompt

    def test_rag_mode_additional_context_before_valid_states(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """Additional Context section appears between rules and Valid States."""
        chunks = _make_rag_chunks()
        prompt = render_prompt(sample_order, sample_slides, sample_event, rag_context=chunks)
        rules_idx = prompt.index("## Your Rules")
        additional_idx = prompt.index("## Additional Context")
        states_idx = prompt.index("## Valid Workflow States")
        assert rules_idx < additional_idx < states_idx

    def test_rag_mode_citation_instruction_in_additional_context(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """Additional Context section includes citation instruction."""
        chunks = _make_rag_chunks()
        prompt = render_prompt(sample_order, sample_slides, sample_event, rag_context=chunks)
        additional_section = prompt.split("## Additional Context")[1].split(
            "## Valid Workflow States"
        )[0]
        assert "do NOT invent descriptive labels" in additional_section

    def test_non_rag_mode_no_additional_context(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """Non-RAG modes do not include the Additional Context section."""
        prompt = render_prompt(sample_order, sample_slides, sample_event)
        assert "## Additional Context" not in prompt

    def test_full_context_mode_no_additional_context(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """Full-context mode does not include Additional Context section."""
        prompt = render_prompt(sample_order, sample_slides, sample_event, full_context=True)
        assert "## Additional Context" not in prompt

    def test_rag_mode_ignores_full_context_flag(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """When rag_context is provided, full_context=True is ignored."""
        chunks = _make_rag_chunks()
        prompt = render_prompt(
            sample_order,
            sample_slides,
            sample_event,
            full_context=True,
            rag_context=chunks,
        )
        # Should have step-filtered rules (only ACC-*), not all rules
        rules_section = prompt.split("## Your Rules")[1].split("## Additional Context")[0]
        assert "**ACC-001**" in rules_section
        assert "**SP-001**" not in rules_section
        assert "**RES-001**" not in rules_section


class TestRuleCitationInstruction:
    """Tests for the formal rule ID citation instruction."""

    def test_citation_instruction_in_all_modes(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """Instruction #6 about formal rule IDs appears in all modes."""
        for kwargs in [
            {},
            {"full_context": True},
            {"rag_context": _make_rag_chunks()},
        ]:
            prompt = render_prompt(sample_order, sample_slides, sample_event, **kwargs)
            instructions = prompt.split("## Instructions")[1].split(
                "\nRespond with ONLY a JSON object"
            )[0]
            assert "formal rule IDs" in instructions
            assert "Do NOT invent descriptive rule" in instructions


class TestFormatAdditionalContext:
    """Tests for the _format_additional_context helper."""

    def test_empty_chunks_returns_empty_string(self) -> None:
        """No chunks returns empty string."""
        result = _format_additional_context([])
        assert result == ""

    def test_chunks_include_section_header(self) -> None:
        """Non-empty chunks include the Additional Context header."""
        chunks = _make_rag_chunks()
        result = _format_additional_context(chunks)
        assert "## Additional Context (Retrieved from SOPs)" in result

    def test_chunks_include_citation_reminder(self) -> None:
        """Non-empty chunks include rule citation reminder."""
        chunks = _make_rag_chunks()
        result = _format_additional_context(chunks)
        assert "do NOT invent descriptive labels" in result

    def test_chunks_numbered_with_source(self) -> None:
        """Chunks are numbered with source attribution."""
        chunks = _make_rag_chunks()
        result = _format_additional_context(chunks)
        assert "### Context 1 (from sops/accessioning.md: Accessioning Evaluation Logic)" in result
        assert "### Context 2 (from sops/resulting.md: 7. Terminal States)" in result

    def test_chunk_text_preserved(self) -> None:
        """Original chunk text is included verbatim."""
        chunks = _make_rag_chunks()
        result = _format_additional_context(chunks)
        assert "severity-based evaluation" in result
        assert "resulting phase may terminate" in result

    def test_single_chunk_formats_correctly(self) -> None:
        """A single chunk produces a numbered, attributed context block."""
        chunk = RetrievalResult(
            text="Single chunk content.",
            source_file="sops/single.md",
            section_title="Only Section",
            doc_type="sop",
            similarity_score=0.9,
        )
        result = _format_additional_context([chunk])
        assert "### Context 1 (from sops/single.md: Only Section)" in result
        assert "Single chunk content." in result
        assert "Context 2" not in result


class TestRagHybridModeNonAccessioning:
    """Test hybrid mode with non-ACCESSIONING workflow states."""

    def test_rag_mode_filters_rules_by_state_for_ihc_staining(
        self,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """Hybrid mode uses step-filtered rules for IHC_STAINING state."""
        order = Order(
            order_id="ORD-010",
            scenario_id="SCN-010",
            patient_name="Test Patient",
            patient_age=55,
            patient_sex="F",
            specimen_type="Core Needle Biopsy",
            anatomic_site="Left Breast",
            fixative="10% NBF",
            fixation_time_hours=12.0,
            ordered_tests=["ER", "PR", "HER2"],
            priority="routine",
            billing_info_present=True,
            current_state="IHC_STAINING",
            flags=[],
            created_at=datetime(2025, 1, 15, 10, 0, 0),
            updated_at=datetime(2025, 1, 15, 10, 0, 0),
        )
        chunks = _make_rag_chunks()
        prompt = render_prompt(order, sample_slides, sample_event, rag_context=chunks)
        rules_section = prompt.split("## Your Rules")[1].split("## Additional Context")[0]
        # IHC rules should be present
        assert "**IHC-" in rules_section
        # ACC rules should NOT be present
        assert "**ACC-" not in rules_section


class TestRagContextEmptyList:
    """Test behavior when rag_context is an empty list (RAG returned no chunks)."""

    def test_rag_context_empty_list_uses_hybrid_mode(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """rag_context=[] triggers hybrid mode (structured rules, no additional context)."""
        prompt = render_prompt(sample_order, sample_slides, sample_event, rag_context=[])
        # Structured rules present
        assert "**ACC-001**" in prompt
        # No additional context section (empty chunks)
        assert "## Additional Context" not in prompt

    def test_rag_context_none_uses_default_mode(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """rag_context=None (default) uses default filtered-rules mode."""
        prompt = render_prompt(sample_order, sample_slides, sample_event, rag_context=None)
        assert "**ACC-001**" in prompt
        assert "## Additional Context" not in prompt

    def test_rag_context_empty_vs_none_both_have_rules(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """Both rag_context=[] and None produce step-filtered rules."""
        prompt_empty = render_prompt(sample_order, sample_slides, sample_event, rag_context=[])
        prompt_none = render_prompt(sample_order, sample_slides, sample_event, rag_context=None)
        # Both should have ACC rules (same state)
        assert "**ACC-001**" in prompt_empty
        assert "**ACC-001**" in prompt_none


# --- Prompt Extras (Phase 3) ---


class TestFormatPromptExtras:
    """Tests for the _format_prompt_extras helper."""

    def test_empty_extras_returns_empty_strings(self) -> None:
        """No extras returns empty blocks."""
        prompt_block, retry_block = _format_prompt_extras(frozenset())
        assert prompt_block == ""
        assert retry_block == ""

    def test_state_sequence_adds_workflow_section(self) -> None:
        """state_sequence extra adds Workflow Step Sequence section."""
        prompt_block, retry_block = _format_prompt_extras(frozenset({"state_sequence"}))
        assert "## Workflow Step Sequence" in prompt_block
        assert "SAMPLE_PREP_PROCESSING" in prompt_block
        assert "SAMPLE_PREP_EMBEDDING" in prompt_block
        assert retry_block == ""

    def test_retry_clarification_adds_instruction(self) -> None:
        """retry_clarification extra adds item 7 to Instructions."""
        prompt_block, retry_block = _format_prompt_extras(frozenset({"retry_clarification"}))
        assert prompt_block == ""
        assert "RETRY current step" in retry_block
        assert "specific workflow state name" in retry_block

    def test_few_shot_adds_example(self) -> None:
        """few_shot extra adds Example section."""
        prompt_block, retry_block = _format_prompt_extras(frozenset({"few_shot"}))
        assert "## Example" in prompt_block
        assert "grossing_complete" in prompt_block
        assert "SAMPLE_PREP_PROCESSING" in prompt_block

    def test_combined_extras(self) -> None:
        """Multiple extras combine correctly."""
        extras = frozenset({"state_sequence", "retry_clarification", "few_shot"})
        prompt_block, retry_block = _format_prompt_extras(extras)
        assert "## Workflow Step Sequence" in prompt_block
        assert "## Example" in prompt_block
        assert "RETRY current step" in retry_block

    def test_invalid_extra_raises(self) -> None:
        """Invalid extra name raises ValueError."""
        with pytest.raises(ValueError, match="Invalid prompt extras"):
            _format_prompt_extras(frozenset({"bogus_extra"}))

    def test_valid_prompt_extras_constant(self) -> None:
        """VALID_PROMPT_EXTRAS contains the expected set."""
        assert {
            "state_sequence",
            "retry_clarification",
            "few_shot",
            "skills",
            "routing_tools",
            "routing_tools_lite",
        } == VALID_PROMPT_EXTRAS


class TestRenderPromptWithExtras:
    """Tests for render_prompt with prompt_extras parameter."""

    def test_default_no_extras(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """Default render has no extras sections."""
        prompt = render_prompt(sample_order, sample_slides, sample_event)
        assert "## Workflow Step Sequence" not in prompt
        assert "## Example" not in prompt

    def test_state_sequence_in_rendered_prompt(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """state_sequence appears between rules and Valid Workflow States."""
        prompt = render_prompt(
            sample_order,
            sample_slides,
            sample_event,
            prompt_extras=frozenset({"state_sequence"}),
        )
        assert "## Workflow Step Sequence" in prompt
        seq_idx = prompt.index("## Workflow Step Sequence")
        states_idx = prompt.index("## Valid Workflow States")
        assert seq_idx < states_idx

    def test_retry_clarification_in_instructions(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """retry_clarification appears in the Instructions section."""
        prompt = render_prompt(
            sample_order,
            sample_slides,
            sample_event,
            prompt_extras=frozenset({"retry_clarification"}),
        )
        instructions = prompt.split("## Instructions")[1].split("Respond with ONLY")[0]
        assert "RETRY current step" in instructions

    def test_few_shot_in_rendered_prompt(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """few_shot example appears in rendered prompt."""
        prompt = render_prompt(
            sample_order,
            sample_slides,
            sample_event,
            prompt_extras=frozenset({"few_shot"}),
        )
        assert "## Example" in prompt
        assert "grossing_complete" in prompt

    def test_all_extras_combined(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """All three extras render correctly together."""
        extras = frozenset({"state_sequence", "retry_clarification", "few_shot"})
        prompt = render_prompt(
            sample_order,
            sample_slides,
            sample_event,
            prompt_extras=extras,
        )
        assert "## Workflow Step Sequence" in prompt
        assert "## Example" in prompt
        assert "RETRY current step" in prompt

    def test_no_unrendered_placeholders_with_extras(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """All template variables populated even with extras."""
        extras = frozenset({"state_sequence", "retry_clarification", "few_shot"})
        prompt = render_prompt(
            sample_order,
            sample_slides,
            sample_event,
            prompt_extras=extras,
        )
        for var in [
            "{rules_for_current_step}",
            "{additional_context}",
            "{prompt_extras}",
            "{retry_clarification}",
            "{valid_states}",
            "{valid_flags}",
            "{flag_reference}",
            "{order_state_json}",
            "{slides_json}",
            "{event_json}",
        ]:
            assert var not in prompt, f"Unrendered placeholder found: {var}"

    def test_extras_work_with_rag_mode(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """Prompt extras work alongside RAG hybrid mode."""
        chunks = _make_rag_chunks()
        extras = frozenset({"state_sequence", "retry_clarification"})
        prompt = render_prompt(
            sample_order,
            sample_slides,
            sample_event,
            rag_context=chunks,
            prompt_extras=extras,
        )
        assert "## Additional Context" in prompt
        assert "## Workflow Step Sequence" in prompt
        assert "RETRY current step" in prompt


# --- Skill Mode (GH #221) ---


class TestSkillMode:
    """Tests for skill-based routing prompt generation."""

    def test_skills_replaces_rules_with_skill_text(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """Skills mode injects skill document instead of formatted rules."""
        prompt = render_prompt(
            sample_order,
            sample_slides,
            sample_event,
            prompt_extras=frozenset({"skills"}),
        )
        # Skill content should be present (accessioning skill for ACCESSIONING state)
        assert "Accessioning Evaluation Skill" in prompt
        # Standard numbered rule format should NOT be present
        assert "1. **ACC-001**" not in prompt

    def test_skills_contains_numeric_comparison(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """Accessioning skill includes explicit numeric comparison steps."""
        prompt = render_prompt(
            sample_order,
            sample_slides,
            sample_event,
            prompt_extras=frozenset({"skills"}),
        )
        assert "< 6.0" in prompt
        assert "> 72.0" in prompt

    def test_skills_contains_checklist(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """Accessioning skill forces evaluation of ALL rules."""
        prompt = render_prompt(
            sample_order,
            sample_slides,
            sample_event,
            prompt_extras=frozenset({"skills"}),
        )
        for rule_id in [
            "ACC-001",
            "ACC-002",
            "ACC-003",
            "ACC-004",
            "ACC-005",
            "ACC-006",
            "ACC-007",
            "ACC-009",
        ]:
            assert rule_id in prompt

    def test_skills_fallback_for_pass_through_state(
        self,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """States with no skill fall back to _format_rules()."""
        order = Order(
            order_id="ORD-FALL",
            scenario_id="SC-FALL",
            patient_name="Test",
            patient_age=50,
            patient_sex="F",
            specimen_type="biopsy",
            anatomic_site="breast",
            fixative="formalin",
            fixation_time_hours=24.0,
            ordered_tests=["ER"],
            priority="routine",
            billing_info_present=True,
            current_state="MISSING_INFO_HOLD",
            flags=[],
            created_at=datetime(2025, 1, 15, 10, 0, 0),
            updated_at=datetime(2025, 1, 15, 10, 0, 0),
        )
        prompt = render_prompt(
            order,
            sample_slides,
            sample_event,
            prompt_extras=frozenset({"skills"}),
        )
        # MISSING_INFO_HOLD has no rules and no skill — should get "No rules apply"
        assert "No rules apply" in prompt

    def test_skills_composable_with_retry_clarification(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """Skills can be combined with other prompt extras."""
        prompt = render_prompt(
            sample_order,
            sample_slides,
            sample_event,
            prompt_extras=frozenset({"skills", "retry_clarification"}),
        )
        assert "Accessioning Evaluation Skill" in prompt
        assert "RETRY current step" in prompt

    def test_skills_no_unrendered_placeholders(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """No template placeholders remain with skills active."""
        prompt = render_prompt(
            sample_order,
            sample_slides,
            sample_event,
            prompt_extras=frozenset({"skills"}),
        )
        for var in [
            "{rules_for_current_step}",
            "{additional_context}",
            "{prompt_extras}",
            "{retry_clarification}",
            "{valid_states}",
        ]:
            assert var not in prompt, f"Unrendered placeholder: {var}"

    def test_skills_suppresses_rag_context(
        self,
        sample_order: Order,
        sample_slides: list[Slide],
        sample_event: Event,
    ) -> None:
        """When skills are active, RAG chunks are suppressed (skills are self-contained)."""
        chunks = _make_rag_chunks()
        prompt = render_prompt(
            sample_order,
            sample_slides,
            sample_event,
            rag_context=chunks,
            prompt_extras=frozenset({"skills"}),
        )
        # Skill content should be present
        assert "Accessioning Evaluation Skill" in prompt
        # RAG additional context should NOT be present
        assert "## Additional Context" not in prompt
