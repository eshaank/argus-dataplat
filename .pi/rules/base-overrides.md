# Argus — Project-Specific Rules

> **Argus** — A conversational financial research terminal.
> Chat-first interface where users ask questions in plain English and get data-driven answers with interactive visualizations.
> Local-first Electron desktop app. tRPC backend in the main process. Sandboxed agent execution.

---

## Domain Naming Convention

Domain names are chosen so an LLM can unambiguously select the right tool from the name alone. Each domain maps to a clear analytical concept:

| Domain | What It Answers | Tool Name Pattern |
|--------|----------------|-------------------|
| `company` | "What does this company do?" | `get_company_profile` |
| `financials` | "How profitable is this company?" | `get_income_statement`, `get_balance_sheet`, `get_cash_flow`, `get_ratios` |
| `pricing` | "What's the stock price / chart?" | `get_price_chart`, `get_quote` |
| `short_interest` | "Is this stock heavily shorted?" | `get_short_interest`, `get_short_volume`, `get_float` |
| `corporate_actions` | "Does it pay dividends? Any splits?" | `get_dividends`, `get_splits`, `get_ipos`, `get_upcoming_dividends`, `get_upcoming_splits` |
| `news` | "What's in the news?" | `get_company_news`, `get_market_news` |
| `economics` | "How's the economy?" | `get_economic_indicators`, `get_upcoming_events` |
| `scanner` | "Find stocks matching a pattern" | `scan_inside_days` |
| `filings` | "Show me SEC filings" | `get_sec_filings` |
| `polymarket` | "What do prediction markets say?" | `get_polymarket_events` |
| `conversations` | _(infrastructure)_ Chat history CRUD | _(no LLM tools — frontend only)_ |
| `settings` | _(infrastructure)_ API key management | _(no LLM tools — public, no auth)_ |
| `fred` | _(internal)_ Raw FRED series data | _(not in AppRouter — consumed by economics)_ |
| `imf` | "International macro data" | _(placeholder — pending `IMF_API_KEY`)_ |
| `_agent` | "Run a deep multi-step analysis" | `run_research_agent` |

**NEVER create a domain named something vague like "research" or "data".**

---

## Project Documentation

| Document | Purpose | When to Read |
|----------|---------|----|
| `project-docs/ARCHITECTURE.md` | System overview, data flow, tRPC + IPC structure | Before architectural changes |
| `project-docs/AI-CHAT-TERMINAL.md` | Chat feature plan, widget types, template system | Before chat/canvas/template work |
| `project-docs/DECISIONS.md` | ADRs — the "why" behind each choice | Before proposing alternatives |
| `project-docs/INFRASTRUCTURE.md` | Env vars, Electron build, agent sandbox | Before environment changes |
| `project-docs/argus-style-guide.md` | Complete visual design system | Before any frontend work |

**ALWAYS read relevant docs before making cross-service changes.**

---

## When Something Seems Wrong (Argus-Specific)

- Widget not rendering? → Check the widget_type matches a registered renderer BEFORE assuming broken
- LLM picking wrong tool? → Check tool descriptions in `electron/domains/chat/tool-defs.ts` BEFORE blaming the model
- IPC not responding? → Check the tRPC adapter in `electron/trpc/ipc-adapter.ts` and the channel name BEFORE assuming broken
- Chat stream breaking? → Check event type parsing on the dedicated IPC channel BEFORE assuming backend issue
- Empty data? → Check if external API services are running BEFORE assuming broken
- Auth failing? → Check which auth system (Supabase JWT via JWKS) BEFORE debugging
- Agent script failing? → Check sandbox permissions (filesystem, network allowlist) BEFORE assuming code bug
- Bun-specific API in electron/? → **This will break.** Electron main process runs Node.js, not Bun.
- Agent not tool-calling? → Check model ID in `agent-roles.ts` — GLM-5 (`zai-org/GLM-5`) works reliably; Llama 3.3 often skips tools with TypeBox schemas
- Agent times out? → Check `wallClockMs` budget in `agent-roles.ts` (orchestrator: 8min, analyst: 4min, visualizer: 3min)
- ESM import error in main process? → Pi packages are ESM-only. Use `pi-imports.ts` helper for `@mariozechner/pi-ai`, never static imports
- Agent produces broken JSX? → `create_artifact` validates via Sucrase before emitting. Check `visualization-handler.ts` validators
- Chat LLM keeps calling tools after agent? → Verify the `agentToolCalled` break in `service.ts` tool loop
- Artifact renders but runtime error? → Data shape mismatch — the inline data passed to `create_artifact` doesn't match what the JSX Component expects

---

## Environment Variables

| Variable | Required | Process | Description |
|----------|----------|---------|-------------|
| `MASSIVE_API_KEY` | Yes | Main | API key for Polygon.io + Massive APIs |
| `FRED_API_KEY` | Yes | Main | API key for FRED economic data |
| `TOGETHER_API_KEY` | Yes | Main | API key for Together AI LLM (chat + agents) |
| `SUPABASE_URL` | Yes | Main | Supabase URL for JWKS verification |
| `VITE_SUPABASE_URL` | Yes | Renderer | Supabase project URL |
| `VITE_SUPABASE_ANON_KEY` | Yes | Renderer | Supabase anon key |
| `DEBUG` | No | Main | Enable debug logging |

---

## Additional Workflow

- When building widgets: always test with real API data, not mocks
- When writing tool descriptions: test with ambiguous user queries to verify the LLM picks correctly
- If a domain is renamed, update the tool registry (`electron/domains/chat/tool-defs.ts` + `tool-registry.ts`)
- When adding tRPC procedures: define Zod input schemas, add types to `@argus/types`
- When working on agents: test sandbox isolation (filesystem, network) before shipping

## Build Verification — CRITICAL

**ALWAYS use `just build` to verify work — NEVER `npx tsc --noEmit` alone.**

`npx tsc -p electron/tsconfig.json --noEmit` only checks the electron workspace. The frontend has a separate `tsc -b` step that catches different errors (especially in hooks, components, and shared type consumers). A passing electron typecheck does NOT mean the build works.

- Before declaring any task done: `just build`
- In orchestrator phase validation gates: `just build`
- When modifying `shared/types/`: always run `just build` — shared types are consumed by BOTH electron and frontend, and type narrowing errors only surface in the frontend build
