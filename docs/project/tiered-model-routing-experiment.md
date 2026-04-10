# Experiment: Tiered Model Routing

## Hypothesis

A smaller, faster model can handle deterministic routing decisions (null checks, threshold comparisons, enum lookups) with accuracy comparable to the best-performing model, while the more capable model is only needed for decisions that require judgment (ambiguous clinical context, novel situations, multi-factor assessments).  If true, a production system could route the majority of decisions through a fast model (sub-4s) and only escalate to a slower, more capable model when needed, without sacrificing overall accuracy.

## Background

The head-to-head evaluation found that 38 of 40 workflow rules are fully deterministic.  The remaining failures in even the best model (Qwen 2.5 Coder 32B at 99.7%) cluster around boundary comparisons and multi-rule satisficing, which are deterministic tasks the LLM occasionally gets wrong.  Meanwhile, Gemma 3 27B achieved 100% state and rule accuracy on accumulated state scenarios at 2.8s/step, suggesting smaller models can handle straightforward routing reliably.

## What to Build

### Phase 1: Classify scenario steps

Create a script (`scripts/classify_steps.py`) that reads all scenarios in the 33-scenario screening set and classifies each step as `deterministic` or `judgment` based on the expected rules in that step.

**Classification criteria:**
- **Deterministic:** Step's expected `applied_rules` contain ONLY rules from this list: ACC-001 through ACC-009, SP-001 through SP-006, HE-001 through HE-004, IHC-001 through IHC-007, IHC-010, IHC-011, RES-001 through RES-005
- **Judgment:** Step's expected `applied_rules` contain ANY of: HE-005 through HE-009, IHC-008, IHC-009

Output a JSON file (`data/step_classifications.json`) mapping `scenario_id + step_number` to `deterministic` or `judgment`, with counts for each category.

### Phase 2: Run both models on the screening set

Run the 33-scenario screening set (same set used in the h2h comparisons, defined in `scripts/scenario_sets.sh` as `SCREENING_SET`) through two models:

1. **Fast model: Gemma 3 27B** - Run locally via llama.cpp, 5 runs
2. **Capable model: Qwen 2.5 Coder 32B** - Run locally via llama.cpp, 5 runs

Use the existing evaluation harness with skills-based prompting (`--prompt-extras skills,retry_clarification`).  Save results to `results/tiered_routing_gemma27b/` and `results/tiered_routing_coder32b/`.

**Important:** Both models must be run locally (not via OpenRouter) so latency numbers are comparable.  If existing local run data already exists for these models on this exact scenario set with skills-based prompting, reuse it rather than re-running.

### Phase 3: Analyze with simulated tiered routing

Create a script (`scripts/analyze_tiered_routing.py`) that:

1. Loads per-step results from both model runs
2. Loads the step classifications from Phase 1
3. For each step across all runs, computes accuracy metrics (state, rules, flags) broken down by:
   - Gemma 3 27B on deterministic steps only
   - Gemma 3 27B on judgment steps only
   - Qwen 2.5 Coder 32B on deterministic steps only
   - Qwen 2.5 Coder 32B on judgment steps only
4. Simulates a **tiered routing** result: for each step, use Gemma 3 27B's answer if the step is classified as `deterministic`, and Qwen 2.5 Coder 32B's answer if classified as `judgment`
5. Computes overall accuracy and latency for the simulated tiered approach vs each model alone
6. Outputs a summary report to `results/tiered_routing_analysis.md`

### Expected output format

The analysis report should include:

**Table 1: Accuracy by step classification**

| Model | Step Type | Count | State Acc | Rule Acc | Flag Acc |
|-------|-----------|-------|-----------|----------|----------|

**Table 2: Simulated tiered routing vs baselines**

| Approach | State Acc | Rule Acc | Flag Acc | Mean Latency | p50 Latency |
|----------|-----------|----------|----------|-------------|------------|
| Gemma 3 27B only | | | | | |
| Qwen 2.5 Coder 32B only | | | | | |
| Tiered (Gemma deterministic + Coder judgment) | | | | | |

**Table 3: Step classification summary**

How many steps fall into each category across the 33 screening scenarios.

## Success Criteria

The hypothesis is supported if:
1. Gemma 3 27B accuracy on deterministic steps is >= 98% (comparable to Qwen 2.5 Coder 32B)
2. The simulated tiered approach achieves overall accuracy within 1 percentage point of Qwen 2.5 Coder 32B alone
3. The simulated tiered approach has significantly lower mean latency than Qwen 2.5 Coder 32B alone

The hypothesis is refuted if:
1. Gemma 3 27B accuracy on deterministic steps is materially worse than Qwen 2.5 Coder 32B (>3pp gap)
2. The accuracy gap on deterministic steps is NOT in boundary comparisons / multi-rule (i.e., the failures are in unexpected places)

## Notes

- The step classification is done post-hoc based on expected rules, not predicted rules.  This means we're asking "if a perfect router sent deterministic steps to Gemma, how would it perform?" rather than "can we build a router that correctly classifies steps in real-time?"  The real-time routing question is a follow-up experiment.
- If the 33-scenario screening set doesn't have enough judgment-required steps to be statistically meaningful, extend to the full 113-scenario set.
- Consider also testing Qwen3 Coder 30B as the fast model (3.3s median, locally run) as an alternative to Gemma 3 27B.
