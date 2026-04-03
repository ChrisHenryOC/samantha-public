"""Data models for the live server routing system.

Defines RoutingResult (returned by RoutingService.process_event) for the
live routing loop. These are separate from the evaluation models in
src/workflow/models.py — the live system has no ground truth to compare against.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RoutingResult:
    """Result of processing a workflow event through the routing service.

    On success (applied=True), the order has transitioned to ``to_state``.
    On invalid transition (applied=False, transition_valid=False), the order
    state is unchanged and the decision is flagged for human review.
    On model error (error is set), no transition was attempted.
    """

    decision_id: str
    order_id: str
    from_state: str
    to_state: str
    applied_rules: tuple[str, ...]
    flags: tuple[str, ...]
    reasoning: str | None
    transition_valid: bool
    applied: bool
    latency_ms: float
    error: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision_id, str) or not self.decision_id:
            raise ValueError("decision_id must be a non-empty string")
        if not isinstance(self.order_id, str) or not self.order_id:
            raise ValueError("order_id must be a non-empty string")
        if not isinstance(self.from_state, str) or not self.from_state:
            raise ValueError("from_state must be a non-empty string")
        if not isinstance(self.applied_rules, tuple):
            raise TypeError(f"applied_rules must be tuple, got {type(self.applied_rules).__name__}")
        if not isinstance(self.flags, tuple):
            raise TypeError(f"flags must be tuple, got {type(self.flags).__name__}")
        # Cross-field: to_state must be non-empty when there is no error.
        if self.error is None and not self.to_state:
            raise ValueError("to_state must be non-empty when error is None")
