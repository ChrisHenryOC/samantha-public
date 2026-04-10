# Phase 4 — Query Baseline Results

- **Date:** 2026-03-03
- **Hardware:** Apple M4 MacBook Air 32GB (local models via Ollama), cloud models via OpenRouter
- **Phase:** 4 (baseline without RAG)
- **Related issues:** GH-103, GH-104
- **Raw data:** `results-old/query_baseline/`

## 1. Executive Summary

- **Models evaluated:** 6
- **Scenarios:** 27
- **Total runs:** 36
- **Total queries:** 936
- **Evaluation period:** 2026-03-03T12:25:50.817536 to 2026-03-03T12:39:24.015762

### Top Performers

1. **claude-opus-4-6-20250514** — 96.3% accuracy, 96.3% scenario reliability
2. **claude-sonnet-4-6-20250514** — 88.9% accuracy, 88.9% scenario reliability
3. **qwen3.5-397b-a17b** — 81.5% accuracy, 81.5% scenario reliability

## 2. Model Performance Overview

### 2.1 Primary Metrics

| Model | Acc% | Prec | Recall | F1 | Rel% |
|-------|-----:|-----:|-------:|---:|-----:|
| claude-opus-4-6-20250514 | 96.3 | 1.000 | 1.000 | 1.000 | 96.3 |
| claude-sonnet-4-6-20250514 | 88.9 | 0.991 | 1.000 | 0.995 | 88.9 |
| qwen3.5-397b-a17b | 81.5 | 0.994 | 0.969 | 0.978 | 81.5 |
| claude-haiku-4-5-20251001 | 77.8 | 0.978 | 0.948 | 0.958 | 77.8 |
| llama3.1:8b | 74.1 | 0.943 | 0.916 | 0.925 | 74.1 |
| llama-3.1-8b-instruct | 59.3 | 0.866 | 0.830 | 0.836 | 59.3 |


## 3. Accuracy by Tier

| Tier | claude-opus-4-6-20250514 | claude-sonnet-4-6-20250514 | qwen3.5-397b-a17b | claude-haiku-4-5-20251001 | llama3.1:8b | llama-3.1-8b-instruct |
|------|-----:|-----:|-----:|-----:|-----:|-----:|
| 1 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 62.5 |
| 2 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 83.3 |
| 3 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| 4 | 66.7 | 33.3 | 33.3 | 0.0 | 0.0 | 0.0 |
| 5 | 100.0 | 80.0 | 40.0 | 40.0 | 20.0 | 20.0 |

## 4. Accuracy by Answer Type

| Answer Type | claude-opus-4-6-20250514 | claude-sonnet-4-6-20250514 | qwen3.5-397b-a17b | claude-haiku-4-5-20251001 | llama3.1:8b | llama-3.1-8b-instruct |
|-------------|-----:|-----:|-----:|-----:|-----:|-----:|
| order_list | 100.0 | 92.3 | 76.9 | 76.9 | 69.2 | 46.2 |
| order_status | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 90.9 |
| prioritized_list | 66.7 | 33.3 | 33.3 | 0.0 | 0.0 | 0.0 |

## 5. Failure Analysis

### 5.1 Failure Type Breakdown

| Model | extra_orders | invalid_json | missing_orders | wrong_order_ids | wrong_order_sequence | Total |
|-------|-----:|-----:|-----:|-----:|-----:|------:|
| claude-opus-4-6-20250514 | 0 | 0 | 0 | 0 | 1 | 1 |
| claude-sonnet-4-6-20250514 | 1 | 0 | 0 | 0 | 2 | 3 |
| qwen3.5-397b-a17b | 1 | 0 | 3 | 0 | 1 | 5 |
| claude-haiku-4-5-20251001 | 1 | 0 | 3 | 1 | 1 | 6 |
| llama3.1:8b | 1 | 0 | 2 | 4 | 0 | 7 |
| llama-3.1-8b-instruct | 2 | 2 | 4 | 3 | 0 | 11 |

### 5.2 Hardest Scenarios

| Scenario | Tier | Answer Type | Accuracy% | Total Evals |
|----------|-----:|-------------|----------:|------------:|
| QR-021 | 4 | prioritized_list | 0.0 | 33 |
| QR-023 | 5 | order_list | 18.2 | 33 |
| QR-020 | 4 | prioritized_list | 21.2 | 33 |
| QR-026 | 5 | order_list | 24.2 | 33 |
| QR-024 | 5 | order_list | 36.4 | 33 |
| QR-022 | 4 | prioritized_list | 45.5 | 33 |
| QR-001 | 1 | order_list | 50.0 | 36 |
| QR-025 | 5 | order_list | 60.6 | 33 |
| QR-007 | 1 | order_list | 72.2 | 36 |
| QR-008 | 1 | order_list | 75.0 | 36 |

### 5.3 Non-Viable Models

No models exceeded the structural failure threshold.

## 6. Secondary Metrics

### 6.1 Latency and Token Usage

| Model | Mean (ms) | p50 (ms) | p95 (ms) | Tokens In | Tokens Out |
|-------|----------:|---------:|---------:|----------:|-----------:|
| claude-opus-4-6-20250514 | 4943 | 4428 | 9257 | 1777 | 211 |
| claude-sonnet-4-6-20250514 | 5573 | 4373 | 15364 | 1777 | 200 |
| qwen3.5-397b-a17b | 2977 | 2556 | 5767 | 1651 | 126 |
| claude-haiku-4-5-20251001 | 2186 | 1982 | 3202 | 1777 | 170 |
| llama3.1:8b | 11789 | 12527 | 14157 | 1480 | 75 |
| llama-3.1-8b-instruct | 2635 | 2359 | 4838 | 1483 | 73 |
