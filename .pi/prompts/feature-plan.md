---
description: Research codebase and generate a two-part implementation + orchestrator plan for a feature
argument-hint: <feature or problem description>
---

# Feature Plan Generator

Generate a complete, agent-executable plan for: **$ARGUMENTS**

---

## Step 1: Determine Folder Name

Derive a short, kebab-case slug from the feature description (e.g., `chat-persistence`, `agent-sandbox`, `real-time-streaming`). The plans will be saved to:

```
project-docs/plans/<slug>/
├── implementation-plan.md
└── orchestrator-plan.md
```

If the folder already exists, ask the user before overwriting.

---

## Step 2: Research Phase

Before writing anything, thoroughly research the codebase to understand the current state and what needs to change. Use explore agents or read files directly.

### 2a. Read Architecture Context

Read these files for system-level understanding:

- `project-docs/ARCHITECTURE.md`
- `project-docs/DECISIONS.md`
- `project-docs/INFRASTRUCTURE.md`
- `.rules/architecture.md`
- `.rules/base-overrides.md`

### 2b. Explore Relevant Code

Based on the feature description, identify which parts of the codebase are affected. Explore:

- **Backend domains** — `electron/domains/` (routers, services, clients)
- **Frontend components** — `frontend/src/components/`, `frontend/src/hooks/`
- **Shared types** — `shared/types/`
- **Core infrastructure** — `electron/core/`
- **Agent system** — `electron/agents/`
- **IPC layer** — `electron/ipc/`, `electron/trpc/`
- **Existing plans** — `project-docs/plans/` (for context on what's already been done)

Use `Glob` and `Grep` to locate relevant files. Read the key files to understand current behavior, data flows, and dependencies.

### 2c. Identify Scope

From your research, produce a mental model of:

- What exists today (current state)
- What needs to change (target state)
- Which files are created, modified, or deleted
- Which domains/systems are affected
- What the dependency graph looks like (what must happen first)
- What can be parallelized

---

## Step 3: Write the Implementation Plan

Create `project-docs/plans/<slug>/implementation-plan.md` following this structure exactly.

### Template: Implementation Plan

```markdown
# [Feature Title]: Implementation Plan

## Purpose

[1-2 sentences: what this plan is for and who will execute it (Claude Code agents). State that each chunk is independent within its phase and can run in parallel unless noted.]

## Current State

[Bullet list of the relevant current architecture, tech stack, data flows, and behavior. Be specific — name files, libraries, patterns.]

## Target State

[Bullet list of what the system looks like after this plan is complete. Be specific about new files, changed patterns, removed code.]

## Architecture Diagram

[ASCII diagram showing the new data flow or component relationships. Skip if the change is small enough that a diagram adds no value.]

---

## Implementation Chunks

[Organize into Phases. Chunks within a phase have no dependencies on each other. Cross-phase dependencies are noted.]

---

### PHASE N: [Phase Name] (run these [in parallel / sequentially])

[1-2 sentences on this phase's goal and what it depends on.]

---

#### CHUNK NA: [Chunk Name]

**Goal:** [What this chunk accomplishes]

**Scope:** [Which areas of the codebase are touched]

**Steps:**

1. [Specific, numbered steps an agent can execute mechanically]
2. [Include exact file paths, function names, import patterns]
3. [Reference existing code to read before writing]

**Files to create:**
- [Exact paths]

**Files to modify:**
- [Exact paths + what changes]

**Files to delete:**
- [If applicable]

**Reference files (read-only):**
- [Files the agent should read for context/behavior matching]

**Validation:** [How to verify this chunk is correct — specific commands, checks, or behaviors to confirm]

---

[Repeat for each chunk and phase]
```

### Rules for the Implementation Plan

1. **Chunks must be mechanically executable** — an agent reading a chunk should know exactly what to do without asking questions.
2. **Every chunk lists specific files** — files to create, modify, delete, and reference. No vague "update relevant files."
3. **Steps reference existing code** — "Read `electron/domains/pricing/client.ts` for the API call pattern, then replicate for the new domain."
4. **Validation is concrete** — `just build` (full frontend + electron build), specific UI behavior to verify, specific data to check. Never "it works."
5. **Phase dependencies are explicit** — "Depends on Phase 0 merged and validated."
6. **Parallel vs sequential is stated** — within each phase, say whether chunks can run in parallel.
7. **Each chunk maps to one agent type** — identify which agent (`backend-trpc`, `frontend-ui`, `infra-tooling`, `test-writer`, `data-engineer`) will execute it.

---

## Step 4: Write the Orchestrator Plan

Create `project-docs/plans/<slug>/orchestrator-plan.md` following this structure exactly.

### Template: Orchestrator Plan

```markdown
# Orchestrator Execution Plan: [Feature Title]

## Overview

You are the orchestrator agent for [feature]. Your job is to execute the plan defined in `project-docs/plans/<slug>/implementation-plan.md` by spawning specialized sub-agents for each chunk.

**You do not write code yourself.** You read the plan, spawn the right agent for each chunk, monitor their completion, validate results between phases, and report status to the user.

## Source of Truth

The detailed steps, file lists, and validation criteria for every chunk are in:

```
project-docs/plans/<slug>/implementation-plan.md
```

Read the relevant chunk section from that file before spawning each agent. Pass the chunk's full content (steps, files to create/modify, reference files, validation) as the agent's prompt.

## Available Agents

| Agent | Type | Use For |
|-------|------|---------|
| `backend-trpc` | Backend TS/tRPC | Domain ports, tRPC routers, shared types, core infra, agent sandbox |
| `frontend-ui` | React/UI | Components, hooks, tRPC client, data fetching |
| `infra-tooling` | Build/config | CI/CD, packaging, workspace config, cleanup, doc updates |
| `test-writer` | Tests | Unit and integration tests |
| `data-engineer` | SQLite/DB | Database schema, migrations, queries, persistence |
| `code-reviewer` | Review | Post-phase review before merging |
| `explore` | Read-only | Pre-task codebase exploration when an agent needs context |

## Execution Rules

1. **Execute one phase at a time.** Never start a later phase until the current phase is complete and validated.
2. **Spawn agents in parallel within a phase** using worktree isolation. Chunks within the same phase have no dependencies on each other.
3. **After each phase completes**, run the validation gate. If validation fails, fix before proceeding.
4. **Always pass the full chunk text** from `implementation-plan.md` to the agent. Don't summarize — the agent needs the file lists, reference files, and exact steps.
5. **After spawning agents for a phase**, report to the user what was spawned and wait for all to complete before running validation.

---

## Phase N: [Phase Name]

**Goal:** [1-2 sentences]

**Chunks to spawn [in parallel / sequentially]:**

| Chunk | Agent | Worktree Branch | What It Does |
|-------|-------|-----------------|--------------|
| NA | `agent-type` | `feat/<slug>-na` | [Brief description] |

**Prompt template for each agent:**

```
You are executing chunk {CHUNK_ID} from the [feature] implementation plan.

Read the full chunk details below, then execute every step. Use the reference files listed to understand the existing behavior. Create all files listed. Run the validation at the end.

Branch: {BRANCH_NAME}

--- CHUNK START ---
{paste full chunk text from implementation-plan.md}
--- CHUNK END ---
```

### Phase N Validation Gate

After all agents complete, run from the main branch (after merging all worktrees):

```bash
npm install
just build
npm run lint
npm run build
```

**Also verify:**
- [Phase-specific checks]

**Ask the user to review and approve before proceeding to the next phase.**

---

[Repeat for each phase]

## Error Recovery

If an agent fails or produces broken output:

1. **Read the error.** Check `just build` (full frontend + electron build) output to identify which files have issues.
2. **Don't re-run the entire chunk.** Spawn a targeted agent to fix the specific files. Give it the error output and the relevant files.
3. **If a foundation chunk fails**, stop everything. Fix it before spawning dependent agents.
4. **If a parallel chunk fails**, other parallel chunks are unaffected. Fix the failing chunk independently.
5. **Merge conflicts** between parallel worktrees are expected in shared files. Resolve by combining — changes are typically additive.

## Merge Conflict Hotspots

[List files that multiple chunks modify, with resolution strategy for each]
```

### Rules for the Orchestrator Plan

1. **Every phase maps to a section** with a chunks table, prompt template, and validation gate.
2. **Agent types are specific** — use the actual agent names from the Available Agents table.
3. **Branch names are consistent** — `feat/<slug>-<chunk-id>` or similar pattern.
4. **Validation gates are copy-pasteable** — the orchestrator should be able to run the commands directly.
5. **Error recovery is practical** — not generic advice, but specific to the feature's failure modes.
6. **Merge conflict hotspots call out the exact files** and how to resolve.

---

## Step 5: Report to User

After writing both files, report:

1. The folder path created
2. A brief summary of the phases and chunk count
3. Which agent types are needed
4. Any assumptions made or decisions the user should validate

Do NOT proceed to implementation — the plans are for the user to review first.
