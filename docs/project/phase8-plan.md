# Phase 8: Live Routing Loop & Chat Interface

## Context

The evaluation POC (Phases 1-7) proved that Qwen3 8B running locally via Ollama
can route breast cancer workflow at 94.1% accuracy, exceeding the cloud Opus
ceiling. The original project vision is a locally hosted chat interface for lab
personnel that routes work and abstracts workflow complexity. Phase 8 transitions
from offline evaluation to a live interactive system.

The existing codebase has strong reusable components:
`PredictionEngine.predict_routing()`, `Database` (already has write methods like
`update_order_state()`), `StateMachine`, `OllamaAdapter`, `RagRetriever`, and
tool definitions. The main gaps are: no web framework, no live orchestration
layer, no chat interface, and `ToolExecutor` is bound to in-memory snapshots
rather than a live DB.

## Architecture

```text
Browser (static HTML/JS)
    |
    |--- POST /api/events             (submit workflow events)
    |--- GET  /api/orders              (list orders, filter by role/state)
    |--- GET  /api/orders/{id}         (order detail + events)
    |--- GET  /api/orders/{id}/slides  (slides for order)
    |--- WS   /ws/chat                 (streaming chat with LLM)
    |--- GET  /health                  (Ollama reachability)
    |
FastAPI (uvicorn)
    |
    |--- RoutingService          (event -> predict -> validate -> apply)
    |--- ChatService             (multi-turn tool-use conversation, streaming)
    |--- LiveToolExecutor        (queries live DB)
    |
    +--- PredictionEngine (existing src/prediction/engine.py)
    +--- StateMachine (existing src/workflow/state_machine.py)
    +--- Database (existing src/workflow/database.py)
    +--- OllamaAdapter (existing src/models/ollama_adapter.py)
    +--- RagRetriever (existing src/rag/retriever.py)
```

All new code goes in `src/server/`. The evaluation harness in `src/evaluation/`
is not touched.

## Design Decisions

- **FastAPI + uvicorn** for the web layer (async, WebSocket support, OpenAPI
  docs)
- **WebSocket** for chat (bidirectional turn-based conversation with token
  streaming)
- **Single HTML page** with vanilla JS for the frontend (no build system, no
  npm)
- **Hardcoded role selection** via dropdown (accessioner, histotech,
  pathologist, lab_manager) — no auth
- **Separate live DB** at `data/live.sqlite` (evaluation DBs untouched in
  `results/`)
- **Qwen3 8B** as the single model for the live system
- **Streaming responses** — OllamaAdapter gets a `chat_stream()` method that
  yields tokens; WebSocket forwards them to the browser so users see responses
  appear word-by-word

## Role-to-State Mapping

```python
ROLE_STATES = {
    "accessioner": {"ACCESSIONING", "MISSING_INFO_HOLD"},
    "histotech": {
        "ACCEPTED", "MISSING_INFO_PROCEED",
        "SAMPLE_PREP_PROCESSING", "SAMPLE_PREP_EMBEDDING",
        "SAMPLE_PREP_SECTIONING", "SAMPLE_PREP_QC",
        "HE_STAINING", "HE_QC", "IHC_STAINING", "IHC_QC",
    },
    "pathologist": {
        "PATHOLOGIST_HE_REVIEW", "IHC_SCORING",
        "SUGGEST_FISH_REFLEX", "RESULTING", "RESULTING_HOLD",
        "PATHOLOGIST_SIGNOUT",
    },
    "lab_manager": None,  # sees all
}
```

## Issues

Items are listed in implementation order. See the
[implementation todo](implementation-todo.md) for the full project tracker.

| # | Title | Blocked By |
|---|-------|------------|
| [GH-188](https://github.com/ChrisHenryOC/samantha/issues/188) | Routing service core | — |
| [GH-189](https://github.com/ChrisHenryOC/samantha/issues/189) | Live tool executor | — |
| [GH-190](https://github.com/ChrisHenryOC/samantha/issues/190) | FastAPI server and REST endpoints | GH-188, GH-189 |
| [GH-191](https://github.com/ChrisHenryOC/samantha/issues/191) | Order seeding and demo data | GH-190 |
| [GH-192](https://github.com/ChrisHenryOC/samantha/issues/192) | Chat service with streaming WebSocket | GH-189, GH-190 |
| [GH-193](https://github.com/ChrisHenryOC/samantha/issues/193) | Web frontend | GH-190, GH-192 |
| [GH-194](https://github.com/ChrisHenryOC/samantha/issues/194) | SSE updates, event bus, and launch script | GH-190, GH-192, GH-193 |

## Dependency Graph

```text
GH-188 (Routing Service) ──┐
                             ├── GH-190 (API Server) ──┬── GH-191 (Seed Data)
GH-189 (Live Executor)  ────┘                          │
                                                        └── GH-192 (Chat + Streaming)
                                                                │
                                                        GH-193 (Frontend) ──── GH-194 (SSE + Launch)
```

GH-188 and GH-189 can be implemented in parallel. Then GH-190. Then GH-191 and
GH-192 in parallel. Then GH-193. Then GH-194.

## What Is NOT In This Plan

- Authentication/authorization (role selected via dropdown, no login)
- Multiple concurrent models (single Qwen3 8B)
- Docker/production deployment (just uvicorn dev server)
- Order creation UI (orders seeded or created via API)
- Push notifications (SSE provides real-time updates, no alerting)

## Verification

After all issues are implemented:

1. `uv run pytest` — all existing + new tests pass
2. `./scripts/start_server.sh` — server starts, health endpoint returns OK
3. Open `http://localhost:8000` — see work queue populated with demo orders
4. Select "accessioner" role — see orders in ACCESSIONING state
5. Submit an event via chat ("mark grossing complete for ORD-001") or POST
   /api/events
6. Observe order moves to next state, work queue updates via SSE
7. Ask a question in chat ("why is ORD-003 on hold?") — see streaming response
   with tool-backed answer
