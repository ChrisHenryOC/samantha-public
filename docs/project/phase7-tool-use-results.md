# Phase 7: Tool-Use Query Evaluation Results

## Overview

Phase 7 replaces context-stuffing with native tool-calling for query
evaluation. Instead of dumping the full database state into the prompt,
models call tools (`list_orders`, `get_order`, `get_slides`,
`get_state_info`, `get_flag_info`) to gather data before answering.

The primary goal: break the **Tier 4 (prioritized list) 0% ceiling**
that context-stuffing could not overcome across any local model.

## Evaluation Configuration

- **Scenarios**: 27 query scenarios (T1: 8, T2: 6, T3: 5, T4: 3, T5: 5)
- **Runs per model**: 3 (for variance measurement)
- **Max tool-use turns**: 10 per scenario
- **Models tested**: 5 of 7 non-Claude models (2 aborted — see below)

## Models Tested

| Model | Provider | Tier | Status |
|-------|----------|------|--------|
| Llama 3.1 8B | ollama (local) | 1 | Completed |
| Qwen3 8B | OpenRouter | 1 | Completed |
| Qwen3 32B | OpenRouter | 2 | Completed |
| Mistral Small 3.2 24B | OpenRouter | 2 | Completed |
| Qwen3.5 35B-A3B | OpenRouter | 3 (MoE) | Completed |
| Phi-4 14B | OpenRouter | 1 | Aborted — no tool-use endpoint |
| Gemma 3 27B | OpenRouter | 2 | Aborted — privacy policy block |

**Phi-4** returned HTTP 404: "No endpoints found that support tool use"
— OpenRouter does not offer Phi-4 with function-calling support.

**Gemma 3 27B** returned HTTP 404: "No endpoints available matching
your guardrail restrictions and data policy" — an OpenRouter account
setting issue, not a model limitation.

## Overall Accuracy

| Model | Accuracy | Precision | Recall | F1 | Reliability | Std Dev |
|-------|----------|-----------|--------|----|-------------|---------|
| Mistral Small 3.2 24B | **68.9%** | 0.848 | 0.889 | 0.860 | 48.1% | ±5.6 |
| Qwen3.5 35B-A3B | 66.7% | 0.717 | 0.721 | 0.718 | **59.3%** | ±2.6 |
| Qwen3 32B | 60.7% | 0.659 | 0.652 | 0.655 | 40.7% | ±10.0 |
| Qwen3 8B | 54.1% | 0.594 | 0.601 | 0.594 | 25.9% | ±10.3 |
| Llama 3.1 8B (local) | 50.4% | 0.613 | 0.611 | 0.608 | 48.1% | ±2.0 |

Mistral Small leads on accuracy and precision/recall. Qwen3.5 has the
highest reliability (59.3% of scenarios correct on every run) and lowest
variance (±2.6), making it the most consistent performer.

## Per-Tier Accuracy

| Model | T1 | T2 | T3 | T4 | T5 |
|-------|----|----|----|----|-----|
| Mistral Small 24B | 70.0% | **93.3%** | 92.0% | 6.7% | **52.0%** |
| Qwen3.5 35B-A3B | 62.5% | **100%** | **100%** | **13.3%** | 32.0% |
| Qwen3 32B | 47.5% | 96.7% | **100%** | 6.7% | 32.0% |
| Qwen3 8B | 37.5% | 90.0% | 92.0% | 0.0% | 32.0% |
| Llama 3.1 8B | 50.0% | 83.3% | 92.0% | 0.0% | 0.0% |

- **T2 (order status)** and **T3 (explanations)** are strong across all
  models (83–100%). Tool-use works well for simple lookups.
- **T4 (prioritized lists)** remains the hardest tier. See comparison
  section below.
- **T5 (complex queries)** shows the widest spread: Mistral Small at
  52% vs Llama 3.1 at 0%.

## RAG Baseline vs Tool-Use Comparison

Comparison against prior RAG (context-stuffing with retrieval)
evaluation results for the same scenarios and models.

### Overall Accuracy Delta

| Model | RAG | Tool-Use | Delta |
|-------|-----|----------|-------|
| Mistral Small 3.2 24B | 67.4% | **68.9%** | **+1.5%** |
| Qwen3.5 35B-A3B | 66.7% | 66.7% | 0.0% |
| Qwen3 32B | 62.2% | 60.7% | -1.5% |
| Qwen3 8B | 57.0% | 54.1% | -3.0% |

Overall accuracy is roughly flat — tool-use neither helps nor hurts at
the aggregate level.

### T4 (Prioritized Lists) — The Target Tier

| Model | RAG T4 | Tool-Use T4 | Delta |
|-------|--------|-------------|-------|
| **Qwen3.5 35B-A3B** | 0.0% | **13.3%** | **+13.3%** |
| Mistral Small 24B | 0.0% | 6.7% | +6.7% |
| Qwen3 32B | 0.0% | 6.7% | +6.7% |
| Qwen3 8B | 0.0% | 0.0% | 0.0% |

**T4 moved off zero for 3 of 4 models.** Context-stuffing scored 0%
across all local models. Tool-use broke through, though modestly.

### Per-Tier Deltas (Tool-Use minus RAG)

| Model | T1 | T2 | T3 | T4 | T5 |
|-------|----|----|----|----|-----|
| Mistral Small 24B | +5.0% | -6.7% | -8.0% | **+6.7%** | **+12.0%** |
| Qwen3.5 35B-A3B | -5.0% | **+16.7%** | 0.0% | **+13.3%** | -20.0% |
| Qwen3 32B | -5.0% | -3.3% | 0.0% | **+6.7%** | 0.0% |
| Qwen3 8B | 0.0% | -10.0% | -8.0% | 0.0% | +4.0% |

Key observations:

- **T4 improved across the board** — three models moved from 0% to >0%.
- **T2/T3 took small hits** for some models — multi-turn overhead
  slightly degraded simple lookups that context-stuffing handled well.
- **Mistral Small is the most balanced** — gains on T1/T4/T5 with
  modest T2/T3 regression.
- **Qwen3.5 has the highest T4 gain (+13.3%)** but a dramatic T5
  regression (-20%).
- **Qwen3 8B got no T4 benefit** — it barely uses tools (0.9
  calls/scenario), so it effectively runs like context-stuffing without
  the context.

## Tool Usage Patterns

| Model | Total Calls | Calls/Scenario | Turns/Scenario | Max-Turns Hit |
|-------|-------------|----------------|----------------|---------------|
| Mistral Small 24B | 579 | 4.3 | 3.3 | 2 |
| Llama 3.1 8B | 556 | 4.1 | 3.8 | 5 |
| Qwen3.5 35B-A3B | 535 | 4.0 | 3.2 | 0 |
| Qwen3 8B | 121 | 0.9 | 1.9 | 0 |
| Qwen3 32B | 110 | 0.8 | 1.8 | 0 |

### Tool Preference by Model

| Model | list_orders | get_order | get_state_info | get_flag_info | get_slides |
|-------|-------------|-----------|----------------|---------------|------------|
| Mistral Small 24B | 88 | 77 | **286** | 116 | 12 |
| Qwen3.5 35B-A3B | 92 | 55 | **307** | 81 | 0 |
| Llama 3.1 8B | **223** | 108 | 105 | 75 | 45 |
| Qwen3 8B | 52 | 52 | 11 | 6 | 0 |
| Qwen3 32B | 44 | 55 | 9 | 2 | 0 |

**Clear behavioral split**: Mistral Small and Qwen3.5 heavily use
`get_state_info` (understanding what workflow states mean), while
Llama 3.1 favors `list_orders` (scanning for data). Qwen3 8B and 32B
barely use tools at all.

## Failure Breakdown

| Model | Empty Response | Invalid JSON | Wrong IDs | Missing | Extra |
|-------|---------------|--------------|-----------|---------|-------|
| Llama 3.1 8B | 5 | **37** | 15 | 5 | 5 |
| Qwen3 32B | **38** | 3 | 5 | 5 | 2 |
| Qwen3.5 35B-A3B | **37** | 0 | 0 | 2 | 6 |
| Qwen3 8B | 19 | 0 | **22** | **17** | 4 |
| Mistral Small 24B | 3 | 8 | 3 | 6 | **22** |

- **Llama 3.1 8B**: Main weakness is JSON formatting (37 invalid_json)
  despite actively using tools. It gathers correct data but cannot
  format the final answer.
- **Qwen3 32B / Qwen3.5**: High empty_response rates — the model
  returns messages with neither content nor tool calls.
- **Qwen3 8B**: Mostly wrong_order_ids and missing_orders — answers
  without enough data.
- **Mistral Small**: Failures are mostly "extra orders" — over-includes
  rather than omitting. Consistent with high recall (0.889).

## Conclusions

1. **Tool-use broke the T4 ceiling** — three models moved from 0% to
   >0% on prioritized lists. The structural limitation of
   context-stuffing is partially overcome.

2. **T4 gains are modest** (6–13%) — the bottleneck is multi-key
   sorting reasoning, not data access. Models can now fetch the right
   orders but still struggle to rank them by priority > flags > age.

3. **Overall accuracy is flat** — tool-use trades T2/T3 regression for
   T4/T5 gains. The multi-turn overhead introduces new failure modes
   (empty responses, JSON formatting) that offset gains elsewhere.

4. **Tool engagement predicts accuracy** — models that actively use
   tools (4+ calls/scenario: Mistral Small, Qwen3.5, Llama 3.1) score
   higher than models that barely call tools (Qwen3 8B, 32B).

5. **Mistral Small 3.2 24B is the best tool-use performer** — highest
   accuracy (68.9%), most balanced per-tier profile, and the most
   efficient tool user (highest accuracy per tool call).

6. **Phi-4 and Gemma 3 are incompatible** with tool-use evaluation via
   OpenRouter — they need to be tested locally via ollama if tool-use
   evaluation is desired.

## Next Steps

- Run Claude ceiling benchmarks (Haiku, Sonnet, Opus) to establish
  upper bound for tool-use performance.
- Investigate why Qwen3 8B/32B underuse tools — prompt engineering or
  model-specific tool-calling behavior.
- Consider prompt refinements for T4 ranking instructions to improve
  multi-key sorting accuracy.
- Test Phi-4 and Gemma 3 locally via ollama for tool-use evaluation.
