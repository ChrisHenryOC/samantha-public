# H&E Staining and Pathologist Review Standard Operating Procedure

**Document ID:** SOP-HE
**Version:** 1.0
**Effective Date:** 2026-02-01
**Workflow Step:** HE_STAINING, HE_QC, PATHOLOGIST_HE_REVIEW
**Applicable Rules:** HE-001 through HE-009

---

## 1. Purpose

This procedure defines the hematoxylin and eosin (H&E) staining process, quality control evaluation, and pathologist review routing for breast cancer specimens. H&E staining produces the initial diagnostic slides that the pathologist reviews to determine the diagnosis and direct subsequent immunohistochemistry (IHC) testing.

## 2. Scope

This procedure applies to all orders that have passed sample preparation QC and been routed to HE_STAINING (per SP-004). The order's accumulated flags carry forward unchanged through H&E staining and QC. The pathologist review step may set the `RECUT_REQUESTED` flag.

## 3. H&E Staining (HE_STAINING)

The technician shall perform hematoxylin and eosin staining on the prepared tissue sections. H&E staining is the standard staining method for initial histologic evaluation, providing contrast between cellular nuclei (blue/purple via hematoxylin) and cytoplasm/extracellular matrix (pink via eosin).

- Entry condition: Order routed from sample prep QC pass (SP-004), OR retry from H&E QC restain (HE-002)
- Success outcome: Advance to HE_QC
- The staining step itself does not have pass/fail routing — all stained slides proceed to QC for evaluation

## 4. H&E Quality Control (HE_QC)

The technician shall evaluate the H&E-stained slides against the following quality criteria:

- **Stain quality**: Hematoxylin and eosin uptake shall be appropriate, with clear nuclear and cytoplasmic differentiation
- **Uniformity**: Staining shall be uniform across the tissue section without uneven coloring or blotching
- **Artifact assessment**: Slides shall be free of significant artifacts (air bubbles, tissue folds, precipitate, mounting defects) that would impair diagnostic evaluation

### 4.1. QC Pass (HE-001)

Per HE-001, when the H&E QC passes all checks, the system shall route the order to pathologist review.

- Trigger: H&E QC passes (stain quality, uniformity, and artifact assessment are all acceptable)
- Action: Route to PATHOLOGIST_HE_REVIEW

### 4.2. QC Failure — Restain Possible (HE-002)

Per HE-002, when the H&E QC fails and the deficiency can be corrected by restaining (e.g., weak stain uptake, uneven staining), the system shall route the order back to H&E staining for a new staining attempt.

- Trigger: H&E QC fails, restain is the appropriate corrective action
- Action: RETRY -> HE_STAINING

### 4.3. QC Failure — Recut Needed, Tissue Available (HE-003)

Per HE-003, when the H&E QC fails due to a deficiency that requires new tissue sections (e.g., tissue folds, section too thick, mounting defects) and tissue remains available, the system shall route the order back to sample preparation sectioning.

- Trigger: H&E QC fails, recut needed, tissue available
- Action: RETRY -> SAMPLE_PREP_SECTIONING

### 4.4. QC Failure — Insufficient Tissue (HE-004)

Per HE-004, when the H&E QC fails and insufficient tissue remains for either restaining or recutting, the system shall abort the order.

- Trigger: H&E QC fails, insufficient tissue for any corrective action
- Action: ABORT -> ORDER_TERMINATED_QNS

## 5. Pathologist H&E Review (PATHOLOGIST_HE_REVIEW)

The pathologist shall review the H&E-stained slides and render a morphologic assessment. The pathologist's diagnosis determines the subsequent IHC panel and routing. The routing system executes the pathologist's determination — it does not make diagnostic decisions.

### 5.1. Invasive Carcinoma (HE-005)

Per HE-005, when the pathologist diagnoses invasive carcinoma, the system shall route to IHC staining with the standard invasive carcinoma panel.

- Trigger: Pathologist diagnosis is invasive carcinoma
- Action: PROCEED_IHC with standard panel: ER, PR, HER2, Ki-67
- The pathologist may add or remove markers from this panel at their discretion. The system routes based on the pathologist's final panel determination, not a fixed panel.

### 5.2. DCIS — Ductal Carcinoma In Situ (HE-006)

Per HE-006, when the pathologist diagnoses ductal carcinoma in situ (DCIS), the system shall route to IHC staining with the DCIS panel.

- Trigger: Pathologist diagnosis is DCIS
- Action: PROCEED_IHC with standard panel: ER, PR. HER2 is included only if specifically ordered.
- The pathologist may add HER2 to the DCIS panel at their discretion.

### 5.3. Suspicious / Atypical (HE-007)

Per HE-007, when the pathologist renders a suspicious or atypical finding, the system shall route to IHC staining with a pathologist-customized panel.

- Trigger: Pathologist diagnosis is suspicious or atypical
- Action: PROCEED_IHC with pathologist-specified markers
- For suspicious/atypical findings, the pathologist determines which IHC markers to order. The system routes the order and tracks the pathologist-specified panel — it does not suggest or select markers.

### 5.4. Benign (HE-008)

Per HE-008, when the pathologist determines the specimen is benign, the system shall cancel IHC testing and route the order directly to resulting.

- Trigger: Pathologist diagnosis is benign
- Action: CANCEL_IHC_BENIGN -> route to RESULTING
- No IHC staining is performed. The order bypasses the IHC workflow entirely.

### 5.5. Recut Request (HE-009)

Per HE-009, when the pathologist requests recuts (additional tissue sections for improved diagnostic evaluation), the system shall route the order back to sample preparation sectioning and set the `RECUT_REQUESTED` flag.

- Trigger: Pathologist requests recuts
- Action: REQUEST_RECUTS -> SAMPLE_PREP_SECTIONING
- Flag set: `RECUT_REQUESTED`
- The `RECUT_REQUESTED` flag tracks that slides were recut, which affects tissue availability assessment for subsequent steps. After new sections are prepared and pass QC, the order returns to H&E staining and proceeds through the standard H&E workflow.

## 6. Panel Change Mechanics

When the pathologist modifies the IHC panel (adding or removing markers from the standard panel for the diagnosis), the `pathologist_he_review` event carries the updated test list. The laboratory information system updates the order's `ordered_tests` field, creates new slide rows for added markers, and sets removed slides to `cancelled` status. Cancelled slide rows are never deleted — they are preserved for audit trail purposes. The routing system sees the updated order state in its next evaluation.

## 7. Output Format

The system shall produce a structured JSON output for each H&E routing decision:

```json
{
  "next_state": "PATHOLOGIST_HE_REVIEW | HE_STAINING | SAMPLE_PREP_SECTIONING | ORDER_TERMINATED_QNS | IHC_STAINING | RESULTING",
  "applied_rules": ["HE-001"],
  "flags": [],
  "reasoning": "Explanation of which rule applies and why"
}
```

Flags accumulated from prior workflow steps shall be preserved in the output. The `RECUT_REQUESTED` flag is added only when HE-009 is applied.
