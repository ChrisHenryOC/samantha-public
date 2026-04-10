# Phase 8: Live System Documentation

## Overview

Phase 8 transitions the Samantha project from an offline evaluation harness
to a live interactive system. Lab personnel can view their work queues, chat
with an LLM assistant to query order state, and submit workflow events
through a web browser.

## How to Run

### Prerequisites

- **Ollama** must be running locally (`ollama serve`)
- **Qwen3 8B** model must be available (the start script pulls it automatically
  if missing)

### Starting the Server

```bash
./scripts/start_server.sh
```

The launch script:

1. Checks Ollama is running at `http://localhost:11434`
2. Verifies Qwen3 8B is available (pulls if missing)
3. Seeds demo data if `data/live.sqlite` does not exist
4. Starts the FastAPI server via uvicorn at `http://localhost:8000`

Open `http://localhost:8000` in your browser to access the UI.

### Stopping the Server

Press `Ctrl+C` in the terminal where the server is running. The SQLite WAL
files (`data/live.sqlite-shm`, `data/live.sqlite-wal`) are cleaned up
automatically on graceful shutdown.

### Resetting Test Data

To reset the database to a clean seeded state:

```bash
# 1. Stop the server (Ctrl+C)

# 2. Delete the database and WAL files
rm -f data/live.sqlite data/live.sqlite-shm data/live.sqlite-wal

# 3. Restart the server (auto-seeds on missing DB)
./scripts/start_server.sh
```

### Reseeding Without Deleting

The seed script is idempotent — it checks for existing seed orders
(`scenario_id = "seed"`) and skips if they already exist. To force a full
reseed, delete the database first (see above).

To run seeding manually without starting the server:

```bash
./scripts/seed_demo_data.sh
```

Or equivalently:

```bash
uv run python -m src.server.seed
```

This creates 30 demo orders covering all 24 workflow states and all 5 flags.

## Architecture

```text
Browser (static HTML/JS)
    |
    |--- POST /api/events             (submit workflow events)
    |--- GET  /api/orders              (list orders, filter by role/state)
    |--- GET  /api/orders/{id}         (order detail)
    |--- GET  /api/orders/{id}/events  (event history)
    |--- GET  /api/orders/{id}/slides  (slides for order)
    |--- WS   /ws/chat                 (streaming chat with LLM)
    |--- GET  /sse/updates             (real-time state change notifications)
    |--- GET  /health                  (Ollama reachability)
    |
FastAPI (uvicorn)
    |
    |--- RoutingService          (event -> predict -> validate -> apply)
    |--- ChatService             (multi-turn tool-use conversation, streaming)
    |--- LiveToolExecutor        (queries live DB)
    |--- EventBus                (async pub/sub for SSE updates)
    |
    +--- PredictionEngine (existing src/prediction/engine.py)
    +--- StateMachine (existing src/workflow/state_machine.py)
    +--- Database (existing src/workflow/database.py)
    +--- OllamaAdapter (existing src/models/ollama_adapter.py)
    +--- RagRetriever (existing src/rag/retriever.py)
```

## API Reference

### POST /api/events

Submit a workflow event to advance an order.

```json
{
    "order_id": "ORD-001",
    "event_type": "grossing_complete",
    "event_data": {"tissue_adequate": true, "sections_taken": 4}
}
```

Returns routing result with `applied`, `to_state`, `applied_rules`, `reasoning`.

### GET /api/orders

Query params: `role`, `state`, `priority`.

Role values: `accessioner`, `histotech`, `pathologist`, `lab_manager`.

### GET /api/orders/{order_id}

Full order detail.

### GET /api/orders/{order_id}/events

Event history ordered by step number.

### GET /api/orders/{order_id}/slides

All slides for the order.

### WS /ws/chat

WebSocket chat with streaming responses. Query param: `role`.

Protocol:

```text
Client sends: {"message": "Which orders need my attention?"}
Server streams:
  {"type": "token", "content": "You"}
  {"type": "token", "content": " have"}
  {"type": "tool_status", "tool": "list_orders", "status": "executing"}
  {"type": "tool_status", "tool": "list_orders", "status": "complete"}
  {"type": "token", "content": " 3 orders..."}
  {"type": "done", "session_id": "...", "latency_ms": 2340}
```

### GET /sse/updates

Server-Sent Events stream of routing decisions. The frontend auto-refreshes
the work queue when a `routing_decision` event arrives.

### GET /health

Returns model and Ollama status.

## Role-Based Work Queues

| Role | Workflow States |
|------|----------------|
| accessioner | ACCESSIONING, MISSING_INFO_HOLD, DO_NOT_PROCESS |
| histotech | ACCEPTED, MISSING_INFO_PROCEED, SAMPLE_PREP_PROCESSING, SAMPLE_PREP_EMBEDDING, SAMPLE_PREP_SECTIONING, SAMPLE_PREP_QC, HE_STAINING, HE_QC, IHC_STAINING, IHC_QC, REPORT_GENERATION |
| pathologist | PATHOLOGIST_HE_REVIEW, IHC_SCORING, SUGGEST_FISH_REFLEX, FISH_SEND_OUT, RESULTING, RESULTING_HOLD, PATHOLOGIST_SIGNOUT |
| lab_manager | All states |

## Chat Capabilities

The chat assistant can:

- Query orders, slides, workflow states, and flags from the live database
- Submit workflow events on behalf of the user ("mark grossing complete for
  ORD-001")
- Stream responses token-by-token for responsive UX
- Maintain per-session conversation history

The system prompt is role-aware, telling the LLM which workflow steps the
user handles.

## Configuration

Server configuration is in `config/server.yaml`:

```yaml
model_id: "qwen3:8b"
ollama_url: "http://localhost:11434"
db_path: "data/live.sqlite"
host: "127.0.0.1"
port: 8000
```

## What Is NOT Included

- Authentication/authorization (role selected via dropdown, no login)
- Multiple concurrent models (single Qwen3 8B)
- Docker/production deployment (just uvicorn dev server)
- Order creation UI (orders seeded or created via API)
- Response streaming for RAG-augmented routing (deferred)

## Related Documents

- [Phase 8 Plan](phase8-plan.md) — original design and issue breakdown
- [Implementation Todo](implementation-todo.md) — issue tracker
- [Architecture](../technical/architecture.md) — system design
