"""WebSocket chat endpoint with streaming responses."""

from __future__ import annotations

import contextlib
import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.server.roles import VALID_ROLES

router = APIRouter()

logger = logging.getLogger(__name__)

_MAX_MESSAGE_LENGTH = 4096


@router.websocket("/ws/chat")
async def chat_endpoint(websocket: WebSocket) -> None:
    """Interactive chat via WebSocket with streaming token delivery.

    Query params:
        role: User role (accessioner, histotech, pathologist, lab_manager).
              Defaults to lab_manager.

    Client sends: ``{"message": "..."}``
    Server streams: token, tool_status, done, or error frames.
    """
    role = websocket.query_params.get("role", "lab_manager")
    if role not in VALID_ROLES:
        await websocket.close(code=4003, reason=f"Invalid role: {role}")
        return

    await websocket.accept()
    session_id = str(uuid.uuid4())

    chat_service = websocket.app.state.chat_service

    try:
        while True:
            data = await websocket.receive_json()
            user_message = data.get("message", "")
            if not user_message:
                await websocket.send_json({"type": "error", "message": "Empty message"})
                continue
            if len(user_message) > _MAX_MESSAGE_LENGTH:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": f"Message too long (max {_MAX_MESSAGE_LENGTH} chars)",
                    }
                )
                continue

            for event in chat_service.handle_message_stream(session_id, user_message, role):
                await websocket.send_json(event)

    except WebSocketDisconnect:
        logger.debug("Chat session %s disconnected", session_id)
        chat_service.remove_session(session_id)
    except Exception as exc:
        logger.error(
            "Chat session %s error: %s: %s",
            session_id,
            type(exc).__name__,
            exc,
        )
        with contextlib.suppress(Exception):
            await websocket.send_json({"type": "error", "message": "Internal server error"})
        chat_service.remove_session(session_id)
