---
name: dataplat
description: >
  Argus DataPlat — the separated Python data platform (ClickHouse + Kafka/Redpanda).
  Covers schema migrations, Schwab ingestion pipelines, Polars transforms, ClickHouse
  queries, backfill CLI, and the future MCP server interface. Use this skill whenever
  working on: the argus-dataplat/ directory, ClickHouse schema or queries, Schwab API
  ingestion (schwabdev), OHLCV/options/universe/fundamentals/economic data pipelines,
  SEC EDGAR ingestion, Polars DataFrames, Kafka producers/consumers, the MCP server,
  or any Python code in the data platform. Also trigger when discussing data source
  boundaries (Schwab vs Polygon vs EDGAR), backfill operations, or dataplat architecture.
---

# DataPlat Skill

## Repo Location

All dataplat code lives in `argus-dataplat/` at the project root — a **separate Python project**, not part of the Argus TypeScript/Electron codebase.

```
/Users/eshaan/projects/3Epsilon/argus-dataplat/
```

## Architecture Documents

Read these before making changes:

- **`argus-dataplat/docs/VISION.md`** — Full architecture: ClickHouse vs DuckDB decision, two-repo design, schema, Kafka topics, MCP tools, migration path
- **`argus-dataplat/docs/BUILD_PLAN.md`** — Concrete implementation plan: project scaffolding, build order, phase sequencing, open questions
- **`argus-dataplat/docs/SEC_EDGAR_PLAN.md`** — SEC EDGAR pipeline: 5 tables, dilution tracking, insider trades, institutional holders

## Hard Rules

### Data Source Boundaries (NO EXCEPTIONS)

| Provider | Owns | Never Used For |
|----------|------|----------------|
| **Schwab** | ALL ongoing ticker-level data: OHLCV, quotes, streaming, options | — |
| **Polygon** | Reference/metadata, universe details, SIC codes, sectors, dividends, splits, news + ONE-OFF 1-min backfill (tagged `source='polygon_backfill'`) | Ongoing price data. The backfill is a one-time bootstrap only. |
| **SEC EDGAR** | Canonical financials (income, balance, cashflow), dilution tracking, insider trades, institutional holders, all SEC filing metadata | — |
| **FRED** | Economic indicators (treasury yields, inflation, labor market) | — |
| **ThetaData** | Historical options backfill (8yr, one-time) | Ongoing options data |

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
├── docs/                           # Architecture & plan docs
│   ├── VISION.md
│   ├── BUILD_PLAN.md
│   ├── SEC_EDGAR_PLAN.md
│   ├── OPTIONS_BACKFILL_PLAN.md
│   ├── FUNDAMENTALS_PLAN.md
│   └── ARGUS_MIGRATION.md
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
│       │   ├── client.py           # ClickHouse client factory (auto-detects cloud)
│       │   ├── migrate.py          # Migration runner + ensure_schema()
│       │   └── migrations/         # Numbered .sql files (001-020+)
│       ├── ingestion/
│       │   ├── base.py             # Abstract IngestPipeline
│       │   ├── schwab/             # Schwab API pipelines
│       │   │   ├── client.py       # schwabdev wrapper
│       │   │   ├── historical.py   # price_history → ohlcv
│       │   │   ├── quotes.py       # Realtime quotes
│       │   │   └── options.py      # Option chains
│       │   ├── polygon/            # Polygon pipelines
│       │   │   ├── backfill_1min.py # One-time 1-min OHLCV backfill
│       │   │   ├── fundamentals.py # Dividends, splits, universe enrichment
│       │   │   ├── economy.py      # Treasury, inflation, labor market
│       │   │   └── universes/      # Ticker list files (spy.txt, qqq.txt, all.txt)
│       │   ├── edgar/              # SEC EDGAR pipelines
│       │   │   ├── client.py       # HTTP client (rate limiter, retry, User-Agent)
│       │   │   ├── cik_map.py      # Ticker → CIK resolution (cached)
│       │   │   ├── concepts.py     # GAAP concept map (~65 line items + fallbacks)
│       │   │   ├── financials.py   # companyfacts → financials table
│       │   │   ├── filings.py      # submissions → sec_filings + material_events
│       │   │   ├── insider.py      # Form 4 XML → insider_trades
│       │   │   └── institutional.py # SC 13G/13D → institutional_holders
│       │   ├── thetadata/          # ThetaData historical options backfill
│       │   │   ├── client.py       # ThetaTerminal v3 REST client
│       │   │   ├── options.py      # Options backfill pipeline
│       │   │   └── transforms.py   # Polars transforms for option chains
│       │   └── fred/
│       │       └── series.py       # Economic indicators
│       ├── transforms/             # Polars transform + validation
│       └── cli/                    # CLI entry points
│           ├── backfill.py         # OHLCV backfill (Schwab + Polygon)
│           ├── backfill_fundamentals.py  # Polygon fundamentals + economy
│           ├── backfill_edgar.py   # SEC EDGAR (all 5 tables)
│           ├── backfill_options.py # ThetaData options backfill
│           ├── migrate.py          # Run migrations
│           └── migrate_to_cloud.py # Local → cloud migration
├── tests/
└── queries/                        # Ad-hoc SQL queries
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
| `financials` | ReplacingMergeTree(ingested_at) | toYear(period_end) | (ticker, period_end, fiscal_period) | **SEC EDGAR** (replaced Polygon) |
| `sec_filings` | ReplacingMergeTree(ingested_at) | toYear(filed_date) | (ticker, filed_date, form_type, accession_number) | SEC EDGAR |
| `material_events` | ReplacingMergeTree(ingested_at) | toYear(filed_date) | (ticker, filed_date, item_code, accession_number) | SEC EDGAR |
| `insider_trades` | ReplacingMergeTree(ingested_at) | toYear(report_date) | (ticker, report_date, reporter_name, transaction_code, shares) | SEC EDGAR Form 4 |
| `institutional_holders` | ReplacingMergeTree(ingested_at) | toYear(filed_date) | (ticker, filed_date, holder_name, accession_number) | SEC EDGAR SC 13G/13D |
| `option_chains` | ReplacingMergeTree(ingested_at) | toYYYYMM(expiration) | (underlying, expiration, strike, put_call, snapshot_at) | ThetaData + Schwab |
| `dividends` | ReplacingMergeTree(ingested_at) | — | (ticker, ex_dividend_date) | Polygon |
| `stock_splits` | ReplacingMergeTree(ingested_at) | — | (ticker, execution_date) | Polygon |
| `treasury_yields` | ReplacingMergeTree(ingested_at) | toYear(date) | (date) | FRED via Polygon |
| `inflation` | ReplacingMergeTree(ingested_at) | toYear(date) | (date) | FRED via Polygon |
| `inflation_expectations` | ReplacingMergeTree(ingested_at) | toYear(date) | (date) | FRED via Polygon |
| `labor_market` | ReplacingMergeTree(ingested_at) | toYear(date) | (date) | FRED via Polygon |

### Convenience Views (migration 020)

| View | Purpose |
|------|---------|
| `v_dilution_snapshot` | Full dilution picture per company per year — authorized headroom, warrants, convertibles, options, SBC %, total dilution % |
| `v_latest_financials` | Most recent annual filing per ticker |
| `v_filings_10k` | Annual reports (10-K, 20-F) |
| `v_filings_10q` | Quarterly reports (10-Q) |
| `v_filings_8k` | Material events (8-K) |
| `v_filings_insider` | Form 3/4/5 insider filings |
| `v_filings_institutional` | SC 13G/13D institutional filings |
| `v_filings_registration` | S-1, S-3, S-8 shelf registrations |
| `v_filings_prospectus` | 424B prospectus supplements |
| `v_insider_buys_sells` | Open market P/S only (filters exercises, tax, gifts) |
| `v_insider_monthly` | Net insider buying aggregated per ticker per month |
| `v_events_timeline` | Human-readable 8-K event feed |
| `v_institutional_latest` | Latest filing per holder per ticker |

## Key Commands

```bash
just migrate                                    # Run pending ClickHouse migrations
just fetch-universe                             # Polygon → universes/all.txt
just backfill-fundamentals --universe all        # Polygon: dividends + splits + universe details
just backfill --source schwab --universe spy      # Schwab daily OHLCV
just backfill --source polygon --universe all     # Polygon 1-min OHLCV (one-time)
just backfill-edgar --all --universe all          # SEC EDGAR: financials + filings + insider + institutional
just backfill-edgar --financials --gaps-only      # Fill only tickers missing from financials
just backfill-edgar --insider --universe spy      # Insider trades only
just backfill-options --universe sp100            # ThetaData options backfill
just backfill-fundamentals --economy              # FRED economic indicators
just test                                        # Run test suite
just ch-shell                                    # ClickHouse shell (auto-detects cloud/local)
just ch-stats                                    # Table row counts + sizes
just options-status                              # Options table audit
```

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

### ClickHouse Insert (Polars → Arrow)

```python
# Preferred: zero-copy Arrow path
ch_client.insert_arrow("ohlcv", df.to_arrow())

# Fallback: pandas bridge (only if insert_arrow has issues)
ch_client.insert_df("ohlcv", df.to_pandas())
```

### Rate Limiting

- Schwab: 120 req/min. Backfill uses 500ms delay.
- Polygon: paid tier ~300 req/min. Backfill uses exponential backoff on 429.
- SEC EDGAR: 10 req/sec. Pipeline uses 100ms delay + exponential backoff.

### Filing URLs

Every SEC table stores `cik`, `accession_number`, and `primary_doc`. Construct links:
```
Index: https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/
Doc:   https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/{primary_doc}
```

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
    │   ├── macro.ts          # getTreasuryYields, getYieldCurve, getInflation, getLaborMarket
    │   ├── options.ts        # getOptionChain, getExpirations, getIVSurface, getGreeksSnapshot
    │   └── sql.ts            # rawQuery, getSchema
    └── utils/
        ├── formatting.ts     # formatCurrency, formatLargeNumber, formatPercent, formatDate
        └── transforms.ts     # normalizeToBase100, computeSMA, computeEMA, computeYoYGrowth
```

### Key Rules

- **All SQL lives in the SDK query modules.** The Electron app and React frontend never write SQL directly.
- **Read-only enforced in `client.ts`:** only SELECT/WITH/EXPLAIN allowed.
- **The SDK is consumed by the Electron app via `file:` dependency:** `"@dataplat/sdk": "file:../argus-dataplat/sdk"`.
- **Future MCP:** Each query module maps 1:1 to a future MCP tool.

## Relationship to Other Skills

| Skill | Relationship |
|-------|-------------|
| **sec-edgar** | SEC EDGAR pipeline details — concepts, Form 4 parsing, 13G parsing, dilution tracking. Load for EDGAR-specific work. |
| **thetadata** | ThetaData historical options backfill. Load for options-specific work. |
| **duckdb-data-layer** | DuckDB is the Argus *edge cache* (per-conversation). DataPlat/ClickHouse is the *central analytical store*. |
| **massive-api** | Polygon/Massive is used in DataPlat ONLY for reference metadata (universe, sectors, SIC). Never for price/ticker data. |
| **chat-orchestration** | Future: DataPlat exposes MCP tools that the chat LLM calls. Not wired yet. |
| **domain-builder** | Argus tRPC domains (TypeScript). Some will be replaced by DataPlat MCP tools over time. |
| **electron-development** | The `argus/` Electron app imports `@dataplat/sdk` and exposes it to the renderer via IPC. |
