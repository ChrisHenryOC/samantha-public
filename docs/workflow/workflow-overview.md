# Workflow Overview

This document defines the breast cancer laboratory workflow — the states, transitions, and terminal conditions that govern how a specimen moves from accessioning through resulting.

## Scope

The laboratory processes **breast cancer specimens only**. Other anatomic sites may arrive but are rejected. The workflow covers accessioning through resulting for immunohistochemistry (IHC) testing.

## Core Principle

The workflow routing system is a **traffic cop**, not a diagnostician. It routes orders between steps and suggests next actions. All clinical decisions (diagnosis, scoring, marker selection for atypical cases) require pathologist approval. The system never makes autonomous clinical decisions.

## Workflow States

```text
ACCESSIONING
  ├── ACCEPTED → SAMPLE_PREP_PROCESSING
  ├── MISSING_INFO_PROCEED → SAMPLE_PREP_PROCESSING (but blocked before resulting)
  ├── MISSING_INFO_HOLD → (wait for info) → re-evaluate all rules
  └── DO_NOT_PROCESS → ORDER_TERMINATED

SAMPLE_PREP_PROCESSING → SAMPLE_PREP_EMBEDDING → SAMPLE_PREP_SECTIONING → SAMPLE_PREP_QC
  (at any step before QC: RETRY on failure with tissue available; ABORT if insufficient tissue → ORDER_TERMINATED_QNS)
  QC checks: section thickness, tissue integrity, mounting quality
  QC outcomes:
  ├── QC_PASS → HE_STAINING
  └── QC_FAIL → RETRY (back to SAMPLE_PREP_SECTIONING) or ABORT if insufficient tissue

H&E STAINING AND REVIEW:
HE_STAINING → HE_QC → PATHOLOGIST_HE_REVIEW
  HE QC checks: stain quality, uniformity, artifact assessment
  HE QC outcomes:
  ├── QC_PASS → PATHOLOGIST_HE_REVIEW
  ├── QC_FAIL (restain) → HE_STAINING
  ├── QC_FAIL (recut needed, tissue available) → SAMPLE_PREP_SECTIONING
  └── QC_FAIL (insufficient tissue) → ORDER_TERMINATED_QNS
  Pathologist review outcomes:
  ├── Tumor present (standard panel or pathologist-customized panel) → IHC_STAINING
  ├── Recuts needed → SAMPLE_PREP_SECTIONING
  └── Benign diagnosis → RESULTING (IHC cancelled)

IHC_STAINING → IHC_QC → IHC_SCORING
  IHC QC checks: stain quality and controls (pass/fail per slide)
  Events arrive per-slide (e.g., "ER slide QC passed", "HER2 slide QC failed")
  Model must track partial completion — some slides may pass while others need retry
  (retry if tissue available; abort if insufficient tissue)
  Scoring is quantitative: HER2 (0, 1+, 2+, 3+), ER/PR (percentage), Ki-67 (percentage)
  Scoring outcomes:
  ├── SCORING_COMPLETE → RESULTING
  └── HER2_EQUIVOCAL → SUGGEST_FISH_REFLEX (requires pathologist approval)
        ├── FISH_APPROVED → FISH_SEND_OUT (external test) → RESULTING or ORDER_TERMINATED_QNS
        └── FISH_DECLINED → RESULTING

RESULTING (check MISSING_INFO_PROCEED flag — hold if present, proceed if cleared)
  → PATHOLOGIST_SIGNOUT → REPORT_GENERATION → ORDER_COMPLETE
  At signout, pathologist determines which tests are included in the final report.
  Reported tests may be a subset of tests performed (pathologist discretion on clinical relevance).
  The set of reported tests is captured for downstream billing and clinical systems.
```

## Workflow Diagrams

### Accessioning

```mermaid
stateDiagram-v2
    state "Order arrives" as entry
    entry --> acc_eval

    acc_eval --> ACCEPTED: All validations pass
    acc_eval --> MISSING_INFO_HOLD: Missing patient name/sex
    acc_eval --> MISSING_INFO_PROCEED: Missing billing only
    acc_eval --> DO_NOT_PROCESS: Invalid site/specimen/fixation

    MISSING_INFO_HOLD --> acc_eval: Info received, re-evaluate

    state "→ Sample Prep" as exit_sp
    state "→ Sample Prep (flagged)" as exit_sp_flagged
    state "ORDER_TERMINATED" as exit_term

    ACCEPTED --> exit_sp
    MISSING_INFO_PROCEED --> exit_sp_flagged
    DO_NOT_PROCESS --> exit_term
```

### Sample Prep

```mermaid
stateDiagram-v2
    state "→ From Accessioning" as entry
    entry --> SAMPLE_PREP_PROCESSING

    SAMPLE_PREP_PROCESSING --> SAMPLE_PREP_EMBEDDING
    SAMPLE_PREP_EMBEDDING --> SAMPLE_PREP_SECTIONING
    SAMPLE_PREP_SECTIONING --> SAMPLE_PREP_QC

    SAMPLE_PREP_QC --> SAMPLE_PREP_SECTIONING: QC Fail (retry)

    state "→ H&E Staining and Review" as exit_he
    state "ORDER_TERMINATED_QNS" as exit_qns

    SAMPLE_PREP_QC --> exit_he: QC Pass
    SAMPLE_PREP_QC --> exit_qns: QC Fail (insufficient tissue)

    note right of SAMPLE_PREP_PROCESSING
        Any step can RETRY on failure
        with tissue available, or ABORT to
        ORDER_TERMINATED_QNS
    end note
```

### H&E Staining and Review

```mermaid
stateDiagram-v2
    state "→ From Sample Prep" as entry
    entry --> HE_STAINING

    HE_STAINING --> HE_QC
    HE_QC --> PATHOLOGIST_HE_REVIEW: QC Pass
    HE_QC --> HE_STAINING: QC Fail (restain)

    PATHOLOGIST_HE_REVIEW --> exit_ihc: Tumor present (HE-005/006/007)
    PATHOLOGIST_HE_REVIEW --> exit_recuts: Recuts needed (HE-009)
    PATHOLOGIST_HE_REVIEW --> exit_resulting: Benign (HE-008)

    state "→ IHC (IHC_STAINING)" as exit_ihc
    state "→ Sample Prep (SAMPLE_PREP_SECTIONING)" as exit_recuts
    state "→ Sample Prep (SAMPLE_PREP_SECTIONING)" as exit_qc_recut
    state "→ Resulting (RESULTING)" as exit_resulting
    state "ORDER_TERMINATED_QNS" as exit_qns
    HE_QC --> exit_qc_recut: QC Fail (recut needed)
    HE_QC --> exit_qns: QC Fail (insufficient tissue)
```

### IHC

```mermaid
stateDiagram-v2
    state "→ From H&E Review" as entry
    entry --> IHC_STAINING

    IHC_STAINING --> IHC_QC
    IHC_STAINING --> IHC_STAINING: HER2 fixation reject (IHC-001)
    IHC_QC --> IHC_SCORING: All slides QC pass
    IHC_QC --> IHC_STAINING: Stain failed (retry)

    IHC_SCORING --> SUGGEST_FISH_REFLEX: HER2 equivocal (only if HER2 in panel)
    SUGGEST_FISH_REFLEX --> FISH_SEND_OUT: Pathologist approves
    state "→ Resulting" as exit_resulting
    state "ORDER_TERMINATED_QNS" as exit_qns

    IHC_SCORING --> exit_resulting: Scoring complete
    SUGGEST_FISH_REFLEX --> exit_resulting: Pathologist declines
    FISH_SEND_OUT --> exit_resulting: FISH result received
    FISH_SEND_OUT --> exit_qns: External lab QNS
    IHC_QC --> exit_qns: Insufficient tissue

    note right of FISH_SEND_OUT
        FISH is an external send-out test.
        We send specimen and receive result
        or QNS — no internal FISH states.
    end note

    note right of IHC_STAINING
        Retry if tissue available, abort if not.
        FISH path only applies when HER2 is ordered.
    end note
```

### Resulting

```mermaid
stateDiagram-v2
    state "→ From H&E Benign" as entry2
    state "→ From IHC" as entry
    entry2 --> check_flags
    entry --> check_flags

    note right of check_flags
        check_flags is a decision point,
        not a persisted workflow state.
    end note

    check_flags --> RESULTING_HOLD: MISSING_INFO_PROCEED flag present
    check_flags --> RESULTING: No blocking flags
    RESULTING_HOLD --> check_flags: Flag cleared (info received)

    RESULTING --> PATHOLOGIST_SIGNOUT: Pathologist selects reportable tests
    PATHOLOGIST_SIGNOUT --> REPORT_GENERATION
    REPORT_GENERATION --> ORDER_COMPLETE

    note right of RESULTING_HOLD
        Order is held until missing info
        (e.g., billing) is provided and
        the flag is cleared.
    end note

    note right of PATHOLOGIST_SIGNOUT
        Reported tests may be a subset of
        tests performed. Pathologist determines
        clinical relevance at signout.
    end note
```

## State-to-Step Mapping

The state machine maps workflow states to rule-catalog steps for rule evaluation. This mapping lives in `src/workflow/state_machine.py` (`_STATE_TO_STEP`). Scenario authors need to know which states trigger which rules.

| State(s) | Rule-Catalog Step | Evaluation Mode | Notes |
|---|---|---|---|
| `ACCESSIONING` | `ACCESSIONING` | All-match | Every rule evaluated; actions accumulate by severity |
| `ACCEPTED`, `MISSING_INFO_PROCEED`, `SAMPLE_PREP_PROCESSING`, `SAMPLE_PREP_EMBEDDING`, `SAMPLE_PREP_SECTIONING`, `SAMPLE_PREP_QC` | `SAMPLE_PREP` | First-match, priority-ordered | ACCEPTED and MISSING_INFO_PROCEED are mapped to SAMPLE_PREP so grossing_complete events can fire SP-001 at those states |
| `HE_QC` | `HE_QC` | First-match, priority-ordered | |
| `PATHOLOGIST_HE_REVIEW` | `PATHOLOGIST_HE_REVIEW` | First-match, priority-ordered | |
| `IHC_STAINING`, `IHC_QC`, `IHC_SCORING`, `SUGGEST_FISH_REFLEX`, `FISH_SEND_OUT` | `IHC` (per-rule `applies_at`) | First-match, priority-ordered | Each IHC rule specifies which state it applies at via `applies_at` |
| `RESULTING`, `RESULTING_HOLD`, `PATHOLOGIST_SIGNOUT`, `REPORT_GENERATION` | `RESULTING` | First-match, priority-ordered | |
| `MISSING_INFO_HOLD`, `DO_NOT_PROCESS`, `HE_STAINING` | (none) | Pass-through | Transient states; no rules evaluated |
| `ORDER_COMPLETE`, `ORDER_TERMINATED`, `ORDER_TERMINATED_QNS` | (none) | Terminal | No rules evaluated |

## Terminal States

Orders can reach terminal states from multiple phases:
- **ORDER_TERMINATED** — from Accessioning (DO_NOT_PROCESS)
- **ORDER_TERMINATED_QNS** — from Sample Prep, H&E, or IHC (insufficient tissue)
- **ORDER_COMPLETE** — from Resulting (normal completion)

## Fixation Check

HER2 testing requires formalin fixation with fixation time between 6-72 hours. This check applies:

- At accessioning: if HER2 is ordered and fixation is out of tolerance -> DO_NOT_PROCESS
- At IHC stage: if HER2 becomes needed (pathologist adds it) but fixation is out of tolerance -> reject specimen for HER2, flag to pathologist

## Related Documents

- [Rule Catalog](rule-catalog.md) — all workflow rules by step
- [Accessioning Logic](accessioning-logic.md) — detailed accessioning decision logic
- [Pathologist Review Panels](pathologist-review-panels.md) — IHC panel mappings
