"""Tests for the query prompt template."""

from __future__ import annotations

import json

import pytest

from src.prediction.query_prompt_template import (
    _STATE_ANNOTATIONS,
    _format_flag_definitions,
    _format_state_reference,
    _to_json_str,
    get_output_format,
    render_query_prompt,
    render_query_prompt_from_parts,
)
from src.simulator.schema import (
    DatabaseStateSnapshot,
    QueryExpectedOutput,
    QueryScenario,
)
from src.workflow.state_machine import StateMachine

# --- Fixtures ---


@pytest.fixture()
def sample_database_state() -> DatabaseStateSnapshot:
    """A database state with mixed order states and no slides."""
    return DatabaseStateSnapshot(
        orders=(
            {
                "order_id": "ORD-101",
                "current_state": "ACCEPTED",
                "specimen_type": "biopsy",
                "anatomic_site": "breast",
                "priority": "routine",
                "flags": [],
                "created_at": "2025-01-15T08:00:00Z",
            },
            {
                "order_id": "ORD-102",
                "current_state": "SAMPLE_PREP_PROCESSING",
                "specimen_type": "excision",
                "anatomic_site": "breast",
                "priority": "routine",
                "flags": [],
                "created_at": "2025-01-15T08:30:00Z",
            },
            {
                "order_id": "ORD-103",
                "current_state": "ACCEPTED",
                "specimen_type": "resection",
                "anatomic_site": "breast",
                "priority": "rush",
                "flags": [],
                "created_at": "2025-01-15T09:00:00Z",
            },
        ),
        slides=(),
    )


@pytest.fixture()
def sample_query_scenario(
    sample_database_state: DatabaseStateSnapshot,
) -> QueryScenario:
    """A Tier 1 order_list query scenario."""
    return QueryScenario(
        scenario_id="QR-001",
        category="query",
        tier=1,
        description="Simple lookup — orders ready for grossing",
        database_state=sample_database_state,
        query="What orders are ready for grossing?",
        expected_output=QueryExpectedOutput(
            answer_type="order_list",
            reasoning="Orders in ACCEPTED state are ready for grossing.",
            order_ids=("ORD-101", "ORD-103"),
        ),
    )


@pytest.fixture()
def scenario_with_flags() -> QueryScenario:
    """A scenario with flagged orders for flag reference testing."""
    return QueryScenario(
        scenario_id="QR-002",
        category="query",
        tier=3,
        description="Flag reasoning — why is order on hold?",
        database_state=DatabaseStateSnapshot(
            orders=(
                {
                    "order_id": "ORD-201",
                    "current_state": "RESULTING_HOLD",
                    "specimen_type": "biopsy",
                    "anatomic_site": "breast",
                    "priority": "routine",
                    "flags": ["MISSING_INFO_PROCEED"],
                    "created_at": "2025-01-15T08:00:00Z",
                },
            ),
            slides=(),
        ),
        query="Why is order ORD-201 on hold?",
        expected_output=QueryExpectedOutput(
            answer_type="order_status",
            reasoning="RESULTING_HOLD with MISSING_INFO_PROCEED flag.",
            order_ids=("ORD-201",),
        ),
    )


# --- Template Rendering ---


class TestRenderQueryPrompt:
    """Tests for the main render_query_prompt function."""

    def test_renders_basic_query(self, sample_query_scenario: QueryScenario) -> None:
        """Template renders correctly for a basic query scenario."""
        prompt = render_query_prompt(sample_query_scenario)

        assert "laboratory information system assistant" in prompt
        assert "breast cancer" in prompt
        assert "What orders are ready for grossing?" in prompt
        assert "ORD-101" in prompt
        assert "ORD-103" in prompt

    def test_no_unrendered_placeholders(self, sample_query_scenario: QueryScenario) -> None:
        """All template variables are populated — no raw {placeholders}."""
        prompt = render_query_prompt(sample_query_scenario)

        for var in [
            "{orders_json}",
            "{slides_json}",
            "{state_reference}",
            "{flag_reference}",
            "{query}",
            "{output_format}",
        ]:
            assert var not in prompt, f"Unrendered placeholder found: {var}"

    def test_orders_json_is_valid(self, sample_query_scenario: QueryScenario) -> None:
        """Orders JSON in the prompt is valid and parseable."""
        prompt = render_query_prompt(sample_query_scenario)

        orders_section = prompt.split("### Orders")[1].split("### Slides")[0].strip()
        parsed = json.loads(orders_section)
        assert len(parsed) == 3
        # Verify all orders are present (sort order tested in TestOrderSorting)
        order_ids = {o["order_id"] for o in parsed}
        assert order_ids == {"ORD-101", "ORD-102", "ORD-103"}

    def test_slides_json_is_valid_empty(self, sample_query_scenario: QueryScenario) -> None:
        """Empty slides list renders as valid JSON."""
        prompt = render_query_prompt(sample_query_scenario)

        slides_section = prompt.split("### Slides")[1].split("## Workflow Reference")[0].strip()
        parsed = json.loads(slides_section)
        assert parsed == []

    def test_includes_workflow_state_reference(self, sample_query_scenario: QueryScenario) -> None:
        """Prompt includes workflow state descriptions."""
        prompt = render_query_prompt(sample_query_scenario)

        assert "State Descriptions" in prompt
        assert "ACCESSIONING" in prompt
        assert "ACCEPTED" in prompt
        assert "ORDER_COMPLETE" in prompt

    def test_includes_flag_definitions(self, sample_query_scenario: QueryScenario) -> None:
        """Prompt includes flag definitions in workflow reference."""
        prompt = render_query_prompt(sample_query_scenario)

        assert "Flag Definitions" in prompt
        assert "MISSING_INFO_PROCEED" in prompt
        assert "FIXATION_WARNING" in prompt
        assert "Cleared by:" in prompt

    def test_query_in_question_section(self, sample_query_scenario: QueryScenario) -> None:
        """The query appears in the Question section."""
        prompt = render_query_prompt(sample_query_scenario)

        question_section = prompt.split("## Question")[1].split("## Instructions")[0]
        assert "What orders are ready for grossing?" in question_section


# --- Output Format Adaptation ---


class TestOutputFormatAdaptation:
    """Tests that output format adapts to answer_type."""

    def test_order_list_format(self, sample_query_scenario: QueryScenario) -> None:
        """order_list answer_type shows order_ids format."""
        prompt = render_query_prompt(sample_query_scenario)
        assert '"order_ids"' in prompt
        assert '"reasoning"' in prompt

    def test_order_status_format(self, scenario_with_flags: QueryScenario) -> None:
        """order_status answer_type shows status_summary format."""
        prompt = render_query_prompt(scenario_with_flags)
        assert '"status_summary"' in prompt
        assert '"order_ids"' in prompt

    def test_explanation_format(self, sample_database_state: DatabaseStateSnapshot) -> None:
        """explanation answer_type shows explanation format."""
        scenario = QueryScenario(
            scenario_id="QR-003",
            category="query",
            tier=2,
            description="Explanation query",
            database_state=sample_database_state,
            query="What does ACCEPTED state mean?",
            expected_output=QueryExpectedOutput(
                answer_type="explanation",
                reasoning="ACCEPTED means accessioning is complete.",
            ),
        )
        prompt = render_query_prompt(scenario)
        assert '"explanation"' in prompt

    def test_prioritized_list_format(self, sample_database_state: DatabaseStateSnapshot) -> None:
        """prioritized_list answer_type shows priority ordering format."""
        scenario = QueryScenario(
            scenario_id="QR-004",
            category="query",
            tier=4,
            description="Priority ranking query",
            database_state=sample_database_state,
            query="Which orders should I process first?",
            expected_output=QueryExpectedOutput(
                answer_type="prioritized_list",
                reasoning="Rush orders before routine.",
                order_ids=("ORD-103", "ORD-101"),
            ),
        )
        prompt = render_query_prompt(scenario)
        assert '"order_ids"' in prompt
        assert "priority order" in prompt


# --- get_output_format ---


class TestGetOutputFormat:
    """Tests for the get_output_format helper."""

    def test_all_valid_types_return_format(self) -> None:
        """All four answer types return a non-empty format string."""
        for answer_type in ["order_list", "order_status", "explanation", "prioritized_list"]:
            fmt = get_output_format(answer_type)
            assert fmt, f"Empty format for {answer_type}"

    def test_unknown_type_raises_value_error(self) -> None:
        """Unknown answer_type raises ValueError."""
        with pytest.raises(ValueError, match="Unknown answer_type"):
            get_output_format("invalid_type")


# --- render_query_prompt_from_parts ---


class TestRenderFromParts:
    """Tests for the render_query_prompt_from_parts function."""

    def test_renders_same_as_scenario(self, sample_query_scenario: QueryScenario) -> None:
        """Rendering from parts produces the same output as from scenario."""
        from_scenario = render_query_prompt(sample_query_scenario)
        from_parts = render_query_prompt_from_parts(
            database_state=sample_query_scenario.database_state,
            query=sample_query_scenario.query,
            answer_type=sample_query_scenario.expected_output.answer_type,
        )
        assert from_scenario == from_parts


# --- Workflow Reference Helpers ---


class TestFormatStateReference:
    """Tests for the _format_state_reference helper."""

    def test_includes_all_phases(self) -> None:
        """State reference covers all workflow phases."""
        sm = StateMachine.get_instance()
        result = _format_state_reference(sm)
        for phase in ["accessioning", "sample_prep", "he_review", "ihc", "resulting", "terminal"]:
            assert phase in result

    def test_includes_state_descriptions(self) -> None:
        """State reference includes descriptions, not just IDs."""
        sm = StateMachine.get_instance()
        result = _format_state_reference(sm)
        # Check a representative description
        assert "ready for grossing" in result

    def test_state_descriptions_include_lab_concepts(self) -> None:
        """State descriptions include human-readable lab terminology.

        Models need to map natural language queries (e.g. 'ready for grossing',
        'sign out') to workflow state names. Descriptions must bridge that gap.
        Assertions are pinned to specific state lines to catch misplaced terms.
        """
        sm = StateMachine.get_instance()
        result = _format_state_reference(sm)
        # Build a map of state_id -> description line for precise assertions
        state_lines = {}
        for line in result.splitlines():
            stripped = line.strip()
            if stripped.startswith("- ") and ": " in stripped:
                state_id, desc = stripped[2:].split(": ", 1)
                state_lines[state_id] = desc
        # ACCEPTED must mention grossing (QR-001 asks about "ready for grossing")
        assert "grossing" in state_lines.get("ACCEPTED", ""), (
            "ACCEPTED description must mention 'grossing'"
        )
        # PATHOLOGIST_SIGNOUT must mention sign out (QR-007 asks about "sign out")
        assert "signs out" in state_lines.get("PATHOLOGIST_SIGNOUT", ""), (
            "PATHOLOGIST_SIGNOUT description must mention 'signs out'"
        )


class TestFormatFlagDefinitions:
    """Tests for the _format_flag_definitions helper."""

    def test_includes_all_flags(self) -> None:
        """Flag definitions include all flags from the vocabulary."""
        sm = StateMachine.get_instance()
        result = _format_flag_definitions(sm)
        for flag_id in sm.get_all_flag_ids():
            assert flag_id in result

    def test_includes_cleared_by(self) -> None:
        """Each flag entry includes 'Cleared by' information."""
        sm = StateMachine.get_instance()
        result = _format_flag_definitions(sm)
        assert "Cleared by:" in result


# --- Section Placement ---


class TestPromptSections:
    """Tests that content appears in the correct prompt section."""

    def test_orders_in_orders_section(self, sample_query_scenario: QueryScenario) -> None:
        """Order data appears between Orders and Slides headers."""
        prompt = render_query_prompt(sample_query_scenario)
        orders_section = prompt.split("### Orders")[1].split("### Slides")[0]
        assert "ORD-101" in orders_section
        assert "ORD-102" in orders_section

    def test_state_reference_in_workflow_section(
        self, sample_query_scenario: QueryScenario
    ) -> None:
        """State descriptions appear in the Workflow Reference section."""
        prompt = render_query_prompt(sample_query_scenario)
        workflow_section = prompt.split("## Workflow Reference")[1].split("## Question")[0]
        assert "ACCESSIONING" in workflow_section
        assert "ORDER_COMPLETE" in workflow_section

    def test_instructions_at_end(self, sample_query_scenario: QueryScenario) -> None:
        """Instructions section appears at the end of the prompt."""
        prompt = render_query_prompt(sample_query_scenario)
        instructions_idx = prompt.index("## Instructions")
        question_idx = prompt.index("## Question")
        assert instructions_idx > question_idx


# --- Edge Cases ---


class TestEdgeCases:
    """Tests for edge cases in query prompt rendering."""

    def test_orders_with_slides(self) -> None:
        """Prompt correctly renders when slides are present."""
        db_state = DatabaseStateSnapshot(
            orders=(
                {
                    "order_id": "ORD-301",
                    "current_state": "IHC_SCORING",
                    "specimen_type": "biopsy",
                    "anatomic_site": "breast",
                    "priority": "routine",
                    "flags": [],
                    "created_at": "2025-01-15T08:00:00Z",
                },
            ),
            slides=(
                {
                    "slide_id": "SLD-301",
                    "order_id": "ORD-301",
                    "test_assignment": "ER",
                    "status": "scored",
                    "score_result": {"allred_score": 8},
                },
            ),
        )
        scenario = QueryScenario(
            scenario_id="QR-005",
            category="query",
            tier=2,
            description="Query with slides present",
            database_state=db_state,
            query="What is the ER score for ORD-301?",
            expected_output=QueryExpectedOutput(
                answer_type="order_status",
                reasoning="ER slide SLD-301 has Allred score 8.",
                order_ids=("ORD-301",),
            ),
        )
        prompt = render_query_prompt(scenario)
        assert "SLD-301" in prompt
        assert "allred_score" in prompt
        slides_section = prompt.split("### Slides")[1].split("## Workflow Reference")[0].strip()
        parsed = json.loads(slides_section)
        assert len(parsed) == 1

    def test_many_orders_token_budget(self) -> None:
        """Large snapshots with many orders still render correctly."""
        orders = tuple(
            {
                "order_id": f"ORD-{i:03d}",
                "current_state": "ACCEPTED",
                "specimen_type": "biopsy",
                "anatomic_site": "breast",
                "priority": "routine",
                "flags": [],
            }
            for i in range(1, 16)
        )
        db_state = DatabaseStateSnapshot(orders=orders, slides=())
        prompt = render_query_prompt_from_parts(
            database_state=db_state,
            query="How many orders are pending?",
            answer_type="order_list",
        )
        # All 15 orders should appear
        for i in range(1, 16):
            assert f"ORD-{i:03d}" in prompt


# --- JSON Serialization Helpers ---


class TestToJsonStr:
    """Tests for the _to_json_str helper."""

    def test_empty_list_serializes(self) -> None:
        """Empty lists serialize to '[]'."""
        result = _to_json_str([])
        assert json.loads(result) == []

    def test_empty_dict_serializes(self) -> None:
        """Empty dicts serialize to '{}'."""
        result = _to_json_str({})
        assert json.loads(result) == {}

    def test_nested_structures(self) -> None:
        """Nested dicts and lists serialize correctly."""
        data: list[dict[str, object]] = [{"id": "ORD-1", "flags": []}]
        result = _to_json_str(data)
        assert json.loads(result) == data

    def test_formats_with_indent(self) -> None:
        """Output is indented for readability."""
        result = _to_json_str({"a": 1, "b": 2})
        assert "\n" in result
        assert "  " in result


# --- Input Validation ---


class TestInputValidation:
    """Tests for input validation on render_query_prompt_from_parts."""

    def test_rejects_none_database_state(self) -> None:
        """None database_state raises TypeError."""
        with pytest.raises(TypeError, match="database_state must be DatabaseStateSnapshot"):
            render_query_prompt_from_parts(
                database_state=None,  # type: ignore[arg-type]
                query="What orders are ready?",
                answer_type="order_list",
            )

    def test_rejects_none_query(self, sample_database_state: DatabaseStateSnapshot) -> None:
        """None query raises TypeError."""
        with pytest.raises(TypeError, match="query must be str"):
            render_query_prompt_from_parts(
                database_state=sample_database_state,
                query=None,  # type: ignore[arg-type]
                answer_type="order_list",
            )

    def test_rejects_empty_query(self, sample_database_state: DatabaseStateSnapshot) -> None:
        """Empty query raises ValueError."""
        with pytest.raises(ValueError, match="query must not be empty"):
            render_query_prompt_from_parts(
                database_state=sample_database_state,
                query="   ",
                answer_type="order_list",
            )


# --- Phase Ordering ---


class TestPhaseOrdering:
    """Tests that phases appear in workflow progression order."""

    def test_phases_in_workflow_order(self) -> None:
        """State reference renders phases in natural workflow order."""
        sm = StateMachine.get_instance()
        result = _format_state_reference(sm)
        phase_positions = {
            phase: result.index(f"**{phase}**")
            for phase in [
                "accessioning",
                "sample_prep",
                "he_review",
                "ihc",
                "resulting",
                "terminal",
            ]
        }
        phases_by_position = sorted(phase_positions, key=phase_positions.get)  # type: ignore[arg-type]
        assert phases_by_position == [
            "accessioning",
            "sample_prep",
            "he_review",
            "ihc",
            "resulting",
            "terminal",
        ]


# --- State Annotations ---


class TestStateAnnotations:
    """Tests for state actor/group annotations in the prompt."""

    def test_annotations_cover_all_states(self) -> None:
        """Every state in the state machine has an annotation and vice versa."""
        sm = StateMachine.get_instance()
        all_states = sm.get_all_states()
        missing = set(all_states) - set(_STATE_ANNOTATIONS)
        assert not missing, f"States missing annotations: {missing}"
        extra = set(_STATE_ANNOTATIONS) - set(all_states)
        assert not extra, f"Annotation keys not present in state machine: {extra}"

    def test_actor_annotations_in_state_reference(self) -> None:
        """State reference output includes actor annotations."""
        sm = StateMachine.get_instance()
        result = _format_state_reference(sm)
        assert "[actor: pathologist]" in result
        assert "[actor: lab tech" in result
        assert "held — waiting for external" in result

    def test_group_annotations_for_ihc_bench(self) -> None:
        """IHC bench states are annotated with group: IHC bench."""
        sm = StateMachine.get_instance()
        result = _format_state_reference(sm)
        for state_id in ("IHC_STAINING", "IHC_QC", "IHC_SCORING"):
            # Find the line containing this state
            state_lines = [line for line in result.splitlines() if state_id in line]
            assert state_lines, f"State {state_id} not in reference"
            assert "group: IHC bench" in state_lines[0], (
                f"{state_id} line missing 'group: IHC bench'"
            )

    def test_combined_actor_and_group_suffix_format(self) -> None:
        """States with both actor and group use semicolon-separated suffix."""
        sm = StateMachine.get_instance()
        result = _format_state_reference(sm)
        ihc_lines = [line for line in result.splitlines() if "IHC_STAINING" in line]
        assert ihc_lines, "IHC_STAINING not found in state reference"
        assert "[actor: lab tech; group: IHC bench]" in ihc_lines[0]

    def test_pathologist_states_annotated(self) -> None:
        """States requiring pathologist action are annotated as such."""
        pathologist_states = {
            k for k, v in _STATE_ANNOTATIONS.items() if v.get("actor") == "pathologist"
        }
        expected = {"PATHOLOGIST_HE_REVIEW", "PATHOLOGIST_SIGNOUT", "SUGGEST_FISH_REFLEX"}
        assert expected == pathologist_states

    def test_held_states_annotated(self) -> None:
        """Hold/wait states are annotated as 'held'."""
        held_states = {k for k, v in _STATE_ANNOTATIONS.items() if "held" in v.get("actor", "")}
        expected = {"MISSING_INFO_HOLD", "FISH_SEND_OUT", "RESULTING_HOLD"}
        assert expected == held_states


# --- Order Sorting ---


class TestOrderSorting:
    """Tests that orders are sorted by created_at in the prompt."""

    def test_orders_sorted_by_created_at(self) -> None:
        """Orders appear in created_at ascending order in the prompt."""
        db_state = DatabaseStateSnapshot(
            orders=(
                {
                    "order_id": "ORD-C",
                    "current_state": "ACCEPTED",
                    "specimen_type": "biopsy",
                    "anatomic_site": "breast",
                    "priority": "routine",
                    "flags": [],
                    "created_at": "2025-01-15T09:00:00Z",
                },
                {
                    "order_id": "ORD-A",
                    "current_state": "ACCEPTED",
                    "specimen_type": "biopsy",
                    "anatomic_site": "breast",
                    "priority": "rush",
                    "flags": [],
                    "created_at": "2025-01-13T08:00:00Z",
                },
                {
                    "order_id": "ORD-B",
                    "current_state": "ACCEPTED",
                    "specimen_type": "biopsy",
                    "anatomic_site": "breast",
                    "priority": "routine",
                    "flags": [],
                    "created_at": "2025-01-14T10:00:00Z",
                },
            ),
            slides=(),
        )
        prompt = render_query_prompt_from_parts(
            database_state=db_state,
            query="Which orders first?",
            answer_type="order_list",
        )
        orders_section = prompt.split("### Orders")[1].split("### Slides")[0].strip()
        parsed = json.loads(orders_section)
        assert [o["order_id"] for o in parsed] == ["ORD-A", "ORD-B", "ORD-C"]

    def test_orders_without_created_at_sort_first(self) -> None:
        """Orders missing created_at sort to the beginning (empty string)."""
        db_state = DatabaseStateSnapshot(
            orders=(
                {
                    "order_id": "ORD-2",
                    "current_state": "ACCEPTED",
                    "specimen_type": "biopsy",
                    "anatomic_site": "breast",
                    "priority": "routine",
                    "flags": [],
                    "created_at": "2025-01-15T08:00:00Z",
                },
                {
                    "order_id": "ORD-1",
                    "current_state": "ACCEPTED",
                    "specimen_type": "biopsy",
                    "anatomic_site": "breast",
                    "priority": "routine",
                    "flags": [],
                },
            ),
            slides=(),
        )
        prompt = render_query_prompt_from_parts(
            database_state=db_state,
            query="What orders?",
            answer_type="order_list",
        )
        orders_section = prompt.split("### Orders")[1].split("### Slides")[0].strip()
        parsed = json.loads(orders_section)
        assert parsed[0]["order_id"] == "ORD-1"


# --- Answer Type Instructions ---


class TestAnswerTypeInstructions:
    """Tests for answer-type-specific instructions."""

    def test_order_list_with_rag_context_sorts_orders(self) -> None:
        """Orders are sorted by created_at even when rag_context is provided."""
        from src.rag.retriever import RetrievalResult

        db_state = DatabaseStateSnapshot(
            orders=(
                {
                    "order_id": "ORD-B",
                    "current_state": "ACCEPTED",
                    "specimen_type": "biopsy",
                    "anatomic_site": "breast",
                    "priority": "routine",
                    "flags": [],
                    "created_at": "2025-01-15T09:00:00Z",
                },
                {
                    "order_id": "ORD-A",
                    "current_state": "ACCEPTED",
                    "specimen_type": "biopsy",
                    "anatomic_site": "breast",
                    "priority": "rush",
                    "flags": [],
                    "created_at": "2025-01-14T08:00:00Z",
                },
            ),
            slides=(),
        )
        rag_chunks = [
            RetrievalResult(
                text="Sample workflow context",
                source_file="sop.md",
                section_title="Workflow",
                doc_type="sop",
                similarity_score=0.9,
            ),
        ]
        prompt = render_query_prompt_from_parts(
            database_state=db_state,
            query="Which orders?",
            answer_type="order_list",
            rag_context=rag_chunks,
        )
        orders_section = prompt.split("### Orders")[1].split("### Slides")[0].strip()
        parsed = json.loads(orders_section)
        assert [o["order_id"] for o in parsed] == ["ORD-A", "ORD-B"]
        # Flag definitions still present in RAG path
        assert "Flag Definitions" in prompt

    def test_prioritized_list_has_ranking_example(self) -> None:
        """prioritized_list prompt includes a worked ranking example."""
        db_state = DatabaseStateSnapshot(
            orders=(
                {
                    "order_id": "ORD-1",
                    "current_state": "ACCEPTED",
                    "specimen_type": "biopsy",
                    "anatomic_site": "breast",
                    "priority": "rush",
                    "flags": [],
                    "created_at": "2025-01-15T08:00:00Z",
                },
            ),
            slides=(),
        )
        prompt = render_query_prompt_from_parts(
            database_state=db_state,
            query="Which first?",
            answer_type="prioritized_list",
        )
        assert "Correct ranking: B, C, A, D" in prompt
        assert "Jan 14 is OLDER than Jan 15" in prompt

    def test_order_list_has_scan_instructions(self) -> None:
        """order_list prompt includes instructions to scan all orders."""
        db_state = DatabaseStateSnapshot(
            orders=(
                {
                    "order_id": "ORD-1",
                    "current_state": "ACCEPTED",
                    "specimen_type": "biopsy",
                    "anatomic_site": "breast",
                    "priority": "routine",
                    "flags": [],
                    "created_at": "2025-01-15T08:00:00Z",
                },
            ),
            slides=(),
        )
        prompt = render_query_prompt_from_parts(
            database_state=db_state,
            query="What orders match?",
            answer_type="order_list",
        )
        assert "Scan EVERY order" in prompt
        assert "not just the most obvious one" in prompt

    def test_explanation_has_no_extra_instructions(self) -> None:
        """explanation answer_type has no special instructions."""
        db_state = DatabaseStateSnapshot(
            orders=(
                {
                    "order_id": "ORD-1",
                    "current_state": "ACCEPTED",
                    "specimen_type": "biopsy",
                    "anatomic_site": "breast",
                    "priority": "routine",
                    "flags": [],
                    "created_at": "2025-01-15T08:00:00Z",
                },
            ),
            slides=(),
        )
        prompt = render_query_prompt_from_parts(
            database_state=db_state,
            query="What does this mean?",
            answer_type="explanation",
        )
        assert "Scan EVERY order" not in prompt
        assert "Ranking rules" not in prompt


# --- Caching ---


class TestCaching:
    """Tests that static reference functions are cached."""

    def test_state_reference_is_cached(self) -> None:
        """Repeated calls return the same object (not just equal value)."""
        sm = StateMachine.get_instance()
        result1 = _format_state_reference(sm)
        result2 = _format_state_reference(sm)
        assert result1 is result2

    def test_flag_definitions_is_cached(self) -> None:
        """Repeated calls return the same object."""
        sm = StateMachine.get_instance()
        result1 = _format_flag_definitions(sm)
        result2 = _format_flag_definitions(sm)
        assert result1 is result2
