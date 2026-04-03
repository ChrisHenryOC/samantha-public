# Resulting Standard Operating Procedure

**Document ID:** SOP-RES
**Version:** 1.0
**Effective Date:** 2026-02-01
**Workflow Step:** RESULTING, RESULTING_HOLD, PATHOLOGIST_SIGNOUT, REPORT_GENERATION, ORDER_COMPLETE
**Applicable Rules:** RES-001 through RES-005

---

## 1. Purpose

This procedure defines the flag check, pathologist signout, and report generation process for completing a breast cancer laboratory order. Resulting is the final workflow phase where test results are assembled into a reportable format, the pathologist selects which tests to include in the final report, and the report is generated.

## 2. Scope

This procedure applies to all orders routed to RESULTING from one of the following pathways:

- **From IHC scoring** (IHC-006): All IHC scoring complete, no equivocal results
- **From FISH** (IHC-009 or IHC-010): Pathologist declined FISH or FISH result received
- **From pathologist H&E review** (HE-008): Benign diagnosis, IHC cancelled

Regardless of the entry pathway, the resulting step begins with a flag check before any further processing.

## 3. Entry Pathways to Resulting

Orders may arrive at the resulting phase from three distinct workflow pathways. Each pathway produces a different set of test results:

- **IHC complete**: Order carries full IHC scoring results (ER, PR, HER2, Ki-67 as applicable)
- **FISH complete**: Order carries IHC scoring plus FISH amplification result, or IHC scoring with equivocal HER2 (if FISH declined)
- **Benign (no IHC)**: Order carries only H&E results; no IHC testing was performed

The resulting phase handles all pathways identically — the flag check and signout process are the same regardless of the entry pathway.

## 4. Resulting Workflow Overview

The resulting phase follows this sequence:

1. **Flag check** — Evaluate accumulated flags for blocking conditions
2. **RESULTING_HOLD** (conditional) — If blocking flags are present, hold until resolved
3. **PATHOLOGIST_SIGNOUT** — Pathologist selects reportable tests
4. **REPORT_GENERATION** — Final report is generated
5. **ORDER_COMPLETE** — Terminal state

The flag check is a decision point, not a persisted workflow state. If the order has no blocking flags, it passes through the check and immediately proceeds to pathologist signout.

## 5. Flag Check Procedure

Upon entry to the resulting phase, the system shall evaluate the order's accumulated flags to determine whether the order can proceed to pathologist signout or must be held.

The `MISSING_INFO_PROCEED` flag is the only flag that blocks at resulting. Other flags (e.g., `RECUT_REQUESTED`, `HER2_FIXATION_REJECT`, `FISH_SUGGESTED`) are informational at this stage and do not block the resulting workflow.

## 6. Pathologist Signout Process

At pathologist signout, the pathologist shall review the completed test results and select which tests to include in the final report. The reported tests may be a **subset** of the tests performed — the pathologist exercises clinical judgment to determine which results are clinically relevant for the report.

The system shall record the pathologist's reportable test selection:

- Slides included in the report have their `reported` flag set to true
- Slides excluded from the report have their `reported` flag set to false
- All slides (reported and unreported) remain in the data for audit purposes — no slide data is deleted

The set of reported tests is captured for downstream billing and clinical systems. The system does not question the pathologist's selection — it records the determination and proceeds to report generation.

## 7. Terminal States

Orders reaching the resulting phase may terminate in one of the following states:

| Terminal State | Meaning | Entry Pathway |
| --- | --- | --- |
| ORDER_COMPLETE | Normal completion — report generated and signed out | Resulting -> Pathologist Signout -> Report Generation |
| ORDER_TERMINATED_QNS | Quantity not sufficient — insufficient tissue | May occur at sample prep, H&E, IHC, or FISH stages before reaching resulting |
| ORDER_TERMINATED | Rejected at accessioning | DO_NOT_PROCESS outcome at accessioning |

Only ORDER_COMPLETE is reached through the resulting phase. The other terminal states occur at earlier workflow steps and bypass resulting entirely.

## 8. Routing Rules

### 8.1. MISSING_INFO_PROCEED Flag Present (RES-001)

Per RES-001, if the order carries a `MISSING_INFO_PROCEED` flag, the system shall place the order in RESULTING_HOLD. The order shall not advance to pathologist signout until the missing information is provided and the flag is cleared.

- Trigger: `MISSING_INFO_PROCEED` flag is present on the order
- Action: Route to RESULTING_HOLD — block until information is received
- Priority: 1
- The `MISSING_INFO_PROCEED` flag was set at accessioning (ACC-007) when billing information was missing. The order proceeded through sample preparation, H&E, and IHC with this flag, but the flag blocks the order at resulting.

### 8.2. Flag Re-evaluation (RES-002)

Per RES-002, when the missing information is received for an order in RESULTING_HOLD, the system shall re-evaluate the flag status.

- Trigger: Information received for a held order
- Action: If the `MISSING_INFO_PROCEED` flag is cleared (missing information has been provided), proceed to RESULTING. If the flag remains (information is still missing or incomplete), remain in RESULTING_HOLD.
- Priority: 2
- The system checks the current flag state — it does not assume that any information submission clears the flag. The flag is cleared only when the specific missing information has been satisfactorily provided.

### 8.3. No Blocking Flags — Proceed to Signout (RES-003)

Per RES-003, when all scoring and testing are complete and no blocking flags are present on the order, the system shall route to pathologist signout.

- Trigger: All scoring/testing complete, no blocking flags
- Action: Route to PATHOLOGIST_SIGNOUT
- Priority: 3

### 8.4. Pathologist Selects Reportable Tests (RES-004)

Per RES-004, at pathologist signout, the pathologist reviews the completed test results and selects which tests to include in the final report.

- Trigger: Pathologist reviews results and selects reportable tests
- Action: Route to REPORT_GENERATION, update slide `reported` flags
- Priority: 4

### 8.5. Report Generated (RES-005)

Per RES-005, after the pathologist selects reportable tests, the system shall generate the final report and transition the order to its terminal state.

- Trigger: Report generated
- Action: Route to ORDER_COMPLETE
- Priority: 5

ORDER_COMPLETE is a terminal state. No further processing or state transitions are possible once the order reaches ORDER_COMPLETE.

## 9. Output Format

The system shall produce a structured JSON output for each resulting routing decision:

```json
{
  "next_state": "RESULTING_HOLD | RESULTING | PATHOLOGIST_SIGNOUT | REPORT_GENERATION | ORDER_COMPLETE",
  "applied_rules": ["RES-003"],
  "flags": [],
  "reasoning": "Explanation of which rule applies and why"
}
```

When the `MISSING_INFO_PROCEED` flag is cleared, it shall be removed from the order's flags array in the output. All other accumulated flags from prior workflow steps shall be preserved.
