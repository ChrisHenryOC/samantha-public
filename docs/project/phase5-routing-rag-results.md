# Phase 5 — Routing RAG Evaluation Results

- **Date:** 2026-03-10
- **Hardware:** Apple M4 MacBook Air 32GB (local models via Ollama), cloud models via OpenRouter
- **Phase:** 5 (RAG-augmented evaluation)
- **Raw data:** `results/routing_rag/`

**Notes:**

- Qwen3 32B routing had only 1 incomplete run (21/105 scenarios, aborted due to extreme latency)
- Model roster changed entirely from Phase 4 — different local models, same cloud models
- All local models ran 5 times; cloud models ran once (cost constraints)

## 1. Executive Summary

- **Models evaluated:** 9
- **Scenarios:** 105
- **Total runs:** 28
- **Total decisions:** 23,268
- **Evaluation period:** 2026-03-10T11:45:02.505630 to 2026-03-10T18:38:07.622358

### Top Performers

1. **claude-opus-4-6-20250514** — 91.6% accuracy, 0.0% scenario reliability
2. **claude-sonnet-4-6-20250514** — 88.3% accuracy, 0.0% scenario reliability
3. **qwen3-8b** — 82.5% accuracy, 0.0% scenario reliability

## 2. Model Performance Overview

### 2.1 Primary Metrics

| Model | Acc% | Rule% | Flag% | Rel% | FP% |
|-------|-----:|------:|------:|-----:|----:|
| claude-opus-4-6-20250514 | 91.6 | 52.3 | 91.0 | 0.0 | 3.1 |
| claude-sonnet-4-6-20250514 | 88.3 | 37.5 | 86.9 | 0.0 | 1.9 |
| qwen3-8b | 82.5 ±1.0 | 43.9 | 88.9 | 0.0 | 1.3 |
| mistral-small-3.2-24b-instruct | 78.5 ±0.7 | 52.7 | 86.1 | 0.0 | 1.1 |
| qwen3.5-35b-a3b | 78.2 ±0.7 | 44.2 | 83.3 | 0.0 | 2.5 |
| claude-haiku-4-5-20251001 | 68.5 | 36.2 | 91.8 | 0.0 | 0.7 |
| gemma-3-27b-it | 65.1 ±4.9 | 45.8 | 83.9 | 0.0 | 0.5 |
| phi-4 | 61.2 ±1.2 | 33.5 | 83.3 | 0.0 | 2.7 |
| qwen3-32b | 29.4 | 8.8 | 58.8 | 0.0 | 5.9 |

### 2.2 Variance Analysis — Local Models

| Model | Acc (mean ±σ) | Rule (mean ±σ) | Flag (mean ±σ) |
|-------|-------------:|---------------:|---------------:|
| qwen3-8b | 82.5 ±1.0 | 43.9 ±0.2 | 88.9 ±0.3 |
| mistral-small-3.2-24b-instruct | 78.5 ±0.7 | 52.7 ±1.2 | 86.1 ±0.3 |
| qwen3.5-35b-a3b | 78.2 ±0.7 | 44.2 ±0.3 | 83.3 ±0.5 |
| gemma-3-27b-it | 65.1 ±4.9 | 45.8 ±3.4 | 83.9 ±6.5 |
| phi-4 | 61.2 ±1.2 | 33.5 ±0.4 | 83.3 ±0.9 |

## 3. Accuracy by Category

### 3.1 Category Performance Matrix

| Category | claude-opus-4-6-20250514 | claude-sonnet-4-6-20250514 | qwen3-8b | mistral-small-3.2-24b-instruct | qwen3.5-35b-a3b | claude-haiku-4-5-20251001 | gemma-3-27b-it | phi-4 | qwen3-32b |
|----------|-----:|-----:|-----:|-----:|-----:|-----:|-----:|-----:|-----:|
| accumulated_state | 89.3 | 83.6 | 82.6 | 77.6 | 73.3 | 65.7 | 67.9 | 63.9 | 0.0 |
| multi_rule | 91.4 | 94.3 | 82.3 | 75.4 | 85.7 | 71.4 | 62.3 | 54.3 | 0.0 |
| rule_coverage | 92.3 | 89.1 | 83.1 | 79.2 | 79.3 | 69.5 | 65.2 | 61.2 | 29.4 |
| unknown_input | 66.7 | 83.3 | 16.7 | 33.3 | 33.3 | 0.0 | 13.3 | 30.0 | 0.0 |

## 4. Rule Selection Diagnostics

#### claude-haiku-4-5-20251001

| | Right State | Wrong State | Total |
|------------|----------:|----------:|------:|
| **Right Rule** | 271 (32.6%) | 30 (3.6%) | 301 |
| **Wrong Rule** | 298 (35.9%) | 232 (27.9%) | 530 |
| **Total** | 569 | 262 | 831 |

#### claude-opus-4-6-20250514

| | Right State | Wrong State | Total |
|------------|----------:|----------:|------:|
| **Right Rule** | 429 (51.6%) | 6 (0.7%) | 435 |
| **Wrong Rule** | 332 (40.0%) | 64 (7.7%) | 396 |
| **Total** | 761 | 70 | 831 |

#### claude-sonnet-4-6-20250514

| | Right State | Wrong State | Total |
|------------|----------:|----------:|------:|
| **Right Rule** | 309 (37.2%) | 3 (0.4%) | 312 |
| **Wrong Rule** | 425 (51.1%) | 94 (11.3%) | 519 |
| **Total** | 734 | 97 | 831 |

#### gemma-3-27b-it

| | Right State | Wrong State | Total |
|------------|----------:|----------:|------:|
| **Right Rule** | 1312 (31.6%) | 592 (14.2%) | 1904 |
| **Wrong Rule** | 1394 (33.5%) | 857 (20.6%) | 2251 |
| **Total** | 2706 | 1449 | 4155 |

#### phi-4

| | Right State | Wrong State | Total |
|------------|----------:|----------:|------:|
| **Right Rule** | 1101 (26.5%) | 292 (7.0%) | 1393 |
| **Wrong Rule** | 1440 (34.7%) | 1322 (31.8%) | 2762 |
| **Total** | 2541 | 1614 | 4155 |

#### mistral-small-3.2-24b-instruct

| | Right State | Wrong State | Total |
|------------|----------:|----------:|------:|
| **Right Rule** | 1921 (46.2%) | 270 (6.5%) | 2191 |
| **Wrong Rule** | 1339 (32.2%) | 625 (15.0%) | 1964 |
| **Total** | 3260 | 895 | 4155 |

#### qwen3-8b

| | Right State | Wrong State | Total |
|------------|----------:|----------:|------:|
| **Right Rule** | 1534 (36.9%) | 288 (6.9%) | 1822 |
| **Wrong Rule** | 1895 (45.6%) | 438 (10.5%) | 2333 |
| **Total** | 3429 | 726 | 4155 |

#### qwen3.5-35b-a3b

| | Right State | Wrong State | Total |
|------------|----------:|----------:|------:|
| **Right Rule** | 1344 (32.3%) | 494 (11.9%) | 1838 |
| **Wrong Rule** | 1907 (45.9%) | 410 (9.9%) | 2317 |
| **Total** | 3251 | 904 | 4155 |

## 5. Failure Analysis

### 5.1 Failure Type Breakdown

| Model | hallucinated_flag | hallucinated_rule | hallucinated_state | invalid_json | wrong_flags | wrong_rules | wrong_state | Total |
|-------|-----:|-----:|-----:|-----:|-----:|-----:|-----:|------:|
| claude-opus-4-6-20250514 | 0 | 32 | 0 | 0 | 40 | 309 | 61 | 442 |
| claude-sonnet-4-6-20250514 | 0 | 67 | 0 | 3 | 38 | 378 | 74 | 560 |
| qwen3-8b | 0 | 569 | 0 | 1 | 186 | 1543 | 508 | 2807 |
| mistral-small-3.2-24b-instruct | 0 | 111 | 0 | 0 | 205 | 1258 | 865 | 2439 |
| qwen3.5-35b-a3b | 0 | 489 | 0 | 154 | 152 | 1496 | 672 | 2963 |
| claude-haiku-4-5-20251001 | 0 | 246 | 0 | 0 | 29 | 199 | 115 | 589 |
| gemma-3-27b-it | 0 | 688 | 8 | 133 | 140 | 1253 | 761 | 2983 |
| phi-4 | 8 | 1029 | 72 | 20 | 122 | 976 | 950 | 3177 |
| qwen3-32b | 0 | 10 | 0 | 11 | 0 | 3 | 7 | 31 |

### 5.2 Hardest Scenarios

| Scenario | Category | Accuracy% | Total Evals |
|----------|----------|----------:|------------:|
| SC-005 | rule_coverage | 0.0 | 28 |
| SC-013 | rule_coverage | 0.0 | 28 |
| SC-081 | multi_rule | 0.0 | 28 |
| SC-003 | rule_coverage | 3.6 | 28 |
| SC-006 | rule_coverage | 3.6 | 28 |
| SC-015 | rule_coverage | 3.6 | 28 |
| SC-016 | rule_coverage | 3.6 | 28 |
| SC-102 | unknown_input | 3.6 | 28 |
| SC-014 | rule_coverage | 7.1 | 28 |
| SC-103 | unknown_input | 7.1 | 28 |

### 5.3 Non-Viable Models

No models exceeded the structural failure threshold.

## 6. Secondary Metrics

### 6.1 Latency and Token Usage

| Model | Mean (ms) | p50 (ms) | p95 (ms) | Tokens In | Tokens Out |
|-------|----------:|---------:|---------:|----------:|-----------:|
| claude-opus-4-6-20250514 | 8424 | 6041 | 20646 | 3339 | 169 |
| claude-sonnet-4-6-20250514 | 4584 | 4262 | 6826 | 3339 | 175 |
| qwen3-8b | 2449 | 2326 | 3656 | 3009 | 88 |
| mistral-small-3.2-24b-instruct | 4224 | 2017 | 10706 | 3155 | 100 |
| qwen3.5-35b-a3b | 2302 | 1681 | 6697 | 3164 | 174 |
| claude-haiku-4-5-20251001 | 3316 | 2991 | 5208 | 3315 | 172 |
| gemma-3-27b-it | 3341 | 2973 | 6117 | 3188 | 85 |
| phi-4 | 5961 | 6426 | 9966 | 2790 | 315 |
| qwen3-32b | 25736 | 18770 | 78578 | 2660 | 607 |
