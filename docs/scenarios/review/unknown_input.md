# Unknown Input Scenarios

**6 scenarios**

## Summary

| ID | Description | Rules | Final State | Steps |
|---|---|---|---|---|
| SC-100 | FNA specimen type → DO_NOT_PROCESS (ACC-004); FNA is incompatible with histology workflow | ACC-004 | DO_NOT_PROCESS | 1 |
| SC-101 | Unrecognized specimen type 'swab' → DO_NOT_PROCESS (ACC-004); unknown type not in histology workflow vocabulary | ACC-004 | DO_NOT_PROCESS | 1 |
| SC-102 | Ambiguous anatomic site 'skin overlying breast' → DO_NOT_PROCESS (ACC-003); not clearly breast-cancer-relevant tissue (acceptable alternative: ACCEPTED if model interprets as breast) | ACC-003 | DO_NOT_PROCESS | 1 |
| SC-103 | Missing fixation time for HER2 order → MISSING_INFO_HOLD; null fixation time is missing data (not an out-of-range value), so the order is held until fixation time is provided | ACC-009 | MISSING_INFO_HOLD | 1 |
| SC-104 | Completely empty order data (all fields missing/null) → DO_NOT_PROCESS; model must identify all defects: missing name, sex, invalid site, unknown specimen, no billing | ACC-001, ACC-002, ACC-003, ACC-004, ACC-007 | DO_NOT_PROCESS | 1 |
| SC-105 | Missing fixation time for HER2 order with missing billing → MISSING_INFO_HOLD; ACC-009 (null fixation time) outranks ACC-007 (missing billing) because HOLD > PROCEED | ACC-007, ACC-009 | MISSING_INFO_HOLD | 1 |

## Details

### SC-100: FNA specimen type → DO_NOT_PROCESS (ACC-004); FNA is incompatible with histology workflow

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | FNA, breast, formalin, 24.0h | DO_NOT_PROCESS | ACC-004 | — |

### SC-101: Unrecognized specimen type 'swab' → DO_NOT_PROCESS (ACC-004); unknown type not in histology workflow vocabulary

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | swab, breast, formalin, 24.0h | DO_NOT_PROCESS | ACC-004 | — |

### SC-102: Ambiguous anatomic site 'skin overlying breast' → DO_NOT_PROCESS (ACC-003); not clearly breast-cancer-relevant tissue (acceptable alternative: ACCEPTED if model interprets as breast)

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, skin overlying breast, formalin, 24.0h | DO_NOT_PROCESS | ACC-003 | — |

### SC-103: Missing fixation time for HER2 order → MISSING_INFO_HOLD; null fixation time is missing data (not an out-of-range value), so the order is held until fixation time is provided

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, fix_time=null | MISSING_INFO_HOLD | ACC-009 | — |

### SC-104: Completely empty order data (all fields missing/null) → DO_NOT_PROCESS; model must identify all defects: missing name, sex, invalid site, unknown specimen, no billing

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | null, fix_time=null, priority=None, no billing, name=null, sex=null | DO_NOT_PROCESS | ACC-001, ACC-002, ACC-003, ACC-004, ACC-007 | — |

### SC-105: Missing fixation time for HER2 order with missing billing → MISSING_INFO_HOLD; ACC-009 (null fixation time) outranks ACC-007 (missing billing) because HOLD > PROCEED

| Step | Event | Key Data | State | Rules | Flags |
|---|---|---|---|---|---|
| 1 | order_received | biopsy, breast, formalin, fix_time=null, no billing | MISSING_INFO_HOLD | ACC-007, ACC-009 | — |
