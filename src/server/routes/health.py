"""Health check endpoint."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    """Check server and model provider reachability."""
    config = request.app.state.config

    if config.provider == "openrouter":
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Accept": "application/json"},
                )
                resp.raise_for_status()
            provider_status = "connected"
        except Exception as exc:
            logger.debug(
                "OpenRouter health check failed: %s: %s",
                type(exc).__name__,
                exc,
            )
            provider_status = "unreachable"
    else:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{config.llamacpp_url}/health")
                resp.raise_for_status()
                body = resp.json()
                if body.get("status") != "ok":
                    raise ValueError(f"llama-server not ready: {body.get('status', 'unknown')}")
            provider_status = "connected"
        except Exception as exc:
            logger.debug(
                "llama-server health check failed: %s: %s",
                type(exc).__name__,
                exc,
            )
            provider_status = "unreachable"

    return {
        "status": "ok",
        "model": config.model_id,
        "provider": config.provider,
        "provider_status": provider_status,
    }
