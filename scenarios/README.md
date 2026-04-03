# scenarios/

Test scenario definitions as JSON files. Each scenario defines a sequence of
workflow events with expected outputs (next state, applied rules, flags) used
by the evaluation harness to score model accuracy.

| Category | Count | Purpose |
|----------|-------|---------|
| `rule_coverage/` | 79 | One scenario per rule in the rule catalog — ensures every rule is exercised |
| `multi_rule/` | 10 | Scenarios that trigger multiple rules in a single step |
| `accumulated_state/` | 10 | Multi-step scenarios testing flag accumulation and state persistence |
| `unknown_input/` | 6 | Invalid or unexpected inputs the model should handle gracefully |
| `query/` | 27 | Query scenarios for the tool-use chat interface (not routing) |

## File Format

Routing scenarios (`sc_*.json`):

```json
{
  "scenario_id": "sc_001",
  "description": "...",
  "events": [
    {
      "step": 1,
      "event_type": "order_received",
      "event_data": { ... },
      "expected_output": {
        "next_state": "ACCEPTED",
        "applied_rules": ["ACC-008"],
        "flags": []
      }
    }
  ]
}
```

Query scenarios (`qr_*.json`) define a database state, a natural-language
query, and expected output (answer type, matching order IDs, reasoning).

## Generating Review Docs

To generate human-readable markdown summaries of all scenarios:

```bash
python scripts/generate_scenario_docs.py
```

Output goes to `docs/scenarios/review/` (gitignored).
