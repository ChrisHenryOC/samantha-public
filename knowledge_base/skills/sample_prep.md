## Sample Prep Routing Skill

Sample prep follows a fixed sequence. Identify the event type and outcome,
then apply the first matching rule.

### State Sequence

When a step completes successfully, advance to the next state in this order:

ACCEPTED → SAMPLE_PREP_PROCESSING → SAMPLE_PREP_EMBEDDING →
SAMPLE_PREP_SECTIONING → SAMPLE_PREP_QC → HE_STAINING

MISSING_INFO_PROCEED also advances to SAMPLE_PREP_PROCESSING (same as ACCEPTED).

### Rules (first match wins)

**For grossing_complete, processing_complete, embedding_complete, sectioning_complete:**

| Outcome | Rule | Next State |
|---------|------|-----------|
| success | SP-001 | Advance to next state in the sequence above |
| failure (tissue available) | SP-002 | Stay at current state (RETRY) |
| failure (no tissue) | SP-003 | ORDER_TERMINATED_QNS |

"RETRY current step" means output the CURRENT state name, not the word "RETRY".

**For sample_prep_qc (at SAMPLE_PREP_QC state):**

| Outcome | Rule | Next State |
|---------|------|-----------|
| pass | SP-004 | HE_STAINING |
| fail (tissue available) | SP-005 | SAMPLE_PREP_SECTIONING |
| fail (no tissue / fail_qns) | SP-006 | ORDER_TERMINATED_QNS |

### Flag Clearing

If RECUT_REQUESTED is in the order's flags AND SP-001 applies (step completes
successfully after a recut), REMOVE RECUT_REQUESTED from the flags list.
The recut has been completed.

### Example

Event: grossing_complete with outcome "success" on an order in ACCEPTED state.
Result: next_state = "SAMPLE_PREP_PROCESSING", applied_rules = ["SP-001"], flags = []
