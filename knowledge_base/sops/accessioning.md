# Accessioning Standard Operating Procedure

**Document ID:** SOP-ACC
**Version:** 1.0
**Effective Date:** 2026-02-01
**Workflow Step:** ACCESSIONING
**Applicable Rules:** ACC-001 through ACC-009

---

## 1. Purpose

This procedure defines the evaluation and routing logic applied when a new laboratory order arrives at accessioning. The accessioning step determines whether a specimen is accepted for processing, held pending missing information, or rejected as incompatible with the breast cancer histology workflow.

## 2. Scope and Evaluation Principles

This procedure applies to all incoming orders received by the breast cancer histology laboratory. The laboratory processes breast cancer specimens only. Orders for non-breast anatomic sites shall be rejected at accessioning.

### 2.1. All-Match Evaluation

The system shall evaluate **all** accessioning rules (ACC-001 through ACC-009) against every incoming order. Multiple rules may match simultaneously. The system shall report all matching rules in the `applied_rules` output.

The final routing outcome is determined by the highest-severity match according to the severity hierarchy defined in Section 2.2. The system shall not stop evaluation at the first match — all applicable issues must be identified in a single pass.

For example, if both patient name (ACC-001) and billing information (ACC-007) are missing, both rules shall be cited in `applied_rules`, but the final routing shall be MISSING_INFO_HOLD because it is the higher-severity outcome.

### 2.2. Severity Hierarchy

The severity hierarchy determines routing when multiple rules match. The highest-severity outcome wins:

1. **DO_NOT_PROCESS** (REJECT) — The order is rejected and routed to ORDER_TERMINATED. The specimen cannot be processed in this workflow.
2. **MISSING_INFO_HOLD** (HOLD) — The order is held at accessioning. No processing begins until the missing information is received. Upon receipt of the missing information, all accessioning rules are re-evaluated from the beginning.
3. **MISSING_INFO_PROCEED** (PROCEED) — The order proceeds to sample preparation, but a `MISSING_INFO_PROCEED` flag is set on the order. This flag blocks the order at the resulting step until the missing information is resolved.
4. **ACCEPTED** (ACCEPT) — All validations pass. The order proceeds to sample preparation with no flags.

## 3. Validation Checks

### 3.1. Information Completeness

Three rules evaluate whether the order contains the required information fields. These checks share Section 3.1 because they all assess completeness of order data, though their severity outcomes differ.

#### ACC-001: Patient Name Missing

Per ACC-001, if the patient name is missing from the order, the system shall route to MISSING_INFO_HOLD and request the patient name. The order shall not proceed to sample preparation until the patient name is provided.

- Trigger: Patient name field is absent or empty
- Action: MISSING_INFO_HOLD — hold order, request patient name
- Severity: HOLD

#### ACC-002: Patient Sex Missing

Per ACC-002, if the patient sex is missing from the order, the system shall route to MISSING_INFO_HOLD and request the patient sex. The order shall not proceed to sample preparation until the patient sex is provided.

- Trigger: Patient sex field is absent or empty
- Action: MISSING_INFO_HOLD — hold order, request patient sex
- Severity: HOLD

When both ACC-001 and ACC-002 match, both missing fields shall be flagged together and requested simultaneously.

#### ACC-007: Billing Information Missing

Per ACC-007, if billing information is missing from the order, the system shall route to MISSING_INFO_PROCEED and set the `MISSING_INFO_PROCEED` flag on the order.

- Trigger: Billing information is absent
- Action: MISSING_INFO_PROCEED — order proceeds to sample preparation with a flag
- Severity: PROCEED

The `MISSING_INFO_PROCEED` flag persists on the order throughout the workflow. When the order reaches the resulting step, this flag blocks further progress until the missing billing information is provided and the flag is cleared. The order proceeds through sample preparation, H&E, and IHC normally despite the missing billing information.

### 3.2. Specimen and Anatomic Site Compatibility

Two rules evaluate whether the specimen is compatible with the breast cancer histology workflow.

#### ACC-003: Anatomic Site Not Breast-Cancer-Relevant

Per ACC-003, if the anatomic site is not relevant to breast cancer diagnostics, the system shall route to DO_NOT_PROCESS. The laboratory processes only breast cancer specimens.

- Trigger: Anatomic site is not breast-cancer-relevant
- Action: DO_NOT_PROCESS
- Severity: REJECT

Valid breast-cancer-relevant anatomic sites:

- **Breast** — primary site for breast cancer specimens
- **Axillary lymph node** — common site for breast cancer metastasis evaluation
- **Chest wall** — relevant for locally advanced breast cancer

Any anatomic site not in the above list shall trigger DO_NOT_PROCESS. The system shall apply general anatomical knowledge to recognize invalid sites (e.g., liver, lung, colon) rather than relying solely on an allowlist.

#### ACC-004: Specimen Type Incompatible with Histology Workflow

Per ACC-004, if the specimen type is incompatible with the histology workflow or is unrecognized, the system shall route to DO_NOT_PROCESS.

- Trigger: Specimen type is incompatible with histology workflow (e.g., FNA) or unrecognized
- Action: DO_NOT_PROCESS
- Severity: REJECT

The `specimen_type` field is a free-text string, not a constrained enumeration. The system must evaluate both known and unknown types:

| Specimen Type | Handling | Rationale |
|---|---|---|
| Biopsy | Accepted (if other checks pass) | Standard histology specimen compatible with grossing, embedding, and sectioning |
| Resection | Accepted (if other checks pass) | Standard histology specimen compatible with grossing, embedding, and sectioning |
| FNA (fine needle aspiration) | DO_NOT_PROCESS | FNA is a cytology specimen — incompatible with the histology workflow (grossing, embedding, sectioning) |
| Unknown / unrecognized | DO_NOT_PROCESS | Specimen types that cannot be mapped to the histology workflow shall be rejected |

The system shall apply general domain knowledge to recognize incompatible specimen types. FNA is a cytology procedure, not a histology procedure, and therefore cannot proceed through the grossing-embedding-sectioning pipeline even when originating from a valid anatomic site.

### 3.3. HER2 Fixation Requirements

HER2 immunohistochemistry testing requires formalin fixation with a fixation time within the 6-72 hour window, per ASCO/CAP guidelines. Two rules enforce this requirement at accessioning.

#### ACC-005: HER2 Ordered, Fixative Is Not Formalin

Per ACC-005, if HER2 testing is ordered and the fixative is not formalin, the system shall route to DO_NOT_PROCESS.

- Trigger: HER2 is included in the ordered tests AND the fixative is not formalin
- Action: DO_NOT_PROCESS
- Severity: REJECT

#### ACC-006: HER2 Ordered, Fixation Time Outside Tolerance

Per ACC-006, if HER2 testing is ordered and the formalin fixation time is outside the 6-72 hour window, the system shall route to DO_NOT_PROCESS.

- Trigger: HER2 is included in the ordered tests AND the fixation time is less than 6 hours or greater than 72 hours
- Action: DO_NOT_PROCESS
- Severity: REJECT

ACC-005 and ACC-006 apply only when HER2 testing is part of the order. Orders without HER2 testing are not subject to these fixation requirements at accessioning. A separate fixation check applies at the IHC stage if HER2 is added later by the pathologist (see IHC SOP, Section 6.1).

### 3.4. Full Acceptance

**ACC-008: All Validations Pass**

Per ACC-008, if no other accessioning rules match (no missing information, valid anatomic site, valid specimen type, valid fixation if applicable), the system shall route to ACCEPTED.

- Trigger: All validation checks pass with no issues found
- Action: ACCEPTED — order proceeds to sample preparation
- Severity: ACCEPT

## 4. Routing Outcomes

After evaluation, the system routes the order based on the highest-severity outcome:

| Outcome | Next State | Flags Set | Action Required |
| --- | --- | --- | --- |
| ACCEPTED | SAMPLE_PREP_PROCESSING | None | Order proceeds to sample prep |
| MISSING_INFO_PROCEED | SAMPLE_PREP_PROCESSING | `MISSING_INFO_PROCEED` | Order proceeds; flag blocks at resulting |
| MISSING_INFO_HOLD | ACCESSIONING (held) | None | Order held; awaiting missing information |
| DO_NOT_PROCESS | ORDER_TERMINATED | None | Order is rejected; no processing |

### 4.1. Re-evaluation After Hold

When an order is in MISSING_INFO_HOLD and the requested information is received, the system shall re-evaluate **all** accessioning rules from the beginning. The re-evaluation may produce a different outcome — for example, if the patient name is provided but the anatomic site is also invalid, the order transitions to DO_NOT_PROCESS rather than ACCEPTED.

## 5. Output Format

The system shall produce a structured JSON output for each accessioning evaluation:

```json
{
  "next_state": "ACCEPTED | MISSING_INFO_HOLD | MISSING_INFO_PROCEED | DO_NOT_PROCESS",
  "applied_rules": ["ACC-001", "ACC-007"],
  "flags": ["MISSING_INFO_PROCEED"],
  "reasoning": "Explanation of which rules matched and why"
}
```

The `applied_rules` array shall contain **all** rules that matched, not just the one that determined the routing outcome.
