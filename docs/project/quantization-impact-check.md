# Quantization Impact Check

Step-by-step instructions for determining whether Q4 quantization degrades
structured output quality for models that required it to fit in 32GB RAM.

Related issue: [#77](https://github.com/ChrisHenryOC/samantha/issues/77)

## Background

The [feasibility check](local-model-feasibility-results.md) (issue #76)
identified one model that required quantization and remained feasible:

| Model | Local Tag | Quantization | Status |
|-------|-----------|-------------|--------|
| Qwen2.5 32B | `Qwen2.5:32b-instruct-q4_K_M` | Q4_K_M | Near-perfect (2/3 rules correct) |
| Llama 3.3 70B | `llama3.3:70b-instruct-q4_K_M` | Q4_K_M | Infeasible (exceeded 32GB RAM) |

The question: did Q4 quantization cause the Qwen formatting error
(`ACC-08` instead of `ACC-008`), or is that a model-level issue that
exists at full precision too?

For the 70B model, the question is simpler: does it perform well at full
precision via a cloud API, making it a candidate if hardware constraints
are removed in the future?

## Prerequisites

### 1. Choose a Cloud API Provider

You need a provider that hosts **full-precision** (FP16/BF16) versions
of the quantized models. **OpenRouter is recommended** — one API key
gives access to models from many backends, which is also useful for
the Phase 4 cloud ceiling benchmarks (Anthropic, OpenAI, Google).

| Provider | Qwen2.5 72B (upper bound) | Llama 3.3 70B | Notes |
|----------|--------------------------|---------------|-------|
| [OpenRouter](https://openrouter.ai) | Yes | Yes | Recommended — single key for multiple backends |
| [Together AI](https://together.ai) | Yes | Yes | Direct provider, lower per-token cost |
| [Groq](https://groq.com) | Check | Yes | Very fast inference, smaller model catalog |

### 2. Get an API Key

Sign up at [openrouter.ai](https://openrouter.ai) (or your chosen
provider) and get an API key. Set it as an environment variable:

```bash
# OpenRouter (recommended)
export OPENROUTER_API_KEY="your-key-here"

# Together AI (alternative)
export TOGETHER_API_KEY="your-key-here"

# Groq (alternative)
export GROQ_API_KEY="your-key-here"
```

### 3. Identify Full-Precision Model IDs

> **Note:** The base Qwen2.5-32B-Instruct is not available on major
> cloud providers (checked Feb 2026). Only the Coder and VL variants
> are hosted. The script uses **Qwen2.5-72B-Instruct** as a same-family
> upper bound instead.

Look up the exact model IDs on your provider's model list:

```text
# OpenRouter (recommended)
qwen/qwen-2.5-72b-instruct    # Upper bound for Qwen2.5-32B Q4
meta-llama/llama-3.3-70b-instruct

# Together AI
Qwen/Qwen2.5-72B-Instruct
meta-llama/Llama-3.3-70B-Instruct

# Groq
llama-3.3-70b-versatile
```

## Option A: Automated Benchmark (Recommended)

A benchmark script automates cloud API calls, compares results with
existing local quantized data, and generates a comparison report.

### Run the Full Comparison

```bash
# OpenRouter (recommended)
uv run python scripts/benchmark_quantization.py \
  --provider openrouter \
  --api-key "$OPENROUTER_API_KEY"

# Together AI (alternative)
uv run python scripts/benchmark_quantization.py \
  --provider together \
  --api-key "$TOGETHER_API_KEY"
```

This will:

- Call the cloud API with the same baseline and enriched prompts used in
  the feasibility benchmark
- Run 3 inference rounds per model per prompt (matching feasibility runs)
- Validate JSON output structure and rule accuracy
- Load existing local Q4 results for side-by-side comparison
- Write a comparison report to `results/quantization_impact/`

### Useful Options

```bash
# More runs for better variance data
uv run python scripts/benchmark_quantization.py \
  --provider openrouter --api-key "$OPENROUTER_API_KEY" --runs 5

# Test only specific models
uv run python scripts/benchmark_quantization.py \
  --provider openrouter --api-key "$OPENROUTER_API_KEY" \
  --models "qwen/qwen-2.5-72b-instruct"

# Only run enriched prompt (skip baseline)
uv run python scripts/benchmark_quantization.py \
  --provider openrouter --api-key "$OPENROUTER_API_KEY" \
  --prompt enriched

# Custom local results path (if not in the default location)
uv run python scripts/benchmark_quantization.py \
  --provider openrouter --api-key "$OPENROUTER_API_KEY" \
  --local-results results/model_feasibility/2026-02-18_14-30/enriched/raw_results.json
```

### Testing Intermediate Quantization Levels

If full-precision significantly outperforms Q4, test intermediate levels
locally to find the best tradeoff:

```bash
# Pull intermediate quantization variants
ollama pull Qwen2.5:32b-instruct-q5_K_M
ollama pull Qwen2.5:32b-instruct-q6_K

# Run the feasibility benchmark on them
uv run python scripts/benchmark_models.py \
  --models "Qwen2.5:32b-instruct-q5_K_M" "Qwen2.5:32b-instruct-q6_K" \
  --skip-pull --prompt enriched
```

### Output Files

| File | Description |
|------|-------------|
| `results/quantization_impact/<timestamp>/comparison_report.md` | Side-by-side comparison |
| `results/quantization_impact/<timestamp>/cloud_raw_results.json` | Machine-readable cloud data |

## Option B: Manual Step-by-Step

If you prefer to run each step individually or need to troubleshoot.

### Step 1: Run Full-Precision Inference via Cloud API

Use `curl` to call the cloud API with the same prompts. Example with
OpenRouter:

```bash
curl -s https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen/qwen-2.5-72b-instruct",
    "messages": [{"role": "user", "content": "YOUR PROMPT HERE"}],
    "temperature": 0.0,
    "max_tokens": 512
  }' | python3 -c "
import sys, json
d = json.load(sys.stdin)
content = d['choices'][0]['message']['content']
print(content)
"
```

Run the **enriched prompt** (from the feasibility check) 3 times and
record each response.

### Step 2: Compare with Local Q4 Results

For each run, check:

- Is the JSON output valid?
- Is `next_state` correct? (Expected: `ACCEPTED`)
- Are `applied_rules` correct? (Expected: `["ACC-008"]`)
- Does the formatting match exactly? (No `ACC-08` instead of `ACC-008`)

### Step 3: Record Results

```text
| Source | Model | Run | JSON Valid | Correct State | Correct Rules | Notes |
|--------|-------|-----|-----------|---------------|---------------|-------|
| Cloud FP16 | Qwen2.5-72B | 1 | | | | |
| Cloud FP16 | Qwen2.5-72B | 2 | | | | |
| Cloud FP16 | Qwen2.5-72B | 3 | | | | |
| Local Q4 | Qwen2.5:32b Q4 | 1 | | | | |
| Local Q4 | Qwen2.5:32b Q4 | 2 | | | | |
| Local Q4 | Qwen2.5:32b Q4 | 3 | | | | |
```

## Decision Criteria

| Outcome | Meaning | Action |
|---------|---------|--------|
| Cloud FP16 == Local Q4 | Quantization has no meaningful impact | Keep Q4 as candidate |
| Cloud FP16 > Local Q4 | Quantization degrades quality | Test Q5/Q6 locally; if Q5/Q6 fixes it, use that level |
| Cloud FP16 < Local Q4 | Unlikely but possible with temperature variance | Run more iterations |

**"Significantly better"** means the full-precision version achieves
higher correct-rule rates across multiple runs, not just one lucky run.

## After Benchmarking

1. Review the comparison report in `results/quantization_impact/`
2. Fill in the results document:
   [quantization-impact-results.md](quantization-impact-results.md)
3. Update issue [#77](https://github.com/ChrisHenryOC/samantha/issues/77)
   with the decision
4. If a model is dropped or a quantization level is changed, update the
   candidate list for Phase 3 adapter work
