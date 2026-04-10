# Query Failure Analysis — Phase 6c

Analysis of Tier 4 and Tier 5 query failures from Phase 4 (baseline)
and Phase 5 (RAG) evaluations, with prompt refinements applied.

## Phase 4 Baseline Results (Cloud Models)

| Model | T4 Accuracy | T5 Accuracy | Overall | Primary Failures |
|-------|------------|------------|---------|-----------------|
| Opus  | 66.7%      | 100.0%     | 96.3%   | wrong_order_sequence (1) |
| Sonnet | 33.3%     | 80.0%      | 88.9%   | wrong_order_sequence (2), extra_orders (1) |
| Haiku | 0.0%       | 40.0%      | 77.8%   | wrong_order_sequence (1), missing_orders (3), wrong_order_ids (1) |

## Tier 4 Failure Analysis

All three Tier 4 scenarios are `prioritized_list` queries requiring
multi-key sorting.

### QR-020: "Which grossing orders should I do first?"

- **Expected**: ORD-2004, ORD-2002, ORD-2003, ORD-2005, ORD-2001
- **Failure type**: `wrong_order_sequence` (precision=1.0, recall=1.0)
- **Root cause**: Models get the correct 5 ACCEPTED orders but mis-rank
  routine orders. They struggle with cross-day date comparisons (Jan 14
  vs Jan 15), sometimes treating "06:00 today" as older than "08:00
  yesterday."

### QR-021: "Rank all orders on the IHC bench by urgency"

- **Expected**: ORD-2110, ORD-2102, ORD-2103, ORD-2104, ORD-2105, ORD-2101
- **Failure type**: `wrong_order_sequence` (Opus 5/5), `missing_orders`
  (Haiku — only finds 4/6 IHC orders)
- **Root cause (Opus)**: Fails to rank ORD-2110 (rush, FIXATION_WARNING)
  before ORD-2102 (rush, no flags). The flagged-before-unflagged rule
  was not being applied consistently within the rush tier.
- **Root cause (Haiku)**: Only matches IHC_STAINING, missing IHC_QC and
  IHC_SCORING as "on the IHC bench."

### QR-022: "I have time for 3 more signouts — which ones?"

- **Expected**: ORD-2202, ORD-2204, ORD-2203
- **Performance**: Opus 100%, Sonnet 100%, Haiku 0% (wrong_order_ids)
- **Root cause (Haiku)**: Includes orders not in PATHOLOGIST_SIGNOUT.

## Tier 5 Failure Analysis

Tier 5 scenarios require cross-order reasoning — scanning multiple
orders and applying domain knowledge to filter/classify.

### QR-024: "Do any orders need pathologist attention right now?"

- **Expected**: ORD-2401, ORD-2407, ORD-2403, ORD-2405, ORD-2411
- **Failure type**: `missing_orders` (Sonnet misses 1, Haiku misses 2)
- **Root cause**: Models use a narrow definition of "pathologist
  attention" — typically only PATHOLOGIST_HE_REVIEW. They miss:
  - SUGGEST_FISH_REFLEX (pathologist must approve/decline FISH)
  - PATHOLOGIST_SIGNOUT (pathologist signs out the case)

### QR-026: "Are there any orders that seem stuck?"

- **Expected**: ORD-2605, ORD-2603, ORD-2601
- **Failure type**: `extra_orders` (Sonnet/Haiku include ORD-2611)
- **Root cause**: Models conflate "waiting for a decision" (active
  workflow step like SUGGEST_FISH_REFLEX) with "stuck" (passive hold
  states like FISH_SEND_OUT, MISSING_INFO_HOLD, RESULTING_HOLD).

## Root Causes Summary

1. **Ranking instruction ambiguity**: The 3-bullet ranking rules were
   too vague for multi-key sorting. Models applied rules inconsistently,
   especially across day boundaries.
2. **Missing state grouping context**: Models didn't know that
   IHC_STAINING + IHC_QC + IHC_SCORING all constitute "the IHC bench."
3. **No actor annotations**: Models couldn't quickly determine which
   states require pathologist action vs lab tech action vs passive
   waiting.
4. **Incomplete order_list scanning**: Models stopped after finding the
   most obvious matching state instead of scanning all orders.

## Prompt Refinements Applied

### 1. Enhanced Ranking Instructions (Tier 4 fix)

Replaced vague 3-bullet rules with explicit multi-key sort algorithm
including a worked example with cross-day dates:

```text
Sort key: (priority_rank, flag_rank, created_at)
Example: B (rush, Jan 14) before A (rush, Jan 15) because Jan 14 < Jan 15
```

### 2. State Actor/Group Annotations (Tier 4 + Tier 5 fix)

Added `[actor: pathologist]`, `[actor: held — waiting for external lab]`,
`[group: IHC bench]` annotations to each state in the workflow
reference. This directly addresses:

- "On the IHC bench" queries → states with `group: IHC bench`
- "Needs pathologist attention" → states with `actor: pathologist`
- "Stuck/not progressing" → states with `actor: held`

### 3. Order Sorting by created_at (Tier 4 fix)

Orders are now sorted by `created_at` ascending in the prompt JSON, so
temporal order is visually obvious. Models no longer need to mentally
reorder scattered dates.

### 4. order_list Scan Instructions (Tier 5 fix)

Added answer-type-specific instructions for `order_list` queries:
"Scan EVERY order... include all states that fit the query, not just
the most obvious one."

### 5. Static Reference Caching (GH-130)

Cached `_format_state_reference()` and `_format_flag_definitions()`
output since the StateMachine is a singleton with static config.

## Next Steps

- Re-run query evaluation with cloud models to measure impact
- If Tier 4 improves, run local model evaluation (5x per scenario)
