# Head-to-Head Results: Coder 32B vs Llama 70B vs Cloud Models

## Test Setup

**Date**: 2026-03-27 (overnight run, ~9.5 hours)
**Skills**: Code-style accessioning checklist + all 6 step skills
**Prompt config**: `--prompt-extras skills,retry_clarification`

| Model | Provider | Size | Memory | Screening Runs | AccState Runs |
|-------|----------|------|--------|---------------|--------------|
| Qwen2.5 Coder 32B | local (llama.cpp) | 32B Q4 | ~20GB | 3 | 1 |
| Llama 3.3 70B | local (llama.cpp) | 70B Q4 | ~43GB | 3 | 1 |
| Qwen3 32B | OpenRouter (cloud) | 32B | — | 1 | 1 |
| Gemma 3 27B | OpenRouter (cloud) | 27B | — | 1 | 1 |

## Screening Set Results (33 scenarios, 111 steps)

| Model | Acc% | ±% | Rule% | Flag% | Rel% | Scenarios Passed | p50 Latency |
|-------|------|-----|-------|-------|------|-----------------|-------------|
| **Qwen2.5 Coder 32B** | **99.7** | **±0.5** | **98.8** | **100** | **96.0** | **32/33** | **20s** |
| Qwen3 32B (cloud) | 99.1 | — | 100.0 | 99.1 | 93.9 | 31/33 | 6s |
| Llama 3.3 70B | 97.6 | ±0.5 | 94.9 | 100 | 82.8 | 27/33 | 40s |
| Gemma 3 27B (cloud) | 89.2 | — | 87.4 | 100 | 57.6 | 19/33 | 3s |

### Key Finding: Coder 32B Outperforms the 70B

The Qwen2.5 Coder 32B achieves the highest accuracy across all metrics while
using half the memory and running twice as fast as the Llama 70B. The coding
model's training on structured instruction-following translates directly to
better skill adherence.

The Llama 70B has **3 consistent wrong-state failures** (SC-009, SC-100,
SC-102) that the Coder 32B handles perfectly. These are ACCESSIONING
validation checks (ACC-003, ACC-004) where the 70B doesn't follow the
explicit valid-set lists in the skill document.

## Accumulated State Results (10 scenarios, 140 steps)

| Model | Acc% | Rule% | Flag% | Rel% | Scenarios Passed |
|-------|------|-------|-------|------|-----------------|
| **Gemma 3 27B** (cloud) | **100.0** | **100.0** | 97.1 | 60.0 | **6/10** |
| Llama 3.3 70B | 97.9 | 97.9 | 95.7 | 40.0 | 4/10 |
| Qwen3 32B (cloud) | 97.9 | 97.1 | 95.0 | 30.0 | 3/10 |
| Qwen2.5 Coder 32B | 95.0 | 95.0 | 96.4 | 0.0 | 0/10 |

### Key Finding: Coder 32B Struggles on Long Sequences

The Coder 32B passes 0 of 10 accumulated state scenarios despite 95% step-level
accuracy. The dominant failure is **IHC QC misinterpretation**: the model
predicts IHC-003 (slides pending) when the event data indicates IHC-002 (all
slides QC pass). This affects SC-090, SC-091, SC-097, SC-098.

Gemma 27B leads on accumulated state with 100% state accuracy — surprising
given its poor screening set performance (89.2%). This suggests Gemma is
better at following multi-step workflow sequences but worse at ACCESSIONING
validation checks.

## Per-Scenario Failure Analysis

### Screening Set: Coder 32B Failures

| Scenario | Runs | Root Cause |
|----------|------|------------|
| SC-082 | 3/3 FAIL | Multi-rule: finds ACC-004/ACC-005 false positives, misses ACC-007 |
| SC-026 | 1/3 FAIL | Hallucinated ACC-006: claimed 40.0h is outside 6-72 range (variance) |

SC-082 is the extreme multi-defect scenario (5 simultaneous issues). The model
consistently over-reports rules. SC-026 is a one-off variance issue — the model
incorrectly evaluated 40.0 as outside the 6-72 range in 1 of 3 runs.

### Screening Set: Llama 70B Failures

| Scenario | Runs | Root Cause | State Wrong? |
|----------|------|------------|-------------|
| SC-009 | 3/3 | FNA not identified as invalid (ACC-004) | **YES** |
| SC-100 | 3/3 | FNA not identified as invalid (ACC-004) | **YES** |
| SC-102 | 2/3 | "skin overlying breast" not rejected (ACC-003) | **YES** |
| SC-010 | 3/3 | False positive ACC-003 (site is breast) | No |
| SC-012 | 3/3 | False positive ACC-003 | No |
| SC-082 | 3/3 | Multi-rule: misses ACC-006 or adds ACC-004 FP | No |

The 70B's 3 wrong-state failures (SC-009, SC-100, SC-102) are all
ACCESSIONING validation checks where the model ignores the explicit
valid-set lists in the skill. The Coder 32B handles all of these correctly.

### Screening Set: Qwen3 32B Failures (cloud)

| Scenario | Root Cause |
|----------|------------|
| SC-026 | SP-005: correct rule but wrong state (SAMPLE_PREP_QC vs SECTIONING) |
| SC-109 | Correct state and rules, missing MISSING_INFO_PROCEED flag |

Minor issues — both have correct rule identification.

### Screening Set: Gemma 27B Failures (cloud)

14 failures. Major patterns:
- Cannot identify FNA/swab as invalid (ACC-004): SC-009, SC-100, SC-101
- Misses ACC-006 threshold (same as original LLM failure): SC-013, SC-014, SC-081
- Applies SP-003 (QNS/terminated) instead of SP-002 (retry): SC-019, SC-020, SC-028
- Cannot validate anatomic site edge cases: SC-102

Gemma 27B does not follow the structured skill checklists as well as the
Qwen-family models or the 70B.

### Accumulated State: Common Failures

These issues affect multiple or all models:

**FIXATION_WARNING flag** (SC-092): All 4 models fail. The scenario expects
this flag but it is not documented in any skill. This is a skill coverage
gap — the FIXATION_WARNING flag needs to be added to the accessioning skill
for the case where fixation time is borderline (within range but near boundary).

**RECUT_REQUESTED flag clearing** (SC-093, SC-099): 3 of 4 models carry
this flag forward when it should have been cleared after recut completion.
The skills don't specify when RECUT_REQUESTED is cleared.

**FISH_SUGGESTED flag clearing** (SC-095, SC-096): Coder 32B and Qwen3 32B
carry this flag forward after the FISH decision. The skill should specify
that FISH_SUGGESTED is cleared after IHC-008 (approve) or IHC-009 (decline).

**SC-094 step 1** (SC-094): Coder 32B and Llama 70B both hallucinate
ACC-006 on an order with fixation_time_hours within the valid range. This
is a variance/hallucination issue, not a skill gap.

### Accumulated State: Coder 32B Specific

**IHC-003 vs IHC-002** (SC-090, SC-091, SC-097, SC-098): The Coder model
consistently predicts IHC-003 (slides pending) when the ihc_qc event data
indicates all slides passed (IHC-002). The IHC skill table says:

```text
| All slides complete AND all QC pass | IHC-002 | IHC_SCORING |
| Not all slides complete (some pending) | IHC-003 | IHC_QC (stay) |
```

The model is misreading the `all_slides_complete` field in the event data.
This is the primary reason the Coder 32B scores 0% reliability on
accumulated state despite 95% step accuracy.

## Combined Model Assessment

| Model | Screening State% | AccState State% | Strengths | Weaknesses |
|-------|-----------------|----------------|-----------|------------|
| Coder 32B | **99.7** | 95.0 | Skill adherence, structured validation, speed, memory | IHC QC misread, flag clearing |
| Llama 70B | 97.6 | 97.9 | Consistent, good long-sequence | Ignores valid-set checks, slow, high memory |
| Qwen3 32B | 99.1 | 97.9 | Near-perfect rules, good overall | Cloud-only, minor state errors |
| Gemma 27B | 89.2 | **100.0** | Excellent long-sequence state | Poor ACCESSIONING, poor skill adherence |

## Recommendations

### For Production Routing (Single-Step Events)

**Qwen2.5 Coder 32B is the recommended model.** At 99.7% state accuracy
on the screening set, 20s latency, and 20GB memory, it is the best overall
choice for production routing. Its only consistent failure (SC-082 rules)
does not affect routing correctness.

### For Accumulated State / Long Sequences

The Coder 32B needs IHC skill refinement before it can reliably handle the
full IHC QC → scoring → FISH pathway. The IHC skill should be updated to
more explicitly guide the model on reading `all_slides_complete` from the
event data.

### Skill Improvements Identified

1. **IHC QC skill**: Add explicit instruction to check `all_slides_complete`
   field before evaluating slide-level results
2. **Flag clearing**: Add guidance to all skills about when flags are cleared
   (RECUT_REQUESTED, FISH_SUGGESTED, MISSING_INFO_PROCEED)
3. **FIXATION_WARNING flag**: Add to accessioning skill for borderline
   fixation time cases (SC-092)
4. **SC-094 ground truth**: Verify whether the expected output is correct —
   multiple models hallucinate ACC-006 on this scenario

## Post-Test: Skill Refinement and Additional Models

### Accumulated State Skill Fixes

Three skill gaps were fixed after the overnight run:

1. **IHC QC**: Added explicit `all_slides_complete` field check with note
   that order flags do not affect QC evaluation. The model was conflating
   MISSING_INFO_PROCEED with slide completion status.
2. **Flag clearing**: Added REMOVE instructions to IHC (FISH_SUGGESTED),
   sample_prep (RECUT_REQUESTED), and resulting (MISSING_INFO_PROCEED) skills.
3. **FIXATION_WARNING**: Added borderline fixation flag (6-8h or 68-72h)
   to accessioning skill.
4. **HER2 prerequisite gate**: Restructured ACC-005/006/009 as explicit
   if/else block with skip example for non-HER2 orders.

**Coder 32B accumulated state after fixes**: 0/10 → 6-8/10 (varies by run).
Remaining failures are SC-094 (HER2 hallucination — model fires ACC-006
when HER2 not ordered) and variance on SC-090/SC-091.

**Qwen3 32B (cloud) accumulated state after fixes**: 8/10, 99.3% state
accuracy. Correctly handles the HER2 prerequisite gate that the Coder fails.

### Qwen3 32B Local Evaluation

Tested Qwen3 32B as a local model (Q4_K_M and Q5_K_M quantizations) to see
if the cloud model's strong performance translates to local deployment.

| Metric | Q4_K_M | Q5_K_M | Coder 32B (ref) | Cloud (ref) |
|--------|--------|--------|-----------------|-------------|
| State accuracy | 98.5% ±2.6 | 95.5% ±4.5 | 100% ±0.0 | 99.1% |
| p50 latency | 44s/step | 52s/step | 20s/step | 6s/step |
| SC-013 | 3/3 PASS | 1/3 PASS | 3/3 PASS | PASS |
| SC-082 | 3/3 PASS | 2/3 PASS | FAIL (rules) | PASS |
| SC-094 | 0/3 FAIL | 0/3 FAIL | FAIL | PASS |

**Qwen3 32B local does NOT justify switching from the Coder 32B:**

- **2x slower** (44s vs 20s per step) — likely due to Qwen3's thinking
  tokens adding hidden compute
- **Less accurate** on the screening scenarios (98.5% vs 100%)
- **Higher variance** (±2.6% vs ±0.0%)
- **Q5 is worse than Q4** — higher quantization didn't help, introducing
  more variance and regressions (SC-013 passed 1/3 instead of 3/3)
- **SC-094 still fails** — the HER2 hallucination persists in local
  quantized versions despite passing in the cloud (full precision) version

## Final Model Recommendation

**Qwen2.5 Coder 32B (Q4_K_M) is the production model.**

| Property | Value |
|----------|-------|
| Screening accuracy | 99.7% ±0.5% (32/33 scenarios) |
| Accumulated state | 6-8/10 with improved skills |
| Memory | ~20GB (leaves 44GB for system + chat) |
| Latency | 20s/step (2x faster than 70B, 2x faster than Qwen3 32B) |
| JSON reliability | 100% (zero empty responses) |
| Variance | Near-zero (±0.0% on 5-scenario set, ±0.5% on 33-scenario set) |

**Why not other models:**

- **Llama 3.3 70B**: 97.6% screening, 3 consistent wrong-state failures on
  ACCESSIONING validation, 43GB memory, 40s/step latency
- **Qwen3 32B local**: 98.5% screening but 44s/step — same speed as the 70B
  at lower accuracy. Q5 quantization made results worse.
- **Qwen3 32B cloud**: 99.1% screening, excellent accumulated state (8/10).
  Best overall if cloud deployment were acceptable, but the project requires
  local models for PHI compliance.
- **Gemma 3 27B**: 89.2% screening — too many ACCESSIONING failures.
  Surprisingly strong on accumulated state (100% state) but poor skill
  adherence on structured checklists.

**Remaining known limitation**: SC-094 HER2 hallucination. The Coder 32B
fires ACC-006 on orders where HER2 is not in ordered_tests. This is a
model-level pattern-matching issue (fixation_time=5.0 triggers ACC-006
reflexively) that skill refinement has not resolved after 3 iterations. The
cloud Qwen3 32B handles it correctly, suggesting it may be a quantization
or architecture limitation. For production, this edge case (non-HER2 orders
with borderline fixation) would need monitoring.

## Runtime

| Segment | Duration |
|---------|----------|
| Coder 32B screening (3 runs) | 1h 59m |
| Coder 32B accumulated state (1 run) | 52m |
| Llama 70B screening (3 runs) | 3h 50m |
| Llama 70B accumulated state (1 run) | 1h 41m |
| Cloud models (all segments) | 58m |
| **Total overnight** | **9h 21m** |
| Skill refinement + retests | ~3h |
| Qwen3 32B local Q4+Q5 test | ~2h |
