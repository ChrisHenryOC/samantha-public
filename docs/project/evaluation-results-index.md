# Evaluation Results Index

Master index of all evaluation documents and raw data across project phases.

## Phase 3 — Local Model Feasibility

Evaluated whether local LLMs can handle laboratory workflow routing at all.

| Document | Description |
|----------|-------------|
| [local-model-feasibility-results.md](local-model-feasibility-results.md) | Initial feasibility testing of local models |
| [quantization-impact-results.md](quantization-impact-results.md) | Impact of quantization on model accuracy |
| [connector-integration-results.md](connector-integration-results.md) | Ollama and cloud API connector validation |

## Phase 4 — Baseline Evaluation (No RAG)

Full evaluation of 7 routing models and 6 query models without RAG context.

| Document | Description |
|----------|-------------|
| [phase4-routing-baseline-results.md](phase4-routing-baseline-results.md) | Routing baseline: 7 models, 104 scenarios, 5 runs each |
| [phase4-query-baseline-results.md](phase4-query-baseline-results.md) | Query baseline: 6 models, 27 scenarios |
| [phase4-combined-report.md](phase4-combined-report.md) | Combined routing + query analysis with go/no-go assessment |

## Phase 5 — RAG-Augmented Evaluation

Full evaluation with RAG-retrieved SOP context. New local model roster.

| Document | Description |
|----------|-------------|
| [phase5-routing-rag-results.md](phase5-routing-rag-results.md) | Routing with RAG: 9 models, 105 scenarios |
| [phase5-query-rag-results.md](phase5-query-rag-results.md) | Query with RAG: 9 models, 27 scenarios |

## Phase 6 — Analysis and Refinement

| Document | Description |
|----------|-------------|
| [rag-vs-baseline-comparison.md](rag-vs-baseline-comparison.md) | Phase 6a: RAG vs baseline comparison for overlapping cloud models |
| [rag-rule-accuracy-root-cause.md](rag-rule-accuracy-root-cause.md) | Phase 6b: Root cause analysis of rule accuracy collapse |
| [query-failure-analysis-phase6c.md](query-failure-analysis-phase6c.md) | Phase 6c: Tier 4/5 query failure analysis and prompt refinements |
| [phase6d-rag-tuning-results.md](phase6d-rag-tuning-results.md) | Phase 6d: RAG retrieval tuning results — routing gains, query regression, decision analysis |

## Model Selection and Prompt Tuning (GH #216, #219)

Local model selection funnel and prompt engineering experiments.

| Document | Description |
|----------|-------------|
| [model-selection-prompt-tuning-results.md](model-selection-prompt-tuning-results.md) | Full narrative: Phase 1-2 model selection, Phase 3a prompt tuning, failure analysis, architectural pivot to hybrid routing |
| [skill-vs-baseline-results.md](skill-vs-baseline-results.md) | Skill-based routing A/B comparison: skills vs few-shot on 33-scenario screening set (GH #221) |
| [h2h-coder-vs-70b-results.md](h2h-coder-vs-70b-results.md) | Head-to-head: Coder 32B vs 70B vs cloud models on screening + accumulated state (GH #221) |

## Next-Generation Model Evaluation (GH #224 follow-up)

Benchmarking newer model releases against the Coder 32B production baseline.

| Document | Description |
|----------|-------------|
| `results/qwen3_coder_30b_full/` | Qwen3 Coder 30B-A3B full suite: 113 scenarios, 5 runs — 97.3% ±1.0 accuracy at 3.3s/step |
| `results/benchmark_coder25_32b/` | Qwen2.5 Coder 32B 5-scenario revalidation (90.9% on hard subset) |
| `results/benchmark_coder3_30b/` | Qwen3 Coder 30B-A3B 5-scenario quick benchmark (95.5%) |
| `results/benchmark_ollama_mlx/` | Ollama MLX preview benchmark — Qwen3.5 35B-A3B (63.6%, thinking model issues) |
| `results/benchmark_llamacpp/` | llama.cpp benchmark — Qwen3.5 35B-A3B (77.3%, thinking model issues) |

### Key Finding: Qwen3 Coder 30B-A3B (2026-04-04)

Full 113-scenario, 5-run evaluation of Qwen3 Coder 30B-A3B (MoE, 3B active params):

| Metric | Qwen2.5 Coder 32B | Qwen3 Coder 30B-A3B | Delta |
|--------|-------------------|---------------------|-------|
| State accuracy | 99.7% ±0.5 | 97.3% ±1.0 | -2.4pp |
| Rule match | 99.1% | 93.8% | -5.3pp |
| Flag match | 99.7% | 92.9% | -6.8pp |
| p50 latency | ~20,000ms | 3,261ms | **6.1x faster** |
| Memory (Q4_K_M) | ~20GB | ~17GB | -15% |

Trade-off: 2.4pp accuracy loss for 6x speed improvement. Rule and flag
gaps are addressable by the hybrid deterministic validation layer.
Strong candidate for production if latency matters more than the last
2% of accuracy.

## Tool-Assisted Routing Experiment (GH #228)

### Experiment Design

Two experiments tested whether architectural changes could close the accuracy
gap between Qwen3 Coder 30B-A3B (93.7%) and Qwen2.5 Coder 32B (99.7%):

1. **Tiered model routing** (negative result): Route deterministic steps to a
   fast model and judgment steps to Coder 32B. Failed — all models score 100%
   on judgment steps; failures are in deterministic rules, not judgment calls.
2. **Tool-assisted routing (lite)**: Give the model a `list_applicable_rules`
   tool that returns all rules for the current workflow state before it
   evaluates them. The model calls this tool first (1 round trip), then
   evaluates each rule itself and produces the routing JSON.

### What `routing_tools_lite` Does

- **The tool**: `list_applicable_rules` takes a workflow state and returns
  every rule that could apply at that state, with trigger descriptions.
- **What the model does**: Calls the tool once, then evaluates all returned
  rules against the order data using its own reasoning. Performs all
  arithmetic (threshold comparisons), field validation, and set membership
  checks itself.
- **Why this helps**: The primary failure mode was multi-rule satisficing —
  the model would find one matching rule and stop, missing others. The tool
  ensures it sees the complete rule list.
- **Why only one tool**: The full tool set (4 tools: check_threshold,
  check_field_present, check_enum_membership, list_applicable_rules) required
  15+ round trips per step (one tool call per turn). This exceeded the turn
  limit on most scenarios.
- **Model compatibility**: Requires native structured function calling.
  Qwen2.5 Coder 32B does not support this (returns tool calls as prose).
  Qwen3 Coder 30B-A3B and Gemma 4 26B-A4B both have native support.
  The tool generalizes across model families — tested on both Qwen and Gemma.

### Results: Qwen3 Coder 30B-A3B (2026-04-05)

33-scenario screening set, 5 runs:

| Approach | State Acc | Rule Acc | Flag Acc | Reliability | p50 Latency |
|----------|-----------|----------|----------|-------------|-------------|
| Skills-only baseline | 93.7% | 87.6% | 92.1% | — | 3,329ms |
| **+ list_applicable_rules tool** | **98.0% ±1.2** | **95.9%** | **98.6%** | **84.2%** | **4,188ms** |

The tool closed more than half the gap to Coder 32B (+4.3pp state accuracy,
+8.3pp rule accuracy, +6.5pp flag accuracy) with only ~25% latency increase.

### Results: Gemma 4 26B-A4B (2026-04-05)

33-scenario screening set, 5 runs. Gemma 4 is a MoE model (4B active params)
with native function-calling support and extended thinking.

| Approach | State Acc | Rule Acc | Flag Acc | Reliability | p50 Latency |
|----------|-----------|----------|----------|-------------|-------------|
| Skills-only baseline | 98.7% ±0.5 | 96.0% | 97.3% | 81.8% | 12,706ms |
| **+ list_applicable_rules tool** | **99.8% ±0.4** | **99.8%** | **98.9%** | **96.4%** | **17,512ms** |

Gemma 4 26B-A4B with tool-assisted routing **matches the Coder 32B ceiling**
(99.7%) and exceeds it on rule accuracy (99.8% vs 98.8%). The tool improved
every metric: +1.1pp state, +3.8pp rules, +1.6pp flags, +14.6pp reliability.

### Full Tool Set vs Lite: More Tools ≠ Better (2026-04-06)

Tested the full 4-tool set (check_threshold, check_field_present,
check_enum_membership, list_applicable_rules) with `parallel_tool_calls`
enabled on Gemma 4 26B-A4B. Despite Gemma 4's native parallel function
calling support, the full tool set performed **worse** than the single-tool
lite approach.

| Gemma 4 26B-A4B Approach | State Acc | Rule Acc | Flag Acc | Reliability | p50 |
|--------------------------|-----------|----------|----------|-------------|-----|
| **+ list_applicable_rules only (lite)** | **99.8%** | **99.8%** | **98.9%** | **96.4%** | **17,512ms** |
| Skills-only | 98.7% | 96.0% | 97.3% | 81.8% | 12,706ms |
| + all 4 tools (full) | 98.2% | 96.6% | 98.4% | 87.9% | 14,724ms |

The full tool set (98.2%) scored 1.6pp below lite (99.8%) and only
marginally above skills-only (98.7%). Consistent failures on SC-010
(5/5 runs), SC-016 (max_turns exceeded 3/5), and SC-082 (5/5) — all
scenarios that passed with the lite approach.

**Why more tools hurt**: The individual check tools (check_threshold,
check_field_present, check_enum_membership) don't improve accuracy because
the model already evaluates these conditions correctly with thinking mode.
The extra round trips add turn exhaustion risk and more opportunities for
the model to produce malformed responses. The single `list_applicable_rules`
tool targets the one failure mode the model can't self-correct: not knowing
which rules to evaluate.

### Key Finding: `list_applicable_rules` Generalizes Across Models

The same single tool improved accuracy for both model families:

| Model | Skills-only | + Tool | Improvement |
|-------|-------------|--------|-------------|
| Qwen3 Coder 30B-A3B | 93.7% | 98.0% | +4.3pp |
| Gemma 4 26B-A4B | 98.7% | 99.8% | +1.1pp |

The tool addresses the same failure mode in both: multi-rule satisficing,
where the model finds one matching rule and stops. Providing the complete
rule list before evaluation ensures no rules are missed. The improvement
is larger for models with lower baselines (Qwen3 Coder gained more because
it had more room to improve).

### Full Comparison Table

| Model | Approach | State Acc | Rule Acc | Flag Acc | p50 Latency |
|-------|----------|-----------|----------|----------|-------------|
| Qwen2.5 Coder 32B | Skills-only | 99.7% ±0.5 | 98.8% | 100% | 20,204ms |
| **Gemma 4 26B-A4B** | **+ tool** | **99.8% ±0.4** | **99.8%** | **98.9%** | **17,512ms** |
| Gemma 4 26B-A4B | Skills-only | 98.7% ±0.5 | 96.0% | 97.3% | 12,706ms |
| Qwen3 Coder 30B-A3B | + tool | 98.0% ±1.2 | 95.9% | 98.6% | 4,188ms |
| Gemma 4 E4B | + tool | 97.5% ±0.4 | 90.1% | 64.5% | 7,347ms |
| Gemma 4 E2B | + tool | 95.5% ±1.4 | 87.6% | 66.3% | 6,906ms |
| Qwen3 Coder 30B-A3B | Skills-only | 93.7% | 87.6% | 92.1% | 3,329ms |
| Mistral Small 3.2 24B | + tool | 92.1% ±0.8 | 89.5% | 98.4% | 15,469ms |
| Llama 4 Scout 17B | + tool | — | — | — | OOM on 64GB M5 Pro |
| Gemma 3 27B | Skills-only | 89.2% | 87.4% | 100% | 3,479ms |

### Gemma 4 Scaling: Model Size vs Accuracy (2026-04-06)

The Gemma 4 family shows a clear accuracy cliff between the 26B MoE and
smaller variants:

| Model | Effective Params | Q4 Size | State Acc | Flag Acc | Reliability | p50 |
|-------|-----------------|---------|-----------|----------|-------------|-----|
| Gemma 4 26B-A4B + tool | 4B active / 26B total | ~15GB | 99.8% | 98.9% | 96.4% | 17,512ms |
| Gemma 4 E4B + tool | 4.5B effective | ~5GB | 97.5% | 64.5% | 46.7% | 7,347ms |
| Gemma 4 E2B + tool | 2.3B effective | ~3GB | 95.5% | 66.3% | 41.8% | 6,906ms |

Both smaller models achieve reasonable state accuracy (95-97%) but
collapse on flags and reliability. E4B has 35.5% false positive rate,
E2B has 33.2%. Both hallucinate flags that shouldn't be set and fail
consistently on multi-step scenarios (SC-019 through SC-028, SC-038,
SC-045, SC-087, SC-109-SC-111).

E2B is additionally unstable across runs (±1.4 variance vs 26B-A4B's
±0.4), and starts failing scenarios that E4B passes (SC-081, SC-112,
SC-016 on later runs).

The MoE architecture of the 26B-A4B (26B total parameters with 4B
active) provides access to significantly more knowledge than either
smaller variant, even though active compute is similar. The total
parameter count — not just active parameters — determines whether
the model can handle complex multi-step workflow reasoning. There is
a clear minimum viable model size for this workload that falls between
E4B (4.5B, not viable) and 26B-A4B (26B total, production-grade).

### Accumulated State Results: Gemma 4 26B-A4B (2026-04-07)

10 accumulated state scenarios (SC-090 through SC-099), 5 runs each. These
scenarios test multi-step workflows where the model must track flags across
14 steps per scenario.

| Gemma 4 26B-A4B Approach | State Acc | Rule Acc | Flag Acc | Reliability | p50 |
|--------------------------|-----------|----------|----------|-------------|-----|
| **Skills-only** | **99.6% ±0.6** | **99.6%** | **97.4%** | **72.0%** | **13,708ms** |
| + list_applicable_rules (lite) | 100.0% ±0.0 | 100.0% | 95.6% | 48.0% | 12,830ms |

**Skills-only wins on accumulated state.** The tool achieves perfect
state/rule accuracy but *degrades* flag accuracy (95.6% vs 97.4%) and
reliability (48% vs 72%). The tool mode generates many "returned reasoning
but no content" warnings — the model exhausts its thinking token budget on
tool-call reasoning, leaving insufficient tokens for flag output.

Accumulated state comparison across all tested models (skills-only for
all except where noted):

| Model | State Acc | Rule Acc | Flag Acc | Reliability |
|-------|-----------|----------|----------|-------------|
| **Gemma 4 26B-A4B** | **99.6%** | **99.6%** | **97.4%** | **72.0%** |
| Gemma 3 27B | 100.0% | 100.0% | 97.1% | 60.0% |
| Llama 3.3 70B | 97.9% | 97.9% | 95.7% | 40.0% |
| Qwen3 32B (cloud) | 97.9% | 97.1% | 95.0% | 30.0% |
| Qwen2.5 Coder 32B | 95.0% | 95.0% | 96.4% | 0.0% |

Gemma 4 26B-A4B has the **highest reliability of any model tested** on
accumulated state (72% vs Gemma 3's 60%). It also has the second-highest
state accuracy (99.6% vs Gemma 3's 100%).

#### Flag Failure Analysis

Every flag failure follows the same pattern: the model predicts `[]` (empty)
when a flag should be set. Three specific flags account for all failures:

| Flag | Scenarios | Skills Fails | Tools Fails | Root Cause |
|------|-----------|-------------|-------------|------------|
| `MISSING_INFO_PROCEED` | SC-090, SC-091, SC-097, SC-098 | 4 steps | 16 steps | Token exhaustion in tool mode; intermittent in skills |
| `FIXATION_WARNING` | SC-092 | 5/5 runs | 5/5 runs | Knowledge gap — model never sets this flag |
| `HER2_FIXATION_REJECT` | SC-094 | 5/5 runs | 5/5 runs | Knowledge gap — model never sets this flag |

SC-093, SC-095, SC-096, SC-099 are clean across all runs in both modes.

**Token budget experiment**: Bumping `max_tokens` from 16,384 to 32,768
reduced SC-090 step-2 failures from 4/5 to 1/3 runs in tool mode, confirming
the token exhaustion hypothesis for `MISSING_INFO_PROCEED`. The
`FIXATION_WARNING` and `HER2_FIXATION_REJECT` failures persisted, confirming
those are knowledge gaps, not token issues.

### Results Data

| Document | Description |
|----------|-------------|
| `results/gemma4_26b_accstate_skills/` | Gemma 4 26B-A4B accumulated state skills-only: 10 scenarios, 5 runs — 99.6% ±0.6, 72% reliability |
| `results/gemma4_26b_accstate_tools_lite/` | Gemma 4 26B-A4B accumulated state tool-assisted: 10 scenarios, 5 runs — 100% state but 48% reliability |
| `results/gemma4_26b_accstate_32k_test/` | max_tokens 32k test: SC-090 + SC-092, 3 runs — confirms token exhaustion hypothesis |
| `results/gemma4_26b_tools_lite/` | Gemma 4 26B-A4B tool-assisted lite: 33 scenarios, 5 runs — 99.8% ±0.4 |
| `results/gemma4_26b_tools_full/` | Gemma 4 26B-A4B full 4-tool set: 33 scenarios, 5 runs — 98.2% (negative: worse than lite) |
| `results/gemma4_26b_skills/` | Gemma 4 26B-A4B skills-only: 33 scenarios, 5 runs — 98.7% ±0.5 |
| `results/gemma4_e4b_tools_lite/` | Gemma 4 E4B tool-assisted lite: 33 scenarios, 5 runs — 97.5% state but 64.5% flags |
| `results/gemma4_e2b_tools_lite/` | Gemma 4 E2B tool-assisted lite: 33 scenarios, 5 runs — 95.5% state but 66.3% flags |
| `results/mistral_small_tools_lite/` | Mistral Small 3.2 24B tool-assisted lite: 33 scenarios, 5 runs — 92.1% ±0.8 |
| `results/tool_assisted_lite_coder3/` | Qwen3 Coder tool-assisted lite: 33 scenarios, 5 runs — 98.0% ±1.2 |
| `results/tool_assisted_smoke/` | Smoke test: SC-003, 1 run — 100% |
| `results/tiered_routing_analysis.md` | Tiered routing analysis (negative result) |
| `data/step_classifications.json` | Step classification: 105 deterministic, 6 judgment |
| `docs/project/tiered-model-routing-experiment.md` | Tiered routing experiment design |
| `docs/project/tool-assisted-routing-experiment.md` | Tool-assisted routing experiment design |

## Raw Data Inventory

### `results/` — Current Phase 6d RAG evaluation data (post-tuning)

| Directory | Contents |
|-----------|----------|
| `results/routing_rag/` | 6 local model directories with per-run JSON, summary.json, evaluation.db, run.log |
| `results/query_rag/` | 6 local model directories with per-run query JSON, query_summary.json, evaluation.db, run.log |
| `results/routing_baseline/` | 6 local model baseline (7-scenario subset), summary.json |

### `results_query-routing_03-10-2026/` — Phase 5 RAG evaluation data (pre-tuning)

| Directory | Contents |
|-----------|----------|
| `results_query-routing_03-10-2026/routing_rag/` | Phase 5 routing per-run data (pre-tuning snapshot) |
| `results_query-routing_03-10-2026/query_rag/` | Phase 5 query per-run data (pre-tuning snapshot) |

### `data/evaluation_summaries/` — Git-tracked summary copies

| File | Contents |
|------|----------|
| `data/evaluation_summaries/routing_rag_summary.json` | Phase 5 routing summary (committed copy) |
| `data/evaluation_summaries/query_rag_summary.json` | Phase 5 query summary (committed copy) |

### `results-old/` — Historical evaluation data

| Directory | Phase | Contents |
|-----------|-------|----------|
| `results-old/model_feasibility/` | 3 | Initial local model feasibility test runs |
| `results-old/quantization_impact/` | 3 | Quantization comparison runs |
| `results-old/connector_tests/` | 3 | Connector integration test outputs |
| `results-old/routing_baseline/` | 4 | Routing baseline: 7 models × 5 runs, summary.json, analysis.md |
| `results-old/routing_baseline_backup/` | 4 | Backup of routing baseline before scenario changes |
| `results-old/query_baseline/` | 4 | Query baseline: 6 models, query_summary.json, query_analysis.md |
| `results-old/phase4_baseline_report/` | 4 | Combined Phase 4 report (phase4_report.md) |
| `results-old/sc104_validation/` | 4 | Targeted validation of scenario SC-104 |
| `results-old/new_scenarios/` | 4 | Test runs for newly added scenarios |
| `results-old/routing_rag/` | 5 (early) | Earlier RAG routing test runs |
| `results-old/query_rag/` | 5 (early) | Earlier RAG query test runs |
| `results-old/test-run/` | — | Test/debug runs |
| `results-old/claude-*/` | 4 | Per-model run archives (cloud models) |
| `results-old/google_gemma-3-27b-it/` | 4-5 | Gemma 3 27B run archives |
| `results-old/llama3_1_8b/` | 4 | Llama 3.1 8B run archives |
| `results-old/microsoft_phi-4/` | 5 | Phi-4 run archives |
| `results-old/mistralai_*/` | 5 | Mistral Small 3.2 run archives |
| `results-old/qwen_*/` | 5 | Qwen model family run archives |

## Model Roster by Phase

### Phase 4 Local Models

- gemma-2-27b-it, mistral-7b-instruct, llama-3.1-8b-instruct, qwen-2.5-coder-32b-instruct

### Phase 5 Local Models

- qwen3-8b, phi-4, qwen3-32b, mistral-small-3.2-24b-instruct, gemma-3-27b-it, qwen3.5-35b-a3b

### Cloud Models (Both Phases)

- claude-haiku-4-5-20251001, claude-sonnet-4-6-20250514, claude-opus-4-6-20250514
