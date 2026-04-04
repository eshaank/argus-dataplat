# DataPlat Build Plan — Database Layer

> Concrete implementation plan for standing up the ClickHouse database, Schwab ingestion pipelines, and project scaffolding. Derived from VISION.md decisions. **No MCP server, no Argus integration yet.**

---

## Current State

What exists today:

| Asset | Status |
|---|---|
| `docker-compose.clickhouse.yml` | ✅ Working — ClickHouse 24.8 |
| `.env` / `.env.example` | ✅ Schwab + ClickHouse creds configured |
| `.schwab_token.json` | ✅ Valid OAuth tokens (manual refresh via POC script) |
| `scripts/schwab_quotes_to_clickhouse.py` | ✅ POC: OAuth flow + GET /quotes → `schwab_quotes` table |
| `pyproject.toml` | ✅ Minimal: `clickhouse-connect`, `httpx`, `python-dotenv` |
| Project structure (`src/dataplat/`) | ❌ Does not exist |
| ClickHouse schema migrations | ❌ Does not exist |
| Schwab historical ingestion | ❌ Does not exist |
| Kafka / Redpanda | ❌ Does not exist (intentionally deferred) |

---

## Key Decisions (locked in)

1. **schwabdev** (`pip install schwabdev`) is the Schwab API client. No hand-rolled OAuth. Handles token management (SQLite-backed, auto-refresh), sync + async clients, full API coverage including streaming.
2. **Batch inserts first, Kafka-ready architecture.** Ingestion pipelines write directly to ClickHouse via Polars → `clickhouse-connect`. The pipeline interfaces are designed so Kafka producers can be dropped in later without rewriting the transform/load layers.
3. **Simple migration runner** — a Python script that tracks applied migrations in a ClickHouse table (`_migrations`). Not alembic (alembic is SQLAlchemy-native; ClickHouse's SQLAlchemy dialect is second-class and adds complexity for zero benefit on DDL-only migrations).
4. **Schwab for ALL ticker-level data going forward.** One-off exception: Polygon is used for the initial 1-minute OHLCV backfill (4 years of history), tagged `source = 'polygon_backfill'`. After that, Schwab is the sole ongoing source for all ticker data.
5. **Polars everywhere.** Pandas is not imported anywhere in the codebase.
6. **uv for package management.** `pyproject.toml` with `[project]` metadata, `uv sync` to install.
7. **1-minute is the base resolution.** Store 1-min bars as the ground truth. Coarser resolutions (5-min, 15-min, 1-hour, daily) are derived via ClickHouse materialized views that auto-update on insert. Never store coarser data as a primary table.
8. **`CODEC(Delta, ZSTD(1))` on all numeric columns.** Delta encoding exploits the sorted order (`ORDER BY ticker, timestamp`) — consecutive rows are the same ticker with incremental price/time changes, producing tiny deltas that ZSTD crushes. ZSTD(1) not ZSTD(3) — the compression difference is marginal but insertion is 20-30% faster, which matters for a 2.2B row backfill. `LowCardinality(String)` columns get no explicit codec (already dictionary-encoded). Target: ~20-25 bytes/row on disk.

---

## Phase 1: Project Scaffolding

### 1.1 Directory Structure

```
argus-dataplat/
├── pyproject.toml                      # Updated with all deps
├── .env.example                        # Updated env vars
├── .gitignore                          # Updated for new paths
├── docker-compose.yml                  # Renamed from docker-compose.clickhouse.yml
│                                       #   (Redpanda gets added here later)
├── justfile                            # Task runner commands
│
├── src/
│   └── dataplat/
│       ├── __init__.py
│       ├── config.py                   # pydantic-settings: all env var loading + validation
│       │
│       ├── db/
│       │   ├── __init__.py
│       │   ├── client.py               # ClickHouse client factory (clickhouse-connect)
│       │   ├── migrate.py              # Migration runner
│       │   └── migrations/
│       │       ├── 001_ohlcv.sql
│       │       ├── 002_universe.sql
│       │       ├── 003_economic_series.sql
│       │       ├── 004_fundamentals.sql
│       │       ├── 005_option_chains.sql
│       │       └── 006_materialized_views.sql
│       │
│       ├── ingestion/
│       │   ├── __init__.py
│       │   ├── base.py                 # Abstract pipeline interface
│       │   ├── schwab/
│       │   │   ├── __init__.py
│       │   │   ├── client.py           # schwabdev wrapper + singleton
│       │   │   ├── historical.py       # price_history (daily) → ohlcv table
│       │   │   ├── quotes.py           # quotes → snapshot data
│       │   │   └── options.py          # option_chains → option_chains table
│       │   ├── polygon/
│       │   │   ├── __init__.py
│       │   │   ├── reference.py        # Ticker universe, company metadata
│       │   │   └── backfill_1min.py    # ONE-OFF: 4yr 1-min OHLCV backfill
│       │   └── fred/
│       │       ├── __init__.py
│       │       └── series.py           # FRED economic indicators
│       │
│       ├── transforms/
│       │   ├── __init__.py
│       │   ├── ohlcv.py                # Raw Schwab candles → clean OHLCV schema
│       │   └── validation.py           # Schema enforcement, null checks, dedup
│       │
│       └── cli/
│           ├── __init__.py
│           ├── migrate.py              # `python -m dataplat.cli.migrate`
│           ├── ingest.py               # `python -m dataplat.cli.ingest`
│           └── backfill.py             # `python -m dataplat.cli.backfill`
│
├── tests/
│   ├── conftest.py                     # ClickHouse test fixtures, test DB
│   ├── test_db/
│   │   └── test_migrations.py
│   ├── test_ingestion/
│   │   └── test_schwab_historical.py
│   └── test_transforms/
│       └── test_ohlcv.py
│
└── scripts/
    ├── schwab_quotes_to_clickhouse.py  # Keep existing POC (reference only)
    └── seed_universe.py                # One-shot: populate universe table
```

### 1.2 pyproject.toml

```toml
[project]
name = "dataplat"
version = "0.1.0"
description = "Argus data platform — Schwab + ClickHouse analytical store"
requires-python = ">=3.12"
dependencies = [
    "schwabdev>=3.0",              # Schwab API client (OAuth, REST, streaming)
    "clickhouse-connect>=0.8,<0.9", # ClickHouse HTTP client
    "polars>=1.0",                  # DataFrame library (NOT pandas)
    "pydantic>=2.0",                # Data validation
    "pydantic-settings>=2.0",       # Env var loading
    "httpx>=0.28",                  # HTTP client (for FRED, Polygon reference)
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "ruff>=0.8",
]

[tool.uv]
package = true

[tool.ruff]
line-length = 120
target-version = "py312"
```

**Deps removed from current pyproject.toml:** `python-dotenv` (replaced by `pydantic-settings`), `httpx` stays but is no longer used for Schwab calls.

**Deps NOT added yet (Kafka phase):** `confluent-kafka`, `mcp`.

### 1.3 Config (pydantic-settings)

Single source of truth for all environment variables. Validates on startup — no silent failures from missing env vars.

```
Settings fields:
  schwab_app_key: str          (SCHWAB_APP_KEY)
  schwab_app_secret: str       (SCHWAB_APP_SECRET)
  schwab_callback_url: str     (SCHWAB_REDIRECT_URI, default "https://127.0.0.1")
  schwab_tokens_db: str        (SCHWAB_TOKENS_DB, default ".schwab_tokens.db")
  
  clickhouse_host: str         (CLICKHOUSE_HOST, default "localhost")
  clickhouse_port: int         (CLICKHOUSE_PORT, default 8123)
  clickhouse_user: str         (CLICKHOUSE_USER, default "default")
  clickhouse_password: str     (CLICKHOUSE_PASSWORD)
  clickhouse_database: str     (CLICKHOUSE_DATABASE, default "dataplat")
  
  polygon_api_key: str | None  (POLYGON_API_KEY, default None — optional for now)
  fred_api_key: str | None     (FRED_API_KEY, default None — optional for now)
```

**Token migration:** schwabdev stores tokens in its own SQLite DB (`tokens_db` param), NOT the flat `.schwab_token.json`. On first run, user re-authenticates once through schwabdev's flow. The old `.schwab_token.json` becomes dead.

### 1.4 .env.example Update

```env
# === Schwab ===
SCHWAB_APP_KEY=
SCHWAB_APP_SECRET=
SCHWAB_REDIRECT_URI=https://127.0.0.1
SCHWAB_TOKENS_DB=.schwab_tokens.db

# === ClickHouse ===
CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=8123
CLICKHOUSE_USER=default
CLICKHOUSE_PASSWORD=local_dev_clickhouse
CLICKHOUSE_DATABASE=dataplat

# === Polygon (reference data only — NOT used for ticker/price data) ===
POLYGON_API_KEY=

# === FRED ===
FRED_API_KEY=
```

---

## Phase 2: ClickHouse Schema & Migrations

### 2.1 Migration Runner Design

Simple, no ORM. Tracks state in a ClickHouse table:

```sql
CREATE TABLE IF NOT EXISTS _migrations (
    version    UInt32,
    name       String,
    applied_at DateTime DEFAULT now()
) ENGINE = MergeTree() ORDER BY version;
```

Runner logic:
1. Read all `NNN_*.sql` files from `db/migrations/`, sorted by number
2. Query `_migrations` for already-applied versions
3. Execute unapplied migrations in order, insert into `_migrations` on success
4. Fail fast on error — no partial migrations

CLI: `python -m dataplat.cli.migrate` (or `just migrate`)

### 2.2 Migration Files (in priority order)

**001_ohlcv.sql** — The backbone table. 1-minute OHLCV as the base resolution.

```sql
CREATE TABLE IF NOT EXISTS ohlcv (
    ticker       LowCardinality(String),
    timestamp    DateTime64(3, 'UTC')      CODEC(Delta, ZSTD(1)),
    open         Float64                   CODEC(Delta, ZSTD(1)),
    high         Float64                   CODEC(Delta, ZSTD(1)),
    low          Float64                   CODEC(Delta, ZSTD(1)),
    close        Float64                   CODEC(Delta, ZSTD(1)),
    volume       UInt64                    CODEC(Delta, ZSTD(1)),
    vwap         Nullable(Float64)         CODEC(Delta, ZSTD(1)),
    transactions Nullable(UInt32)          CODEC(Delta, ZSTD(1)),
    source       LowCardinality(String) DEFAULT 'schwab',
    ingested_at  DateTime                  CODEC(Delta, ZSTD(1))
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYear(timestamp)
ORDER BY (ticker, timestamp);
```

Key design notes:
- **`DateTime64(3, 'UTC')` not `Date`** — 1-minute resolution requires millisecond timestamps. All times stored in UTC.
- **`CODEC(Delta, ZSTD(1))`** on all numeric columns — Delta encoding exploits the sorted order: consecutive rows are the same ticker with prices that differ by cents. Produces tiny deltas that ZSTD crushes. ZSTD(1) not ZSTD(3): marginal compression difference, but significantly faster insertion for the 2.2B row backfill.
- **No codec on `LowCardinality(String)`** — already dictionary-encoded. Adding compression is redundant.
- **Not Gorilla on OHLC** — Gorilla suits random gauge spikes. Our prices are sorted and correlated. Delta is strictly better here.
- `ReplacingMergeTree(ingested_at)` — deduplicates on `(ticker, timestamp)` ORDER BY key, keeping the row with the latest `ingested_at`. Safe for re-ingestion / backfill reruns.
- `PARTITION BY toYear(timestamp)` — allows efficient pruning for date-range queries. With 4yr of 1-min data, this gives ~4-5 partitions.
- `vwap` and `transactions` — Polygon backfill provides both. Schwab daily candles may not. Nullable for source flexibility.

**Estimated storage (3,000 tickers, 4yr 1-min, ZSTD):** ~50 GB on disk.

**002_universe.sql** — Ticker metadata. Seeded from Polygon reference API (or manual CSV).

```sql
CREATE TABLE IF NOT EXISTS universe (
    ticker       String,
    name         String,
    type         LowCardinality(String),   -- CS, ETF, ADRC, INDEX
    exchange     LowCardinality(String),   -- XNYS, XNAS, ARCX
    sector       Nullable(LowCardinality(String)),
    sic_code     Nullable(LowCardinality(String)),
    market_cap   Nullable(Float64),
    active       Bool DEFAULT true,
    updated_at   DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY ticker;
```

**003_economic_series.sql** — FRED macro indicators.

```sql
CREATE TABLE IF NOT EXISTS economic_series (
    series_id    LowCardinality(String),
    date         Date,
    value        Float64,
    source       LowCardinality(String) DEFAULT 'fred',
    ingested_at  DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYear(date)
ORDER BY (series_id, date);
```

**004_fundamentals.sql** — Financial statements (source: SEC EDGAR, not Polygon).

```sql
CREATE TABLE IF NOT EXISTS fundamentals (
    ticker         LowCardinality(String),
    period_end     Date,
    report_type    Enum8('income' = 1, 'balance' = 2, 'cashflow' = 3),
    fiscal_year    UInt16,
    fiscal_quarter Enum8('Q1' = 1, 'Q2' = 2, 'Q3' = 3, 'Q4' = 4, 'FY' = 5),
    data           String,   -- JSON blob of all line items
    source         LowCardinality(String) DEFAULT 'sec_edgar',
    ingested_at    DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYear(period_end)
ORDER BY (ticker, period_end, report_type);
```

**005_option_chains.sql** — Option snapshots from Schwab. Deferred implementation but schema is defined now.

```sql
CREATE TABLE IF NOT EXISTS option_chains (
    underlying    LowCardinality(String),
    expiration    Date,
    strike        Float64,
    put_call      Enum8('call' = 1, 'put' = 2),
    bid           Float64,
    ask           Float64,
    last          Float64,
    volume        UInt32,
    open_interest UInt32,
    implied_vol   Float64,
    delta         Float64,
    gamma         Float64,
    theta         Float64,
    vega          Float64,
    snapshot_at   DateTime,
    ingested_at   DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(expiration)
ORDER BY (underlying, expiration, strike, put_call, snapshot_at);
```

### 2.3 Materialized Views (migration 006)

**006_materialized_views.sql** — Auto-maintained coarser resolutions derived from the 1-minute base table. These update automatically on every insert to `ohlcv` — zero application code required.

```sql
-- 5-minute bars
CREATE MATERIALIZED VIEW IF NOT EXISTS ohlcv_5min_mv
ENGINE = ReplacingMergeTree()
PARTITION BY toYear(bucket)
ORDER BY (ticker, bucket)
AS SELECT
    ticker,
    toStartOfFiveMinutes(timestamp) AS bucket,
    argMin(open, timestamp)         AS open,
    max(high)                       AS high,
    min(low)                        AS low,
    argMax(close, timestamp)        AS close,
    sum(volume)                     AS volume,
    sumIf(volume * vwap, vwap IS NOT NULL)
        / sumIf(volume, vwap IS NOT NULL) AS vwap,
    sum(transactions)               AS transactions,
    min(source)                     AS source
FROM ohlcv
GROUP BY ticker, bucket;

-- 15-minute bars
CREATE MATERIALIZED VIEW IF NOT EXISTS ohlcv_15min_mv
ENGINE = ReplacingMergeTree()
PARTITION BY toYear(bucket)
ORDER BY (ticker, bucket)
AS SELECT
    ticker,
    toStartOfFifteenMinutes(timestamp) AS bucket,
    argMin(open, timestamp)            AS open,
    max(high)                          AS high,
    min(low)                           AS low,
    argMax(close, timestamp)           AS close,
    sum(volume)                        AS volume,
    sumIf(volume * vwap, vwap IS NOT NULL)
        / sumIf(volume, vwap IS NOT NULL) AS vwap,
    sum(transactions)                  AS transactions,
    min(source)                        AS source
FROM ohlcv
GROUP BY ticker, bucket;

-- 1-hour bars
CREATE MATERIALIZED VIEW IF NOT EXISTS ohlcv_1h_mv
ENGINE = ReplacingMergeTree()
PARTITION BY toYear(bucket)
ORDER BY (ticker, bucket)
AS SELECT
    ticker,
    toStartOfHour(timestamp) AS bucket,
    argMin(open, timestamp)  AS open,
    max(high)                AS high,
    min(low)                 AS low,
    argMax(close, timestamp) AS close,
    sum(volume)              AS volume,
    sumIf(volume * vwap, vwap IS NOT NULL)
        / sumIf(volume, vwap IS NOT NULL) AS vwap,
    sum(transactions)        AS transactions,
    min(source)              AS source
FROM ohlcv
GROUP BY ticker, bucket;

-- Daily bars
CREATE MATERIALIZED VIEW IF NOT EXISTS ohlcv_daily_mv
ENGINE = ReplacingMergeTree()
PARTITION BY toYear(day)
ORDER BY (ticker, day)
AS SELECT
    ticker,
    toDate(timestamp)        AS day,
    argMin(open, timestamp)  AS open,
    max(high)                AS high,
    min(low)                 AS low,
    argMax(close, timestamp) AS close,
    sum(volume)              AS volume,
    sumIf(volume * vwap, vwap IS NOT NULL)
        / sumIf(volume, vwap IS NOT NULL) AS vwap,
    sum(transactions)        AS transactions,
    min(source)              AS source
FROM ohlcv
GROUP BY ticker, day;
```

Key design notes:
- **`argMin(open, timestamp)` / `argMax(close, timestamp)`** — Gets the open from the first bar in the bucket and close from the last bar, which is the correct OHLC aggregation semantic.
- **VWAP aggregation** — Volume-weighted: `sum(volume * vwap) / sum(volume)`. Handles NULLs with `sumIf`.
- **All four views fire on every insert to `ohlcv`** — No cron jobs, no manual refresh. Insert 1-min data, get 5-min/15-min/hourly/daily for free.
- **Query any resolution directly:**
  ```sql
  SELECT * FROM ohlcv_daily_mv WHERE ticker = 'AAPL' AND day >= '2024-01-01';
  SELECT * FROM ohlcv_5min_mv WHERE ticker = 'AAPL' AND bucket >= '2025-04-01';
  ```

### 2.4 Database Initialization

The `dataplat` database itself doesn't exist by default in ClickHouse's `default` instance. Migration runner's first action:

```sql
CREATE DATABASE IF NOT EXISTS dataplat;
```

Then all migrations run against the `dataplat` database.

---

## Phase 3: OHLCV Backfill — Two-Source Strategy

Two separate backfill pipelines that populate the same `ohlcv` table:

| Source | Resolution | Lookback | Purpose |
|---|---|---|---|
| **Polygon** (one-off) | 1-minute | ~4 years (Apr 2021 → present) | Seed the minute-level base table |
| **Schwab** (ongoing) | Daily | 20 years | Long-term daily history + ongoing updates |

Both write to the same `ohlcv` table with different `source` values (`'polygon_backfill'` vs `'schwab'`). The materialized views aggregate across both seamlessly.

### 3.1 schwabdev Client Wrapper

Thin wrapper around `schwabdev.Client`:

- Instantiates with creds from `config.Settings`
- Points `tokens_db` to project-local path (not `~/.schwabdev/`)
- Provides typed helper methods that return Polars DataFrames instead of raw `requests.Response`

On first run, schwabdev will open browser for OAuth. After that, tokens auto-refresh.

### 3.2 Polygon 1-Minute Backfill (one-off bootstrap)

Endpoint: `GET /v2/aggs/ticker/{ticker}/range/1/minute/{from}/{to}`

Tested against your Polygon plan:
- **Lookback:** ~4 years (April 2021+). Anything before March 2021 returns `NOT_AUTHORIZED`.
- **Bars per trading day:** ~734
- **Bars per monthly request:** ~15,500 (fits in one API call with `limit=50000`)
- **Rate limit:** Effectively none — rapid-fire requests all succeed at ~400ms latency.
- **No pagination needed** — one month fits in a single response.

Response shape:
```json
{
  "results": [
    {
      "v": 1694,           // volume (may be float, cast to int)
      "vw": 221.4161,      // vwap
      "o": 221.42,         // open
      "c": 221.41,         // close
      "h": 221.42,         // high
      "l": 221.41,         // low
      "t": 1743494400000,  // timestamp (epoch ms)
      "n": 29              // number of transactions
    }
  ],
  "resultsCount": 734,
  "status": "OK"
}
```

**Backfill strategy:**
- Chunk by month (48 months per ticker)
- 10 concurrent requests (asyncio + httpx or aiohttp)
- Insert each month's DataFrame into ClickHouse immediately
- `source = 'polygon_backfill'` on all rows

**Backfill numbers:**

| Universe | Requests | Rows | Time (10 concurrent) | Storage (ZSTD) |
|---|---|---|---|---|
| S&P 500 | 24,000 | 370M | ~20 min | ~8 GB |
| 1,000 tickers | 48,000 | 740M | ~40 min | ~16 GB |
| 3,000 tickers | 144,000 | 2.2B | ~2 hours | ~50 GB |

CLI:
```
python -m dataplat.cli.backfill --source polygon --tickers AAPL,MSFT --months 48
python -m dataplat.cli.backfill --source polygon --universe --concurrency 10
```

### 3.3 Schwab Daily Backfill (ongoing)

Endpoint: `GET /marketdata/v1/pricehistory`

```
schwabdev call:
  client.price_history(
      symbol="AAPL",
      periodType="year",
      period=20,                 # up to 20 years
      frequencyType="daily",
      frequency=1,
      needExtendedHoursData=False,
      needPreviousClose=False,
  )
```

Response shape:
```json
{
  "candles": [
    {
      "open": 150.0,
      "high": 152.0,
      "low": 149.5,
      "close": 151.0,
      "volume": 50000000,
      "datetime": 1704067200000
    }
  ],
  "symbol": "AAPL",
  "empty": false
}
```

**Note:** Schwab daily candles have one timestamp per day (market open). These are stored in the same `ohlcv` table as the 1-min Polygon data. The `ohlcv_daily_mv` materialized view will aggregate the minute data into its own daily bars, so the Schwab daily data is primarily useful for the 16+ year history that Polygon doesn't cover (pre-2021).

CLI:
```
python -m dataplat.cli.backfill --source schwab --tickers AAPL,MSFT --years 20
python -m dataplat.cli.backfill --source schwab --universe
```

Rate limiting: 120 requests/min. 500ms delay between requests. ~25 min for 3,000 tickers.

### 3.4 Transform Layer (`transforms/ohlcv.py`)

Both Polygon and Schwab responses → clean Polars DataFrame matching the `ohlcv` ClickHouse schema:

1. Parse response into Polars DataFrame
2. Convert timestamp (epoch ms) → `DateTime64(3)` column (UTC)
3. Cast `volume` to `UInt64` (Polygon returns floats)
4. Add `ticker` column
5. Add `source` column (`'polygon_backfill'` or `'schwab'`)
6. Validate: no nulls in OHLC, volume ≥ 0, high ≥ low, high ≥ open, high ≥ close
7. Deduplicate on `(ticker, timestamp)`

Output schema:
```
ticker:       Utf8
timestamp:    Datetime(ms, UTC)
open:         Float64
high:         Float64
low:          Float64
close:        Float64
volume:       UInt64
vwap:         Float64 | null   -- Polygon provides, Schwab daily may not
transactions: UInt32 | null    -- Polygon provides, Schwab daily may not
source:       Utf8
```

### 3.5 Load Layer

Polars DataFrame → ClickHouse bulk insert via Arrow (zero-copy, no pandas):

```python
ch_client.insert_arrow("ohlcv", df.to_arrow())
```

`insert_arrow()` is the preferred path — Polars → Arrow is zero-copy, and `clickhouse-connect` inserts Arrow natively. No pandas involved.

**Fallback** if `insert_arrow()` has type-mapping edge cases:
```python
ch_client.insert("ohlcv", df.to_pandas(), column_names=[...])
```

The `.to_pandas()` path is the ONE sanctioned exception to the no-pandas rule, used only at the insert boundary.

### 3.6 Kafka-Ready Interface

The pipeline is structured as **Extract → Transform → Load** with clean interfaces between stages. When Kafka is added later:

- **Without Kafka (now):** `extract() → transform() → load_to_clickhouse()`
- **With Kafka (later):** `extract() → produce_to_kafka()` ... `consume_from_kafka() → transform() → load_to_clickhouse()`

The `transform()` and `load_to_clickhouse()` functions don't change. Only the plumbing between extract and transform gets a Kafka hop inserted.

Concretely, the base pipeline interface:

```python
class IngestPipeline(ABC):
    """Abstract base for all ingestion pipelines."""
    
    @abstractmethod
    def extract(self, **params) -> list[dict]:
        """Fetch raw data from source API. Returns list of raw records."""
        ...
    
    @abstractmethod
    def transform(self, raw: list[dict]) -> pl.DataFrame:
        """Clean, validate, and shape raw data into target schema."""
        ...
    
    @abstractmethod
    def load(self, df: pl.DataFrame) -> int:
        """Insert DataFrame into ClickHouse. Returns row count."""
        ...
    
    def run(self, **params) -> int:
        """Execute full ETL. Override to add Kafka in the middle later."""
        raw = self.extract(**params)
        df = self.transform(raw)
        return self.load(df)
```

---

## Phase 4: Universe Seeding

The `universe` table needs to be populated before bulk backfill can use `--universe` mode. Two options:

### Option A: Polygon Reference API (preferred)
If `POLYGON_API_KEY` is set, pull the full active ticker universe:
- `GET /v3/reference/tickers?active=true&market=stocks&limit=1000`
- Paginate through all results
- Extract: ticker, name, type, exchange, SIC code
- Insert into `universe` table

This gives ~10K+ active US equities/ETFs with metadata.

### Option B: Manual CSV / curated list
A `scripts/seed_universe.py` that reads a CSV or hardcoded list (e.g. S&P 500 constituents) and inserts into `universe`. Good enough for initial testing.

**Recommendation:** Start with Option B (hardcoded S&P 500 list) for immediate testing. Add Option A as a proper ingestion pipeline when Polygon reference data is needed.

---

## Phase 5: Docker Compose Update

Rename `docker-compose.clickhouse.yml` → `docker-compose.yml`. Add volume persistence and a named database:

```yaml
services:
  clickhouse:
    image: clickhouse/clickhouse-server:24.8
    environment:
      CLICKHOUSE_USER: default
      CLICKHOUSE_PASSWORD: local_dev_clickhouse
      CLICKHOUSE_DB: dataplat            # auto-creates the database
    ports:
      - "8123:8123"   # HTTP
      - "9000:9000"   # Native TCP
    volumes:
      - clickhouse_data:/var/lib/clickhouse
    ulimits:
      nofile:
        soft: 262144
        hard: 262144

  # Redpanda goes here in a future phase
  # redpanda:
  #   image: redpandadata/redpanda:latest
  #   ...

volumes:
  clickhouse_data:
```

Key changes from current:
- Named volume `clickhouse_data` — data persists across `docker compose down` / `up`
- `CLICKHOUSE_DB: dataplat` — auto-creates the `dataplat` database on first start
- Renamed file so `docker compose up` works without `-f`

---

## Phase 6: justfile (Task Runner)

```makefile
# Start ClickHouse
up:
    docker compose up -d

# Stop ClickHouse
down:
    docker compose down

# Nuke ClickHouse data and start fresh
reset:
    docker compose down -v
    docker compose up -d

# Run schema migrations
migrate:
    uv run python -m dataplat.cli.migrate

# Backfill OHLCV for specific tickers
backfill *ARGS:
    uv run python -m dataplat.cli.backfill {{ARGS}}

# Seed the universe table
seed-universe:
    uv run python scripts/seed_universe.py

# Run tests
test:
    uv run pytest tests/ -v

# Lint
lint:
    uv run ruff check src/ tests/
    uv run ruff format --check src/ tests/

# ClickHouse shell
ch-shell:
    docker exec -it $(docker compose ps -q clickhouse) clickhouse-client -d dataplat

# Check ClickHouse is healthy
ch-ping:
    curl -sS 'http://localhost:8123/ping'
```

---

## Build Order (what to implement, in sequence)

Each step is a self-contained unit that can be verified before moving to the next.

### Step 1 — Scaffolding & Config
- [ ] Create `src/dataplat/` package structure (all `__init__.py` files)
- [ ] Write `config.py` with pydantic-settings
- [ ] Update `pyproject.toml` with full deps
- [ ] Update `.env.example`
- [ ] Rename docker-compose file, add volume + named DB
- [ ] Create `justfile`
- [ ] **Verify:** `uv sync`, `just up`, `just ch-ping` all work

### Step 2 — ClickHouse Client & Migrations
- [ ] Write `db/client.py` — ClickHouse client factory
- [ ] Write `db/migrate.py` — migration runner
- [ ] Write `db/migrations/001_ohlcv.sql` through `006_materialized_views.sql`
- [ ] Write `cli/migrate.py` — CLI entry point
- [ ] **Verify:** `just migrate` creates all tables + MVs, re-running is idempotent

### Step 3 — Schwab Client & OHLCV Transform
- [ ] Write `ingestion/base.py` — abstract `IngestPipeline`
- [ ] Write `ingestion/schwab/client.py` — schwabdev wrapper
- [ ] Write `transforms/ohlcv.py` — Schwab candles → Polars DataFrame
- [ ] Write `transforms/validation.py` — schema enforcement
- [ ] **Verify:** Can call `client.price_history("AAPL", ...)` and get a clean DataFrame

### Step 4a — Polygon 1-Minute Backfill (one-off)
- [ ] Write `ingestion/polygon/backfill_1min.py` — full pipeline (extract → transform → load)
- [ ] Add concurrency (10 concurrent requests via asyncio + httpx)
- [ ] Add monthly chunking logic (48 months per ticker)
- [ ] Add progress logging and error summary
- [ ] **Verify:** `just backfill --source polygon --tickers AAPL,MSFT` populates ohlcv + MVs auto-populate

### Step 4b — Schwab Daily Backfill
- [ ] Write `ingestion/schwab/historical.py` — full pipeline (extract → transform → load)
- [ ] Write `cli/backfill.py` — CLI with `--source`, `--tickers`, `--file`, `--universe` flags
- [ ] Add rate limiting (500ms between requests for Schwab)
- [ ] Add progress logging and error summary
- [ ] **Verify:** `just backfill --source schwab --tickers AAPL,MSFT --years 20` populates ohlcv table

### Step 5 — Universe Seeding
- [ ] Write `scripts/seed_universe.py` — S&P 500 starter list
- [ ] (Optional) Write `ingestion/polygon/reference.py` — full Polygon universe pull
- [ ] **Verify:** `just seed-universe` populates universe table, `just backfill --universe` works

### Step 6 — Tests
- [ ] Write `tests/conftest.py` — ClickHouse test fixtures (test database, cleanup)
- [ ] Write transform unit tests (mock Schwab response → verify DataFrame shape)
- [ ] Write migration tests (apply, verify tables exist, idempotent re-apply)
- [ ] **Verify:** `just test` passes

---

## What's Explicitly Deferred

| Item | Why | When |
|---|---|---|
| Kafka / Redpanda | Batch inserts work fine for historical backfill. Kafka adds value for streaming. | Phase D (streaming) |
| MCP Server | DataPlat needs data before it needs an API. | After backfill is working |
| Schwab streaming | Requires Kafka infrastructure to be useful. | Phase D |
| Option chain ingestion | Schema is defined, pipeline is deferred. Schwab option chain API is complex (body buffer overflow issues for large chains). | After OHLCV is solid |
| FRED ingestion | Lower priority than price data. Simple pipeline, can be added quickly. | After OHLCV backfill |
| SEC EDGAR fundamentals | Complex parsing (XBRL). Separate research needed. | Later phase |
| Argus MCP client | DataPlat-only for now. | Phase B in VISION.md |

---

## Rate Limits & Constraints

| Constraint | Value | Impact |
|---|---|---|
| Schwab API rate limit | 120 requests/min | Backfill of 3000 tickers ≈ 25 min (daily) |
| Schwab price_history max | 20 years daily candles | Single request per ticker covers full history |
| Schwab access token TTL | 30 minutes | schwabdev auto-refreshes |
| Schwab refresh token TTL | 7 days | Must re-auth if unused for 7 days |
| Polygon rate limit | Effectively none on your plan | 10 concurrent requests safe |
| Polygon 1-min lookback | ~4 years (April 2021+) | March 2021 and earlier returns NOT_AUTHORIZED |
| Polygon bars per month request | ~15,500 | Fits in one API call (`limit=50000`) |
| ClickHouse batch insert sweet spot | 10K–100K rows per insert | One ticker-month of 1-min ≈ 15K rows — ideal |

---

## Open Questions (resolve during build)

1. **Schwab `price_history` vwap/transactions:** Does the daily frequency response include `vwap` and `transactions` fields? If not, those columns stay NULL for Schwab-sourced data. Need to test with a real API call.

2. **ClickHouse `insert_arrow()` vs `insert_df()`:** Which path is more reliable for Polars → ClickHouse? `insert_arrow()` avoids pandas entirely but may have edge cases with ClickHouse type mapping. Test both.

3. **Universe scope for initial backfill:** S&P 500 only? Russell 3000? Start small, expand later. The schema supports any number of tickers.

4. **schwabdev `call_on_auth` callback:** For headless/server environments, schwabdev's default auth opens a browser. May need to implement a custom `call_on_auth` that works like the existing Flask callback server. Test this during Step 3.

5. **Polygon backfill → Schwab daily overlap:** For dates where both 1-min Polygon data and Schwab daily data exist (Apr 2021–present), the daily MV will aggregate from the 1-min rows. The raw Schwab daily rows will also be in `ohlcv` but won't conflict — `ReplacingMergeTree` deduplicates on `(ticker, timestamp)` and they have different timestamps. Verify that `ohlcv_daily_mv` produces correct results when both sources are present.
