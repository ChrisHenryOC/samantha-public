# Scenario Design

This document describes the principles, categories, and structure for test scenarios used to evaluate model performance.

## Design Principle

Every rule in the catalog must be the primary trigger in at least 2 scenarios — one straightforward activation and one with complicating context. Scenarios are organized by what they test, not by difficulty.

## Scenario Categories

### Rule Coverage (~80 scenarios)

Two scenarios per rule in the catalog (40 rules). The first scenario is a clean trigger — only the target rule applies. The second adds complicating context where multiple rules *could* apply but the target rule should fire based on priority ordering.

### Multi-Rule Interactions (~10 scenarios)

Situations where two or more rules could apply. Tests whether the model respects priority ordering and, at accessioning, reports all matching rules. Examples: missing patient name (ACC-001) and bad fixation (ACC-006) on the same order — model should report both rules and route to DO_NOT_PROCESS (highest severity); H&E QC failure where both restain (HE-002) and recut (HE-003) could be argued — model must select based on backup slide availability (restain if backups available, recut if not).

### Accumulated State (~10 scenarios)

Decisions that depend on flags or state set in earlier workflow steps. Examples: MISSING_INFO_PROCEED flag set at accessioning must block at RESULTING (not before); RECUT_REQUESTED affects tissue availability at a later retry decision; partial slide completion (3 of 5 done) requires hold.

### Unknown/Unexpected Inputs (~5 scenarios)

Inputs the rules don't explicitly cover. Tests whether the model applies domain knowledge or fails safely. Examples: FNA specimen type, unrecognized specimen type (e.g., "swab"), anatomic site that's ambiguous (e.g., "skin overlying breast").

### Hallucination Probing (~8 scenarios)

Inputs designed to tempt the model into fabricating information — invented rule IDs, phantom flags, or clinical reasoning not grounded in the rule catalog. Each scenario has a clear correct answer using only existing rules; the hallucination risk is that the model invents something extra. Examples:

- Extra clinical context (BRCA1 mutation, family history) that no rule references — model should ignore it, not invent a genetic-risk rule
- Unrecognized test name (e.g., "PD-L1") — no accessioning rule validates test names, so the order should be accepted
- Unusual demographics (19-year-old male) — no rule rejects based on age or sex *value*
- Diagnosis not explicitly listed in HE rules (e.g., LCIS) — model must map to the closest existing rule (HE-007: suspicious/atypical), not invent a new rule ID
- HER2 1+ score (definitively negative) — model should not hallucinate a FISH suggestion
- Benign diagnosis with suspicious free-text narrative — model must follow the structured diagnosis field, not override based on clinical notes
- Extra metadata fields in event data — model should ignore fields not referenced by any rule
- Fixation time at exact boundary (6.0 hours for HER2) — valid per ACC-006, model should not flag or reject

### Query (27 scenarios)

Natural-language questions about order state and worklist status, replacing traditional LIS screen lookups with a conversational interface. The model receives a database state snapshot (all orders, slides, flags) and a free-text query, then returns a structured answer. Scenarios are organized into five complexity tiers:

- **Tier 1 — Simple lookup** (8 scenarios): Filter orders by a single state. Example: "What orders are ready for grossing?" Expected answer (`order_list`): the exact set of order IDs matching the filter criteria.
- **Tier 2 — Order status** (6 scenarios): Map a specific order's state to the next physical action. Example: "What's the next step for order 12345?" Expected answer (`order_status`): the next action (e.g., "Proceed to grossing") derived from the order's current state and flags.
- **Tier 3 — Flag reasoning** (5 scenarios): Explain why an order has a specific flag or hold state. Example: "Why is order 12345 on hold?" Expected answer (`order_status`): the referenced order IDs with reasoning that traces the flag to the originating rule.
- **Tier 4 — Prioritization** (4 scenarios): Rank orders within a workflow step by priority, age, and state. Example: "Which grossing orders should I do first?" Expected answer (`prioritized_list`): an ordered list of order IDs with justification (rush before routine, older before newer).
- **Tier 5 — Cross-order reasoning** (4 scenarios): Scan multiple orders to identify those matching a complex condition. Example: "Do any orders need pathologist attention?" Expected answer (`order_list`): the set of orders in states that require pathologist review (e.g., PATHOLOGIST_HE_REVIEW, SUGGEST_FISH_REFLEX) with the reason for each.

## Boundary and False-Positive Probing

Within the rule coverage and multi-rule categories, include scenarios designed to test whether the model invents problems that don't exist. Examples:
- Fixation time at exact boundaries (6.0 hours, 72.0 hours — both valid)
- Orders with all fields correct (model should not flag anything)
- Situations where context is tempting but wrong (e.g., pathologist says benign but HER2 was ordered — model should cancel IHC, not reconcile)

## Target Count

**~140 scenarios total** (78 rule coverage + 10 multi-rule + 10 accumulated state + 6 unknown inputs + 8 hallucination + 27 query). If eval results reveal gaps, add targeted scenarios rather than padding existing categories.

## Authoring Process

Scenarios and their ground truth are authored collaboratively (human + Claude Code). Each scenario requires manual review to validate that the expected outputs correctly reflect the [Rule Catalog](../workflow/rule-catalog.md) and [Workflow Overview](../workflow/workflow-overview.md).

## Scenario JSON Structure

Each scenario is a JSON file containing the scenario metadata and an ordered sequence of events, each with ground-truth expected outputs.

```json
{
  "scenario_id": "SC-001",
  "category": "rule_coverage",
  "description": "Standard invasive carcinoma, Breast IHC Panel, routine",
  "events": [
    {
      "step": 1,
      "event_type": "order_received",
      "event_data": {
        "patient_name": "TESTPATIENT-0001, Sarah",
        "age": 58,
        "sex": "F",
        "specimen_type": "biopsy",
        "anatomic_site": "breast",
        "fixative": "formalin",
        "fixation_time_hours": 24,
        "ordered_tests": ["Breast IHC Panel"],
        "priority": "routine",
        "billing_info_present": true
      },
      "expected_output": {
        "next_state": "ACCEPTED",
        "applied_rules": ["ACC-008"],
        "flags": []
      }
    },
    {
      "step": 2,
      "event_type": "grossing_complete",
      "event_data": {"outcome": "success"},
      "expected_output": {
        "next_state": "SAMPLE_PREP_PROCESSING",
        "applied_rules": ["SP-001"],
        "flags": []
      }
    }
  ]
}
```

## Query Scenario JSON Structure

Query scenarios use a different structure from routing scenarios. Instead of an event sequence, each query scenario contains a database state snapshot and a natural-language question with structured ground truth.

```json
{
  "scenario_id": "QR-001",
  "category": "query",
  "tier": 1,
  "description": "Simple lookup — orders in accepted state",
  "database_state": {
    "orders": [
      {"order_id": "ORD-100", "current_state": "ACCEPTED", "priority": "routine", "flags": []},
      {"order_id": "ORD-101", "current_state": "ACCEPTED", "priority": "rush", "flags": []},
      {"order_id": "ORD-102", "current_state": "SAMPLE_PREP_PROCESSING", "priority": "routine", "flags": []}
    ],
    "slides": []
  },
  "query": "What orders have been accepted and are ready for sample prep?",
  "expected_output": {
    "answer_type": "order_list",
    "order_ids": ["ORD-100", "ORD-101"],
    "reasoning": "Orders in ACCEPTED state have been accessioned and are ready for sample prep."
  }
}
```

## Related Documents

- [Rule Catalog](../workflow/rule-catalog.md) — rules that scenarios test
- [Workflow Overview](../workflow/workflow-overview.md) — states and transitions
- [Evaluation Metrics](../technical/evaluation-metrics.md) — how scenario results are scored
