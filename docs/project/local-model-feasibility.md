# Local Model Feasibility Validation

Step-by-step instructions for validating that candidate local models
can run on the target hardware (M4 MacBook Air, 32GB RAM) and produce
correct structured JSON output.

Related issue: [#76](https://github.com/ChrisHenryOC/samantha/issues/76)

## Prerequisites

1. **Install Ollama** (if not already installed):

   ```bash
   brew install ollama
   ```

2. **Start the Ollama server** (runs in the background):

   ```bash
   ollama serve
   ```

3. **Verify Ollama is working:**

   ```bash
   ollama list
   ```

   You should see an empty table or a list of any previously pulled models.

## Candidate Models

| Model | Ollama Tag | Approx Size | Notes |
|-------|-----------|-------------|-------|
| Llama 3.1 8B | `llama3.1:8b` | ~4.7 GB | Smallest Llama candidate |
| Mistral 7B | `mistral:7b` | ~4.1 GB | Strong JSON instruction following |
| Phi-3 | `phi3:latest` | ~2.3 GB | Smallest candidate |
| Gemma 2 27B | `gemma2:27b` | ~16 GB | Mid-size candidate (added after initial round) |
| Qwen 2.5 32B (Q4) | `Qwen2.5:32b-instruct-q4_K_M` | ~20 GB | Largest feasible candidate |
| Llama 3.3 70B (Q4) | `llama3.3:70b-instruct-q4_K_M` | ~40 GB | May exceed RAM — key test |

> **Note on the 70B model:** At Q4 quantization, Llama 3.3 70B requires
> ~40 GB of RAM. On a 32GB machine it will use swap heavily and may be
> impractically slow. The benchmark will confirm this — if it fails, skip
> it and note the result.

## Option A: Automated Benchmark (Recommended)

A benchmark script automates pulling models, running inference, measuring
speed, validating JSON output, and generating a decision table.

### Run the Full Suite

```bash
uv run python scripts/benchmark_models.py
```

This will:

- Pull each candidate model (can take a while on first run)
- Run 3 inference rounds per model with a standardized test prompt
- Validate JSON output structure (correct fields, valid states, valid rule IDs)
- Write results to `results/model_feasibility/<prompt>/`

### Useful Options

```bash
# Test only specific models
uv run python scripts/benchmark_models.py --models llama3.1:8b mistral:7b

# More runs for better variance data
uv run python scripts/benchmark_models.py --runs 5

# Skip pulling (if models are already downloaded)
uv run python scripts/benchmark_models.py --skip-pull

# Use the enriched prompt (includes valid states, rule catalog, flags)
uv run python scripts/benchmark_models.py --prompt enriched --skip-pull
```

### Prompt Variants

| Variant | Description |
|---------|-------------|
| `baseline` | Minimal prompt — no domain context. Tests JSON structure only. |
| `enriched` | Includes valid states, accessioning rule catalog, severity logic, and valid flags. Simulates what the RAG pipeline will provide. |

Results for each variant are stored in separate subdirectories under
`results/model_feasibility/`.

### Output Files

| File | Description |
|------|-------------|
| `results/model_feasibility/<prompt>/feasibility_report.md` | Decision table and per-run details |
| `results/model_feasibility/<prompt>/raw_results.json` | Machine-readable raw data |

## Option B: Manual Step-by-Step

If you prefer to run each step individually or need to troubleshoot.

### Step 1: Pull Each Model

```bash
ollama pull llama3.1:8b
ollama pull mistral:7b
ollama pull phi3:latest
ollama pull gemma2:27b
ollama pull Qwen2.5:32b-instruct-q4_K_M
ollama pull llama3.3:70b-instruct-q4_K_M
```

Verify they downloaded:

```bash
ollama list
```

### Step 2: Test Structured JSON Output

Run the test prompt against each model. The prompt asks the model to route
a straightforward accessioning event using the expected output format.

```bash
ollama run llama3.1:8b "You are a laboratory workflow routing engine for breast cancer specimens. Given the current order state and a new event, determine the next workflow state by matching rules from the rule catalog.

Current order state: ACCESSIONING
New event: order_received

Order details:
- specimen_type: core_biopsy
- anatomic_site: left_breast
- fixative: 10pct_nbf
- fixation_time_hours: 12
- patient_name: Jane Doe
- mrn: MRN-12345
- ordering_physician: Dr. Smith
- clinical_history: Suspicious mass
- insurance_info: BlueCross-1234

All required fields are present and valid.

Respond with ONLY a JSON object in this exact format, no other text:
{\"next_state\": \"<state>\", \"applied_rules\": [\"<rule_id>\"], \"flags\": [], \"reasoning\": \"<brief explanation>\"}"
```

Repeat for each model, replacing `llama3.1:8b` with the other model tags.

**What to check in each response:**

- Is the output valid JSON? (no extra text, markdown fences, or commentary)
- Is `next_state` a recognized state? (expected: `ACCEPTED` for this scenario)
- Does `applied_rules` contain properly formatted rule IDs? (e.g., `ACC-001`)
- Is the `reasoning` field present and coherent?

### Step 3: Measure Inference Speed

Time the full response for each model:

```bash
time ollama run llama3.1:8b "Your test prompt here..."
```

For more detailed metrics, use the Ollama API directly:

```bash
curl -s http://localhost:11434/api/generate \
  -d '{"model": "llama3.1:8b", "prompt": "Your test prompt...", "stream": false}' \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
total_ns = d.get('total_duration', 0)
eval_count = d.get('eval_count', 0)
eval_ns = d.get('eval_duration', 1)
print(f'Total duration: {total_ns/1e9:.1f}s')
print(f'Tokens generated: {eval_count}')
print(f'Tokens/sec: {eval_count/(eval_ns/1e9):.1f}')
print(f'Time to first token: {d.get(\"prompt_eval_duration\", 0)/1e9:.1f}s')
"
```

### Step 4: Record Results

Fill in this table with your measurements:

```text
| Model | Duration (s) | Tokens/s | TTFT (s) | JSON Valid | Valid State | Feasible |
|-------|--------------|----------|----------|------------|------------|----------|
| llama3.1:8b | | | | | | |
| llama3.3:70b Q4 | | | | | | |
| mistral:7b | | | | | | |
| phi3:latest | | | | | | |
```

## Decision Criteria

A model is **feasible** if ALL of the following are true:

| Criterion | Threshold | Rationale |
|-----------|-----------|-----------|
| Inference time | < 120 seconds | Practical for evaluation runs |
| JSON parsability | >= 50% of runs | Model can follow structured output instructions |
| Swap usage | Minimal / none | Heavy swapping makes timing unreliable |

A model is **marginal** if it meets most criteria but has concerns
(e.g., occasionally fails JSON, or causes swap pressure).

## Expected Outcomes

Based on model sizes and the 32GB RAM constraint:

- **llama3.1:8b** — Should run comfortably.
- **mistral:7b** — Should run comfortably.
- **phi3:latest** — Should run comfortably.
- **llama3.3:70b Q4** — Likely infeasible. ~40 GB needed, will swap heavily.
  If confirmed infeasible, consider `llama3.1:70b-q4_K_M` or dropping to a
  smaller quantization.

## After Benchmarking

1. Review the feasibility report in `results/model_feasibility/`
2. Fill in the Recommendations section of the report
3. Update issue [#76](https://github.com/ChrisHenryOC/samantha/issues/76)
   with the decision
4. Proceed with adapter code only for models that pass feasibility
