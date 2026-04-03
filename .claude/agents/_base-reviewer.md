# Base Reviewer Template

This file contains shared context for all reviewer agents. Individual agents extend this with their specialty focus.

## Project Context

- **Project**: Lab Workflow LLM Prediction POC (Python)
- **Components**: RAG pipeline, rule catalog, prediction engine, evaluation harness, model adapters
- **Domain**: Breast cancer histology lab workflow routing
- **Standards**: Type hints required, ruff linting, pytest testing, dataclasses preferred
- **Key constraint**: The model is a workflow traffic cop, not a diagnostician

## Review Process

1. Read `code_reviews/PR{NUMBER}-{title}/pr.diff` using the Read tool
2. Focus on changed lines (+ lines in diff)
3. Flag issues only in new/modified code unless critical
4. Write findings to `code_reviews/PR{NUMBER}-{title}/{agent-name}.md`
5. Your output files must follow project markdown conventions: every fenced code block must have a language identifier (use `text` when not a specific language)

## Output Format

```markdown
# {Agent Name} Review for PR #{NUMBER}

## Summary
[2-3 sentences]

## Findings

### Critical
[Security vulnerabilities, data loss, breaking changes, incorrect workflow logic]

### High
[Performance >10% impact, missing critical tests, logic errors]

### Medium
[Code quality affecting maintainability]

### Low
[Minor suggestions - usually skip]
```

Each finding: **Issue** - `file.py:line` - Recommendation - Confidence: N/100

### Strengths

\[Notable positive patterns observed in the changes\]

## Confidence Scoring

Rate each finding 0–100:

- **91–100**: Critical bug, security flaw, or explicit project standard violation
- **76–90**: Important issue that clearly needs attention
- **51–75**: Valid concern but low impact or subjective
- **26–50**: Minor nitpick, not backed by project standards
- **0–25**: Likely false positive or pre-existing issue

**Only report findings with confidence >= 76.** If you are uncertain, err on the side of not reporting. Include the confidence score with each finding.

## Severity Definitions

- **Critical**: Security vulnerabilities, data loss, incorrect workflow state transitions, rule catalog inconsistencies, breaking changes
- **High**: Performance bottlenecks >10%, missing tests for new code, logic errors, incorrect ground truth in scenarios
- **Medium**: Code quality issues affecting maintainability
- **Low**: Minor suggestions (typically skip)
