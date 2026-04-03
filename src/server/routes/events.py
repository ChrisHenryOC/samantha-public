"""Event ingestion endpoint."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from src.workflow.models import Event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


class EventRequest(BaseModel):
    """Request body for submitting a workflow event."""

    order_id: str
    event_type: str
    event_data: dict[str, Any] = Field(default_factory=dict)


@router.post("/events")
async def submit_event(request: Request, body: EventRequest) -> dict[str, Any]:
    """Submit a workflow event to advance an order.

    Generates event_id and step_number automatically, delegates to
    RoutingService.process_event(), and returns the routing result.
    """
    db = request.app.state.db
    routing_service = request.app.state.routing_service

    # Compute next step_number via MAX to avoid TOCTOU race
    step_number = db.get_max_step_number(body.order_id) + 1

    event = Event(
        event_id=str(uuid.uuid4()),
        order_id=body.order_id,
        step_number=step_number,
        event_type=body.event_type,
        event_data=body.event_data,
        created_at=datetime.now(),
    )

    try:
        result = routing_service.process_event(body.order_id, event)
    except ValueError as exc:
        error_msg = str(exc)
        if "terminal state" in error_msg:
            raise HTTPException(status_code=409, detail=error_msg) from exc
        raise HTTPException(status_code=404, detail=error_msg) from exc
    except Exception as exc:
        logger.error("Event processing failed: %s: %s", type(exc).__name__, exc)
        raise HTTPException(status_code=500, detail="Internal error processing event") from exc

    # Publish routing decision to event bus for SSE clients (fire-and-forget)
    event_bus = request.app.state.event_bus
    if event_bus is not None:
        try:
            await event_bus.publish(
                {
                    "type": "routing_decision",
                    "order_id": result.order_id,
                    "from_state": result.from_state,
                    "to_state": result.to_state,
                    "applied_rules": list(result.applied_rules),
                    "applied": result.applied,
                    "timestamp": datetime.now().astimezone().isoformat(),
                }
            )
        except Exception as exc:
            logger.warning("Failed to publish SSE event: %s", exc)

    return {
        "decision_id": result.decision_id,
        "order_id": result.order_id,
        "from_state": result.from_state,
        "to_state": result.to_state,
        "applied_rules": list(result.applied_rules),
        "flags": list(result.flags),
        "reasoning": result.reasoning,
        "transition_valid": result.transition_valid,
        "applied": result.applied,
        "latency_ms": result.latency_ms,
        "error": result.error,
    }
