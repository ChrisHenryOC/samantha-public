# Rule Catalog

The workflow rules are structured as a discrete catalog of individually identifiable rules. Each rule has a trigger condition and a prescribed action. The routing system's job is twofold: (1) match the current situation to the correct rule(s), and (2) apply the rule to produce the correct output. These are scored independently.

## Rule Structure

```json
{
  "rule_id": "ACC-001",
  "step": "ACCESSIONING",
  "trigger": "Patient name is missing from order",
  "action": "MISSING_INFO_HOLD — hold order, request patient name",
  "priority": 1,
  "source": "Accessioning SOP, Section 3.1"
}
```

## Rule Fields

| Field | Type | Description |
|-------|------|-------------|
| rule_id | string | Unique identifier (e.g., ACC-001, IHC-003) |
| step | string | Workflow step where this rule applies |
| trigger | string | Condition that activates this rule |
| action | string | Prescribed state transition and/or action |
| priority | integer | Evaluation order when multiple rules could match (lower = first) |
| source | string | Reference to the SOP section this rule derives from |

## Accessioning Rules

All accessioning rules are evaluated on every order. Multiple rules can fire simultaneously (e.g., both ACC-001 and ACC-002 if name and sex are missing). The outcome severity determines the final routing: DO_NOT_PROCESS > MISSING_INFO_HOLD > MISSING_INFO_PROCEED > ACCEPTED. The model should report all matching rules in `applied_rules`.

Note: Accessioning uses a **Severity** column (not Priority) because all rules are evaluated simultaneously and the highest-severity outcome wins. Other workflow steps use **Priority** for sequential first-match evaluation.

| Rule ID | Trigger | Action | Severity |
|---------|---------|--------|----------|
| ACC-001 | Patient name missing | MISSING_INFO_HOLD, request patient name | HOLD |
| ACC-002 | Patient sex missing | MISSING_INFO_HOLD, request patient sex | HOLD |
| ACC-003 | Anatomic site not breast-cancer-relevant | DO_NOT_PROCESS | REJECT |
| ACC-004 | Specimen type incompatible with histology workflow (e.g., FNA) or unrecognized | DO_NOT_PROCESS | REJECT |
| ACC-005 | HER2 ordered + fixative is not formalin | DO_NOT_PROCESS | REJECT |
| ACC-006 | HER2 ordered + fixation time outside 6-72 hours | DO_NOT_PROCESS | REJECT |
| ACC-009 | HER2 ordered + fixation time is null (missing) | MISSING_INFO_HOLD, request fixation time | HOLD |
| ACC-007 | Billing info missing | MISSING_INFO_PROCEED | PROCEED |
| ACC-008 | All validations pass | ACCEPTED | ACCEPT |

## Sample Prep Rules

| Rule ID | Trigger | Action | Priority |
|---------|---------|--------|----------|
| SP-001 | Step completed successfully | Advance to next sample prep step | 1 |
| SP-002 | Step failed, tissue available | RETRY current step | 2 |
| SP-003 | Step failed, insufficient tissue | ABORT -> ORDER_TERMINATED_QNS | 3 |
| SP-004 | Sample prep QC passes | Advance to HE_STAINING | 4 |
| SP-005 | Sample prep QC fails, tissue available | RETRY -> SAMPLE_PREP_SECTIONING | 5 |
| SP-006 | Sample prep QC fails, insufficient tissue | ABORT -> ORDER_TERMINATED_QNS | 6 |

## H&E / Pathologist Review Rules

| Rule ID | Trigger | Action | Priority |
|---------|---------|--------|----------|
| HE-001 | H&E QC passes | Route to PATHOLOGIST_HE_REVIEW | 1 |
| HE-002 | H&E QC fails, restain possible | RETRY -> HE_STAINING | 2 |
| HE-003 | H&E QC fails, recut needed, tissue available | RETRY -> SAMPLE_PREP_SECTIONING | 3 |
| HE-004 | H&E QC fails, insufficient tissue | ABORT -> ORDER_TERMINATED_QNS | 4 |
| HE-005 | Pathologist diagnosis: invasive carcinoma | PROCEED_IHC (standard panel: ER, PR, HER2, Ki-67) | 1 |
| HE-006 | Pathologist diagnosis: DCIS | PROCEED_IHC (standard panel: ER, PR; HER2 only if ordered) | 2 |
| HE-007 | Pathologist diagnosis: suspicious/atypical | PROCEED_IHC (pathologist-customized panel) | 3 |
| HE-008 | Pathologist diagnosis: benign | Cancel IHC, route to RESULTING | 4 |
| HE-009 | Pathologist requests recuts | REQUEST_RECUTS -> SAMPLE_PREP_SECTIONING | 5 |

## IHC Rules

| Rule ID | Trigger | Action | Priority |
|---------|---------|--------|----------|
| IHC-001 | HER2 added by pathologist + fixation out of tolerance | Reject specimen for HER2, flag to pathologist | 1 |
| IHC-002 | All slides stained and QC passed | Route to IHC_SCORING | 2 |
| IHC-003 | Some slides still pending | HOLD — wait for remaining slides | 3 |
| IHC-004 | Staining failed | RETRY staining | 4 |
| IHC-005 | Staining failed, insufficient tissue | ABORT -> ORDER_TERMINATED_QNS | 5 |
| IHC-006 | Scoring complete, no equivocal results | RESULTING | 6 |
| IHC-007 | HER2 equivocal | SUGGEST_FISH_REFLEX (requires pathologist approval) | 7 |
| IHC-008 | Pathologist approves FISH reflex | FISH_SEND_OUT (external test) | 8 |
| IHC-009 | Pathologist declines FISH reflex | Route to RESULTING | 9 |
| IHC-010 | FISH result received | Route to RESULTING | 10 |
| IHC-011 | FISH external lab returns QNS | ABORT -> ORDER_TERMINATED_QNS | 11 |

## Resulting Rules

| Rule ID | Trigger | Action | Priority |
|---------|---------|--------|----------|
| RES-001 | MISSING_INFO_PROCEED flag present | RESULTING_HOLD — block until info received | 1 |
| RES-002 | Info received, re-evaluate flags | If flag cleared -> proceed to RESULTING; if still missing -> remain in RESULTING_HOLD | 2 |
| RES-003 | All scoring/testing complete, no blocking flags | Route to PATHOLOGIST_SIGNOUT | 3 |
| RES-004 | Pathologist selects reportable tests | Route to REPORT_GENERATION (update slide `reported` flags) | 4 |
| RES-005 | Report generated | ORDER_COMPLETE | 5 |

## Flag Vocabulary

Flags are accumulated state that carries forward across the order lifecycle. The routing system may set flags as part of its output, and must consider existing flags when making decisions.

| Flag | Set At | Effect |
|------|--------|--------|
| MISSING_INFO_PROCEED | Accessioning | Blocks resulting until info is resolved; order proceeds through IHC normally |
| FIXATION_WARNING | Accessioning or IHC | Alerts that fixation was borderline or needs review |
| RECUT_REQUESTED | Pathologist H&E Review | Tracks that slides were recut (affects tissue availability assessment) |
| HER2_FIXATION_REJECT | IHC | HER2 rejected due to fixation out of tolerance, flagged to pathologist |
| FISH_SUGGESTED | IHC Scoring | HER2 equivocal, FISH reflex suggested pending pathologist approval |

Flags are stored in the order's `flags` array and persist until explicitly resolved. The routing system must check existing flags before making state transition decisions — for example, an order with MISSING_INFO_PROCEED must not advance to RESULTING until the flag is cleared.

## Related Documents

- [Workflow Overview](workflow-overview.md) — states and transitions
- [Accessioning Logic](accessioning-logic.md) — detailed accessioning decision logic
