# Agents

Project rules live in `.claude/rules/`. Invocable workflows are in `.claude/skills/`. Agent prompt bodies are in `.claude/agents/`.

## Available Agents

### code-reviewer
You are a senior code reviewer. Your job is to find real problems — not nitpick style.
- Prompt: `.claude/agents/code-reviewer.md`

### test-writer
You are a testing specialist. You write tests that CATCH BUGS, not tests that just pass.
- Prompt: `.claude/agents/test-writer.md`

### explore
You are a codebase explorer for **Argus**, a local-first Electron desktop app with **tRPC in the main process** and a **React + Vite** renderer.
- Prompt: `.claude/agents/explore.md`
- Search: use `codemogger_search` first — see `.claude/rules/codemogger.md`.

### data-engineer
Senior data engineer for local SQLite persistence. Handles schema design, migrations, query optimization, and all DB code in electron/core/db.ts and electron/domains/conversations/. Specializes in financial and economic data modeling.
- Prompt: `.claude/agents/data-engineer.md`

### backend-trpc
Backend migration agent — ports domains to TypeScript tRPC routers in the Electron main process.
- Prompt: `.claude/agents/backend-trpc.md`

### frontend-ui
Frontend UI agent for React components, hooks, and renderer-side code.
- Prompt: `.claude/agents/frontend-ui.md`

### infra-tooling
Infrastructure and tooling agent for build config, Electron Forge, CI, and dev scripts.
- Prompt: `.claude/agents/infra-tooling.md`
