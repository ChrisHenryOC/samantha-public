"""Order query endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from src.server.live_executor import order_to_dict, slide_to_dict
from src.server.roles import ROLE_STATES, VALID_ROLES

router = APIRouter(prefix="/api")


@router.get("/orders")
async def list_orders(
    request: Request,
    role: str | None = Query(None, description="Filter by role"),
    state: str | None = Query(None, description="Filter by workflow state"),
    priority: str | None = Query(None, description="Filter by priority"),
) -> list[dict[str, Any]]:
    """List orders, optionally filtered by role, state, or priority.

    When ``role`` is provided, orders are filtered to states relevant
    to that role. An explicit ``state`` filter narrows further within
    the role's states.
    """
    db = request.app.state.db

    if role is not None and role not in VALID_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role '{role}'. Must be one of: {sorted(VALID_ROLES)}",
        )

    # If role has specific states and no explicit state filter, query each state
    if role is not None and state is None:
        allowed_states = ROLE_STATES[role]
        if allowed_states is not None:
            results: list[dict[str, Any]] = []
            for s in sorted(allowed_states):
                orders = db.list_orders(state=s, priority=priority)
                results.extend(order_to_dict(o) for o in orders)
            return results

    # If role + state, validate state is in role's allowed set
    if role is not None and state is not None:
        allowed_states = ROLE_STATES[role]
        if allowed_states is not None and state not in allowed_states:
            return []

    orders = db.list_orders(state=state, priority=priority)
    return [order_to_dict(o) for o in orders]


@router.get("/orders/{order_id}")
async def get_order(request: Request, order_id: str) -> dict[str, Any]:
    """Get full details for a specific order."""
    db = request.app.state.db
    order = db.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order not found: {order_id}")
    return order_to_dict(order)


@router.get("/orders/{order_id}/events")
async def get_order_events(request: Request, order_id: str) -> list[dict[str, Any]]:
    """Get event history for an order."""
    db = request.app.state.db
    order = db.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order not found: {order_id}")
    events = db.get_events_for_order(order_id)
    return [
        {
            "event_id": e.event_id,
            "order_id": e.order_id,
            "step_number": e.step_number,
            "event_type": e.event_type,
            "event_data": e.event_data,
            "created_at": e.created_at.isoformat(),
        }
        for e in events
    ]


@router.get("/orders/{order_id}/slides")
async def get_order_slides(request: Request, order_id: str) -> list[dict[str, Any]]:
    """Get all slides for an order."""
    db = request.app.state.db
    order = db.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order not found: {order_id}")
    slides = db.get_slides_for_order(order_id)
    return [slide_to_dict(s) for s in slides]
