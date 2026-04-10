# Phase 5 — Query RAG Evaluation Results

- **Date:** 2026-03-10
- **Hardware:** Apple M4 MacBook Air 32GB (local models via Ollama), cloud models via OpenRouter
- **Phase:** 5 (RAG-augmented evaluation)
- **Raw data:** `results/query_rag/`

**Notes:**

- Model roster changed entirely from Phase 4 — different local models, same cloud models
- All local models ran 5 times; cloud models ran once (cost constraints)

## 1. Executive Summary

- **Models evaluated:** 9
- **Scenarios:** 27
- **Total runs:** 33
- **Total queries:** 891
- **Evaluation period:** 2026-03-10T11:44:59.379792 to 2026-03-10T12:34:47.065962

### Top Performers

1. **claude-opus-4-6-20250514** — 88.9% accuracy, 88.9% scenario reliability
2. **claude-sonnet-4-6-20250514** — 88.9% accuracy, 88.9% scenario reliability
3. **claude-haiku-4-5-20251001** — 81.5% accuracy, 81.5% scenario reliability

### Non-Viable Models

- **qwen3-32b** — 31 structural failures (63% of all failures), 63.7% accuracy

## 2. Model Performance Overview

### 2.1 Primary Metrics

| Model | Acc% | Prec | Recall | F1 | Rel% |
|-------|-----:|-----:|-------:|---:|-----:|
| claude-opus-4-6-20250514 | 88.9 | 0.991 | 1.000 | 0.995 | 88.9 |
| claude-sonnet-4-6-20250514 | 88.9 | 0.951 | 0.932 | 0.938 | 88.9 |
| claude-haiku-4-5-20251001 | 81.5 | 0.944 | 0.936 | 0.938 | 81.5 |
| qwen3.5-35b-a3b | 76.3 ±2.0 | 0.957 | 0.976 | 0.962 | 74.1 |
| mistral-small-3.2-24b-instruct | 73.3 ±1.7 | 0.956 | 0.952 | 0.951 | 70.4 |
| gemma-3-27b-it | 68.9 ±2.0 | 0.911 | 0.901 | 0.895 | 63.0 |
| qwen3-32b | 63.7 ±3.1 | 0.742 | 0.750 | 0.743 | 51.9 |
| qwen3-8b | 63.0 ±0.0 | 0.890 | 0.943 | 0.907 | 63.0 |
| phi-4 | 59.3 ±3.7 | 0.878 | 0.859 | 0.850 | 48.1 |

### 2.2 Variance Analysis — Local Models

| Model | Acc (mean ±σ) |
|-------|-------------:|
| qwen3.5-35b-a3b | 76.3 ±2.0 |
| mistral-small-3.2-24b-instruct | 73.3 ±1.7 |
| gemma-3-27b-it | 68.9 ±2.0 |
| qwen3-32b | 63.7 ±3.1 |
| qwen3-8b | 63.0 ±0.0 |
| phi-4 | 59.3 ±3.7 |

## 3. Accuracy by Tier

| Tier | claude-opus-4-6-20250514 | claude-sonnet-4-6-20250514 | claude-haiku-4-5-20251001 | qwen3.5-35b-a3b | mistral-small-3.2-24b-instruct | gemma-3-27b-it | qwen3-32b | qwen3-8b | phi-4 |
|------|-----:|-----:|-----:|-----:|-----:|-----:|-----:|-----:|-----:|
| 1 | 100.0 | 100.0 | 100.0 | 75.0 | 75.0 | 75.0 | 65.0 | 62.5 | 60.0 |
| 2 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 96.7 | 90.0 | 100.0 | 100.0 |
| 3 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| 4 | 33.3 | 66.7 | 33.3 | 33.3 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| 5 | 80.0 | 60.0 | 40.0 | 52.0 | 56.0 | 36.0 | 32.0 | 20.0 | 4.0 |

## 4. Accuracy by Answer Type

| Answer Type | claude-opus-4-6-20250514 | claude-sonnet-4-6-20250514 | claude-haiku-4-5-20251001 | qwen3.5-35b-a3b | mistral-small-3.2-24b-instruct | gemma-3-27b-it | qwen3-32b | qwen3-8b | phi-4 |
|-------------|-----:|-----:|-----:|-----:|-----:|-----:|-----:|-----:|-----:|
| order_list | 92.3 | 84.6 | 76.9 | 66.2 | 67.7 | 60.0 | 52.3 | 46.2 | 38.5 |
| order_status | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 98.2 | 94.5 | 100.0 | 100.0 |
| prioritized_list | 33.3 | 66.7 | 33.3 | 33.3 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |

## 5. Failure Analysis

### 5.1 Failure Type Breakdown

| Model | extra_orders | invalid_json | missing_orders | wrong_order_ids | wrong_order_sequence | Total |
|-------|-----:|-----:|-----:|-----:|-----:|------:|
| claude-opus-4-6-20250514 | 1 | 0 | 0 | 0 | 2 | 3 |
| claude-sonnet-4-6-20250514 | 0 | 0 | 1 | 2 | 0 | 3 |
| claude-haiku-4-5-20251001 | 1 | 0 | 2 | 1 | 1 | 5 |
| qwen3.5-35b-a3b | 17 | 0 | 4 | 6 | 5 | 32 |
| mistral-small-3.2-24b-instruct | 9 | 0 | 11 | 12 | 4 | 36 |
| gemma-3-27b-it | 13 | 4 | 14 | 10 | 1 | 42 |
| qwen3-32b | 7 | 31 | 2 | 6 | 3 | 49 |
| qwen3-8b | 28 | 0 | 6 | 16 | 0 | 50 |
| phi-4 | 16 | 0 | 22 | 12 | 5 | 55 |

### 5.2 Hardest Scenarios

| Scenario | Tier | Answer Type | Accuracy% | Total Evals |
|----------|-----:|-------------|----------:|------------:|
| QR-021 | 4 | prioritized_list | 0.0 | 33 |
| QR-026 | 5 | order_list | 0.0 | 33 |
| QR-020 | 4 | prioritized_list | 3.0 | 33 |
| QR-024 | 5 | order_list | 6.1 | 33 |
| QR-001 | 1 | order_list | 15.2 | 33 |
| QR-008 | 1 | order_list | 21.2 | 33 |
| QR-022 | 4 | prioritized_list | 24.2 | 33 |
| QR-023 | 5 | order_list | 30.3 | 33 |
| QR-025 | 5 | order_list | 57.6 | 33 |
| QR-007 | 1 | order_list | 78.8 | 33 |

### 5.3 Non-Viable Models

Models where structural failures (invalid JSON, timeout, empty response) exceed 50% of all failures:

| Model | Structural | Total Failures | Structural% | Accuracy% |
|-------|----------:|---------------:|------------:|----------:|
| qwen3-32b | 31 | 49 | 63.3% | 63.7 |

## 6. Secondary Metrics

### 6.1 Latency and Token Usage

| Model | Mean (ms) | p50 (ms) | p95 (ms) | Tokens In | Tokens Out |
|-------|----------:|---------:|---------:|----------:|-----------:|
| claude-opus-4-6-20250514 | 6312 | 5708 | 9680 | 2941 | 216 |
| claude-sonnet-4-6-20250514 | 5194 | 4666 | 7966 | 2941 | 193 |
| claude-haiku-4-5-20251001 | 3071 | 2801 | 4179 | 2941 | 184 |
| qwen3.5-35b-a3b | 1632 | 1556 | 2546 | 2744 | 131 |
| mistral-small-3.2-24b-instruct | 6719 | 1756 | 19040 | 2706 | 111 |
| gemma-3-27b-it | 5577 | 4757 | 11686 | 2741 | 112 |
| qwen3-32b | 22128 | 14751 | 72170 | 2605 | 474 |
| qwen3-8b | 2468 | 2319 | 4260 | 2603 | 111 |
| phi-4 | 4162 | 3301 | 10379 | 2476 | 198 |
