---
name: agent-system
description: Pi multi-agent research system — orchestrator, sub-agents, workspace management, job queue, and artifact pipeline. Use when adding new agent roles, modifying agent behavior, working on sandbox execution, or extending the agent tool set.
---

# Agent System Skill

## Key Files

```
electron/agents/
├── agent-factory.ts           # Creates Pi Agent instances by role (88 lines)
├── agent-roles.ts             # System prompts, models, budgets (340 lines)
├── agent-bridge.ts            # Pi events → Argus IPC events (187 lines)
├── workspace.ts               # Workspace lifecycle + conventions (347 lines)
├── job-queue.ts               # In-memory FIFO queue, concurrency=1 (414 lines)
├── router.ts                  # tRPC router: submitJob, status, results (195 lines)
├── pi-imports.ts              # ESM import helper for @mariozechner/pi-ai (36 lines)
├── shared-extensions/
│   ├── argus-data-tools.ts    # 17 domain services as Pi tools (401 lines)
│   ├── sandbox-bash.ts        # Sandboxed bash via @anthropic-ai/sandbox-runtime (206 lines)
│   ├── safety-limits.ts       # Budget enforcement: turns, cost, wall-clock (84 lines)
│   └── artifact-collector.ts  # File detection + type inference from workspace dirs (133 lines)
└── sub-agents/
    ├── orchestrator.ts        # Main research agent + create_artifact pipeline (584 lines)
    ├── data-analyst.ts        # Data fetching + Python analysis (118 lines)
    └── visualizer.ts          # Chart creation via sandboxed matplotlib/plotly (102 lines)
```

## Architecture

### Data Flow

```
Frontend → router.submitJob() → job-queue enqueues
  → runResearchOrchestrator()
    → Pi Orchestrator (GLM-5) with:
      ├── 10 Argus data tools (subset of 17; batched via Promise.all)
      ├── create_artifact (JSX → Sucrase validation → IPC → frontend)
      ├── query_data (read-only SQL on DuckDB session cache)
      └── run_data_analysis → spawns data-analyst sub-agent
```

### Agent Roles (from `agent-roles.ts`)

| Role | Model | Turns | Cost | Wall Clock | Tools |
|------|-------|-------|------|------------|-------|
| orchestrator | GLM-5 | 20 | $1.00 | 8 min | 10 data + create_artifact + query_data + run_data_analysis |
| data-analyst | GLM-5 | 20 | $0.30 | 4 min | 17 data + bash + read/write/edit/ls |
| visualizer | GLM-5 | 12 | $0.15 | 3 min | bash + read/write/edit/ls (no data tools) |
| dashboard-builder | GLM-5 | 15 | $0.20 | 4 min | bash + read/write/edit/ls |

Tool subsets are defined in `getToolNamesForRole()` at the bottom of `agent-roles.ts`.

### ESM/CommonJS Bridge (CRITICAL)

Pi packages are ESM-only. Electron main process is CommonJS.
- `pi-agent-core`: works with `await import('@mariozechner/pi-agent-core')`
- `pi-ai`: requires `pi-imports.ts` helper (resolves dist entry by filesystem traversal because the exports map blocks CJS `import()`)
- Type-only imports (`import type`) are safe — erased at compile time
- NEVER use static `import` for Pi runtime packages in `electron/` code

### Agent Factory (`agent-factory.ts`)

Creates Pi `Agent` instances configured for Together AI:
- `getTogetherModel(modelId)` — builds a pi-ai Model object for Together AI endpoint
- `createAgent(role, options)` — instantiates Agent, wires AbortSignal and event subscriber
- All agents use `toolExecution: 'sequential'` (one tool at a time per turn)

### Workspace Conventions

**Job workspaces** at `{userData}/agent-workspaces/{jobId}/`:
```
data/        — JSON/CSV from data analyst
charts/      — PNG/HTML from visualizer
scripts/     — Python scripts
dashboards/  — HTML dashboards
_meta/       — Internal metadata (manifest.json)
```
Created by `createWorkspaceWithConventions()`. Cleaned up on job completion.

**Conversation workspaces** at `.argus/workspaces/{conversationId}/` (persistent across messages). Created by `getOrCreateConversationWorkspace()`. Same subdirectory layout.

### Sandbox Configuration (`sandbox-bash.ts`)

- Network: PyPI-only (`pypi.org`, `files.pythonhosted.org`)
- Filesystem: writes confined to workspace + `/tmp`
- Denied reads: `.env`, `~/.ssh`, `~/.aws`, `~/.gnupg`
- Timeout: 120s per bash command (configurable via `bashTimeoutMs` in budget)
- Lazy initialization: sandbox created on first bash call, not at agent start
- Python packages pre-installed: pandas, numpy, scipy, matplotlib, plotly, pillow

### Batchable Data Tools (`argus-data-tools.ts`)

17 tools wrapping domain service calls. Single-ticker tools accept `tickers: string[]` and parallelize via `Promise.all`:
- Concurrency limit: 5 parallel API calls per batch
- Results auto-cached in DuckDB via `cacheToolResult()`
- Returns text summaries (not raw JSON) to keep agent context small
- Orchestrator gets 10 of 17; data-analyst gets all 17

### Safety Limits (`safety-limits.ts`)

- Tracks turns, cost (USD), wall-clock time via `agent.subscribe()` on `turn_end` events
- Aborts agent (`agent.abort()`) when any limit is hit
- Usage: `attachSafetyLimits(agent, budget)` — called in every sub-agent factory
- Query status: `getSafetyStatus(agent)` returns `{ turns, cost, elapsedMs, limitHit }`

### Job Queue (`job-queue.ts`)

- FIFO with `concurrencyLimit=1` (SandboxManager singleton constraint)
- Event subscription: `subscribeToJob(jobId, listener)` for streaming to IPC
- Job states: `queued` → `running` → `completed | failed | cancelled`
- Cooperative cancellation: executor polls `isCancelled(jobId)`, propagates via AbortSignal
- Job retention: 1 hour after terminal state, then evicted from memory
- V2 results: `setJobResultV2()` / `getJobResultV2()` for structured multi-agent results

### Agent Bridge (`agent-bridge.ts`)

Maps Pi `AgentEvent` types to Argus `AgentStreamEvent` types for IPC:
- `agent_start` → `agent:started` (orchestrator) or `agent:sub_started` (sub-agent)
- `message_update` → `agent:thinking` / `agent:sub_thinking` (buffered, flushed every 500ms)
- `tool_execution_start/end` → `agent:sub_tool` / `agent:sub_tool_done` (sub-agents only)
- `turn_end` → `agent:turn_complete` with turn counter
- Helper emitters: `emitDelegating`, `emitSubComplete`, `emitArtifact`, `emitFailed`

### Artifact Pipeline (`orchestrator.ts`)

1. Orchestrator calls `create_artifact` tool with `{ title, code, surface }`.
2. Data auto-injected from DuckDB cache — maps tool names to session table data keys.
3. JSX validated via Sucrase dry-run (`validateCodeSyntax`) + structure check (`validateCodeStructure`).
4. Emitted to frontend via `bridge.emitArtifact(surface, payload)` → IPC.
5. Fallback: if orchestrator finishes without calling `create_artifact`, auto-generates one.

### Router (`router.ts`)

All procedures require auth (`authedProcedure`). Ownership enforced per job.
- `submitJob` — creates workspace, enqueues job, returns `{ jobId }` immediately
- `getJobStatus` — poll job state
- `getJobResult` — raw string result (V1)
- `getJobResultV2` — structured result with artifacts and sub-agent details
- `getJobArtifacts` — read artifact files from workspace (base64 for binary, utf8 for text)
- `cancelJob` — request cancellation (cooperative via AbortSignal polling every 1s)
- `listJobs` — list jobs for current user, optionally filtered by status

## Adding a New Agent Role

1. Add role to `AgentRole` type in `shared/types/` (union type)
2. Define budget in `BUDGETS`, model in `MODEL_IDS`, prompt in `SYSTEM_PROMPTS` in `agent-roles.ts`
3. Add tool subset in `getToolNamesForRole()` in `agent-roles.ts`
4. Create `sub-agents/<role>.ts` with factory function + runner function (follow `data-analyst.ts` pattern)
5. If orchestrator-delegated: add a delegation tool in `orchestrator.ts` (like `run_data_analysis`)
6. If directly exposed: add tRPC procedure in `router.ts`

## Common Pitfalls

- **Model choice:** GLM-5 (`zai-org/GLM-5`) works reliably for tool-calling; Llama 3.3 often skips tools with TypeBox schemas
- **Wall clock budget:** includes network latency — set generously (8 min for orchestrator)
- **ESM imports:** NEVER use static `import` for pi-ai in electron/ code; use `pi-imports.ts`
- **Sandbox network:** PyPI-only — agents cannot call external APIs from bash; data must come through Argus domain tools
- **Sub-agent tools:** only the orchestrator has `create_artifact`; sub-agents produce files in workspace
- **JSX validation:** always validate via Sucrase before emitting (see `visualization-handler.ts`)
- **Tool result capture:** orchestrator captures tool results via `tool_execution_end` events into a WeakMap for data injection into artifacts
- **Concurrency:** job queue is limited to 1 concurrent job due to SandboxManager singleton
