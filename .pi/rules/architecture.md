# Argus — Architecture

Argus is a local-first **Electron** desktop app. The **React + Vite** renderer communicates with a **tRPC router** running in Electron's main process via IPC. All domain logic is TypeScript. Agent scripts run in OS-level sandboxes via `@anthropic-ai/sandbox-runtime` with a bundled Python interpreter.

> **Note:** Pi packages (`@mariozechner/pi-ai`, `pi-agent-core`) are **ESM-only**. Runtime code in `electron/` must use `pi-imports.ts` helper or dynamic `import()`. Tests (Vitest) handle ESM natively.

## The Core Loop

```
User interaction → tRPC client (renderer) → IPC bridge → tRPC router (main)
→ Domain service → External API (cached) → Response via IPC → React Query → UI
```

## Main Process — Domain-Driven Design

Each business domain is a self-contained tRPC router. The chat service calls domain services **directly via TypeScript imports** — not through IPC.

```
electron/
├── main.ts                         # Electron entry, initializes tRPC + IPC
├── preload.ts                      # Exposes IPC invoke/on to renderer
├── trpc/
│   ├── index.ts                    # tRPC init, procedures, middleware
│   ├── context.ts                  # Auth context (Supabase JWT)
│   ├── root.ts                     # Merged AppRouter (all domain routers)
│   └── ipc-adapter.ts             # Single IPC handler → tRPC dispatch
├── core/                           # HTTP client (ky), TTL cache, errors, rate limiter, config
├── domains/
│   ├── company/                    # Company profile, search (Polygon reference API)
│   ├── financials/                 # Income statement, balance sheet, cash flow, ratios (Massive)
│   ├── pricing/                    # OHLC charts, quotes, snapshots (Polygon candles)
│   ├── short_interest/             # Short interest, short volume, float (Massive)
│   ├── corporate_actions/          # Dividends, splits, IPOs (Polygon reference)
│   ├── news/                       # Company news + market news (Polygon)
│   ├── economics/                  # Macro indicators, upcoming events (FRED + Massive)
│   ├── fred/                       # Internal — consumed by economics only (not in AppRouter)
│   ├── scanner/                    # Inside-day pattern detection
│   ├── filings/                    # SEC filings
│   ├── polymarket/                 # Prediction markets
│   ├── imf/                        # International macro data (placeholder, pending IMF_API_KEY)
│   ├── chat/                       # LLM orchestration, tool registry, SSE streaming
│   ├── conversations/              # Chat history CRUD, user-scoped via Supabase JWT
│   └── settings/                   # API key management via electron-store (public, no auth)
├── agents/
│   ├── agent-factory.ts            # Creates configured Pi Agent instances by role
│   ├── agent-roles.ts              # System prompts, models, budgets per specialist
│   ├── agent-bridge.ts             # Maps Pi events → Argus IPC events
│   ├── workspace.ts                # Workspace lifecycle + directory conventions
│   ├── job-queue.ts                # In-memory job queue + event subscription
│   ├── router.ts                   # tRPC router (submitJob, results, artifacts)
│   ├── shared-extensions/          # Reusable Pi extensions
│   │   ├── argus-data-tools.ts     # Domain services as Pi AgentTools
│   │   ├── sandbox-bash.ts         # Sandboxed bash (PyPI-only network)
│   │   ├── safety-limits.ts        # Per-agent budget enforcement
│   │   └── artifact-collector.ts   # Workspace file detection
│   └── sub-agents/                 # Specialist Pi agents
│       ├── orchestrator.ts         # Task decomposition + delegation
│       ├── data-analyst.ts         # Data fetching + Python analysis
│       └── visualizer.ts           # Chart creation specialist
└── ipc/
    └── registry.ts                 # tRPC adapter + chat stream + agent stream channels

shared/types/                       # @argus/types workspace package
├── index.ts                        # Re-exports all domain types
└── {domain}.ts                     # One file per domain
```

### Adding a New Domain

1. Create `electron/domains/<name>/` with `router.ts` and `client.ts`
2. Add shared response types to `shared/types/<name>.ts`
3. Add router import in `electron/trpc/root.ts`
4. Add tool entry in `electron/domains/chat/tool-defs.ts` and handler in `tool-registry.ts`
5. Zero changes to existing domains

## Frontend

```
frontend/src/
├── components/
│   ├── auth/                      # AuthPage
│   ├── chat/                      # ChatPage, ChatPanel, ChatInput, MessageList, MessageBubble, ThinkingBlock, ToolActivity, AgentActivity, ArtifactFrame
│   ├── layout/                    # Header
│   ├── settings/                  # OnboardingModal, SettingsModal, ApiKeyInput
│   └── ui/                        # Shared primitives: Badge, Card, Skeleton, ErrorBoundary
├── contexts/                      # AuthContext, SettingsContext
├── hooks/                         # useChat (IPC streaming), useAgentStream, useClock
├── providers/                     # TRPCProvider
├── lib/
│   ├── trpc.ts                    # tRPC client with IPC link
│   └── supabase.ts                # Supabase client
├── types/
│   └── electron.d.ts              # Window.argus IPC type declarations
└── App.tsx
```

---

## Chat System Rules

### Tool Registry (`electron/domains/chat/tool-registry.ts`)

- Every tool has a `name`, `description`, `parameters`, and `handler`
- The `description` is what the LLM reads — it must be precise and unambiguous
- The `handler` calls domain services directly via TypeScript import (in-process)
- Tool descriptions should specify WHEN to use the tool, not just what it does
- Example: "Retrieve income statement data including revenue, operating income, net income. **Use for profitability and earnings questions.**"

### Artifact System

- The LLM calls `create_visualization` or `create_generative_visualization` as tools to emit artifacts
- Artifact payloads reference prior tool results by `toolCallId` — no data duplication
- Two surfaces: `inline` (in chat messages, height-constrained) and `forge` (persistent side panel)
- Two kinds: `structured` (typed renderers: `line_chart`, `bar_chart`, `data_table`, `metrics_card`, `comparison_table`, `company_summary`) and `generative` (LLM-written React)
- Rendered in sandboxed iframes (`<iframe sandbox="allow-scripts">`) with lazy-loaded per-type renderers
- Artifact data must always come from tool results — NEVER fabricated by the LLM

### Streaming (Chat IPC)

- Chat uses dedicated IPC channels (`argus:chat:stream` / `argus:chat:event`), not tRPC
- Event types: `thinking`, `text`, `tool_start`, `tool_result`, `artifact_inline`, `artifact_forge`, `error`, `done`
- Frontend processes all event types from the same IPC listener

### Conversation Context

- Full conversation history is sent with each LLM call (up to context limit)
- A state object tracks: active entities (tickers), active timeframe, user expertise level
- Follow-up references like "compare that to MSFT" must resolve correctly
