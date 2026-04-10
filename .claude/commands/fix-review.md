Fix high and medium severity issues from code review for PR $ARGUMENTS.

## SETUP

```bash
# Find the review directory (diff file was saved by /review-pr)
ls -d code_reviews/PR$ARGUMENTS-* 2>/dev/null | head -1
```

The diff file is at `code_reviews/PR$ARGUMENTS-<title>/pr.diff` (saved by `/review-pr`).

## CHECK FOR COMMENTS
ONLY If requested, check for @claude comments:
```bash
gh api repos/{owner}/{repo}/pulls/$ARGUMENTS/comments --jq '.[] | select(.body | contains("@claude")) | {id, path, body: .body[:80]}'
```

## GATHER FINDINGS

Read `CONSOLIDATED-REVIEW.md` from the review directory. It contains the Issue Matrix with severity, scope, and actionability already determined.

Also add any @claude PR comments as High severity issues (record comment ID for later reply).

## BUILD ISSUE MATRIX

Before implementing fixes, create a matrix of ALL issues using format from `.claude/memories/review-issue-matrix.md`.

## CREATE TODO LIST

Use TodoWrite to track actionable issues:
- One todo per issue with severity prefix (e.g., "[High] Fix docstring")
- Mark deferred items separately

## IMPLEMENT

**Use Sequential Thinking MCP** when fixes have dependencies or require tracing through code:
- Call `mcp__sequential-thinking__sequentialthinking` to reason through complex fixes
- Identify if fixing one issue affects others
- Plan the order of fixes to avoid conflicts

For each issue (Critical > High > Medium):
1. Mark todo in_progress
2. Read the file before editing
3. Implement the fix
4. Mark todo completed
5. Reply to @claude comments if applicable:
   ```bash
   gh api repos/{owner}/{repo}/pulls/$ARGUMENTS/comments/{ID}/replies --method POST -f body="Fixed. [description]"
   ```

## VALIDATE AND COMMIT

```bash
uv run ruff format src/ tests/
uv run ruff check src/ tests/
git add <changed-files>
git commit -m "fix: Address code review findings"
git push
```

Note: The pre-commit hook runs `uv run pytest` automatically before committing.
The mypy hook checks edited files individually; for a full project check run `uv run mypy src/`.

## SIMPLIFICATION PASS

After all fixes are validated, launch the `code-simplifier` agent on the files modified during this fix round. The agent should:

1. Read only the files changed by fix commits (use `git diff --name-only HEAD~1`)
2. Look for complexity introduced by the fixes: unnecessary nesting, redundant guards, overly verbose patterns
3. Suggest simplifications that preserve behavior
4. Apply simplifications that are clearly safe (no semantic change)
5. Skip this step if the only changes were documentation or test files

If the simplifier makes changes, run validation again before committing:

```bash
uv run ruff format src/ tests/
uv run ruff check src/ tests/
git add <simplified-files>
git commit -m "refactor: Simplify code after review fixes"
git push
```

## HANDLE DEFERRED ITEMS

Skip if no deferred items or all are Low severity (auto-skip Low items).

For High/Medium deferred items, use AskUserQuestion with options:
- Fix now
- Add to existing issue (if related issue found)
- Create new issue
- Skip

**If "Create new issue"**: Create a GitHub issue with `gh issue create`.

## FINAL SUMMARY

Post to PR with:
- Issues Fixed table
- Deferred Items table (with decisions/outcomes)
- Validation results

```bash
gh pr comment $ARGUMENTS --body "$(cat <<'EOF'
## Code Review Fixes Applied
[summary tables]
EOF
)"
```

**Reminders:**
- Build complete matrix BEFORE implementing
- Reply to all @claude comments
- Create GitHub issues for deferred items as needed
