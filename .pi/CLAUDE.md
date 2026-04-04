## Session Start

1. Read `tasks/lessons.md` in the current project directory (if it exists)
2. If this is a new repo: check if `.codemogger/` index exists; if not, run `codemogger_index`

## Orientation

Claude Code loads three layers of context automatically:
- **`CLAUDE.md`** — project-level instructions (this file is global; project repos have their own)
- **`rules/*.md`** — topic-specific rules, loaded into every session
- **`skills/*/SKILL.md`** — invocable via `/skill-name`, provide specialized workflows

### Key Rules (always loaded)
| File | What it governs |
|---|---|
| `rules/architecture.md` | Argus app architecture (Electron, tRPC, React+Vite, IPC) |
| `rules/base.md` | Critical project rules (base) |
| `rules/base-overrides.md` | Argus project-specific rules and overrides |
| `rules/codemogger.md` | Search code with codemogger before Grep/Glob |
| `rules/design-system.md` | Argus design system (dark-mode, typography, tokens) |
| `rules/git.md` | Branch naming, conventional commits, PR discipline |
| `rules/prompt-refinement.md` | Clarify before acting on ambiguous requests |
| `rules/protobuf.md` | Protobuf/buf lint, format, generate, ConnectRPC |
| `rules/skill-loader.md` | Read matching skills before writing any code |

### Available Skills
| Skill | Domain |
|---|---|
| `agent-system` | Pi multi-agent research system, orchestrator, sub-agents |
| `autoresearch` | Karpathy-style autonomous self-improvement loop on evals |
| `chat-orchestration` | Chat LLM orchestration, tool-calling loop, streaming |
| `code-review` | Comprehensive code review (security, performance, best practices) |
| `domain-builder` | Creates new backend domains (DDD pattern, tRPC routers) |
| `duckdb-data-layer` | DuckDB session data layer, per-conversation caching |
| `electron-development` | Electron desktop app patterns, IPC, security, packaging |
| `massive-api` | Massive (Polygon) stock, crypto, forex, market data APIs |
| `polymarket-api` | Polymarket CLOB API, Gamma API, on-chain data |
| `supabase-postgres-best-practices` | Postgres performance optimization and best practices |
| `testing-patterns` | Vitest, React Testing Library, backend service tests |
| `together-chat-completions` | Together AI chat/completions API, tool calling, streaming |
| `typescript-best-practices` | TypeScript coding standards and conventions for Argus |
| `ui-design-system` | Argus design system (surfaces, typography, components) |
| `vercel-react-best-practices` | React performance optimization guidelines |
| `widget-builder` | Creates new widget types for the canvas panel |

## Workflow

### 1. Prompt Refinement First
For non-trivial, ambiguous requests: restate intent, surface assumptions, ask focused questions.
Skip for: simple requests, bug reports, follow-ups, debugging. See `rules/prompt-refinement.md`.

### 2. Plan Mode
After prompt refinement aligns on intent: enter plan mode for any task with 3+ steps or architectural decisions.
If something goes sideways, stop and re-plan — don't keep pushing.

### 3. Code Search: codemogger First
Always use `codemogger_search` before Grep, Glob, or Explore agents — see `rules/codemogger.md`.

### 4. Subagent Strategy
- Use subagents liberally to keep main context window clean
- Subagents also have codemogger — they should use it before Grep/Glob too
- One task per subagent for focused execution
- For complex problems, throw more compute at it via parallel subagents

### 5. Verification Before Done
- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"

### 6. Autonomous Bug Fixing
When given a bug report: just fix it. No hand-holding. Investigate, fix, verify.
(This skips prompt refinement and plan mode — act immediately.)

## Core Principles
- **Simplicity First**: Make every change as simple as possible
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact**: Only touch what's necessary
- **Demand Elegance**: For non-trivial implementations, state your approach before executing and flag if a clearly better alternative exists. Skip for simple, obvious fixes.

## Task Management
1. **Plan First**: Write plan to `tasks/todo.md` (project-relative; create `tasks/` if needed)
2. **Verify Plan**: Check in with user before starting implementation
3. **Track Progress**: Mark items complete as you go
4. **Capture Lessons**: After any correction, update `tasks/lessons.md` with the pattern

## Self-Improvement Loop
- After ANY correction: update `tasks/lessons.md` with the pattern
- Write rules for yourself that prevent the same mistake
- Review lessons at session start (see Session Start checklist)
## Never Do
- Never use `--no-verify` on git commits — fix the underlying hook failure
- Never hardcode secrets, tokens, or API keys — use env vars or secret stores
- Never edit generated files directly — modify the generator and run the generation command
- Never push unless explicitly asked
- Never force-push to `main` or shared branches
- Never add dependencies without asking
- Never run `go test`, `golangci-lint`, etc. directly when a Makefile target exists

<!-- nono-sandbox-start -->
## Nono Sandbox - CRITICAL

**You are running inside the nono security sandbox.** This is a capability-based sandbox that CANNOT be bypassed or modified from within the session.

### On ANY "operation not permitted" or "EPERM" error:

**IMMEDIATELY tell the user:**
> This path is not accessible in the current nono sandbox session. You need to exit and restart with:
> `nono run --allow /path/to/needed -- claude`

**NEVER attempt:**
- Alternative file paths or locations
- Copying files to accessible directories
- Using sudo or permission changes
- Manual workarounds for the user to try
- ANY other approach besides restarting nono

The sandbox is a hard security boundary. Once applied, it cannot be expanded. The ONLY solution is to restart the session with additional --allow flags.
<!-- nono-sandbox-end -->

<!-- tai-skills:start -->
## Workflow Orchestration

### 1. Plan Mode Default

- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately — don't keep pushing
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

### 2. Code Search: codemogger First

- **ALWAYS use `codemogger_search` before Grep, Glob, or Explore agents** — see `rules/codemogger.md` for modes, setup, and fallback rules

### 3. Subagent Strategy

- Use subagents liberally to keep main context window clean
- Subagents also have codemogger — they should use it before Grep/Glob too
- Offload remaining research and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution

### 4. Self-Improvement Loop

- After ANY correction from the user: update `tasks/lessons.md` with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for relevant project

### 5. Verification Before Done

- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness

### 6. Demand Elegance (Balanced)

- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes — don't over-engineer
- Challenge your own work before presenting it

### 7. Autonomous Bug Fixing

- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests — then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how

## Task Management

1. **Plan First**: Write plan to `tasks/todo.md` with checkable items
2. **Verify Plan**: Check in before starting implementation
3. **Track Progress**: Mark items complete as you go
4. **Explain Changes**: High-level summary at each step
5. **Document Results**: Add review section to `tasks/todo.md`
6. **Capture Lessons**: Update `tasks/lessons.md` after corrections

## Core Principles

- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs.
<!-- tai-skills:end -->
