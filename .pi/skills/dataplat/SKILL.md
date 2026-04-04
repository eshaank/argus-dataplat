---
name: dataplat
description: >
  Argus DataPlat — the separated Python data platform (ClickHouse + Kafka/Redpanda).
  Covers schema migrations, Schwab ingestion pipelines, Polars transforms, ClickHouse
  queries, backfill CLI, and the future MCP server interface. Use this skill whenever
  working on: the argus-dataplat/ directory, ClickHouse schema or queries, Schwab API
  ingestion (schwabdev), OHLCV/options/universe/fundamentals/economic data pipelines,
  Polars DataFrames, Kafka producers/consumers, the MCP server, or any Python code in
  the data platform. Also trigger when discussing data source boundaries (Schwab vs
  Polygon), backfill operations, or dataplat architecture.
---

# DataPlat Skill

## Repo Location

All dataplat code lives in `argus-dataplat/` at the project root — a **separate Python project**, not part of the Argus TypeScript/Electron codebase.

```
/Users/eshaan/projects/3Epsilon/argus-dataplat/
```

## Architecture Documents

Read these before making changes:

- **`argus-dataplat/VISION.md`** — Full architecture: ClickHouse vs DuckDB decision, two-repo design, schema, Kafka topics, MCP tools, migration path
- **`argus-dataplat/BUILD_PLAN.md`** — Concrete implementation plan: project scaffolding, build order, phase sequencing, open questions

## Hard Rules

### Data Source Boundaries (NO EXCEPTIONS)

| Provider | Owns | Never Used For |
|----------|------|----------------|
| **Schwab** | ALL ticker-level data going forward: OHLCV, quotes, streaming, options, fundamentals (quote-level) | — |
| **Polygon** | Reference/metadata + ONE-OFF 1-min backfill (4yr, tagged `source='polygon_backfill'`), universe, SIC codes, sectors, news, corporate actions, alt data | Ongoing price data. The backfill is a one-time bootstrap only. |
| **FRED** | Economic indicators | — |
| **SEC EDGAR** | Full financial statements (income, balance, cashflow) | — |

### Schema Safety (NO EXCEPTIONS)

- **Every pipeline that writes to ClickHouse MUST call `ensure_schema()` before the first insert.** This runs all pending migrations idempotently so tables always exist. Never assume the table is already there.
- The function lives at `dataplat.db.migrate.ensure_schema`. Import it, call it once at the top of any `run_*()` entry point that does `insert_arrow()` or `insert_df()`.
- New pipelines MUST follow this pattern. PRs that add a new ClickHouse writer without `ensure_schema()` are rejected.

### Technology Choices

- **1-minute is the base resolution.** Coarser views (5-min, 15-min, hourly, daily) are ClickHouse materialized views that auto-update on insert.
- **ZSTD compression** with Delta encoding on numeric columns: `CODEC(Delta, ZSTD(3))`. Target ~20-25 bytes/row.
- **Polars everywhere.** Pandas is NEVER imported. The only exception: `.to_pandas()` at the `clickhouse-connect` insert boundary if `insert_arrow()` doesn't work.
- **schwabdev** (`pip install schwabdev`) is the Schwab API client. No hand-rolled OAuth/token management.
- **uv** for package management. No pip, poetry, conda.
- **pydantic-settings** for config. No `python-dotenv` direct usage.
- **Batch inserts first, Kafka-ready interfaces.** Pipelines follow Extract → Transform → Load with clean seams for Kafka insertion later.

## Project Structure

```
argus-dataplat/
├── pyproject.toml
├── docker-compose.yml              # ClickHouse (+ Redpanda later)
├── justfile                        # Task runner
├── sdk/                            # TypeScript SDK (consumed by Argus Electron app)
│   ├── package.json
│   ├── tsconfig.json
│   └── src/
│       ├── index.ts
│       ├── client.ts
│       ├── types.ts
│       ├── queries/                # One module per data domain
│       └── utils/                  # Formatting + transforms
├── src/
│   └── dataplat/
│       ├── config.py               # pydantic-settings env loading
│       ├── db/
│       │   ├── client.py           # ClickHouse client factory
│       │   ├── migrate.py          # Migration runner
│       │   └── migrations/         # Numbered .sql files
│       ├── ingestion/
│       │   ├── base.py             # Abstract IngestPipeline
│       │   ├── schwab/             # Schwab API pipelines
│       │   │   ├── client.py       # schwabdev wrapper
│       │   │   ├── historical.py   # price_history → ohlcv
│       │   │   ├── quotes.py       # Realtime quotes
│       │   │   └── options.py      # Option chains
│       │   ├── polygon/
│       │   │   └── reference.py    # Universe/metadata ONLY
│       │   └── fred/
│       │       └── series.py       # Economic indicators
│       ├── transforms/             # Polars transform + validation
│       └── cli/                    # CLI entry points
├── tests/
└── scripts/
```

## ClickHouse Schema

Core tables (see `db/migrations/` for DDL):

| Table | Engine | Partition | Order By | Source |
|-------|--------|-----------|----------|--------|
| `ohlcv` | ReplacingMergeTree(ingested_at) | toYear(timestamp) | (ticker, timestamp) | Schwab + Polygon backfill |
| `ohlcv_5min_mv` | Materialized View | toYear(bucket) | (ticker, bucket) | auto from ohlcv |
| `ohlcv_15min_mv` | Materialized View | toYear(bucket) | (ticker, bucket) | auto from ohlcv |
| `ohlcv_1h_mv` | Materialized View | toYear(bucket) | (ticker, bucket) | auto from ohlcv |
| `ohlcv_daily_mv` | Materialized View | toYear(day) | (ticker, day) | auto from ohlcv |
| `universe` | ReplacingMergeTree(updated_at) | — | ticker | Polygon reference |
| `economic_series` | ReplacingMergeTree(ingested_at) | toYear(date) | (series_id, date) | FRED |
| `fundamentals` | ReplacingMergeTree(ingested_at) | toYear(period_end) | (ticker, period_end, report_type) | SEC EDGAR |
| `option_chains` | ReplacingMergeTree(ingested_at) | toYYYYMM(expiration) | (underlying, expiration, strike, put_call, snapshot_at) | Schwab |

## Key Patterns

### Pipeline Interface (Kafka-ready)

```python
class IngestPipeline(ABC):
    def extract(self, **params) -> list[dict]: ...
    def transform(self, raw: list[dict]) -> pl.DataFrame: ...
    def load(self, df: pl.DataFrame) -> int: ...
    def run(self, **params) -> int:
        raw = self.extract(**params)
        df = self.transform(raw)
        return self.load(df)
```

When Kafka is added: extract() → produce_to_kafka() ... consume_from_kafka() → transform() → load(). The transform and load functions don't change.

### ClickHouse Insert (Polars → Arrow)

```python
# Preferred: zero-copy Arrow path
ch_client.insert_arrow("ohlcv", df.to_arrow())

# Fallback: pandas bridge (only if insert_arrow has issues)
ch_client.insert_df("ohlcv", df.to_pandas())
```

### Rate Limiting

Schwab: 120 requests/min max. Backfill uses 500ms delay between calls (~120 req/min).

## TypeScript SDK (`argus-dataplat/sdk/`)

The SDK is a typed TypeScript package that provides read-only access to ClickHouse over HTTPS. It is the **sole data access layer** for the Argus Electron app — no raw SQL in UI code.

### Structure

```
argus-dataplat/sdk/
├── package.json              # @dataplat/sdk
├── tsconfig.json
└── src/
    ├── index.ts              # Barrel export
    ├── client.ts             # ClickHouse HTTP client (read-only enforced)
    ├── types.ts              # All TypeScript interfaces
    ├── queries/
    │   ├── ohlcv.ts          # getOHLCV, getOHLCVMulti, getReturns, getLatestPrices
    │   ├── financials.ts     # getFinancials, getIncomeStatement, getBalanceSheet, getCashFlow, getMetric
    │   ├── universe.ts       # getUniverse, searchTickers, getTicker, getSectors, getTickersBySector
    │   ├── dividends.ts      # getDividends, getDividendCalendar
    │   ├── splits.ts         # getSplits
    │   ├── macro.ts          # getTreasuryYields, getYieldCurve, getYieldCurveTimeSeries, getInflation, getLaborMarket, getInflationExpectations
    │   ├── options.ts        # getOptionChain, getExpirations, getIVSurface, getIVSkew, getGreeksSnapshot, getIVHistory, getOpenInterestProfile, getVolumeProfile
    │   └── sql.ts            # rawQuery, getSchema
    └── utils/
        ├── formatting.ts     # formatCurrency, formatLargeNumber, formatPercent, formatDate
        └── transforms.ts     # normalizeToBase100, computeSMA, computeEMA, computeYoYGrowth, computeMargins
```

### Key Rules

- **All SQL lives in the SDK query modules.** The Electron app and React frontend never write SQL directly.
- **The SDK maps interval → correct MV automatically:** `1m` → `ohlcv`, `5m` → `ohlcv_5min_mv`, `15m` → `ohlcv_15min_mv`, `1h` → `ohlcv_1h_mv`, `1d` → `ohlcv_daily_mv`.
- **Read-only enforced in `client.ts`:** only SELECT/WITH/EXPLAIN allowed. Mutation keywords are blocked.
- **Snake_case from ClickHouse is mapped to camelCase TypeScript interfaces** in each query module's `mapRow()` function.
- **The SDK is consumed by the Electron app via `file:` dependency:** `"@dataplat/sdk": "file:../argus-dataplat/sdk"`.
- **Build with:** `cd argus-dataplat/sdk && npx tsc`
- **Future MCP:** Each query module maps 1:1 to a future MCP tool. The SDK is the shared implementation; MCP wraps it.

### SDK → MCP Mapping

| SDK Module | Future MCP Tool |
|-----------|----------------|
| `queries/ohlcv.ts` | `query_market_data` |
| `queries/financials.ts` | `query_financials` |
| `queries/universe.ts` | `query_universe` |
| `queries/macro.ts` | `query_economics` |
| `queries/dividends.ts` + `queries/splits.ts` | `query_corporate_actions` |
| `queries/options.ts` | `query_options` |
| `queries/sql.ts` | `run_sql` |

## Relationship to Other Skills

| Skill | Relationship |
|-------|-------------|
| **duckdb-data-layer** | DuckDB is the Argus *edge cache* (per-conversation). DataPlat/ClickHouse is the *central analytical store*. Different repos, different purposes. |
| **massive-api** | Polygon/Massive is used in DataPlat ONLY for reference metadata (universe, sectors, SIC). Never for price/ticker data. |
| **chat-orchestration** | Future: DataPlat exposes MCP tools that the chat LLM calls. Not wired yet. |
| **domain-builder** | Argus tRPC domains (TypeScript). Some will be replaced by DataPlat MCP tools over time. |
| **electron-development** | The `argus/` Electron app imports `@dataplat/sdk` and exposes it to the renderer via IPC. See `argus/electron/ipc-handlers.ts`. |
