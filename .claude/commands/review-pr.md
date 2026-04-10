---
allowed-tools: Bash(gh pr comment:*),Bash(gh pr diff:*),Bash(gh pr view:*),Bash(mkdir:*),Bash(gh api:*),Bash(gh pr list:*)
description: Review a pull request
---

Review PR $ARGUMENTS (auto-detect from current branch if empty).

## Step 1: Setup

```bash
gh pr view $ARGUMENTS --json title,number -q '"\(.number) \(.title)"'
mkdir -p code_reviews/PR$ARGUMENTS-<sanitized-title>
gh pr diff $ARGUMENTS > code_reviews/PR$ARGUMENTS-<sanitized-title>/pr.diff
```

Directory name: PR number + lowercase title with non-alphanumeric replaced by hyphens.
The diff is saved to `code_reviews/PR{N}-{title}/pr.diff` for reuse by `/fix-review`.

## Step 2: Select and Launch Agents

### Aspect Filtering

If `$ARGUMENTS` includes aspect keywords after the PR number (e.g., `42 tests security`), only launch matching agents:

| Keyword | Agent |
|---------|-------|
| `quality` | code-quality-reviewer |
| `perf`, `performance` | performance-reviewer |
| `tests`, `testing` | test-coverage-reviewer |
| `docs`, `documentation` | documentation-accuracy-reviewer |
| `security`, `sec` | security-code-reviewer |
| `workflow`, `logic` | workflow-logic-reviewer |
| `errors`, `failures` | silent-failure-hunter |
| `types` | type-design-reviewer |
| `simplify` | code-simplifier |

### Auto-Detection (No Aspect Keywords)

If no aspect keywords are provided, auto-detect from the diff:

1. **Always run**: code-quality-reviewer, workflow-logic-reviewer, silent-failure-hunter
2. **If test files changed** (`tests/`): test-coverage-reviewer
3. **If docs changed** (`docs/`, `*.md`): documentation-accuracy-reviewer
4. **If model adapters, RAG, or evaluation code changed**: performance-reviewer
5. **If API keys, config, or data handling changed**: security-code-reviewer
6. **If dataclass or type definitions changed**: type-design-reviewer

When in doubt, include the agent — it costs less than missing a real issue.

### Launch

Launch selected agents in parallel. Each agent reads `code_reviews/PR$ARGUMENTS-<title>/pr.diff` and saves findings to `code_reviews/PR$ARGUMENTS-<title>/{agent}.md`.

## Step 3: Consolidate

After agents complete, create `PR$ARGUMENTS-CONSOLIDATED-REVIEW.md`.

### Deduplication Rules

Before building the Issue Matrix:

1. **Merge duplicates**: If two or more agents flag the same issue (same file, same line, same root cause), merge them into a single row. List all reporting agents in the Reviewer(s) column.
2. **Severity conflicts**: When agents disagree on severity, use the highest level.
3. **Complementary findings**: If agents flag the same location but for different reasons (e.g., security-code-reviewer flags an injection risk AND code-quality-reviewer flags missing validation), keep them as separate rows — they require different fixes.

### Output Format

```markdown
# Consolidated Review for PR #$ARGUMENTS

## Summary
[2-3 sentences]

## Issue Matrix
(Use format from `.claude/memories/review-issue-matrix.md`, with columns in the exact same order as in the template)

## Actionable Issues
[Issues where In PR Scope AND Actionable are Yes]

## Deferred Issues
[Issues where either is No, with reason]
```

## Step 4: Post Comment

```bash
gh pr comment $ARGUMENTS --body "[summary by severity]"
```

---

## Agent Instructions

Each agent:
1. Read `code_reviews/PR{NUMBER}-<title>/pr.diff` using the Read tool
2. Save findings to `code_reviews/PR{NUMBER}-<title>/{agent-name}.md` with:
   - Summary (2-3 sentences)
   - Findings by severity
   - File:line references
