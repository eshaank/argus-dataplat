# STOP — Read Skills Before Writing Code

**This is a hard gate. Do NOT write, edit, or create any file until you have completed the steps below.**

## Step 1: Identify Matching Skills

Look at the task. Match it to one or more rows below.

| If the task involves... | Read these SKILL.md files |
|------------------------|--------------------------|
| Any frontend component, styling, layout, colors, tokens | `.claude/skills/ui-design-system/SKILL.md` + `.claude/skills/vercel-react-best-practices/SKILL.md` |
| Chat, LLM, tool registry, streaming, system prompt | `.claude/skills/chat-orchestration/SKILL.md` |
| New backend domain, router, service, client | `.claude/skills/domain-builder/SKILL.md` |
| Massive/Polygon API integration | `.claude/skills/massive-api/SKILL.md` |
| Polymarket API integration | `.claude/skills/polymarket-api/SKILL.md` |
| Chat widget (chart, table, card) | `.claude/skills/widget-builder/SKILL.md` + `.claude/skills/ui-design-system/SKILL.md` |
| Electron main process, IPC, preload, packaging | `.claude/skills/electron-development/SKILL.md` |
| Refactor, migration, rename, restructure | `.claude/skills/refactor-migrator/SKILL.md` |
| TypeScript patterns, types, generics | `.claude/skills/typescript-best-practices/SKILL.md` |
| Supabase auth, Postgres, RLS | `.claude/skills/supabase-postgres-best-practices/SKILL.md` |
| Agent system, Pi, roles, sub-agents, workspace | `.claude/skills/electron-development/SKILL.md` |
| Code review, audit, quality check | `.claude/skills/code-review/SKILL.md` |
| Commands, skills, agents, plans, tooling | No skill needed — but still verify codebase state before writing |

## Step 2: Read Each Matching Skill

Use the `Read` tool on each SKILL.md file path from Step 1. Read the full file. These are not slash commands — they are files on disk.

## Step 3: Verify Codebase State

Before writing anything, confirm your assumptions match reality:
- Check `package.json` for the actual package manager and scripts
- Check actual file structure with `Glob` if you're unsure what exists
- Do NOT rely on old plans, memories, or assumptions about tooling

## Step 4: Now You May Write Code

Only after completing Steps 1-3.
