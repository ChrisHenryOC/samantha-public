# IHC Staining, Scoring, and FISH Reflex Standard Operating Procedure

**Document ID:** SOP-IHC
**Version:** 1.0
**Effective Date:** 2026-02-01
**Workflow Step:** IHC_STAINING, IHC_QC, IHC_SCORING, SUGGEST_FISH_REFLEX, FISH_SEND_OUT
**Applicable Rules:** IHC-001 through IHC-011

---

## 1. Purpose

This procedure defines the immunohistochemistry (IHC) staining, quality control, scoring, and FISH reflex testing process for breast cancer specimens. IHC testing quantifies biomarker expression (ER, PR, HER2, Ki-67) to guide treatment decisions. This procedure also covers the HER2 equivocal pathway and FISH reflex testing.

## 2. Scope

This procedure applies to all orders routed to IHC_STAINING from the pathologist H&E review (per HE-005, HE-006, or HE-007). Orders diagnosed as benign (HE-008) bypass IHC entirely. The IHC panel is determined by the pathologist at H&E review and may differ from the originally ordered tests.

## 3. IHC Panel Selection

The IHC panel is determined by the pathologist's diagnosis at H&E review. The following standard panels apply:

| Diagnosis            | Standard IHC Panel          | Notes |
| --- | --- | --- |
| Invasive carcinoma   | ER, PR, HER2, Ki-67         | Pathologist may add or remove markers |
| DCIS                 | ER, PR                      | HER2 only if specifically ordered or added by pathologist |
| Suspicious / atypical | Pathologist-specified markers | System routes based on pathologist's panel, does not select markers |

The routing system tracks completeness against the **pathologist-determined panel**, not the original order. If the pathologist modifies the panel at H&E review, the updated panel becomes the basis for tracking.

## 4. Per-Slide Tracking

IHC processing operates on a per-slide basis. Each marker in the panel has its own slide(s), and events arrive individually per slide (e.g., "ER slide QC passed," "HER2 slide QC failed"). The system shall track the status of each slide independently and determine the overall order state based on the aggregate status of all slides.

The system shall not advance the order to scoring until all slides in the panel have completed their respective QC. Partial completion is a normal operating state — some slides may pass QC while others are still pending or require retry.

## 5. IHC Staining (IHC_STAINING)

The technician shall perform immunohistochemical staining for each marker in the pathologist-determined panel. Each marker requires its own slide with the appropriate antibody and detection chemistry.

- Entry condition: Order routed from pathologist H&E review (HE-005, HE-006, or HE-007), OR retry from IHC QC failure (IHC-004)
- Success outcome: All slides stained, advance to IHC_QC
- Events arrive per slide — the system shall track staining completion across all slides in the panel

## 6. IHC Staining Checks and Quality Control

### 6.1. Late HER2 Fixation Check (IHC-001)

Per IHC-001, when the pathologist adds HER2 to the panel at H&E review and the specimen's fixation is out of tolerance, the system shall reject the specimen for HER2 testing and flag the issue to the pathologist.

- Trigger: HER2 added by pathologist at H&E review AND fixation is out of tolerance (fixative is not formalin OR fixation time is outside 6-72 hours)
- Action: Reject specimen for HER2, flag to pathologist
- Flag set: `HER2_FIXATION_REJECT`
- Priority: 1

This check applies only when HER2 was **not** in the original order (that case is caught at accessioning by ACC-005 and ACC-006) but is added later by the pathologist during H&E review. The remaining markers in the panel (ER, PR, Ki-67) proceed normally — only the HER2 slide is rejected.

The pathologist is notified of the fixation rejection and may determine whether alternative testing is appropriate. The system does not make this clinical determination.

### 6.2. All Slides QC Passed (IHC-002)

Per IHC-002, when all slides in the panel have been stained and all have passed QC, the system shall route the order to scoring.

- Trigger: All slides stained AND all slides QC passed
- Action: Route to IHC_SCORING
- Priority: 2

### 6.3. Some Slides Still Pending (IHC-003)

Per IHC-003, when some slides have passed QC but others are still pending (not yet stained or not yet QC evaluated), the system shall hold the order and wait for the remaining slides.

- Trigger: Some slides pending (staining or QC not yet complete for all slides)
- Action: HOLD — wait for remaining slides
- Priority: 3
- The order remains in IHC_QC or IHC_STAINING until all slides have been processed

### 6.4. Staining Failed, Tissue Available (IHC-004)

Per IHC-004, when staining fails for one or more slides and tissue remains available, the system shall retry staining for the failed slides.

- Trigger: Staining failed for one or more slides, tissue available
- Action: RETRY staining for the failed slides
- Priority: 4
- Slides that have already passed QC are not restained — only the failed slides are retried

### 6.5. Staining Failed, Insufficient Tissue (IHC-005)

Per IHC-005, when staining fails and insufficient tissue remains for retry, the system shall abort the order.

- Trigger: Staining failed, insufficient tissue for retry
- Action: ABORT -> ORDER_TERMINATED_QNS
- Priority: 5

## 7. IHC Scoring and FISH Reflex

The technician or pathologist shall score each IHC slide using the appropriate quantitative scale for that marker. Scoring formats are specific to each biomarker:

| Marker | Scoring Format | Scale |
| --- | --- | --- |
| HER2 | Intensity score | 0, 1+, 2+, 3+ |
| ER | Percentage positive | 0-100% |
| PR | Percentage positive | 0-100% |
| Ki-67 | Proliferation index | 0-100% |

### 7.1. Scoring Complete, No Equivocal Results (IHC-006)

Per IHC-006, when scoring is complete for all slides and no equivocal results are present, the system shall route the order to resulting.

- Trigger: All slides scored, no HER2 equivocal (2+) result
- Action: Route to RESULTING
- Priority: 6

### 7.2. HER2 Equivocal (IHC-007)

Per IHC-007, when the HER2 score is 2+ (equivocal), the system shall suggest FISH reflex testing. FISH (fluorescence in situ hybridization) testing is required to resolve equivocal HER2 results and determine the definitive HER2 amplification status.

- Trigger: HER2 score is 2+ (equivocal)
- Action: SUGGEST_FISH_REFLEX — suggest FISH testing, requires pathologist approval
- Flag set: `FISH_SUGGESTED`
- Priority: 7

The system suggests FISH reflex testing but does not autonomously order it. Pathologist approval is required before proceeding.

### 7.3. Pathologist Approves FISH (IHC-008)

Per IHC-008, when the pathologist approves the FISH reflex, the system shall route the order to FISH_SEND_OUT.

- Trigger: Pathologist approves FISH reflex testing
- Action: Route to FISH_SEND_OUT (external test)
- Priority: 8
- The specimen is sent to an external reference laboratory for FISH testing. The system tracks the send-out and awaits the result.

### 7.4. Pathologist Declines FISH (IHC-009)

Per IHC-009, when the pathologist declines the FISH reflex, the system shall route the order to resulting with the equivocal HER2 result as-is.

- Trigger: Pathologist declines FISH reflex testing
- Action: Route to RESULTING
- Priority: 9
- The HER2 2+ (equivocal) result is reported without FISH confirmation.

### 7.5. FISH Result Received (IHC-010)

Per IHC-010, when the FISH result is received from the external laboratory, the system shall route the order to resulting.

- Trigger: FISH result received from external reference laboratory
- Action: Route to RESULTING
- Priority: 10
- The FISH result (amplified or not amplified) supplements the IHC scoring data for the final report.

### 7.6. FISH External Lab Returns QNS (IHC-011)

Per IHC-011, when the external FISH laboratory returns a quantity not sufficient (QNS) result, the system shall abort the order.

- Trigger: External FISH laboratory returns QNS
- Action: ABORT -> ORDER_TERMINATED_QNS
- Priority: 11
- The specimen was insufficient for FISH testing at the external laboratory.

## 8. Output Format

The system shall produce a structured JSON output for each IHC routing decision:

```json
{
  "next_state": "IHC_QC | IHC_SCORING | IHC_STAINING | RESULTING | SUGGEST_FISH_REFLEX | FISH_SEND_OUT | ORDER_TERMINATED_QNS",
  "applied_rules": ["IHC-002"],
  "flags": [],
  "reasoning": "Explanation of which rule applies and why"
}
```

Flags accumulated from prior workflow steps shall be preserved. IHC-specific flags (`HER2_FIXATION_REJECT`, `FISH_SUGGESTED`) are added when the corresponding rules are applied.
