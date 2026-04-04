---
name: duckdb-data-layer
description: DuckDB session data layer — per-conversation caching, schema design, query_data tool, and conversation persistence. Use when modifying the data cache, adding new session tables, or working on the query_data tool. This is the Argus EDGE CACHE (TypeScript/Electron), NOT the central analytical store. For ClickHouse / the central data platform, use the dataplat skill instead.
---

# DuckDB Data Layer

## Key Files
- `electron/core/duckdb.ts` — SessionDbManager (ephemeral → on-disk lifecycle)
- `electron/domains/chat/data-cache.ts` (600 lines) — Tool result caching + session tables
- `electron/domains/conversations/service.ts` — SQLite conversation CRUD
- `electron/domains/conversations/router.ts` — tRPC router for conversations

## Architecture

### SessionDbManager (electron/core/duckdb.ts)
- Starts **ephemeral** (in-memory) for new chats
- Migrates to **on-disk** when conversationId assigned (via `migrateEphemeralToConversation()`)
- On-disk path: `{userData}/duckdb/{conversationId}.duckdb`
- API: `openEphemeral()`, `openForConversation(id)`, `migrateEphemeralToConversation(id)`, `getActiveDb()`, `closeActive()`, `deleteConversationDb(id)`
- Migration: exports each table's data via INSERT statements, handles schema differences

### Session Schema (18 tables in data-cache.ts)
Every table has `_tool_call_id VARCHAR` and `_fetched_at TIMESTAMP DEFAULT current_timestamp`:

| Table | Key Columns | Source Tool |
|-------|------------|-------------|
| session_quotes | ticker, last, change, change_percent, volume, market_cap, pe_ratio | get_quote |
| session_price_history | ticker, date, open, high, low, close, volume | get_price_chart |
| session_income_statements | ticker, period_end, fiscal_year, revenue, net_income, eps, ebitda | get_income_statement |
| session_balance_sheets | ticker, period_end, total_assets, total_liabilities, total_equity | get_balance_sheet |
| session_cash_flows | ticker, period_end, net_cash_from_operating, capex, free_cash_flow | get_cash_flow |
| session_ratios | ticker, date, pe_ratio, pb_ratio, roe, debt_to_equity, ev_to_ebitda | get_ratios |
| session_company_profiles | ticker, name, sector, total_employees, market_cap | get_company_profile |
| session_news | id, title, published_utc, tickers, description | get_company_news, get_market_news |
| session_economic_indicators | id, indicator, country, actual, forecast, date | get_economic_indicators |
| session_upcoming_events | id, name, datetime, priority, category | get_upcoming_events |
| session_dividends | ticker, ex_date, amount, frequency | get_dividends |
| session_splits | ticker, execution_date, split_from, split_to | get_splits |
| session_ipos | ticker, issuer_name, share_price, listing_date, status | get_ipos |
| session_sec_filings | ticker, filing_type, filing_date, description, link | get_sec_filings |
| session_short_interest | ticker, date, short_interest, days_to_cover | get_short_interest |
| session_short_volume | ticker, date, short_volume, total_volume | get_short_volume |
| session_float | ticker, shares_outstanding, float_shares | get_float |
| session_tool_results | tool_call_id, tool_name, domain, ticker, row_count | (metadata) |

### Caching Pattern (data-cache.ts)
- `TOOL_CACHE_MAP`: maps tool names → cache function + table name
- `cacheToolResult(toolName, toolCallId, result)`: fire-and-forget, errors logged not thrown
- `parseResult()`: handles JSON string, `{count, rows}` envelope, raw array, single object
- Safe type conversions: `safeNum()`, `safeInt()`, `safeStr()`
- Per-tool functions: `cacheQuotes()`, `cachePriceHistory()`, etc.

### query_data Tool
- Read-only SQL on session_* tables (DuckDB dialect)
- SQL validation: must start with SELECT or WITH, rejects mutating keywords (INSERT, DELETE, UPDATE, DROP, CREATE, etc.)
- Word-boundary check: column names like "updated_at" do NOT trigger guard
- Caps results to 50 rows
- Supports CTEs, window functions, aggregations, cross-table joins

### getSessionContext()
- Returns formatted summary of cached data for system prompt injection
- Format: `## Cached Session Data` with tool call metadata
- Returns empty string when no data cached

### Conversation Persistence (SQLite via better-sqlite3)
- `electron/domains/conversations/service.ts` — CRUD operations
- Tables: conversations, messages (with tool_activity JSON), artifacts
- All user-scoped (WHERE user_id = ?)
- Auto-title from first user message (80 chars, word boundary)
- On delete: also cleans up DuckDB file + workspace (fire-and-forget)

## Adding a New Session Table
1. Add table definition in `data-cache.ts` schema creation
2. Add cache function (e.g., `cacheMyData()`) with safe type conversions
3. Add entry in `TOOL_CACHE_MAP` mapping tool name → cache function
4. Add corresponding tool in `tool-defs.ts` and `tool-registry.ts`
5. Test: verify round-trip (cache → query_data SELECT → compare)

## Common Pitfalls
- DuckDB caching is fire-and-forget — NEVER await or check for errors
- Always use safe type conversions (safeNum, safeStr) — API data is unpredictable
- Migration from ephemeral to on-disk happens once per conversation — don't call twice
- SQL validation uses word boundaries — `updated_at` is safe, `UPDATE` is not
- Session tables are conversation-scoped — data resets when switching conversations
