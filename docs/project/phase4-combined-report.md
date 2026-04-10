# Phase 4 — Combined Baseline Report

- **Date:** 2026-02-23 to 2026-03-03
- **Hardware:** Apple M4 MacBook Air 32GB (local models via Ollama), cloud models via OpenRouter
- **Phase:** 4 (baseline without RAG)
- **Related issues:** GH-101, GH-103, GH-104
- **Raw data:** `results-old/routing_baseline/`, `results-old/query_baseline/`

## 1. Executive Summary

- **Total unique models:** 9
- **Models in routing baseline:** 7
- **Models in query baseline:** 6
- **Models in both tracks:** 4
- **Routing evaluation period:** 2026-02-23T20:39:43.027288 to 2026-02-24T17:47:29.385681
- **Query evaluation period:** 2026-03-03T12:25:50.817536 to 2026-03-03T12:39:24.015762

### Top Performers (Combined Score)

1. **claude-opus-4-6-20250514** — routing 95.0%, query 96.3%
2. **claude-sonnet-4-6-20250514** — routing 90.4%, query 88.9%
3. **qwen3.5-397b-a17b** — query 81.5%

## 2. Unified Scorecard

| Model | Type | Routing Acc% | Query Acc% | Routing Rel% | Query Rel% | Routing σ |
|-------|------|------------:|----------:|--------------:|----------:|---------:|
| claude-opus-4-6-20250514 | Cloud | 95.0 | 96.3 | 57.5 | 96.3 | ±1.8 |
| claude-sonnet-4-6-20250514 | Cloud | 90.4 | 88.9 | 34.0 | 88.9 | ±1.7 |
| qwen3.5-397b-a17b | Local | — | 81.5 | — | 81.5 | — |
| claude-haiku-4-5-20251001 | Cloud | 82.2 | 77.8 | 16.7 | 77.8 | ±1.8 |
| llama3.1:8b | Local | — | 74.1 | — | 74.1 | — |
| gemma-2-27b-it | Local | 60.1 | — | 3.3 | — | ±1.5 |
| mistral-7b-instruct | Local | 43.8 | — | 6.9 | — | ±1.6 |
| llama-3.1-8b-instruct | Local | 25.2 | 59.3 | 2.5 | 59.3 | ±0.6 |
| qwen-2.5-coder-32b-instruct | Local | 12.5 | — | 0.0 | — | ±0.6 |

## 3. Cross-Track Correlation

### 3.1 Routing vs Query Performance

| Model | Routing Acc% | Query Acc% | Delta | Stronger Track |
|-------|------------:|----------:|------:|----------------|
| claude-opus-4-6-20250514 | 95.0 | 96.3 | -1.3 | Balanced |
| claude-sonnet-4-6-20250514 | 90.4 | 88.9 | +1.5 | Balanced |
| claude-haiku-4-5-20251001 | 82.2 | 77.8 | +4.4 | Routing |
| llama-3.1-8b-instruct | 25.2 | 59.3 | -34.1 | Query |

### 3.2 Observations

- Performance is **balanced across tracks** for most models.
- **Model ranking is identical** across both tracks — models that excel at routing also excel at query answering.

## 4. Model Capability Matrix

| Model | Type | Routing | Query | Consistency | Latency |
|-------|------|---------|-------|-------------|---------|
| claude-opus-4-6-20250514 | Cloud | Strong | Strong | Moderate | Slow |
| claude-sonnet-4-6-20250514 | Cloud | Strong | Moderate | Moderate | Slow |
| qwen3.5-397b-a17b | Local | N/A | Moderate | N/A | Moderate |
| claude-haiku-4-5-20251001 | Cloud | Moderate | Moderate | Moderate | Moderate |
| llama3.1:8b | Local | N/A | Moderate | N/A | Slow |
| gemma-2-27b-it | Local | Weak | N/A | Moderate | Moderate |
| mistral-7b-instruct | Local | Weak | N/A | Moderate | Moderate |
| llama-3.1-8b-instruct | Local | Poor | Weak | High | Fast |
| qwen-2.5-coder-32b-instruct | Local | Poor | N/A | High | Fast |

## 5. Go/No-Go Assessment

### 5.1 Feasibility

- **Routing:** 3 model(s) achieve ≥80% accuracy: claude-opus-4-6-20250514, claude-sonnet-4-6-20250514, claude-haiku-4-5-20251001
- **Query:** 3 model(s) achieve ≥80% accuracy: claude-opus-4-6-20250514, claude-sonnet-4-6-20250514, qwen3.5-397b-a17b

**Verdict:** The task is feasible — at least one model achieves acceptable routing accuracy with full context.

### 5.2 Ceiling Benchmark

- **Routing:** Best cloud 95.0% vs best local 60.1% (gap: 34.8 pp)
- **Query:** Best cloud 96.3% vs best local 81.5% (gap: 14.8 pp)

**Verdict:** Significant headroom exists between cloud and local models. RAG or other retrieval strategies could help close this gap.

### 5.3 RAG Justification

Local model context usage (mean input tokens, routing):

- **qwen-2.5-coder-32b-instruct:** 1569 tokens
- **llama-3.1-8b-instruct:** 1682 tokens
- **mistral-7b-instruct:** 1951 tokens
- **gemma-2-27b-it:** 2049 tokens

**4 local model(s) fail to reach 80% routing accuracy** (gemma-2-27b-it, mistral-7b-instruct, llama-3.1-8b-instruct, qwen-2.5-coder-32b-instruct), despite receiving full context. RAG could help these models by providing more targeted, relevant context rather than the entire knowledge base.

### 5.4 Variance Assessment

| Model | Routing Acc% | Flag Acc% | σ | Clinical Viable? |
|-------|------------:|----------:|----:|-----------------|
| gemma-2-27b-it | 60.1 | 91.6 | ±1.5 | No |
| mistral-7b-instruct | 43.8 | 92.5 | ±1.6 | No |
| llama-3.1-8b-instruct | 25.2 | 82.3 | ±0.6 | No |
| qwen-2.5-coder-32b-instruct | 12.5 | 12.7 | ±0.6 | No |

**No local models currently meet clinical deployment criteria** (≥80% accuracy with ≤2.0σ variance).

## 6. Phase 5 Recommendations

### 6.1 Priority Models for RAG

These local models show sufficient baseline capability to benefit from RAG-enhanced context:

1. **gemma-2-27b-it** — routing 60.1%
1. **mistral-7b-instruct** — routing 43.8%

### 6.2 Models to Exclude

These models (qwen-2.5-coder-32b-instruct) perform below 20% routing accuracy and are unlikely to benefit from RAG. Exclude from Phase 5.

### 6.3 Expected RAG Impact

- The cloud-local gap of **34.8 percentage points** on routing represents the theoretical maximum improvement from better context.
- RAG is expected to improve local models by providing focused, relevant context instead of the full knowledge base.
- Priority should be given to models that already demonstrate strong rule-matching ability but struggle with state transitions.
