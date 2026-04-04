# Argus DataPlat — Claude Code Instructions

Argus DataPlat is the central analytical data platform. Python + ClickHouse + Polars. Ingests from Schwab, Polygon, FRED, ThetaData. Exposes data via a TypeScript SDK (consumed by Argus Electron app) and a future MCP server.

## Code Search: Codemogger First (MANDATORY)

**ALWAYS use `codemogger_search` as the PRIMARY code search tool — before `grep`, `find`, `rg`, or any bash file search.**

- **Keyword mode** for exact identifiers: `codemogger_search("ensure_schema", mode="keyword")`
- **Semantic mode** for concepts: `codemogger_search("how does the universe table get populated", mode="semantic")`
- Fall back to grep/find **only** when codemogger returns no results, you need every reference (not just definitions), or searching non-code files (.md, .env, .sql)
- After creating/modifying/deleting source files, call `codemogger_reindex`
- If the index doesn't exist yet, run `codemogger_index("/Users/eshaan/projects/3Epsilon/argus-dataplat")`

## Architecture

```
argus-dataplat/
├── src/dataplat/
│   ├── config.py               # pydantic-settings (.env loading)
│   ├── db/
│   │   ├── client.py           # ClickHouse client factory
│   │   ├── migrate.py          # Migration runner + ensure_schema()
│   │   └── migrations/         # Numbered .sql DDL files
│   ├── ingestion/
│   │   ├── schwab/             # OHLCV, quotes, options (primary data source)
│   │   ├── polygon/            # Universe, fundamentals, dividends, splits, 1-min backfill
│   │   ├── fred/               # Economic indicators
│   │   └── thetadata/          # Historical options backfill (one-time)
│   ├── transforms/             # Polars transforms + validation
│   └── cli/                    # CLI entry points (backfill, migrate, etc.)
├── sdk/                        # TypeScript SDK (@dataplat/sdk)
│   └── src/queries/            # Typed read-only ClickHouse queries
├── tests/
├── justfile                    # Task runner
└── docker-compose.yml          # ClickHouse (+ Redpanda later)
```

## Data Source Boundaries (NO EXCEPTIONS)

| Provider | Owns | Never Used For |
|----------|------|----------------|
| **Schwab** | ALL ongoing ticker-level data: OHLCV, quotes, streaming, options | — |
| **Polygon** | Reference/metadata, universe, fundamentals, dividends, splits, news + one-time 1-min OHLCV backfill | Ongoing price data |
| **FRED** | Economic indicators (treasury yields, inflation, labor market) | — |
| **ThetaData** | Historical options backfill (8-year, one-time) | Ongoing options data |

## Hard Rules

- **`ensure_schema()` before every write** — every pipeline that inserts into ClickHouse must call `ensure_schema()` first. Import from `dataplat.db.migrate`. No exceptions.
- **Polars everywhere** — never import pandas. Only `.to_pandas()` at the `insert_arrow()` boundary if needed.
- **uv** for packages — no pip, poetry, conda.
- **1-minute base resolution** — coarser views are ClickHouse materialized views.
- **ZSTD + Delta compression** — `CODEC(Delta, ZSTD(3))` on numeric columns.

## Key Commands

```bash
just migrate                          # Run pending ClickHouse migrations
just fetch-universe                   # Polygon → universes/all.txt
just backfill-fundamentals --universe all   # Fundamentals + dividends + splits + universe details
just backfill --source schwab --universe spy --years 20   # Schwab daily OHLCV
just backfill --source polygon --universe all --months 48  # Polygon 1-min backfill
just backfill-options --universe sp100      # ThetaData options backfill
just test                             # Run test suite
just ch-shell                         # ClickHouse interactive shell (auto-detects cloud/local)
just ch-stats                         # Table row counts + sizes
```

## Workflow

1. **Codemogger first** — search before reading files, never guess paths
2. **Plan mode** for any task with 3+ steps or architectural decisions
3. **Verify before done** — run tests, check migrations, demonstrate correctness
4. **Simplicity first** — minimal changes, find root causes, no hacks
5. **Autonomous bug fixing** — investigate, fix, verify. No hand-holding.

## Never Do

- Never hardcode secrets — use env vars via pydantic-settings
- Never import pandas — use Polars
- Never write a pipeline without `ensure_schema()` before inserts
- Never use Polygon for ongoing price data (Schwab only)
- Never use `--no-verify` on git commits
- Never push unless explicitly asked
- Never add dependencies without asking
