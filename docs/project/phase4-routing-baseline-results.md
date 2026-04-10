# Phase 4 — Routing Baseline Results

- **Date:** 2026-02-23 to 2026-02-24
- **Hardware:** Apple M4 MacBook Air 32GB (local models via Ollama), cloud models via OpenRouter
- **Phase:** 4 (baseline without RAG)
- **Related issues:** GH-101, GH-103
- **Raw data:** `results-old/routing_baseline/`

## 1. Executive Summary

- **Models evaluated:** 7
- **Scenarios:** 104
- **Total runs:** 35
- **Total decisions:** 29,050
- **Evaluation period:** 2026-02-23T20:39:43.027288 to 2026-02-24T17:47:29.385681

### Top Performers

1. **claude-opus-4-6-20250514** — 95.0% accuracy, 57.5% scenario reliability
2. **claude-sonnet-4-6-20250514** — 90.4% accuracy, 34.0% scenario reliability
3. **claude-haiku-4-5-20251001** — 82.2% accuracy, 16.7% scenario reliability

### Non-Viable Models

- **qwen-2.5-coder-32b-instruct** — 3617 structural failures (91% of all failures), 12.5% accuracy

## 2. Model Performance Overview

### 2.1 Primary Metrics

| Model | Acc% | Rule% | Flag% | Rel% | FP% |
|-------|-----:|------:|------:|-----:|----:|
| claude-opus-4-6-20250514 | 95.0 ±1.8 | 98.4 | 97.5 | 57.5 | 2.3 |
| claude-sonnet-4-6-20250514 | 90.4 ±1.7 | 97.8 | 98.3 | 34.0 | 1.4 |
| claude-haiku-4-5-20251001 | 82.2 ±1.8 | 99.2 | 97.7 | 16.7 | 2.1 |
| gemma-2-27b-it | 60.1 ±1.5 | 75.5 | 91.6 | 3.3 | 7.2 |
| mistral-7b-instruct | 43.8 ±1.6 | 61.2 | 92.5 | 6.9 | 0.2 |
| llama-3.1-8b-instruct | 25.2 ±0.6 | 66.1 | 82.3 | 2.5 | 17.1 |
| qwen-2.5-coder-32b-instruct | 12.5 ±0.6 | 4.9 | 12.7 | 0.0 | 0.1 |

### 2.2 Variance Analysis — Local Models

| Model | Acc (mean ±σ) | Rule (mean ±σ) | Flag (mean ±σ) |
|-------|-------------:|---------------:|---------------:|
| claude-opus-4-6-20250514 | 95.0 ±1.8 | 98.4 ±0.4 | 97.5 ±0.4 |
| claude-sonnet-4-6-20250514 | 90.4 ±1.7 | 97.8 ±0.1 | 98.3 ±0.0 |
| claude-haiku-4-5-20251001 | 82.2 ±1.8 | 99.2 ±0.1 | 97.7 ±0.2 |
| gemma-2-27b-it | 60.1 ±1.5 | 75.5 ±3.4 | 91.6 ±0.4 |
| mistral-7b-instruct | 43.8 ±1.6 | 61.2 ±2.8 | 92.5 ±1.4 |
| llama-3.1-8b-instruct | 25.2 ±0.6 | 66.1 ±2.9 | 82.3 ±0.4 |
| qwen-2.5-coder-32b-instruct | 12.5 ±0.6 | 4.9 ±0.1 | 12.7 ±0.1 |

## 3. Accuracy by Category

### 3.1 Category Performance Matrix

| Category | claude-opus-4-6-20250514 | claude-sonnet-4-6-20250514 | claude-haiku-4-5-20251001 | gemma-2-27b-it | mistral-7b-instruct | llama-3.1-8b-instruct | qwen-2.5-coder-32b-instruct |
|----------|-----:|-----:|-----:|-----:|-----:|-----:|-----:|
| accumulated_state | 94.6 | 90.4 | 86.4 | 68.7 | 54.0 | 32.9 | 14.3 |
| multi_rule | 95.4 | 89.1 | 69.1 | 49.7 | 34.9 | 9.7 | 8.6 |
| rule_coverage | 95.0 | 90.6 | 82.1 | 59.1 | 42.0 | 24.5 | 12.4 |
| unknown_input | 100.0 | 80.0 | 60.0 | 28.0 | 60.0 | 12.0 | 0.0 |

## 4. Rule Selection Diagnostics

#### claude-haiku-4-5-20251001

| | Right State | Wrong State | Total |
|------------|----------:|----------:|------:|
| **Right Rule** | 3402 (82.0%) | 715 (17.2%) | 4117 |
| **Wrong Rule** | 8 (0.2%) | 25 (0.6%) | 33 |
| **Total** | 3410 | 740 | 4150 |

#### claude-opus-4-6-20250514

| | Right State | Wrong State | Total |
|------------|----------:|----------:|------:|
| **Right Rule** | 3920 (94.5%) | 164 (4.0%) | 4084 |
| **Wrong Rule** | 22 (0.5%) | 44 (1.1%) | 66 |
| **Total** | 3942 | 208 | 4150 |

#### claude-sonnet-4-6-20250514

| | Right State | Wrong State | Total |
|------------|----------:|----------:|------:|
| **Right Rule** | 3685 (88.8%) | 375 (9.0%) | 4060 |
| **Wrong Rule** | 68 (1.6%) | 22 (0.5%) | 90 |
| **Total** | 3753 | 397 | 4150 |

#### gemma-2-27b-it

| | Right State | Wrong State | Total |
|------------|----------:|----------:|------:|
| **Right Rule** | 2197 (52.9%) | 935 (22.5%) | 3132 |
| **Wrong Rule** | 299 (7.2%) | 719 (17.3%) | 1018 |
| **Total** | 2496 | 1654 | 4150 |

#### llama-3.1-8b-instruct

| | Right State | Wrong State | Total |
|------------|----------:|----------:|------:|
| **Right Rule** | 843 (20.3%) | 1901 (45.8%) | 2744 |
| **Wrong Rule** | 202 (4.9%) | 1204 (29.0%) | 1406 |
| **Total** | 1045 | 3105 | 4150 |

#### mistral-7b-instruct

| | Right State | Wrong State | Total |
|------------|----------:|----------:|------:|
| **Right Rule** | 1649 (39.7%) | 889 (21.4%) | 2538 |
| **Wrong Rule** | 170 (4.1%) | 1442 (34.7%) | 1612 |
| **Total** | 1819 | 2331 | 4150 |

#### qwen-2.5-coder-32b-instruct

| | Right State | Wrong State | Total |
|------------|----------:|----------:|------:|
| **Right Rule** | 199 (4.8%) | 5 (0.1%) | 204 |
| **Wrong Rule** | 318 (7.7%) | 3628 (87.4%) | 3946 |
| **Total** | 517 | 3633 | 4150 |

## 5. Failure Analysis

### 5.1 Failure Type Breakdown

| Model | hallucinated_flag | hallucinated_rule | hallucinated_state | invalid_json | wrong_flags | wrong_rules | wrong_state | Total |
|-------|-----:|-----:|-----:|-----:|-----:|-----:|-----:|------:|
| claude-opus-4-6-20250514 | 0 | 0 | 0 | 0 | 104 | 22 | 208 | 334 |
| claude-sonnet-4-6-20250514 | 0 | 0 | 0 | 0 | 60 | 68 | 397 | 525 |
| claude-haiku-4-5-20251001 | 0 | 0 | 2 | 0 | 57 | 8 | 738 | 805 |
| gemma-2-27b-it | 34 | 330 | 12 | 3 | 20 | 266 | 1332 | 1997 |
| mistral-7b-instruct | 1 | 7 | 120 | 266 | 3 | 170 | 1938 | 2505 |
| llama-3.1-8b-instruct | 34 | 239 | 123 | 3 | 55 | 202 | 2707 | 3363 |
| qwen-2.5-coder-32b-instruct | 0 | 329 | 0 | 3617 | 4 | 0 | 5 | 3955 |

### 5.2 Hardest Scenarios

| Scenario | Category | Accuracy% | Total Steps |
|----------|----------|----------:|------------:|
| SC-104 | unknown_input | 14.3 | 35 |
| SC-081 | multi_rule | 28.6 | 35 |
| SC-022 | rule_coverage | 37.1 | 140 |
| SC-029 | rule_coverage | 37.1 | 140 |
| SC-103 | unknown_input | 37.1 | 35 |
| SC-018 | rule_coverage | 40.0 | 105 |
| SC-021 | rule_coverage | 41.0 | 105 |
| SC-020 | rule_coverage | 41.7 | 175 |
| SC-019 | rule_coverage | 41.9 | 105 |
| SC-002 | rule_coverage | 42.9 | 70 |

### 5.3 Non-Viable Models

Models where structural failures (invalid JSON, timeout, empty response) exceed 50% of all failures:

| Model | Structural | Total Failures | Structural% | Accuracy% |
|-------|----------:|---------------:|------------:|----------:|
| qwen-2.5-coder-32b-instruct | 3617 | 3955 | 91.5% | 12.5 |

## 6. Secondary Metrics

### 6.1 Latency and Token Usage

| Model | Mean (ms) | p50 (ms) | p95 (ms) | Tokens In | Tokens Out |
|-------|----------:|---------:|---------:|----------:|-----------:|
| claude-opus-4-6-20250514 | 4328 | 4162 | 5965 | 1976 | 152 |
| claude-sonnet-4-6-20250514 | 3839 | 3638 | 5445 | 1978 | 152 |
| claude-haiku-4-5-20251001 | 2393 | 2270 | 3330 | 1978 | 151 |
| gemma-2-27b-it | 2345 | 2252 | 2738 | 2049 | 70 |
| mistral-7b-instruct | 2529 | 1908 | 6542 | 1951 | 190 |
| llama-3.1-8b-instruct | 1484 | 1062 | 4211 | 1682 | 82 |
| qwen-2.5-coder-32b-instruct | 1395 | 1213 | 2531 | 1569 | 25 |
