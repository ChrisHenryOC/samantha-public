"""Routing service: live event processing with LLM-based next-state prediction.

Ties PredictionEngine + Database + StateMachine together for live operations.
Receives a workflow event, predicts the next state via the LLM, validates
the transition, updates the database, and persists an audit trail.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from src.prediction.engine import PredictionEngine
from src.server.models import RoutingResult
from src.workflow.database import Database
from src.workflow.models import VALID_FLAGS, Event
from src.workflow.state_machine import StateMachine

if TYPE_CHECKING:
    from src.rag.retriever import RagRetriever
    from src.server.event_bus import EventBus

logger = logging.getLogger(__name__)


class RoutingService:
    """Orchestrates live workflow routing: event → predict → validate → apply.

    Args:
        db: Open Database connection for order/event persistence.
        engine: PredictionEngine wrapping the model adapter.
        state_machine: StateMachine for transition validation.
        rag_retriever: Optional RAG retriever for context augmentation.
    """

    def __init__(
        self,
        db: Database,
        engine: PredictionEngine,
        state_machine: StateMachine,
        rag_retriever: RagRetriever | None = None,
        event_bus: EventBus | None = None,
        prompt_extras: frozenset[str] = frozenset(),
    ) -> None:
        self._db = db
        self._engine = engine
        self._state_machine = state_machine
        self._rag_retriever = rag_retriever
        self._event_bus = event_bus
        self._prompt_extras = prompt_extras

    def process_event(self, order_id: str, event: Event) -> RoutingResult:
        """Process a workflow event and route the order to its next state.

        1. Load the order and its slides from the database.
        2. Reject events for orders in terminal states.
        3. Call the prediction engine to determine the next state.
        4. Validate the predicted transition against the state machine.
        5. If valid, update the order state, insert the event, and persist
           the routing decision.
        6. If invalid, persist the decision with applied=False.
        7. Return a RoutingResult with the decision details.

        All DB writes within a single event are atomic (single commit).

        Raises:
            ValueError: If the order_id does not exist in the database
                or the order is in a terminal state.
        """
        decision_id = str(uuid.uuid4())
        now = datetime.now()

        # 1. Load order + slides
        order = self._db.get_order(order_id)
        if order is None:
            raise ValueError(f"Order not found: {order_id}")

        from_state = order.current_state

        # 2. Reject events for terminal orders
        if self._state_machine.is_terminal_state(from_state):
            raise ValueError(
                f"Order {order_id} is in terminal state {from_state}; cannot process further events"
            )

        slides = self._db.get_slides_for_order(order_id)

        # 3. Predict next state
        prediction = self._engine.predict_routing(
            order,
            slides,
            event,
            rag_retriever=self._rag_retriever,
            prompt_extras=self._prompt_extras,
        )

        # Handle model error
        if prediction.error is not None:
            logger.warning("Model error for order %s: %s", order_id, prediction.error)
            self._db.insert_event(event, _commit=False)
            self._db.insert_routing_decision(
                decision_id=decision_id,
                event_id=event.event_id,
                order_id=order_id,
                model_id=self._engine.model_id,
                from_state=from_state,
                to_state="",
                applied_rules=[],
                flags=[],
                reasoning=None,
                transition_valid=False,
                applied=False,
                latency_ms=prediction.raw_response.latency_ms,
                created_at=now,
                _commit=False,
            )
            self._db.commit()
            return RoutingResult(
                decision_id=decision_id,
                order_id=order_id,
                from_state=from_state,
                to_state="",
                applied_rules=(),
                flags=(),
                reasoning=None,
                transition_valid=False,
                applied=False,
                latency_ms=prediction.raw_response.latency_ms,
                error=prediction.error,
            )

        # Handle missing next_state (prediction succeeded but no state)
        if prediction.next_state is None:
            error_msg = (
                f"prediction_missing_state: model returned no next_state for order {order_id}"
            )
            logger.warning(error_msg)
            self._db.insert_event(event, _commit=False)
            self._db.insert_routing_decision(
                decision_id=decision_id,
                event_id=event.event_id,
                order_id=order_id,
                model_id=self._engine.model_id,
                from_state=from_state,
                to_state="",
                applied_rules=[],
                flags=[],
                reasoning=prediction.reasoning,
                transition_valid=False,
                applied=False,
                latency_ms=prediction.raw_response.latency_ms,
                created_at=now,
                _commit=False,
            )
            self._db.commit()
            return RoutingResult(
                decision_id=decision_id,
                order_id=order_id,
                from_state=from_state,
                to_state="",
                applied_rules=(),
                flags=(),
                reasoning=prediction.reasoning,
                transition_valid=False,
                applied=False,
                latency_ms=prediction.raw_response.latency_ms,
                error=error_msg,
            )

        to_state = prediction.next_state
        applied_rules = list(prediction.applied_rules)
        # Filter predicted flags to only valid flag IDs
        predicted_flags = [f for f in prediction.flags if f in VALID_FLAGS]
        reasoning = prediction.reasoning
        latency_ms = prediction.raw_response.latency_ms

        # 4. Validate transition
        transition_valid = self._state_machine.is_valid_transition(from_state, to_state)

        # 5/6. Apply or flag for review (atomic commit)
        if transition_valid:
            # Merge predicted flags with existing order flags (union, sorted)
            merged_flags = sorted(set(order.flags) | set(predicted_flags))
            self._db.insert_event(event, _commit=False)
            self._db.update_order_state(order_id, to_state, merged_flags, now, _commit=False)
            applied = True
        else:
            self._db.insert_event(event, _commit=False)
            merged_flags = sorted(predicted_flags)
            applied = False
            logger.warning(
                "Invalid transition %s -> %s for order %s (model predicted); "
                "decision %s flagged for human review",
                from_state,
                to_state,
                order_id,
                decision_id,
            )

        # Persist routing decision and commit all writes atomically
        self._db.insert_routing_decision(
            decision_id=decision_id,
            event_id=event.event_id,
            order_id=order_id,
            model_id=self._engine.model_id,
            from_state=from_state,
            to_state=to_state,
            applied_rules=applied_rules,
            flags=merged_flags,
            reasoning=reasoning,
            transition_valid=transition_valid,
            applied=applied,
            latency_ms=latency_ms,
            created_at=now,
            _commit=False,
        )
        self._db.commit()

        return RoutingResult(
            decision_id=decision_id,
            order_id=order_id,
            from_state=from_state,
            to_state=to_state,
            applied_rules=tuple(applied_rules),
            flags=tuple(merged_flags),
            reasoning=reasoning,
            transition_valid=transition_valid,
            applied=applied,
            latency_ms=latency_ms,
        )
