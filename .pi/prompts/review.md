---
description: Review code for bugs, security issues, and best practices
allowed-tools: Read, Grep, Glob, Bash(git diff:*)
---

# Code Review

Review the current changes for quality, security, and correctness.

## Branch Check

Verify the current branch context:

```bash
git branch --show-current
```

- If on `main` or `master`: warn — "You're reviewing changes directly on main. Next time, start work on a feature branch."
- Report which branch is being reviewed in the output header
- Review is read-only so no auto-branch is created

## Context
- Current diff: !`git diff HEAD`
- Staged changes: !`git diff --cached`

## Review Checklist

### Cross-cutting
1. **Security** — OWASP Top 10, no secrets in code, proper input validation
2. **Error Handling** — No swallowed errors, proper logging, user-friendly messages
3. **Testing** — New code has tests where appropriate, tests have explicit assertions

### Language-Specific

Detect the language(s) from changed files and apply relevant checks:

**TypeScript/JavaScript:**
- No `any` types, proper null handling
- Hook dependency arrays correct (React)
- No inline styles for layout

**Python:**
- Type hints on every function
- Pydantic models for API request/response bodies
- Async handlers for I/O operations
- No bare `except:`

**Go:**
- Error returns checked
- Context propagation
- Proper defer usage

**Rust:**
- No unwrap() in production paths
- Proper error handling with Result

## Output Format

For each issue found:
- **File**: path/to/file:line
- **Severity**: Critical | Warning | Info
- **Issue**: Description
- **Fix**: Suggested change
