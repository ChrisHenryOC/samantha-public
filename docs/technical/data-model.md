# Data Model

This document defines the data structures and persistence model for orders, specimens, slides, events, and evaluation runs.

## Design Principle

Every field exists because it drives at least one decision point. No extraneous data.

## Patient

| Field | Type | Required | Decision Role |
|-------|------|----------|---------------|
| patient_name | string | Yes | Missing -> MISSING_INFO_HOLD |
| age | integer | No | Collected but not decision-critical for POC |
| sex | string (M/F) | Yes | Missing -> MISSING_INFO_HOLD |

Patient names must be obviously synthetic (e.g., "TESTPATIENT-0042, Jane") to avoid privacy concerns.

## Specimen

| Field | Type | Required | Decision Role |
|-------|------|----------|---------------|
| specimen_type | string | Yes | See [Accessioning Logic](../workflow/accessioning-logic.md) for specimen type handling |
| anatomic_site | string | Yes | Not breast-cancer-relevant -> DO_NOT_PROCESS |
| fixative | enum: fresh, formalin | Yes | HER2 ordered + not formalin -> DO_NOT_PROCESS |
| fixation_time_hours | float (nullable) | Required if formalin | Outside 6-72 hrs + HER2 -> DO_NOT_PROCESS |

Valid anatomic sites (breast-cancer-relevant): breast, axillary lymph node, chest wall.

## Order

| Field | Type | Required | Decision Role |
|-------|------|----------|---------------|
| ordered_tests | list of strings | Yes | Drives slide count, IHC panel, fixation checks |
| priority | enum: routine, rush | Yes | Affects processing queue |
| billing_info_present | boolean | Yes | False -> MISSING_INFO_PROCEED |

Valid ordered tests: ER, PR, HER2, Ki-67, or "Breast IHC Panel" (expands to ER, PR, HER2, Ki-67). Panel names are expanded to individual tests by the harness at order creation — the model always sees individual test names in `ordered_tests`.

## Slide Count

Initial slide count at sectioning = number of ordered tests + 1 (H&E) + 2 (backup). Additional slides may be cut if the pathologist adds markers at H&E review.

Example: Breast IHC Panel = ER + PR + HER2 + Ki-67 + H&E + 2 backup = 7 slides. If the pathologist adds a marker, an additional slide is cut from backup or new sectioning.

## Persistence Model

Order data and event data are kept strictly separate. Events are inputs that trigger model invocations; order state is what the model reads and what gets updated after the model's decision. Persistence uses SQLite.

### Orders Table

Stores the current state of each order. One row per order, updated after each model decision.

| Column | Type | Description |
|--------|------|-------------|
| order_id | TEXT PK | Unique order identifier |
| scenario_id | TEXT | Scenario this order belongs to |
| patient_name | TEXT | Patient name (nullable — missing drives HOLD) |
| patient_age | INTEGER | Patient age |
| patient_sex | TEXT | Patient sex (nullable — missing drives HOLD) |
| specimen_type | TEXT | biopsy, resection, FNA |
| anatomic_site | TEXT | Anatomic site |
| fixative | TEXT | fresh, formalin |
| fixation_time_hours | REAL | Fixation time in hours (nullable) |
| ordered_tests | TEXT (JSON array) | Tests ordered |
| priority | TEXT | routine, rush |
| billing_info_present | BOOLEAN | Whether billing info is present |
| current_state | TEXT | Current workflow state |
| flags | TEXT (JSON array) | Accumulated flags (e.g., MISSING_INFO_PROCEED) |
| created_at | TIMESTAMP | Order creation time |
| updated_at | TIMESTAMP | Last update time |

### Slides Table

Tracks individual slides and their lifecycle. One row per slide, FK to orders.

| Column | Type | Description |
|--------|------|-------------|
| slide_id | TEXT PK | Unique slide identifier |
| order_id | TEXT FK | Parent order |
| test_assignment | TEXT | Which test this slide is for (ER, PR, HER2, Ki-67, H&E, backup) |
| status | TEXT | Current status (e.g., sectioned, stain_pending, stain_complete, qc_pass, qc_fail, scored, cancelled) |
| qc_result | TEXT | QC outcome (nullable) |
| score_result | TEXT (JSON) | Quantitative scoring outcome — format varies by test (nullable, see below) |
| reported | BOOLEAN | Whether this test is included in the final report (set at pathologist signout) |
| created_at | TIMESTAMP | Slide creation time |
| updated_at | TIMESTAMP | Last update time |

**Scoring Formats by Test:**

| Test | Format | Equivocal Trigger |
|------|--------|-------------------|
| HER2 | Score: 0, 1+, 2+, 3+ | 2+ -> SUGGEST_FISH_REFLEX |
| ER | Percentage (0-100%) | N/A |
| PR | Percentage (0-100%) | N/A |
| Ki-67 | Percentage (0-100%) | N/A |

### Events Table

Append-only log of everything that happens to an order. Never modified after insertion.

| Column | Type | Description |
|--------|------|-------------|
| event_id | TEXT PK | Unique event identifier |
| order_id | TEXT FK | Which order this event applies to |
| step_number | INTEGER | Sequence number within the scenario |
| event_type | TEXT | Type of event (see event types below) |
| event_data | TEXT (JSON) | Event-specific payload |
| created_at | TIMESTAMP | When the event occurred |

**Event Types:**

| Event Type | Workflow Step(s) | Description |
|------------|-----------------|-------------|
| order_received | Accessioning | New order arrives for evaluation |
| info_received | Accessioning, Resulting | Missing information provided (patient data, billing, etc.) |
| grossing_complete | Sample Prep | Grossing step outcome |
| processing_complete | Sample Prep | Processing step outcome |
| embedding_complete | Sample Prep | Embedding step outcome |
| sectioning_complete | Sample Prep | Sectioning step outcome |
| sample_prep_qc_result | Sample Prep | QC assessment of prepared slides |
| stain_complete | H&E, IHC | Staining step outcome |
| he_qc_result | H&E | H&E stain QC assessment |
| pathologist_he_review | H&E | Pathologist diagnosis and IHC panel decision |
| ihc_qc_result | IHC | IHC stain QC assessment |
| ihc_scoring_complete | IHC | IHC scoring outcome per slide |
| fish_reflex_decision | IHC | Pathologist approves or declines FISH |
| fish_result_received | IHC | External FISH result returned |
| pathologist_signout | Resulting | Pathologist selects reportable tests |
| report_generated | Resulting | Final report produced |

### Decisions Table

Append-only log of model outputs. Captures a snapshot of the order state at decision time for reproducibility.

| Column | Type | Description |
|--------|------|-------------|
| decision_id | TEXT PK | Unique decision identifier |
| run_id | TEXT FK | Which evaluation run this belongs to |
| event_id | TEXT FK | Which event triggered this decision |
| order_id | TEXT FK | Which order |
| model_id | TEXT | Which model made this decision |
| order_state_snapshot | TEXT (JSON) | Full order state at the time of decision |
| model_input | TEXT (JSON) | Exact prompt/context sent to the model |
| model_output | TEXT (JSON) | Raw model response |
| predicted_next_state | TEXT | Model's predicted next state |
| predicted_applied_rules | TEXT (JSON array) | Rule IDs the model cited |
| predicted_flags | TEXT (JSON array) | Flags the model output |
| expected_next_state | TEXT | Ground truth next state |
| expected_applied_rules | TEXT (JSON array) | Ground truth rule IDs |
| expected_flags | TEXT (JSON array) | Ground truth flags |
| state_correct | BOOLEAN | Whether next_state matched |
| rules_correct | BOOLEAN | Whether applied_rules matched |
| flags_correct | BOOLEAN | Whether flags matched |
| latency_ms | INTEGER | Time to get model response |
| input_tokens | INTEGER | Token count for input |
| output_tokens | INTEGER | Token count for output |
| created_at | TIMESTAMP | Decision timestamp |

### Runs Table

Tracks each complete evaluation pass. Every decision row links back to a run, making results reproducible and comparable across iterations.

| Column | Type | Description |
|--------|------|-------------|
| run_id | TEXT PK | Unique run identifier |
| prompt_template_version | TEXT | Version identifier for the prompt template used |
| scenario_set_version | TEXT | Version identifier for the scenario set used |
| model_id | TEXT | Which model was evaluated in this run |
| run_number | INTEGER | Which repetition (1-5 for local models, 1 for cloud) |
| started_at | TIMESTAMP | Run start time |
| completed_at | TIMESTAMP | Run completion time |
| notes | TEXT | Optional notes (e.g., "after prompt revision for IHC rules") |

The decisions table's `run_id` links each decision to its parent run, allowing direct comparison between runs — e.g., "did prompt v2 improve IHC accuracy over prompt v1?"

## Data Lifecycle

**At scenario start:** The first event (`order_received`) carries the order data as entered by lab staff. The test harness (acting as LIS) creates order and slide rows from this event. Order `current_state` is set to `ACCESSIONING`.

**Per event:** An event row is inserted. The current order state (plus slides) is snapshot and sent to the model along with the event. The model's response is recorded as a decision row. The test harness then updates the order and/or slide rows to reflect the new state. Some events carry data that the harness applies before the model sees the next snapshot — e.g., a `pathologist_he_review` event may update `ordered_tests` to reflect the pathologist's panel decision.

**At scenario end:** The orders table reflects final state. The events and decisions tables contain the complete audit trail. All runs are queryable — you can always answer "what did the model see when it made this call?"

## Related Documents

- [Workflow Overview](../workflow/workflow-overview.md) — states and transitions
- [Rule Catalog](../workflow/rule-catalog.md) — rules that drive decisions on this data
- [Architecture](architecture.md) — system layers and how data flows
