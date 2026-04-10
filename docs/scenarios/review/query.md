# Query Scenarios

**27 scenarios**

## Summary

| ID | Tier | Description | Answer Type | Expected Orders |
|---|---|---|---|---|
| QR-001 | 1 | Simple lookup — orders ready for grossing (ACCEPTED state) | order_list | ORD-101, ORD-103, ORD-105 |
| QR-002 | 1 | Simple lookup — orders currently in sample preparation | order_list | ORD-201, ORD-203, ORD-204, ORD-206 |
| QR-003 | 1 | Simple lookup — orders needing H&E quality control review | order_list | ORD-301, ORD-304 |
| QR-004 | 1 | Simple lookup — orders awaiting pathologist H&E review | order_list | ORD-401, ORD-403, ORD-406 |
| QR-005 | 1 | Simple lookup — orders in IHC staining | order_list | ORD-501, ORD-503 |
| QR-006 | 1 | Simple lookup — orders currently on hold | order_list | ORD-601, ORD-603, ORD-606 |
| QR-007 | 1 | Simple lookup — orders ready for pathologist signout | order_list | ORD-701, ORD-704 |
| QR-008 | 1 | Simple lookup — rush priority orders across all active states | order_list | ORD-801, ORD-803, ORD-806 |
| QR-009 | 2 | Order status — next step for an order in ACCEPTED state | order_status | ORD-901 |
| QR-010 | 2 | Order status — order currently in tissue processing | order_status | ORD-1002 |
| QR-011 | 2 | Order status — checking if a completed order is done | order_status | ORD-1101 |
| QR-012 | 2 | Order status — identifying what is blocking a held order | order_status | ORD-1201 |
| QR-013 | 2 | Order status — locating an order in the IHC scoring step | order_status | ORD-1302 |
| QR-014 | 2 | Order status — checking if an order has been rejected | order_status | ORD-1401 |
| QR-015 | 3 | Flag reasoning — why an order is on hold at resulting | order_status | ORD-1501 |
| QR-016 | 3 | Flag reasoning — identifying flags affecting an order | order_status | ORD-1603 |
| QR-017 | 3 | Flag reasoning — whether an order can proceed to signout | order_status | ORD-1703 |
| QR-018 | 3 | Flag reasoning — what must happen before an order can be released | order_status | ORD-1804 |
| QR-019 | 3 | Flag reasoning — why HER2 testing was rejected for an order | order_status | ORD-1905 |
| QR-020 | 4 | Prioritization — ranking grossing orders by priority and age | prioritized_list | ORD-2004, ORD-2002, ORD-2003, ORD-2005, ORD-2001 |
| QR-021 | 4 | Prioritization — rank all orders on the IHC bench by urgency | prioritized_list | ORD-2110, ORD-2102, ORD-2103, ORD-2104, ORD-2105, ORD-2101 |
| QR-022 | 4 | Prioritization — selecting top 3 signout cases by priority and age | prioritized_list | ORD-2202, ORD-2204, ORD-2203 |
| QR-023 | 5 | Cross-order reasoning — identifying orders at risk of fixation timing out | order_list | ORD-2303, ORD-2301, ORD-2310 |
| QR-024 | 5 | Cross-order reasoning — identifying orders needing pathologist attention | order_list | ORD-2401, ORD-2407, ORD-2403, ORD-2405, ORD-2411 |
| QR-025 | 5 | Cross-order reasoning — identifying orders with flags or issues needing resolution | order_list | ORD-2501, ORD-2502, ORD-2504, ORD-2506, ORD-2507, ORD-2510 |
| QR-026 | 5 | Cross-order reasoning — identifying orders that appear stuck | order_list | ORD-2605, ORD-2603, ORD-2601 |
| QR-027 | 5 | Cross-order reasoning — orders waiting on external results | order_list | ORD-2701, ORD-2703 |

## Details

### QR-001 (Tier 1): Simple lookup — orders ready for grossing (ACCEPTED state)

**Query:** What orders are ready for grossing?

**Database State:**

| Order ID | State | Specimen | Priority | Flags | Created |
|---|---|---|---|---|---|
| ORD-101 | ACCEPTED | biopsy | routine | — | 2025-01-15 08:00:00 |
| ORD-102 | SAMPLE_PREP_PROCESSING | excision | routine | — | 2025-01-15 08:30:00 |
| ORD-103 | ACCEPTED | resection | rush | — | 2025-01-15 09:00:00 |
| ORD-104 | HE_STAINING | biopsy | routine | — | 2025-01-14 14:00:00 |
| ORD-105 | ACCEPTED | biopsy | routine | — | 2025-01-15 09:15:00 |
| ORD-106 | ORDER_COMPLETE | excision | routine | — | 2025-01-13 10:00:00 |
| ORD-107 | ACCESSIONING | biopsy | routine | — | 2025-01-15 09:30:00 |

**Expected Output:**

- **Answer type:** order_list
- **Order IDs:** ORD-101, ORD-103, ORD-105
- **Reasoning:** Orders in ACCEPTED state have completed accessioning and are ready for grossing. ORD-101, ORD-103, and ORD-105 are all in ACCEPTED state.

### QR-002 (Tier 1): Simple lookup — orders currently in sample preparation

**Query:** Which orders are currently going through sample prep?

**Database State:**

| Order ID | State | Specimen | Priority | Flags | Created |
|---|---|---|---|---|---|
| ORD-201 | SAMPLE_PREP_PROCESSING | biopsy | routine | — | 2025-01-14 08:00:00 |
| ORD-202 | ACCEPTED | excision | rush | — | 2025-01-15 07:00:00 |
| ORD-203 | SAMPLE_PREP_EMBEDDING | resection | routine | — | 2025-01-14 09:00:00 |
| ORD-204 | SAMPLE_PREP_SECTIONING | biopsy | routine | — | 2025-01-14 10:00:00 |
| ORD-205 | HE_STAINING | biopsy | routine | — | 2025-01-13 14:00:00 |
| ORD-206 | SAMPLE_PREP_QC | excision | rush | — | 2025-01-14 11:00:00 |
| ORD-207 | ORDER_COMPLETE | biopsy | routine | — | 2025-01-12 08:00:00 |
| ORD-208 | PATHOLOGIST_HE_REVIEW | resection | routine | — | 2025-01-13 08:00:00 |

**Expected Output:**

- **Answer type:** order_list
- **Order IDs:** ORD-201, ORD-203, ORD-204, ORD-206
- **Reasoning:** Orders in sample preparation include those in SAMPLE_PREP_PROCESSING, SAMPLE_PREP_EMBEDDING, SAMPLE_PREP_SECTIONING, and SAMPLE_PREP_QC states. ORD-201 is in processing, ORD-203 in embedding, ORD-204 in sectioning, and ORD-206 in QC.

### QR-003 (Tier 1): Simple lookup — orders needing H&E quality control review

**Query:** What orders need H&E QC right now?

**Database State:**

| Order ID | State | Specimen | Priority | Flags | Created |
|---|---|---|---|---|---|
| ORD-301 | HE_QC | biopsy | routine | — | 2025-01-14 08:00:00 |
| ORD-302 | HE_STAINING | excision | rush | — | 2025-01-14 09:00:00 |
| ORD-303 | PATHOLOGIST_HE_REVIEW | biopsy | routine | — | 2025-01-13 14:00:00 |
| ORD-304 | HE_QC | resection | rush | — | 2025-01-14 10:00:00 |
| ORD-305 | ACCEPTED | biopsy | routine | — | 2025-01-15 07:00:00 |
| ORD-306 | IHC_STAINING | excision | routine | — | 2025-01-13 10:00:00 |

**Expected Output:**

- **Answer type:** order_list
- **Order IDs:** ORD-301, ORD-304
- **Reasoning:** Orders in HE_QC state are awaiting H&E quality control review. ORD-301 and ORD-304 are both in HE_QC state.

### QR-004 (Tier 1): Simple lookup — orders awaiting pathologist H&E review

**Query:** Which cases are waiting for the pathologist to review H&E slides?

**Database State:**

| Order ID | State | Specimen | Priority | Flags | Created |
|---|---|---|---|---|---|
| ORD-401 | PATHOLOGIST_HE_REVIEW | biopsy | rush | — | 2025-01-14 07:00:00 |
| ORD-402 | HE_QC | excision | routine | — | 2025-01-14 08:30:00 |
| ORD-403 | PATHOLOGIST_HE_REVIEW | resection | routine | — | 2025-01-14 06:00:00 |
| ORD-404 | IHC_SCORING | biopsy | routine | — | 2025-01-13 14:00:00 |
| ORD-405 | SAMPLE_PREP_PROCESSING | biopsy | routine | — | 2025-01-15 08:00:00 |
| ORD-406 | PATHOLOGIST_HE_REVIEW | biopsy | routine | FIXATION_WARNING | 2025-01-14 09:00:00 |
| ORD-407 | RESULTING | excision | routine | — | 2025-01-13 10:00:00 |

**Expected Output:**

- **Answer type:** order_list
- **Order IDs:** ORD-401, ORD-403, ORD-406
- **Reasoning:** Orders in PATHOLOGIST_HE_REVIEW state are waiting for pathologist H&E review. ORD-401, ORD-403, and ORD-406 are all in this state.

### QR-005 (Tier 1): Simple lookup — orders in IHC staining

**Query:** Show me orders that are currently undergoing IHC staining.

**Database State:**

| Order ID | State | Specimen | Priority | Flags | Created |
|---|---|---|---|---|---|
| ORD-501 | IHC_STAINING | biopsy | routine | — | 2025-01-13 08:00:00 |
| ORD-502 | PATHOLOGIST_HE_REVIEW | excision | rush | — | 2025-01-14 07:00:00 |
| ORD-503 | IHC_STAINING | resection | rush | — | 2025-01-13 09:00:00 |
| ORD-504 | IHC_QC | biopsy | routine | — | 2025-01-13 07:00:00 |
| ORD-505 | ACCEPTED | biopsy | routine | — | 2025-01-15 08:00:00 |
| ORD-506 | HE_STAINING | excision | routine | — | 2025-01-14 10:00:00 |

**Expected Output:**

- **Answer type:** order_list
- **Order IDs:** ORD-501, ORD-503
- **Reasoning:** Orders in IHC_STAINING state are currently undergoing immunohistochemistry staining. ORD-501 and ORD-503 are in this state.

### QR-006 (Tier 1): Simple lookup — orders currently on hold

**Query:** Are any orders on hold right now?

**Database State:**

| Order ID | State | Specimen | Priority | Flags | Created |
|---|---|---|---|---|---|
| ORD-601 | MISSING_INFO_HOLD | biopsy | routine | — | 2025-01-14 08:00:00 |
| ORD-602 | ACCEPTED | excision | rush | — | 2025-01-15 07:00:00 |
| ORD-603 | RESULTING_HOLD | biopsy | routine | MISSING_INFO_PROCEED | 2025-01-13 10:00:00 |
| ORD-604 | HE_STAINING | resection | routine | — | 2025-01-14 09:00:00 |
| ORD-605 | SAMPLE_PREP_PROCESSING | biopsy | routine | — | 2025-01-14 10:00:00 |
| ORD-606 | MISSING_INFO_HOLD | excision | rush | — | 2025-01-15 06:00:00 |
| ORD-607 | PATHOLOGIST_SIGNOUT | biopsy | routine | — | 2025-01-12 14:00:00 |

**Expected Output:**

- **Answer type:** order_list
- **Order IDs:** ORD-601, ORD-603, ORD-606
- **Reasoning:** Orders on hold include those in MISSING_INFO_HOLD and RESULTING_HOLD states. ORD-601 and ORD-606 are in MISSING_INFO_HOLD, and ORD-603 is in RESULTING_HOLD.

### QR-007 (Tier 1): Simple lookup — orders ready for pathologist signout

**Query:** What cases are ready for the pathologist to sign out?

**Database State:**

| Order ID | State | Specimen | Priority | Flags | Created |
|---|---|---|---|---|---|
| ORD-701 | PATHOLOGIST_SIGNOUT | biopsy | routine | — | 2025-01-13 08:00:00 |
| ORD-702 | RESULTING | excision | routine | — | 2025-01-13 09:00:00 |
| ORD-703 | IHC_SCORING | resection | rush | — | 2025-01-14 07:00:00 |
| ORD-704 | PATHOLOGIST_SIGNOUT | excision | rush | — | 2025-01-13 10:00:00 |
| ORD-705 | REPORT_GENERATION | biopsy | routine | — | 2025-01-12 14:00:00 |
| ORD-706 | ACCEPTED | biopsy | routine | — | 2025-01-15 08:00:00 |

**Expected Output:**

- **Answer type:** order_list
- **Order IDs:** ORD-701, ORD-704
- **Reasoning:** Orders in PATHOLOGIST_SIGNOUT state are ready for the pathologist to review and sign out the final report. ORD-701 and ORD-704 are in this state.

### QR-008 (Tier 1): Simple lookup — rush priority orders across all active states

**Query:** Are there any rush orders currently being processed?

**Database State:**

| Order ID | State | Specimen | Priority | Flags | Created |
|---|---|---|---|---|---|
| ORD-801 | ACCEPTED | biopsy | rush | — | 2025-01-15 07:00:00 |
| ORD-802 | SAMPLE_PREP_PROCESSING | excision | routine | — | 2025-01-14 08:00:00 |
| ORD-803 | HE_STAINING | resection | rush | — | 2025-01-15 06:00:00 |
| ORD-804 | PATHOLOGIST_HE_REVIEW | biopsy | routine | — | 2025-01-14 10:00:00 |
| ORD-805 | ORDER_COMPLETE | biopsy | rush | — | 2025-01-13 08:00:00 |
| ORD-806 | IHC_QC | excision | rush | — | 2025-01-14 14:00:00 |
| ORD-807 | RESULTING | biopsy | routine | — | 2025-01-13 14:00:00 |
| ORD-808 | DO_NOT_PROCESS | biopsy | rush | — | 2025-01-15 05:00:00 |

**Expected Output:**

- **Answer type:** order_list
- **Order IDs:** ORD-801, ORD-803, ORD-806
- **Reasoning:** Rush priority orders in active processing states are ORD-801 (ACCEPTED), ORD-803 (HE_STAINING), and ORD-806 (IHC_QC). ORD-805 is rush but already complete (ORDER_COMPLETE), and ORD-808 is rush but halted (DO_NOT_PROCESS) — neither is currently being processed.

### QR-009 (Tier 2): Order status — next step for an order in ACCEPTED state

**Query:** What's the next step for order ORD-901?

**Database State:**

| Order ID | State | Specimen | Priority | Flags | Created |
|---|---|---|---|---|---|
| ORD-901 | ACCEPTED | biopsy | routine | — | 2025-01-15 08:00:00 |
| ORD-902 | HE_STAINING | excision | rush | — | 2025-01-14 09:00:00 |
| ORD-903 | SAMPLE_PREP_PROCESSING | resection | routine | — | 2025-01-14 10:00:00 |
| ORD-904 | PATHOLOGIST_HE_REVIEW | biopsy | routine | — | 2025-01-13 14:00:00 |
| ORD-905 | ORDER_COMPLETE | biopsy | routine | — | 2025-01-12 08:00:00 |

**Expected Output:**

- **Answer type:** order_status
- **Order IDs:** ORD-901
- **Reasoning:** ORD-901 is in ACCEPTED state, meaning accessioning is complete. The next step is grossing, where the specimen will be examined and tissue sections selected for processing.

### QR-010 (Tier 2): Order status — order currently in tissue processing

**Query:** What's happening with order ORD-1002?

**Database State:**

| Order ID | State | Specimen | Priority | Flags | Created |
|---|---|---|---|---|---|
| ORD-1001 | ACCEPTED | biopsy | routine | — | 2025-01-15 08:00:00 |
| ORD-1002 | SAMPLE_PREP_PROCESSING | excision | rush | — | 2025-01-14 09:00:00 |
| ORD-1003 | HE_QC | biopsy | routine | — | 2025-01-13 14:00:00 |
| ORD-1004 | PATHOLOGIST_SIGNOUT | resection | routine | — | 2025-01-12 10:00:00 |
| ORD-1005 | RESULTING | biopsy | routine | — | 2025-01-13 08:00:00 |

**Expected Output:**

- **Answer type:** order_status
- **Order IDs:** ORD-1002
- **Reasoning:** ORD-1002 is in SAMPLE_PREP_PROCESSING state. Tissue processing is currently in progress — the specimen is being fixed, dehydrated, and embedded in paraffin. The next step after processing completes will be embedding.

### QR-011 (Tier 2): Order status — checking if a completed order is done

**Query:** Is order ORD-1101 done?

**Database State:**

| Order ID | State | Specimen | Priority | Flags | Created |
|---|---|---|---|---|---|
| ORD-1101 | ORDER_COMPLETE | biopsy | routine | — | 2025-01-12 08:00:00 |
| ORD-1102 | REPORT_GENERATION | excision | rush | — | 2025-01-13 09:00:00 |
| ORD-1103 | ACCEPTED | resection | routine | — | 2025-01-15 08:00:00 |
| ORD-1104 | HE_STAINING | biopsy | routine | — | 2025-01-14 10:00:00 |
| ORD-1105 | IHC_SCORING | excision | routine | — | 2025-01-14 07:00:00 |

**Expected Output:**

- **Answer type:** order_status
- **Order IDs:** ORD-1101
- **Reasoning:** Yes, ORD-1101 is in ORDER_COMPLETE state. The final report has been generated and the order is fully complete.

### QR-012 (Tier 2): Order status — identifying what is blocking a held order

**Query:** What's blocking order ORD-1201?

**Database State:**

| Order ID | State | Specimen | Priority | Flags | Created |
|---|---|---|---|---|---|
| ORD-1201 | MISSING_INFO_HOLD | biopsy | routine | — | 2025-01-14 08:00:00 |
| ORD-1202 | SAMPLE_PREP_EMBEDDING | excision | rush | — | 2025-01-14 09:00:00 |
| ORD-1203 | HE_QC | resection | routine | — | 2025-01-13 14:00:00 |
| ORD-1204 | ACCEPTED | biopsy | routine | — | 2025-01-15 07:00:00 |
| ORD-1205 | ORDER_COMPLETE | biopsy | routine | — | 2025-01-12 08:00:00 |
| ORD-1206 | PATHOLOGIST_HE_REVIEW | excision | routine | FIXATION_WARNING | 2025-01-13 10:00:00 |

**Expected Output:**

- **Answer type:** order_status
- **Order IDs:** ORD-1201
- **Reasoning:** ORD-1201 is in MISSING_INFO_HOLD state. The order is on hold because required information is missing from the requisition. Processing cannot continue until the missing information is received and the hold is resolved.

### QR-013 (Tier 2): Order status — locating an order in the IHC scoring step

**Query:** Where is order ORD-1302 in the workflow?

**Database State:**

| Order ID | State | Specimen | Priority | Flags | Created |
|---|---|---|---|---|---|
| ORD-1301 | ACCEPTED | biopsy | routine | — | 2025-01-15 08:00:00 |
| ORD-1302 | IHC_SCORING | excision | rush | — | 2025-01-13 09:00:00 |
| ORD-1303 | SAMPLE_PREP_SECTIONING | resection | routine | — | 2025-01-14 10:00:00 |
| ORD-1304 | IHC_QC | biopsy | routine | — | 2025-01-13 14:00:00 |
| ORD-1305 | PATHOLOGIST_SIGNOUT | excision | routine | — | 2025-01-12 14:00:00 |
| ORD-1306 | HE_STAINING | biopsy | routine | — | 2025-01-14 08:00:00 |
| ORD-1307 | RESULTING | resection | routine | — | 2025-01-13 08:00:00 |

**Expected Output:**

- **Answer type:** order_status
- **Order IDs:** ORD-1302
- **Reasoning:** ORD-1302 is in IHC_SCORING state. The IHC-stained slides have passed quality control and are currently being scored for biomarker expression levels (ER, PR, HER2, Ki-67). After scoring, results will proceed to the resulting step.

### QR-014 (Tier 2): Order status — checking if an order has been rejected

**Query:** Has order ORD-1401 been rejected?

**Database State:**

| Order ID | State | Specimen | Priority | Flags | Created |
|---|---|---|---|---|---|
| ORD-1401 | DO_NOT_PROCESS | biopsy | routine | — | 2025-01-14 07:00:00 |
| ORD-1402 | ACCEPTED | excision | rush | — | 2025-01-15 08:00:00 |
| ORD-1403 | HE_STAINING | resection | routine | — | 2025-01-14 09:00:00 |
| ORD-1404 | SAMPLE_PREP_PROCESSING | biopsy | routine | — | 2025-01-14 10:00:00 |
| ORD-1405 | ORDER_COMPLETE | excision | routine | — | 2025-01-12 08:00:00 |

**Expected Output:**

- **Answer type:** order_status
- **Order IDs:** ORD-1401
- **Reasoning:** Yes, ORD-1401 is in DO_NOT_PROCESS state and has been rejected. The DO_NOT_PROCESS state is a terminal state indicating the specimen was rejected during accessioning and will not proceed through the workflow.

### QR-015 (Tier 3): Flag reasoning — why an order is on hold at resulting

**Query:** Why is order ORD-1501 on hold at resulting?

**Database State:**

| Order ID | State | Specimen | Priority | Flags | Created |
|---|---|---|---|---|---|
| ORD-1501 | RESULTING_HOLD | biopsy | routine | MISSING_INFO_PROCEED | 2025-01-13 08:00:00 |
| ORD-1502 | PATHOLOGIST_HE_REVIEW | excision | routine | — | 2025-01-14 09:00:00 |
| ORD-1503 | IHC_SCORING | biopsy | rush | — | 2025-01-14 10:00:00 |
| ORD-1504 | ACCEPTED | resection | routine | — | 2025-01-15 07:00:00 |
| ORD-1505 | SAMPLE_PREP_PROCESSING | biopsy | routine | — | 2025-01-14 14:00:00 |
| ORD-1506 | ORDER_COMPLETE | excision | routine | — | 2025-01-12 08:00:00 |
| ORD-1507 | HE_STAINING | biopsy | routine | — | 2025-01-14 16:00:00 |
| ORD-1508 | RESULTING | biopsy | routine | — | 2025-01-13 10:00:00 |
| ORD-1509 | IHC_STAINING | excision | rush | — | 2025-01-15 06:00:00 |
| ORD-1510 | PATHOLOGIST_SIGNOUT | biopsy | routine | — | 2025-01-13 09:00:00 |

**Expected Output:**

- **Answer type:** order_status
- **Order IDs:** ORD-1501
- **Reasoning:** ORD-1501 is in RESULTING_HOLD state because it has the MISSING_INFO_PROCEED flag. This flag was set at accessioning (rule ACC-007) because billing information was missing. The order was allowed to proceed through the workflow but is now blocked at resulting per rule RES-001. The missing billing information must be received before the order can advance to pathologist signout.

### QR-016 (Tier 3): Flag reasoning — identifying flags affecting an order

**Query:** What flags are affecting order ORD-1603?

**Database State:**

| Order ID | State | Specimen | Priority | Flags | Created |
|---|---|---|---|---|---|
| ORD-1601 | ACCEPTED | biopsy | routine | — | 2025-01-15 08:00:00 |
| ORD-1602 | IHC_STAINING | excision | rush | — | 2025-01-14 10:00:00 |
| ORD-1603 | PATHOLOGIST_HE_REVIEW | biopsy | routine | FIXATION_WARNING | 2025-01-14 08:00:00 |
| ORD-1604 | SAMPLE_PREP_EMBEDDING | resection | routine | — | 2025-01-15 07:00:00 |
| ORD-1605 | ORDER_COMPLETE | biopsy | routine | — | 2025-01-12 09:00:00 |
| ORD-1606 | HE_QC | excision | routine | — | 2025-01-14 11:00:00 |
| ORD-1607 | RESULTING | biopsy | routine | — | 2025-01-13 10:00:00 |
| ORD-1608 | SAMPLE_PREP_PROCESSING | biopsy | routine | MISSING_INFO_PROCEED | 2025-01-15 06:00:00 |
| ORD-1609 | PATHOLOGIST_SIGNOUT | excision | rush | — | 2025-01-13 08:00:00 |
| ORD-1610 | IHC_QC | biopsy | routine | — | 2025-01-14 14:00:00 |

**Expected Output:**

- **Answer type:** order_status
- **Order IDs:** ORD-1603
- **Reasoning:** ORD-1603 has the FIXATION_WARNING flag. This flag indicates that the specimen's fixation time was borderline — close to the acceptable limits for histology processing. The pathologist reviewing the H&E slides should be aware of this warning as it may affect tissue quality and interpretation of results.

### QR-017 (Tier 3): Flag reasoning — whether an order can proceed to signout

**Query:** Can order ORD-1703 proceed to signout?

**Database State:**

| Order ID | State | Specimen | Priority | Flags | Created |
|---|---|---|---|---|---|
| ORD-1701 | PATHOLOGIST_SIGNOUT | excision | routine | — | 2025-01-13 09:00:00 |
| ORD-1702 | IHC_SCORING | biopsy | rush | — | 2025-01-14 10:00:00 |
| ORD-1703 | RESULTING_HOLD | biopsy | routine | MISSING_INFO_PROCEED | 2025-01-13 07:00:00 |
| ORD-1704 | ACCEPTED | resection | routine | — | 2025-01-15 08:00:00 |
| ORD-1705 | HE_STAINING | biopsy | routine | — | 2025-01-14 14:00:00 |
| ORD-1706 | SAMPLE_PREP_SECTIONING | excision | routine | RECUT_REQUESTED | 2025-01-14 11:00:00 |
| ORD-1707 | ORDER_COMPLETE | biopsy | routine | — | 2025-01-11 08:00:00 |
| ORD-1708 | RESULTING | excision | rush | — | 2025-01-13 12:00:00 |
| ORD-1709 | SAMPLE_PREP_PROCESSING | biopsy | routine | — | 2025-01-15 07:00:00 |
| ORD-1710 | IHC_STAINING | biopsy | routine | FIXATION_WARNING | 2025-01-14 09:00:00 |

**Expected Output:**

- **Answer type:** order_status
- **Order IDs:** ORD-1703
- **Reasoning:** No, ORD-1703 cannot proceed to signout. The order is currently in RESULTING_HOLD state because it has an active MISSING_INFO_PROCEED flag. This flag was set at accessioning (ACC-007) due to missing billing information. Per rule RES-001, the order is blocked at resulting until the missing information is received and the flag is cleared.

### QR-018 (Tier 3): Flag reasoning — what must happen before an order can be released

**Query:** What needs to happen before order ORD-1804 can be released?

**Database State:**

| Order ID | State | Specimen | Priority | Flags | Created |
|---|---|---|---|---|---|
| ORD-1801 | IHC_QC | biopsy | routine | — | 2025-01-14 10:00:00 |
| ORD-1802 | PATHOLOGIST_HE_REVIEW | excision | rush | — | 2025-01-14 08:00:00 |
| ORD-1803 | ACCEPTED | biopsy | routine | — | 2025-01-15 09:00:00 |
| ORD-1804 | RESULTING_HOLD | resection | routine | MISSING_INFO_PROCEED | 2025-01-12 08:00:00 |
| ORD-1805 | SAMPLE_PREP_QC | biopsy | routine | — | 2025-01-14 16:00:00 |
| ORD-1806 | ORDER_COMPLETE | excision | routine | — | 2025-01-11 08:00:00 |
| ORD-1807 | HE_QC | biopsy | routine | — | 2025-01-14 12:00:00 |
| ORD-1808 | PATHOLOGIST_SIGNOUT | biopsy | rush | — | 2025-01-13 09:00:00 |
| ORD-1809 | SAMPLE_PREP_PROCESSING | excision | routine | — | 2025-01-15 07:00:00 |
| ORD-1810 | RESULTING | biopsy | routine | — | 2025-01-13 14:00:00 |

**Expected Output:**

- **Answer type:** order_status
- **Order IDs:** ORD-1804
- **Reasoning:** ORD-1804 is in RESULTING_HOLD due to the MISSING_INFO_PROCEED flag. The missing billing information that was noted at accessioning (ACC-007) must be received. Once the information is provided, the flag can be cleared per rule RES-002, allowing the order to advance from RESULTING_HOLD to RESULTING and then proceed to pathologist signout.

### QR-019 (Tier 3): Flag reasoning — why HER2 testing was rejected for an order

**Query:** Why was HER2 testing rejected for order ORD-1905?

**Database State:**

| Order ID | State | Specimen | Priority | Flags | Created |
|---|---|---|---|---|---|
| ORD-1901 | ACCEPTED | biopsy | routine | — | 2025-01-15 08:00:00 |
| ORD-1902 | HE_STAINING | excision | routine | — | 2025-01-14 14:00:00 |
| ORD-1903 | IHC_STAINING | biopsy | rush | — | 2025-01-14 10:00:00 |
| ORD-1904 | ORDER_COMPLETE | biopsy | routine | — | 2025-01-11 08:00:00 |
| ORD-1905 | IHC_SCORING | excision | routine | HER2_FIXATION_REJECT | 2025-01-13 08:00:00 |
| ORD-1906 | SAMPLE_PREP_PROCESSING | resection | routine | — | 2025-01-15 07:00:00 |
| ORD-1907 | PATHOLOGIST_HE_REVIEW | biopsy | routine | FIXATION_WARNING | 2025-01-14 09:00:00 |
| ORD-1908 | RESULTING | biopsy | routine | — | 2025-01-13 10:00:00 |
| ORD-1909 | PATHOLOGIST_SIGNOUT | excision | rush | — | 2025-01-13 12:00:00 |
| ORD-1910 | SAMPLE_PREP_SECTIONING | biopsy | routine | — | 2025-01-14 16:00:00 |

**Expected Output:**

- **Answer type:** order_status
- **Order IDs:** ORD-1905
- **Reasoning:** ORD-1905 has the HER2_FIXATION_REJECT flag. This flag was set because the pathologist added HER2 testing at IHC review but the specimen's fixation was out of tolerance (rule IHC-001). When HER2 is added by the pathologist rather than ordered upfront, IHC-001 checks fixation parameters at the IHC stage. The specimen failed these requirements, so HER2 testing was rejected and the pathologist has been flagged.

### QR-020 (Tier 4): Prioritization — ranking grossing orders by priority and age

**Query:** Which grossing orders should I do first?

**Database State:**

| Order ID | State | Specimen | Priority | Flags | Created |
|---|---|---|---|---|---|
| ORD-2001 | ACCEPTED | biopsy | routine | — | 2025-01-15 09:00:00 |
| ORD-2002 | ACCEPTED | excision | rush | — | 2025-01-15 10:00:00 |
| ORD-2003 | ACCEPTED | resection | routine | — | 2025-01-14 08:00:00 |
| ORD-2004 | ACCEPTED | biopsy | rush | — | 2025-01-15 07:00:00 |
| ORD-2005 | ACCEPTED | biopsy | routine | — | 2025-01-15 06:00:00 |
| ORD-2006 | SAMPLE_PREP_PROCESSING | excision | routine | — | 2025-01-14 10:00:00 |
| ORD-2007 | HE_STAINING | biopsy | rush | — | 2025-01-14 14:00:00 |
| ORD-2008 | ORDER_COMPLETE | biopsy | routine | — | 2025-01-12 08:00:00 |
| ORD-2009 | PATHOLOGIST_HE_REVIEW | excision | routine | — | 2025-01-13 09:00:00 |
| ORD-2010 | IHC_SCORING | biopsy | routine | — | 2025-01-13 14:00:00 |

**Expected Output:**

- **Answer type:** prioritized_list
- **Order IDs:** ORD-2004, ORD-2002, ORD-2003, ORD-2005, ORD-2001
- **Reasoning:** Orders in ACCEPTED state are ready for grossing. Rush priority orders come first: ORD-2004 (rush, received 07:00) before ORD-2002 (rush, received 10:00) because it has been waiting longer. Then routine orders by age: ORD-2003 (routine, received Jan 14 08:00 — oldest), ORD-2005 (routine, received 06:00), and ORD-2001 (routine, received 09:00).

### QR-021 (Tier 4): Prioritization — rank all orders on the IHC bench by urgency

**Query:** Rank all orders currently on the IHC bench by urgency.

**Database State:**

| Order ID | State | Specimen | Priority | Flags | Created |
|---|---|---|---|---|---|
| ORD-2101 | IHC_STAINING | biopsy | routine | — | 2025-01-14 08:00:00 |
| ORD-2102 | IHC_QC | excision | rush | — | 2025-01-14 14:00:00 |
| ORD-2103 | IHC_STAINING | biopsy | rush | — | 2025-01-15 07:00:00 |
| ORD-2104 | IHC_SCORING | resection | routine | — | 2025-01-13 10:00:00 |
| ORD-2105 | IHC_QC | biopsy | routine | — | 2025-01-13 14:00:00 |
| ORD-2106 | ACCEPTED | biopsy | rush | — | 2025-01-15 09:00:00 |
| ORD-2107 | PATHOLOGIST_HE_REVIEW | excision | routine | — | 2025-01-14 09:00:00 |
| ORD-2108 | ORDER_COMPLETE | biopsy | routine | — | 2025-01-12 08:00:00 |
| ORD-2109 | HE_STAINING | biopsy | routine | — | 2025-01-14 16:00:00 |
| ORD-2110 | IHC_SCORING | biopsy | rush | FIXATION_WARNING | 2025-01-14 06:00:00 |

**Expected Output:**

- **Answer type:** prioritized_list
- **Order IDs:** ORD-2110, ORD-2102, ORD-2103, ORD-2104, ORD-2105, ORD-2101
- **Reasoning:** Orders on the IHC bench (IHC_STAINING, IHC_QC, IHC_SCORING states) ranked by urgency. Rush orders first, then by time waiting: ORD-2110 (rush, IHC_SCORING, since Jan 14 06:00 — also has FIXATION_WARNING requiring attention), ORD-2102 (rush, IHC_QC, since Jan 14 14:00), ORD-2103 (rush, IHC_STAINING, since Jan 15 07:00). Then routine by age: ORD-2104 (routine, IHC_SCORING, since Jan 13 10:00), ORD-2105 (routine, IHC_QC, since Jan 13 14:00), ORD-2101 (routine, IHC_STAINING, since Jan 14 08:00).

### QR-022 (Tier 4): Prioritization — selecting top 3 signout cases by priority and age

**Query:** I have time for 3 more signouts — which ones?

**Database State:**

| Order ID | State | Specimen | Priority | Flags | Created |
|---|---|---|---|---|---|
| ORD-2201 | PATHOLOGIST_SIGNOUT | biopsy | routine | — | 2025-01-13 08:00:00 |
| ORD-2202 | PATHOLOGIST_SIGNOUT | excision | rush | — | 2025-01-14 10:00:00 |
| ORD-2203 | PATHOLOGIST_SIGNOUT | resection | routine | — | 2025-01-12 09:00:00 |
| ORD-2204 | PATHOLOGIST_SIGNOUT | biopsy | rush | — | 2025-01-14 14:00:00 |
| ORD-2205 | PATHOLOGIST_SIGNOUT | biopsy | routine | — | 2025-01-14 08:00:00 |
| ORD-2206 | RESULTING | excision | rush | — | 2025-01-14 09:00:00 |
| ORD-2207 | IHC_SCORING | biopsy | routine | — | 2025-01-14 11:00:00 |
| ORD-2208 | ORDER_COMPLETE | biopsy | routine | — | 2025-01-11 08:00:00 |
| ORD-2209 | ACCEPTED | excision | routine | — | 2025-01-15 08:00:00 |
| ORD-2210 | HE_QC | biopsy | routine | — | 2025-01-14 16:00:00 |

**Expected Output:**

- **Answer type:** prioritized_list
- **Order IDs:** ORD-2202, ORD-2204, ORD-2203
- **Reasoning:** Five orders are in PATHOLOGIST_SIGNOUT state. Picking the top 3 by priority then age: ORD-2202 (rush, received Jan 14 10:00) and ORD-2204 (rush, received Jan 14 14:00) are the rush cases and should go first. Among the remaining routine cases, ORD-2203 (routine, received Jan 12 09:00) has been waiting the longest. The remaining two routine cases — ORD-2201 (Jan 13) and ORD-2205 (Jan 14) — can wait.

### QR-023 (Tier 5): Cross-order reasoning — identifying orders at risk of fixation timing out

**Query:** Are any orders at risk of timing out on fixation?

**Database State:**

| Order ID | State | Specimen | Priority | Flags | Created |
|---|---|---|---|---|---|
| ORD-2301 | ACCESSIONING | biopsy | routine | — | 2025-01-15 06:00:00 |
| ORD-2302 | ACCESSIONING | excision | rush | — | 2025-01-15 08:00:00 |
| ORD-2303 | ACCEPTED | biopsy | routine | — | 2025-01-14 10:00:00 |
| ORD-2304 | ACCESSIONING | resection | routine | — | 2025-01-15 09:00:00 |
| ORD-2305 | ACCEPTED | biopsy | rush | — | 2025-01-15 07:00:00 |
| ORD-2306 | SAMPLE_PREP_PROCESSING | excision | routine | — | 2025-01-14 14:00:00 |
| ORD-2307 | HE_STAINING | biopsy | routine | — | 2025-01-14 09:00:00 |
| ORD-2308 | ORDER_COMPLETE | biopsy | routine | — | 2025-01-12 08:00:00 |
| ORD-2309 | PATHOLOGIST_HE_REVIEW | excision | routine | — | 2025-01-13 10:00:00 |
| ORD-2310 | ACCESSIONING | biopsy | routine | — | 2025-01-15 05:00:00 |

**Expected Output:**

- **Answer type:** order_list
- **Order IDs:** ORD-2303, ORD-2301, ORD-2310
- **Reasoning:** Rule ACC-006 requires fixation time within 6-72 hours when HER2 is ordered (Breast IHC Panel includes HER2). ORD-2303 has Breast IHC Panel ordered with 70.5 hours fixation (ACCEPTED, still awaiting grossing). ORD-2301 has Breast IHC Panel ordered with 68.0 hours fixation (ACCESSIONING). ORD-2310 has Breast IHC Panel ordered with 65.0 hours fixation (ACCESSIONING). All three are approaching the 72-hour limit and require attention. Other orders with Breast IHC Panel (ORD-2304 at 12.0h, ORD-2305 at 18.0h) are well within the safe range. Orders with only H&E (ORD-2302, ORD-2306, ORD-2309) are not subject to ACC-006.

### QR-024 (Tier 5): Cross-order reasoning — identifying orders needing pathologist attention

**Query:** Do any orders need pathologist attention right now?

**Database State:**

| Order ID | State | Specimen | Priority | Flags | Created |
|---|---|---|---|---|---|
| ORD-2401 | PATHOLOGIST_HE_REVIEW | biopsy | rush | — | 2025-01-14 10:00:00 |
| ORD-2402 | ACCEPTED | excision | routine | — | 2025-01-15 08:00:00 |
| ORD-2403 | SUGGEST_FISH_REFLEX | biopsy | routine | FISH_SUGGESTED | 2025-01-13 09:00:00 |
| ORD-2404 | SAMPLE_PREP_PROCESSING | resection | routine | — | 2025-01-14 16:00:00 |
| ORD-2405 | PATHOLOGIST_SIGNOUT | excision | routine | — | 2025-01-13 08:00:00 |
| ORD-2406 | IHC_STAINING | biopsy | routine | — | 2025-01-14 14:00:00 |
| ORD-2407 | PATHOLOGIST_HE_REVIEW | excision | routine | FIXATION_WARNING | 2025-01-14 08:00:00 |
| ORD-2408 | ORDER_COMPLETE | biopsy | routine | — | 2025-01-11 08:00:00 |
| ORD-2409 | RESULTING | biopsy | routine | — | 2025-01-13 14:00:00 |
| ORD-2410 | HE_QC | biopsy | rush | — | 2025-01-14 12:00:00 |
| ORD-2411 | PATHOLOGIST_SIGNOUT | biopsy | rush | — | 2025-01-14 06:00:00 |
| ORD-2412 | FISH_SEND_OUT | excision | routine | FISH_SUGGESTED | 2025-01-12 10:00:00 |

**Expected Output:**

- **Answer type:** order_list
- **Order IDs:** ORD-2401, ORD-2407, ORD-2403, ORD-2405, ORD-2411
- **Reasoning:** Five orders require pathologist attention. ORD-2401 and ORD-2407 are in PATHOLOGIST_HE_REVIEW awaiting H&E slide review (ORD-2407 also has a FIXATION_WARNING the pathologist should note). ORD-2403 is in SUGGEST_FISH_REFLEX with a FISH_SUGGESTED flag — the pathologist must decide whether to approve FISH reflex testing for the equivocal HER2 result. ORD-2405 and ORD-2411 are in PATHOLOGIST_SIGNOUT awaiting final case signout.

### QR-025 (Tier 5): Cross-order reasoning — identifying orders with flags or issues needing resolution

**Query:** Which orders have flags or issues that need resolution?

**Database State:**

| Order ID | State | Specimen | Priority | Flags | Created |
|---|---|---|---|---|---|
| ORD-2501 | RESULTING_HOLD | biopsy | routine | MISSING_INFO_PROCEED | 2025-01-13 08:00:00 |
| ORD-2502 | PATHOLOGIST_HE_REVIEW | excision | routine | FIXATION_WARNING | 2025-01-14 09:00:00 |
| ORD-2503 | ACCEPTED | biopsy | rush | — | 2025-01-15 08:00:00 |
| ORD-2504 | IHC_SCORING | resection | routine | HER2_FIXATION_REJECT | 2025-01-13 10:00:00 |
| ORD-2505 | SAMPLE_PREP_PROCESSING | biopsy | routine | — | 2025-01-14 16:00:00 |
| ORD-2506 | SUGGEST_FISH_REFLEX | biopsy | routine | FISH_SUGGESTED | 2025-01-13 14:00:00 |
| ORD-2507 | SAMPLE_PREP_SECTIONING | excision | routine | RECUT_REQUESTED | 2025-01-14 10:00:00 |
| ORD-2508 | HE_STAINING | biopsy | routine | — | 2025-01-14 12:00:00 |
| ORD-2509 | ORDER_COMPLETE | biopsy | routine | — | 2025-01-11 08:00:00 |
| ORD-2510 | IHC_STAINING | excision | rush | MISSING_INFO_PROCEED | 2025-01-14 14:00:00 |
| ORD-2511 | PATHOLOGIST_SIGNOUT | biopsy | routine | — | 2025-01-13 09:00:00 |

**Expected Output:**

- **Answer type:** order_list
- **Order IDs:** ORD-2501, ORD-2502, ORD-2504, ORD-2506, ORD-2507, ORD-2510
- **Reasoning:** Six orders have active flags requiring attention. ORD-2501 has MISSING_INFO_PROCEED and is blocked in RESULTING_HOLD — billing info must be received. ORD-2502 has FIXATION_WARNING — the pathologist should note borderline fixation during H&E review. ORD-2504 has HER2_FIXATION_REJECT — HER2 testing was rejected due to fixation out of tolerance. ORD-2506 has FISH_SUGGESTED — awaiting pathologist decision on FISH reflex testing. ORD-2507 has RECUT_REQUESTED — recuts were requested by the pathologist and sectioning is in progress. ORD-2510 has MISSING_INFO_PROCEED — billing info is missing and will block at resulting.

### QR-026 (Tier 5): Cross-order reasoning — identifying orders that appear stuck

**Query:** Are there any orders that seem stuck or haven't progressed?

**Database State:**

| Order ID | State | Specimen | Priority | Flags | Created |
|---|---|---|---|---|---|
| ORD-2601 | MISSING_INFO_HOLD | biopsy | routine | — | 2025-01-10 08:00:00 |
| ORD-2602 | ACCEPTED | excision | routine | — | 2025-01-15 08:00:00 |
| ORD-2603 | RESULTING_HOLD | biopsy | routine | MISSING_INFO_PROCEED | 2025-01-09 09:00:00 |
| ORD-2604 | SAMPLE_PREP_PROCESSING | resection | rush | — | 2025-01-15 07:00:00 |
| ORD-2605 | FISH_SEND_OUT | biopsy | routine | FISH_SUGGESTED | 2025-01-08 10:00:00 |
| ORD-2606 | HE_STAINING | excision | routine | — | 2025-01-14 14:00:00 |
| ORD-2607 | IHC_SCORING | biopsy | routine | — | 2025-01-14 10:00:00 |
| ORD-2608 | ORDER_COMPLETE | biopsy | routine | — | 2025-01-12 08:00:00 |
| ORD-2609 | PATHOLOGIST_HE_REVIEW | excision | routine | — | 2025-01-14 09:00:00 |
| ORD-2610 | PATHOLOGIST_SIGNOUT | biopsy | rush | — | 2025-01-14 06:00:00 |
| ORD-2611 | SUGGEST_FISH_REFLEX | excision | routine | FISH_SUGGESTED | 2025-01-10 14:00:00 |

**Expected Output:**

- **Answer type:** order_list
- **Order IDs:** ORD-2605, ORD-2603, ORD-2601
- **Reasoning:** Three orders appear stuck based on their age and hold/wait state. ORD-2605 (created Jan 8) has been in FISH_SEND_OUT for over a week — the external FISH result has not been received. ORD-2603 (created Jan 9) has been in RESULTING_HOLD for 6 days due to MISSING_INFO_PROCEED — billing info still hasn't arrived. ORD-2601 (created Jan 10) has been in MISSING_INFO_HOLD for 5 days — missing patient information has not been provided. ORD-2611 (SUGGEST_FISH_REFLEX, 5 days) is excluded because it is awaiting a pathologist decision, which is an active workflow step rather than a stalled hold.

### QR-027 (Tier 5): Cross-order reasoning — orders waiting on external results

**Query:** How many orders are waiting on external results?

**Database State:**

| Order ID | State | Specimen | Priority | Flags | Created |
|---|---|---|---|---|---|
| ORD-2701 | FISH_SEND_OUT | biopsy | routine | FISH_SUGGESTED | 2025-01-12 08:00:00 |
| ORD-2702 | ACCEPTED | excision | rush | — | 2025-01-15 08:00:00 |
| ORD-2703 | FISH_SEND_OUT | excision | rush | FISH_SUGGESTED | 2025-01-13 10:00:00 |
| ORD-2704 | SAMPLE_PREP_PROCESSING | resection | routine | — | 2025-01-14 16:00:00 |
| ORD-2705 | IHC_SCORING | biopsy | routine | — | 2025-01-14 10:00:00 |
| ORD-2706 | PATHOLOGIST_HE_REVIEW | excision | routine | — | 2025-01-14 09:00:00 |
| ORD-2707 | RESULTING_HOLD | biopsy | routine | MISSING_INFO_PROCEED | 2025-01-13 08:00:00 |
| ORD-2708 | ORDER_COMPLETE | biopsy | routine | — | 2025-01-11 08:00:00 |
| ORD-2709 | HE_QC | biopsy | routine | — | 2025-01-14 14:00:00 |
| ORD-2710 | PATHOLOGIST_SIGNOUT | excision | routine | — | 2025-01-13 12:00:00 |
| ORD-2711 | MISSING_INFO_HOLD | biopsy | routine | — | 2025-01-14 07:00:00 |

**Expected Output:**

- **Answer type:** order_list
- **Order IDs:** ORD-2701, ORD-2703
- **Reasoning:** Two orders are waiting on external results. Both are in FISH_SEND_OUT state, meaning specimens have been sent to an external laboratory for FISH testing after equivocal HER2 IHC results. ORD-2701 (routine, sent out Jan 12) and ORD-2703 (rush, sent out Jan 13) are both awaiting FISH results from the external lab before they can proceed to resulting.
