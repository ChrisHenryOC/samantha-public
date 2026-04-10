# Experiment: Tool-Assisted Routing for Deterministic Checks

## Context

The tiered model routing experiment (see `results/tiered_routing_analysis.md`) found that **all models score 100% on judgment-required steps** and that **all failures occur on deterministic steps** (boundary comparisons, multi-rule satisficing).  Routing decisions to different models doesn't help because the fast models fail on the "easy" steps.

The failures aren't because the models can't reason about the rules.  They fail on the arithmetic: "is 5.0 hours between 6 and 72 hours?" and "have I checked all 9 accessioning rules, or did I stop at 3?"

## Hypothesis

Giving the model tools that handle deterministic checks (numeric thresholds, field validation, rule enumeration) will close the accuracy gap on the known failure modes, while keeping the LLM in the loop for context, interpretation, and explanation.  The model decides *which* check to run and interprets the result.  The tool does the math.

This is different from a rules engine.  The LLM still drives the routing decision.  The tools are like a calculator for a human doing math: you could do it in your head, but the calculator is more reliable.

## What to Build

### Phase 1: Define new routing tools

Add new tool definitions to `src/tools/definitions.py` alongside the existing query tools.  These tools are specifically for routing decisions:

**Tool 1: `check_threshold`**
Evaluates whether a numeric value falls within a specified range.
```json
{
  "name": "check_threshold",
  "description": "Check whether a numeric value falls within an acceptable range (inclusive). Returns {\"in_range\": true/false, \"value\": <value>, \"min\": <min>, \"max\": <max>}. Use this for fixation time checks, specimen age validation, or any numeric boundary comparison.",
  "parameters": {
    "value": { "type": "number", "description": "The value to check" },
    "min": { "type": "number", "description": "Minimum acceptable value (inclusive)" },
    "max": { "type": "number", "description": "Maximum acceptable value (inclusive)" }
  }
}
```

**Tool 2: `check_field_present`**
Checks whether a field exists and is non-null/non-empty in the event data.
```json
{
  "name": "check_field_present",
  "description": "Check whether a field is present and has a non-null, non-empty value. Returns {\"present\": true/false, \"field\": <field_name>, \"value\": <actual_value_or_null>}. Use this for missing info checks (patient name, sex, billing info).",
  "parameters": {
    "field_name": { "type": "string", "description": "The field name to check" },
    "field_value": { "type": ["string", "number", "boolean", "null"], "description": "The field value to evaluate" }
  }
}
```

**Tool 3: `check_enum_membership`**
Checks whether a value is in an allowed set.
```json
{
  "name": "check_enum_membership",
  "description": "Check whether a value is a member of an allowed set. Returns {\"is_member\": true/false, \"value\": <value>, \"allowed\": [...]}. Use this for specimen type validation, anatomic site checks, or any set membership test.",
  "parameters": {
    "value": { "type": "string", "description": "The value to check" },
    "allowed_values": { "type": "array", "items": { "type": "string" }, "description": "List of allowed values" }
  }
}
```

**Tool 4: `list_applicable_rules`**
Given a workflow step and the event data, returns all rules that could apply.  This addresses the multi-rule satisficing failure where models find one matching rule and stop.
```json
{
  "name": "list_applicable_rules",
  "description": "Given a workflow step, list ALL rules that could potentially apply based on their trigger conditions. Returns a list of rule IDs with their trigger descriptions. The model should then evaluate each one against the event data. Use this at accessioning (where multiple validation rules must be checked simultaneously) or any step with more than 2 possible rules.",
  "parameters": {
    "current_state": { "type": "string", "description": "Current workflow state (e.g. ACCESSIONING, SAMPLE_PREP_QC)" }
  }
}
```

### Phase 2: Implement tool execution

Add the new tools to `src/tools/executor.py`.  The implementations should be straightforward:

- `check_threshold`: Pure arithmetic comparison, return JSON result
- `check_field_present`: Null/empty check, return JSON result
- `check_enum_membership`: Set membership test, return JSON result
- `list_applicable_rules`: Read from the knowledge base skill documents (already loaded by the skill loader in `src/prediction/skill_loader.py`) and return rule IDs with trigger conditions for the given state

### Phase 3: Update skill documents to reference tools

Update the skill documents in `knowledge_base/skills/` to instruct the model to use these tools.  For example, in `accessioning.md`, add instructions like:

> Before evaluating accessioning rules, call `list_applicable_rules` with current_state "ACCESSIONING" to get the full list of rules to check.  For each rule that involves a numeric threshold (e.g., fixation time), use `check_threshold` rather than evaluating the comparison yourself.  For each rule that checks field presence (e.g., patient name), use `check_field_present`.

Keep the instructions natural and integrated into the existing skill document flow.  Don't make them feel like a separate system.

### Phase 4: Create a tool-use routing prompt variant

The existing evaluation harness already supports `--prompt-extras` for prompt variants.  Create a new prompt extra `routing_tools` that:

1. Includes the tool definitions in the prompt
2. Instructs the model to use tools for deterministic checks
3. Keeps the existing skills-based prompt structure

This should work alongside the existing `skills` prompt extra.  Usage: `--prompt-extras skills,routing_tools`

### Phase 5: Run the evaluation

Run the 33-scenario screening set with the tool-assisted prompt against:

1. **Qwen 2.5 Coder 32B** (local, 5 runs) - to see if tools close the 0.3% gap
2. **Qwen3 Coder 30B** (local, 5 runs) - to see if tools close the larger 6.3% gap
3. Optionally **Gemma 3 27B** (local, 5 runs) - to see if tools help the weakest model

Save results to `results/tool_assisted_routing/`.

### Phase 6: Analysis

Create `scripts/analyze_tool_assisted_routing.py` that compares tool-assisted results against the existing skills-only baselines:

**Table 1: Tool-assisted vs skills-only baselines**

| Model | Approach | State Acc | Rule Acc | Flag Acc | Latency | Tool Calls/Step |
|-------|----------|-----------|----------|----------|---------|----------------|

**Table 2: Failure analysis**

For each model, compare failure modes between skills-only and tool-assisted:
- Did boundary comparison failures decrease?
- Did multi-rule satisficing failures decrease?
- Did any new failure modes appear (e.g., incorrect tool usage, tool call failures)?

**Table 3: Tool usage patterns**

- How often did the model call each tool?
- Did it call tools when it should have?
- Did it call tools when it didn't need to?

Save analysis to `results/tool_assisted_routing_analysis.md`.

## Success Criteria

The hypothesis is supported if:
1. Tool-assisted accuracy for Qwen 2.5 Coder 32B exceeds 99.7% (current baseline), specifically by eliminating boundary comparison failures
2. Tool-assisted accuracy for Qwen3 Coder 30B exceeds 93.7% by at least 3pp
3. Latency increase from tool calls is < 2x the baseline (tools add overhead but shouldn't double inference time)

The hypothesis is refuted if:
1. Models don't reliably use the tools when they should (the model "forgets" to call `check_threshold` and does the math itself)
2. Tool overhead makes latency prohibitive
3. New failure modes from tool interaction outweigh the accuracy gains

## Relationship to Tiered Routing Experiment

This experiment builds on the tiered routing finding.  That experiment showed the problem isn't which model handles which step, it's that all models fail on the same deterministic checks.  This experiment asks: can we fix those specific failures by giving the model better tools, rather than replacing the model?

## Branch

This work should be done on the existing `feature/issue-228-tiered-model-routing` branch and included in the same PR.  The tiered routing experiment stays as-is (negative result is valuable), and this tool-assisted experiment extends it.
