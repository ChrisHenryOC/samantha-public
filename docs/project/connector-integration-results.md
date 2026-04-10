# Connector Integration Test Results

**Date:** 2026-02-23
**Hardware:** Apple M4 MacBook Air, 32GB RAM
**Cloud provider:** OpenRouter
**Models tested:** 4 local (Ollama), 3 cloud (OpenRouter)
**Scenarios:** 5 routing, 3 query
**Related PR:** [#96](https://github.com/ChrisHenryOC/samantha/pull/96) (prompt state/flag vocabularies)

## Summary

All 7 model adapters (4 Ollama, 3 OpenRouter) were exercised across 5
routing scenarios and 3 query scenarios. This is the first end-to-end
test of the connector layer with the updated routing prompt that includes
explicit state and flag vocabularies (PR #96).

Key findings:

- **All connectors working.** Every adapter produced structured JSON
  responses with no connection failures or parsing errors.
- **mistral:7b is non-viable.** It scored 0/5 on state accuracy,
  echoing the current state (`ACCESSIONING`) instead of determining
  the next state. Eliminated from further evaluation.
- **Qwen2.5:32b and Claude Haiku 4.5 achieved perfect routing.**
  5/5 state, 5/5 rules, 5/5 flags on all routing scenarios.
- **SC-004 (multi-rule) remains the hardest routing scenario.** Three
  models missed at least one rule on this scenario.
- **Query accuracy is weaker than routing across all models.** QR-001
  (ACCEPTED state lookup) was the most commonly failed query scenario.

## Routing Results

| Model | Provider | SC-001 | SC-002 | SC-003 | SC-004 | SC-005 | State | Rules | Flags |
|-------|----------|--------|--------|--------|--------|--------|-------|-------|-------|
| llama3.1:8b | ollama | S R F | S R F | S . F | S . F | S R F | 5/5 | 3/5 | 5/5 |
| mistral:7b | ollama | . . F | . . F | . . F | . . F | . . F | 0/5 | 0/5 | 5/5 |
| gemma2:27b | ollama | S R F | S R F | S R F | S . F | S R F | 5/5 | 4/5 | 5/5 |
| Qwen2.5:32b | ollama | S R F | S R F | S R F | S R F | S R F | 5/5 | 5/5 | 5/5 |
| Haiku 4.5 | openrouter | S R F | S R F | S R F | S R F | S R F | 5/5 | 5/5 | 5/5 |
| Sonnet 4.6 | openrouter | S R F | S R F | S . F | S R . | S . F | 5/5 | 3/5 | 4/5 |
| Opus 4.6 | openrouter | S R F | S R F | S R F | S R . | S R F | 5/5 | 5/5 | 4/5 |

Legend: **S** = state correct, **R** = rules correct, **F** = flags correct,
**.** = incorrect.

### Aggregate Routing Accuracy

| Model | State % | Rules % | Flags % |
|-------|---------|---------|---------|
| llama3.1:8b | 100 | 60 | 100 |
| mistral:7b | 0 | 0 | 100 |
| gemma2:27b | 100 | 80 | 100 |
| Qwen2.5:32b | 100 | 100 | 100 |
| Haiku 4.5 | 100 | 100 | 100 |
| Sonnet 4.6 | 100 | 60 | 80 |
| Opus 4.6 | 100 | 100 | 80 |

## Query Results

| Model | Provider | QR-001 | QR-002 | QR-003 | Accuracy |
|-------|----------|--------|--------|--------|----------|
| llama3.1:8b | ollama | X | O | O | 2/3 |
| mistral:7b | ollama | X | X | O | 1/3 |
| gemma2:27b | ollama | X | O | O | 2/3 |
| Qwen2.5:32b | ollama | X | O | O | 2/3 |
| Haiku 4.5 | openrouter | X | O | O | 2/3 |
| Sonnet 4.6 | openrouter | O | O | O | 3/3 |
| Opus 4.6 | openrouter | O | O | O | 3/3 |

Legend: **O** = order IDs correct, **X** = incorrect.

QR-001 (orders in ACCEPTED state) was the hardest query scenario —
only Claude Sonnet and Opus answered it correctly. All local models
returned extra or wrong order IDs.

## Failure Analysis

### mistral:7b — Non-viable

Mistral predicted `ACCESSIONING` (the current state, not a valid
next state) on all 5 routing scenarios. It is echoing the input
rather than reasoning about the transition. With 0% state accuracy
it is eliminated from further evaluation.

### SC-004 Multi-Rule Difficulty

SC-004 requires identifying both ACC-001 (patient name missing,
HOLD) and ACC-007 (billing missing, PROCEED), with HOLD winning
the severity conflict. Three models struggled:

- **llama3.1:8b** predicted ACC-001 + ACC-002 (wrong second rule)
- **gemma2:27b** predicted only ACC-001 (missed ACC-007 entirely)
- **Sonnet 4.6** got both rules correct but added a spurious
  `MISSING_INFO_PROCEED` flag

### Sonnet's Extra ACC-008 Pattern

Sonnet 4.6 appended ACC-008 to its rule lists on SC-003 and SC-005.
ACC-008's trigger is "all validations pass," which means all
demographic, specimen, and fixation checks must succeed. In both
SC-003 and SC-005, demographic fields are missing (triggering
ACC-001 or ACC-002), so ACC-008's trigger condition is false.
Sonnet is incorrectly evaluating ACC-008's trigger — this is a
rule-matching error, not a scoping ambiguity. The prompt may need
clearer language about ACC-008 being mutually exclusive with any
other accessioning rule.

### MISSING_INFO_PROCEED Flag on SC-004

Both Sonnet 4.6 and Opus 4.6 emitted `MISSING_INFO_PROCEED` as a
flag on SC-004. The ground truth expects no flags, assuming that
the HOLD severity suppresses all actions from lower-severity rules.

However, the rule catalog states that severity determines the
*routing* (state transition), not explicitly that it suppresses
*flag-setting* from lower-severity rules. ACC-007 genuinely matched
(billing is missing) and its action includes setting
`MISSING_INFO_PROCEED`. Two strong reasoning models independently
followed this interpretation, suggesting the spec is ambiguous
rather than the models being clearly wrong.

This ambiguity should be resolved before Phase 4 evaluation to
avoid polluting flag accuracy metrics.

### QR-001 Query Failures

QR-001 asks for orders in the ACCEPTED state from a mixed-state
dataset. Five of seven models returned incorrect order ID lists:

- **llama3.1:8b** returned 5 IDs (2 extra)
- **mistral:7b** returned 4 IDs (1 extra)
- **gemma2:27b** returned 2 wrong IDs (0 overlap with expected)
- **Qwen2.5:32b** returned 2 wrong IDs (0 overlap with expected)
- **Haiku 4.5** returned an empty list

This suggests the query prompt or data presentation needs improvement
before Phase 4 evaluation. Routing accuracy is significantly stronger
than query accuracy.

## Latency

### Average Routing Latency (ms)

| Model | Provider | Avg Latency |
|-------|----------|-------------|
| Haiku 4.5 | openrouter | 2,659 |
| Sonnet 4.6 | openrouter | 4,310 |
| Opus 4.6 | openrouter | 4,987 |
| llama3.1:8b | ollama | 6,252 |
| mistral:7b | ollama | 8,683 |
| gemma2:27b | ollama | 31,141 |
| Qwen2.5:32b | ollama | 35,116 |

### Average Query Latency (ms)

| Model | Provider | Avg Latency |
|-------|----------|-------------|
| Haiku 4.5 | openrouter | 1,944 |
| Sonnet 4.6 | openrouter | 3,019 |
| Opus 4.6 | openrouter | 2,974 |
| llama3.1:8b | ollama | 10,012 |
| mistral:7b | ollama | 12,892 |
| gemma2:27b | ollama | 40,868 |
| Qwen2.5:32b | ollama | 52,815 |

Cloud models are 2-18x faster than local models. Among local models,
the 7-8B models are 3-5x faster than the 27-32B models.

## Interpretation

### For Phase 4 Planning

1. **mistral:7b is eliminated.** It cannot determine next states
   even with explicit state vocabularies in the prompt.

2. **Three local models remain viable:** llama3.1:8b, gemma2:27b,
   and Qwen2.5:32b. Qwen2.5:32b is the strongest local candidate
   with perfect routing accuracy.

3. **Cloud models confirm the ceiling.** Haiku 4.5 matched
   Qwen2.5:32b's perfect routing accuracy at 13x less latency.
   Opus 4.6 got perfect state and rules but over-flagged on SC-004.

4. **Rule scoping is the main error pattern.** Models that got the
   state wrong (mistral aside) are rare. The common failure is
   listing extra rules or flags — over-application rather than
   hallucination. The prompt may need clearer instructions about
   listing only rules that drive the state transition.

5. **Query scenarios need work.** 5/7 models failed QR-001. Query
   prompt engineering should be improved before running the full
   evaluation harness.

6. **Variance testing is still needed.** These are single-pass
   results (1 run per scenario per model). Phase 4 will run 5x per
   scenario to measure consistency, which is the primary selection
   criterion.
