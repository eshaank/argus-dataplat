---
name: codemogger-explore
description: Explore and navigate the Argus codebase using codemogger semantic and keyword search. Use when the user asks to find code, trace data flows, locate components, understand architecture, or answer "where is X?" / "how does Y work?" questions. Also use when onboarding to an unfamiliar area of the codebase.
---

# Codemogger Explore

Use codemogger as the **primary** code search tool to explore the Argus codebase. Always search before reading files — don't guess paths.

## Prerequisites

The codemogger index must exist at `.codemogger/` in the project root. If missing:

```bash
codemogger_index
```

Ensure `.codemogger/` is in `.gitignore`.

After creating, deleting, or heavily refactoring files in the same session, run:

```bash
codemogger_reindex
```

---

## Search Modes

### Keyword Mode — for known identifiers

Use when you have an exact symbol, type name, function name, file name, or string literal.

```
codemogger_search("UserClaims", mode="keyword")
codemogger_search("getPriceChart", mode="keyword")
codemogger_search("tool-registry", mode="keyword")
codemogger_search("ipc-adapter", mode="keyword")
```

**Best for:** type names, function names, variable names, file names, config keys, IPC channel names, CSS class names.

### Semantic Mode — for concepts and behavior

Use when you're asking *how* something works, *where* behavior lives, or searching across concerns.

```
codemogger_search("how does chat streaming work", mode="semantic")
codemogger_search("where is tRPC auth enforced", mode="semantic")
codemogger_search("agent sandbox workspace job queue", mode="semantic")
codemogger_search("CSS variables design tokens", mode="semantic")
```

**Best for:** architecture questions, data flow tracing, cross-cutting concerns, "where is X handled?", onboarding to unfamiliar areas.

### Choosing the Right Mode

| You have… | Use |
|---|---|
| An exact name: `AppRouter`, `useChat`, `ExternalAPIError` | **keyword** |
| A concept: "how does auth work", "where are widgets registered" | **semantic** |
| A partial name you're not sure about | Try **keyword** first, fall back to **semantic** |
| A cross-cutting question spanning multiple files | **semantic** |

---

## Search Strategies by Task

Each strategy: **codemogger first**, then Grep/Glob/Read only if codemogger misses.

### Find a tRPC procedure
1. Keyword: procedure name (e.g. `getDetails`, `getPriceChart`)
2. Semantic: `"tRPC procedure for [description] in domain routers"`
3. Fallback: `Grep` in `electron/domains/*/router.ts`

### Find a domain's types
1. Keyword: type name (e.g. `CompanyProfile`, `PriceBar`)
2. Semantic: `"domain types for [domain name]"`
3. Fallback: Read `shared/types.ts`

### Find where an external API is called
1. Semantic: `"external API calls in [domain] domain"`
2. Keyword: client symbol (e.g. `polygonClient`, `fredClient`)
3. Fallback: Read `electron/domains/<name>/client.ts`

### Find the router aggregation
1. Keyword: `AppRouter` or `root`
2. Fallback: Read `electron/trpc/root.ts`

### Find auth logic
1. Semantic: `"tRPC auth context Supabase JWT"`
2. Fallback: Read `electron/trpc/context.ts` + `frontend/src/providers/`

### Find a React component
1. Keyword: component name (e.g. `ChatPanel`, `WidgetContainer`)
2. Semantic: `"React component for [description]"`
3. Fallback: `Glob` `frontend/src/components/**/<Name>.tsx`

### Find a tRPC hook usage in the renderer
1. Keyword: `trpc.<domain>` (e.g. `trpc.pricing`)
2. Semantic: `"tRPC hook usage for [domain] in renderer"`
3. Fallback: `Grep` in `frontend/src/`

### Find chat streaming logic
1. Semantic: `"chat stream IPC useChat"`
2. Fallback: Read `frontend/src/hooks/useChat*` + `electron/domains/chat/`

### Find tool definitions
1. Keyword: `tool-defs` or specific tool name
2. Semantic: `"chat tool registration"`
3. Fallback: Read `electron/domains/chat/tool-defs.ts` and `tool-registry.ts`

### Find widget definitions
1. Semantic: `"canvas widget types"`
2. Fallback: `Glob` `frontend/src/components/widgets/`

### Find the HTTP client
1. Keyword: `http-client` or `ky`
2. Fallback: Read `electron/http-client.ts`

### Find design tokens / CSS variables
1. Semantic: `"CSS variables design tokens"`
2. Fallback: Read `frontend/src/index.css`

### Find agent sandbox logic
1. Semantic: `"agent sandbox workspace job queue"`
2. Fallback: Read `electron/agents/`

### Find IPC channels
1. Keyword: channel name (e.g. `argus:chat:stream`)
2. Semantic: `"IPC channel registration"`
3. Fallback: Read `electron/ipc/channels.ts` + `electron/ipc/registry.ts`

---

## When to Skip Codemogger

Fall back to Grep, Glob, or Read directly when:

- **Codemogger returns no useful hits** — try the other mode first, then fall back
- **You need every reference** — codemogger finds definitions; use Grep for exhaustive usage lists
- **The target is non-code** — `project-docs/`, config files, `.md` files
- **You already know the exact file** — just Read it

---

## Directory Map

```
electron/
  main.ts                          — Electron entry, initializes tRPC + IPC
  preload.ts                       — Exposes IPC invoke/on to renderer
  config.ts                        — Settings from .env + electron-store
  http-client.ts                   — ky client (retry, timeout, request ID)
  cache.ts                         — Generic TTLCache<K, V>
  errors.ts                        — AppError → ExternalAPIError, NotFoundError, etc.
  trpc/
    index.ts                       — tRPC init, procedures, middleware
    context.ts                     — Auth context factory (Supabase JWT via jose)
    root.ts                        — Merged AppRouter (all domain routers)
    ipc-adapter.ts                 — Single IPC handler → tRPC dispatch
  domains/                         — Domain modules (DDD, each self-contained)
  agents/                          — Agent sandbox, workspace, job queue, orchestrator
  ipc/                             — IPC registry, channels, middleware

frontend/
  src/App.tsx                      — Root component, routing
  src/main.tsx                     — Vite entry
  src/index.css                    — Global styles + CSS variables
  src/providers/                   — TRPCProvider, AuthProvider
  src/lib/                         — tRPC client, Supabase client
  src/hooks/                       — useChat, useCanvas, useTemplates
  src/components/
    chat/                          — Chat panel, messages, input, suggestions
    canvas/                        — Widget canvas, grid layout
    widgets/                       — Chart, table, metrics card, comparison
    sidebar/                       — Templates, history, search
    layout/                        — App shell, icon rail, split-view
    ui/                            — Shared primitives

shared/
  types.ts                         — Shared TypeScript types
  ipc-channels.ts                  — IPC channel constants
```

---

## Output Format

When reporting exploration results:

```markdown
## Files Found

- `path/to/file.ts:42` — [what this file/line is relevant for]
- `path/to/other.ts:10` — [why this matters]

## Data Flow (if applicable)

[Brief trace: Component → Hook → IPC → tRPC → Domain → External API]

## Notes

- [Anything missing, ambiguous, or not yet implemented]
```

Always include **file paths with line numbers**. Be precise — report what you found, flag ambiguities, and say when something doesn't exist yet.
