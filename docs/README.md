# Documentation

## Workflow Domain

These documents describe the breast cancer histology workflow that Samantha routes.

- [Workflow Overview](workflow/workflow-overview.md) - States, transitions, and the overall specimen processing pipeline
- [Rule Catalog](workflow/rule-catalog.md) - Discrete rules with trigger conditions and prescribed actions
- [Accessioning Logic](workflow/accessioning-logic.md) - Order triage and intake rules
- [Pathologist Review Panels](workflow/pathologist-review-panels.md) - H&E and IHC review decision points

## Technical Design

- [Architecture](technical/architecture.md) - System design and component interactions
- [Data Model](technical/data-model.md) - Database schema (orders, slides, events, decisions)
- [Evaluation Metrics](technical/evaluation-metrics.md) - How accuracy, variance, and reliability are measured
- [Technology Stack](technical/technology-stack.md) - Python, llama.cpp, ChromaDB, FastAPI

## Test Design

- [Scenario Design](scenarios/scenario-design.md) - How test scenarios are structured and categorized
- [Event Data Contracts](scenarios/event-data-contracts.md) - Expected data formats for workflow events
