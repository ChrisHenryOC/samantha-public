# Architecture

This document describes the five-layer architecture of the evaluation system: RAG corpus, order simulator, prediction engine, model abstraction, and evaluation harness.

## Layer 1: Workflow Knowledge Base (RAG Corpus)

Documents to be created and indexed:
- **Workflow state machine** — complete definition of states, transitions, and conditions (YAML/JSON, also rendered as markdown for RAG)
- **Accessioning SOP** — validation rules, routing logic
- **Sample prep SOP** — steps, retry/abort criteria
- **H&E SOP** — staining, QC, pathologist review routing
- **IHC SOP** — panel selection rules, staining, scoring, FISH reflex criteria
- **Resulting SOP** — report generation, sign-out
- **Breast IHC panel rules** — diagnosis-to-marker mappings, fixation requirements (ASCO/CAP guidelines)

### RAG Implementation
- **Embedding model**: all-MiniLM-L6-v2 or similar (runs locally)
- **Vector store**: ChromaDB (preferred for simplicity with small corpus; evaluate fit during Phase 3 architecture review)
- **Chunking strategy**: section-aware for SOPs (don't split mid-procedure); whole-document for rule sets (panel definitions stay together)
- **Retrieval**: tunable number of chunks per prediction (start with 3-5, experiment)
- **Framework**: LlamaIndex (preferred for focused RAG workflows; evaluate during Phase 3)

## Layer 2: Order Simulator

Generates synthetic test scenarios. Each scenario is a sequence of events with ground-truth expected outcomes. See [Scenario Design](../scenarios/scenario-design.md) for scenario structure, categories, and authoring process.

**Scenario JSON structure:**
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

## Layer 3: Prediction Engine

Takes current order state + event data -> retrieves relevant RAG context -> prompts model -> returns structured prediction.

**Input to model:**
- Current order state (full order data + current workflow state)
- New event (what just happened)
- Retrieved RAG context (relevant SOP sections, rules)

**Required output format (JSON):**
```json
{
  "next_state": "SAMPLE_PREP_PROCESSING",
  "applied_rules": ["SP-001"],
  "flags": [],
  "reasoning": "Grossing completed successfully. Specimen is adequate. Proceeding to tissue processing per SOP-SP-001."
}
```

**Prompt strategy:** Standardized prompt template used across all models. Single prompt design, no model-specific tuning. See below for the prompt template skeleton — to be refined during Phase 4.

### Prompt Template (Skeleton)

```text
You are a laboratory workflow routing system for a breast cancer histology lab.
Your job is to determine what should happen next to a lab order based on an
incoming event. You are a workflow traffic cop — you route orders between steps
and identify issues. You NEVER make clinical decisions.

## Your Rules

The following rules apply to the current workflow step. Evaluate ALL rules
against the current situation. For most workflow steps, apply the first
matching rule. For ACCESSIONING, identify ALL matching rules — multiple
issues can be flagged at once. The highest-severity outcome determines
the next state (REJECT > HOLD > PROCEED > ACCEPT).

If no rule matches, respond with the closest valid state from the vocabulary,
set applied_rules to an empty list [], and explain the ambiguity in your
reasoning. The empty applied_rules list serves as the machine-parseable
signal that no rule matched.

{rules_for_current_step}

## Flag Reference

Flags carry forward across workflow steps. Check the order's existing flags
before making your decision — they may block or alter the expected transition.

{flag_reference}

## Current Order State

{order_state_json}

## Slides

{slides_json}

## New Event

{event_json}

## Instructions

1. Review the current order state and the new event.
2. Check the order's existing flags — they may affect your decision.
3. Evaluate the rules above against the current situation.
4. For ACCESSIONING: identify ALL matching rules. The highest-severity outcome
   determines the next state (REJECT > HOLD > PROCEED > ACCEPT). Report every
   matching rule in applied_rules.
5. For all other steps: identify the FIRST rule whose trigger condition matches
   (by priority order) and apply it to determine the next state and any flags.

Respond with ONLY a JSON object in this exact format, no other text:

{
  "next_state": "<the workflow state the order should transition to>",
  "applied_rules": ["<rule_id(s) that matched>"],
  "flags": ["<any flags to add — omit if none>"],
  "reasoning": "<brief explanation of why this rule applies>"
}
```

### Template Variables

| Variable | Source | Description |
|----------|--------|-------------|
| `{rules_for_current_step}` | Rule catalog, filtered by current workflow step | Rules formatted as a numbered list with ID, trigger, action, and priority. For full-context baseline (Phase 4), all rules are included. |
| `{flag_reference}` | Flag vocabulary, filtered to active flags | Each active flag with its downstream effect (e.g., "MISSING_INFO_PROCEED: blocks resulting until info received"). Empty if no flags set. |
| `{order_state_json}` | Orders table snapshot | Current order state including patient, specimen, order fields, current_state, and accumulated flags |
| `{slides_json}` | Slides table snapshot | All slides for this order with current statuses |
| `{event_json}` | Events table | The new event that triggered this invocation |

### Query Evaluation Flow

In addition to routing predictions, the prediction engine supports a **query evaluation track** where the model answers natural-language questions about order state and worklist status. This replaces traditional LIS worklist screens with a conversational interface.

**Query types (illustrative examples):**

1. **Order query**: "What's the next step for order X?" — given an order's current state, flags, and slide statuses, return the next physical action needed.
2. **Worklist query**: "What orders are ready for step Y?" — given a workflow step, return all orders waiting for that step.

These are the two simplest query forms. The authoritative categorization is the five-tier complexity model defined in [Scenario Design](../scenarios/scenario-design.md), which includes additional tiers for flag reasoning, prioritization, and cross-order reasoning.

**Context-stuffing approach (POC strategy):**

For the POC, query evaluation uses context stuffing rather than tool use or database access. The model receives a complete database state snapshot in the prompt — all orders, their states, flags, and slide statuses — alongside the natural-language query. This mirrors the full-context approach used for routing in Phase 4.

**Input to model (query mode):**

- Database state snapshot (all orders with current states, flags, slides)
- Workflow state reference (valid states and their meanings)
- Natural-language query

**Required output format (JSON):**

```json
{
  "answer_type": "order_list",
  "order_ids": ["ORD-100", "ORD-101"],
  "reasoning": "Orders in ACCEPTED state have been accessioned and are ready for sample prep."
}
```

The `answer_type` field varies by query tier — see [Evaluation Metrics](evaluation-metrics.md) for scoring details per tier.

**Follow-on: tool-use evaluation.** A natural extension beyond the POC is to give the model tools (e.g., `query_orders(state=...)`, `get_order(id=...)`) instead of stuffing the full database state into the prompt. This tests whether models can decompose queries into tool calls — a more realistic production pattern. This is out of scope for the current POC but noted as a potential Phase 7 track.

## Layer 4: Model Abstraction Layer

Unified interface for all models. Each model adapter implements:
- `predict(prompt: str) -> ModelResponse`
- Tracks: latency, input/output tokens, cost estimate

### Local Models (via llama-server on Apple Silicon)
- Llama 3.1 8B
- Llama 3.3 70B (Q4 quantized)
- Mistral 7B
- Phi-3 (or current equivalent)

### Cloud Models (via API)

**Phase 3 (via OpenRouter):**

- Claude Haiku 4.5
- Claude Sonnet 4.6
- Claude Opus 4.6

Three capability tiers via OpenRouter's OpenAI-compatible API provide
meaningful ceiling benchmarks without the integration cost of multiple SDKs.

**Deferred to post-Phase 6:**

- GPT-4o
- GPT-o3 (reasoning model — see note below)
- Gemini 2.5 Pro

**Note on reasoning models:** GPT-o3 is a reasoning model with a different API pattern (no streaming, higher latency, higher cost). It is included to test whether extended "thinking" improves performance on multi-rule and accumulated state scenarios. Latency and cost comparisons with standard models are not apples-to-apples.

**Model roles:** Local models are the real candidates — laboratories will likely resist cloud models due to patient privacy concerns (PHI leaving the network). Cloud models serve as a ceiling benchmark to establish how well the task *can* be done, providing context for evaluating local model performance.

## Layer 5: Evaluation Harness

Runs all scenarios against all models. Produces comparison reports.

**Run strategy:** Local models run each scenario 5 times to measure variance — consistency matters as much as accuracy in a lab environment. Cloud models run each scenario once as a ceiling benchmark. The evaluation harness records each run independently; metrics are reported as mean +/- standard deviation for local models and single-run values for cloud models.

**Variance as a metric:** A local model that scores 88% +/- 2% is a stronger candidate than one that scores 91% +/- 8%, even though the latter has a higher mean. High variance means unpredictable behavior — unacceptable in a clinical workflow.

See [Evaluation Metrics](evaluation-metrics.md) for the full metrics framework and failure handling.

## Related Documents

- [Data Model](data-model.md) — persistence schema and data lifecycle
- [Evaluation Metrics](evaluation-metrics.md) — scoring and failure handling
- [Technology Stack](technology-stack.md) — tools and runtime
- [Scenario Design](../scenarios/scenario-design.md) — scenario categories and authoring
