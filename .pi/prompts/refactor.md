---
description: Refactor a file following all project best practices — split, type, extract, clean
argument-hint: <file-path> [--dry-run]
allowed-tools: Read, Write, Edit, Grep, Glob, Bash, AskUserQuestion
---

# Refactor — Best Practices Enforcement

Refactor the target file following every rule in this project's CLAUDE.md and the correct layer.

**Target:** $ARGUMENTS

If `--dry-run` is passed, report what WOULD change without modifying any files.

## Step 0 — Detect Layer and Auto-Branch

**Layer detection:** From the target file path and extension, determine which rules apply:
- `.ts`, `.tsx`, `.js`, `.jsx` → **Frontend (TypeScript/JavaScript)** — apply TypeScript and framework checks
- `.py` → **Backend (Python)** — apply Python checks
- `.go` → **Go** — apply Go checks
- `.rs` → **Rust** — apply Rust checks

Report: "Refactoring [language] file: <path>"

Before making any changes, check the current branch:

```bash
git branch --show-current
```

- If on `main` or `master`: create a feature branch and switch to it:
  ```bash
  git checkout -b refactor/<filename-without-extension>
  ```
  Report: "Created branch `refactor/<name>` — main stays untouched."
- If already on a feature branch: proceed
- If not a git repo: skip this check

## Step 0.5 — Read Before Touching

**NEVER refactor blind.** Read these files first:

1. The target file (fully — every line)
2. `CLAUDE.md` — project rules
3. Project architecture docs (if they exist)
4. Language config: `tsconfig.json`, `pyproject.toml`, `go.mod`, etc.

Also check what imports this file (blast radius):
- Search for the filename/module name across the project

Report: "This file is imported by X other files. Changes here affect: [list]"

## Step 1 — Audit the File

Run through EVERY check that applies to the detected language. For each violation, note line number, what's wrong, and the fix.

### 1A. File Size (Quality Gates)

- **> 300 lines = MUST split.** No exceptions.
- Identify logical sections that can become their own files
- Group by: types/schemas, constants, helpers, main logic, exports

### 1B. Function Size (Quality Gates)

- **> 50 lines = MUST extract.** No exceptions.
- Identify functions that do multiple things — each "thing" becomes its own function
- Name extracted functions by what they DO, not where they came from

### TypeScript/JavaScript

#### 1C. TypeScript Compliance
- If the file is `.js` or `.jsx` → **convert to `.ts` / `.tsx`**
- Find ALL `any` types → replace with proper types or `unknown`
- Check for missing return types on exported functions
- Check for missing parameter types
- Check for `@ts-ignore` or `@ts-expect-error` — remove if possible, document if necessary

#### 1D. Import Hygiene
- No barrel imports (`import * as everything from`)
- No circular imports (A imports B, B imports A)
- Types should use `import type { }` not `import { }`
- Unused imports → remove
- Sort: external packages first, then internal, then types

#### 1E. Error Handling
- No swallowed errors (`catch { return null }`)
- No empty catch blocks
- Errors must be logged with context; user-facing errors must have clear messages

#### 1F. Independent Awaits
- Sequential `await` calls that don't depend on each other → wrap in `Promise.all`

### Python

#### 1C. Type Hints
- Every function has type hints for all parameters and return type
- Use `list[...]`, `str | None` (Python 3.10+), not `List`, `Optional`

#### 1D. Async Consistency
- Handlers that do I/O use `async def`
- No blocking calls in async paths

#### 1E. Error Handling
- No bare `except:` or empty catch
- Errors logged with context

#### 1F. Lint
- Code should pass linting (ruff for Python, eslint for JS/TS)

### Cross-cutting

#### 1G. Security
- No hardcoded secrets, API keys, tokens
- Input validation on external/user data

#### 1H. Dead Code
- Unused functions → remove (don't comment out)
- Unused variables → remove
- Commented-out code blocks → remove (use git history)

## Step 2 — Plan the Refactor

Before changing ANYTHING, present the plan to the user. Use concrete line counts and file names. Include:
- File size and whether split is required
- If splitting: list of new files and what goes in each
- Function extractions (name, current line count, split into...)
- Type/lint fixes (per line or per item)
- Other fixes (awaits, errors, dead code)
- Blast radius (importers)

**WAIT for user approval before making any changes.**

Use named steps so the user can say "skip Step 3" or "change Step 2."

## Step 3 — Execute the Refactor

After approval, make changes in this order:

1. **Create new files first** (types/schemas, helpers, utilities)
2. **Move code** from the original file to new files
3. **Update imports** in the original and in all files that imported it
4. **Fix types/lint**
5. **Fix patterns** (Promise.all, error handling, dead code)

## Step 4 — Verify

After all changes:

- Run the project's linter/type checker
- No file exceeds 300 lines
- No function exceeds 50 lines

## Step 5 — Report

Summarize: file(s) created/modified, line counts before/after, fixes applied, and verification result.
