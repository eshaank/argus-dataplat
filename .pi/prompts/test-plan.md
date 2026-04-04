---
description: Generate a structured test plan for a feature
argument-hint: <feature-name>
---

# Test Plan Generator

Create a structured test plan for: **$ARGUMENTS**

## Auto-Branch (if on main)

Before creating test plan files, check the current branch:

```bash
git branch --show-current
```

- If on `main` or `master`: create a feature branch and switch to it:
  ```bash
  git checkout -b test/<feature-name>-plan
  ```
  Report: "Created branch `test/<feature>-plan` — main stays untouched."
- If already on a feature branch: proceed
- If not a git repo: skip this check

## Template

Generate the following markdown document:

```markdown
# [Feature] Test Plan

**Created:** [today's date]
**Feature:** $ARGUMENTS
**Status:** Not Started

---

## Quick Status

Feature Area A:    NOT TESTED
Feature Area B:    NOT TESTED
Feature Area C:    NOT TESTED

---

## Prerequisites

- [ ] Application running (check relevant services)
- [ ] Environment variables configured (`.env`)

---

## Test 1: [Happy Path]

### 1.1 [Core scenario]

**Action:** [What to do]
**Expected:** [What should happen — be SPECIFIC]

| Check | Expected | Actual | Status |
|-------|----------|--------|--------|
| Response code / URL | 200 or correct route | | |
| Data returned | [specific shape or visible content] | | |
| UI updated | [specific change] | | |

---

## Test 2: [Error Cases]

### 2.1 [Invalid input]

**Action:** [What to do]
**Expected:** [Specific error message/behavior]

---

## Test 3: [Edge Cases]

### 3.1 [Empty state]
### 3.2 [Loading state]
### 3.3 [Boundary values]

---

## Pass/Fail Criteria

| Criteria | Pass | Fail |
|----------|------|------|
| All happy paths work | Yes | Any failure |
| Error messages shown | Yes | Silent failure |
| Data consistency | Yes | Stale or wrong data |

---

## How to Run Tests

- **Unit tests:** Detect and list the project's test runner commands
- **E2E tests:** List E2E framework commands if configured
```

Save to `tests/plans/[feature-name]-test-plan.md`
