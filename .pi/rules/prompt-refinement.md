---
description: Prompt refinement workflow — restate intent, surface assumptions, ask focused questions before non-trivial tasks
alwaysApply: true
---

# Prompt Refinement

Before executing any non-trivial task, pause to align on intent:

1. **Restate the intent** — 1-2 sentence summary of what you'll do
2. **Surface assumptions** — scope, approach, affected files, tradeoffs
3. **Ask focused questions** — if ambiguous or multiple valid outcomes exist, ask (max 3 questions per round; prefer multiple-choice over open-ended)
4. **Propose a refined prompt** — rewrite as a precise, unambiguous instruction

Only proceed after the user confirms or adjusts. Keep the refinement short — a few lines, not an essay.

## How this interacts with other rules

- **Plan mode**: Refinement happens *before* entering plan mode. Once aligned, go straight into planning.
- **Bug reports**: Skip refinement — CLAUDE.md says "just fix it." Only clarify if the bug report is genuinely ambiguous (e.g., multiple possible root causes with different fixes).
- **Self-improvement loop**: If a correction reveals the original prompt was misunderstood, note the pattern in `tasks/lessons.md`.

## Skip refinement for:
- Simple, unambiguous requests ("run tests", "show git status", "read file X")
- Bug reports and error fixes (act autonomously per CLAUDE.md §7)
- Follow-ups within an already-refined task or active plan
- Debugging sessions (read the error, investigate, fix)
- When the user signals urgency or says "just do it" / "go ahead" / "ship it"
- Single-file, single-change edits where intent is obvious
- Non-interactive sessions (CI bots, GitHub Actions, automated reviews, Agent SDK with no human in the loop)

## Examples

**Needs refinement:**
> "refactor the auth system"
→ Ask: scope (whole system or specific module?), goals (performance, readability, security?), constraints (breaking changes OK?)

**Skip refinement:**
> "add a timeout to the HTTP client in pkg/client/http.go"
→ Intent is clear, single file, single change. Just do it.

> "tests are failing in CI, fix them"
→ Bug report. Investigate and fix autonomously.