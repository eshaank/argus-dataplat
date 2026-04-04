---
description: Smart commit with context — generates conventional commit message
allowed-tools: Bash(git add:*), Bash(git status:*), Bash(git commit:*), Bash(git diff:*)
argument-hint: [optional commit message override]
---

# Smart Commit

## Context
- Current git status: !`git status --short`
- Current diff: !`git diff HEAD --stat`
- Current branch: !`git branch --show-current`
- Recent commits: !`git log --oneline -5`

## Auto-Branch (if on main)

Before committing, check the current branch:

```bash
git branch --show-current
```

- If on `main` or `master`: create a feature branch from the staged changes context:
  ```bash
  git checkout -b feat/<scope-from-changes>
  ```
  Report: "Created branch `feat/<scope>` — committing there instead of main."
  Then proceed with the commit on the new branch.
- If already on a feature branch: proceed normally
- If not a git repo: skip this check

## Task

Review the staged changes and create a commit.

### Rules
1. Use **conventional commit** format: `type(scope): description`
   - Types: feat, fix, docs, style, refactor, test, chore, perf
   - Scope: e.g. frontend, backend, api, research-tab
2. Description should be concise but descriptive (max 72 chars)
3. If changes span multiple concerns, suggest splitting into multiple commits
4. NEVER commit .env files or secrets
5. Verify .gitignore includes .env before committing

### If message provided
Use this as the commit message: $ARGUMENTS

### If no message provided
Generate an appropriate commit message based on the diff.
