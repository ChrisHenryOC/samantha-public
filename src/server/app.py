"""FastAPI application factory for the live routing server."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from src.models.base import ModelAdapter
from src.models.config import ModelConfig
from src.prediction.engine import PredictionEngine
from src.server.chat_service import ChatService
from src.server.config import ServerConfig, load_server_config
from src.server.event_bus import EventBus
from src.server.routes import chat, events, health, orders, static, updates
from src.server.routing_service import RoutingService
from src.workflow.database import Database
from src.workflow.state_machine import StateMachine


def _build_adapter(server_config: ServerConfig) -> ModelAdapter:
    """Build the appropriate model adapter based on config."""
    if server_config.provider == "openrouter":
        from src.models.openrouter_adapter import OpenRouterAdapter

        api_key_path = Path("notes/openrouter-api-key.txt")
        if api_key_path.exists():
            api_key = api_key_path.read_text().strip()
            os.environ["OPENROUTER_API_KEY"] = api_key

        model_config = ModelConfig(
            name="live-server",
            provider="openrouter",
            model_id=server_config.model_id,
            temperature=0.0,
            max_tokens=1024,
            token_limit=8192,
        )
        return OpenRouterAdapter(model_config)
    else:
        from src.models.llamacpp_adapter import LlamaCppAdapter

        model_config = ModelConfig(
            name="live-server",
            provider="llamacpp",
            model_id=server_config.model_id,
            temperature=0.0,
            max_tokens=1024,
            token_limit=8192,
        )
        return LlamaCppAdapter(model_config, base_url=server_config.llamacpp_url)


def create_app(
    config: ServerConfig | None = None,
    config_path: Path | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    The ``config`` parameter allows tests to inject configuration
    directly. In production, config is loaded from YAML.
    """
    server_config = config or load_server_config(config_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        app.state.config = server_config

        event_bus = EventBus()
        app.state.event_bus = event_bus

        db = Database(server_config.db_path, check_same_thread=False)
        db.__enter__()
        adapter = None
        try:
            db.init_db()
            app.state.db = db

            adapter = _build_adapter(server_config)
            engine = PredictionEngine(adapter)
            state_machine = StateMachine.get_instance()
            routing_service = RoutingService(
                db,
                engine,
                state_machine,
                event_bus=event_bus,
                prompt_extras=server_config.prompt_extras,
            )

            app.state.adapter = adapter
            app.state.routing_service = routing_service
            app.state.chat_service = ChatService(adapter, db, routing_service)

            yield
        finally:
            if adapter is not None:
                adapter.close()
            db.__exit__(None, None, None)

    app = FastAPI(
        title="Samantha — Lab Workflow Routing",
        description="Live routing service for breast cancer laboratory workflow",
        lifespan=lifespan,
    )

    # Register routes
    app.include_router(health.router)
    app.include_router(events.router)
    app.include_router(orders.router)
    app.include_router(chat.router)
    app.include_router(updates.router)
    app.include_router(static.router)

    return app


def create_test_app(
    db: Database,
    routing_service: RoutingService,
    server_config: ServerConfig,
    chat_service: ChatService | None = None,
    event_bus: EventBus | None = None,
) -> FastAPI:
    """Create a FastAPI app with pre-built dependencies for testing.

    Skips the lifespan (no llama-server connection needed) and injects
    dependencies directly into app.state.
    """
    app = FastAPI(title="Samantha Test")

    app.state.config = server_config
    app.state.db = db
    app.state.routing_service = routing_service
    app.state.event_bus = event_bus or EventBus()
    if chat_service is not None:
        app.state.chat_service = chat_service

    app.include_router(health.router)
    app.include_router(events.router)
    app.include_router(orders.router)
    app.include_router(chat.router)
    app.include_router(updates.router)

    return app
