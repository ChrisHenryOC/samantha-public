# Skill vs Baseline A/B Comparison Results

## Test Setup

**Model**: Llama 3.3 70B (Q4_K_M, llama.cpp)
**Scenario set**: Phase 1 screening set — 33 scenarios (111 steps), chosen
for maximum model differentiation
**Date**: 2026-03-25

| Run | Prompt Config | Scenarios | Runs |
|-----|--------------|-----------|------|
| 1 | `skills,retry_clarification` | 33 (111 steps) | 1 |
| 2 | `state_sequence,retry_clarification,few_shot` (Phase 3a winner) | 33 (111 steps) | 1 |
| 3 | `skills,retry_clarification` (variance check) | 5 (11 steps) | 3 |

## Summary

Skills is a strict improvement over the Phase 3a winner across all metrics,
with no regressions on any scenario.

| Metric | Skills | Few-Shot | Delta |
|--------|--------|----------|-------|
| Scenarios passed | **29/33** | 22/33 | **+7** |
| State accuracy | **99.1%** (110/111) | 96.4% (107/111) | **+2.7pp** |
| Rule accuracy | **96.4%** (107/111) | 89.2% (99/111) | **+7.2pp** |
| Flag accuracy | **100%** (111/111) | 100% (111/111) | — |
| Reliability (all correct) | **87.9%** | 66.7% | **+21.2pp** |
| Variance (5-scenario check) | **±0.0%** | ±0.0% (Phase 3a) | — |

## Per-Scenario Comparison

Skills passes every scenario that few-shot passes, plus 7 additional:

| Scenario | Skills | Few-Shot | What Skills Fixed |
|----------|--------|----------|-------------------|
| SC-012 | PASS | FAIL | Accessioning checklist |
| SC-013 | PASS | FAIL | Numeric threshold decomposition (5.0 < 6.0) |
| SC-038 | PASS | FAIL | Multi-step workflow with IHC |
| SC-045 | PASS | FAIL | Multi-step workflow with IHC |
| SC-087 | PASS | FAIL | Multi-rule multi-step |
| SC-110 | PASS | FAIL | Long-path hallucination scenario (12 steps) |
| SC-111 | PASS | FAIL | Long-path hallucination scenario (9 steps) |

## Shared Failures (4 scenarios)

Both approaches fail these 4 scenarios. All are ACCESSIONING multi-rule or
edge cases.

### SC-010: ACC-004 + ACC-005 (missed ACC-005)

- **Scenario**: Cytospin specimen with alcohol fixative, HER2 ordered
- **Expected**: DO_NOT_PROCESS with [ACC-004, ACC-005]
- **Skills predicted**: DO_NOT_PROCESS with [ACC-004] only
- **Root cause**: Model finds the invalid specimen type (ACC-004) but misses
  the non-formalin fixative check (ACC-005). State is correct because ACC-004
  alone is REJECT severity.
- **Fixable?**: Likely — ACC-005 check in the skill is concise. The model may
  be short-circuiting after finding one REJECT rule. Reinforcing "continue
  checking ALL rules even after finding a REJECT" in the skill could help.

### SC-081: ACC-001 + ACC-006 (missed ACC-006 → wrong state)

- **Scenario**: Missing patient name + fixation time 5.0h with HER2
- **Expected**: DO_NOT_PROCESS with [ACC-001, ACC-006]
- **Skills predicted**: MISSING_INFO_HOLD with [ACC-001] only
- **Root cause**: Model finds ACC-001 (HOLD severity) but misses ACC-006
  (REJECT severity). Because the missed rule has higher severity, the state
  is wrong. This is the same numeric comparison failure as SC-013, but in a
  multi-rule context — the model correctly handles ACC-006 in isolation
  (SC-013: 100%) but misses it when other rules also fire.
- **Fixable?**: Partially. The model handles SC-013 perfectly, suggesting the
  numeric decomposition works in isolation. In multi-rule contexts, the model
  may rush through the checklist. Adding emphasis like "CRITICAL: check
  ACC-006 even if other rules already matched" could help, but this is the
  hardest failure mode.

### SC-082: Multi-rule (5 defects, false positives)

- **Scenario**: 5 simultaneous defects (missing name, sex, invalid site,
  bad fixation, no billing)
- **Expected**: DO_NOT_PROCESS with [ACC-001, ACC-002, ACC-003, ACC-006, ACC-007]
- **Skills predicted**: DO_NOT_PROCESS with [ACC-001, ACC-002, ACC-003, ACC-004,
  ACC-007, ACC-009] — misses ACC-006, adds false positives ACC-004 and ACC-009
- **Root cause**: The model correctly identifies most rules but:
  - Misses ACC-006 (same numeric comparison issue as SC-081)
  - False-positives ACC-004 (specimen_type is "biopsy" which IS valid)
  - False-positives ACC-009 (fixation_time is 5.0, not null)
- **Fixable?**: The false positives suggest the model gets confused in
  high-defect scenarios. ACC-004 and ACC-009 skill text was already tightened
  in review fixes. ACC-006 remains the persistent gap.

### SC-109: LCIS diagnosis → HE-006 vs expected HE-007

- **Scenario**: 9-step path with lobular_carcinoma_in_situ diagnosis at
  pathologist H&E review
- **Expected**: IHC_STAINING with [HE-007] (suspicious/atypical)
- **Skills predicted**: IHC_STAINING with [HE-006] (DCIS)
- **Root cause**: LCIS is not in the rule catalog. The ground truth maps it
  to HE-007 (suspicious/atypical). The model maps it to HE-006 (DCIS) since
  LCIS and DCIS are both carcinoma in situ. State is correct either way
  (both route to IHC_STAINING), but the rule citation is wrong.
- **Fixable?**: Yes — add LCIS to the pathologist_he_review skill explicitly
  mapped to HE-007 (suspicious/atypical), matching the ground truth.

## Failure Pattern Summary

| Root Cause | Scenarios | State Impact | Fixable? |
|------------|-----------|-------------|----------|
| ACC-006 missed in multi-rule context | SC-081, SC-082 | SC-081 wrong state | Partially — works in isolation, fails in multi-rule |
| ACC-005 missed alongside ACC-004 | SC-010 | State correct | Likely — reinforce "continue after REJECT" |
| ACC-004/ACC-009 false positives | SC-082 | State correct | Skill text already tightened |
| LCIS not in skill | SC-109 | State correct | Yes — add explicit mapping |

## Variance Check (Run 3)

5 scenarios (SC-003, SC-013, SC-019, SC-082, SC-103), 3 runs:

- State accuracy: **100% ±0.0%** across all 3 runs
- SC-082 fails consistently on rules (same false positive pattern)
- Zero variance confirms skills produce deterministic behavior

## Key Takeaways

1. **Skills is strictly better than few-shot** — 29/33 vs 22/33 scenarios,
   with zero regressions. Every metric improves.

2. **The numeric decomposition works in isolation but not in multi-rule
   contexts** — SC-013 (single defect with ACC-006) passes 100%, but SC-081
   and SC-082 (multiple defects including ACC-006) still miss it. The model
   appears to rush through the checklist when many rules fire.

3. **Flag carry-forward is now working** — 100% flag accuracy across all
   111 steps. The prompt instruction change ("carry forward existing flags
   AND add new ones") fully resolved the prior flag propagation issue.

4. **Hallucination scenarios largely pass** — 7 of 8 hallucination scenarios
   (SC-106 through SC-113) pass. SC-109 fails only on rule citation (LCIS
   mapping), not state.

5. **The remaining ceiling is multi-rule ACCESSIONING** — 3 of 4 failures
   involve the model missing rules when multiple defects are present
   simultaneously. This is the primary area for skill refinement.
