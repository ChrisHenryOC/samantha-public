# Scenario Chat Guide

The scenario chat script (`scripts/chat_scenario.py`) loads a scenario into
a model's context and opens an interactive conversation. It is a developer
tool for probing model reasoning, asking follow-up questions, and exploring
how a model understands the workflow rules — without running the evaluation
harness.

## Quick Start

```bash
# Chat with a local llama-server model about a routing scenario
uv run python scripts/chat_scenario.py --scenario SC-001 --model "Llama 3.1 8B"

# Chat with the default ceiling model about a query scenario
uv run python scripts/chat_scenario.py --scenario QR-001

# Chat with RAG context enabled
uv run python scripts/chat_scenario.py --scenario SC-001 --model "Qwen3 8B" --rag
```

## Command Line Options

### `--scenario ID` (required)

The scenario to load. Accepts both routing (`SC-NNN`) and query (`QR-NNN`)
scenario IDs. The script scans all subdirectories under `scenarios/` to find
the matching JSON file.

```bash
--scenario SC-001    # routing scenario
--scenario SC-042    # multi-step routing scenario
--scenario QR-005    # query scenario
```

### `--model NAME`

Model name from `config/models.yaml`. Case-insensitive. If omitted, defaults
to the first ceiling-tier model in the config (currently Claude Haiku 4.5).

The provider (llamacpp vs openrouter) is determined by the model's `provider`
field in the config — there is no separate CLI flag.

```bash
--model "Llama 3.1 8B"            # llamacpp (local)
--model "Qwen3 8B"                # openrouter
--model "Claude Sonnet 4.6"       # openrouter (ceiling)
```

Available models are listed in `config/models.yaml`. If the name doesn't
match, the script prints the full list of available models and exits.

### `--rag`

Enable RAG retrieval. Loads the vector index from the path configured in
`config/settings.yaml` (`rag.index_path`) and retrieves relevant SOP chunks
for context. The retrieved chunks are included in the system message sent to
the model.

```bash
uv run python scripts/chat_scenario.py --scenario SC-001 --model "Qwen3 8B" --rag
```

Requires the RAG index to be built first (`uv run python scripts/build_rag_index.py`).

### `--step N`

For routing scenarios, select which step to chat about (default: step 1). The
script builds state through all preceding steps (so cumulative flags and slide
status are correct), then loads the target step's context.

```bash
# Chat about step 2 of a multi-step scenario
uv run python scripts/chat_scenario.py --scenario SC-042 --step 2 --model "Qwen3 8B"
```

Ignored for query scenarios.

## REPL Commands

Once the scenario is loaded, the script drops into a `You>` prompt. Type
freely to converse with the model. The following commands are also available:

| Command | Description |
|---------|-------------|
| `quit` / `exit` | End the session |
| `context` | Reprint the scenario summary |
| `history` | Show the conversation history |
| `clear` | Clear conversation history (keep system context) |
| `step N` | Switch to step N (routing only, clears history) |
| `help` | Show available commands |

Ctrl+D also exits the session.

## How It Works

### System context

The script reuses the same prompt templates as the evaluation harness:

- **Routing scenarios**: `render_prompt()` from `src/prediction/prompt_template.py`
- **Query scenarios**: `render_query_prompt()` from `src/prediction/query_prompt_template.py`

This gives the model full knowledge of the order, slides, event, applicable
rules, and (if `--rag` is enabled) relevant SOP chunks. The prompt is sent as
a system message with an instruction to respond conversationally rather than
in JSON.

### Multi-turn conversation

The script uses each adapter's `chat()` method to support multi-turn
conversation with full message history. Each exchange is appended to the
messages array so the model remembers prior turns.

### Step switching

When you use the `step N` command during a REPL session, the script:

1. Rebuilds order/slide/event state through all preceding steps
2. Re-renders the prompt for the new step
3. Replaces the system context
4. Clears conversation history

## Common Workflows

### Exploring model reasoning on a routing scenario

```bash
uv run python scripts/chat_scenario.py --scenario SC-015 --model "Qwen3 8B"
```

```text
You> What state should this order transition to, and why?
You> Which rules apply here?
You> What if the specimen type were a biopsy instead?
```

### Comparing models on the same scenario

```bash
# Terminal 1
uv run python scripts/chat_scenario.py --scenario SC-001 --model "Qwen3 8B"

# Terminal 2
uv run python scripts/chat_scenario.py --scenario SC-001 --model "Claude Sonnet 4.6"
```

### Walking through a multi-step scenario

```bash
uv run python scripts/chat_scenario.py --scenario SC-042 --model "Qwen3 8B"
```

```text
You> Walk me through this step.
You> step 2
You> What changed between step 1 and step 2?
You> step 3
You> Why do these rules apply at this point?
```

### Probing a query scenario

```bash
uv run python scripts/chat_scenario.py --scenario QR-001 --model "Claude Sonnet 4.6"
```

```text
You> What orders match this query?
You> Why did you exclude order ORD-003?
```

## Prerequisites

- **For all usage**: A model entry in `config/models.yaml`
- **For llamacpp models**: llama-server must be running locally with the model loaded
- **For openrouter models**: API key in `notes/openrouter-api-key.txt`
- **For `--rag`**: A built RAG index at the path in `config/settings.yaml`

## Error Handling

- **Scenario not found**: Prints the scenarios directory and exits
- **Model not found**: Prints the list of available model names and exits
- **RAG index missing**: Prints the expected index path and exits
- **API errors during chat**: Prints the error and continues the REPL (does
  not crash). The failed message is removed from history so you can retry.
- **Empty model response**: Prints a notice and continues. The empty turn is
  not added to history.
- **Step out of range**: Prints the valid range (both at startup and during
  `step N` commands)
