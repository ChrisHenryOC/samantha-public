# Multi Rule Scenarios

**10 scenarios**

## Summary

| ID | Description | Rules | Final State | Steps |
|---|---|---|---|---|
| SC-080 | Multiple accessioning defects: missing name (ACC-001) + invalid site (ACC-003) → DO_NOT_PROCESS; REJECT beats HOLD | ACC-001, ACC-003 | DO_NOT_PROCESS | 1 |
| SC-081 | Multiple accessioning defects: missing name (ACC-001) + bad fixation time (ACC-006) → DO_NOT_PROCESS; REJECT beats HOLD | ACC-001, ACC-006 | DO_NOT_PROCESS | 1 |
| SC-082 | All accessioning defects: missing name + missing sex + invalid site + bad fixation + no billing → DO_NOT_PROCESS, applied_rules lists all 5 matching rules | ACC-001, ACC-002, ACC-003, ACC-006, ACC-007 | DO_NOT_PROCESS | 1 |
| SC-083 | HOLD vs PROCEED priority: missing sex (ACC-002, HOLD) + missing billing (ACC-007, PROCEED) → MISSING_INFO_HOLD; HOLD beats PROCEED | ACC-002, ACC-007 | MISSING_INFO_HOLD | 1 |
| SC-084 | H&E QC ambiguity: restain vs recut — backup slides available, restain preferred → HE_STAINING (HE-002) | ACC-008, HE-002, SP-001, SP-004 | HE_STAINING | 8 |
| SC-085 | H&E QC ambiguity: restain vs recut — no backup slides, recut is only option → SAMPLE_PREP_SECTIONING (HE-003) | ACC-008, HE-003, SP-001, SP-004 | SAMPLE_PREP_SECTIONING | 8 |
| SC-086 | False-positive probe: perfect order, all fields valid, model must not invent problems → ACCEPTED, applied_rules: [ACC-008] only | ACC-008, SP-001 | SAMPLE_PREP_PROCESSING | 2 |
| SC-087 | False-positive probe: pathologist says benign, HER2 was ordered → RESULTING (cancel IHC, don't reconcile HER2) | ACC-008, HE-001, HE-008, SP-001, SP-004 | RESULTING | 9 |
| SC-088 | False-positive probe: fixation at exactly 6.0hr boundary, HER2 ordered → ACCEPTED (boundary is valid, ACC-008 only) | ACC-008, SP-001 | SAMPLE_PREP_PROCESSING | 2 |
| SC-089 | False-positive probe: fixation at exactly 72.0hr boundary, HER2 ordered → ACCEPTED (boundary is valid, ACC-008 only) | ACC-008, SP-001 | SAMPLE_PREP_PROCESSING | 2 |

## Details

### SC-080: Multiple accessioning defects: missing name (ACC-001) + invalid site (ACC-003) → DO_NOT_PROCESS; REJECT beats HOLD

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, lung, formalin, 24.0h, name=null | DO_NOT_PROCESS | ACC-001, ACC-003 | — |

### SC-081: Multiple accessioning defects: missing name (ACC-001) + bad fixation time (ACC-006) → DO_NOT_PROCESS; REJECT beats HOLD

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 5.0h, name=null | DO_NOT_PROCESS | ACC-001, ACC-006 | — |

### SC-082: All accessioning defects: missing name + missing sex + invalid site + bad fixation + no billing → DO_NOT_PROCESS, applied_rules lists all 5 matching rules

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, lung, formalin, 5.0h, no billing, name=null, sex=null | DO_NOT_PROCESS | ACC-001, ACC-002, ACC-003, ACC-006, ACC-007 | — |

### SC-083: HOLD vs PROCEED priority: missing sex (ACC-002, HOLD) + missing billing (ACC-007, PROCEED) → MISSING_INFO_HOLD; HOLD beats PROCEED

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 24.0h, no billing, sex=null | MISSING_INFO_HOLD | ACC-002, ACC-007 | — |

### SC-084: H&E QC ambiguity: restain vs recut — backup slides available, restain preferred → HE_STAINING (HE-002)

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | excision, breast, formalin, 24.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | fail_restain, backup_slides=True | HE_STAINING | HE-002 | — |

### SC-085: H&E QC ambiguity: restain vs recut — no backup slides, recut is only option → SAMPLE_PREP_SECTIONING (HE-003)

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | excision, breast, formalin, 24.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | fail_recut, tissue_remaining=True, backup_slides=False | SAMPLE_PREP_SECTIONING | HE-003 | — |

### SC-086: False-positive probe: perfect order, all fields valid, model must not invent problems → ACCEPTED, applied_rules: [ACC-008] only

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 36.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |

### SC-087: False-positive probe: pathologist says benign, HER2 was ordered → RESULTING (cancel IHC, don't reconcile HER2)

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | excision, breast, formalin, 48.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |
| 9 | pathologist_he_review | benign | RESULTING | HE-008 | — |

### SC-088: False-positive probe: fixation at exactly 6.0hr boundary, HER2 ordered → ACCEPTED (boundary is valid, ACC-008 only)

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 6.0h, priority=rush | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |

### SC-089: False-positive probe: fixation at exactly 72.0hr boundary, HER2 ordered → ACCEPTED (boundary is valid, ACC-008 only)

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | excision, breast, formalin, 72.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
