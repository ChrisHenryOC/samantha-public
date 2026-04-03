# HER2 Fixation Requirements

This document defines the ASCO/CAP fixation requirements for HER2
immunohistochemistry testing. It serves as the authoritative reference for
fixation validation at both accessioning and the IHC stage.

## ASCO/CAP Fixation Standard

HER2 testing requires:

- **Fixative**: Formalin (required)
- **Fixation time**: 6 to 72 hours (inclusive)

### Boundary Behavior

Both boundary values are valid:

- 6.0 hours of fixation time is **valid** (meets minimum requirement)
- 72.0 hours of fixation time is **valid** (meets maximum requirement)
- Less than 6.0 hours is **out of tolerance**
- Greater than 72.0 hours is **out of tolerance**

This boundary behavior is important for false-positive testing. The model must
not reject specimens at exactly 6.0 or 72.0 hours.

## Validation Point 1: Accessioning

Fixation is checked at accessioning when HER2 is part of the original order.
Both rules are evaluated on every order where HER2 is ordered.

### ACC-005 — Wrong Fixative

- **Trigger**: HER2 is ordered AND fixative is not formalin
- **Action**: DO_NOT_PROCESS
- **Severity**: REJECT
- **Rationale**: Non-formalin fixation invalidates HER2 IHC results per ASCO/CAP
  guidelines. The specimen cannot be processed for HER2 testing.

### ACC-006 — Fixation Time Out of Tolerance

- **Trigger**: HER2 is ordered AND fixation time is outside 6-72 hours
  (less than 6.0 or greater than 72.0)
- **Action**: DO_NOT_PROCESS
- **Severity**: REJECT
- **Rationale**: Fixation time outside the 6-72 hour window compromises antigen
  preservation and produces unreliable HER2 results per ASCO/CAP guidelines.

**Null fixation time**: ACC-006 does not fire when fixation time is null. A null
value means fixation time was not recorded — it is missing data, not an
out-of-range measurement. Null fixation time is handled by ACC-009 instead.

### ACC-009 — Fixation Time Missing (Null)

- **Trigger**: HER2 is ordered AND fixation time is null
- **Action**: MISSING_INFO_HOLD — hold order, request fixation time
- **Severity**: HOLD
- **Rationale**: A null fixation time means the value was not recorded. The order
  cannot be accepted or rejected without knowing the fixation time, so it is held
  until the information is provided. This is distinct from a recorded value
  outside 6-72 hours, which is a definitive tolerance violation handled by
  ACC-006.

### Accessioning Behavior

Both ACC-005 and ACC-006 produce DO_NOT_PROCESS outcomes. If HER2 is not in the
ordered tests, these rules do not apply. Multiple accessioning rules can fire
simultaneously — the highest-severity outcome wins (DO_NOT_PROCESS > MISSING_INFO_HOLD
\> MISSING_INFO_PROCEED > ACCEPTED).

## Validation Point 2: IHC Stage

Fixation is rechecked at the IHC stage when the pathologist adds HER2 at H&E
review. This catches cases where HER2 was not originally ordered (and therefore
not checked at accessioning) but the pathologist later determines it is needed.

### IHC-001 — HER2 Added with Fixation Out of Tolerance

- **Trigger**: HER2 is added by the pathologist at H&E review AND fixation is
  out of tolerance (wrong fixative or fixation time outside 6-72 hours)
- **Action**: Reject the specimen for HER2 testing. Flag to pathologist.
- **Priority**: 1 (evaluated first among IHC rules)
- **Flag set**: HER2_FIXATION_REJECT
- **Rationale**: Even though the specimen passed accessioning without HER2
  fixation checks (because HER2 was not originally ordered), the ASCO/CAP
  requirements still apply. The specimen cannot be used for HER2 IHC.

### IHC Stage Behavior

When IHC-001 fires, HER2 testing is rejected but other ordered IHC markers
(ER, PR, Ki-67) may still proceed if their staining is unaffected. The
HER2_FIXATION_REJECT flag alerts the pathologist that HER2 could not be
performed due to fixation non-compliance.

## Decision Summary

| Checkpoint | Condition | Rule | Outcome | Flag |
|------------|-----------|------|---------|------|
| Accessioning | HER2 ordered + not formalin | ACC-005 | DO_NOT_PROCESS | — |
| Accessioning | HER2 ordered + time outside 6-72h | ACC-006 | DO_NOT_PROCESS | — |
| Accessioning | HER2 ordered + fixation time null | ACC-009 | MISSING_INFO_HOLD | — |
| IHC stage | HER2 added + fixation out of tolerance | IHC-001 | Reject HER2, flag pathologist | HER2_FIXATION_REJECT |

## Related Rules

- ACC-005: HER2 fixative validation at accessioning
- ACC-006: HER2 fixation time validation at accessioning
- ACC-009: HER2 fixation time null validation at accessioning
- IHC-001: HER2 fixation validation at IHC stage
