## H&E Routing Skill

### At HE_STAINING (after he_staining_complete)

This is a pass-through: he_staining_complete always routes to HE_QC.
No rule applies — set applied_rules to [].

### At HE_QC (after he_qc)

Evaluate the he_qc event outcome and apply the first matching rule.

### Rules (first match wins)

| Outcome | Rule | Next State | Flags |
|---------|------|-----------|-------|
| pass | HE-001 | PATHOLOGIST_HE_REVIEW | [] |
| fail_restain | HE-002 | HE_STAINING | [] |
| fail_recut AND tissue_available is true | HE-003 | SAMPLE_PREP_SECTIONING | [] |
| fail_qns (quantity not sufficient) | HE-004 | ORDER_TERMINATED_QNS | [] |

"RETRY" to HE_STAINING means output "HE_STAINING", not the word "RETRY".
