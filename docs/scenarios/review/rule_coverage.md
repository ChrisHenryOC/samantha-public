# Rule Coverage Scenarios

**79 scenarios**

## Summary

| ID | Description | Rules | Final State | Steps |
|---|---|---|---|---|
| SC-001 | ACC-008: Standard invasive, all fields valid, accepted | ACC-008, SP-001 | SAMPLE_PREP_PROCESSING | 2 |
| SC-002 | ACC-008: Fixation at upper boundary 72.0hr, accepted | ACC-008, SP-001 | SAMPLE_PREP_PROCESSING | 2 |
| SC-003 | ACC-001: Patient name missing, order held for missing info | ACC-001 | MISSING_INFO_HOLD | 1 |
| SC-004 | ACC-001: Patient name and billing missing; HOLD beats PROCEED, order held | ACC-001, ACC-007 | MISSING_INFO_HOLD | 1 |
| SC-005 | ACC-002: Patient sex missing, order held for missing info | ACC-002 | MISSING_INFO_HOLD | 1 |
| SC-006 | ACC-002: Patient name and sex both missing; both HOLD rules fire, order held | ACC-001, ACC-002 | MISSING_INFO_HOLD | 1 |
| SC-007 | ACC-003: Invalid anatomic site (lung), order rejected | ACC-003 | DO_NOT_PROCESS | 1 |
| SC-008 | ACC-003: Invalid site + missing name; REJECT beats HOLD | ACC-001, ACC-003 | DO_NOT_PROCESS | 1 |
| SC-009 | ACC-004: Incompatible specimen type (FNA), order rejected | ACC-004 | DO_NOT_PROCESS | 1 |
| SC-010 | ACC-004+ACC-005: Cytospin with alcohol fixative; both REJECT rules fire | ACC-004, ACC-005 | DO_NOT_PROCESS | 1 |
| SC-011 | ACC-005: HER2 ordered with non-formalin fixative (fresh), order rejected | ACC-005 | DO_NOT_PROCESS | 1 |
| SC-012 | ACC-005: Alcohol fixative, different patient; domain generalization | ACC-005 | DO_NOT_PROCESS | 1 |
| SC-013 | ACC-006: HER2 ordered with fixation time under 6 hours (5.0hr), order rejected | ACC-006 | DO_NOT_PROCESS | 1 |
| SC-014 | ACC-006: Fixation over 72hr (73.0hr), all else valid | ACC-006 | DO_NOT_PROCESS | 1 |
| SC-015 | ACC-007: Billing info missing, all else valid, order proceeds with flag | ACC-007 | MISSING_INFO_PROCEED | 1 |
| SC-016 | ACC-007: Billing missing, fixation at boundary 6.0hr | ACC-007 | MISSING_INFO_PROCEED | 1 |
| SC-017 | SP-001: Grossing success → SAMPLE_PREP_PROCESSING | ACC-008, SP-001 | SAMPLE_PREP_PROCESSING | 2 |
| SC-018 | SP-001: Processing success → SAMPLE_PREP_EMBEDDING (mid-chain progression) | ACC-008, SP-001 | SAMPLE_PREP_EMBEDDING | 3 |
| SC-019 | SP-002: Processing fails, tissue available (excision) → retry SAMPLE_PREP_PROCESSING (self-loop) | ACC-008, SP-001, SP-002 | SAMPLE_PREP_PROCESSING | 3 |
| SC-020 | SP-002: Sectioning fails, tissue available (excision) → retry SAMPLE_PREP_SECTIONING (self-loop) | ACC-008, SP-001, SP-002 | SAMPLE_PREP_SECTIONING | 5 |
| SC-021 | SP-003: Processing fails, insufficient tissue (biopsy) → ORDER_TERMINATED_QNS | ACC-008, SP-001, SP-003 | ORDER_TERMINATED_QNS | 3 |
| SC-022 | SP-003: Embedding fails, insufficient tissue (biopsy) → ORDER_TERMINATED_QNS (mid-chain) | ACC-008, SP-001, SP-003 | ORDER_TERMINATED_QNS | 4 |
| SC-023 | SP-004: Sample prep QC passes → HE_STAINING | ACC-008, SP-001, SP-004 | HE_STAINING | 6 |
| SC-024 | SP-004: QC passes after prior processing retry → HE_STAINING | ACC-008, SP-001, SP-002, SP-004 | HE_STAINING | 7 |
| SC-025 | SP-005: QC fails, tissue available (excision) → SAMPLE_PREP_SECTIONING | ACC-008, SP-001, SP-005 | SAMPLE_PREP_SECTIONING | 6 |
| SC-026 | SP-005: QC fails after prior re-section (excision) → SAMPLE_PREP_SECTIONING (2nd time) | ACC-008, SP-001, SP-005 | SAMPLE_PREP_SECTIONING | 8 |
| SC-027 | SP-006: QC fails, insufficient tissue (biopsy) → ORDER_TERMINATED_QNS | ACC-008, SP-001, SP-006 | ORDER_TERMINATED_QNS | 6 |
| SC-028 | SP-006: QC fails, QNS (biopsy), after prior sectioning retry → ORDER_TERMINATED_QNS | ACC-008, SP-001, SP-002, SP-006 | ORDER_TERMINATED_QNS | 7 |
| SC-029 | SP-002: Embedding fails, tissue available (excision) → retry SAMPLE_PREP_EMBEDDING (self-loop) | ACC-008, SP-001, SP-002 | SAMPLE_PREP_EMBEDDING | 4 |
| SC-030 | HE-001: H&E QC passes → PATHOLOGIST_HE_REVIEW | ACC-008, HE-001, SP-001, SP-004 | PATHOLOGIST_HE_REVIEW | 8 |
| SC-031 | HE-001: H&E QC passes on second attempt after restain (HE-002 then HE-001) → PATHOLOGIST_HE_REVIEW | ACC-008, HE-001, HE-002, SP-001, SP-004 | PATHOLOGIST_HE_REVIEW | 10 |
| SC-032 | HE-002: H&E QC fails, restain possible → HE_STAINING | ACC-008, HE-002, SP-001, SP-004 | HE_STAINING | 8 |
| SC-033 | HE-002: H&E QC fails, restain possible, tissue also available (excision) → HE_STAINING (restain preferred over recut) | ACC-008, HE-002, SP-001, SP-004 | HE_STAINING | 8 |
| SC-034 | HE-003: H&E QC fails, recut needed, tissue available → SAMPLE_PREP_SECTIONING | ACC-008, HE-003, SP-001, SP-004 | SAMPLE_PREP_SECTIONING | 8 |
| SC-035 | HE-003: H&E QC fails, no backup slides, tissue available → SAMPLE_PREP_SECTIONING (recut from block) | ACC-008, HE-003, SP-001, SP-004 | SAMPLE_PREP_SECTIONING | 8 |
| SC-036 | HE-004: H&E QC fails, insufficient tissue → ORDER_TERMINATED_QNS | ACC-008, HE-004, SP-001, SP-004 | ORDER_TERMINATED_QNS | 8 |
| SC-037 | HE-004: H&E QC fails, no backup slides, no tissue remaining → ORDER_TERMINATED_QNS | ACC-008, HE-004, SP-001, SP-004 | ORDER_TERMINATED_QNS | 8 |
| SC-038 | HE-005: Pathologist diagnoses invasive carcinoma → IHC_STAINING | ACC-008, HE-001, HE-005, SP-001, SP-004 | IHC_STAINING | 9 |
| SC-039 | HE-005: Pathologist diagnoses invasive carcinoma, adds E-cadherin marker → IHC_STAINING (panel modification) | ACC-008, HE-001, HE-005, SP-001, SP-004 | IHC_STAINING | 9 |
| SC-040 | HE-006: Pathologist diagnoses DCIS → IHC_STAINING | ACC-008, HE-001, HE-006, SP-001, SP-004 | IHC_STAINING | 9 |
| SC-041 | HE-006: Pathologist diagnoses DCIS, adds HER2 marker → IHC_STAINING (panel modification) | ACC-008, HE-001, HE-006, SP-001, SP-004 | IHC_STAINING | 9 |
| SC-042 | HE-007: Pathologist diagnoses suspicious/atypical → IHC_STAINING | ACC-008, HE-001, HE-007, SP-001, SP-004 | IHC_STAINING | 9 |
| SC-043 | HE-007: Pathologist diagnoses suspicious/atypical, custom markers added → IHC_STAINING (custom panel) | ACC-008, HE-001, HE-007, SP-001, SP-004 | IHC_STAINING | 9 |
| SC-044 | HE-008: Pathologist diagnoses benign → RESULTING (IHC cancelled) | ACC-008, HE-001, HE-008, SP-001, SP-004 | RESULTING | 9 |
| SC-045 | HE-008: Pathologist diagnoses benign, HER2 was ordered → RESULTING (IHC cancelled, no reconciliation needed) | ACC-008, HE-001, HE-008, SP-001, SP-004 | RESULTING | 9 |
| SC-046 | HE-009: Pathologist requests recuts → SAMPLE_PREP_SECTIONING (RECUT_REQUESTED flag) | ACC-008, HE-001, HE-009, SP-001, SP-004 | SAMPLE_PREP_SECTIONING | 9 |
| SC-047 | HE-009: Pathologist requests recuts, tissue limited (biopsy) → SAMPLE_PREP_SECTIONING (RECUT_REQUESTED flag) | ACC-008, HE-001, HE-009, SP-001, SP-004 | SAMPLE_PREP_SECTIONING | 9 |
| SC-048 | IHC-001: HER2 added at pathologist review, fixation out of tolerance → reject HER2 slide, set HER2_FIXATION_REJECT flag | ACC-008, HE-001, HE-005, IHC-001, SP-001, SP-004 | IHC_STAINING | 10 |
| SC-049 | IHC-001: HER2 added at pathologist review, fixation at boundary (6.0hr) → no reject (boundary is valid, false-positive probe) | ACC-008, HE-001, HE-005, SP-001, SP-004 | IHC_QC | 10 |
| SC-050 | IHC-002: All IHC slides QC passed → IHC_SCORING | ACC-008, HE-001, HE-005, IHC-002, SP-001, SP-004 | IHC_SCORING | 11 |
| SC-051 | IHC-002: All slides pass after one retry → IHC_SCORING (complicating: prior IHC-004 self-loop) | ACC-008, HE-001, HE-005, IHC-002, IHC-004, SP-001, SP-004 | IHC_SCORING | 13 |
| SC-052 | IHC-003: Some slides QC pending → hold at IHC_QC (self-loop) | ACC-008, HE-001, HE-005, IHC-003, SP-001, SP-004 | IHC_QC | 11 |
| SC-053 | IHC-003: 3 of 5 slides complete, 2 pending → hold at IHC_QC (per-slide event_data) | ACC-008, HE-001, HE-005, IHC-003, SP-001, SP-004 | IHC_QC | 11 |
| SC-054 | IHC-004: IHC staining failed → retry IHC_STAINING | ACC-008, HE-001, HE-005, IHC-004, SP-001, SP-004 | IHC_STAINING | 11 |
| SC-055 | IHC-004: Staining failed on specific marker, others pass → retry IHC_STAINING (partial failure) | ACC-008, HE-001, HE-005, IHC-004, SP-001, SP-004 | IHC_STAINING | 11 |
| SC-056 | IHC-005: IHC staining failed, insufficient tissue → ORDER_TERMINATED_QNS | ACC-008, HE-001, HE-005, IHC-005, SP-001, SP-004 | ORDER_TERMINATED_QNS | 11 |
| SC-057 | IHC-005: Staining failed after retry, no tissue → ORDER_TERMINATED_QNS | ACC-008, HE-001, HE-005, IHC-004, IHC-005, SP-001, SP-004 | ORDER_TERMINATED_QNS | 13 |
| SC-058 | IHC-006: Scoring complete, no equivocal results → RESULTING | ACC-008, HE-001, HE-005, IHC-002, IHC-006, SP-001, SP-004 | RESULTING | 12 |
| SC-059 | IHC-006: All scores definitive (ER 90%, PR 85%, HER2 3+, Ki-67 20%) → RESULTING | ACC-008, HE-001, HE-005, IHC-002, IHC-006, SP-001, SP-004 | RESULTING | 12 |
| SC-060 | IHC-007: HER2 equivocal (2+) → SUGGEST_FISH_REFLEX, set FISH_SUGGESTED flag | ACC-008, HE-001, HE-005, IHC-002, IHC-007, SP-001, SP-004 | SUGGEST_FISH_REFLEX | 12 |
| SC-061 | IHC-007: HER2 2+ with high Ki-67 → SUGGEST_FISH_REFLEX (complicating: other scores don't affect FISH decision) | ACC-008, HE-001, HE-005, IHC-002, IHC-007, SP-001, SP-004 | SUGGEST_FISH_REFLEX | 12 |
| SC-062 | IHC-008: Pathologist approves FISH → FISH_SEND_OUT | ACC-008, HE-001, HE-005, IHC-002, IHC-007, IHC-008, SP-001, SP-004 | FISH_SEND_OUT | 13 |
| SC-063 | IHC-008: Pathologist approves FISH on borderline fixation case → FISH_SEND_OUT | ACC-008, HE-001, HE-005, IHC-002, IHC-007, IHC-008, SP-001, SP-004 | FISH_SEND_OUT | 13 |
| SC-064 | IHC-009: Pathologist declines FISH → RESULTING | ACC-008, HE-001, HE-005, IHC-002, IHC-007, IHC-009, SP-001, SP-004 | RESULTING | 13 |
| SC-065 | IHC-009: Pathologist declines FISH, FISH_SUGGESTED flag still set → RESULTING | ACC-008, HE-001, HE-006, IHC-002, IHC-007, IHC-009, SP-001, SP-004 | RESULTING | 13 |
| SC-066 | IHC-010: FISH result received → RESULTING | ACC-008, HE-001, HE-005, IHC-002, IHC-007, IHC-008, IHC-010, SP-001, SP-004 | RESULTING | 14 |
| SC-067 | IHC-010: FISH amplified result → RESULTING (complicating: result changes clinical picture) | ACC-008, HE-001, HE-005, IHC-002, IHC-007, IHC-008, IHC-010, SP-001, SP-004 | RESULTING | 14 |
| SC-068 | IHC-011: FISH external lab reports QNS → ORDER_TERMINATED_QNS | ACC-008, HE-001, HE-005, IHC-002, IHC-007, IHC-008, IHC-011, SP-001, SP-004 | ORDER_TERMINATED_QNS | 14 |
| SC-069 | IHC-011: FISH lab QNS after extended processing → ORDER_TERMINATED_QNS | ACC-008, HE-001, HE-007, IHC-002, IHC-007, IHC-008, IHC-011, SP-001, SP-004 | ORDER_TERMINATED_QNS | 14 |
| SC-070 | RES-001: MISSING_INFO_PROCEED flag triggers RESULTING_HOLD on clean invasive path | ACC-007, HE-001, HE-005, IHC-002, IHC-006, RES-001, SP-001, SP-004 | RESULTING_HOLD | 13 |
| SC-071 | RES-001: MISSING_INFO_PROCEED flag after FISH pathway triggers RESULTING_HOLD | ACC-007, HE-001, HE-005, IHC-002, IHC-007, IHC-008, IHC-010, RES-001, SP-001, SP-004 | RESULTING_HOLD | 15 |
| SC-072 | RES-002: Info received at RESULTING_HOLD resolves to RESULTING | ACC-007, HE-001, HE-005, IHC-002, IHC-006, RES-001, RES-002, SP-001, SP-004 | RESULTING | 14 |
| SC-073 | RES-002: Irrelevant info received at RESULTING_HOLD — flag persists, remains in RESULTING_HOLD | ACC-007, HE-001, HE-005, IHC-002, IHC-006, RES-001, RES-002, SP-001, SP-004 | RESULTING_HOLD | 14 |
| SC-074 | RES-003: No flags, all complete, resulting_review advance to PATHOLOGIST_SIGNOUT | ACC-008, HE-001, HE-005, IHC-002, IHC-006, RES-003, SP-001, SP-004 | PATHOLOGIST_SIGNOUT | 13 |
| SC-075 | RES-003: After FISH pathway, resulting_review advance to PATHOLOGIST_SIGNOUT | ACC-008, HE-001, HE-005, IHC-002, IHC-007, IHC-008, IHC-010, RES-003, SP-001, SP-004 | PATHOLOGIST_SIGNOUT | 15 |
| SC-076 | RES-004: All tests reported, pathologist signout to REPORT_GENERATION | ACC-008, HE-001, HE-005, IHC-002, IHC-006, RES-003, RES-004, SP-001, SP-004 | REPORT_GENERATION | 14 |
| SC-077 | RES-004: Subset of tests reported, pathologist signout to REPORT_GENERATION | ACC-008, HE-001, HE-005, IHC-002, IHC-006, RES-003, RES-004, SP-001, SP-004 | REPORT_GENERATION | 14 |
| SC-078 | RES-005: Report generated, full clean path to ORDER_COMPLETE | ACC-008, HE-001, HE-005, IHC-002, IHC-006, RES-003, RES-004, RES-005, SP-001, SP-004 | ORDER_COMPLETE | 15 |
| SC-079 | RES-005: Full resulting lifecycle with RESULTING_HOLD, all 5 RES rules to ORDER_COMPLETE | ACC-007, HE-001, HE-005, IHC-002, IHC-006, RES-001, RES-002, RES-003, RES-004, RES-005, SP-001, SP-004 | ORDER_COMPLETE | 17 |

## Details

### SC-001: ACC-008: Standard invasive, all fields valid, accepted

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 24.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |

### SC-002: ACC-008: Fixation at upper boundary 72.0hr, accepted

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 72.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |

### SC-003: ACC-001: Patient name missing, order held for missing info

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 24.0h, name=null | MISSING_INFO_HOLD | ACC-001 | — |

### SC-004: ACC-001: Patient name and billing missing; HOLD beats PROCEED, order held

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 24.0h, no billing, name=null | MISSING_INFO_HOLD | ACC-001, ACC-007 | — |

### SC-005: ACC-002: Patient sex missing, order held for missing info

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 24.0h, sex=null | MISSING_INFO_HOLD | ACC-002 | — |

### SC-006: ACC-002: Patient name and sex both missing; both HOLD rules fire, order held

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 24.0h, name=null, sex=null | MISSING_INFO_HOLD | ACC-001, ACC-002 | — |

### SC-007: ACC-003: Invalid anatomic site (lung), order rejected

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, lung, formalin, 24.0h | DO_NOT_PROCESS | ACC-003 | — |

### SC-008: ACC-003: Invalid site + missing name; REJECT beats HOLD

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, lung, formalin, 24.0h, name=null | DO_NOT_PROCESS | ACC-001, ACC-003 | — |

### SC-009: ACC-004: Incompatible specimen type (FNA), order rejected

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | FNA, breast, formalin, 24.0h | DO_NOT_PROCESS | ACC-004 | — |

### SC-010: ACC-004+ACC-005: Cytospin with alcohol fixative; both REJECT rules fire

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | cytospin, breast, alcohol, 24.0h | DO_NOT_PROCESS | ACC-004, ACC-005 | — |

### SC-011: ACC-005: HER2 ordered with non-formalin fixative (fresh), order rejected

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, fresh, 24.0h | DO_NOT_PROCESS | ACC-005 | — |

### SC-012: ACC-005: Alcohol fixative, different patient; domain generalization

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, alcohol, 48.0h | DO_NOT_PROCESS | ACC-005 | — |

### SC-013: ACC-006: HER2 ordered with fixation time under 6 hours (5.0hr), order rejected

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 5.0h | DO_NOT_PROCESS | ACC-006 | — |

### SC-014: ACC-006: Fixation over 72hr (73.0hr), all else valid

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 73.0h | DO_NOT_PROCESS | ACC-006 | — |

### SC-015: ACC-007: Billing info missing, all else valid, order proceeds with flag

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 24.0h, no billing | MISSING_INFO_PROCEED | ACC-007 | MISSING_INFO_PROCEED |

### SC-016: ACC-007: Billing missing, fixation at boundary 6.0hr

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 6.0h, no billing | MISSING_INFO_PROCEED | ACC-007 | MISSING_INFO_PROCEED |

### SC-017: SP-001: Grossing success → SAMPLE_PREP_PROCESSING

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 24.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |

### SC-018: SP-001: Processing success → SAMPLE_PREP_EMBEDDING (mid-chain progression)

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 36.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |

### SC-019: SP-002: Processing fails, tissue available (excision) → retry SAMPLE_PREP_PROCESSING (self-loop)

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | excision, breast, formalin, 18.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | failure | SAMPLE_PREP_PROCESSING | SP-002 | — |

### SC-020: SP-002: Sectioning fails, tissue available (excision) → retry SAMPLE_PREP_SECTIONING (self-loop)

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | excision, breast, formalin, 48.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | failure | SAMPLE_PREP_SECTIONING | SP-002 | — |

### SC-021: SP-003: Processing fails, insufficient tissue (biopsy) → ORDER_TERMINATED_QNS

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 12.0h, priority=rush | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | failure | ORDER_TERMINATED_QNS | SP-003 | — |

### SC-022: SP-003: Embedding fails, insufficient tissue (biopsy) → ORDER_TERMINATED_QNS (mid-chain)

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 30.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | failure | ORDER_TERMINATED_QNS | SP-003 | — |

### SC-023: SP-004: Sample prep QC passes → HE_STAINING

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 24.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |

### SC-024: SP-004: QC passes after prior processing retry → HE_STAINING

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | excision, breast, formalin, 20.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | failure | SAMPLE_PREP_PROCESSING | SP-002 | — |
| 4 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 5 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 6 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 7 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |

### SC-025: SP-005: QC fails, tissue available (excision) → SAMPLE_PREP_SECTIONING

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | excision, breast, formalin, 24.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | fail_tissue_available | SAMPLE_PREP_SECTIONING | SP-005 | — |

### SC-026: SP-005: QC fails after prior re-section (excision) → SAMPLE_PREP_SECTIONING (2nd time)

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | excision, breast, formalin, 40.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | fail_tissue_available | SAMPLE_PREP_SECTIONING | SP-005 | — |
| 7 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 8 | sample_prep_qc | fail_tissue_available | SAMPLE_PREP_SECTIONING | SP-005 | — |

### SC-027: SP-006: QC fails, insufficient tissue (biopsy) → ORDER_TERMINATED_QNS

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 24.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | fail_qns | ORDER_TERMINATED_QNS | SP-006 | — |

### SC-028: SP-006: QC fails, QNS (biopsy), after prior sectioning retry → ORDER_TERMINATED_QNS

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 16.0h, priority=rush | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | failure | SAMPLE_PREP_SECTIONING | SP-002 | — |
| 6 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 7 | sample_prep_qc | fail_qns | ORDER_TERMINATED_QNS | SP-006 | — |

### SC-029: SP-002: Embedding fails, tissue available (excision) → retry SAMPLE_PREP_EMBEDDING (self-loop)

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | excision, breast, formalin, 22.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | failure | SAMPLE_PREP_EMBEDDING | SP-002 | — |

### SC-030: HE-001: H&E QC passes → PATHOLOGIST_HE_REVIEW

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 24.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |

### SC-031: HE-001: H&E QC passes on second attempt after restain (HE-002 then HE-001) → PATHOLOGIST_HE_REVIEW

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | excision, breast, formalin, 36.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | fail_restain | HE_STAINING | HE-002 | — |
| 9 | he_staining_complete | ok | HE_QC | — | — |
| 10 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |

### SC-032: HE-002: H&E QC fails, restain possible → HE_STAINING

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 18.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | fail_restain | HE_STAINING | HE-002 | — |

### SC-033: HE-002: H&E QC fails, restain possible, tissue also available (excision) → HE_STAINING (restain preferred over recut)

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | excision, breast, formalin, 32.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | fail_restain | HE_STAINING | HE-002 | — |

### SC-034: HE-003: H&E QC fails, recut needed, tissue available → SAMPLE_PREP_SECTIONING

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 12.0h, priority=rush | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | fail_recut | SAMPLE_PREP_SECTIONING | HE-003 | — |

### SC-035: HE-003: H&E QC fails, no backup slides, tissue available → SAMPLE_PREP_SECTIONING (recut from block)

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 20.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | fail_recut, backup_slides=False | SAMPLE_PREP_SECTIONING | HE-003 | — |

### SC-036: HE-004: H&E QC fails, insufficient tissue → ORDER_TERMINATED_QNS

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 8.0h, priority=rush | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | fail_qns | ORDER_TERMINATED_QNS | HE-004 | — |

### SC-037: HE-004: H&E QC fails, no backup slides, no tissue remaining → ORDER_TERMINATED_QNS

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 14.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | fail_qns, tissue_remaining=False, backup_slides=False | ORDER_TERMINATED_QNS | HE-004 | — |

### SC-038: HE-005: Pathologist diagnoses invasive carcinoma → IHC_STAINING

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 24.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |
| 9 | pathologist_he_review | invasive_carcinoma | IHC_STAINING | HE-005 | — |

### SC-039: HE-005: Pathologist diagnoses invasive carcinoma, adds E-cadherin marker → IHC_STAINING (panel modification)

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | excision, breast, formalin, 28.0h, priority=rush | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |
| 9 | pathologist_he_review | invasive_carcinoma | IHC_STAINING | HE-005 | — |

### SC-040: HE-006: Pathologist diagnoses DCIS → IHC_STAINING

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 22.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |
| 9 | pathologist_he_review | dcis | IHC_STAINING | HE-006 | — |

### SC-041: HE-006: Pathologist diagnoses DCIS, adds HER2 marker → IHC_STAINING (panel modification)

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | excision, breast, formalin, 40.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |
| 9 | pathologist_he_review | dcis | IHC_STAINING | HE-006 | — |

### SC-042: HE-007: Pathologist diagnoses suspicious/atypical → IHC_STAINING

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 16.0h, priority=rush | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |
| 9 | pathologist_he_review | suspicious_atypical | IHC_STAINING | HE-007 | — |

### SC-043: HE-007: Pathologist diagnoses suspicious/atypical, custom markers added → IHC_STAINING (custom panel)

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | excision, breast, formalin, 44.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |
| 9 | pathologist_he_review | suspicious_atypical | IHC_STAINING | HE-007 | — |

### SC-044: HE-008: Pathologist diagnoses benign → RESULTING (IHC cancelled)

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 20.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |
| 9 | pathologist_he_review | benign | RESULTING | HE-008 | — |

### SC-045: HE-008: Pathologist diagnoses benign, HER2 was ordered → RESULTING (IHC cancelled, no reconciliation needed)

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | excision, breast, formalin, 48.0h, priority=rush | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |
| 9 | pathologist_he_review | benign | RESULTING | HE-008 | — |

### SC-046: HE-009: Pathologist requests recuts → SAMPLE_PREP_SECTIONING (RECUT_REQUESTED flag)

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 30.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |
| 9 | pathologist_he_review | recut_requested | SAMPLE_PREP_SECTIONING | HE-009 | RECUT_REQUESTED |

### SC-047: HE-009: Pathologist requests recuts, tissue limited (biopsy) → SAMPLE_PREP_SECTIONING (RECUT_REQUESTED flag)

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 36.0h, priority=rush | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |
| 9 | pathologist_he_review | recut_requested | SAMPLE_PREP_SECTIONING | HE-009 | RECUT_REQUESTED |

### SC-048: IHC-001: HER2 added at pathologist review, fixation out of tolerance → reject HER2 slide, set HER2_FIXATION_REJECT flag

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 5.0h, tests=['ER', 'PR', 'Ki-67'] | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |
| 9 | pathologist_he_review | invasive_carcinoma | IHC_STAINING | HE-005 | — |
| 10 | ihc_staining_complete | partial | IHC_STAINING | IHC-001 | HER2_FIXATION_REJECT |

### SC-049: IHC-001: HER2 added at pathologist review, fixation at boundary (6.0hr) → no reject (boundary is valid, false-positive probe)

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 6.0h, tests=['ER', 'PR', 'Ki-67'] | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |
| 9 | pathologist_he_review | invasive_carcinoma | IHC_STAINING | HE-005 | — |
| 10 | ihc_staining_complete | success | IHC_QC | — | — |

### SC-050: IHC-002: All IHC slides QC passed → IHC_SCORING

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 24.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |
| 9 | pathologist_he_review | invasive_carcinoma | IHC_STAINING | HE-005 | — |
| 10 | ihc_staining_complete | success | IHC_QC | — | — |
| 11 | ihc_qc | 4 slides (4P/0F) | IHC_SCORING | IHC-002 | — |

### SC-051: IHC-002: All slides pass after one retry → IHC_SCORING (complicating: prior IHC-004 self-loop)

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | excision, breast, formalin, 30.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |
| 9 | pathologist_he_review | invasive_carcinoma | IHC_STAINING | HE-005 | — |
| 10 | ihc_staining_complete | success | IHC_QC | — | — |
| 11 | ihc_qc | 4 slides (3P/1F), all_complete=? | IHC_STAINING | IHC-004 | — |
| 12 | ihc_staining_complete | success | IHC_QC | — | — |
| 13 | ihc_qc | 4 slides (4P/0F) | IHC_SCORING | IHC-002 | — |

### SC-052: IHC-003: Some slides QC pending → hold at IHC_QC (self-loop)

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 18.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |
| 9 | pathologist_he_review | invasive_carcinoma | IHC_STAINING | HE-005 | — |
| 10 | ihc_staining_complete | success | IHC_QC | — | — |
| 11 | ihc_qc | 4 slides (3P/1F), all_complete=False | IHC_QC | IHC-003 | — |

### SC-053: IHC-003: 3 of 5 slides complete, 2 pending → hold at IHC_QC (per-slide event_data)

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | excision, breast, formalin, 36.0h, priority=rush | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |
| 9 | pathologist_he_review | invasive_carcinoma | IHC_STAINING | HE-005 | — |
| 10 | ihc_staining_complete | success | IHC_QC | — | — |
| 11 | ihc_qc | 5 slides (3P/2F), all_complete=False | IHC_QC | IHC-003 | — |

### SC-054: IHC-004: IHC staining failed → retry IHC_STAINING

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | excision, breast, formalin, 20.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |
| 9 | pathologist_he_review | invasive_carcinoma | IHC_STAINING | HE-005 | — |
| 10 | ihc_staining_complete | success | IHC_QC | — | — |
| 11 | ihc_qc | 4 slides (0P/4F), all_complete=? | IHC_STAINING | IHC-004 | — |

### SC-055: IHC-004: Staining failed on specific marker, others pass → retry IHC_STAINING (partial failure)

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | excision, breast, formalin, 28.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |
| 9 | pathologist_he_review | invasive_carcinoma | IHC_STAINING | HE-005 | — |
| 10 | ihc_staining_complete | success | IHC_QC | — | — |
| 11 | ihc_qc | 4 slides (3P/1F), all_complete=? | IHC_STAINING | IHC-004 | — |

### SC-056: IHC-005: IHC staining failed, insufficient tissue → ORDER_TERMINATED_QNS

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 24.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |
| 9 | pathologist_he_review | invasive_carcinoma | IHC_STAINING | HE-005 | — |
| 10 | ihc_staining_complete | success | IHC_QC | — | — |
| 11 | ihc_qc | 4 slides (0P/4F), all_complete=? | ORDER_TERMINATED_QNS | IHC-005 | — |

### SC-057: IHC-005: Staining failed after retry, no tissue → ORDER_TERMINATED_QNS

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 18.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |
| 9 | pathologist_he_review | invasive_carcinoma | IHC_STAINING | HE-005 | — |
| 10 | ihc_staining_complete | success | IHC_QC | — | — |
| 11 | ihc_qc | 4 slides (0P/4F), all_complete=? | IHC_STAINING | IHC-004 | — |
| 12 | ihc_staining_complete | failure | IHC_QC | — | — |
| 13 | ihc_qc | 4 slides (0P/4F), all_complete=? | ORDER_TERMINATED_QNS | IHC-005 | — |

### SC-058: IHC-006: Scoring complete, no equivocal results → RESULTING

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 24.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |
| 9 | pathologist_he_review | invasive_carcinoma | IHC_STAINING | HE-005 | — |
| 10 | ihc_staining_complete | success | IHC_QC | — | — |
| 11 | ihc_qc | 4 slides (4P/0F) | IHC_SCORING | IHC-002 | — |
| 12 | ihc_scoring | ER=85%; PR=70%; HER2=1+; Ki-67=15% | RESULTING | IHC-006 | — |

### SC-059: IHC-006: All scores definitive (ER 90%, PR 85%, HER2 3+, Ki-67 20%) → RESULTING

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | excision, breast, formalin, 42.0h, priority=rush | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |
| 9 | pathologist_he_review | invasive_carcinoma | IHC_STAINING | HE-005 | — |
| 10 | ihc_staining_complete | success | IHC_QC | — | — |
| 11 | ihc_qc | 4 slides (4P/0F) | IHC_SCORING | IHC-002 | — |
| 12 | ihc_scoring | ER=90%; PR=85%; HER2=3+; Ki-67=20% | RESULTING | IHC-006 | — |

### SC-060: IHC-007: HER2 equivocal (2+) → SUGGEST_FISH_REFLEX, set FISH_SUGGESTED flag

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 24.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |
| 9 | pathologist_he_review | invasive_carcinoma | IHC_STAINING | HE-005 | — |
| 10 | ihc_staining_complete | success | IHC_QC | — | — |
| 11 | ihc_qc | 4 slides (4P/0F) | IHC_SCORING | IHC-002 | — |
| 12 | ihc_scoring | ER=75%; PR=60%; HER2=2+ (equivocal); Ki-67=10%, any_equivocal | SUGGEST_FISH_REFLEX | IHC-007 | FISH_SUGGESTED |

### SC-061: IHC-007: HER2 2+ with high Ki-67 → SUGGEST_FISH_REFLEX (complicating: other scores don't affect FISH decision)

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | excision, breast, formalin, 36.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |
| 9 | pathologist_he_review | invasive_carcinoma | IHC_STAINING | HE-005 | — |
| 10 | ihc_staining_complete | success | IHC_QC | — | — |
| 11 | ihc_qc | 4 slides (4P/0F) | IHC_SCORING | IHC-002 | — |
| 12 | ihc_scoring | ER=40%; PR=20%; HER2=2+ (equivocal); Ki-67=45%, any_equivocal | SUGGEST_FISH_REFLEX | IHC-007 | FISH_SUGGESTED |

### SC-062: IHC-008: Pathologist approves FISH → FISH_SEND_OUT

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 24.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |
| 9 | pathologist_he_review | invasive_carcinoma | IHC_STAINING | HE-005 | — |
| 10 | ihc_staining_complete | success | IHC_QC | — | — |
| 11 | ihc_qc | 4 slides (4P/0F) | IHC_SCORING | IHC-002 | — |
| 12 | ihc_scoring | ER=80%; PR=55%; HER2=2+ (equivocal); Ki-67=18%, any_equivocal | SUGGEST_FISH_REFLEX | IHC-007 | FISH_SUGGESTED |
| 13 | fish_decision | approved=True | FISH_SEND_OUT | IHC-008 | — |

### SC-063: IHC-008: Pathologist approves FISH on borderline fixation case → FISH_SEND_OUT

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 6.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |
| 9 | pathologist_he_review | invasive_carcinoma | IHC_STAINING | HE-005 | — |
| 10 | ihc_staining_complete | success | IHC_QC | — | — |
| 11 | ihc_qc | 4 slides (4P/0F) | IHC_SCORING | IHC-002 | — |
| 12 | ihc_scoring | ER=65%; PR=40%; HER2=2+ (equivocal); Ki-67=25%, any_equivocal | SUGGEST_FISH_REFLEX | IHC-007 | FISH_SUGGESTED |
| 13 | fish_decision | approved=True | FISH_SEND_OUT | IHC-008 | — |

### SC-064: IHC-009: Pathologist declines FISH → RESULTING

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 20.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |
| 9 | pathologist_he_review | invasive_carcinoma | IHC_STAINING | HE-005 | — |
| 10 | ihc_staining_complete | success | IHC_QC | — | — |
| 11 | ihc_qc | 4 slides (4P/0F) | IHC_SCORING | IHC-002 | — |
| 12 | ihc_scoring | ER=50%; PR=30%; HER2=2+ (equivocal); Ki-67=12%, any_equivocal | SUGGEST_FISH_REFLEX | IHC-007 | FISH_SUGGESTED |
| 13 | fish_decision | approved=False | RESULTING | IHC-009 | — |

### SC-065: IHC-009: Pathologist declines FISH, FISH_SUGGESTED flag still set → RESULTING

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | excision, breast, formalin, 48.0h, priority=rush | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |
| 9 | pathologist_he_review | dcis | IHC_STAINING | HE-006 | — |
| 10 | ihc_staining_complete | success | IHC_QC | — | — |
| 11 | ihc_qc | 4 slides (4P/0F) | IHC_SCORING | IHC-002 | — |
| 12 | ihc_scoring | ER=95%; PR=80%; HER2=2+ (equivocal); Ki-67=8%, any_equivocal | SUGGEST_FISH_REFLEX | IHC-007 | FISH_SUGGESTED |
| 13 | fish_decision | approved=False | RESULTING | IHC-009 | — |

### SC-066: IHC-010: FISH result received → RESULTING

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 24.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |
| 9 | pathologist_he_review | invasive_carcinoma | IHC_STAINING | HE-005 | — |
| 10 | ihc_staining_complete | success | IHC_QC | — | — |
| 11 | ihc_qc | 4 slides (4P/0F) | IHC_SCORING | IHC-002 | — |
| 12 | ihc_scoring | ER=70%; PR=45%; HER2=2+ (equivocal); Ki-67=22%, any_equivocal | SUGGEST_FISH_REFLEX | IHC-007 | FISH_SUGGESTED |
| 13 | fish_decision | approved=True | FISH_SEND_OUT | IHC-008 | — |
| 14 | fish_result | negative (success) | RESULTING | IHC-010 | — |

### SC-067: IHC-010: FISH amplified result → RESULTING (complicating: result changes clinical picture)

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | excision, breast, formalin, 30.0h, priority=rush | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |
| 9 | pathologist_he_review | invasive_carcinoma | IHC_STAINING | HE-005 | — |
| 10 | ihc_staining_complete | success | IHC_QC | — | — |
| 11 | ihc_qc | 4 slides (4P/0F) | IHC_SCORING | IHC-002 | — |
| 12 | ihc_scoring | ER=10%; PR=5%; HER2=2+ (equivocal); Ki-67=35%, any_equivocal | SUGGEST_FISH_REFLEX | IHC-007 | FISH_SUGGESTED |
| 13 | fish_decision | approved=True | FISH_SEND_OUT | IHC-008 | — |
| 14 | fish_result | positive (success) | RESULTING | IHC-010 | — |

### SC-068: IHC-011: FISH external lab reports QNS → ORDER_TERMINATED_QNS

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 22.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |
| 9 | pathologist_he_review | invasive_carcinoma | IHC_STAINING | HE-005 | — |
| 10 | ihc_staining_complete | success | IHC_QC | — | — |
| 11 | ihc_qc | 4 slides (4P/0F) | IHC_SCORING | IHC-002 | — |
| 12 | ihc_scoring | ER=55%; PR=35%; HER2=2+ (equivocal); Ki-67=28%, any_equivocal | SUGGEST_FISH_REFLEX | IHC-007 | FISH_SUGGESTED |
| 13 | fish_decision | approved=True | FISH_SEND_OUT | IHC-008 | — |
| 14 | fish_result | qns (qns) | ORDER_TERMINATED_QNS | IHC-011 | — |

### SC-069: IHC-011: FISH lab QNS after extended processing → ORDER_TERMINATED_QNS

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 18.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |
| 9 | pathologist_he_review | suspicious_atypical | IHC_STAINING | HE-007 | — |
| 10 | ihc_staining_complete | success | IHC_QC | — | — |
| 11 | ihc_qc | 4 slides (4P/0F) | IHC_SCORING | IHC-002 | — |
| 12 | ihc_scoring | ER=30%; PR=15%; HER2=2+ (equivocal); Ki-67=40%, any_equivocal | SUGGEST_FISH_REFLEX | IHC-007 | FISH_SUGGESTED |
| 13 | fish_decision | approved=True | FISH_SEND_OUT | IHC-008 | — |
| 14 | fish_result | qns (qns) | ORDER_TERMINATED_QNS | IHC-011 | — |

### SC-070: RES-001: MISSING_INFO_PROCEED flag triggers RESULTING_HOLD on clean invasive path

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 24.0h, no billing | MISSING_INFO_PROCEED | ACC-007 | MISSING_INFO_PROCEED |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | MISSING_INFO_PROCEED |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | MISSING_INFO_PROCEED |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | MISSING_INFO_PROCEED |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | MISSING_INFO_PROCEED |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | MISSING_INFO_PROCEED |
| 7 | he_staining_complete | ok | HE_QC | — | MISSING_INFO_PROCEED |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | MISSING_INFO_PROCEED |
| 9 | pathologist_he_review | invasive_carcinoma | IHC_STAINING | HE-005 | MISSING_INFO_PROCEED |
| 10 | ihc_staining_complete | success | IHC_QC | — | MISSING_INFO_PROCEED |
| 11 | ihc_qc | 4 slides (4P/0F) | IHC_SCORING | IHC-002 | MISSING_INFO_PROCEED |
| 12 | ihc_scoring | ER=85%; PR=70%; HER2=1+; Ki-67=15% | RESULTING | IHC-006 | MISSING_INFO_PROCEED |
| 13 | resulting_review | hold | RESULTING_HOLD | RES-001 | MISSING_INFO_PROCEED |

### SC-071: RES-001: MISSING_INFO_PROCEED flag after FISH pathway triggers RESULTING_HOLD

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 24.0h, no billing | MISSING_INFO_PROCEED | ACC-007 | MISSING_INFO_PROCEED |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | MISSING_INFO_PROCEED |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | MISSING_INFO_PROCEED |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | MISSING_INFO_PROCEED |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | MISSING_INFO_PROCEED |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | MISSING_INFO_PROCEED |
| 7 | he_staining_complete | ok | HE_QC | — | MISSING_INFO_PROCEED |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | MISSING_INFO_PROCEED |
| 9 | pathologist_he_review | invasive_carcinoma | IHC_STAINING | HE-005 | MISSING_INFO_PROCEED |
| 10 | ihc_staining_complete | success | IHC_QC | — | MISSING_INFO_PROCEED |
| 11 | ihc_qc | 4 slides (4P/0F) | IHC_SCORING | IHC-002 | MISSING_INFO_PROCEED |
| 12 | ihc_scoring | ER=70%; PR=45%; HER2=2+ (equivocal); Ki-67=22%, any_equivocal | SUGGEST_FISH_REFLEX | IHC-007 | MISSING_INFO_PROCEED, FISH_SUGGESTED |
| 13 | fish_decision | approved=True | FISH_SEND_OUT | IHC-008 | MISSING_INFO_PROCEED, FISH_SUGGESTED |
| 14 | fish_result | negative (success) | RESULTING | IHC-010 | MISSING_INFO_PROCEED, FISH_SUGGESTED |
| 15 | resulting_review | hold | RESULTING_HOLD | RES-001 | MISSING_INFO_PROCEED, FISH_SUGGESTED |

### SC-072: RES-002: Info received at RESULTING_HOLD resolves to RESULTING

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 24.0h, no billing | MISSING_INFO_PROCEED | ACC-007 | MISSING_INFO_PROCEED |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | MISSING_INFO_PROCEED |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | MISSING_INFO_PROCEED |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | MISSING_INFO_PROCEED |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | MISSING_INFO_PROCEED |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | MISSING_INFO_PROCEED |
| 7 | he_staining_complete | ok | HE_QC | — | MISSING_INFO_PROCEED |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | MISSING_INFO_PROCEED |
| 9 | pathologist_he_review | invasive_carcinoma | IHC_STAINING | HE-005 | MISSING_INFO_PROCEED |
| 10 | ihc_staining_complete | success | IHC_QC | — | MISSING_INFO_PROCEED |
| 11 | ihc_qc | 4 slides (4P/0F) | IHC_SCORING | IHC-002 | MISSING_INFO_PROCEED |
| 12 | ihc_scoring | ER=85%; PR=70%; HER2=1+; Ki-67=15% | RESULTING | IHC-006 | MISSING_INFO_PROCEED |
| 13 | resulting_review | hold | RESULTING_HOLD | RES-001 | MISSING_INFO_PROCEED |
| 14 | missing_info_received | billing=BCBS-12345 | RESULTING | RES-002 | — |

### SC-073: RES-002: Irrelevant info received at RESULTING_HOLD — flag persists, remains in RESULTING_HOLD

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 24.0h, no billing | MISSING_INFO_PROCEED | ACC-007 | MISSING_INFO_PROCEED |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | MISSING_INFO_PROCEED |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | MISSING_INFO_PROCEED |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | MISSING_INFO_PROCEED |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | MISSING_INFO_PROCEED |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | MISSING_INFO_PROCEED |
| 7 | he_staining_complete | ok | HE_QC | — | MISSING_INFO_PROCEED |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | MISSING_INFO_PROCEED |
| 9 | pathologist_he_review | invasive_carcinoma | IHC_STAINING | HE-005 | MISSING_INFO_PROCEED |
| 10 | ihc_staining_complete | success | IHC_QC | — | MISSING_INFO_PROCEED |
| 11 | ihc_qc | 4 slides (4P/0F) | IHC_SCORING | IHC-002 | MISSING_INFO_PROCEED |
| 12 | ihc_scoring | ER=85%; PR=70%; HER2=1+; Ki-67=15% | RESULTING | IHC-006 | MISSING_INFO_PROCEED |
| 13 | resulting_review | hold | RESULTING_HOLD | RES-001 | MISSING_INFO_PROCEED |
| 14 | missing_info_received | specimen_orientation=lateral | RESULTING_HOLD | RES-002 | MISSING_INFO_PROCEED |

### SC-074: RES-003: No flags, all complete, resulting_review advance to PATHOLOGIST_SIGNOUT

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 24.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |
| 9 | pathologist_he_review | invasive_carcinoma | IHC_STAINING | HE-005 | — |
| 10 | ihc_staining_complete | success | IHC_QC | — | — |
| 11 | ihc_qc | 4 slides (4P/0F) | IHC_SCORING | IHC-002 | — |
| 12 | ihc_scoring | ER=85%; PR=70%; HER2=1+; Ki-67=15% | RESULTING | IHC-006 | — |
| 13 | resulting_review | advance | PATHOLOGIST_SIGNOUT | RES-003 | — |

### SC-075: RES-003: After FISH pathway, resulting_review advance to PATHOLOGIST_SIGNOUT

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 24.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |
| 9 | pathologist_he_review | invasive_carcinoma | IHC_STAINING | HE-005 | — |
| 10 | ihc_staining_complete | success | IHC_QC | — | — |
| 11 | ihc_qc | 4 slides (4P/0F) | IHC_SCORING | IHC-002 | — |
| 12 | ihc_scoring | ER=70%; PR=45%; HER2=2+ (equivocal); Ki-67=22%, any_equivocal | SUGGEST_FISH_REFLEX | IHC-007 | FISH_SUGGESTED |
| 13 | fish_decision | approved=True | FISH_SEND_OUT | IHC-008 | — |
| 14 | fish_result | negative (success) | RESULTING | IHC-010 | — |
| 15 | resulting_review | advance | PATHOLOGIST_SIGNOUT | RES-003 | — |

### SC-076: RES-004: All tests reported, pathologist signout to REPORT_GENERATION

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 24.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |
| 9 | pathologist_he_review | invasive_carcinoma | IHC_STAINING | HE-005 | — |
| 10 | ihc_staining_complete | success | IHC_QC | — | — |
| 11 | ihc_qc | 4 slides (4P/0F) | IHC_SCORING | IHC-002 | — |
| 12 | ihc_scoring | ER=85%; PR=70%; HER2=1+; Ki-67=15% | RESULTING | IHC-006 | — |
| 13 | resulting_review | advance | PATHOLOGIST_SIGNOUT | RES-003 | — |
| 14 | pathologist_signout | H&E, ER, PR, HER2, Ki-67 | REPORT_GENERATION | RES-004 | — |

### SC-077: RES-004: Subset of tests reported, pathologist signout to REPORT_GENERATION

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 24.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |
| 9 | pathologist_he_review | invasive_carcinoma | IHC_STAINING | HE-005 | — |
| 10 | ihc_staining_complete | success | IHC_QC | — | — |
| 11 | ihc_qc | 4 slides (4P/0F) | IHC_SCORING | IHC-002 | — |
| 12 | ihc_scoring | ER=85%; PR=70%; HER2=1+; Ki-67=15% | RESULTING | IHC-006 | — |
| 13 | resulting_review | advance | PATHOLOGIST_SIGNOUT | RES-003 | — |
| 14 | pathologist_signout | H&E, ER, PR | REPORT_GENERATION | RES-004 | — |

### SC-078: RES-005: Report generated, full clean path to ORDER_COMPLETE

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 24.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |
| 9 | pathologist_he_review | invasive_carcinoma | IHC_STAINING | HE-005 | — |
| 10 | ihc_staining_complete | success | IHC_QC | — | — |
| 11 | ihc_qc | 4 slides (4P/0F) | IHC_SCORING | IHC-002 | — |
| 12 | ihc_scoring | ER=85%; PR=70%; HER2=1+; Ki-67=15% | RESULTING | IHC-006 | — |
| 13 | resulting_review | advance | PATHOLOGIST_SIGNOUT | RES-003 | — |
| 14 | pathologist_signout | H&E, ER, PR, HER2, Ki-67 | REPORT_GENERATION | RES-004 | — |
| 15 | report_generated | success | ORDER_COMPLETE | RES-005 | — |

### SC-079: RES-005: Full resulting lifecycle with RESULTING_HOLD, all 5 RES rules to ORDER_COMPLETE

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 24.0h, no billing | MISSING_INFO_PROCEED | ACC-007 | MISSING_INFO_PROCEED |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | MISSING_INFO_PROCEED |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | MISSING_INFO_PROCEED |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | MISSING_INFO_PROCEED |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | MISSING_INFO_PROCEED |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | MISSING_INFO_PROCEED |
| 7 | he_staining_complete | ok | HE_QC | — | MISSING_INFO_PROCEED |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | MISSING_INFO_PROCEED |
| 9 | pathologist_he_review | invasive_carcinoma | IHC_STAINING | HE-005 | MISSING_INFO_PROCEED |
| 10 | ihc_staining_complete | success | IHC_QC | — | MISSING_INFO_PROCEED |
| 11 | ihc_qc | 4 slides (4P/0F) | IHC_SCORING | IHC-002 | MISSING_INFO_PROCEED |
| 12 | ihc_scoring | ER=85%; PR=70%; HER2=1+; Ki-67=15% | RESULTING | IHC-006 | MISSING_INFO_PROCEED |
| 13 | resulting_review | hold | RESULTING_HOLD | RES-001 | MISSING_INFO_PROCEED |
| 14 | missing_info_received | billing=UHC-67890 | RESULTING | RES-002 | — |
| 15 | resulting_review | advance | PATHOLOGIST_SIGNOUT | RES-003 | — |
| 16 | pathologist_signout | H&E, ER, PR, HER2, Ki-67 | REPORT_GENERATION | RES-004 | — |
| 17 | report_generated | success | ORDER_COMPLETE | RES-005 | — |
