# Evaluation Metrics

This document defines how model performance is measured — primary accuracy metrics, diagnostic matrices, secondary metrics, and failure handling.

## Primary Metrics

| Metric | Description |
|--------|-------------|
| **Accuracy (overall)** | % of individual predictions where next_state is correct. Binary — no partial credit. |
| **Accuracy by category** | Broken down by rule coverage / multi-rule / accumulated state / unknown inputs. |
| **Rule selection accuracy** | % of predictions where the model identified the correct rule(s) from the catalog. Scored independently from next_state accuracy to distinguish rule-matching ability from rule-application ability. |
| **Flag accuracy** | % of predictions where the model output the correct flags. Scored independently — flags drive downstream behavior (e.g., MISSING_INFO_PROCEED blocks resulting), so a correct state with wrong flags will cause failures in later steps. |
| **False positive rate** | % of predictions where model suggests an unwarranted action or routing (e.g., flags fixation issue when fixation is fine). |
| **Scenario reliability** | % of complete scenario runs where every step was predicted correctly. This is the key metric — a model that's 95% on individual steps but fails 40% of scenarios is not reliable. |

## Rule Selection Diagnostic Matrix

| Right Rule? | Right State? | Interpretation |
|-------------|-------------|----------------|
| Yes | Yes | Working as intended |
| Yes | No | Can identify rules but fails to apply them correctly |
| No | Yes | Correct by coincidence — unreliable on edge cases |
| No | No | Cannot match or apply rules |

## Secondary Metrics

| Metric | Description |
|--------|-------------|
| **Latency** | Time per prediction (ms). |
| **Token usage** | Input + output tokens per prediction. |
| **Cost per prediction** | Estimated API cost (cloud models only). |
| **Reasoning quality** | Qualitative review of chain-of-thought explanations. Not formally scored, but captured for analysis. Post-evaluation, Claude can be used to analyze reasoning patterns across model outputs (e.g., does the model cite the correct rule, does it explain flag effects). |

## False Positive Definition

A false positive is any model output that:
- Suggests a state transition that is not warranted by the current data
- Flags an issue that does not exist (e.g., fixation concern when fixation is within range)
- Recommends an action not supported by the workflow rules
- Suggests clinical decisions beyond its scope

## Query Evaluation Metrics

The query track measures a different capability than routing — the model must comprehend a natural-language question, locate relevant data in a database state snapshot, and return a structured answer. Metrics are defined per tier.

### Query-Specific Metrics

| Metric | Description |
|--------|-------------|
| **Query comprehension accuracy** | % of queries where the model correctly identified what was being asked (right answer type, right scope). Scored independently from result correctness — a model that understands the question but returns wrong data has a different failure mode than one that misinterprets the question entirely. |
| **Result completeness** | % of expected items present in the model's answer. For order-set answers: size(expected ∩ returned) / size(expected). A model that returns 3 of 5 matching orders scores 60% completeness. |
| **Result correctness** | % of items in the model's answer that are actually correct. For order-set answers: size(expected ∩ returned) / size(returned). A model that returns 5 orders but only 3 are correct scores 60% correctness. |
| **Query accuracy (overall)** | % of queries where the answer is exactly correct — all expected items present, no extra items, correct reasoning where applicable. Binary — no partial credit. |

### Scoring by Tier

| Tier | Answer Type | Scoring Approach |
|------|-------------|------------------|
| **Tier 1 — Simple lookup** | Order list | Exact set match on order IDs. Precision + recall scored separately. |
| **Tier 2 — Order status** | Order status | Exact set match on order IDs. Status summary captured but not auto-scored. |
| **Tier 3 — Flag reasoning** | Order status | Exact set match on order IDs. Status summary captured but not auto-scored. |
| **Tier 4 — Prioritization** | Prioritized list | Exact sequence match on order IDs — same elements in the same order. Partial credit is not given. |
| **Tier 5 — Cross-order reasoning** | Order list | Exact set match on order IDs. Reasoning captured for qualitative analysis. |

### Canonical `answer_type` Values

Each tier uses a distinct `answer_type` string in the query response JSON. These are the exact values the evaluation harness will expect:

| Tier | `answer_type` Value | Required Fields |
|------|---------------------|-----------------|
| 1 | `order_list` | `order_ids`: list of order ID strings, `reasoning`: string |
| 2 | `order_status` | `order_ids`: list of order ID strings, `status_summary`: string, `reasoning`: string |
| 3 | `order_status` | `order_ids`: list of order ID strings, `status_summary`: string, `reasoning`: string |
| 4 | `prioritized_list` | `order_ids`: list of order ID strings (position = priority rank), `reasoning`: string |
| 5 | `order_list` | `order_ids`: list of order ID strings, `reasoning`: string |

All response types also include a `reasoning` field with a brief explanation.

| — | `explanation` | `explanation`: string, `reasoning`: string |

The `explanation` answer type is structurally validated only — no order IDs to compare. It is used for open-ended queries that ask "why" rather than "which orders."

### Query Failure Types

Failures are classified in priority order — the first matching category wins.

| Priority | Failure Type | Description |
|----------|-------------|-------------|
| 1 | `timeout` | Model exceeded the response time limit. |
| 2 | `invalid_json` | Model output could not be parsed as JSON. |
| 3 | `empty_response` | Model returned an empty or null response. |
| 4 | `wrong_field_names` | Required fields for the answer type are missing. |
| 5 | `wrong_field_type` | A required field has the wrong type (e.g., string instead of list). |
| 6 | `wrong_order_ids` | Model returns orders with both missing and extra IDs vs. expected. |
| 7 | `wrong_order_sequence` | For `prioritized_list`: correct set but wrong priority order. |
| 8 | `missing_orders` | Model omits orders that should have been included. |
| 9 | `extra_orders` | Model includes orders that should not be in the result. |

For `explanation` answer type, only structural failures (priorities 1–5) apply. If structurally valid, the result is correct.

All query failures follow the same no-retry policy as routing failures — each failure is scored as incorrect and logged with its failure type. Structural failures (priorities 1–5) are handled identically to routing responses per the Model Failure Handling section below.

## Model Failure Handling

No retries for any failure type — each failure is a meaningful signal about the model's reliability. All failures are scored as incorrect and logged with their failure type for separate reporting.

| Failure Type | Timeout Threshold | Handling |
|-------------|-------------------|----------|
| Invalid JSON | N/A | Score incorrect. Log raw output for analysis. |
| Wrong field names (e.g., `state` instead of `next_state`) | N/A | Score incorrect — treated as invalid output. No lenient parsing. |
| Hallucinated state (not in workflow) | N/A | Score incorrect. Flag separately — different failure mode than picking the wrong valid state. |
| Timeout | 30s local, 60s cloud | Score incorrect. Log separately. |
| Empty/null response | N/A | Score incorrect. Log separately. |

**Extra fields:** If the model returns valid JSON with all required fields plus additional unexpected fields, this is **not** a failure — the response is scored normally. However, extra fields are logged for analysis (may indicate the model is "thinking out loud" in structured output).

Each failure type gets its own counter per model so the evaluation can distinguish "this model gives wrong answers" from "this model returns unusable output." A model with high accuracy but frequent JSON failures is not deployable.

## Related Documents

- [Architecture](architecture.md) — evaluation harness design
- [Scenario Design](../scenarios/scenario-design.md) — what's being evaluated
