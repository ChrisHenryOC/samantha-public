"""Simple in-process pub/sub event bus for real-time SSE updates.

The event bus broadcasts routing decisions to all connected SSE clients
so the frontend work queue can auto-refresh when order state changes.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

logger = logging.getLogger(__name__)


class EventBus:
    """Async pub/sub event bus using asyncio.Queue per subscriber."""

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[dict[str, Any]]] = []

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        """Register a new subscriber and return its queue."""
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        """Remove a subscriber's queue."""
        with contextlib.suppress(ValueError):
            self._subscribers.remove(q)

    async def publish(self, event: dict[str, Any]) -> None:
        """Broadcast an event to all subscribers (snapshot-safe)."""
        for q in list(self._subscribers):
            try:
                await q.put(event)
            except Exception as exc:
                logger.warning("Failed to publish to subscriber: %s", exc)

    @property
    def subscriber_count(self) -> int:
        """Number of active subscribers."""
        return len(self._subscribers)
