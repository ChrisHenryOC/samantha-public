"""Server-Sent Events endpoint for real-time routing updates."""

from __future__ import annotations

import asyncio
import collections.abc
import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter()

logger = logging.getLogger(__name__)


@router.get("/sse/updates")
async def updates(request: Request) -> StreamingResponse:
    """Stream routing decision events to connected clients.

    The frontend connects via ``new EventSource("/sse/updates")`` and
    refreshes the work queue when a routing decision event arrives.
    """
    event_bus = request.app.state.event_bus
    queue = event_bus.subscribe()

    async def event_generator() -> collections.abc.AsyncIterator[str]:
        try:
            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    try:
                        yield f"data: {json.dumps(event)}\n\n"
                    except (TypeError, ValueError) as exc:
                        logger.warning("Failed to serialize SSE event: %s", exc)
                except TimeoutError:
                    # Send keepalive comment to prevent connection timeout
                    yield ": keepalive\n\n"
        finally:
            event_bus.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
