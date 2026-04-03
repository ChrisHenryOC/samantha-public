# Sample Preparation Standard Operating Procedure

**Document ID:** SOP-SP
**Version:** 1.0
**Effective Date:** 2026-02-01
**Workflow Step:** SAMPLE_PREP (GROSSING through QC)
**Applicable Rules:** SP-001 through SP-006

---

## 1. Purpose and Scope

This procedure defines the processing steps, quality control checks, and
routing logic for specimen preparation. Sample preparation transforms a gross
tissue specimen into stained-ready tissue sections through a series of
sequential sub-steps: grossing, processing, embedding, sectioning, and
quality control.

This procedure applies to all orders that have been accepted at accessioning
(routed to SAMPLE_PREP_PROCESSING from either ACCEPTED or MISSING_INFO_PROCEED
outcomes). The order's accumulated flags (e.g., `MISSING_INFO_PROCEED`) carry
forward unchanged through sample preparation.

## 2. Step Processing Rules

These rules govern how the system routes orders through the sequential sample
preparation sub-steps. At each sub-step, the system evaluates the event
outcome and applies the first matching rule.

### 2.1. Step Advancement (SP-001)

Per SP-001, when a sample preparation step is completed successfully, the
system shall advance the order to the next sample preparation step in
sequence:

- SAMPLE_PREP_PROCESSING -> SAMPLE_PREP_EMBEDDING
- SAMPLE_PREP_EMBEDDING -> SAMPLE_PREP_SECTIONING
- SAMPLE_PREP_SECTIONING -> SAMPLE_PREP_QC

- Trigger: Step completed successfully
- Action: Advance to next sample prep step
- Priority: 1

### 2.2. Retry on Failure with Tissue Available (SP-002)

Per SP-002, when a sample preparation step fails and tissue remains available
for rework, the system shall retry the current step. The order remains at the
same sub-step and the failed attempt is recorded as an event.

- Trigger: Step failed, tissue available for rework
- Action: RETRY current step
- Priority: 2
- The system does not advance or regress — the order remains at the current
  sub-step

### 2.3. Abort on Insufficient Tissue (SP-003)

Per SP-003, when a sample preparation step fails and insufficient tissue
remains, the system shall abort the order. The order transitions to the
terminal state ORDER_TERMINATED_QNS (quantity not sufficient).

- Trigger: Step failed, insufficient tissue for rework
- Action: ABORT -> ORDER_TERMINATED_QNS
- Priority: 3
- This is a terminal state — no further processing is possible

## 3. Quality Control

The technician shall perform quality control checks on the prepared tissue
sections before releasing them for H&E staining. QC evaluation assesses the
following criteria:

- **Section thickness**: Sections shall be of uniform and appropriate thickness
- **Tissue integrity**: Tissue shall be intact without tears, folds, or
  compression artifacts
- **Mounting quality**: Sections shall be properly mounted on the slide without
  bubbles or debris

### 3.1. QC Pass (SP-004)

Per SP-004, when sample preparation QC passes all checks (section thickness,
tissue integrity, mounting quality), the system shall advance the order to H&E
staining.

- Trigger: Sample prep QC passes all criteria
- Action: Advance to HE_STAINING
- Priority: 4

### 3.2. QC Failure with Tissue Available (SP-005)

Per SP-005, when sample preparation QC fails and tissue remains available, the
system shall route the order back to sectioning for rework. The order returns
to SAMPLE_PREP_SECTIONING, not to the specific QC-failing step.

- Trigger: Sample prep QC fails, tissue available for resectioning
- Action: RETRY -> SAMPLE_PREP_SECTIONING
- Priority: 5

### 3.3. QC Failure with Insufficient Tissue (SP-006)

Per SP-006, when sample preparation QC fails and insufficient tissue remains
for resectioning, the system shall abort the order.

- Trigger: Sample prep QC fails, insufficient tissue
- Action: ABORT -> ORDER_TERMINATED_QNS
- Priority: 6

## 4. Sample Preparation Sub-Steps

Sample preparation consists of five sequential sub-steps. Each sub-step must
complete successfully before the order advances to the next.

### 4.1. Grossing (performed at SAMPLE_PREP_PROCESSING entry)

The technician shall perform gross examination and dissection of the tissue
specimen. Grossing involves macroscopic evaluation, measurement, description,
and selection of tissue sections for processing. Grossing is performed as
part of the SAMPLE_PREP_PROCESSING state entry — there is no separate
SAMPLE_PREP_GROSSING state.

- Entry condition: Order routed from accessioning (ACCEPTED or
  MISSING_INFO_PROCEED) via `grossing_complete` event
- Success outcome: Per SP-001, advance to SAMPLE_PREP_PROCESSING

### 4.2. Tissue Processing (SAMPLE_PREP_PROCESSING)

The technician shall process the tissue through fixation, dehydration, clearing,
and infiltration. Tissue processing prepares the specimen for embedding in
paraffin wax.

- Entry condition: Grossing completed successfully
- Success outcome: Per SP-001, advance to SAMPLE_PREP_EMBEDDING
- Failure with tissue available: Per SP-002, retry processing
- Failure with insufficient tissue: Per SP-003, abort to ORDER_TERMINATED_QNS

### 4.3. Embedding (SAMPLE_PREP_EMBEDDING)

The technician shall embed the processed tissue in paraffin wax to create a
tissue block. Proper orientation of the tissue within the block is critical
for subsequent sectioning.

- Entry condition: Processing completed successfully
- Success outcome: Per SP-001, advance to SAMPLE_PREP_SECTIONING
- Failure with tissue available: Per SP-002, retry embedding
- Failure with insufficient tissue: Per SP-003, abort to ORDER_TERMINATED_QNS

### 4.4. Sectioning (SAMPLE_PREP_SECTIONING)

The technician shall cut thin sections from the paraffin block using a
microtome and mount the sections onto glass slides. Section thickness shall be
appropriate for downstream staining.

- Entry condition: Embedding completed successfully, OR retry from QC failure,
  OR recut request from pathologist H&E review
- Success outcome: Per SP-001, advance to SAMPLE_PREP_QC
- Failure with tissue available: Per SP-002, retry sectioning
- Failure with insufficient tissue: Per SP-003, abort to ORDER_TERMINATED_QNS

Sectioning is a re-entry point in the workflow. Orders may return to sectioning
from:

- Sample prep QC failure (per SP-005)
- H&E QC failure requiring recut (per HE-003)
- Pathologist recut request (per HE-009)

Each return to sectioning consumes additional tissue from the block. The system
shall assess tissue availability at each re-entry.

### 4.5. Quality Control (SAMPLE_PREP_QC)

QC is the final sub-step of sample preparation. The technician evaluates the
prepared sections against the criteria defined in Section 3. The routing rules
in Sections 3.1 through 3.3 determine the outcome.

## 5. Tissue Availability Assessment

Tissue availability is a critical decision factor at every failure point in
sample preparation. The system routes differently based on whether sufficient
tissue remains:

| Tissue Available | Routing |
|---|---|
| Yes | Retry the current step (SP-002) or return to sectioning (SP-005) |
| No | Abort to ORDER_TERMINATED_QNS (SP-003 or SP-006) |

The tissue availability determination is provided in the event data. The system
shall not estimate or infer tissue availability — this is reported by the
laboratory technician.

## 6. Output Format

The system shall produce a structured JSON output for each sample preparation
routing decision:

```json
{
  "next_state": "SAMPLE_PREP_PROCESSING | SAMPLE_PREP_EMBEDDING | SAMPLE_PREP_SECTIONING | SAMPLE_PREP_QC | HE_STAINING | ORDER_TERMINATED_QNS",
  "applied_rules": ["SP-001"],
  "flags": [],
  "reasoning": "Explanation of why this rule applies"
}
```

Flags accumulated from accessioning (e.g., `MISSING_INFO_PROCEED`) shall be
preserved in the output. Sample preparation does not add or remove flags — it
passes them through unchanged.
