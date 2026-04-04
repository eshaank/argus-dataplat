---
name: ui-design-system
description: "MANDATORY for all frontend work. The Argus design system for a data-dense financial explorer: dark-mode layered surfaces, vibrant multi-color palette, DM Sans + JetBrains Mono + Fraunces typography, treemap heatmaps, momentum charts, sector-colored tiles. Load this skill BEFORE writing or modifying any frontend component."
metadata:
  author: eshaank
  version: "3.0.0"
---

# Argus Design System

> **This is the single source of truth for all UI decisions.**
> Every component you build MUST follow these patterns exactly.

---

## CRITICAL: Read This First

Argus is a **data-dense financial data explorer** — not a chat app, not a minimal dashboard. Think finviz treemaps, CIS momentum dashboards, Bloomberg terminal density — but with modern dark UI polish. Every pixel should convey data. Key principles:

- **Color IS data.** Use the full 8-color chart palette, sector-specific colors, and heatmap gradients. Green/red for direction, but also blue, purple, amber, cyan, orange, pink for identity and differentiation.
- **Density over whitespace.** Multiple data sections visible simultaneously. Compact spacing (8–12px padding on data rows, 12–16px on cards). Fill the viewport.
- **Numbers are the hero.** Prices, returns, volumes should be large, bold, monospace, and color-coded. They’re the first thing the eye hits.
- Corners are **rounded** (6–12px), not sharp
- Fonts are **DM Sans / JetBrains Mono / Fraunces**, not system fonts
- There are **no shadows** — depth comes from surface color tiers and colored fills
- Icons are **stroke-only** (stroke-width 1.8), never filled
- **Fill the viewport.** No max-width constraints. Grids scale with screen size.
- **ClickHouse is fast.** Don’t be afraid of heavy queries — aggregations over millions of rows return in <200ms. Show more data, not less.

---

## CSS Variables — The Complete Token Set

Every value in the UI comes from these variables. NEVER use hardcoded hex values.

```css
:root {
  /* Surfaces (4 tiers — each one step lighter) */
  --bg-primary: #0a0b0e;      /* App background, canvas */
  --bg-secondary: #111318;    /* Sidebar, chat panel, widget cards */
  --bg-tertiary: #181b22;     /* Inputs, toggles, nested containers */
  --bg-hover: #1e2230;        /* Hover state on any surface */

  /* Borders (2 tiers) */
  --border: #252a36;          /* Interactive elements — buttons, inputs */
  --border-subtle: #1c2028;   /* Structural dividers — panel edges */

  /* Text (3 tiers) */
  --text-primary: #e8eaf0;    /* Headings, primary content */
  --text-secondary: #8b90a0;  /* Body text, descriptions */
  --text-muted: #555b6e;      /* Labels, metadata, placeholders */

  /* Accent */
  --accent: #5b8cff;          /* Active states, focused borders, CTAs */
  --accent-dim: #3d6ae0;      /* Hover on accent elements */
  --accent-glow: rgba(91, 140, 255, 0.08);  /* Selected/active backgrounds */

  /* Semantic */
  --green: #34d399;
  --green-dim: rgba(52, 211, 153, 0.12);
  --red: #f87171;
  --red-dim: rgba(248, 113, 113, 0.12);
  --amber: #fbbf24;

  /* Charts (use in order for multi-series) */
  --chart-1: #5b8cff;         /* blue */
  --chart-2: #a78bfa;         /* purple */
  --chart-3: #34d399;         /* emerald */
  --chart-4: #fbbf24;         /* amber */
  --chart-5: #f87171;         /* red */
  --chart-6: #fb923c;         /* orange */
  --chart-7: #38bdf8;         /* cyan */
  --chart-8: #e879f9;         /* pink */

  /* Chart dim variants (15% opacity fills for tiles, backgrounds) */
  --chart-1-dim: rgba(91, 140, 255, 0.15);
  --chart-2-dim: rgba(167, 139, 250, 0.15);
  --chart-3-dim: rgba(52, 211, 153, 0.15);
  --chart-4-dim: rgba(251, 191, 36, 0.15);
  --chart-5-dim: rgba(248, 113, 113, 0.15);
  --chart-6-dim: rgba(251, 146, 60, 0.15);
  --chart-7-dim: rgba(56, 189, 248, 0.15);
  --chart-8-dim: rgba(232, 121, 249, 0.15);

  /* Heatmap scale (performance: strong neg → neutral → strong pos) */
  --heat-neg-strong: #dc2626;
  --heat-neg: #ef4444;
  --heat-neg-light: #f87171;
  --heat-neutral: #374151;
  --heat-pos-light: #34d399;
  --heat-pos: #10b981;
  --heat-pos-strong: #059669;

  /* Sector palette (unique color per sector) */
  --sector-tech: #5b8cff;
  --sector-finance: #a78bfa;
  --sector-energy: #fb923c;
  --sector-pharma: #34d399;
  --sector-retail: #fbbf24;
  --sector-utilities: #38bdf8;
  --sector-services: #e879f9;
  --sector-food: #f97316;
  --sector-other: #6b7280;

  /* Momentum */
  --momentum-up: #10b981;
  --momentum-down: #ef4444;
}
```

### Surface Layering Rule

Each element sits on a surface **one tier lighter** than its parent:

```
--bg-primary (app shell)
  └── --bg-secondary (sidebar, chat panel, widget card)
        └── --bg-tertiary (input fields, toggles inside panels)
              └── --bg-hover (hover states inside tertiary containers)
```

NEVER skip tiers for containers. Small elements (badges, pills) can sit on any tier.

---

## Typography

### Three Font Families

| Role | Family | Weights | When To Use |
|------|--------|---------|-------------|
| **Body / UI** | `DM Sans` | 400, 500, 600, 700 | All interface text, labels, buttons, chat messages |
| **Data / Numbers** | `JetBrains Mono` | 400, 500 | Any number the user might scan or compare: prices, percentages, metrics, tickers, dates in data contexts |
| **Display** | `Fraunces` | 300, 600 | Canvas titles, empty state headings — serif for warmth. Used sparingly. |

### Type Scale (complete)

| Element | Size | Weight | Family | Color |
|---------|------|--------|--------|-------|
| Canvas title | 18px | 600 | Fraunces | `--text-primary` |
| Chat header | 14px | 600 | DM Sans | `--text-primary` |
| Section label | 10–11px | 600 | DM Sans | `--text-muted` |
| Body / chat | 13.5px | 400 | DM Sans | `--text-secondary` |
| Sidebar item | 13px | 500 | DM Sans | `--text-primary` |
| Sidebar meta | 11px | 400 | DM Sans | `--text-muted` |
| Button label | 11–12px | 500 | DM Sans | `--text-secondary` |
| Table header | 11px | 600 | DM Sans | `--text-muted` |
| Table data | 13px | 400 | DM Sans | `--text-secondary` |
| Metric value | 20px | 500 | JetBrains Mono | `--text-primary` |
| Change badge | 11px | 500 | JetBrains Mono | Semantic color |
| Inline metric | 12px | 400 | JetBrains Mono | `--accent` |
| Ticker badge | 10px | 600 | JetBrains Mono | `--text-secondary` |
| Chart label | 10px | 400 | JetBrains Mono | `--text-muted` |
| Tool call | 11px | 400 | JetBrains Mono | `--text-secondary` |
| Footer | 10px | 400 | DM Sans | `--text-muted` |

### Section Labels

ALL section/category labels use this pattern — it's the primary "this is a label" signal:

```css
font-size: 10–11px;
font-weight: 600;
letter-spacing: 0.06–0.08em;
text-transform: uppercase;
color: var(--text-muted);
```

---

## Layout

### App Shell

```css
.app {
  display: grid;
  grid-template-columns: 56px 1fr;
  grid-template-rows: 48px 1fr;
  height: 100vh;
}
```

| Column | Width | Content |
|--------|-------|---------|
| Icon rail | 56px | Nav icons, logo — spans full height |
| Main content | `1fr` | Full viewport width, scrolls independently |

**No max-width constraints.** The dashboard fills the entire viewport. Grids use `auto-fill` / `auto-fit` to scale with screen size.

### Dashboard Grid

Dashboard uses a fluid grid that adapts to viewport width:

```css
.dashboard {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 0;  /* AppShell provides padding */
  width: 100%;
}

/* 3-column sections scale down to 2 or 1 on smaller screens */
.movers-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 12px;
}

/* Heatmap tiles fill available space */
.sector-heatmap {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 6px;
}
```

### Spacing Scale (4px base)

| Token | Pixels | Usage |
|-------|--------|-------|
| xs | 4px | Icon-label gap, badge padding |
| sm | 8px | Small component padding, compact gaps |
| md | 12px | Input padding, list items |
| lg | 16px | Panel padding, widget gap |
| xl | 20px | Chat area padding |
| 2xl | 24px | Canvas padding |

---

## Border Radius

| Size | Radius | Usage |
|------|--------|-------|
| xs | 2–3px | Chart bar tops, legend dots |
| sm | 4px | Badges, toggle buttons, small pills |
| md | 6px | Icon backgrounds, small action buttons |
| lg | 8px | Inputs, sidebar items, rail buttons |
| xl | 10–12px | Widget cards, chat input wrapper |
| pill | 20px | Suggestion chips |
| circle | 50% | Status dot only |

**Rule:** Outer container radius ≥ inner element radius. A widget card (12px) contains toggles (4px).

---

## Icons

- **Style:** Stroke-only SVGs, NEVER filled
- **Stroke width:** 1.8 (standard), 2.0 (inside small containers)
- **Viewbox:** `0 0 24 24`
- **Line cap/join:** round
- **Sizes:** 18px in rail, 13–14px in sidebar, 14px in buttons, 10px in tool calls
- **Colors:** `--text-muted` default → `--text-secondary` hover → `--accent` active

---

## Component Patterns

### Widget Card

```css
background: var(--bg-secondary);
border: 1px solid var(--border-subtle);
border-radius: 12px;
padding: 20px;
/* Hover: border → var(--border) over 0.2s */
```

Every widget has: header (label + optional controls) → data area → optional legend.

### Buttons

**Ghost:** `bg: none | --bg-tertiary`, `border: 1px solid --border`, `radius: 6–8px`
**Primary (send):** `bg: --accent`, `border: none`, `radius: 8px`, `color: white`
**Toggle group:** Container `--bg-tertiary` / `radius: 6px`, buttons `radius: 4px`, active `--bg-hover` or `--accent`
**Suggestion chip:** `bg: --bg-tertiary`, `border: 1px solid --border`, `radius: 20px` → hover: accent border/text

### Inputs

```css
background: var(--bg-tertiary);
border: 1px solid var(--border);
border-radius: 8px;
padding: 8–10px 12px;
color: var(--text-primary);
font-size: 13–13.5px;
/* Focus: border-color → var(--accent) */
```

### Data Tables

```css
/* Headers: 11px uppercase --text-muted, border-bottom --border */
/* Cells: 13px --text-secondary, border-bottom --border-subtle */
/* First column: --text-primary, font-weight 500 */
/* Numeric columns: right-aligned, JetBrains Mono */
/* Last row: no bottom border */
```

### Metric Cards

Vertical stack: label (11px `--text-muted`) → value (20px JetBrains Mono) → change badge (11px, semantic color on dim background, `radius: 4px`, `padding: 1px 6px`, arrow character ▲/▼).

### Chat Messages

- User: sender "YOU" uppercase `--text-muted`, body `--text-secondary`
- AI: sender "ARGUS" uppercase `--accent`, optional tool calls, body with `<strong>` in `--text-primary`, optional suggestion chips
- Animation: `0.3s ease-out` slide-up (translateY 8px → 0, opacity 0 → 1)

### Inline Metrics (Chat)

```css
font-family: JetBrains Mono;
font-size: 12px;
color: var(--accent);
background: var(--accent-glow);
padding: 1px 6px;
border-radius: 4px;
```

Green variant: `--green` text on `--green-dim` background.

### Tool Call Indicator

```css
background: var(--bg-tertiary);
border: 1px solid var(--border-subtle);
border-radius: 8px;
padding: 8px 12px;
/* Contains: icon (20px, --accent-glow bg) → name (JetBrains Mono 11px) → params (11px --text-muted) → status ✓ (--green) */
```

---

## Charts

### Bar Charts
- Colors: chart palette in order
- Rounded tops (3px), flat bottoms
- 3px gap within group, 1px between groups
- Hover: opacity 0.8
- Legend below, 14px margin-top

### Line Charts
- SVG polyline, stroke-width 2px, round caps/joins
- Area fill: line color gradient at 10–15% opacity → transparent
- Grid lines: 0.5px `--border-subtle`
- End dots: 3px radius, filled with line color

### Legend
- Flex row, 16px gap
- Colored dot: 8px square, border-radius 2px
- Label: 12px `--text-secondary`

---

## Motion

| Duration | Usage |
|----------|-------|
| 0.12s | Micro-interactions: hover bg, toggle |
| 0.15s | Standard: border-color, text-color |
| 0.2s | Widget card hover border |
| 0.3s | Chat message entrance |

Timing: `ease` or `ease-out` only. NEVER `linear`, `bounce`, `elastic`, or `spring`.

Chat messages animate in. Widgets appear instantly. No page-load animations.

---

## Scrollbars

```css
::-webkit-scrollbar { width: 5–6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
```

---

## Data Dashboard Patterns

These patterns are specific to the data-dense dashboard views in Argus (`argus/` project).

### Treemap Heatmap (Sector/Market Map)

A market-cap-weighted treemap where rectangle **area = market cap** and **color = performance**.

- Use D3 `d3.treemap()` with `squarify` tiling for the classic finviz look
- Color scale: `--heat-neg-strong` → `--heat-neutral` → `--heat-pos-strong` (7-stop gradient)
- Each rectangle shows: ticker (bold, 11px), return % (large, 14–18px), company name (9px, muted)
- Rectangles have 1px gap between them (padding in treemap layout)
- Rounded corners on outermost container only (the treemap itself has square tiles)
- Interactive: hover shows tooltip with full stats, click navigates to ticker page
- Group by sector — each sector cluster is visually contiguous

### Sector Tiles

Each sector gets a **unique color** from `--sector-*` tokens. This is NOT green/red — it’s identity color.

```css
/* Each sector tile uses its own color at ~15% opacity as background */
.sector-tile[data-sector="tech"]     { background: var(--chart-1-dim); border-left: 3px solid var(--sector-tech); }
.sector-tile[data-sector="finance"]  { background: var(--chart-2-dim); border-left: 3px solid var(--sector-finance); }
.sector-tile[data-sector="energy"]   { background: var(--chart-6-dim); border-left: 3px solid var(--sector-energy); }
/* ... etc */
```

The return % inside the tile is STILL green/red (semantic). The tile identity color is the border-left + background tint.

### Momentum Velocity Chart

A D3 bar chart showing weekly or daily returns over time:

- Positive bars: `--momentum-up` (#10b981)
- Negative bars: `--momentum-down` (#ef4444)
- Bar width: 60–80% of available space per period
- Rounded tops (3px), flat bottoms
- X-axis: date labels in `--text-muted`, JetBrains Mono 9px
- Y-axis: percentage scale, `--text-muted`
- Zero line: 1px `--border` — always visible
- Background: `--bg-secondary`

### Movers List

A compact ranked list of tickers (gainers, losers, most active):

- Section header colored by intent: `--green` for gainers, `--red` for losers, `--accent` for active
- Each row: `ticker (mono, bold, primary)` | `name (body, muted, truncated)` | `price (mono, secondary)` | `change (mono, green/red)`
- Row height: 28–32px. No wasted vertical space.
- Hover: `--bg-tertiary` background
- Click: navigate to ticker page
- Volume column for “most active” uses `--accent` color (blue) to differentiate from change %

### Sparklines

Tiny inline area charts (60–80px wide, 24–32px tall):

- Line color: green if close > open (over period), red if down
- Area fill: line color at 12% opacity
- No axes, no labels, no crosshair, no price scale
- Used inside: index cards, watchlist cards, mover rows

### Index Cards

Market index summary (SPY, QQQ, DIA, IWM):

- Ticker (mono, 11px, bold) + change badge (green/red pill) in header
- Price (mono, 18–22px, bold, primary) as hero element
- 30-day sparkline below
- Card background: `--bg-secondary`, hover: `--border`

### Color Usage Philosophy

| Purpose | Colors to use | NOT |
|---------|--------------|-----|
| Direction (up/down) | `--green` / `--red` | Only these two |
| Sector identity | `--sector-*` (9 unique colors) | NOT green/red |
| Chart series | `--chart-1` through `--chart-8` in order | Don’t repeat |
| Tile backgrounds | `--chart-*-dim` (15% opacity) | NOT solid fills |
| Heatmap intensity | `--heat-*` scale (7 stops) | NOT binary green/red |
| Volume / activity | `--accent` (blue) or `--chart-7` (cyan) | NOT green/red |
| Momentum bars | `--momentum-up/down` | — |

The goal: a user should be able to glance at the dashboard and instantly distinguish sections by color, read direction by green/red, and identify sectors by their unique hue.

---

## Anti-Patterns Checklist

Before submitting ANY component, verify NONE of these exist:

- [ ] Hardcoded hex color instead of CSS variable
- [ ] `box-shadow` used for elevation (only allowed on status dot glow)
- [ ] Filled icon instead of stroke-only
- [ ] Border thicker than 1px (except sector tile left border: 3px)
- [ ] Sharp corners (0px radius) on any container
- [ ] `font-family: Inter`, `Arial`, `Roboto`, or system fonts
- [ ] Number displayed without JetBrains Mono in a data context
- [ ] `bounce`, `spring`, or `elastic` animation
- [ ] Color not in the token set (chart-*, sector-*, heat-*, semantic, or surface tokens)
- [ ] DM Sans number next to JetBrains Mono number in same table
- [ ] Missing hover state on interactive element
- [ ] Section label without uppercase + letter-spacing
- [ ] `max-width` on dashboard containers (fill the viewport)
- [ ] Only using green/red when the full palette is available
- [ ] Sector tiles all the same color instead of using `--sector-*` identity colors
- [ ] Heatmap using binary green/red instead of the 7-stop `--heat-*` gradient