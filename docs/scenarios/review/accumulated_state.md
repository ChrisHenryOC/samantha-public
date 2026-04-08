# Accumulated State Scenarios

**10 scenarios**

## Summary

| ID | Description | Rules | Final State | Steps |
|---|---|---|---|---|
| SC-090 | MISSING_INFO_PROCEED flag: set at accessioning, persists through all phases, blocks at RESULTING (RES-001) | ACC-007, HE-001, HE-005, IHC-002, IHC-006, RES-001, SP-001, SP-004 | RESULTING_HOLD | 13 |
| SC-091 | MISSING_INFO_PROCEED flag: set at accessioning, cleared mid-workflow when billing info received at RESULTING_HOLD (RES-002) | ACC-007, HE-001, HE-005, IHC-002, IHC-006, RES-001, RES-002, RES-003, SP-001, SP-004 | PATHOLOGIST_SIGNOUT | 15 |
| SC-092 | FIXATION_WARNING flag: set at accessioning for borderline fixation, persists informational through IHC (does not block) | ACC-008, HE-001, HE-005, IHC-002, IHC-006, SP-001, SP-004 | RESULTING | 12 |
| SC-093 | RECUT_REQUESTED flag: set at pathologist H&E review (HE-009), recut succeeds and returns to HE staining | ACC-008, HE-001, HE-009, SP-001, SP-004 | PATHOLOGIST_HE_REVIEW | 13 |
| SC-094 | HER2_FIXATION_REJECT flag: set at IHC_STAINING (IHC-001), persists through resulting to ORDER_COMPLETE | ACC-008, HE-001, HE-005, IHC-001, IHC-002, IHC-006, RES-003, RES-004, RES-005, SP-001, SP-004 | ORDER_COMPLETE | 16 |
| SC-095 | FISH_SUGGESTED flag: set at IHC_SCORING (IHC-007), pathologist approves FISH, FISH result received → RESULTING | ACC-008, HE-001, HE-005, IHC-002, IHC-007, IHC-008, IHC-010, SP-001, SP-004 | RESULTING | 14 |
| SC-096 | FISH_SUGGESTED flag: set at IHC_SCORING (IHC-007), pathologist declines FISH → RESULTING directly | ACC-008, HE-001, HE-005, IHC-002, IHC-007, IHC-009, SP-001, SP-004 | RESULTING | 13 |
| SC-097 | MISSING_INFO_PROCEED flag set at accessioning persists through workflow to resulting hold | ACC-007, HE-001, HE-005, IHC-002, IHC-006, RES-001, SP-001, SP-004 | RESULTING_HOLD | 13 |
| SC-098 | Flag clearing: MISSING_INFO_PROCEED cleared at RESULTING_HOLD, subsequent steps have empty flags through to ORDER_COMPLETE | ACC-007, HE-001, HE-005, IHC-002, IHC-006, RES-001, RES-002, RES-003, RES-004, RES-005, SP-001, SP-004 | ORDER_COMPLETE | 17 |
| SC-099 | Flag lifecycle: RECUT_REQUESTED set at H&E review, sample prep succeeds, flag persists to second H&E review where invasive carcinoma diagnosed | ACC-008, HE-001, HE-005, HE-009, SP-001, SP-004 | IHC_STAINING | 14 |

## Details

### SC-090: MISSING_INFO_PROCEED flag: set at accessioning, persists through all phases, blocks at RESULTING (RES-001)

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
| 12 | ihc_scoring | ER=75%; PR=60%; HER2=1+; Ki-67=12% | RESULTING | IHC-006 | MISSING_INFO_PROCEED |
| 13 | resulting_review | hold | RESULTING_HOLD | RES-001 | MISSING_INFO_PROCEED |

### SC-091: MISSING_INFO_PROCEED flag: set at accessioning, cleared mid-workflow when billing info received at RESULTING_HOLD (RES-002)

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
| 12 | ihc_scoring | ER=80%; PR=65%; HER2=1+; Ki-67=18% | RESULTING | IHC-006 | MISSING_INFO_PROCEED |
| 13 | resulting_review | hold | RESULTING_HOLD | RES-001 | MISSING_INFO_PROCEED |
| 14 | missing_info_received | billing=BCBS-12345 | RESULTING | RES-002 | — |
| 15 | resulting_review | advance | PATHOLOGIST_SIGNOUT | RES-003 | — |

### SC-092: FIXATION_WARNING flag: set at accessioning for borderline fixation, persists informational through IHC (does not block)

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 7.0h | ACCEPTED | ACC-008 | FIXATION_WARNING |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | FIXATION_WARNING |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | FIXATION_WARNING |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | FIXATION_WARNING |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | FIXATION_WARNING |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | FIXATION_WARNING |
| 7 | he_staining_complete | ok | HE_QC | — | FIXATION_WARNING |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | FIXATION_WARNING |
| 9 | pathologist_he_review | invasive_carcinoma | IHC_STAINING | HE-005 | FIXATION_WARNING |
| 10 | ihc_staining_complete | success | IHC_QC | — | FIXATION_WARNING |
| 11 | ihc_qc | 4 slides (4P/0F) | IHC_SCORING | IHC-002 | FIXATION_WARNING |
| 12 | ihc_scoring | ER=90%; PR=80%; HER2=1+; Ki-67=10% | RESULTING | IHC-006 | FIXATION_WARNING |

### SC-093: RECUT_REQUESTED flag: set at pathologist H&E review (HE-009), recut succeeds and returns to HE staining

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | excision, breast, formalin, 24.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |
| 9 | pathologist_he_review | recut_requested | SAMPLE_PREP_SECTIONING | HE-009 | RECUT_REQUESTED |
| 10 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 11 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 12 | he_staining_complete | ok | HE_QC | — | — |
| 13 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |

### SC-094: HER2_FIXATION_REJECT flag: set at IHC_STAINING (IHC-001), persists through resulting to ORDER_COMPLETE

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
| 11 | ihc_staining_complete | success | IHC_QC | — | HER2_FIXATION_REJECT |
| 12 | ihc_qc | 3 slides (3P/0F) | IHC_SCORING | IHC-002 | HER2_FIXATION_REJECT |
| 13 | ihc_scoring | ER=70%; PR=55%; Ki-67=22% | RESULTING | IHC-006 | HER2_FIXATION_REJECT |
| 14 | resulting_review | advance | PATHOLOGIST_SIGNOUT | RES-003 | HER2_FIXATION_REJECT |
| 15 | pathologist_signout | H&E, ER, PR, Ki-67 | REPORT_GENERATION | RES-004 | HER2_FIXATION_REJECT |
| 16 | report_generated | success | ORDER_COMPLETE | RES-005 | HER2_FIXATION_REJECT |

### SC-095: FISH_SUGGESTED flag: set at IHC_SCORING (IHC-007), pathologist approves FISH, FISH result received → RESULTING

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
| 12 | ihc_scoring | ER=85%; PR=70%; HER2=2+ (equivocal); Ki-67=20%, any_equivocal | SUGGEST_FISH_REFLEX | IHC-007 | FISH_SUGGESTED |
| 13 | fish_decision | approved=True | FISH_SEND_OUT | IHC-008 | — |
| 14 | fish_result | negative (success), ratio=1.1 | RESULTING | IHC-010 | — |

### SC-096: FISH_SUGGESTED flag: set at IHC_SCORING (IHC-007), pathologist declines FISH → RESULTING directly

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
| 12 | ihc_scoring | ER=60%; PR=45%; HER2=2+ (equivocal); Ki-67=30%, any_equivocal | SUGGEST_FISH_REFLEX | IHC-007 | FISH_SUGGESTED |
| 13 | fish_decision | approved=False | RESULTING | IHC-009 | — |

### SC-097: MISSING_INFO_PROCEED flag set at accessioning persists through workflow to resulting hold

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, 7.0h, no billing | MISSING_INFO_PROCEED | ACC-007 | MISSING_INFO_PROCEED |
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
| 12 | ihc_scoring | ER=75%; PR=60%; HER2=1+; Ki-67=15% | RESULTING | IHC-006 | MISSING_INFO_PROCEED |
| 13 | resulting_review | hold | RESULTING_HOLD | RES-001 | MISSING_INFO_PROCEED |

### SC-098: Flag clearing: MISSING_INFO_PROCEED cleared at RESULTING_HOLD, subsequent steps have empty flags through to ORDER_COMPLETE

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
| 12 | ihc_scoring | ER=92%; PR=78%; HER2=3+; Ki-67=25% | RESULTING | IHC-006 | MISSING_INFO_PROCEED |
| 13 | resulting_review | hold | RESULTING_HOLD | RES-001 | MISSING_INFO_PROCEED |
| 14 | missing_info_received | billing=AETNA-55555 | RESULTING | RES-002 | — |
| 15 | resulting_review | advance | PATHOLOGIST_SIGNOUT | RES-003 | — |
| 16 | pathologist_signout | H&E, ER, PR, HER2, Ki-67 | REPORT_GENERATION | RES-004 | — |
| 17 | report_generated | success | ORDER_COMPLETE | RES-005 | — |

### SC-099: Flag lifecycle: RECUT_REQUESTED set at H&E review, sample prep succeeds, flag persists to second H&E review where invasive carcinoma diagnosed

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | excision, breast, formalin, 24.0h | ACCEPTED | ACC-008 | — |
| 2 | grossing_complete | success | SAMPLE_PREP_PROCESSING | SP-001 | — |
| 3 | processing_complete | success | SAMPLE_PREP_EMBEDDING | SP-001 | — |
| 4 | embedding_complete | success | SAMPLE_PREP_SECTIONING | SP-001 | — |
| 5 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 6 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 7 | he_staining_complete | ok | HE_QC | — | — |
| 8 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |
| 9 | pathologist_he_review | recut_requested | SAMPLE_PREP_SECTIONING | HE-009 | RECUT_REQUESTED |
| 10 | sectioning_complete | success | SAMPLE_PREP_QC | SP-001 | — |
| 11 | sample_prep_qc | pass | HE_STAINING | SP-004 | — |
| 12 | he_staining_complete | ok | HE_QC | — | — |
| 13 | he_qc | pass | PATHOLOGIST_HE_REVIEW | HE-001 | — |
| 14 | pathologist_he_review | invasive_carcinoma | IHC_STAINING | HE-005 | — |
