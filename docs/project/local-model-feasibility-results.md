# Local Model Feasibility Results

**Date:** 2026-02-18
**Hardware:** Apple M4 MacBook Air, 32GB RAM
**Runs per model:** 3 per prompt variant
**Related issue:** [#76](https://github.com/ChrisHenryOC/samantha/issues/76)

## Summary

Six candidate models were evaluated for hardware feasibility (RAM, speed,
JSON output) and instruction-following accuracy (correct state and rule
selection with domain context provided).

Two prompt variants were tested:

- **Baseline** — no domain context; tests whether the model can produce
  valid JSON in the expected structure
- **Enriched** — includes valid workflow states, the accessioning rule
  catalog with severity logic, and valid flags; simulates what will be
  injected into the prompt at inference time (via RAG or prompt template)

## Hardware Feasibility (Baseline Prompt)

| Model | Avg Duration (s) | Avg Tokens/s | JSON Valid | Feasible? |
|-------|-----------------|-------------|------------|-----------|
| phi3:latest | 3.5 | 10.0 | 100% | YES |
| mistral:7b | 4.1 | 5.3 | 100% | YES |
| llama3.1:8b | 4.3 | 4.1 | 100% | YES |
| gemma2:27b | 11.6 | 1.4 | 100% | YES |
| Qwen2.5:32b-instruct-q4_K_M | 16.2 | 1.3 | 100% | YES |
| llama3.3:70b-instruct-q4_K_M | 288.1 | N/A | 0% | NO |

The 70B model exceeded available RAM (~40 GB needed vs 32 GB available),
causing heavy swap usage. Two of three runs timed out at 300s; the third
completed in 264s but returned an empty response.

All other models produced structurally valid JSON 100% of the time within
reasonable timeframes. No swap pressure was observed for any model except
the 70B.

## Accuracy With Domain Context (Enriched Prompt)

Test scenario: straightforward accessioning of a valid breast core biopsy
with all fields present. Expected answer: `ACCEPTED` with rule `ACC-008`.

| Model | Avg Duration (s) | Correct State (3 runs) | Correct Rule (3 runs) | Notes |
|-------|-----------------|----------------------|---------------------|-------|
| llama3.1:8b | 5.2 | 3/3 | 3/3 | Perfect |
| mistral:7b | 6.8 | 3/3 | 3/3 | Perfect, most detailed reasoning |
| gemma2:27b | 20.0 | 3/3 | 3/3 | Perfect, most detailed reasoning of mid-size models |
| Qwen2.5:32b-instruct-q4_K_M | 22.5 | 3/3 | 2/3 | Run 2 wrote `ACC-08` instead of `ACC-008` |
| phi3:latest | 4.1 | 1/3 | 0/3 | Hallucinated rule triggers despite valid context |

### Per-Model Analysis

**llama3.1:8b** — Returned `ACCEPTED` + `ACC-008` on all 3 runs. Reasoning
was concise and accurate. Consistent across runs.

**mistral:7b** — Returned `ACCEPTED` + `ACC-008` on all 3 runs. Provided
the most thorough reasoning, explicitly checking each validation criterion.
Nearly identical output across runs (highest consistency).

**gemma2:27b** — Returned `ACCEPTED` + `ACC-008` on all 3 runs. Provided
thorough reasoning that explicitly referenced breast cancer histology
relevance, fixation range, and billing. Run 1 was slower (32.3s, likely
cold start) but runs 2-3 settled to 11-17s. Approximately 3x slower than
the 7-8B models but faster than Qwen2.5:32b on average.

**Qwen2.5:32b-instruct-q4_K_M** — Returned `ACCEPTED` on all 3 runs.
Correctly identified `ACC-008` on runs 1 and 3. Run 2 wrote `ACC-08`
(dropped a zero) — correct intent but a formatting error that would fail
strict rule ID matching. Approximately 4x slower than the 7-8B models.

**phi3:latest** — Despite being the fastest model, accuracy was poor:

- Run 1: `DO_NOT_PROCESS` + `ACC-003` (claimed left_breast is not
  breast-cancer-relevant — incorrect)
- Run 2: `ACCEPTED` + `ACC-007` (correct state, wrong rule — ACC-007
  is for missing billing, which is present)
- Run 3: `ACCEPTED` + `ACC-002, ACC-003` (hallucinated missing patient sex
  and non-breast site; contradicted by the order data)

Phi3 uses valid states and rule IDs from the provided context but applies
rules to conditions that don't exist in the input data.

## Key Findings

1. **RAG context is essential.** Without domain context (baseline), every
   model hallucinated states and rule IDs. With context (enriched), four
   of five feasible models achieved perfect or near-perfect accuracy on
   the straightforward scenario.

2. **Small models can follow constrained instructions.** The 7-8B parameter
   models (llama3.1, mistral) matched rules correctly when given the rule
   catalog, valid states, and severity hierarchy in the prompt.

3. **More parameters don't guarantee better accuracy on easy scenarios.**
   Gemma2:27b (perfect) and Qwen2.5:32b (near-perfect) were no more
   accurate than the 7-8B models on this test, while being 3-4x slower.
   The harder Phase 3 scenarios will test whether the extra parameters
   help on complex multi-rule cases.

4. **Speed vs accuracy tradeoff is real.** Phi3 is the fastest model
   (3.5-4.1s avg) but the least accurate. Mistral and llama3.1 are
   slightly slower (4-7s) but perfectly accurate. The mid-size and large
   models (gemma2, Qwen2.5) are accurate but 3-4x slower (~11-22s).

5. **The 70B model is infeasible on 32GB hardware.** This was expected
   and is confirmed. There is no practical workaround without significantly
   more RAM or a much smaller quantization that would degrade quality.

6. **This test used one easy scenario.** All models were tested on the
   simplest case (all validations pass). Harder scenarios — missing fields,
   fixation violations, multiple rules firing, severity conflicts — will
   be the real differentiator. These are tested in the full evaluation
   harness (Phase 3).

## Recommendations

### Eliminated

- **llama3.3:70b-instruct-q4_K_M** — infeasible on 32GB hardware.
  Timed out or returned empty responses. No workaround short of
  significantly more RAM.
- **phi3:latest** — hallucinated rule triggers on the simplest scenario
  despite having the correct rule catalog in context. Unreliable
  reasoning makes it unsuitable for a rule-matching task.

### Remaining Candidates

Four models passed hardware feasibility and the enriched prompt accuracy
test. However, this was a single easy scenario (all validations pass).
There is not enough data to recommend a specific model yet.

| Model | Parameters | Status | Rationale |
|-------|-----------|--------|-----------|
| llama3.1:8b | 8B | Proceed to full evaluation | Perfect on enriched test, fastest |
| mistral:7b | 7B | Proceed to full evaluation | Perfect on enriched test, most consistent |
| gemma2:27b | 27B | Proceed to full evaluation | Perfect on enriched test, fills mid-size gap |
| Qwen2.5:32b-instruct-q4_K_M | 32B (Q4) | Proceed to full evaluation | Near-perfect, largest feasible model |

The four candidates span a useful range: two 7-8B models (fast, tests
whether small models suffice), one 27B (mid-size gap filler), and one
32B quantized (tests whether more parameters help on harder scenarios).

### Next Steps

1. Build adapters for the four remaining candidates (Phase 3 adapter work)
2. Run the full evaluation harness with all scenario types — missing
   fields, fixation violations, multiple rules, severity conflicts —
   to differentiate between models
3. Use variance across 5x runs per scenario as the primary selection
   criterion, per the evaluation design

