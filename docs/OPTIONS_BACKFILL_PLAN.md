# Options Backfill Implementation Plan

> 8 years of EOD option chain snapshots (greeks, IV, OI, volume) from ThetaData v3 → ClickHouse, then Schwab takes over for daily ongoing snapshots.

---

## Current State

| Asset | Status |
|---|---|
| `option_chains` ClickHouse table (005_option_chains.sql) | ✅ Exists — but schema needs expansion for ThetaData fields |
| ThetaTerminal v3 | ✅ Running — `just thetadata up` on port 25503 (requires Java 21+) |
| ThetaData v3 REST API | ✅ Verified — `expiration=*` returns full chain (2,268 AAPL contracts in 1.2s) |
| ThetaData MCP Server | ✅ Available at `http://127.0.0.1:25503/mcp/sse` |
| Pi extension (MCP bridge) | ✅ Built — `.pi/extensions/mcp-bridge/` |
| ThetaData skill + OpenAPI spec | ✅ Written — `.pi/skills/thetadata/` |
| Ingestion pipeline (`ingestion/thetadata/`) | ❌ Does not exist |
| Schwab daily options pipeline (`ingestion/schwab/options.py`) | ❌ Does not exist |
| CLI entry point (`cli/backfill_options.py`) | ❌ Does not exist |

---

## Phase 1: Schema Migration

### 1.1 Expand `option_chains` Table

The current `005_option_chains.sql` schema is too narrow. ThetaData provides 2nd-order greeks, underlying price, and OHLCV that we should capture. Rather than alter the existing table (which has no data yet), create a new migration that drops and recreates it.

**New migration: `014_option_chains_v2.sql`**

```sql
DROP TABLE IF EXISTS option_chains;

CREATE TABLE IF NOT EXISTS option_chains (
    -- Contract identity
    underlying        LowCardinality(String),
    expiration        Date,
    strike            Float64,
    put_call          Enum8('call' = 1, 'put' = 2),

    -- OHLCV (from EOD endpoint)
    open              Nullable(Float64),
    high              Nullable(Float64),
    low               Nullable(Float64),
    close             Nullable(Float64),
    volume            UInt32                          DEFAULT 0,
    trade_count       UInt32                          DEFAULT 0,

    -- Quote (from EOD_QUOTE_GREEKS)
    bid               Float64,
    ask               Float64,
    bid_size          UInt32                          DEFAULT 0,
    ask_size          UInt32                          DEFAULT 0,

    -- Greeks — 1st order
    delta             Float64,
    gamma             Float64,
    theta             Float64,
    vega              Float64,
    rho               Float64,

    -- Greeks — 2nd order (ThetaData bonus, Schwab won't have these)
    vanna             Nullable(Float64),
    charm             Nullable(Float64),
    vomma             Nullable(Float64),
    veta              Nullable(Float64),
    epsilon           Nullable(Float64),
    lambda            Nullable(Float64),

    -- Volatility
    implied_vol       Float64,

    -- Open interest
    open_interest     UInt32                          DEFAULT 0,

    -- Context
    underlying_price  Nullable(Float64),

    -- Metadata
    snapshot_date     Date,
    source            LowCardinality(String)          DEFAULT 'thetadata',
    ingested_at       DateTime                        DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYear(snapshot_date)
ORDER BY (underlying, expiration, strike, put_call, snapshot_date);
```

**Key design decisions:**
- **`PARTITION BY toYear(snapshot_date)`** not `toYYYYMM(expiration)` — we query by snapshot date range more often than by expiration month. 8 years = 8 partitions, clean pruning.
- **`snapshot_date` (Date)** not `snapshot_at` (DateTime) — ThetaData gives us EOD snapshots, one per day. No intraday timestamps. Date is sufficient and more efficient.
- **2nd-order greeks are Nullable** — Schwab doesn't provide these, so ongoing snapshots will have NULLs for vanna/charm/vomma/veta/epsilon/lambda.
- **`source` column** — `'thetadata'` for backfill, `'schwab'` for ongoing. Enables filtering and auditing.
- **ReplacingMergeTree** — Safe for re-runs. Deduplicates on ORDER BY key, keeps latest `ingested_at`.

### 1.2 Polygon Options Reference Table

**New migration: `015_option_contracts_ref.sql`**

```sql
CREATE TABLE IF NOT EXISTS option_contracts (
    ticker            String,                         -- O:AAPL260116C00200000
    underlying        LowCardinality(String),         -- AAPL
    contract_type     Enum8('call' = 1, 'put' = 2),
    exercise_style    LowCardinality(String),         -- american, european
    expiration_date   Date,
    strike_price      Float64,
    shares_per_contract UInt16                        DEFAULT 100,
    primary_exchange  LowCardinality(String),
    updated_at        DateTime                        DEFAULT now()
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (underlying, expiration_date, strike_price, contract_type);
```

Source: Polygon `/v3/reference/options/contracts` — periodic sync.

---

## Phase 2: ThetaData v3 Ingestion Pipeline

### 2.1 HTTP Client (`ingestion/thetadata/client.py`)

Thin wrapper around ThetaTerminal v3 REST API on port 25503.

```python
class ThetaDataClient:
    """HTTP client for ThetaTerminal v3 REST API on localhost:25503."""

    def __init__(self, host: str = "127.0.0.1", port: int = 25503):
        self.base_url = f"http://{host}:{port}/v3"

    def get_eod_greeks(
        self, symbol: str, date: str, *, format: str = "ndjson",
        max_dte: int | None = None, strike_range: int | None = None,
    ) -> str:
        """Full chain EOD greeks for one underlying on one day.
        Uses expiration=* to get ALL contracts in one request.
        Returns raw NDJSON/CSV string."""
        # GET /v3/option/history/greeks/eod?symbol={symbol}&expiration=*&start_date={date}&end_date={date}&format=ndjson

    def get_open_interest(
        self, symbol: str, date: str, *, format: str = "ndjson",
    ) -> str:
        """Full chain open interest for one underlying on one day.
        Uses expiration=* to get ALL contracts in one request."""
        # GET /v3/option/history/open_interest?symbol={symbol}&expiration=*&date={date}&format=ndjson

    def get_expirations(self, symbol: str) -> list[str]:
        """All expiration dates for an underlying."""
        # GET /v3/option/list/expirations?symbol={symbol}

    def get_trading_dates(self, symbol: str) -> list[str]:
        """All dates with data for an underlying."""
        # GET /v3/option/list/dates/eod?symbol={symbol}
```

**Key v3 differences from v2:**
- All endpoints on port **25503** with `/v3/` prefix
- `expiration=*` returns the ENTIRE chain in one request (all strikes, all expirations, both calls and puts)
- Strikes are **dollars** (e.g., `220.00`), not tenths-of-cent integers
- Dates accept `YYYYMMDD` or `YYYY-MM-DD`
- `right` uses `call`/`put`/`both` (lowercase), not `C`/`P`
- Supports `format=ndjson` for streaming line-by-line processing
- Built-in `max_dte` and `strike_range` server-side filters

### 2.2 Transform (`ingestion/thetadata/transforms.py`)

Parse NDJSON responses into Polars DataFrames matching the `option_chains` schema.

**No merging needed for greeks** — the v3 `/greeks/eod` endpoint returns OHLCV + quote + all greeks + IV + underlying_price in one response. Only OI requires a separate join.

```python
def parse_greeks_ndjson(ndjson_text: str) -> pl.DataFrame:
    """
    Parse NDJSON from /v3/option/history/greeks/eod into a Polars DataFrame.
    Each line is a flat JSON object with all fields.
    """
    # 1. pl.read_ndjson() for zero-copy parsing
    # 2. Rename: symbol → underlying, right → put_call (call/put → Enum)
    # 3. Parse expiration string → Date, timestamp → Date (snapshot_date)
    # 4. Add source='thetadata'
    # 5. Validate: no nulls in required greeks

def parse_oi_ndjson(ndjson_text: str) -> pl.DataFrame:
    """
    Parse NDJSON from /v3/option/history/open_interest.
    Returns (symbol, expiration, strike, right, open_interest) DataFrame.
    """

def merge_greeks_and_oi(
    greeks_df: pl.DataFrame, oi_df: pl.DataFrame
) -> pl.DataFrame:
    """
    Left join greeks onto OI by (underlying, expiration, strike, put_call).
    Missing OI → 0.
    """
```

### 2.3 Pipeline (`ingestion/thetadata/options.py`)

The main backfill orchestrator. **Day-by-day, full-chain requests.**

**Algorithm:**

```
For each underlying in universe:
  1. GET /v3/option/list/dates/eod?symbol={underlying}
     → list of all trading dates with data

  2. For each date (filtering to 8-year window):
     a. GET /v3/option/history/greeks/eod?symbol={underlying}&expiration=*
        &start_date={date}&end_date={date}&format=ndjson
        → ALL contracts for this underlying on this date (greeks + OHLCV + quote)
     b. GET /v3/option/history/open_interest?symbol={underlying}&expiration=*
        &date={date}&format=ndjson
        → ALL contracts' open interest
     c. Parse NDJSON → Polars, join greeks + OI
     d. Bulk insert into ClickHouse

  3. Log progress, track failures
```

**Why day-by-day?** The `expiration=*` wildcard requires `start_date == end_date` (ThetaData constraint). But each request returns ALL contracts (~800-2,200 per underlying per day), so total request count is manageable.

### 2.4 Request Count & Timing (Verified)

**Measured performance (AAPL, April 1 2025):**
- `/v3/option/history/greeks/eod?expiration=*` → 2,268 contracts, **1.2 seconds**, 1.6MB NDJSON
- `/v3/option/history/open_interest?expiration=*` → 2,265 contracts, **0.9 seconds**
- **Max concurrent requests: 4** (ThetaTerminal v3 limit)

**S&P 500 full backfill:**

```
500 underlyings × 2,000 trading days × 2 requests = 2,000,000 requests

Sequential (~1.1s/req):  611 hours (25.5 days) — too slow
4 concurrent (~3.6 req/s): 154 hours (6.4 days) ✔️ feasible
```

**S&P 100 (start here):**

```
100 underlyings × 2,000 trading days × 2 requests = 400,000 requests
4 concurrent: ~31 hours (1.3 days)
```

**No need for strike_range/max_dte/monthly-only filters** — `expiration=*` is already fast enough to grab everything.

---

## Phase 3: CLI Entry Point

**`cli/backfill_options.py`**

```bash
# Backfill options for specific tickers
just backfill-options --tickers AAPL,MSFT,GOOGL

# Backfill for a universe
just backfill-options --universe sp100

# Resume after interruption (skips already-ingested dates per underlying)
just backfill-options --universe sp100 --resume

# Dry run (count requests, estimate time)
just backfill-options --universe sp100 --dry-run
```

**Features:**
- `--resume` flag: queries ClickHouse for already-ingested `(underlying, snapshot_date)` pairs, skips those dates
- `--dry-run`: fetches date lists per underlying, prints request count and time estimate without pulling data
- `--concurrency N`: number of concurrent requests (default: 4, max: 4 per ThetaTerminal limit)
- Progress logging: `[1,204/400,000] AAPL 2024-03-15: 2,143 contracts, 1.2s`
- Error summary at end with list of failed (underlying, date) pairs for retry

---

## Phase 4: Schwab Daily Pipeline (Post-Backfill)

After ThetaData backfill completes, `ingestion/schwab/options.py` takes over for daily EOD snapshots.

**Schwab option chain API:**
```
GET /marketdata/v1/chains?symbol=AAPL
```

Returns the full chain with: bid, ask, last, mark, volume, OI, delta, gamma, theta, vega, rho, IV, intrinsic/extrinsic value.

**Differences from ThetaData:**
- No 2nd-order greeks (vanna, charm, vomma, veta → NULL)
- No OHLCV per contract (only last/bid/ask)
- `source = 'schwab'` instead of `'thetadata'`
- One request per underlying returns the ENTIRE chain (all strikes, all expirations)

**Pipeline:**
1. Iterate universe (500 underlyings)
2. One GET per underlying → flatten all contracts into rows
3. Insert into same `option_chains` table with `source='schwab'`
4. Rate limit: 120 req/min → ~4 minutes for 500 underlyings

**Schedule:** Daily at 16:30 ET (after market close, before EOD settlement).

---

## Phase 5: Polygon Reference Sync

**`ingestion/polygon/options_ref.py`**

Weekly sync of contract metadata from Polygon:
```
GET /v3/reference/options/contracts?underlying_ticker=AAPL&limit=1000
```

Populates `option_contracts` reference table. Used for:
- Mapping Polygon's `O:AAPL260116C00200000` ticker format
- Exercise style (american/european)
- Primary exchange
- Shares per contract (usually 100, but adjusted options differ)

---

## Build Order

### Step 1: Schema
- [ ] Write `014_option_chains_v2.sql` — expanded schema
- [ ] Write `015_option_contracts_ref.sql` — Polygon reference table
- [ ] Run `just migrate`
- [ ] **Verify:** tables exist with correct columns

### Step 2: ThetaData Client
- [ ] Create `ingestion/thetadata/__init__.py`
- [ ] Write `ingestion/thetadata/client.py` — HTTP wrapper
- [ ] **Verify:** can call all three endpoints and get data for AAPL

### Step 3: Transform
- [ ] Write `ingestion/thetadata/transforms.py` — merge + clean
- [ ] **Verify:** produces a valid Polars DataFrame from AAPL test data

### Step 4: Pipeline + CLI
- [ ] Write `ingestion/thetadata/options.py` — backfill orchestrator
- [ ] Write `cli/backfill_options.py` — CLI entry point
- [ ] Add `backfill-options` recipe to justfile
- [ ] **Verify:** `just backfill-options --tickers AAPL --dry-run` reports correct counts
- [ ] **Verify:** `just backfill-options --tickers AAPL` inserts data into ClickHouse

### Step 5: Full Backfill
- [ ] Run `just backfill-options --universe sp100 --monthly-only --resume`
- [ ] Monitor progress, fix any failures
- [ ] Expand to S&P 500 if time permits within subscription window
- [ ] **Verify:** `SELECT count() FROM option_chains WHERE source = 'thetadata'`

### Step 6: Schwab Takeover
- [ ] Write `ingestion/schwab/options.py` — daily EOD pipeline
- [ ] Test with `--tickers AAPL`
- [ ] **Verify:** Schwab rows appear in `option_chains` with `source='schwab'`
- [ ] Cancel ThetaData subscription

### Step 7: Polygon Reference Sync
- [ ] Write `ingestion/polygon/options_ref.py`
- [ ] **Verify:** `option_contracts` table populated

---

## Storage Estimate

**Measured:** AAPL returns ~2,268 contracts per day. Average across S&P 500 is ~800.

| Scope | Rows | Disk (ZSTD) | Download (NDJSON) |
|---|---|---|---|
| S&P 100, all expirations, 8yr | ~160M | ~7 GB | ~120 GB |
| S&P 500, all expirations, 8yr | ~800M | ~36 GB | ~600 GB |
| Ongoing daily (500 underlyings) | ~400K rows/day | ~18 MB/day | — |

**No need for monthly-only filtering** — with v3's `expiration=*`, we get all contracts at no extra request cost. Storage is manageable.

Start with S&P 100 (~31 hours at 4 concurrent). Expand to S&P 500 (~6.4 days) if time permits.

---

## Concurrency

**Resolved:** ThetaTerminal v3 supports **max 4 concurrent requests**. Use `asyncio.Semaphore(4)` with `httpx.AsyncClient` in the pipeline. This gives ~3.6 req/s effective throughput.

---

## Validation Queries (Post-Backfill)

```sql
-- Total rows by source
SELECT source, formatReadableQuantity(count()) AS rows
FROM option_chains GROUP BY source;

-- Coverage: underlyings × dates
SELECT
    underlying,
    min(snapshot_date) AS earliest,
    max(snapshot_date) AS latest,
    count(DISTINCT snapshot_date) AS trading_days,
    count() AS total_rows
FROM option_chains
WHERE source = 'thetadata'
GROUP BY underlying
ORDER BY total_rows DESC
LIMIT 20;

-- Spot check: AAPL IV surface on a specific date
SELECT
    expiration, strike, put_call,
    implied_vol, delta, gamma, theta, vega,
    open_interest, volume, bid, ask
FROM option_chains
WHERE underlying = 'AAPL'
    AND snapshot_date = '2024-01-15'
    AND put_call = 'call'
ORDER BY expiration, strike;

-- IV term structure over time (ATM 30-day)
SELECT
    snapshot_date,
    avg(implied_vol) AS atm_30d_iv
FROM option_chains
WHERE underlying = 'AAPL'
    AND abs(delta) BETWEEN 0.4 AND 0.6
    AND expiration BETWEEN snapshot_date + 25 AND snapshot_date + 35
GROUP BY snapshot_date
ORDER BY snapshot_date;
```
