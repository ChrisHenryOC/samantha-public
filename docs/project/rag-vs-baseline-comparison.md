# Phase 6a — RAG vs Baseline Comparison

- **Date:** 2026-03-10
- **Phase:** 6a (analysis of Phase 4 baseline vs Phase 5 RAG results)
- **Related documents:**
  - [Phase 4 routing baseline](phase4-routing-baseline-results.md)
  - [Phase 4 query baseline](phase4-query-baseline-results.md)
  - [Phase 5 routing RAG](phase5-routing-rag-results.md)
  - [Phase 5 query RAG](phase5-query-rag-results.md)

## 1. Overview

Phase 4 established baseline performance without RAG. Phase 5 added RAG-augmented
context retrieval. This report compares the two to assess whether RAG improved
model performance.

**Key constraint:** Only 3 cloud models (Haiku, Sonnet, Opus) appear in both
phases. The local model rosters are entirely different:

- **Phase 4 local:** gemma-2-27b, mistral-7b, llama-3.1-8b, qwen-2.5-coder-32b
- **Phase 5 local:** qwen3-8b, phi-4, qwen3-32b, mistral-small-3.2-24b, gemma-3-27b, qwen3.5-35b-a3b

Direct baseline-to-RAG comparison is only valid for the 3 cloud models.

**Other changes between phases:**

- Scenario count changed from 104 to 105 (routing)
- Cloud models ran 5x in Phase 4, 1x in Phase 5 (cost constraints)
- Phase 5 used RAG-augmented prompts with retrieved SOP context

## 2. Cloud Model Deltas — Routing

| Model | Baseline Acc% | RAG Acc% | Delta | Baseline Rule% | RAG Rule% | Delta |
|-------|-------------:|--------:|------:|---------------:|---------:|------:|
| Opus | 95.0 | 91.6 | -3.4 | 98.4 | 52.3 | -46.1 |
| Sonnet | 90.4 | 88.3 | -2.1 | 97.8 | 37.5 | -60.3 |
| Haiku | 82.2 | 68.5 | -13.7 | 99.2 | 36.2 | -63.0 |

| Model | Baseline Flag% | RAG Flag% | Delta | Baseline Rel% | RAG Rel% | Delta |
|-------|---------------:|---------:|------:|--------------:|--------:|------:|
| Opus | 97.5 | 91.0 | -6.5 | 57.5 | 0.0 | -57.5 |
| Sonnet | 98.3 | 86.9 | -11.4 | 34.0 | 0.0 | -34.0 |
| Haiku | 97.7 | 91.8 | -5.9 | 16.7 | 0.0 | -16.7 |

### Routing findings

- **State accuracy declined** across all cloud models (-2.1 to -13.7 pp).
  Haiku was hit hardest.
- **Rule accuracy collapsed** (-46 to -63 pp). This is the most concerning
  finding. The RAG context may have diluted or confused rule identification.
- **Scenario reliability dropped to 0%** for all cloud models, meaning no
  scenario had every step (state + rules + flags) all correct. This is driven
  primarily by the rule accuracy collapse.
- **Caveats:** Phase 5 cloud models only ran 1x (vs 5x in Phase 4), so
  variance cannot be compared. The scenario set also changed slightly
  (104 vs 105 scenarios).

### Per-category routing comparison (cloud models)

| Category | Opus P4 | Opus P5 | Sonnet P4 | Sonnet P5 | Haiku P4 | Haiku P5 |
|----------|-------:|-------:|---------:|---------:|--------:|--------:|
| accumulated_state | 94.6 | 89.3 | 90.4 | 83.6 | 86.4 | 65.7 |
| multi_rule | 95.4 | 91.4 | 89.1 | 94.3 | 69.1 | 71.4 |
| rule_coverage | 95.0 | 92.3 | 90.6 | 89.1 | 82.1 | 69.5 |
| unknown_input | 100.0 | 66.7 | 80.0 | 83.3 | 60.0 | 0.0 |

- Sonnet improved slightly on multi_rule (+5.2 pp) and unknown_input (+3.3 pp).
- All other category comparisons show regression.
- Haiku's unknown_input dropped from 60% to 0% — a complete failure.

## 3. Cloud Model Deltas — Query

| Model | Baseline Acc% | RAG Acc% | Delta | Baseline Rel% | RAG Rel% | Delta |
|-------|-------------:|--------:|------:|--------------:|--------:|------:|
| Opus | 96.3 | 88.9 | -7.4 | 96.3 | 88.9 | -7.4 |
| Sonnet | 88.9 | 88.9 | 0.0 | 88.9 | 88.9 | 0.0 |
| Haiku | 77.8 | 81.5 | +3.7 | 77.8 | 81.5 | +3.7 |

| Model | Baseline Prec | RAG Prec | Baseline Rec | RAG Rec | Baseline F1 | RAG F1 |
|-------|-------------:|--------:|------------:|-------:|-----------:|------:|
| Opus | 1.000 | 0.991 | 1.000 | 1.000 | 1.000 | 0.995 |
| Sonnet | 0.991 | 0.951 | 1.000 | 0.932 | 0.995 | 0.938 |
| Haiku | 0.978 | 0.944 | 0.948 | 0.936 | 0.958 | 0.938 |

### Per-tier query comparison (cloud models)

| Tier | Opus P4 | Opus P5 | Sonnet P4 | Sonnet P5 | Haiku P4 | Haiku P5 |
|------|-------:|-------:|---------:|---------:|--------:|--------:|
| T1 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| T2 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| T3 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| T4 | 66.7 | 33.3 | 33.3 | 66.7 | 0.0 | 33.3 |
| T5 | 100.0 | 80.0 | 80.0 | 60.0 | 40.0 | 40.0 |

### Query findings

- **Mixed results:** Opus declined (-7.4 pp), Sonnet unchanged, Haiku improved (+3.7 pp).
- **Precision and recall slightly declined** for Opus and Sonnet, suggesting RAG
  context occasionally introduced noise in order identification.
- **Tier 4 (prioritized lists)** remains the hardest category. Sonnet improved
  on T4 (+33.4 pp) but Opus declined (-33.4 pp) — likely noise from single runs.
- **Overall impact is neutral to slightly negative** for query answering.

## 4. Phase 5 Local Models in Context

Since Phase 4 and Phase 5 used different local models, direct comparison is
impossible. Instead, we assess Phase 5 local models against the cloud ceiling.

### Routing — cloud-local gap

| Model | Acc% | Gap to Opus | Type |
|-------|-----:|------------:|------|
| Opus (ceiling) | 91.6 | — | Cloud |
| Sonnet | 88.3 | 3.3 | Cloud |
| qwen3-8b | 82.5 | 9.1 | Local |
| mistral-small-3.2-24b | 78.5 | 13.1 | Local |
| qwen3.5-35b-a3b | 78.2 | 13.4 | Local |
| Haiku | 68.5 | 23.1 | Cloud |
| gemma-3-27b-it | 65.1 | 26.5 | Local |
| phi-4 | 61.2 | 30.4 | Local |
| qwen3-32b (aborted) | 29.4 | 62.2 | Local |

- **Three local models outperform Haiku** on state accuracy: qwen3-8b (82.5%),
  mistral-small-3.2 (78.5%), qwen3.5-35b-a3b (78.2%).
- The cloud-local gap narrowed significantly vs Phase 4 (34.8 pp in P4 vs
  9.1 pp in P5 for best local).
- Phase 5 used stronger local models (8-35B parameter range) than Phase 4.

### Query — cloud-local gap

| Model | Acc% | Gap to Opus | Type |
|-------|-----:|------------:|------|
| Opus (ceiling) | 88.9 | — | Cloud |
| Sonnet | 88.9 | 0.0 | Cloud |
| Haiku | 81.5 | 7.4 | Cloud |
| qwen3.5-35b-a3b | 76.3 | 12.6 | Local |
| mistral-small-3.2 | 73.3 | 15.6 | Local |
| gemma-3-27b-it | 68.9 | 20.0 | Local |
| qwen3-32b | 63.7 | 25.2 | Local |
| qwen3-8b | 63.0 | 25.9 | Local |
| phi-4 | 59.3 | 29.6 | Local |

- **All cloud models outperform all local models** on query accuracy.
- Best local (qwen3.5-35b-a3b at 76.3%) is 5.2 pp behind Haiku.
- The cloud-local gap in Phase 5 (12.6 pp) is similar to Phase 4 (14.8 pp).

## 5. RAG Impact Assessment

### Did RAG help?

**For routing: No.** RAG degraded performance across the board:

- State accuracy declined for all 3 directly comparable models.
- Rule accuracy collapsed catastrophically (from ~98% to ~40%).
- The most likely explanation: RAG-retrieved SOP chunks introduced confusion
  about which rules to cite, even though the model could still identify the
  correct next state. Rule IDs are specific catalog identifiers that the
  model must match exactly — retrieved context may have presented
  overlapping or adjacent rules that led to incorrect citations.

**For query: Marginally — mixed signals.** One model improved (Haiku +3.7 pp),
one unchanged (Sonnet), one declined (Opus -7.4 pp). With single runs per
cloud model, this is within noise.

### Why did rule accuracy collapse?

The Phase 4 baseline used full context (all SOPs in the prompt). Phase 5 RAG
selectively retrieved relevant chunks. Possible explanations:

1. **Incomplete retrieval:** The RAG system may not retrieve all rule-relevant
   chunks for a given scenario, causing the model to miss applicable rules.
2. **Chunk boundary issues:** Rules that span multiple chunks may be partially
   retrieved, leading to incomplete rule identification.
3. **Context format change:** The shift from structured full-context to
   RAG-retrieved snippets may have confused rule citation formatting.
4. **Rule ID granularity:** The model may identify the correct behavior but
   cite a parent or sibling rule ID instead of the exact expected one.

## 6. Recommendations for Phase 6b-6e

### 6b. Prompt refinement

- Investigate the rule accuracy collapse. Compare the RAG prompt template
  to the baseline template — is rule ID citation explicitly instructed?
- Consider a hybrid approach: always include the rule catalog index in the
  prompt, even with RAG-retrieved context.
- Test whether the state accuracy decline is from prompt formatting or
  from the RAG context itself.

### 6c. RAG tuning

- Audit retrieval coverage: for each scenario, check whether the relevant
  SOP chunks are being retrieved.
- Increase chunk overlap or retrieval top-k to ensure rule completeness.
- Consider rule-specific retrieval: retrieve by rule ID in addition to
  semantic similarity.

### 6d. Scenario improvements

- The 105-scenario set covers routing well but query evaluation has only
  27 scenarios. Expand the query scenario set, especially Tier 4
  (prioritized lists) which has only 3 scenarios.
- Add scenarios that specifically test rule citation accuracy to isolate
  the RAG impact on rule matching vs state prediction.

### 6e. Model selection

- For local deployment, qwen3-8b shows the best routing accuracy (82.5%)
  while being small enough for efficient inference.
- qwen3.5-35b-a3b shows the best query performance (76.3%) among local models.
- Consider a dual-model approach: different models for routing vs query tasks.
