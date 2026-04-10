---
allowed-tools: Bash(gh issue view:*),Bash(gh issue list:*),Bash(git checkout:*),Bash(git branch:*),Bash(git push:*)
description: Analyze and fix a GitHub issue
---

Analyze and fix GitHub issue: $ARGUMENTS

## 1. IDENTIFY & APPROVE

**Required before ANY work:**
1. Find issue:
   - "next": `gh issue list --state open --sort created`
   - Number: `gh issue view $ARGUMENTS`
2. **Use AskUserQuestion** for approval (GitHub #, title, description)
3. Only proceed after explicit "Yes"

## 2. PLAN

**Use Sequential Thinking MCP** for complex issues to break down the problem:
- Call `mcp__sequential-thinking__sequentialthinking` to reason through the approach
- Identify dependencies, affected files, and potential risks
- Revise thinking as you explore the codebase

1. `gh issue view` for full details
2. For complex issues, launch **Explore agent** (quick):
   - Search for similar patterns in source code
3. Break into tasks with **TodoWrite**

## 3. CREATE

1. Create branch: `feature/issue-{number}-{desc}` or `fix/issue-{number}-{desc}`
2. Implement in small steps, commit after each
3. All commits go to the feature branch — never commit to main

## 4. TEST

1. Write positive + negative tests
2. Run tests: `uv run pytest` (also enforced by pre-commit hook)
3. Format/lint code: `uv run ruff format src/ tests/ && uv run ruff check src/ tests/ --fix`
4. Format/lint docs: `markdownlint-cli2 --fix "**/*.md"`
5. Type check: `uv run mypy src/` (per-file checks run automatically via hook; full project check is manual)
6. All functions need type annotations

## 5. PUSH & PR

1. Push: `git push -u origin {branch}`
2. Create PR: `gh pr create` with title `{feat|fix}: description`, body includes `Closes #{github_issue_number}`

Note: Code review happens via `/review-pr` after PR creation.
