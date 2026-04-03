"""Graph connectivity tests for the workflow state machine.

Verifies BFS reachability: every non-terminal state is reachable from
ACCESSIONING, and every non-terminal state can reach a terminal state.
"""

from __future__ import annotations

from collections import deque
from typing import Any

import pytest


@pytest.fixture()
def adjacency(workflow_data: dict[str, Any]) -> dict[str, set[str]]:
    """Build forward adjacency list from transitions."""
    adj: dict[str, set[str]] = {}
    for t in workflow_data["transitions"]:
        adj.setdefault(t["from"], set()).add(t["to"])
    return adj


@pytest.fixture()
def state_ids(workflow_data: dict[str, Any]) -> set[str]:
    return {s["id"] for s in workflow_data["states"]}


@pytest.fixture()
def terminal_ids(workflow_data: dict[str, Any]) -> set[str]:
    return set(workflow_data["terminal_states"])


def _bfs_reachable(start: str, adjacency: dict[str, set[str]]) -> set[str]:
    """Return all states reachable from start via BFS."""
    visited: set[str] = set()
    queue: deque[str] = deque([start])
    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        for neighbor in adjacency.get(current, set()):
            if neighbor not in visited:
                queue.append(neighbor)
    return visited


class TestForwardReachability:
    def test_all_non_terminal_reachable_from_accessioning(
        self, adjacency: dict[str, set[str]], state_ids: set[str], terminal_ids: set[str]
    ) -> None:
        reachable = _bfs_reachable("ACCESSIONING", adjacency)
        non_terminal = state_ids - terminal_ids
        unreachable = non_terminal - reachable
        assert unreachable == set(), f"States not reachable from ACCESSIONING: {unreachable}"

    def test_all_terminal_reachable_from_accessioning(
        self, adjacency: dict[str, set[str]], terminal_ids: set[str]
    ) -> None:
        reachable = _bfs_reachable("ACCESSIONING", adjacency)
        unreachable = terminal_ids - reachable
        assert unreachable == set(), (
            f"Terminal states not reachable from ACCESSIONING: {unreachable}"
        )


class TestTerminalReachability:
    def test_every_non_terminal_can_reach_a_terminal(
        self, adjacency: dict[str, set[str]], state_ids: set[str], terminal_ids: set[str]
    ) -> None:
        non_terminal = state_ids - terminal_ids
        for state in non_terminal:
            reachable = _bfs_reachable(state, adjacency)
            reached_terminal = reachable & terminal_ids
            assert len(reached_terminal) > 0, f"State {state} cannot reach any terminal state"


class TestNoUnreachableSubgraphs:
    def test_no_unreachable_subgraphs(
        self, adjacency: dict[str, set[str]], state_ids: set[str]
    ) -> None:
        """All states (except bypassed) should be reachable from ACCESSIONING."""
        reachable = _bfs_reachable("ACCESSIONING", adjacency)
        unreachable = state_ids - reachable
        assert unreachable == set(), f"Unreachable subgraph: {unreachable}"


class TestSelfLoops:
    def test_self_loops_present(self, adjacency: dict[str, set[str]]) -> None:
        """At least SP-002 self-loops and IHC self-loops exist."""
        self_loop_states = {s for s, targets in adjacency.items() if s in targets}
        expected_self_loops = {
            "SAMPLE_PREP_PROCESSING",
            "SAMPLE_PREP_EMBEDDING",
            "SAMPLE_PREP_SECTIONING",
            "IHC_STAINING",
            "IHC_QC",
        }
        assert expected_self_loops.issubset(self_loop_states), (
            f"Missing self-loops: {expected_self_loops - self_loop_states}"
        )
