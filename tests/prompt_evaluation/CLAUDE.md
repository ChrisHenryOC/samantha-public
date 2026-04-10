# Prompt Evaluation

This folder contains rendered prompts from the evaluation harness for manual
testing with Claude Code or Cowork. The goal is to evaluate how Claude responds
to specific routing prompts without incurring OpenRouter API costs.

## How to use

### Generate a prompt

```bash
uv run python -m tests.prompt_evaluation.generate_prompt SC-070 13 > tests/prompt_evaluation/cases/sc070_step13.md
```

### Evaluate with Claude Code or Cowork

Open a case file from `cases/`. Each file contains:

1. **Metadata** — scenario ID, description, current state, current flags
2. **Expected output** — the ground truth answer
3. **Full prompt** — the exact prompt the model receives during evaluation

To evaluate: copy the "Full Prompt" section and submit it to Claude. Compare
the model's JSON response against the expected output.

### What to look for

- Does the model pick the correct `next_state`?
- Does it identify the right `applied_rules`?
- Does it add/remove flags correctly?
- If the model disagrees with the expected output, is the model wrong or is the
  ground truth wrong?

## Known issues under investigation

### Issue #4: SP-001 state ambiguity at processing_complete (step 3)

Rule SP-001 says "Advance to next sample prep step" but doesn't name the
specific target state. The model must infer `SAMPLE_PREP_PROCESSING` goes to
`SAMPLE_PREP_EMBEDDING` from context, but often skips ahead to
`SAMPLE_PREP_QC` or `SAMPLE_PREP_SECTIONING`.

**Test case**: `cases/sc020_step3_processing_complete.md`

### Issue #5: MISSING_INFO_PROCEED flag not propagated in ground truth (FIXED)

Fixed in PR #114. The 9 scenarios now correctly propagate
`MISSING_INFO_PROCEED` through all intermediate steps.

**Test case**: `cases/sc070_step13_resulting_review.md`
