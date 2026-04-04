---
description: Create a Playwright E2E test with explicit success criteria
argument-hint: <feature-or-page-name>
allowed-tools: Read, Write, Grep, Glob, Bash, AskUserQuestion
---

# Create E2E Test

Create a Playwright E2E test for: **$ARGUMENTS**

## ABSOLUTE RULES — Read Before Writing a Single Line

### 1. Every test MUST have explicit success criteria

"Page loads" is NOT a test. Every `test()` block MUST assert:
- **URL** — verify the page navigated to the correct URL
- **Visible elements** — verify key elements are present and visible
- **Correct data** — verify the right content is displayed (or loading/error state)
- **Error states** — verify error messages show when expected

```typescript
// CORRECT — explicit success criteria (finance dashboard example)
test('Research tab shows price chart after selecting ticker', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveURL(/\//);
  await page.getByRole('tab', { name: /Research/i }).click();
  await page.getByPlaceholder(/ticker|symbol/i).fill('AAPL');
  await page.getByRole('button', { name: /search|go/i }).click();

  await expect(page).toHaveURL(/research/);
  await expect(page.locator('[data-testid="price-chart"]')).toBeVisible();
  await expect(page.locator('text=AAPL')).toBeVisible();
});

// WRONG — this passes even when completely broken
test('Research tab loads', async ({ page }) => {
  await page.goto('/research');
  // no assertions!
});
```

### 2. A test is FINISHED when it has ALL of these

A test is NOT done until it has:
- [ ] At least one `await expect(page).toHaveURL()` assertion
- [ ] At least one `await expect(locator).toBeVisible()` assertion
- [ ] At least one content/data verification (`toContainText`, `toHaveValue`, etc.)
- [ ] Error case coverage where relevant (e.g. invalid ticker, API error)
- [ ] No `// TODO` or placeholder assertions

If you cannot check ALL of these, the test is incomplete. Say so and explain what's missing.

### 3. Test structure — ALWAYS follow this pattern

```typescript
import { test, expect } from '@playwright/test';

test.describe('[Feature Name]', () => {
  test.describe('happy path', () => {
    test('should [specific behavior] when [specific condition]', async ({ page }) => {
      // ARRANGE — navigate, set up state
      // ACT — perform the user action
      // ASSERT — verify SPECIFIC outcomes (URL, elements, data)
    });
  });

  test.describe('error handling', () => {
    test('should show error when [invalid input]', async ({ page }) => {
      // Test the failure mode
    });
  });

  test.describe('edge cases', () => {
    test('should handle [empty state / loading / etc]', async ({ page }) => {
      // Test boundaries
    });
  });
});
```

### 4. Port configuration

This project runs frontend and backend separately:

| Service   | Port | Base URL              |
|-----------|------|------------------------|
| Frontend  | 5173 | http://localhost:5173  |
| Backend   | 8000 | http://localhost:8000  |

Set `baseURL: 'http://localhost:5173'` in `playwright.config.ts` (or equivalent). The frontend calls the backend via `VITE_API_BASE_URL`; for E2E, ensure the backend is running on 8000 or use a test double.

Use relative paths for frontend routes:

```typescript
// CORRECT — uses baseURL from config
await page.goto('/');

// WRONG — hardcoded URL (unless you need a specific origin)
await page.goto('http://localhost:5173/research');
```

### 5. What to test for this project

**For a tab/page (Overview, Scanner, Research):**
- URL or tab state after navigation
- Page title or heading present
- Key UI elements visible (nav tabs, main content area)
- Data loaded and displayed (e.g. market indices, scanner table, price chart) or loading/error state
- Links/tabs navigate correctly

**For Research tab (ticker flow):**
- Ticker input and search trigger correct URL/state
- Price chart (or placeholder) visible for valid ticker
- Company details section shows expected data or loading state
- Timeframe buttons update chart (if applicable)
- Invalid or empty ticker shows appropriate message or state

**For API (if testing backend directly):**
- Correct response status code
- Response body matches expected shape (Pydantic schema)
- Error responses have proper status codes and messages

### 6. Naming convention

File: `tests/e2e/[feature-name].spec.ts`

Examples for this project:
- `tests/e2e/overview.spec.ts`
- `tests/e2e/scanner.spec.ts`
- `tests/e2e/research-ticker.spec.ts`
- `tests/e2e/nav-tabs.spec.ts`

## Step 0 — Auto-Branch (if on main)

Before creating any files, check the current branch:

```bash
git branch --show-current
```

- If on `main` or `master`: create a feature branch and switch to it:
  ```bash
  git checkout -b test/<feature-name>
  ```
  Report: "Created branch `test/<feature>` — main stays untouched."
- If already on a feature branch: proceed
- If not a git repo: skip this check

## Step 1 — Gather Information

Before writing the test:

1. **Read the source code** for the feature/page being tested (e.g. `frontend/src/components/`, routing in `DashboardLayout`)
2. **Identify all assertions** — what URLs, elements, and data should be verified?
3. **Identify error states** — invalid ticker, API down, empty state
4. **Check** — does the test need the backend running, or can it run against mock/preview?

## Step 2 — Ask What to Verify (if not obvious)

If the feature has multiple possible success criteria, ask the user:

- "What specific elements should be visible on this page?"
- "What data should be displayed after selecting a ticker?"
- "What error message should appear for an invalid ticker?"

## Step 3 — Write the Test

Create the test file at `tests/e2e/[feature-name].spec.ts` following ALL rules above.

Every test file MUST include:
1. At least one happy-path test
2. At least one error or edge-case test
3. Explicit assertions in every `test()` block

## Step 4 — Verification Checklist

After writing, verify:

- [ ] File is at `tests/e2e/[name].spec.ts`
- [ ] Every `test()` has at least 3 assertions (URL, element, data)
- [ ] Error or edge cases are covered
- [ ] No hardcoded ports (uses baseURL from config)
- [ ] No `// TODO` placeholders
- [ ] Test names describe behavior: "should [verb] when [condition]"
- [ ] No `any` types
- [ ] No `.only` left in the code

## Running Tests

Ensure backend is running (for tests that hit the API):
```bash
cd backend && uv run uvicorn app.main:app --reload
```

Then run Playwright (from project root or frontend, depending on where playwright.config is):
```bash
# Run all E2E tests
npx playwright test

# Run a specific file
npx playwright test tests/e2e/research-ticker.spec.ts

# Run with UI (debug)
npx playwright test --ui

# Run headed (see browser)
npx playwright test --headed

# Show last report
npx playwright show-report
```

If the project uses npm scripts (e.g. in root or frontend `package.json`), use those instead (e.g. `npm run test:e2e`).
