---
description: Git workflow rules — branch naming, conventional commits, PR discipline, rebase strategy
alwaysApply: true
---

# Git

## Branches
- Name branches as `ticket/description` — e.g. `TCL-1234/add-rate-limiting`
- Branch from `main` unless explicitly told otherwise

## Commits
- Use conventional commits: `fix:`, `feat:`, `refactor:`, `test:`, `docs:`, `chore:`
- Keep commits focused — one logical change per commit
- Don't push unless explicitly asked

## Pull Requests
- Keep PRs under ~500-800 lines when possible; one feature per PR
- PR title should match the conventional commit format
- Reference the Linear ticket in the PR body
- Don't merge — rebase onto main, then fast-forward merge

## Rebase
- Rebase onto main before merging — keep history linear
- Never force-push to `main` or shared branches
- Interactive rebase to clean up local commits before pushing is fine
- **Exception:** floating major tags on GitHub Actions repos require `git push -f` — see `rules/release-please.md`

## `.gitattributes`
- All repos should have a `.gitattributes` file marking generated files with `linguist-generated=true`
- When adding generated files (protobuf output, codegen, `.codemogger/`, etc.), add a matching pattern to `.gitattributes`
- Check `.gitattributes` when setting up a new repo or adding new codegen steps

## CI Gates
- Tests, lint, and typecheck must all pass before merge — no exceptions