# Breast IHC Panel Definitions

This document defines the immunohistochemistry (IHC) panel mappings for breast
cancer specimens. It serves as the authoritative reference for diagnosis-to-marker
assignments, panel modification mechanics, and slide count calculations.

## "Breast IHC Panel" Expansion

When an order specifies "Breast IHC Panel", the test harness expands it to four
individual markers:

- ER (estrogen receptor)
- PR (progesterone receptor)
- HER2
- Ki-67

The model always sees individual test names in the `ordered_tests` field. Panel
expansion happens at order creation.

## Diagnosis-to-Panel Mappings

The pathologist determines the actual IHC panel at H&E review. The panel may
differ from the originally ordered tests. The routing system routes based on the
pathologist's panel decision, not the original order.

These rules use **priority-based, first-match evaluation** — the first matching
rule wins. Only one HE rule fires per pathologist review event.

| Diagnosis | Standard Panel | Rule ID | Priority | Notes |
|-----------|---------------|---------|----------|-------|
| Invasive carcinoma | ER, PR, HER2, Ki-67 | HE-005 | 1 | Pathologist may add or remove markers |
| DCIS | ER, PR (HER2 only if specifically ordered) | HE-006 | 2 | Pathologist may add HER2 at review |
| Suspicious/atypical | Pathologist specifies markers | HE-007 | 3 | System routes but does not select markers |
| Benign | No IHC performed | HE-008 | 4 | Cancel IHC and proceed directly to RESULTING |

### Rule Details

- **HE-005** (Priority 1): Pathologist diagnosis is invasive carcinoma. Action:
  PROCEED_IHC with standard panel (ER, PR, HER2, Ki-67).
- **HE-006** (Priority 2): Pathologist diagnosis is DCIS. Action: PROCEED_IHC
  with standard panel (ER, PR; HER2 only if it was in the original order).
- **HE-007** (Priority 3): Pathologist diagnosis is suspicious or atypical.
  Action: PROCEED_IHC with a pathologist-customized panel. The system routes the
  order but does not select which markers to run.
- **HE-008** (Priority 4): Pathologist diagnosis is benign. Action:
  CANCEL_IHC_BENIGN and route to RESULTING. No IHC is performed.
- **HE-009** (Priority 5): Pathologist requests recuts. Action: REQUEST_RECUTS
  and route back to SAMPLE_PREP_SECTIONING.

## Panel Modification Mechanics

The pathologist has discretion to add or remove markers from the standard panel
at H&E review. When the pathologist modifies the panel:

1. The `pathologist_he_review` event carries the updated test list.
2. The test harness (acting as LIS) updates the order's `ordered_tests` field to
   reflect the pathologist's panel decision.
3. New slide rows are created for any added markers.
4. Slides for removed markers are set to `cancelled` status. Rows are never
   deleted — this preserves the audit trail.
5. The model sees the updated order state in its next snapshot.

The routing system tracks completeness against the pathologist-determined panel,
not the original order.

## Slide Count Formula

Initial slide count at sectioning:

```text
slides = number of ordered tests + 1 (H&E) + 2 (backup)
```

**Example — Breast IHC Panel:**

| Component | Count |
|-----------|-------|
| ER | 1 |
| PR | 1 |
| HER2 | 1 |
| Ki-67 | 1 |
| H&E | 1 |
| Backup | 2 |
| **Total** | **7** |

If the pathologist adds a marker at H&E review, an additional slide is cut from
backup stock or via new sectioning.

## Related Rules

- HE-005: Invasive carcinoma panel assignment
- HE-006: DCIS panel assignment
- HE-007: Suspicious/atypical panel assignment
- HE-008: Benign — cancel IHC
- HE-009: Pathologist requests recuts
