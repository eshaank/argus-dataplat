---
name: polymarket-api
description: Deep integration guide for Polymarket's CLOB API, Gamma API, and on-chain data. Use when building trading functionality, fetching market data, or implementing order execution.
---

# Polymarket API Integration Skill

## Overview

This skill provides comprehensive guidance for integrating with Polymarket's APIs and smart contracts within the Argus codebase. All code is TypeScript, running in Electron's main process.

## Existing Domain: `electron/domains/polymarket/`

Argus already has a polymarket domain with three files:

| File | Purpose |
|------|---------|
| `client.ts` | HTTP calls to Gamma API via `fetchWithRetry`, with TTL caching |
| `service.ts` | Schema mapping (`rawEventToSchema`, `rawMarketToSchema`), aggregation (`extractTrending`, `computeStats`) |
| `router.ts` | tRPC router with `getEvents`, `getEventBySlug`, `getStats` procedures |

Shared types live in `shared/types/polymarket.ts` (`PolymarketEvent`, `PolymarketMarket`, `PolymarketStats`, `CategoryBreakdown`, `PolymarketEventsResponse`).

The chat tool (`get_polymarket_events`) is currently **commented out** in `tool-defs.ts` and `tool-registry.ts`.

## API Endpoints

### CLOB API (Central Limit Order Book)
Base URL: `https://clob.polymarket.com`

#### Authentication Levels
- **Level 0 (Public)**: Market data, orderbooks, prices
- **Level 1 (Signer)**: Create/derive API keys
- **Level 2 (Authenticated)**: Trading, orders, positions

#### Key Endpoints
```
GET  /markets              # List all markets
GET  /markets/{token_id}   # Get specific market
GET  /price?token_id=X     # Get current price
GET  /midpoint?token_id=X  # Get midpoint price
GET  /book?token_id=X      # Get orderbook
GET  /trades               # Get user trades
POST /order                # Place order
DELETE /order/{id}         # Cancel order
GET  /positions            # Get positions
```

### Gamma API (Market Metadata)
Base URL: `https://gamma-api.polymarket.com`

This is the API the Argus polymarket domain currently uses.

```
GET /events              # List events (supports: active, closed, order, tag_slug, limit, offset)
GET /events?slug={slug}  # Get event by slug
GET /markets             # List markets
GET /markets/{id}        # Get market details
```

## Infrastructure (Argus Patterns)

All polymarket code uses the shared Argus infrastructure. Never import third-party HTTP libraries directly.

### HTTP Client

```typescript
import { fetchWithRetry } from '../../core/http-client';
// ky-based, 2 retries with exponential backoff, 10s timeout, jitter enabled
// Retries on: 408, 429, 500, 502, 503, 504
```

### TTL Cache

```typescript
import { TTLCache } from '../../core/cache';

// TTLCache<KeyType, ValueType>(ttlSeconds, maxSize)
const cache = new TTLCache<string, Record<string, unknown>[]>(120, 64);

// Usage:
const cached = cache.get(key);
if (cached) return cached;
// ... fetch data ...
cache.set(key, data);
```

### Error Handling

```typescript
import { ExternalAPIError, NotFoundError } from '../../core/errors';

// Wrap upstream failures:
throw new ExternalAPIError('Polymarket', 'Failed to fetch events', { status: 502 });

// Missing resources:
throw new NotFoundError('Event', slug);
```

### Validation

- **Inputs**: Zod schemas in router procedures
- **API responses**: Manual parsing with safe helpers (no Zod for external API responses)

### Types

```typescript
import type {
  PolymarketEvent,
  PolymarketMarket,
  PolymarketStats,
  CategoryBreakdown,
} from '@argus/types';
```

## TypeScript Implementation Patterns

### Client Layer (HTTP + Caching)

The client layer handles raw HTTP calls and caching. It returns `Record<string, unknown>` (untyped) — the service layer handles schema mapping.

```typescript
// electron/domains/polymarket/client.ts
import { fetchWithRetry } from '../../core/http-client';
import { TTLCache } from '../../core/cache';

const GAMMA_BASE_URL = 'https://gamma-api.polymarket.com';

const _events_cache = new TTLCache<string, Record<string, unknown>[]>(120, 64);
const _event_slug_cache = new TTLCache<string, Record<string, unknown>>(120, 128);

export async function fetchEvents(
  category?: string,
  limit = 50,
  offset = 0,
): Promise<Record<string, unknown>[]> {
  const cacheKey = `events:${category}:${limit}:${offset}`;
  const cached = _events_cache.get(cacheKey);
  if (cached) return cached;

  const searchParams: Record<string, string | number | boolean> = {
    limit,
    offset,
    active: 'true',
    closed: 'false',
    order: 'volume24hr',
    ascending: 'false',
  };

  if (category && category.toLowerCase() !== 'all') {
    searchParams.tag_slug = category.toLowerCase();
  }

  const response = await fetchWithRetry(`${GAMMA_BASE_URL}/events`, { searchParams });
  const data = await response.json();
  const results: Record<string, unknown>[] = Array.isArray(data) ? data : [];

  _events_cache.set(cacheKey, results);
  return results;
}

export async function fetchEventBySlug(
  slug: string,
): Promise<Record<string, unknown> | null> {
  const cacheKey = `slug:${slug}`;
  const cached = _event_slug_cache.get(cacheKey);
  if (cached) return cached;

  const response = await fetchWithRetry(`${GAMMA_BASE_URL}/events`, {
    searchParams: { slug },
  });
  const data = await response.json();
  const results: Record<string, unknown>[] = Array.isArray(data) ? data : [];

  if (results.length === 0) return null;
  _event_slug_cache.set(cacheKey, results[0]);
  return results[0];
}
```

### Service Layer (Schema Mapping + Aggregation)

The service layer converts raw API responses into typed `@argus/types` interfaces. It also handles business logic like trending extraction and stats computation.

```typescript
// electron/domains/polymarket/service.ts
import type { PolymarketMarket, PolymarketEvent, PolymarketStats } from '@argus/types';

function safeParseFloat(val: unknown, defaultVal = 0): number {
  if (val == null) return defaultVal;
  const num = Number(val);
  return isNaN(num) ? defaultVal : num;
}

export function rawMarketToSchema(raw: Record<string, unknown>): PolymarketMarket {
  return {
    id: String(raw.id ?? ''),
    question: (raw.question as string) ?? '',
    outcomes: parseOutcomes(raw.outcomes),
    outcome_prices: parsePrices(raw.outcomePrices),
    volume: safeParseFloat(raw.volume),
    liquidity: safeParseFloat(raw.liquidity),
    active: Boolean(raw.active ?? true),
    closed: Boolean(raw.closed ?? false),
    end_date: (raw.endDate as string) ?? null,
  };
}

export function rawEventToSchema(raw: Record<string, unknown>): PolymarketEvent {
  const rawMarkets = (raw.markets as Record<string, unknown>[]) ?? [];
  const markets = rawMarkets.map((m) => rawMarketToSchema(m));
  return {
    id: String(raw.id ?? ''),
    slug: (raw.slug as string) ?? '',
    title: (raw.title as string) ?? '',
    description: (raw.description as string) ?? null,
    category: extractCategory((raw.tags as Record<string, unknown>[]) ?? []),
    image: (raw.image as string) ?? null,
    volume: safeParseFloat(raw.volume),
    volume_24hr: safeParseFloat(raw.volume24hr),
    liquidity: safeParseFloat(raw.liquidity),
    open_interest: safeParseFloat(raw.openInterest),
    markets,
  };
}

export function extractTrending(events: PolymarketEvent[], count = 8): PolymarketEvent[] {
  return [...events].sort((a, b) => b.volume_24hr - a.volume_24hr).slice(0, count);
}

export function computeStats(events: PolymarketEvent[]): PolymarketStats {
  // Aggregates active_markets, total_volume_24hr, total_open_interest,
  // total_liquidity, and categories breakdown across all events
  // ...
}
```

### Router Layer (tRPC Procedures)

```typescript
// electron/domains/polymarket/router.ts
import { z } from 'zod';
import { router, authedProcedure } from '../../trpc';
import { NotFoundError } from '../../core/errors';
import { fetchEvents, fetchEventBySlug } from './client';
import { rawEventToSchema, extractTrending, computeStats } from './service';

export const polymarketRouter = router({
  getEvents: authedProcedure
    .input(z.object({
      category: z.string().optional(),
      limit: z.number().int().min(1).max(100).default(50),
    }))
    .query(async ({ input }) => {
      const rawEvents = await fetchEvents(input.category, input.limit);
      const events = rawEvents.map((e) => rawEventToSchema(e));
      const trending = extractTrending(events);
      return { events, trending, total: events.length };
    }),

  getEventBySlug: authedProcedure
    .input(z.object({ slug: z.string().min(1) }))
    .query(async ({ input }) => {
      const raw = await fetchEventBySlug(input.slug);
      if (!raw) throw new NotFoundError('Event', input.slug);
      return rawEventToSchema(raw);
    }),

  getStats: authedProcedure
    .input(z.object({}))
    .query(async () => {
      const rawEvents = await fetchEvents(undefined, 100);
      const events = rawEvents.map((e) => rawEventToSchema(e));
      return computeStats(events);
    }),
});
```

### Registering as a Chat Tool

The `get_polymarket_events` tool is currently commented out. To enable it:

**1. Uncomment in `electron/domains/chat/tool-defs.ts`:**

```typescript
tool(
  'get_polymarket_events',
  'Get prediction market events from Polymarket, optionally filtered by category. ' +
  'Returns: Array of {id, title, slug, volume, volume24hr, markets: [...], tags, startDate, endDate}.',
  {
    properties: {
      category: {
        type: 'string',
        description: 'Filter by category (politics, crypto, sports, culture, science)',
      },
      limit: {
        type: 'integer',
        description: 'Number of events to return (1-100, default 50)',
      },
    },
    required: [],
  },
),
```

**2. Uncomment in `electron/domains/chat/tool-registry.ts`:**

```typescript
// Import:
import { fetchEvents as fetchPolymarketEvents } from '../polymarket/client';

// In the tool domain map:
get_polymarket_events: 'polymarket',

// In the handler:
if (name === 'get_polymarket_events') {
  const category = optionalString(args, 'category');
  const limit = optionalNumber(args, 'limit', 50);
  const result = await fetchPolymarketEvents(category, limit);
  return storeAndSerializeList(result as unknown[], 15, context, toolCallId);
}
```

### Adding a CLOB API Client (If Trading Needed)

The current domain only uses the Gamma API (read-only market metadata). To add CLOB API support for orderbooks, prices, or trading:

```typescript
// electron/domains/polymarket/clob-client.ts
import { fetchWithRetry } from '../../core/http-client';
import { TTLCache } from '../../core/cache';
import { ExternalAPIError } from '../../core/errors';

const CLOB_BASE_URL = 'https://clob.polymarket.com';

const _orderbook_cache = new TTLCache<string, Record<string, unknown>>(30, 256);
const _price_cache = new TTLCache<string, number>(30, 512);

/**
 * Fetch current price for a token (Level 0 — no auth).
 */
export async function fetchPrice(tokenId: string): Promise<number> {
  const cached = _price_cache.get(tokenId);
  if (cached !== undefined) return cached;

  const response = await fetchWithRetry(`${CLOB_BASE_URL}/price`, {
    searchParams: { token_id: tokenId, side: 'buy' },
  });
  const data = (await response.json()) as { price: string };
  const price = parseFloat(data.price);

  if (isNaN(price)) {
    throw new ExternalAPIError('Polymarket CLOB', `Invalid price for token ${tokenId}`);
  }

  _price_cache.set(tokenId, price);
  return price;
}

/**
 * Fetch orderbook for a token (Level 0 — no auth).
 */
export async function fetchOrderbook(tokenId: string): Promise<Record<string, unknown>> {
  const cached = _orderbook_cache.get(tokenId);
  if (cached) return cached;

  const response = await fetchWithRetry(`${CLOB_BASE_URL}/book`, {
    searchParams: { token_id: tokenId },
  });
  const data = (await response.json()) as Record<string, unknown>;

  _orderbook_cache.set(tokenId, data);
  return data;
}

/**
 * Fetch midpoint price for a token (Level 0 — no auth).
 */
export async function fetchMidpoint(tokenId: string): Promise<number> {
  const response = await fetchWithRetry(`${CLOB_BASE_URL}/midpoint`, {
    searchParams: { token_id: tokenId },
  });
  const data = (await response.json()) as { mid: string };
  return parseFloat(data.mid);
}
```

### WebSocket Subscription (If Real-Time Updates Needed)

```typescript
// electron/domains/polymarket/ws-client.ts
import WebSocket from 'ws';

const WS_URL = 'wss://ws-subscriptions-clob.polymarket.com/ws/market';

interface MarketUpdate {
  event_type: string;
  market: string;
  price: number;
  timestamp: number;
}

export function subscribeMarketUpdates(
  tokenIds: string[],
  onUpdate: (update: MarketUpdate) => void,
  onError?: (err: Error) => void,
): () => void {
  const ws = new WebSocket(WS_URL);

  ws.on('open', () => {
    ws.send(JSON.stringify({
      type: 'subscribe',
      markets: tokenIds,
    }));
  });

  ws.on('message', (raw: Buffer) => {
    try {
      const data = JSON.parse(raw.toString()) as MarketUpdate;
      onUpdate(data);
    } catch (err) {
      onError?.(err instanceof Error ? err : new Error(String(err)));
    }
  });

  ws.on('error', (err) => onError?.(err));

  // Return cleanup function
  return () => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.close();
    }
  };
}
```

## Price Calculations

```typescript
/** Polymarket prices ARE probabilities (0 to 1). */
function impliedProbability(price: number): number {
  return price;
}

function calculateCost(price: number, shares: number): number {
  return price * shares;
}

function calculatePnl(
  entryPrice: number,
  currentPrice: number,
  shares: number,
  side: 'BUY' | 'SELL',
): number {
  return side === 'BUY'
    ? (currentPrice - entryPrice) * shares
    : (entryPrice - currentPrice) * shares;
}
```

## Order Types

- **GTC** (Good Till Cancelled): Stays until filled or cancelled
- **GTD** (Good Till Date): Expires at specified time
- **FOK** (Fill or Kill): Must fill entirely or cancel
- **IOC** (Immediate or Cancel): Fill what's available, cancel rest

## Rate Limits

- Public endpoints: ~100 requests/minute
- Authenticated endpoints: ~1000 requests/minute
- WebSocket: Varies by subscription type

The Argus `fetchWithRetry` client handles retries with exponential backoff automatically. For high-frequency polling, use `TTLCache` with short TTLs (30s for prices, 120s for events).

## Key Contract Addresses (Polygon)

```typescript
const POLYMARKET_CONTRACTS = {
  CTF_EXCHANGE: '0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E',
  NEG_RISK_CTF_EXCHANGE: '0xC5d563A36AE78145C45a50134d48A1215220f80a',
  CONDITIONAL_TOKENS: '0x4D97DCd97eC945f40cF65F87097ACe5EA0476045',
  USDC: '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174',
} as const;
```

## Checklist: Adding New Polymarket Features

1. Add HTTP functions to `client.ts` (use `fetchWithRetry` + `TTLCache`)
2. Add schema mapping to `service.ts` (return typed `@argus/types` interfaces)
3. Add tRPC procedures to `router.ts` (Zod input validation, `authedProcedure`)
4. Add shared types to `shared/types/polymarket.ts` if new shapes are needed
5. Register chat tools in `tool-defs.ts` (description) and `tool-registry.ts` (handler)
6. Router is already merged in `electron/trpc/root.ts` as `polymarket`
