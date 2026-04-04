# Argus — Design System

The frontend follows the Argus design system documented in `project-docs/argus-style-guide.md`. Key principles:

- **Dark-mode only** — layered surface system (`#0a0b0e` → `#111318` → `#181b22`)
- **Three fonts** — DM Sans (UI), JetBrains Mono (data/numbers), Fraunces (display titles)
- **Accent blue** (`#5b8cff`) — the only brand color, used for active states and CTAs
- **Semantic colors** — green for positive, red for negative, amber for caution
- **No shadows** — depth comes from surface color tiers, not elevation
- **1px borders only** — `--border-subtle` for structural, `--border` for interactive
- **Rounded corners everywhere** — 8px for inputs/buttons, 12px for cards, 20px for pills
- **Stroke-only icons** — never filled, stroke-width 1.8
- **Accessibility** — focus-visible rings on all interactives, aria-invalid for form errors, sr-only labels for icon buttons

See `project-docs/argus-style-guide.md` for the full token list, component patterns, and do's/don'ts.
