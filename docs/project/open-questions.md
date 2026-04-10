# Open Questions / Future Considerations

Status: **deferred** = post-POC | **active** = under consideration now | **resolved** = decided

All items are currently resolved. New questions will be added here as they arise.

- **[resolved]** Constrained generation (limiting model outputs to valid next-states only) — POC evaluates raw model output only. Hallucinated states are scored as failures and logged separately. Constrained generation can be revisited if hallucination rates are high.
- **[resolved]** 21 CFR Part 11 validation requirements — out of scope for this POC.
- **[resolved]** Multi-step prediction (predict remainder of workflow, not just next step) — out of scope. The POC tests per-step routing accuracy. Multi-step forecasting is a different research question that depends on predicting unknowable future events (pathologist decisions, QC outcomes).
- **[resolved]** Prompt tuning per model — moved to [Implementation Phases](implementation-phases.md) as a post-Phase 6 follow-on. Standardized comparison must complete first.
- **[resolved]** Quantization impact experiment — moved to [Implementation Phases](implementation-phases.md) Phase 3. Run during model integration when local models are already being pulled and tested.
