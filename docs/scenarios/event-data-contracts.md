# Event Data Contracts

This document defines the `event_data` payload for each of the 18 event types used in test scenarios. Each event type has required and optional fields that describe what happened in the workflow.

> **Scope note:** Field-level validation of `event_data` is out of scope for issue #24. The scenario loader accepts any `dict` for `event_data`; these contracts are for scenario authors and future validation.

## Accessioning

### order_received

Initial order submission with patient and specimen information.

| Field | Type | Required | Description |
|---|---|---|---|
| patient_name | string | Yes | Patient name (LASTNAME, First) |
| age | integer | Yes | Patient age in years |
| sex | string | Yes | Patient sex (M/F) |
| specimen_type | string | Yes | Specimen type (biopsy, resection; excision and mastectomy are subtypes of resection) |
| anatomic_site | string | Yes | Anatomic site of specimen |
| fixative | string | Yes | Fixative used (formalin, alcohol, etc.) |
| fixation_time_hours | number | Yes | Fixation time in hours |
| ordered_tests | array[string] | Yes | Tests or panels ordered |
| priority | string | Yes | Priority level (routine, rush) |
| billing_info_present | boolean | Yes | Whether billing information is present |

```json
{
  "patient_name": "TESTPATIENT-0001, Sarah",
  "age": 58,
  "sex": "F",
  "specimen_type": "biopsy",
  "anatomic_site": "breast",
  "fixative": "formalin",
  "fixation_time_hours": 24,
  "ordered_tests": ["Breast IHC Panel"],
  "priority": "routine",
  "billing_info_present": true
}
```

### missing_info_received

Information that was previously missing has been provided.

| Field | Type | Required | Description |
|---|---|---|---|
| info_type | string | Yes | Type of info received (patient_name, patient_sex, billing) |
| value | string | Yes | The provided value |

```json
{
  "info_type": "patient_name",
  "value": "TESTPATIENT-0002, Jane"
}
```

## Sample Prep

### grossing_complete

Grossing step completed.

| Field | Type | Required | Description |
|---|---|---|---|
| outcome | string | Yes | Result of grossing (success, failure) |
| tissue_available | boolean | No | Whether tissue remains for retry (required if outcome is failure) |

```json
{
  "outcome": "success"
}
```

### processing_complete

Tissue processing step completed.

| Field | Type | Required | Description |
|---|---|---|---|
| outcome | string | Yes | Result of processing (success, failure) |
| tissue_available | boolean | No | Whether tissue remains for retry (required if outcome is failure) |

```json
{
  "outcome": "success"
}
```

### embedding_complete

Tissue embedding step completed.

| Field | Type | Required | Description |
|---|---|---|---|
| outcome | string | Yes | Result of embedding (success, failure) |
| tissue_available | boolean | No | Whether tissue remains for retry (required if outcome is failure) |

```json
{
  "outcome": "success"
}
```

### sectioning_complete

Tissue sectioning step completed.

| Field | Type | Required | Description |
|---|---|---|---|
| outcome | string | Yes | Result of sectioning (success, failure) |
| tissue_available | boolean | No | Whether tissue remains for retry (required if outcome is failure) |

```json
{
  "outcome": "success"
}
```

### sample_prep_qc

Quality control check on prepared sample sections.

| Field | Type | Required | Description |
|---|---|---|---|
| result | string | Yes | QC result (pass, fail) |
| tissue_available | boolean | No | Whether tissue remains for recut (required if result is fail) |
| issues | array[string] | No | Description of QC issues found |

```json
{
  "result": "pass"
}
```

## H&E Staining and Review

### he_staining_complete

H&E staining step completed.

| Field | Type | Required | Description |
|---|---|---|---|
| outcome | string | Yes | Result of staining (success, failure) |

```json
{
  "outcome": "success"
}
```

### he_qc

Quality control check on H&E stained slide.

| Field | Type | Required | Description |
|---|---|---|---|
| result | string | Yes | QC result (pass, fail) |
| failure_reason | string | No | Reason for failure (restain, recut) |
| tissue_available | boolean | No | Whether tissue remains for recut (required if failure_reason is recut) |

```json
{
  "result": "pass"
}
```

### pathologist_he_review

Pathologist review of H&E slide with diagnosis.

| Field | Type | Required | Description |
|---|---|---|---|
| diagnosis | string | Yes | Pathologist diagnosis (invasive_carcinoma, dcis, suspicious_atypical, benign) |
| panel | array[string] | No | Custom IHC panel specified by pathologist (required for suspicious_atypical) |
| recuts_needed | boolean | No | Whether pathologist requests recuts |
| notes | string | No | Pathologist notes |

```json
{
  "diagnosis": "invasive_carcinoma"
}
```

## IHC

### ihc_staining_complete

IHC staining completed for one or more slides.

| Field | Type | Required | Description |
|---|---|---|---|
| slide_id | string | Yes | Slide identifier |
| test | string | Yes | Test marker (ER, PR, HER2, Ki-67) |
| outcome | string | Yes | Result of staining (success, failure) |
| tissue_available | boolean | No | Whether tissue remains for retry (required if outcome is failure) |

```json
{
  "slide_id": "SL-001",
  "test": "ER",
  "outcome": "success"
}
```

### ihc_qc

Quality control check on IHC stained slide.

| Field | Type | Required | Description |
|---|---|---|---|
| slide_id | string | Yes | Slide identifier |
| test | string | Yes | Test marker (ER, PR, HER2, Ki-67) |
| result | string | Yes | QC result (pass, fail) |
| tissue_available | boolean | No | Whether tissue remains for retry (required if result is fail) |

```json
{
  "slide_id": "SL-001",
  "test": "ER",
  "result": "pass"
}
```

### ihc_scoring

Scoring result for an IHC slide.

| Field | Type | Required | Description |
|---|---|---|---|
| slide_id | string | Yes | Slide identifier |
| test | string | Yes | Test marker (ER, PR, HER2, Ki-67) |
| score | string | Yes | Score value (e.g., "3+", "90%", "15%") |
| interpretation | string | No | Result interpretation (positive, negative, equivocal) |

```json
{
  "slide_id": "SL-003",
  "test": "HER2",
  "score": "2+",
  "interpretation": "equivocal"
}
```

### fish_decision

Pathologist decision on FISH reflex testing for equivocal HER2.

| Field | Type | Required | Description |
|---|---|---|---|
| decision | string | Yes | Pathologist decision (approve, decline) |

```json
{
  "decision": "approve"
}
```

### fish_result

Result received from external FISH testing lab.

| Field | Type | Required | Description |
|---|---|---|---|
| result | string | Yes | FISH result (amplified, not_amplified, qns) |
| ratio | number | No | HER2/CEP17 ratio (if result is amplified or not_amplified) |

```json
{
  "result": "amplified",
  "ratio": 2.5
}
```

## Resulting

### resulting_review

Routing engine evaluates resulting rules. Outcome determines hold or advance.

| Field | Type | Required | Description |
|---|---|---|---|
| outcome | string | Yes | Review outcome (hold, advance) |

```json
{
  "outcome": "advance"
}
```

### pathologist_signout

Pathologist signs out the case and selects reportable tests.

| Field | Type | Required | Description |
|---|---|---|---|
| reportable_tests | array[string] | Yes | Tests to include in final report |
| notes | string | No | Signout notes |

```json
{
  "reportable_tests": ["ER", "PR", "HER2", "Ki-67"]
}
```

### report_generated

Report has been generated, completing the order.

| Field | Type | Required | Description |
|---|---|---|---|
| report_id | string | No | Report identifier |

```json
{
  "report_id": "RPT-001"
}
```

## Related Documents

- [Scenario Design](scenario-design.md) -- scenario structure and categories
- [Rule Catalog](../workflow/rule-catalog.md) -- rules that scenarios test
- [Data Model](../technical/data-model.md) -- persistence entities
