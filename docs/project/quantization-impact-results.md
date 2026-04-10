# Quantization Impact Results

**Date:** 2026-02-20
**Hardware:** Apple M4 MacBook Air, 32GB RAM
**Cloud provider:** OpenRouter
**Related issue:** [#77](https://github.com/ChrisHenryOC/samantha/issues/77)

## Summary

One model required Q4 quantization to fit in 32GB RAM and remained
feasible: **Qwen2.5:32b-instruct-q4_K_M**. The base Qwen2.5-32B-Instruct
is not available on any major cloud API provider (OpenRouter, Together AI,
Groq) — only the Coder and VL variants are hosted. We used
**Qwen2.5-72B-Instruct** (same family, larger, full precision) as an
upper-bound comparison.

The **Llama 3.3 70B** was infeasible locally but tested at full
precision via cloud API as a ceiling benchmark.

**Key finding:** Q4 quantization does not meaningfully degrade structured
output quality for Qwen2.5-32B on this test scenario. The `ACC-08`
formatting error observed in the original feasibility run was intermittent
variance — a fresh 3-run test of the local Q4 model returned `ACC-008`
correctly on all 3 runs.

## Comparison: Qwen2.5 (32B Q4 Local vs 72B FP16 Cloud)

### Enriched Prompt (ACC-008 Scenario)

| Source | Model | Run | JSON | State | Rules | Duration | Notes |
|--------|-------|-----|------|-------|-------|----------|-------|
| Local Q4 | 32B | 1 | Yes | ACCEPTED | ACC-008 | 43.5s | Correct |
| Local Q4 | 32B | 2 | Yes | ACCEPTED | ACC-008 | 17.5s | Correct |
| Local Q4 | 32B | 3 | Yes | ACCEPTED | ACC-008 | 11.2s | Correct |
| Cloud FP16 | 72B | 1 | Yes | ACCEPTED | ACC-008 | 2.7s | Correct |
| Cloud FP16 | 72B | 2 | Yes | ACCEPTED | ACC-008 | 3.1s | Correct |
| Cloud FP16 | 72B | 3 | Yes | ACCEPTED | ACC-008 | 2.6s | Correct |

### Baseline Prompt (No Domain Context)

| Source | Model | Run | JSON | State | Rules | Duration | Notes |
|--------|-------|-----|------|-------|-------|----------|-------|
| Local Q4 | 32B | 1 | Yes | PRE_ANALYSIS | RULE-012 | 30.9s | Hallucinated |
| Local Q4 | 32B | 2 | Yes | RECEIVING | R0102 | 14.5s | Hallucinated |
| Local Q4 | 32B | 3 | Yes | FIXATION_VERIFICATION | RUL-001 | 12.7s | Hallucinated |
| Cloud FP16 | 72B | 1 | Yes | GROSSING | (custom) | 2.6s | Hallucinated |
| Cloud FP16 | 72B | 2 | Yes | GROSSING | (custom) | 2.4s | Hallucinated |
| Cloud FP16 | 72B | 3 | Yes | GROSSING | (custom) | 2.6s | Hallucinated |

Both models hallucinate states and rules without domain context, confirming
the feasibility check finding that RAG context is essential.

### Assessment

The local Q4 Qwen2.5-32B matched the cloud FP16 Qwen2.5-72B perfectly on
the enriched prompt — both achieved 3/3 correct state and rules. The
`ACC-08` typo from the original feasibility run did not reproduce in this
fresh test, suggesting it was random formatting variance rather than a
systematic quantization issue.

The 72B is ~10x faster on cloud infrastructure (2-3s vs 11-44s locally),
but that's expected — the comparison is about output quality, not speed.

## Comparison: Llama 3.3 70B

### Enriched Prompt (ACC-008 Scenario)

| Source | Run | JSON Valid | Correct State | Correct Rules | Duration | Notes |
|--------|-----|-----------|---------------|---------------|----------|-------|
| Local Q4 | — | — | — | — | — | Infeasible (exceeded 32GB) |
| Cloud FP16 | 1 | Yes | ACCEPTED | ACC-008 | 1.6s | Correct |
| Cloud FP16 | 2 | Yes | ACCEPTED | ACC-008 | 4.3s | Correct |
| Cloud FP16 | 3 | Yes | ACCEPTED | ACC-008 | 0.8s | Correct |

### Assessment

At full precision via cloud API, Llama 3.3 70B performs perfectly on this
scenario — 3/3 correct with detailed, accurate reasoning. It's a strong
model that would be a good candidate if hardware constraints were removed
(e.g., a machine with 64+ GB RAM or a cloud-only deployment).

For this project, it remains infeasible as a local candidate.

## Intermediate Quantization Levels

Not needed. The Q4 Qwen2.5-32B performed identically to the full-precision
72B on this test scenario. No evidence that quantization is degrading output
quality.

## Decision

**Q4 quantization has no meaningful impact** on structured output quality
for Qwen2.5-32B on this test scenario. The `ACC-08` formatting error
from the original feasibility run was intermittent variance, not a
systematic quantization artifact.

### Impact on Candidate List

| Model | Previous Status | Updated Status | Rationale |
|-------|----------------|----------------|-----------|
| Qwen2.5:32b Q4 | Candidate | **Keep as candidate** | Q4 output quality matches FP16 family upper bound |
| Llama 3.3 70B | Eliminated (RAM) | **Eliminated (confirmed)** | Strong at FP16 but infeasible on 32GB hardware |

### Caveats

1. This test used a single easy scenario (all validations pass). Harder
   multi-rule scenarios in the full evaluation harness (Phase 4) will
   provide a more rigorous test of whether quantization affects complex
   reasoning.
2. The cloud comparison used Qwen2.5-72B, not an exact 32B FP16 match.
   The 72B has more parameters, so it's an upper bound, not a direct
   control. However, the fact that the local 32B Q4 matched it perfectly
   is a strong signal.
3. The `ACC-08` issue appeared in 1 of 6 total runs (1/3 in the original
   feasibility test, 0/3 in this test). At ~17% occurrence, it may
   reappear in longer evaluation runs. The full harness will measure this
   variance properly with 5x runs per scenario.

## Next Steps

1. Proceed with Qwen2.5:32b-instruct-q4_K_M as a candidate for Phase 3
   adapter work — no quantization level change needed
2. The harder multi-rule scenarios in Phase 4 will provide the definitive
   test of whether quantization affects complex reasoning
3. If the `ACC-08` formatting issue recurs at significant rates during
   Phase 4 evaluation, revisit Q5/Q6 quantization at that point
