# Pathologist H&E Review — IHC Panel Mappings

The pathologist determines the actual IHC panel at H&E review. The panel may be a superset or subset of the originally ordered tests — the pathologist has discretion to add or remove markers based on the H&E findings. The routing system's job is to route correctly based on the pathologist's panel decision and track completeness against the pathologist-determined panel (not the original order).

## Panel Change Mechanics

When the pathologist modifies the panel at H&E review, the LIS performs a coordinated update before the order advances. The sequence is:

1. **Pathologist modifies panel** — the `pathologist_he_review` event carries the updated test list (e.g., removing Ki-67, adding HER2).
2. **LIS updates ordered tests** — the order's `ordered_tests` field is replaced with the pathologist-determined panel.
3. **LIS cancels removed slides** — slides for markers no longer in the panel have their status set to `cancelled`. Rows are never deleted; the audit trail is preserved.
4. **LIS creates new slides** — slides are created for any newly added markers (status: `pending`).
5. **System routes to `IHC_STAINING`** — the order advances with the updated panel. The model sees the new order state (updated tests, cancelled/new slides) in its next snapshot.

### Slide Lifecycle During Panel Change

```text
Original panel: [ER, PR, Ki-67]
Pathologist panel: [ER, PR, HER2]

Slide actions:
  ER   → no change (already exists)
  PR   → no change (already exists)
  Ki-67 → status set to "cancelled"
  HER2  → new slide row created (status: "pending")
```

Key invariants:

- Cancelled slides remain in the database — they are never deleted.
- The model evaluates completeness against the pathologist-determined panel, not the original order.
- If HER2 is added and fixation is out of tolerance, the fixation check at `IHC_STAINING` applies (see [Workflow Overview — Fixation Check](workflow-overview.md#fixation-check)).

## Diagnosis-to-Panel Mappings

| Diagnosis | Typical IHC Panel | Notes |
|-----------|-------------------|-------|
| Invasive carcinoma | ER, PR, HER2, Ki-67 | Pathologist may add/remove markers |
| DCIS | ER, PR (HER2 only if specifically ordered) | Pathologist may add HER2 |
| Suspicious/atypical | Pathologist specifies markers | System routes, does not select |
| Benign | Cancel IHC -> proceed to resulting | No IHC performed |

## Related Documents

- [Rule Catalog](rule-catalog.md) — H&E / Pathologist Review rules (HE-005 through HE-009)
- [Workflow Overview](workflow-overview.md) — H&E and IHC state diagrams
