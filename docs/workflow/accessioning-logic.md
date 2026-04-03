# Accessioning Decision Logic

This document describes the evaluation logic applied when an order arrives at accessioning. All rules are evaluated on every order — the system should identify **all** applicable issues, not stop at the first match.

## Severity Hierarchy

The final routing is determined by the highest-severity outcome found:

1. If any DO_NOT_PROCESS rule matches -> **DO_NOT_PROCESS** (order is rejected)
2. If any MISSING_INFO_HOLD rule matches -> **MISSING_INFO_HOLD** (all missing fields flagged together)
3. If only MISSING_INFO_PROCEED rules match -> **MISSING_INFO_PROCEED** (order proceeds with flag)
4. If no issues found -> **ACCEPTED**

## Checks (All Evaluated)

- Patient name missing -> MISSING_INFO_HOLD
- Patient sex missing -> MISSING_INFO_HOLD
- Anatomic site not breast-cancer-relevant -> DO_NOT_PROCESS
- Specimen type incompatible with histology workflow or unrecognized -> DO_NOT_PROCESS
- HER2 ordered + fixative is not formalin -> DO_NOT_PROCESS
- HER2 ordered + formalin fixation time outside 6-72 hours -> DO_NOT_PROCESS
- HER2 ordered + fixation time is null (missing) -> MISSING_INFO_HOLD
- Billing info missing -> MISSING_INFO_PROCEED
- All valid -> ACCEPTED

## Evaluation Principle

The system must report **all** matching rules in `applied_rules`, not just the highest-severity one. For example, if both patient name (ACC-001) and billing info (ACC-007) are missing, both rules should be cited even though the final routing is MISSING_INFO_HOLD (the higher severity).

See the [Rule Catalog](rule-catalog.md) for the full accessioning rule table (ACC-001 through ACC-009).

## Specimen Type Handling

The `specimen_type` field is a free string, not a constrained enum. This is intentional — the system must decide how to handle both known and unknown types.

| Type | Handling | Rationale |
|------|----------|-----------|
| biopsy | ACCEPTED (if other checks pass) | Standard histology specimen |
| resection | ACCEPTED (if other checks pass) | Standard histology specimen |
| excision | ACCEPTED (if other checks pass) | Standard histology specimen (surgical excision) |
| FNA | DO_NOT_PROCESS | FNA is a cytology specimen — incompatible with the histology workflow (grossing -> embedding -> sectioning) |
| Unknown/unrecognized | DO_NOT_PROCESS | Reject specimen types that cannot be mapped to the workflow |

FNA and unknown types serve as test cases for the ability to recognize specimens that are inappropriate for this workflow, even when the rules don't explicitly enumerate every invalid type. General domain knowledge should be applied (FNA = cytology != histology) rather than relying solely on an allowlist.

## Valid Anatomic Sites

Breast-cancer-relevant sites: breast, axillary lymph node, chest wall.

## Related Documents

- [Rule Catalog](rule-catalog.md) — full rule tables
- [Workflow Overview](workflow-overview.md) — states and transitions
