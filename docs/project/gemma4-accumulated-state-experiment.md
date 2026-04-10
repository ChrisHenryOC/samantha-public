# Experiment: Gemma 4 26B-A4B Accumulated State Evaluation

## Context

Gemma 4 26B-A4B achieved 99.8% state accuracy on the 33-scenario screening set with the `list_applicable_rules` tool, making it the top performer overall.  However, it has not been tested on the accumulated state scenarios (SC-090 through SC-099), which test multi-step workflows where the model must track flags across multiple routing events.

The article currently shows accumulated state results for Gemma 3 27B, Qwen3 32B, Qwen3 Coder 30B, Qwen 2.5 Coder 32B, and Llama 3.3 70B.  Gemma 4 26B-A4B is missing from that comparison.

## What to Run

Run the 10 accumulated state scenarios (defined in `scripts/scenario_sets.sh` as `ACCSTATE_SET`) against Gemma 4 26B-A4B in two configurations:

### Run 1: Skills-only baseline
```bash
# 5 runs, skills-based prompting, no tools
uv run python -m src.evaluation.runner \
  --output results/gemma4_26b_accstate_skills \
  --model "Gemma 4 26B-A4B Local" \
  --scenario-ids SC-090,SC-091,SC-092,SC-093,SC-094,SC-095,SC-096,SC-097,SC-098,SC-099 \
  --runs 5 \
  --prompt-extras skills,retry_clarification
```

### Run 2: Tool-assisted (lite)
```bash
# 5 runs, skills + list_applicable_rules tool
uv run python -m src.evaluation.runner \
  --output results/gemma4_26b_accstate_tools_lite \
  --model "Gemma 4 26B-A4B Local" \
  --scenario-ids SC-090,SC-091,SC-092,SC-093,SC-094,SC-095,SC-096,SC-097,SC-098,SC-099 \
  --runs 5 \
  --prompt-extras skills,routing_tools_lite,retry_clarification
```

## Expected Output

For each run, report:
- State accuracy (mean ± variance across 5 runs)
- Rule accuracy
- Flag accuracy
- Scenario reliability
- Mean and p50 latency

Save results to `results/gemma4_26b_accstate_skills/` and `results/gemma4_26b_accstate_tools_lite/`.

## Results (2026-04-07)

Both runs completed overnight (~6.4 hours total).

### Skills-only baseline

```text
gemma-4-26b-a4b  99.6 ±0.6  Rule 99.6%  Flag 97.4%  Rel 72.0%  p50 13,708ms
```

Failures: 15 wrong_flags, 3 timeouts.

### Tool-assisted lite

```text
gemma-4-26b-a4b  100.0 ±0.0  Rule 100.0%  Flag 95.6%  Rel 48.0%  p50 12,830ms
```

Failures: 31 wrong_flags. Heavy "returned reasoning but no content" warnings
throughout — the model exhausts its 16k thinking token budget on tool-call
reasoning.

### Summary

| Metric | Skills-only | + Tool |
|--------|-------------|--------|
| State accuracy | 99.6% ±0.6 | 100.0% ±0.0 |
| Rule accuracy | 99.6% | 100.0% |
| Flag accuracy | **97.4%** | 95.6% |
| Reliability | **72.0%** | 48.0% |
| p50 latency | 13,708ms | 12,830ms |

**Skills-only is the better configuration for accumulated state.** The tool
achieves perfect state/rule accuracy but doubles the flag errors and drops
reliability from 72% to 48%.

### Flag Failure Analysis

Every flag failure is the same pattern: model predicts `[]` when a flag
should be set. Three flags account for all failures:

| Flag | Scenarios | Skills | Tools | Root Cause |
|------|-----------|--------|-------|------------|
| `MISSING_INFO_PROCEED` | SC-090, SC-091, SC-097, SC-098 | 4 | 16 | Token exhaustion (tools); intermittent (skills) |
| `FIXATION_WARNING` | SC-092 | 5/5 | 5/5 | Knowledge gap |
| `HER2_FIXATION_REJECT` | SC-094 | 5/5 | 5/5 | Knowledge gap |

SC-093, SC-095, SC-096, SC-099 are clean in both modes.

### Token Budget Experiment

Bumping `max_tokens` from 16,384 to 32,768 (and `ctx_size` to 65,536)
reduced SC-090 step-2 flag failures from 4/5 to 1/3 in tool mode. SC-092's
`FIXATION_WARNING` failure persisted, confirming it is a knowledge gap.

### Cross-Model Comparison

| Model | State Acc | Rule Acc | Flag Acc | Reliability |
|-------|-----------|----------|----------|-------------|
| **Gemma 4 26B-A4B** | **99.6%** | **99.6%** | **97.4%** | **72.0%** |
| Gemma 3 27B | 100.0% | 100.0% | 97.1% | 60.0% |
| Llama 3.3 70B | 97.9% | 97.9% | 95.7% | 40.0% |
| Qwen3 32B (cloud) | 97.9% | 97.1% | 95.0% | 30.0% |
| Qwen2.5 Coder 32B | 95.0% | 95.0% | 96.4% | 0.0% |

Gemma 4 26B-A4B has the highest reliability of any model tested on
accumulated state (72% vs Gemma 3's 60%).

## Why This Matters

The accumulated state test is the harder test.  The screening set evaluates single-step routing decisions, but accumulated state tests whether the model can maintain flag state across 14 steps per scenario.  Gemma 3 27B scored 100% state/rule accuracy on accumulated state but only 60% reliability due to flag issues.  We need to know if Gemma 4 26B-A4B does better, especially with the tool.

## Branch

This work should be done on the existing `feature/issue-228-tiered-model-routing` branch.
