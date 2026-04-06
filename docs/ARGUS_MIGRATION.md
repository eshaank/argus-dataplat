# Argus Electron App — Migration Plan

> Strategy for connecting the existing Argus Electron app to DataPlat via MCP, then incrementally deleting the old domain services.

---

## Current State of Argus (`finance-dashboard/`)

~25K lines of TypeScript in an Electron + React + tRPC app:

| Layer | Status | Lines |
|-------|--------|-------|
| **Chat domain** (LLM orchestration, tools, streaming) | Most mature — tool registry, DuckDB caching, visualization | 3,648 |
| **Agent system** (Pi multi-agent, workspaces, job queue) | Functional | ~1,500 |
| **13 domain services** (pricing, financials, news, etc.) | Most will be replaced by DataPlat MCP tools | ~5,100 |
| **Frontend** (chat UI, settings, auth) | Built, basic | ~3,300 |
| **DuckDB session cache** | Working (per-conversation) | ~600 |
| **Electron shell** (IPC, forge, packaging) | Scaffolded | ~2,000 |

### Domain Services (candidates for deletion)

```
electron/domains/
├── chat/               ← KEEP (core LLM orchestration)
├── conversations/      ← KEEP (chat history CRUD)
├── settings/           ← KEEP (API key management)
├── company/            → replaced by query_universe MCP tool
├── corporate_actions/  → replaced by query_market_data MCP tool
├── economics/          → replaced by query_economics MCP tool
├── filings/            → replaced by query_financials MCP tool
├── financials/         → replaced by query_financials MCP tool
├── fred/               → replaced by query_economics MCP tool
├── news/               → KEEP (real-time, not worth storing)
├── pricing/            → replaced by query_market_data MCP tool
├── scanner/            → replaced by run_sql MCP tool
└── short_interest/     → replaced by query_alternative MCP tool
```

---

## Decision: Keep and Migrate, Don't Rewrite

**Don't start from scratch.** Rationale:

1. **The hard parts are already done.** Chat orchestration (tool-calling loop, streaming, LLM integration), agent system, DuckDB session cache, tRPC plumbing, and Electron shell are non-trivial infrastructure that works. Rewriting gives zero new capability.

2. **The parts that need to go are the easy parts.** The 13 domain services are thin API wrappers — exactly what DataPlat's MCP server replaces. Deleting them is easier than rewriting the chat system.

3. **The migration path is incremental.** Add MCP client alongside existing tools. Both paths work simultaneously. Migrate one domain at a time. Delete old code when parity is confirmed. No big-bang cutover.

---

## Prerequisites (DataPlat side)

Before touching the Electron app, DataPlat needs an API to connect to:

- [x] ClickHouse schema + migrations
- [x] Polygon 1-min backfill pipeline
- [x] Schwab daily backfill pipeline
- [x] Materialized views (5-min, 15-min, hourly, daily)
- [ ] **Run full SPY backfill** (503 tickers, overnight)
- [ ] **Build MCP server** in DataPlat (the bridge between DataPlat and Argus)
- [ ] **MCP tools**: `query_market_data`, `query_universe`, `run_sql`, `get_schema`

The MCP server is the critical blocker. Without it, Argus has nothing to connect to.

### MCP Server Spec (DataPlat side)

Transport: Streamable HTTP on port `8811`.

Tools to implement:

| Tool | Description | Replaces Argus Domain |
|------|-------------|----------------------|
| `query_market_data` | OHLCV at any resolution (1min/5min/hourly/daily), date range, multi-ticker | `pricing` |
| `query_financials` | Income statements, balance sheets, cash flow | `financials`, `filings` |
| `query_economics` | FRED series data | `economics`, `fred` |
| `query_universe` | Ticker metadata, search, filter by sector/exchange | `company` |
| `query_options` | Option chains, greeks | (future) |
| `query_alternative` | Short interest, corporate actions | `short_interest`, `corporate_actions` |
| `run_sql` | Raw read-only SQL for complex analysis | `scanner` |
| `get_schema` | Table definitions and column types | (new) |

---

## Phase 1: Clean the Codebase

**Goal:** Get to a clean "it runs" state.

- [ ] Delete stale git branches
- [ ] Verify `npm run dev:electron` boots without errors
- [ ] Remove dead code, unused imports, commented-out blocks
- [ ] Ensure the chat UI can send a message and get a response
- [ ] Verify DuckDB session cache works (conversation persistence)
- [ ] Document what works and what's broken in a status report

**Do not change architecture.** Just clean and verify.

---

## Phase 2: Wire MCP Client

**Goal:** Argus can connect to DataPlat's MCP server and discover tools.

### 2.1 Add MCP Client to Electron

```
npm install @modelcontextprotocol/sdk
```

New file: `electron/mcp/client.ts`

```typescript
import { Client } from "@modelcontextprotocol/sdk/client";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp";

export async function createDataPlatClient(): Promise<Client> {
  const client = new Client({ name: "argus", version: "1.0.0" });
  const transport = new StreamableHTTPClientTransport(
    new URL("http://localhost:8811/mcp")
  );
  await client.connect(transport);
  return client;
}
```

### 2.2 Dynamic Tool Discovery

Instead of hardcoded tool definitions in `tool-defs.ts`, discover tools from the MCP server at startup:

```typescript
// On startup or reconnect
const tools = await mcpClient.listTools();
// Register each tool in the chat LLM's tool list
// Tool descriptions come from DataPlat — Argus doesn't define them
```

### 2.3 Add Connection Settings

- New setting: `DATAPLAT_MCP_URL` (default: `http://localhost:8811/mcp`)
- Connection status indicator in settings UI
- Graceful fallback: if MCP server is unavailable, existing domain services still work

### 2.4 Register MCP Tools Alongside Existing Tools

Both paths work simultaneously:
- LLM sees MCP tools (from DataPlat) AND existing domain tools (from Argus)
- User can use either — no functionality lost during migration
- This is the safety net that prevents breaking anything

---

## Phase 3: Migrate Domains (Incremental)

One domain at a time. For each:

1. Verify the MCP tool returns equivalent data
2. Remove the old domain service's tool registration from `tool-registry.ts`
3. Remove the domain's tRPC router from the root router
4. Delete the `electron/domains/{name}/` directory
5. Test: same LLM questions, same quality answers

### Migration Order (by impact and simplicity)

| Order | Domain | MCP Tool | Risk | Notes |
|-------|--------|----------|------|-------|
| 1 | `pricing` | `query_market_data` | Low | Most-used domain. MCP version has 5 years of 1-min data vs real-time API snapshots. Strictly better. |
| 2 | `fred` | `query_economics` | Low | Simple 1:1 mapping. |
| 3 | `economics` | `query_economics` | Low | Same MCP tool as fred. |
| 4 | `financials` | `query_financials` | Low | Direct replacement. |
| 5 | `filings` | `query_financials` | Low | Merges into same tool. |
| 6 | `company` | `query_universe` | Low | Ticker metadata lookup. |
| 7 | `corporate_actions` | `query_market_data` | Low | Merges into market data. |
| 8 | `short_interest` | `query_alternative` | Low | Direct replacement. |
| 9 | `scanner` | `run_sql` | Medium | Scanner has complex logic. `run_sql` is more flexible but LLM needs to write SQL. |
| 10 | `news` | — | Skip | Keep as-is. News is real-time, not worth storing in ClickHouse. Still hits Polygon API directly. |

### What Stays in Argus Forever

- `electron/domains/chat/` — LLM orchestration, tool-calling loop, streaming
- `electron/domains/conversations/` — chat history CRUD (SQLite)
- `electron/domains/settings/` — API key management, preferences
- `electron/domains/news/` — real-time news (direct Polygon API)
- `electron/agents/` — Pi agent system (agents use MCP tools like the LLM does)
- `electron/core/duckdb.ts` — per-conversation session cache (caches MCP query results)
- All frontend code
- Electron shell (IPC, window management, packaging)

---

## Phase 4: Polish

After all domains are migrated:

- [ ] Remove `MASSIVE_API_KEY` from Argus settings (Polygon calls now go through DataPlat)
- [ ] Remove unused dependencies (`httpx`, domain-specific types)
- [ ] Update tool-defs.ts to be purely MCP-discovered (no hardcoded tools)
- [ ] Add MCP connection health monitoring
- [ ] DuckDB cache: update session tables to match MCP response shapes
- [ ] Agent system: agents discover and use MCP tools automatically

---

## Timeline Estimate

| Phase | Effort | Depends On |
|-------|--------|------------|
| DataPlat: Full SPY backfill | Overnight run | ✅ Ready now |
| DataPlat: MCP server | 1-2 sessions | Backfill complete |
| Phase 1: Clean Argus | 1 session | Nothing |
| Phase 2: Wire MCP client | 1 session | MCP server running |
| Phase 3: Migrate domains | 1 domain per session, ~10 sessions total | Phase 2 |
| Phase 4: Polish | 1-2 sessions | Phase 3 |

**Critical path:** DataPlat MCP server → Phase 2 → Phase 3. Everything else is parallelizable.

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| MCP server is down | Graceful fallback to existing domain services (both registered simultaneously) |
| MCP tool returns different shape than old domain | DuckDB cache adapts — session tables are schema-flexible |
| LLM writes bad SQL via `run_sql` | Read-only enforcement, keyword blocking, row limit |
| Backfill data has gaps | `ReplacingMergeTree` allows safe re-ingestion. Re-run backfill for missing tickers. |
| Performance regression | ClickHouse queries are sub-second. Old domains hit live APIs with 200-500ms latency. MCP should be faster. |
