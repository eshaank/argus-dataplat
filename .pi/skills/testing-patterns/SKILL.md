---
name: testing-patterns
description: Testing conventions for the Argus project — Vitest, React Testing Library, backend service tests. Use when writing tests, improving test coverage, or debugging test failures.
---

# Testing Patterns

## Config

- **Framework:** Vitest (not Jest)
- **Frontend config:** `frontend/vitest.config.ts` — jsdom, globals: true, setup: `./src/test/setup.ts`
- **Backend config:** `electron/vitest.config.ts` — node, timeout: 30s, pattern: `__tests__/**/*.test.ts`, alias `@argus/types`
- **Package manager:** npm (`npm run test`)

## Test File Locations

- Frontend: `frontend/src/components/**/__tests__/*.test.tsx`
- Backend: `electron/__tests__/*.test.ts`

## Running Tests

```bash
npm run test              # All tests
npx vitest run electron   # Backend only
npx vitest run frontend   # Frontend only
npx vitest --watch        # Watch mode
```

## Frontend Component Tests

- Use `render()` from `@testing-library/react`
- Query with `screen.getByText()`, `getByLabelText()`, `getByRole()`
- Use `vi.fn()` for mock callbacks
- Use `act()` for state updates triggered by events
- Use `vi.useFakeTimers()` for timer-dependent behavior
- Test DOM attributes directly: `iframe.getAttribute('sandbox')`
- For IPC-dependent components, mock `window.argus`

## Backend Service Tests

- Import functions directly, no HTTP layer
- For DuckDB tests: `initSessionDb()` in beforeAll, `closeSessionDb()` in afterAll, `resetSessionData()` in beforeEach
- Test happy path + error cases + edge cases
- For SQL validation: test both valid and invalid inputs, check word-boundary behavior
- For caching: verify data round-trips correctly (insert, query, compare)

## What to Mock (and What Not To)

**DO mock:** external HTTP calls (Polygon API, Together AI), IPC channels, `window.argus`

**Do NOT mock:** DuckDB (use real in-memory instances), domain service internals (test actual transform logic)

## Test Structure

```typescript
describe('FeatureName', () => {
  beforeAll(async () => { /* init resources */ });
  afterAll(async () => { /* cleanup */ });
  beforeEach(() => { /* reset state */ });

  it('should do X when Y', async () => {
    // Arrange
    // Act
    // Assert — use expect() with specific matchers
  });
});
```

## Assertion Style

- `expect(x).toBe(y)` — primitives
- `expect(x).toEqual(y)` — objects/arrays
- `expect(x).toContain(y)` — strings/arrays
- `expect(x).toBeGreaterThan(y)` — numbers
- `expect(x).toHaveBeenCalledWith(y)` — spies
- Every test MUST assert something meaningful — "page loads" is NOT a success criterion

## Existing Tests to Reference

| Test File | Type | Key Patterns |
|-----------|------|-------------|
| `Card.test.tsx` (23 lines) | Component | Simple render + className assertions |
| `ArtifactFrame.test.tsx` (372 lines) | Component | iframe sandbox, postMessage, height clamping, fake timers, `fireEvent` |
| `duckdb-session.test.ts` (807 lines) | Backend service | Singleton lifecycle, schema validation, data caching, SQL execution |
| `agent-duckdb.test.ts` (271 lines) | Integration | Summary format, SQL validation (word boundaries), context budget constants |
