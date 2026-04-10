---
description: Merge a PR and clean up branches
allowed-tools: Bash(gh pr view:*),Bash(gh pr merge:*),Bash(git checkout:*),Bash(git pull:*),Bash(git push:*),Bash(git fetch:*),Bash(git branch:*),Bash(git add:*),Bash(git commit:*),Bash(markdownlint-cli2:*),Read,Edit,Grep
---

Merge PR $ARGUMENTS with automatic implementation-todo.md updates.

## Step 1: Resolve PR and linked issues

```bash
gh pr view $ARGUMENTS --json number,headRefName,closingIssuesReferences \
  -q '{number,branch: .headRefName, issues: [.closingIssuesReferences[].number]}'
```

Save the branch name and list of closing issue numbers.

## Step 2: Update implementation-todo.md

**If the PR closes one or more GitHub issues:**

1. Check out the PR's branch: `git checkout <branch>`
2. Read `docs/project/implementation-todo.md`
3. For each closing issue number, find the table row containing `GH-<number>`
   and change its Status column from `Open` to `Done` using the Edit tool.
   If a `GH-<number>` is not found in the file, skip it silently.
4. Run: `markdownlint-cli2 --fix "docs/project/implementation-todo.md"`
5. Commit and push:

```bash
git add docs/project/implementation-todo.md
git commit -m "docs: Mark GH-<numbers> as Done in implementation todo"
git push
```

**If the PR closes no issues**, skip this step entirely.

## Step 3: Merge and clean up

```bash
gh pr merge $ARGUMENTS --merge --delete-branch && git checkout main && git pull origin main && git fetch --prune origin
```

## Step 4: Report

Report:
- Which issues (if any) were marked Done in implementation-todo.md
- "PR #$ARGUMENTS merged. On branch main."
