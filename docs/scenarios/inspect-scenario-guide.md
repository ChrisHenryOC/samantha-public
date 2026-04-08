# Scenario Inspector Guide

The scenario inspector (`scripts/inspect_scenario.py`) runs a single scenario
through a single model and prints detailed diagnostic output. It is a developer
tool for debugging scenarios, tuning prompts, and understanding model behavior
without running the full evaluation harness.

## Quick Start

```bash
# View the prompt for a routing scenario (no model call, no cost)
uv run python scripts/inspect_scenario.py --scenario SC-001 --prompt-only

# Run a routing scenario through a model
uv run python scripts/inspect_scenario.py --scenario SC-001 --model "Qwen3 8B"

# Run a query scenario through the default ceiling model
uv run python scripts/inspect_scenario.py --scenario QR-001
```

## Command Line Options

### `--scenario ID` (required)

The scenario to inspect. Accepts both routing (`SC-NNN`) and query (`QR-NNN`)
scenario IDs. The script scans all subdirectories under `scenarios/` to find
the matching JSON file.

```bash
--scenario SC-001    # routing scenario
--scenario SC-042    # multi-step routing scenario
--scenario QR-005    # query scenario
```

### `--model NAME`

Model name from `config/models.yaml`. Case-insensitive. If omitted, defaults
to the first ceiling-tier model in the config (currently Claude Sonnet 4.6).

The provider (llamacpp vs openrouter) is not a separate flag — it comes from
the model's `provider` field in the config. To use a local model, add a model
entry with `provider: llamacpp` and ensure llama-server is running with the
model loaded.

```bash
--model "Qwen3 8B"              # openrouter
--model "Phi-4 14B"             # openrouter
--model "Mistral Small 3.2 24B" # openrouter
--model "Claude Haiku 4.5"      # openrouter (ceiling)
--model "Claude Sonnet 4.6"     # openrouter (ceiling)
```

Available models are listed in `config/models.yaml`. If the name doesn't
match, the script prints the full list of available models and exits.

### `--prompt-only`

Print the rendered prompt without calling the model. No adapter or engine is
created, no API key is needed, and no cost is incurred. Useful for reviewing
what the model will see.

```bash
uv run python scripts/inspect_scenario.py --scenario SC-001 --prompt-only
uv run python scripts/inspect_scenario.py --scenario SC-001 --prompt-only --rag
```

### `--show-prompt`

Print the full prompt in addition to running the model. Unlike `--prompt-only`,
this still calls the model and shows prediction results alongside the prompt.

```bash
uv run python scripts/inspect_scenario.py --scenario SC-001 --model "Qwen3 8B" --show-prompt
```

### `--step N`

Run only step N of a multi-step routing scenario. The script still builds
state through all preceding steps (so cumulative flags and slide status are
correct), but only prints output for the target step. Ignored for query
scenarios.

```bash
# Inspect step 2 of a 3-step scenario
uv run python scripts/inspect_scenario.py --scenario SC-042 --step 2 --prompt-only

# See what the model predicts for step 3 only
uv run python scripts/inspect_scenario.py --scenario SC-042 --step 3 --model "Qwen3 8B"
```

### `--rag`

Enable RAG retrieval. Loads the vector index from the path configured in
`config/models.yaml` (`rag_settings.index_path`) and retrieves relevant
SOP chunks for context. The retrieved chunks are displayed in the output
and included in the prompt.

```bash
uv run python scripts/inspect_scenario.py --scenario SC-001 --rag --prompt-only
uv run python scripts/inspect_scenario.py --scenario SC-001 --model "Qwen3 8B" --rag
```

Requires the RAG index to be built first (`uv run python scripts/build_rag_index.py`).

## Scenario Types

### Routing Scenarios (`SC-NNN`)

Multi-step workflow routing scenarios. Each step has an event type, event data,
and expected output (next_state, applied_rules, flags). The inspector shows:

- Event data for each step
- RAG chunks (if `--rag` is enabled)
- Rendered prompt (if `--show-prompt` or `--prompt-only`)
- Ground truth (expected state, rules, flags)
- Model prediction with match indicators (if not `--prompt-only`)
- Model stats (latency, tokens, cost)

Match indicators use order-independent comparison for `applied_rules` and
`flags` (matching the evaluation harness behavior).

### Query Scenarios (`QR-NNN`)

Single-turn query scenarios against a database state. The inspector shows:

- Query text
- Database state summary (order/slide counts)
- RAG chunks (if `--rag` is enabled)
- Rendered prompt (if `--show-prompt` or `--prompt-only`)
- Ground truth (answer_type, order_ids, reasoning)
- Model prediction with match indicators for answer_type and order_ids
- Model stats

## Output Sections

For each step (routing) or scenario (query), the output includes these
sections separated by Unicode bar characters:

| Section | Content |
|---------|---------|
| Header | Scenario ID, step number, event type |
| Event Data | Raw JSON event data from the scenario |
| RAG Chunks | Retrieved SOP chunks with similarity scores (only with `--rag`) |
| Prompt | Full rendered prompt (only with `--show-prompt` or `--prompt-only`) |
| Ground Truth | Expected next_state, applied_rules, flags |
| Prediction | Model output with check/cross marks against ground truth |
| Model | Model name, latency, token counts, cost estimate |

## Common Workflows

### Debugging a failing scenario

```bash
# Step 1: See what the prompt looks like
uv run python scripts/inspect_scenario.py --scenario SC-015 --prompt-only

# Step 2: Run with RAG to see which SOP chunks are retrieved
uv run python scripts/inspect_scenario.py --scenario SC-015 --rag --prompt-only

# Step 3: Run against the model and compare prediction to ground truth
uv run python scripts/inspect_scenario.py --scenario SC-015 --model "Qwen3 8B" --rag
```

### Comparing models on the same scenario

```bash
uv run python scripts/inspect_scenario.py --scenario SC-001 --model "Qwen3 8B"
uv run python scripts/inspect_scenario.py --scenario SC-001 --model "Phi-4 14B"
uv run python scripts/inspect_scenario.py --scenario SC-001 --model "Claude Sonnet 4.6"
```

### Inspecting a specific step in a multi-step scenario

```bash
# See the full prompt for step 3, including accumulated state from steps 1-2
uv run python scripts/inspect_scenario.py --scenario SC-042 --step 3 --show-prompt --model "Qwen3 8B"
```

### Validating a new scenario file

```bash
# The script validates ground truth against the rule catalog on load.
# Warnings are printed to stderr if rule IDs or states are invalid.
uv run python scripts/inspect_scenario.py --scenario SC-NEW --prompt-only
```

## Prerequisites

- **For `--prompt-only`**: No external dependencies beyond the scenario files
- **For model calls**: All current models use OpenRouter, which requires
  `notes/openrouter-api-key.txt`. For llamacpp models, llama-server must be
  running locally with the model loaded.
- **For `--rag`**: A built RAG index at the path in `config/models.yaml`

## Error Handling

- **Scenario not found**: Prints the scenarios directory and exits. If a JSON
  file failed to parse during the scan, a warning is printed to stderr.
- **Model not found**: Prints the list of available model names and exits.
- **RAG index missing**: Prints the expected index path and exits.
- **RAG retrieval failure**: Prints the error and exits cleanly (no raw
  traceback).
- **Step out of range**: Prints the valid range and exits.
