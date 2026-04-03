"""Red-team tests: graph invariants on the workflow state machine.

Tests structural properties of the transition graph: terminal states have
no outbound transitions, self-loops exist only at expected states, cycle
bounds, and bottleneck/entry-point properties.
"""

from __future__ import annotations

from collections import defaultdict

import pytest

from src.workflow.state_machine import StateMachine


@pytest.fixture(scope="module")
def sm() -> StateMachine:
    return StateMachine()


# ---------------------------------------------------------------------------
# Terminal state properties
# ---------------------------------------------------------------------------


class TestTerminalStateProperties:
    """Terminal states should be graph sinks (no outbound transitions)."""

    def test_terminal_states_have_no_outbound_transitions(self, sm: StateMachine) -> None:
        """No transition leaves a terminal state."""
        for state in sm.get_all_states():
            if sm.is_terminal_state(state):
                transitions = sm.get_valid_transitions(state)
                assert transitions == [], (
                    f"Terminal state {state} has outbound transitions: "
                    f"{[t.to_state for t in transitions]}"
                )

    def test_terminal_states_are_known_states(self, sm: StateMachine) -> None:
        """Every terminal state is a valid state in the state machine."""
        all_states = sm.get_all_states()
        for state in sm._terminal_states:
            assert state in all_states, f"Terminal state {state} not in all_states"

    def test_only_missing_info_hold_transitions_to_accessioning(self, sm: StateMachine) -> None:
        """Only MISSING_INFO_HOLD has a transition into ACCESSIONING."""
        sources_to_accessioning = set()
        for state in sm.get_all_states():
            for t in sm.get_valid_transitions(state):
                if t.to_state == "ACCESSIONING":
                    sources_to_accessioning.add(t.from_state)

        assert sources_to_accessioning == {"MISSING_INFO_HOLD"}, (
            f"Expected only MISSING_INFO_HOLD → ACCESSIONING, got: {sources_to_accessioning}"
        )


# ---------------------------------------------------------------------------
# Cycle properties
# ---------------------------------------------------------------------------


class TestCycleProperties:
    """Self-loops and short cycles only at known states."""

    def test_self_loops_only_at_expected_states(self, sm: StateMachine) -> None:
        """Self-loops (A→A) exist only at these 6 states."""
        expected_self_loops = {
            "SAMPLE_PREP_PROCESSING",
            "SAMPLE_PREP_EMBEDDING",
            "SAMPLE_PREP_SECTIONING",
            "IHC_STAINING",
            "IHC_QC",
            "RESULTING_HOLD",
        }
        actual_self_loops = set()
        for state in sm.get_all_states():
            if sm.is_valid_transition(state, state):
                actual_self_loops.add(state)

        assert actual_self_loops == expected_self_loops

    def test_two_state_cycles_at_known_pairs(self, sm: StateMachine) -> None:
        """Two-state cycles (A→B→A) only at known pairs."""
        expected_cycles = {
            frozenset({"MISSING_INFO_HOLD", "ACCESSIONING"}),
            frozenset({"HE_QC", "HE_STAINING"}),
            frozenset({"IHC_QC", "IHC_STAINING"}),
            frozenset({"RESULTING", "RESULTING_HOLD"}),
            frozenset({"SAMPLE_PREP_QC", "SAMPLE_PREP_SECTIONING"}),
        }
        actual_cycles: set[frozenset[str]] = set()
        for state in sm.get_all_states():
            for t in sm.get_valid_transitions(state):
                neighbor = t.to_state
                if neighbor != state and sm.is_valid_transition(neighbor, state):
                    actual_cycles.add(frozenset({state, neighbor}))

        assert actual_cycles == expected_cycles

    def test_longest_cycle_free_path_bounded(self, sm: StateMachine) -> None:
        """Longest cycle-free path through the graph is at most the total state count.

        Uses backtracking DFS from ACCESSIONING with O(V!) worst-case. Safe for
        the current sparse 26-state graph but would need a timeout guard (e.g.
        pytest-timeout) if the graph grows significantly.
        """
        # Build adjacency from transitions.
        adj: dict[str, list[str]] = defaultdict(list)
        for state in sm.get_all_states():
            for t in sm.get_valid_transitions(state):
                adj[state].append(t.to_state)

        max_length = 0

        def dfs(node: str, visited: set[str], depth: int) -> None:
            nonlocal max_length
            max_length = max(max_length, depth)
            for neighbor in adj[node]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    dfs(neighbor, visited, depth + 1)
                    visited.discard(neighbor)

        dfs("ACCESSIONING", {"ACCESSIONING"}, 0)
        state_count = len(sm.get_all_states())
        assert max_length <= state_count, (
            f"Longest cycle-free path is {max_length}, expected ≤ {state_count}"
        )


# ---------------------------------------------------------------------------
# Bottleneck / entry-point properties
# ---------------------------------------------------------------------------


class TestBottleneckProperties:
    """Convergence points and entry points in the graph."""

    def test_resulting_has_multiple_inbound_sources(self, sm: StateMachine) -> None:
        """RESULTING is a convergence point with ≥4 distinct inbound sources."""
        sources = set()
        for state in sm.get_all_states():
            for t in sm.get_valid_transitions(state):
                if t.to_state == "RESULTING":
                    sources.add(t.from_state)

        assert len(sources) >= 4, (
            f"RESULTING should have ≥4 inbound sources, got {len(sources)}: {sources}"
        )

    def test_accessioning_only_inbound_is_reentry(self, sm: StateMachine) -> None:
        """ACCESSIONING's only inbound source is MISSING_INFO_HOLD (re-entry).

        This confirms ACCESSIONING is the workflow entry point — no other
        state feeds into it except the re-evaluation loop.
        """
        inbound_sources: set[str] = set()
        for state in sm.get_all_states():
            for t in sm.get_valid_transitions(state):
                if t.to_state == "ACCESSIONING" and t.from_state != "ACCESSIONING":
                    inbound_sources.add(t.from_state)

        assert inbound_sources == {"MISSING_INFO_HOLD"}, (
            f"ACCESSIONING should only have inbound from MISSING_INFO_HOLD, got: {inbound_sources}"
        )
