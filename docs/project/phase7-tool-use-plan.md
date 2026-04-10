# Phase 7: Tool-Use Query Evaluation

## Motivation

Routing evaluation is solved — Qwen3 8B at 94.1% exceeds cloud Opus
(91.6%). But query evaluation has a **structural ceiling**: Tier 4
(prioritized lists) scores **0% across all local models** because
context-stuffing forces models to mentally sort 15+ orders from a wall
of text. This architectural limitation cannot be overcome by prompt or
retrieval tuning.

The fix is to give models **callable tools** instead of dumping all data
into the prompt, then rerun the same 27 query scenarios to directly
compare context-stuffing vs tool-use. This is also the architecture
you'd use in production — no lab system would stuff its entire DB into a
prompt.

## Design Decisions

- **Mode, not track.** Tool-use is a new `--mode tool_use` option in the
  existing query runner, not a third evaluation track. Same 27 scenarios,
  same expected outputs, different method. Direct A/B comparison.
- **Native API tool-calling.** Use Ollama `/api/chat` with `tools` and
  OpenRouter `tools` parameter. Not simulated text-based tool calling.
- **In-memory execution.** Tools operate on the scenario's
  `DatabaseStateSnapshot` (in-memory dicts), not the live SQLite DB.
  Evaluation stays isolated.
- **Multi-turn loop.** The engine manages the conversation loop — send
  prompt with tool defs, model responds with tool calls, engine executes
  them, sends results back, repeat until the model produces a final text
  answer or max turns is hit.

## Phase 7a: Tool Definitions and Executor

### New file: `src/tools/definitions.py`

Define 5 tools as JSON Schema (the format Ollama and OpenRouter expect):

| Tool | Parameters | Purpose |
|------|-----------|---------|
| `list_orders` | `state?`, `priority?`, `has_flags?` | Filter/list orders — covers T1, T4, T5 queries |
| `get_order` | `order_id` (required) | Full order details — covers T2, T3 queries |
| `get_slides` | `order_id` (required) | Slides for an order |
| `get_state_info` | `state_id` (required) | Workflow state meaning, who acts on it |
| `get_flag_info` | `flag_id` (required) | Flag effect, how it's cleared |

Each tool definition uses the OpenAI function-calling schema (which both
Ollama and OpenRouter accept):

```json
{
    "type": "function",
    "function": {
        "name": "list_orders",
        "description": "List orders, optionally filtered by state, priority, or flag presence.",
        "parameters": {
            "type": "object",
            "properties": {
                "state": {"type": "string", "description": "Filter by current_state"},
                "priority": {"type": "string", "description": "Filter by priority (rush/routine)"},
                "has_flags": {"type": "boolean", "description": "If true, only orders with active flags"}
            },
            "required": []
        }
    }
}
```

Also define a `TOOL_REGISTRY: dict[str, ToolDefinition]` mapping tool
names to their schemas, and a helper `get_all_tool_definitions()` that
returns them in API-ready format.

### New file: `src/tools/executor.py`

`ToolExecutor` class that operates on a `DatabaseStateSnapshot`:

```python
class ToolExecutor:
    def __init__(self, database_state: DatabaseStateSnapshot) -> None:
        # Convert scenario's order/slide dicts into searchable in-memory structures

    def execute(self, tool_name: str, arguments: dict) -> str:
        # Dispatch to the right method, return JSON string result
        # Unknown tool -> return error message (don't raise)

    def list_orders(self, state=None, priority=None, has_flags=None) -> list[dict]
    def get_order(self, order_id: str) -> dict | None
    def get_slides(self, order_id: str) -> list[dict]
    def get_state_info(self, state_id: str) -> dict | None
    def get_flag_info(self, flag_id: str) -> dict | None
```

`get_state_info` and `get_flag_info` pull from
`StateMachine.get_instance()` — the same source the context-stuffing
prompt uses, but delivered on-demand instead of upfront.

`execute()` returns a JSON string (what gets sent back to the model as
the tool result). Errors return `{"error": "..."}` instead of raising.

### New file: `src/tools/__init__.py`

Empty init to make it a package.

**Related issue:** #176

---

## Phase 7b: Adapter Chat Interface

### Modify: `src/models/base.py`

Add data types for multi-turn chat:

```python
@dataclass(frozen=True)
class ChatMessage:
    role: str          # "system", "user", "assistant", "tool"
    content: str | None
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None  # For role="tool" responses

@dataclass(frozen=True)
class ToolCall:
    id: str
    function_name: str
    arguments: dict[str, Any]

@dataclass(frozen=True)
class ChatResponse:
    message: ChatMessage
    latency_ms: float | int
    input_tokens: int
    output_tokens: int
    cost_estimate_usd: float | None
    model_id: str
    error: str | None = None
    timed_out: bool = False
```

Add a default `chat()` method to `ModelAdapter`:

```python
def chat(
    self,
    messages: list[ChatMessage],
    tools: list[dict[str, Any]] | None = None,
) -> ChatResponse:
    """Multi-turn chat with optional tool definitions."""
    raise NotImplementedError(
        f"{self.provider}/{self.model_id} does not support chat()"
    )
```

This is a concrete method (not abstract) so existing adapters don't
break. Adapters override it to opt in.

### Modify: `src/models/ollama_adapter.py`

Implement `chat()` using Ollama's `/api/chat` endpoint (not
`/api/generate`):

- Payload format: `{"model": ..., "messages": [...], "tools": [...], "stream": false}`
- Parse `response.message.tool_calls` or `response.message.content`
- Same error handling pattern as `predict()` — connection errors,
  timeouts, HTTP errors return `ChatResponse` with error set

### Modify: `src/models/openrouter_adapter.py`

Implement `chat()` by adding `tools` and `tool_choice` to the existing
chat completions payload:

- Parse `choices[0].message.tool_calls` alongside `content`
- Existing `predict()` stays unchanged

**Related issue:** #177

---

## Phase 7c: Tool-Use Prediction Engine

### New file: `src/prediction/tool_use_prompt.py`

System prompt for tool-use mode. **No database state in the prompt** —
that's the whole point. The prompt:

1. Sets the role: "You are a laboratory information system assistant..."
2. Describes the available tools and when to use them
3. Presents the question
4. Specifies the answer format (same JSON schemas as context-stuffing)
5. Instructs the model to call tools to gather data before answering

### Modify: `src/prediction/engine.py`

Add `predict_query_with_tools()` to `PredictionEngine` that manages the
multi-turn conversation loop:

```text
1. Render system + user messages (no database state)
2. Loop (max 10 turns):
   a. Call adapter.chat(messages, tools)
   b. If response has tool_calls:
      - Execute each via ToolExecutor
      - Append tool results as messages
      - Continue loop
   c. If response has text content (final answer):
      - Parse JSON answer
      - Return result with tool call log
3. If max turns exceeded, return error
```

Define `ToolUseQueryResult` (frozen dataclass):

- `parsed_output: dict | None`
- `error: str | None`
- `tool_calls: tuple[ToolCallRecord, ...]` — full audit log
- `turns: int`
- `total_latency_ms: float` — sum across all turns
- `total_input_tokens: int`, `total_output_tokens: int`
- `model_id: str`

**Related issue:** #178

---

## Phase 7d: Tool-Use Query Harness

### New file: `src/evaluation/tool_use_harness.py`

`ToolUseQueryHarness` — structurally mirrors `QueryEvaluationHarness`
but uses the tool-use prediction path:

- Same `__init__` signature (models, settings, scenarios, db_path)
- Same `run_all()` orchestration (sequential/parallel, early-abort,
  dashboard)
- Different `_run_query_scenario()`:
  - Creates a `ToolExecutor` for the scenario's `database_state`
  - Calls `engine.predict_query_with_tools(scenario, executor, tool_defs)`
  - Validates the final answer with existing
    `validate_query_prediction()` — **same validation as context-stuffing**
  - Classifies failures with existing `classify_query_failure()`
  - Persists a `QueryDecision` to SQLite — tool-use metadata
    (`tool_calls` audit log, `turns`, per-turn token counts) is
    serialized into the existing `model_output` JSON column alongside
    the raw model response

The final answer validation is identical to context-stuffing mode, making
the A/B comparison apples-to-apples.

### New file: `src/evaluation/tool_use_metrics.py`

Extends standard query metrics with tool-use dimensions:

- Standard: `query_accuracy`, `accuracy_by_tier`, `accuracy_by_answer_type`,
  `mean_precision`, `mean_recall`, `mean_f1`, `scenario_reliability`
- Tool-use: `tool_calls_total`, `tool_calls_per_scenario_mean`,
  `turns_per_scenario_mean`, `max_turns_hit_count`,
  `most_used_tools: dict[str, int]`
- Infra: `latency_mean_ms`, `token_input_mean`, `token_output_mean`,
  `failure_counts`

### Modify: `src/evaluation/query_runner.py`

Add `tool_use` to `--mode` choices. When `mode == "tool_use"`:

- Use `ToolUseQueryHarness` instead of `QueryEvaluationHarness`
- Output to `results/query_tool_use/`
- Use tool-use reporter and metrics functions

**Related issue:** #179

---

## Phase 7e: Reporting and Analysis

### Modify: `src/evaluation/reporter.py`

Add `write_tool_use_run_results()`,
`write_tool_use_summary_report()`, `print_tool_use_summary_table()` —
following the pattern of existing query reporter functions. Per-run JSON
includes tool call logs. Summary includes tool-use-specific metrics.

### New file: `src/evaluation/tool_use_analysis.py`

Markdown report generator:

- Per-model accuracy tables (same format as query analysis)
- **Tool usage section**: which tools called most, average calls per
  scenario, max-turns-hit rate
- **Comparison section**: context-stuffing vs tool-use accuracy
  side-by-side (reads both `results/query_rag/` and
  `results/query_tool_use/`)
- Highlights tier-level deltas (especially T4 — the target)

### New file: `scripts/run_query_tool_use.sh`

Shell script following the pattern of `run_query_rag.sh`:

```bash
OUTPUT_DIR="results/query_tool_use"
uv run python -m src.evaluation.query_runner \
    --output "$OUTPUT_DIR" --mode tool_use "$@"
```

**Related issue:** #180

---

## Phase 7f: Testing

| Test file | Covers |
|-----------|--------|
| `tests/test_tool_definitions.py` | Schema validity, registry completeness |
| `tests/test_tool_executor.py` | Each tool against sample snapshots: filtering, edge cases (empty results, unknown IDs), JSON serialization |
| `tests/test_chat_adapters.py` | `chat()` on both adapters — mock HTTP, tool_calls parsing, error handling, message format conversion |
| `tests/test_tool_use_engine.py` | Multi-turn loop: tool call, execute, respond, final answer. Max turns exceeded. Error mid-loop. Token accumulation. |
| `tests/test_tool_use_harness.py` | E2E with MockAdapter: scenario execution, validation, decision persistence, early-abort |
| `tests/test_tool_use_metrics.py` | Metric computation from mock result lists |

Tests are included in the acceptance criteria for each phase's issue.

---

## Implementation Order

```text
7a (tools)  ───┐
               ├──> 7c (engine) ──> 7d (harness) ──> 7e (reporting)
7b (adapters) ─┘
                                                      7f (tests alongside each phase)
```

Phases 7a and 7b can be developed in parallel.

## File Summary

### New files (14)

- `src/tools/__init__.py`
- `src/tools/definitions.py`
- `src/tools/executor.py`
- `src/prediction/tool_use_prompt.py`
- `src/evaluation/tool_use_harness.py`
- `src/evaluation/tool_use_metrics.py`
- `src/evaluation/tool_use_analysis.py`
- `scripts/run_query_tool_use.sh`
- `tests/test_tool_definitions.py`
- `tests/test_tool_executor.py`
- `tests/test_chat_adapters.py`
- `tests/test_tool_use_engine.py`
- `tests/test_tool_use_harness.py`
- `tests/test_tool_use_metrics.py`

### Modified files (6)

- `src/models/base.py` — ChatMessage, ToolCall, ChatResponse + default
  `chat()`
- `src/models/ollama_adapter.py` — `chat()` via `/api/chat`
- `src/models/openrouter_adapter.py` — `chat()` with `tools` parameter
- `src/prediction/engine.py` — `predict_query_with_tools()`
- `src/evaluation/query_runner.py` — `--mode tool_use`
- `src/evaluation/reporter.py` — tool-use reporter functions

## Verification

1. `uv run pytest` — all existing + new tests pass
2. `uv run mypy src/` — clean
3. `uv run ruff check src/ tests/` — clean
4. `./scripts/run_query_tool_use.sh --dry-run` — validates config, prints
   plan
5. `./scripts/run_query_tool_use.sh --model "Qwen3 8B" --runs 1 --limit 5`
   — smoke test with 5 scenarios
6. Compare `results/query_tool_use/query_summary.json` T4 accuracy vs
   `results/query_rag/query_summary.json` T4 accuracy (expecting >0%
   vs 0%)

## Success Criteria

If Qwen3 8B can route at 94% **and** answer complex queries via tool-use
at 80%+, this validates that a single 8B local model can serve as a
complete lab workflow agent — no cloud API, no PHI exposure, no context
window limitations.
