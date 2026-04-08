# UI Test Prompts

Suggested prompts for interactive testing of the web UI chat interface,
organized by role. Each prompt targets a specific seed order designed to
exercise that role's workflow.

## Accessioner

| Order | State | Prompt |
|-------|-------|--------|
| ORD-003 | MISSING_INFO_HOLD | "What information is missing for ORD-003? What do I need to resolve the hold?" |
| ORD-003 | MISSING_INFO_HOLD | "Show me all orders that are on hold and need my attention." |
| ORD-004 | DO_NOT_PROCESS | "Why was ORD-004 marked do-not-process?" |

## Histotech

| Order | State | Prompt |
|-------|-------|--------|
| ORD-012 | SAMPLE_PREP_QC + FIXATION_WARNING | "ORD-012 has a fixation warning. What does that mean for QC?" |
| ORD-012 | SAMPLE_PREP_QC + FIXATION_WARNING | "Show me all orders in sample prep that have warnings or flags." |
| ORD-025 | REPORT_GENERATION | "What's the status of report generation for ORD-025?" |

## Pathologist

| Order | State | Prompt |
|-------|-------|--------|
| ORD-015 | PATHOLOGIST_HE_REVIEW (rush) | "What are my rush orders awaiting H&E review?" |
| ORD-015 | PATHOLOGIST_HE_REVIEW (rush) | "Show me the slide details for ORD-015." |
| ORD-026 | RESULTING (rush) | "What are the IHC scores for ORD-026? Is FISH needed?" |
| ORD-026 | RESULTING (rush) | "Show me my resulting queue with all pending rush orders." |

## Lab Manager

| Order | State | Prompt |
|-------|-------|--------|
| — | all | "Give me a summary of all orders by state." |
| — | all | "Which orders are blocked and why?" |
| — | all | "How many orders currently have workflow flags set? What are the flags?" |
| ORD-020 | SUGGEST_FISH_REFLEX + FISH_SUGGESTED | "What's the status of ORD-020? Why is FISH being suggested?" |

## Setup

Before testing, reset the database to get a clean set of 30 seed orders:

```bash
rm -f data/live.sqlite data/live.sqlite-shm data/live.sqlite-wal
./scripts/start_server.sh
```

Then open `http://localhost:8000`, select the appropriate role from the
dropdown, and enter the prompts above.
