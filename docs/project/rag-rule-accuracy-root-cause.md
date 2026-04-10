# Root Cause Analysis: RAG Rule Accuracy Collapse

- **Date:** 2026-03-11
- **Issue:** [#161](https://github.com/ChrisHenryOC/samantha/issues/161)
- **Related:** [RAG vs Baseline Comparison](rag-vs-baseline-comparison.md)

## 1. Summary

Rule accuracy collapsed from 97-99% (baseline) to 36-52% (RAG) across all cloud
models. This analysis identifies **two co-occurring root causes** and one
contributing factor:

1. **Primary: Retrieval misses the actual rules.** The RAG query
   `"workflow state: ACCESSIONING; event: order_received"` retrieves overview and
   summary sections, not the chunks containing rule definitions. The critical
   "3. Validation Checks" chunk (containing ACC-001 through ACC-008 with explicit
   rule IDs) ranks outside the top-20 results. The "Rule Catalog" chunk (a
   compact table of all rules) ranks 8th — just outside the `top_k=5` cutoff.

2. **Primary: Context format lacks rule ID structure.** Even when rule-adjacent
   content is retrieved, RAG chunks are raw markdown prose. The baseline prompt
   formats rules as numbered entries with bold `**ACC-008**` labels, explicit
   trigger/action/severity fields. The RAG prompt substitutes free-form SOP text
   that mentions rules narratively but doesn't present them as an enumerated
   checklist. Models either cite no rules or invent descriptive labels
   (`"missing_patient_name"` instead of `"ACC-001"`).

3. **Contributing: No rule ID citation instruction in RAG mode.** The prompt
   template's `## Your Rules` header and `applied_rules` output format assume
   the model can see formal rule IDs. In RAG mode, the model often can't — the
   retrieved chunks may not contain them.

## 2. Hypothesis Testing

### Hypothesis 1: Incomplete Retrieval — CONFIRMED (Primary Cause)

**Evidence:**

For `ACCESSIONING / order_received` (the most common scenario type), the top-5
retrieved chunks are:

| Rank | Score | Source | Section | Contains Rules? |
|------|-------|--------|---------|-----------------|
| 1 | 0.787 | workflow_states.md | Accessioning Evaluation Logic | No (severity hierarchy only) |
| 2 | 0.735 | sops/resulting.md | 7. Terminal States | No (wrong SOP entirely) |
| 3 | 0.728 | sops/accessioning.md | 4. Routing Outcomes | No (summary table only) |
| 4 | 0.717 | sops/accessioning.md | 5. Output Format | No (JSON example only) |
| 5 | 0.716 | sops/accessioning.md | 1. Purpose | No (overview text) |

The chunk containing the actual rules (`sops/accessioning.md: 3. Validation
Checks`, 5704 chars) does not appear in the top-20. The compact `Rule Catalog`
table from `workflow_states.md` appears at rank 8 (score 0.710) — just outside
`top_k=5`.

**Why?** The query `"workflow state: ACCESSIONING; event: order_received"` is
semantically closer to overview/process descriptions than to detailed validation
check specifications. The embeddings encode the query as "what happens at
accessioning when an order arrives" which matches process descriptions, not
rule-by-rule trigger conditions.

**Impact:** Without rule definitions in context, models have three failure modes:

- Cite no rules (`applied_rules: []`) — 57% of Opus failures
- Invent descriptive labels (`"missing_patient_name"`) — 8% of Opus failures
- Cite wrong formal IDs (guessing from limited context) — 34% of Opus failures

### Hypothesis 2: Chunk Boundary Issues — REFUTED

The H2-boundary chunking with `min_chunk_chars=100` does not split rules. The
"3. Validation Checks" section (which contains H3 and H4 subsections for
individual rules) stays as a single 5704-character chunk. Similarly, the "Rule
Catalog" in `workflow_states.md` is a single 4689-character chunk. The chunker
correctly preserves rule groupings within their H2 sections.

**Verdict:** Not a contributing factor. Chunk boundaries are fine; the problem is
retrieval ranking, not chunk splitting.

### Hypothesis 3: Context Format Change — CONFIRMED (Primary Cause)

**Evidence from prompt comparison:**

Baseline mode populates the `{rules_for_current_step}` template variable with:

```text
1. **ACC-003** — Severity: REJECT
   Trigger: Anatomic site not breast-cancer-relevant
   Action: DO_NOT_PROCESS

2. **ACC-004** — Severity: REJECT
   Trigger: Specimen type incompatible with histology workflow
   Action: DO_NOT_PROCESS
...
```

RAG mode populates the same template variable with:

```text
### Context 1 (from workflow_states.md: Accessioning Evaluation Logic)

## Accessioning Evaluation Logic

All accessioning rules use **severity-based, all-match evaluation** ...

### Context 2 (from sops/resulting.md: 7. Terminal States)

## 7. Terminal States
Orders reaching the resulting phase may terminate in ...
```

The baseline gives the model an enumerated checklist of rules with explicit IDs,
triggers, and actions. The RAG mode gives the model narrative SOP prose with no
rule enumeration. The prompt header says "Your Rules" but the content isn't
rules — it's process descriptions.

**Impact on model behavior:**

- Models correctly identify the *behavior* (e.g., patient name is missing) but
  cannot cite the formal rule ID because it's not in the context
- Models output descriptive strings like `"fixation_time_warning"`,
  `"specimen_type_incompatible"`, `"anatomic_site_mismatch"` — these describe
  the same conditions as ACC-006, ACC-004, ACC-003 respectively
- State accuracy only declined modestly (-2 to -14 pp) because models can still
  infer the correct routing outcome from general SOP knowledge

### Hypothesis 4: Rule ID Granularity — PARTIALLY CONFIRMED

**Evidence:**

In 34% of Opus failures, the model cited a formal rule ID that was wrong
(e.g., predicted `SP-002` instead of expected `SP-003`). In some cases these
are parent/sibling rules within the same workflow step. This suggests the model
has partial knowledge of rule IDs from whatever fragments appear in the
retrieved context (output format examples, routing outcomes tables) but maps
them incorrectly.

The `Rule Catalog` chunk at rank 8 sometimes enters the context when queries
slightly shift. When it does, models get the full ID table but may still
confuse similar rules (SP-002 vs SP-003) because the table format is compact
and the distinction between triggers is subtle.

## 3. Failure Pattern Breakdown (All Models)

| Model | Total Failures | Empty [] | Descriptive Labels | Wrong Formal IDs |
|-------|---------------:|---------:|-------------------:|-----------------:|
| Opus | 396 | 228 (57%) | 32 (8%) | 136 (34%) |
| Sonnet | 519 | 230 (44%) | 67 (12%) | 222 (42%) |
| Haiku | 530 | 44 (8%) | 242 (45%) | 244 (46%) |
| gemma-3-27b | 2251 | 551 (24%) | 12 (0%) | 1688 (74%) |
| phi-4 | 2762 | 175 (6%) | 1058 (38%) | 1529 (55%) |
| mistral-small | 1964 | 1284 (65%) | 88 (4%) | 592 (30%) |
| qwen3-32b | 31 | 21 (67%) | 10 (32%) | 0 (0%) |
| qwen3-8b | 2333 | 471 (20%) | 505 (21%) | 1357 (58%) |
| qwen3.5-35b | 2317 | 744 (32%) | 482 (20%) | 1091 (47%) |

**Patterns:**

- **Opus** mostly returns empty rules (57%) — it's cautious and avoids guessing
- **Haiku** mostly invents descriptive labels (45%) or wrong IDs (46%) — it
  aggressively tries to fill in rule IDs from general knowledge
- **Local models** heavily favor wrong formal IDs — they hallucinate plausible
  rule IDs from the ID pattern they see in whatever context fragments are available
- **qwen3-32b** is the outlier with only 31 failures — it may have strong
  rule-following behavior that compensates, but its empty-prediction rate (67%)
  suggests it's cautious rather than knowledgeable

## 4. Recommendations

### 4.1. Retrieval Fixes (Addresses Root Cause 1)

**R1: Increase `top_k` from 5 to 10-15.** The `Rule Catalog` chunk ranks 8th
for accessioning queries. Increasing top_k to at least 10 would capture it.
Trade-off: more context tokens, but the chunks are relatively small (median
~700 chars).

**R2: Add the Rule Catalog as a mandatory context chunk.** For routing decisions,
always prepend the `Rule Catalog` chunk from `workflow_states.md` regardless of
retrieval results. This is a 4689-character chunk containing all 40 rule IDs in
table format. It fits easily within context limits and guarantees rule ID
availability.

**R3: Improve query construction in `retrieve_for_routing()`.** The current query
`"workflow state: X; event: Y"` matches process overviews. Add rule-specific
terms:

```python
# Current
parts = [f"workflow state: {current_state}", f"event: {event_type}"]

# Proposed
parts = [
    f"workflow rules for {current_state}",
    f"rule triggers for event {event_type}",
    f"validation checks routing decision",
]
```

### 4.2. Prompt Template Fixes (Addresses Root Cause 2)

**R4: Add explicit rule ID citation instruction to the RAG prompt.** When using
RAG context, add an instruction that tells the model to look for and cite formal
rule IDs from the context:

```text
IMPORTANT: When citing rules in applied_rules, use the formal rule ID format
(e.g., "ACC-001", "SP-002", "HE-005"). If the context mentions a rule by
description but you cannot find its formal ID, set applied_rules to [].
Do NOT invent rule names or use descriptive labels.
```

**R5: Restructure RAG context presentation.** Instead of dumping raw chunks into
the `## Your Rules` section, post-process retrieved chunks to extract rule
definitions and re-format them in the structured baseline format. This could be
a simple regex extraction of `Rule ID | Trigger | Action` patterns from
retrieved markdown.

**R6: Separate "rules" from "context" in the RAG prompt.** Use a two-section
approach:

```text
## Your Rules
{formatted_rules_from_rule_catalog_or_retrieval}

## Additional Context
{rag_retrieved_sop_content}
```

This ensures the model always has a structured rules section and treats RAG
chunks as supplementary context rather than replacing the rules entirely.

### 4.3. Priority Order

| Priority | Recommendation | Impact | Effort |
|----------|---------------|--------|--------|
| 1 | R2 — Mandatory Rule Catalog chunk | High | Low |
| 2 | R4 — Rule ID citation instruction | High | Low |
| 3 | R6 — Separate rules from context | High | Medium |
| 4 | R3 — Improved query construction | Medium | Low |
| 5 | R1 — Increase top_k | Medium | Low |
| 6 | R5 — Post-process RAG chunks | Medium | High |

### 4.4. Proposed Prompt Diff (R2 + R4 + R6 Combined)

```python
# In prompt_template.py, render_prompt():

if rag_context:
    # R2: Always include Rule Catalog for the current step
    rules_text = _format_rules(sm.get_rules_for_state(order.current_state))
    # R6: RAG context as supplementary section
    rag_section = _format_rag_context(rag_context)
else:
    rules_text = _format_rules(...)
    rag_section = None
```

```text
## Your Rules

{rules_text}  <-- Always structured rule list, even in RAG mode

## Additional Context (Retrieved from SOPs)  <-- NEW section, RAG only

{rag_section}

## Instructions

...
4. Use ONLY the formal rule IDs from "Your Rules" above in applied_rules.  <-- R4
   Do not invent rule names or use descriptive labels.
```

## 5. Key Insight

The rule accuracy collapse is not a model capability problem — it's a context
problem. Models in RAG mode get the right answer (correct state routing) but
can't cite the right rule IDs because those IDs aren't in their context. The
fix is ensuring rule IDs are always present and clearly structured, regardless
of retrieval mode.

State accuracy declined only modestly (-2 to -14 pp), confirming that the SOP
knowledge in RAG chunks is sufficient for routing decisions. The catastrophic
metric is rule *citation*, not rule *application*.
