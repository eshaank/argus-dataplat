---
name: chat-orchestration
description: Chat LLM orchestration, tool-calling loop, streaming, system prompt, tool registry, and artifact pipeline. Use when modifying chat behavior, adding tools, changing the system prompt, or working on the streaming pipeline.
---

# Chat Orchestration Skill

## Key Files

| File | Lines | Purpose |
|------|-------|---------|
| `electron/domains/chat/service.ts` | ~990 | Streaming tool-calling loop, retry logic, context budget |
| `electron/domains/chat/tool-defs.ts` | ~630 | 25+ tools in OpenAI function-calling format, TOOL_DOMAIN_MAP |
| `electron/domains/chat/tool-registry.ts` | ~405 | Tool dispatch, ToolCallContext, dual result storage |
| `electron/domains/chat/prompts.ts` | ~410 | System prompt construction with optional sections |
| `electron/domains/chat/data-cache.ts` | ~600 | DuckDB session caching, TOOL_CACHE_MAP, getSessionContext |
| `electron/domains/chat/visualization-handler.ts` | ~365 | Structured + generative artifact creation, data resolution |
| `electron/domains/chat/router.ts` | minimal | tRPC router (getModels only) |
| `electron/ipc/registry.ts` | ~491 | IPC channel handlers, persistence, concurrency guard |
| `shared/types/chat.ts` | ~73 | ChatMessage, ChatEvent, ToolActivity type definitions |

---

## Streaming Loop (`service.ts`)

The main entry point is `streamChat()`, which wraps `runStreamChat()` in a try/finally that always emits a `done` event. The loop never rejects -- errors are emitted as events.

### Flow

1. Resolve model from `ALLOWED_MODELS` (Qwen3.5-397B, Llama-3.3-70B, DeepSeek-V3, Kimi-K2.5, etc.)
2. Build messages: system prompt + user history, inject `getSessionContext()` from DuckDB cache
3. Tool-calling loop: up to `MAX_TOOL_ROUNDS` (5) rounds
   - Round 0: all tools sent via `asTogetherTools()`
   - Rounds 1-4: only tools from active domains via `getToolsForDomains(activeDomains)` -- artifact/data/agent tools always included
   - 2s delay between rounds (`INTER_ROUND_DELAY_MS`) for rate limit backoff
   - Context budget check each round: 100K chars with 20K headroom
4. Final text response: streamed with `tool_choice: 'none'` (when tools were called)

### Retry Logic

`withRetry()` handles 503 (GPU capacity) and 429 (rate limit) with exponential backoff: 5s, 10s, 20s, 40s. Maximum 4 retries. Emits `thinking` events with retry status so the UI can show progress.

### Tool Result Storage (Dual Map Pattern)

Every tool result is stored twice:
- **`toolResults`** -- parsed JSON, used for `create_visualization` data resolution
- **`fullToolResults`** -- same as toolResults (untruncated), preferred by visualization handler

The LLM sees a **truncated** version (max 1500 chars via `truncateForLLM()`). The truncation uses smart array reduction: halves item count until it fits, preserving JSON structure.

### Key Constants

```typescript
const MAX_TOOL_ROUNDS = 5;
const INTER_ROUND_DELAY_MS = 2_000;
const MAX_RETRIES = 4;
const MAX_TOOL_RESULT_CHARS = 1500;
const MAX_CONTEXT_CHARS = 100_000;
const CONTEXT_HEADROOM_CHARS = 20_000;
const MAX_TOOL_ROUND_TOKENS = 16384;
const MAX_FINAL_RESPONSE_TOKENS = 2048;
```

### Garbage Detection

Open models sometimes hallucinate tool-call XML (`<tool_call>`, `<arg_key>`, etc.) in text responses. `containsGarbage()` checks the last 300 chars against `GARBAGE_PATTERNS`. If detected, text is truncated at the first match, and a retry is attempted (up to `MAX_STREAM_RETRIES = 1`).

### Agent Break

When `run_research_agent` is called, the loop breaks immediately after that round. The agent's `summary` field is emitted as the final text response, skipping the redundant final API call.

---

## Tool Registry (`tool-registry.ts`)

### `executeTool(name, args, context?, toolCallId?)`

Central dispatch function. Uses an if-chain (not an object lookup) to route tool names to domain client functions via direct TypeScript imports (in-process, not IPC).

Returns a JSON string always. Domain clients return typed objects; `executeTool` serializes them with `bigintReplacer` and row-limits large datasets to `MAX_ROWS` (8).

### ToolCallContext

```typescript
interface ToolCallContext {
  emitEvent: (event: { type: string; data: unknown }) => void;
  conversationId?: string;
  toolResults: Map<string, unknown>;       // truncated for LLM
  fullToolResults: Map<string, unknown>;   // full for renderers
  toolCallMeta: Map<string, ToolCallMeta>; // name + args per tool_call_id
  messageId: string;
}
```

The context is passed to `create_visualization` and `create_generative_visualization` handlers so they can resolve data from prior tool calls by `tool_call_id`.

---

## Tool Definitions (`tool-defs.ts`)

### Format

OpenAI function-calling format. The `tool()` helper creates `{ type: 'function', function: { name, description, parameters } }`.

### TOOL_DOMAIN_MAP

Maps every tool name to a business domain string. Used for per-round pruning after round 0.

```typescript
const ALWAYS_INCLUDE_DOMAINS = new Set(['_artifact', '_data', '_agent']);
```

`getToolsForDomains(activeDomains)` returns only tools whose domain is in `activeDomains` or `ALWAYS_INCLUDE_DOMAINS`. If `activeDomains` is empty, returns all tools.

### Current Tools (25+)

- **pricing**: `get_price_chart`, `get_quote`
- **company**: `get_company_profile`, `get_index_constituents`
- **financials**: `get_balance_sheet`, `get_income_statement`, `get_cash_flow`, `get_ratios`
- **short_interest**: `get_short_interest`, `get_short_volume`, `get_float`
- **economics**: `get_economic_indicators`, `get_upcoming_events`
- **news**: `get_company_news`, `get_market_news`
- **corporate_actions**: `get_dividends`, `get_splits`, `get_upcoming_dividends`, `get_upcoming_splits`, `get_ipos`
- **filings**: `get_sec_filings`
- **scanner**: `run_screen`
- **_artifact**: `create_visualization`, `create_generative_visualization`
- **_data**: `query_data`
- **_agent**: `run_research_agent`

---

## System Prompt (`prompts.ts`)

### `buildSystemPrompt(forgeContext?, sessionContext?, hints?)`

Constructs the prompt from 6 optional sections:
1. **BASE_PROMPT** -- identity and capabilities (always included)
2. **GUIDELINES** -- behavioral rules including agent delegation pattern (always included)
3. **VISUALIZATION_RULES** -- artifact creation rules, type decision table (always included)
4. **query_data rules** -- SQL usage guidance (included when `sessionContext` is present)
5. **screener rules** -- `run_screen` usage patterns (included when scanner domain is active)
6. **forge iteration rules** -- rules for updating Forge artifacts (included when `forgeContext` is present)

### PromptHints

```typescript
interface PromptHints {
  hasToolResults?: boolean;
  activeDomains?: Set<string>;
}
```

Selectively omits sections when context makes them unnecessary.

### `buildDateContext()`

Injects current date and market-closed note (weekends, holidays).

---

## DuckDB Data Cache (`data-cache.ts`)

### Design

Fire-and-forget: `cacheToolResult()` is called with `void ... .catch()` in the tool loop. Errors are logged but **never propagate** to the caller or block the stream.

### TOOL_CACHE_MAP

Maps tool names to DuckDB session table names. 19 tools map to 18 tables (some share tables, e.g., `get_company_news` and `get_market_news` both go to `session_news`).

### Session Tables

`session_quotes`, `session_price_history`, `session_income_statements`, `session_balance_sheets`, `session_cash_flows`, `session_ratios`, `session_company_profiles`, `session_news`, `session_economic_indicators`, `session_upcoming_events`, `session_dividends`, `session_splits`, `session_ipos`, `session_sec_filings`, `session_short_interest`, `session_short_volume`, `session_float`, `session_tool_results` (metadata).

### Per-Tool Cache Functions

Each function uses safe type conversions (`safeNum`, `safeInt`, `safeStr`) and handles field name aliases (e.g., `consolidated_net_income_loss` vs `net_income`). Every row includes `_tool_call_id` for provenance tracking.

### `getSessionContext()`

Queries `session_tool_results` metadata table and builds a markdown summary injected into the system prompt. Tells the LLM which data is already cached and to use `query_data` instead of re-fetching.

---

## Visualization Pipeline (`visualization-handler.ts`)

### `handleCreateVisualization(args, context)`

1. Validates args via Zod (`CreateVisualizationSchema`)
2. Resolves data from `fullToolResults` (preferred) or `toolResults` by `data_source_tool_call_id`
3. Builds `ArtifactPayload` with `kind: 'structured'`
4. Emits `artifact_inline` or `artifact_forge` event
5. Returns confirmation string to the LLM

### `handleCreateGenerativeVisualization(args, context)`

1. Validates args via Zod (`CreateGenerativeVisualizationSchema`)
2. Validates JSX code via Sucrase transform (catches syntax errors before rendering)
3. Supports `data_source_tool_call_id: "all"` to merge all data tool results
4. Builds `ArtifactPayload` with `kind: 'generative'`

### Data Resolution (`resolveMultiSourceData`)

Three modes:
- **Single ID**: returns that tool's result directly
- **Array of IDs**: merges all results into flat array with `_source_tool` / `_source_ticker` tags
- **`"all"`**: merges ALL available data-tool results (excludes meta-tools via `EXCLUDED_FROM_ALL`)

Supports fuzzy/prefix matching for tool_call_ids since LLMs commonly hallucinate a few characters.

---

## IPC Streaming (`ipc/registry.ts`)

### Channels

- `argus:chat:stream` -- renderer invokes `streamChat` via `ipcMain.handle`
- `argus:chat:event` -- main process sends events to renderer via `webContents.send`
- `argus:agent:subscribe` / `argus:agent:event` / `argus:agent:cancel` -- agent streaming

### Concurrency Guard

`activeStreams` map tracks one stream per window (`webContents.id`). Second request while streaming returns `STREAM_ACTIVE` error.

### Auth

Extracts user ID from Supabase JWT `sub` claim. Dev mode falls back to `'dev-user'`.

### Persistence

On stream start: creates conversation if needed, saves user message, creates assistant placeholder. During stream: accumulates content, thinking, tool activities, and artifacts. On `done`: finalizes assistant message with full content.

---

## Adding a New Tool (Step by Step)

1. **`tool-defs.ts`**: Add tool definition using `tool()` helper. Write a description that says WHEN to use it. Include the `Returns:` field describing the response shape.
2. **`tool-defs.ts`**: Add entry in `TOOL_DOMAIN_MAP` mapping tool name to its domain string.
3. **`tool-registry.ts`**: Add an `else if` branch in `executeTool()` that calls the domain client function. Serialize the result with `JSON.stringify(data, bigintReplacer)`.
4. **`data-cache.ts`** (recommended): Add a `cache*` function, add entry in `TOOL_CACHE_MAP`, add `case` in the switch inside `cacheToolResult()`.
5. **Test**: Query the LLM with ambiguous prompts to verify it picks the right tool.

---

## Common Pitfalls

| Problem | Cause | Fix |
|---------|-------|-----|
| LLM picks wrong tool | Vague description | Rewrite description to say WHEN to use, not just what |
| Tool unavailable after round 0 | Missing `TOOL_DOMAIN_MAP` entry | Add mapping in `tool-defs.ts` |
| `create_visualization` can't find data | Data not in `fullToolResults` | Ensure `executeTool` stores parsed result |
| `query_data` has no data | Missing DuckDB cache function | Add `cache*` function and `TOOL_CACHE_MAP` entry |
| Context overflow mid-conversation | Tool results too large | Check `truncateForLLM` settings, consider reducing `MAX_ROWS` |
| Garbage XML in final response | Open model hallucination | `containsGarbage()` handles this; if persistent, file is `service.ts` |
| Stream hangs | Together AI 503 with no retry | Check `withRetry` backoff, verify `MAX_RETRIES` |
| Agent result not shown | Missing `agentToolCalled` break | Verify the break logic around line 670 in `service.ts` |
| Artifact data shape mismatch | Renderer expects different fields | Check `resolveMultiSourceData` output and renderer's expected props |
