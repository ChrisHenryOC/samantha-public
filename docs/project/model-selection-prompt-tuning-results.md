# Model Selection and Prompt Tuning Results

## Summary

GH #216 ran a 4-phase funnel to select a local model for production routing on
Apple M5 Pro (64GB). GH #219 then ran prompt tuning experiments on the
finalists. Prompt engineering improved the best model from 61.9% to 85.7%
accuracy, but failure analysis revealed the remaining errors are fundamental
LLM limitations — not fixable with better prompts. This led to an
architectural pivot toward hybrid routing (GH #221): a deterministic code-based
rule engine with LLM fallback for edge cases.

## Phase 1: Quick Screen (GH #216)

**Goal**: Eliminate clearly unfit models from 9 candidates.

**Setup**: 33 discriminating scenarios (111 steps), 1 run per model.

| Rank | Model | Size | Acc% | Rule% | Flag% | Avg Latency | Decision |
|------|-------|------|------|-------|-------|-------------|----------|
| 1 | Llama 3.3 70B | 70B Q4 | 66.7% | 93.7% | 100% | 37s/step | Advance |
| 2 | Qwen3 14B | 14B Q4 | 64.0% | 79.3% | 83.8% | 34s/step | Advance |
| 3 | Gemma 3 27B | 27B Q4 | 59.5% | 87.4% | 100% | 24s/step | Advance |
| 4 | Mistral Small 3.2 24B | 24B Q4 | 54.1% | 89.2% | 100% | 14s/step | Advance |
| 5 | Gemma 3 12B | 12B Q4 | 51.4% | 73.9% | 93.7% | 10s/step | Borderline |
| 6 | Llama 3.1 8B | 8B | 18.0% | 62.2% | 97.3% | 3s/step | Eliminated |
| 7 | Qwen3 8B | 8B | — | — | — | — | Eliminated |
| 8 | Hermes 3 8B | 8B | — | — | — | — | Incompatible |
| 9 | Qwen3 30B-A3B MoE | 30B | — | — | — | — | Eliminated |

**Outcome**: Top 4 advanced to Phase 2. 8B-class models and MoE eliminated.

## Phase 2: Variance Measurement (GH #216)

**Goal**: Measure consistency. A model at 70% +/-15% is worse than 60% +/-2%.

**Setup**: 10 discriminating scenarios (35 steps), 5 runs per model.

| Rank | Model | Acc% | +/-% | Rule% | Flag% | Decision |
|------|-------|------|------|-------|-------|----------|
| 1 | Llama 3.3 70B | 61.9% | +/-1.4% | 91.0% | 100% | **Advance** |
| 2 | Qwen3 14B | 61.9% | +/-3.5% | 75.5% | 73.5% | **Advance** |
| 3 | Gemma 3 27B | 59.4% | +/-3.3% | 83.4% | 97.1% | Eliminated |
| 4 | Mistral Small 3.2 24B | 44.0% | +/-3.3% | 70.3% | 97.1% | Eliminated |

**Outcome**: Llama 70B and Qwen3 14B advance. Gemma and Mistral eliminated.

**Key finding**: Accuracy on the 10-scenario subset was lower than Phase 1's
33-scenario set for all models. These scenarios were specifically chosen for
model differentiation — they are harder than the average scenario.

## Phase 2 Root Cause Analysis

Before Phase 3, analysis of failure data identified three failure modes driving
the 38.1% error rate:

1. **Wrong sample prep sequence**: Models output SAMPLE_PREP_EMBEDDING when
   SAMPLE_PREP_PROCESSING is expected. They don't know the correct step
   ordering (PROCESSING -> EMBEDDING -> SECTIONING -> QC).

2. **Literal RETRY output**: The 70B outputs `"RETRY current step"` as its
   predicted state instead of mapping to a valid state name. The rule says
   "RETRY current step" but the model treats the action description as the
   state.

3. **Empty predictions**: Qwen3 14B returns empty `predicted_next_state` on
   several scenarios — invalid JSON or parsing failures.

4. **Prompts are NOT being truncated**: Max prompt size is ~2,541 tokens, well
   within the 4,096 ctx_size. Context length is not the issue.

These findings shaped the Phase 3 experiment design.

## Phase 3a: Prompt Experiments (GH #219)

**Goal**: Test additive prompt sections targeting the specific failure modes.

**Setup**: 5 scenarios (11 steps), 3 runs, 2 models, 5 experiments.

### Experiment Design

| # | Experiment | Prompt Addition | Target |
|---|-----------|----------------|--------|
| 0 | Baseline | — | Phase 2 data |
| 1 | +state_sequence | Explicit step ordering table | Sample prep sequence errors |
| 2 | +retry_clarification | "RETRY means output the current state name" | Literal RETRY output |
| 3 | +combined | Experiments 1 + 2 | Combined effect |
| 4 | +few_shot | Experiment 3 + worked example | Output format grounding |
| 5 | temp=0.1 | Experiment 3 + temperature 0.1 | Slight randomness |

### Results

| # | Experiment | 70B Acc% | 70B +/-% | 14B Acc% | 14B +/-% |
|---|-----------|---------|--------|---------|--------|
| 0 | Baseline | 61.9% | +/-1.4% | 61.9% | +/-3.5% |
| 1 | +state_sequence | 61.9% | +/-8.2% | 52.4% | +/-21.8% |
| 2 | +retry_clarification | **76.2%** | +/-8.2% | 52.4% | +/-21.8% |
| 3 | +combined | 71.4% | **+/-0.0%** | 52.4% | +/-8.2% |
| 4 | **+few_shot** | **85.7%** | **+/-0.0%** | **71.4%** | +/-14.3% |
| 5 | temp=0.1 | 71.4% | +/-0.0% | 57.1% | +/-0.0% |

### What Succeeded

**Experiment 4 (+few_shot)** was the clear winner:

- **Llama 70B**: 85.7% +/-0.0% — +23.8pp over baseline, zero variance
- **Qwen3 14B**: 71.4% +/-14.3% — +9.5pp over baseline (but high variance)

**retry_clarification** was the key unlock for the 70B (+14.3pp alone),
confirming the "literal RETRY" hypothesis was correct.

**few_shot** on top of combined was the single biggest lift. The worked example
(grossing_complete -> SAMPLE_PREP_PROCESSING) grounded the model's
understanding of state transitions. SC-019, which failed in all other
experiments, passed all 9 evaluations with few_shot.

**Qwen3 14B was dropped** after Phase 3a due to +/-14.3% variance even with the
best prompt. The project spec requires consistency for production use.

### What Failed

**state_sequence was net-harmful**: It caused the model to skip the ACCEPTED
state and jump directly to SAMPLE_PREP_PROCESSING. The few_shot example had to
compensate for this by explicitly demonstrating the ACCEPTED -> SAMPLE_PREP
transition. An experiment with retry_clarification + few_shot (no
state_sequence) was never tested and might perform as well or better.

**temp=0.1 provided no benefit**: Same or worse accuracy than combined at
temp=0.0. Temperature tuning is not a lever for this task.

### What Prompt Engineering Cannot Fix

Failure analysis of the Phase 3a experiment 4 results (the best configuration)
identified two irreducible failure modes in the Llama 70B:

#### Failure 1: Numerical Boundary Comparison (SC-013)

**100% failure rate across all 15 runs in all 5 experiments.**

SC-013: HER2 ordered with `fixation_time_hours: 5.0`. Rule ACC-006 says "HER2
ordered and fixation time outside 6-72 hours" -> DO_NOT_PROCESS. Since
5.0 < 6.0, ACC-006 should fire.

The model's reasoning (verbatim):

> fixation time is 5 hours, which is within the acceptable range

The model explicitly states 5 hours is within 6-72 hours. It cannot correctly
evaluate 5.0 < 6.0 in the context of a range boundary. This is a known LLM
limitation — boundary-condition numerical reasoning. The rule text is
unambiguous; the model cannot perform the comparison.

#### Failure 2: Multi-Rule Satisficing (SC-082)

**100% failure rate on rules across all 15 runs in all 5 experiments.**

SC-082 has 5 simultaneous accessioning defects (missing name, missing sex,
invalid site, bad fixation, no billing). Expected: 5 rules (ACC-001, -002,
-003, -006, -007). The model finds only ACC-003 (invalid site = "lung") — the
most obvious defect — gets the correct state (DO_NOT_PROCESS) and stops.

The model's reasoning (verbatim):

> The anatomic site is 'lung', which is not breast-cancer-relevant, triggering
> rule ACC-003 with a severity of REJECT, resulting in the action
> DO_NOT_PROCESS.

Despite explicit instructions to "identify ALL matching rules for
ACCESSIONING," the model satisfices after finding the first REJECT-severity
rule. It never evaluates the remaining 4 rules.

#### Qwen3 14B: JSON Generation Reliability

Qwen3's dominant failure mode is empty predictions (~60% of failures) — the
model returns unparseable JSON. When it does produce valid output, it sometimes
reasons better than the 70B (finding 2 rules in SC-082 vs 70B's 1). But
output reliability is too inconsistent for production use.

## Architectural Pivot: Hybrid Routing (GH #221)

### The Insight

A rule-by-rule assessment of all 40 workflow rules revealed that **38 of 40
are fully deterministic** — evaluable by code with 100% accuracy:

| Step | Rules | Deterministic | Condition Type |
|------|-------|---------------|----------------|
| ACCESSIONING | 9 | 7 + 2 with valid-value sets | Null checks, thresholds, enums |
| SAMPLE_PREP | 6 | 6 | event_type + outcome |
| HE | 9 | 9 | QC result / diagnosis field |
| IHC | 11 | 11 | Event outcome + scoring |
| RESULTING | 5 | 5 | Flag checks + event data |

The LLM was being asked to do work that code could handle perfectly. The
prompt engineering ceiling is not a model limitation for the task as a whole —
it is a limitation of the single-shot LLM-only architecture.

### The Pivot

GH #221 proposes a **hybrid routing architecture**:

1. **Deterministic rule engine** (code): Evaluates all rules with
   boolean/numeric conditions. Returns matching rules with severity. Handles
   ~95% of routing decisions with 100% accuracy.

2. **LLM judgment agent** (local model): Called only for ambiguous or
   unknown inputs that the rule engine cannot resolve. Output constrained via
   GBNF grammar to eliminate parse failures.

3. **Validation layer** (code): Cross-checks LLM output against rule engine
   results. Catches contradictions.

The LLM's role shifts from "sole decision-maker" to "edge-case handler" — a
more appropriate use of its capabilities. The LLM remains central to the
**chat interface** (Phase 8), where natural language understanding is the
primary requirement.

### What This Means for Phase 4

The original Phase 4 plan (GH #216) was to run the winning model + prompt
config against the full 113-scenario corpus. This validation is still useful
to establish a baseline, but the architectural pivot means the production
system will not rely on single-shot LLM routing. Phase 4 results become a
comparison benchmark rather than a production readiness test.

## Timeline

| Date | Milestone |
|------|-----------|
| 2026-03-22 | GH #216 Phase 1 + 2 complete: Llama 70B and Qwen3 14B selected |
| 2026-03-23 | GH #219 Phase 3a complete: few_shot prompt wins (+23.8pp) |
| 2026-03-23 | Failure analysis reveals prompt engineering ceiling |
| 2026-03-24 | GH #221 created: hybrid routing architecture |

## Key Lessons

1. **Prompt engineering has high ROI up to a point.** The few_shot example and
   retry clarification together gained +23.8pp with minimal effort. But the
   remaining failures are structural, not linguistic.

2. **Additive prompt sections can be harmful.** The state_sequence text was
   designed to fix sequence errors but actually introduced new failures by
   creating competing signals with existing rules. The few_shot example fixed
   the original problem AND compensated for the state_sequence damage.

3. **LLMs cannot reliably do precise numerical comparison.** The 70B
   confidently states "5 hours is within the 6-72 hour range" across 15 runs.
   This is not a prompt problem — it is a fundamental limitation of
   pattern-matching-based reasoning.

4. **LLMs satisfice on multi-item evaluation.** Despite explicit "identify ALL"
   instructions, the model stops after finding a sufficient answer. Exhaustive
   evaluation requires either a structured iteration loop or code.

5. **Most workflow rules are deterministic.** 38/40 rules can be evaluated by
   simple code (null checks, numeric comparisons, enum matching). Using an LLM
   for these checks is both slower and less accurate than code.

6. **Variance is as important as accuracy.** Qwen3 14B achieved 71.4%
   accuracy with few_shot — higher than the 70B baseline — but +/-14.3%
   variance made it unsuitable for production.

## Related Documents

- [Phase 3a failure analysis](../../results/phase3a_analysis.md) — detailed
  per-scenario failure data from SQLite databases
- [GH #216](https://github.com/ChrisHenryOC/samantha/issues/216) — model
  selection funnel (Phases 1-4)
- [GH #219](https://github.com/ChrisHenryOC/samantha/issues/219) — prompt
  tuning experiments (Phase 3a/3b)
- [GH #221](https://github.com/ChrisHenryOC/samantha/issues/221) — hybrid
  routing architecture
