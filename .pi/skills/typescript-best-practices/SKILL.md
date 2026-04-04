---
name: typescript-best-practices
description: >
  TypeScript coding standards, patterns, and conventions for the Argus project.
  Use this skill whenever writing or modifying any TypeScript code in the codebase —
  including tRPC routers, domain services, utilities, types, React components, hooks,
  or configuration files. Also trigger when reviewing TypeScript code, refactoring
  existing modules, creating new domain files, or setting up project configuration
  (tsconfig, linting, package.json). If the task involves writing TypeScript in any
  capacity, load this skill first. This applies to backend (Electron main process),
  frontend (React renderer), and shared packages.
---

# TypeScript Best Practices

This skill covers two layers: general TypeScript patterns that apply to any project,
followed by Argus-specific conventions. Both layers are mandatory — the general patterns
ensure code quality, and the Argus patterns ensure consistency across the codebase.

## General TypeScript Patterns

### Strict Mode — Non-Negotiable

Every `tsconfig.json` in the project must have `"strict": true`. This enables the full
suite of strict checks: `noImplicitAny`, `strictNullChecks`, `strictPropertyInitialization`,
`noImplicitReturns`, `noFallthroughCasesInSwitch`, and `useUnknownInCatchVariables`.

Why this matters: without strict mode, TypeScript silently allows `any` to leak through
parameters, catch blocks, and uninitialized properties. This defeats the purpose of using
TypeScript at all. The compiler is your safety net — keep it tight.

Additional flags to always enable:

```json
{
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,
    "forceConsistentCasingInFileNames": true,
    "isolatedModules": true,
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "target": "ES2022",
    "module": "ES2022"
  }
}
```

`noUncheckedIndexedAccess` is particularly important — it forces you to handle the case
where an array or object index might be `undefined`, which catches a very common class of
runtime errors.

### Type Design

**Prefer `interface` for object shapes, `type` for unions and intersections.**

```typescript
// Object shapes — use interface
interface CompanyDetails {
  ticker: string;
  name: string;
  marketCap: number;
  sector: string | null;
}

// Unions, intersections, mapped types — use type
type Timeframe = '1D' | '1W' | '1M' | '6M' | '12M' | '5Y' | 'Max';
type ApiResult<T> = { success: true; data: T } | { success: false; error: AppError };
```

**Never use `any`.** If the type is truly unknown, use `unknown` and narrow it. If you're
dealing with third-party data, validate it at the boundary with Zod and let the validated
type flow through the rest of the code.

```typescript
// Bad — any disables all type checking downstream
function parseResponse(data: any): CompanyDetails { ... }

// Good — validate at the boundary, type-safe from here on
const CompanyDetailsSchema = z.object({
  ticker: z.string(),
  name: z.string(),
  marketCap: z.number(),
  sector: z.string().nullable(),
});
type CompanyDetails = z.infer<typeof CompanyDetailsSchema>;

function parseResponse(data: unknown): CompanyDetails {
  return CompanyDetailsSchema.parse(data);
}
```

**Make impossible states unrepresentable.** Use discriminated unions to ensure the type
system enforces valid states:

```typescript
// Bad — what does it mean when status is 'error' but data is present?
interface JobState {
  status: 'queued' | 'running' | 'completed' | 'failed';
  data?: unknown;
  error?: string;
}

// Good — each state carries exactly the data it should
type JobState =
  | { status: 'queued' }
  | { status: 'running'; startedAt: Date }
  | { status: 'completed'; data: unknown; completedAt: Date }
  | { status: 'failed'; error: string; failedAt: Date };
```

**Use `satisfies` to validate object literals while preserving their narrow type:**

```typescript
const CACHE_TTLS = {
  pricing: 60,
  company: 300,
  economics: 600,
} satisfies Record<string, number>;
// Type is still { pricing: 60; company: 300; economics: 600 } — not Record<string, number>
```

### Error Handling

**Use typed error hierarchies, not raw `throw new Error()`.**

```typescript
class AppError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly statusCode: number = 500,
    public readonly details?: Record<string, unknown>,
  ) {
    super(message);
    this.name = this.constructor.name;
  }
}

class ExternalAPIError extends AppError {
  constructor(service: string, message: string, details?: Record<string, unknown>) {
    super(`${service}: ${message}`, 'EXTERNAL_API_ERROR', 502, details);
  }
}

class NotFoundError extends AppError {
  constructor(resource: string, id: string) {
    super(`${resource} '${id}' not found`, 'NOT_FOUND', 404);
  }
}
```

**In catch blocks, narrow the unknown error:**

```typescript
try {
  await fetchData();
} catch (err) {
  if (err instanceof AppError) {
    // Handle known error — has .code, .statusCode, .details
  } else if (err instanceof Error) {
    // Unexpected error — wrap it
    throw new AppError(err.message, 'UNEXPECTED_ERROR');
  } else {
    // Something truly weird was thrown
    throw new AppError(String(err), 'UNKNOWN_ERROR');
  }
}
```

**Consider the Result pattern for operations that are expected to fail:**

```typescript
type Result<T, E = AppError> =
  | { ok: true; value: T }
  | { ok: false; error: E };

async function fetchQuote(ticker: string): Promise<Result<SnapshotQuote>> {
  try {
    const data = await httpClient.get(`/quotes/${ticker}`);
    return { ok: true, value: QuoteSchema.parse(data) };
  } catch (err) {
    return { ok: false, error: new ExternalAPIError('Polygon', `Failed for ${ticker}`) };
  }
}
```

### Async Patterns

**Always use `async/await` over raw Promises.** The only exception is `Promise.all()` and
`Promise.allSettled()` for concurrent execution.

**Use `Promise.allSettled()` when partial failure is acceptable:**

```typescript
// Fetching quotes for multiple tickers — some may fail, and that's OK
const results = await Promise.allSettled(
  tickers.map(ticker => fetchQuote(ticker))
);

const successful = results
  .filter((r): r is PromiseFulfilledResult<SnapshotQuote> => r.status === 'fulfilled')
  .map(r => r.value);
```

**Never fire-and-forget an async function.** If you intentionally don't await something,
use `void` to signal intent:

```typescript
// Bad — unhandled promise, swallowed errors
cleanup();

// Good — explicit intent
void cleanup().catch(err => logger.error('Cleanup failed', err));
```

### Naming Conventions

- **Files:** `kebab-case.ts` — e.g., `http-client.ts`, `price-chart.ts`
- **Types/Interfaces:** `PascalCase` — e.g., `CompanyDetails`, `ApiResponse`
- **Functions/Variables:** `camelCase` — e.g., `fetchQuote`, `cacheTimeout`
- **Constants:** `SCREAMING_SNAKE_CASE` for true constants, `camelCase` for derived values
- **Zod schemas:** `PascalCase` suffixed with `Schema` — e.g., `CompanyDetailsSchema`
- **Enums:** Prefer string literal unions over `enum`. TypeScript enums have quirks around
  type erasure and reverse mapping that string unions avoid entirely.

### Imports

**Use explicit named imports.** Avoid `import *` except for well-known namespaces (d3, three).

```typescript
// Good
import { createHTTPServer } from '@trpc/server/adapters/standalone';
import { z } from 'zod';

// Acceptable for namespaced libraries
import * as d3 from 'd3';
```

**Group imports in order:** external packages, then internal packages (`@argus/*`), then
relative imports. Separate each group with a blank line.

### Functions

**Keep functions short and single-purpose.** If a function does more than one thing, split it.
The name should describe what it does — if you need "and" in the name, it's doing too much.

**Use early returns to avoid deep nesting:**

```typescript
// Bad
function getTimeframeParams(timeframe: Timeframe) {
  if (timeframe === '1D') {
    return { multiplier: 5, span: 'minute', from: subDays(now, 1) };
  } else {
    if (timeframe === '1W') {
      return { multiplier: 15, span: 'minute', from: subDays(now, 7) };
    } else {
      // ...more nesting
    }
  }
}

// Good
function getTimeframeParams(timeframe: Timeframe) {
  if (timeframe === '1D') return { multiplier: 5, span: 'minute', from: subDays(now, 1) };
  if (timeframe === '1W') return { multiplier: 15, span: 'minute', from: subDays(now, 7) };
  if (timeframe === '1M') return { multiplier: 1, span: 'hour', from: subMonths(now, 1) };
  // ...
  throw new ValidationError(`Unknown timeframe: ${timeframe}`);
}
```

**Prefer `const` arrow functions for pure helpers, `function` declarations for exports:**

```typescript
// Internal helper
const formatCurrency = (value: number): string =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value);

// Exported module function
export function calculateProfitMargin(revenue: number, cost: number): number {
  if (revenue === 0) throw new ValidationError('Revenue cannot be zero');
  return ((revenue - cost) / revenue) * 100;
}
```

---

## Argus-Specific Conventions

These patterns are specific to the Argus codebase and should be followed whenever working
on this project.

### Project Structure

```
finance-dashboard/
├── electron/           # Main process (tRPC server, IPC, domain logic)
│   ├── core/           # Shared infra (http-client, cache, errors, config)
│   ├── domains/        # Domain-driven modules
│   │   └── {domain}/
│   │       ├── router.ts    # tRPC router (endpoint definitions)
│   │       ├── service.ts   # Business logic
│   │       ├── client.ts    # External API calls
│   │       └── types.ts     # Domain-specific types (if not in shared)
│   ├── trpc/           # tRPC server setup
│   │   ├── index.ts    # Router init, procedures, middleware
│   │   ├── root.ts     # Merged root router, AppRouter type export
│   │   ├── context.ts  # Context factory
│   │   └── ipc-adapter.ts  # Electron IPC ↔ tRPC bridge
│   └── agents/         # Sandbox agent infrastructure
├── frontend/           # Renderer process (React + tRPC client)
│   └── src/
│       ├── lib/        # Client utilities (trpc client, supabase)
│       ├── hooks/      # React hooks
│       ├── components/ # UI components
│       ├── contexts/   # React contexts (auth, settings)
│       └── providers/  # Provider wrappers (tRPC, QueryClient)
└── shared/
    └── types/          # Shared TypeScript types (@argus/types)
```

### Domain Module Pattern

Every domain follows the same 4-file pattern. Consistency here is more important than
cleverness — when every domain looks the same, anyone (human or AI) can navigate instantly.

**router.ts** — tRPC endpoint definitions. Input validation via Zod. Calls service functions.
Keep these thin — they define the contract but delegate logic.

```typescript
import { z } from 'zod';
import { router, authedProcedure } from '../../trpc';
import { getPriceChart } from './service';
import { TimeframeSchema } from '@argus/types';

export const pricingRouter = router({
  getPriceChart: authedProcedure
    .input(z.object({
      ticker: z.string().min(1).max(10).toUpperCase(),
      timeframe: TimeframeSchema,
    }))
    .query(async ({ input }) => {
      return getPriceChart(input.ticker, input.timeframe);
    }),
});
```

**service.ts** — Business logic. Calls client.ts for external data, applies transformations,
caching, and validation. This is where domain knowledge lives.

**client.ts** — Raw external API calls using the shared HTTP client. Returns unvalidated
data. The service layer validates and transforms it.

**types.ts** — Domain-specific types that aren't shared across domains. For types used
by multiple domains or the frontend, put them in `@argus/types`.

### Zod for Runtime Validation

All external API responses must be validated with Zod at the boundary. The type system
protects you inside the app, but data from Polygon.io, FRED, Massive API, etc. can change
without warning. Zod catches malformed responses before they propagate.

```typescript
// In client.ts — validate what comes back from the API
const PolygonBarSchema = z.object({
  o: z.number(),  // open
  h: z.number(),  // high
  l: z.number(),  // low
  c: z.number(),  // close
  v: z.number(),  // volume
  t: z.number(),  // timestamp
});

export async function fetchCandles(ticker: string, params: CandleParams) {
  const raw = await httpClient.get(`/aggs/ticker/${ticker}/range/...`);
  return z.array(PolygonBarSchema).parse(raw.results);
}
```

### API Response Envelope

All tRPC responses wrap data in the standard envelope. The tRPC middleware handles this
automatically — individual procedures just return the data.

```typescript
interface ApiResponse<T> {
  data: T;
  meta: {
    timestamp: string;
    requestId: string;
  };
}
```

### Caching Convention

Use the shared `TTLCache` from `electron/core/cache.ts`. Standard TTLs:

- Price/quote data: 60 seconds
- Company details: 300 seconds (5 minutes)
- Economic data: 600 seconds (10 minutes)
- Static reference data: 3600 seconds (1 hour)

Cache at the service layer, not the client or router layer.

### Configuration

All secrets and configurable values come from environment variables loaded via `.env`.
Never import `process.env` directly — use the typed config singleton from `electron/core/config.ts`.

```typescript
// Bad
const apiKey = process.env.MASSIVE_API_KEY;

// Good
import { config } from '../core/config';
const apiKey = config.massiveApiKey;
```

### Package Manager

Use **npm** for everything: `npm install`, `npm run`, `npx`. Never use yarn, pnpm, or bun
commands. The lockfile is `package-lock.json`.

### Dependencies to Prefer

When you need a library, prefer these:

| Need | Use | Not |
|------|-----|-----|
| HTTP client | `ky` | axios, got, node-fetch |
| Validation | `zod` | joi, yup, io-ts |
| Date handling | `date-fns` | moment, dayjs, luxon |
| RPC | `tRPC` | REST endpoints, GraphQL |
| Data fetching (React) | `@tanstack/react-query` (via tRPC) | SWR, Apollo |
| Serialization | `superjson` | manual JSON transforms |
| Testing | `vitest` | jest, mocha |
| Linting | `eslint` + `@typescript-eslint` | tslint |

### Comments

Write code that doesn't need comments. Use descriptive names, small functions, and
clear types. Add comments only for:

- **Why** something is done a certain way (not what)
- Links to external documentation for non-obvious API behavior
- TODO/FIXME with a brief explanation

```typescript
// Good — explains why
// Polygon.io returns timestamps in milliseconds for US markets
// but seconds for crypto. We normalize to milliseconds.
const normalizedTs = ts < 1e12 ? ts * 1000 : ts;

// Bad — explains what (the code already says this)
// Convert ticker to uppercase
const upper = ticker.toUpperCase();
```

### Reference Files

For deeper guidance on specific topics, read these project docs:

- `project-docs/ARCHITECTURE.md` — System overview, data flow, tRPC + IPC structure
- `project-docs/DECISIONS.md` — ADRs explaining the "why" behind each choice
