# Fundamentals & Economy — Backfill Plan

> Schemas and ingestion plan for company fundamentals, corporate actions, and economic indicators from Polygon/Massive. Complements the existing OHLCV 1-min backfill.

---

## Data Sources

All data comes from Polygon/Massive API. These are **reference and fundamental data only** — not price data (Schwab owns that).

### Company Data

| Endpoint | API Path | What It Contains | Records (SPY) | Frequency |
|---|---|---|---|---|
| **Financials** | `/vX/reference/financials` | Income statement, balance sheet, cash flow, comprehensive income | ~10K | Quarterly filings |
| **Dividends** | `/v3/reference/dividends` | Cash dividends with all dates, amounts, types | ~10K | Per-event |
| **Stock Splits** | `/v3/reference/splits` | Split ratio and execution date | ~500 | Per-event (rare) |
| **Ticker Details** | `/v3/reference/tickers/{ticker}` | Company description, SIC, employees, market cap, address, CIK, FIGI | 500 | Enrichment (one-time + refresh) |

### Economy Data

| Endpoint | API Path | Fields | Records | History |
|---|---|---|---|---|
| **Treasury Yields** | `/fed/v1/treasury-yields` | 1mo, 3mo, 1yr, 2yr, 5yr, 10yr, 30yr yields | 16,046 | 1962–present (daily) |
| **Inflation** | `/fed/v1/inflation` | CPI, CPI core, PCE, PCE core, PCE spending | 950 | 1947–present (monthly) |
| **Inflation Expectations** | `/fed/v1/inflation-expectations` | Market 5yr/10yr, forward 5-10yr, model 1/5/10/30yr | 531 | 1982–present (monthly) |
| **Labor Market** | `/fed/v1/labor-market` | Unemployment rate, participation rate, avg hourly earnings, job openings | 938 | 1948–present (monthly) |

---

## Schema Design Principles

1. **Wide tables, not normalized.** ClickHouse is columnar — unused columns cost zero I/O. A wide `financials` table with income + balance sheet + cash flow columns is faster than 3 tables with joins.
2. **`universe` as the dimension table.** Join on `ticker` when you need company names, sectors, etc. ClickHouse loads the small table (500 rows) into memory — instant.
3. **Structured columns for top fields, JSON overflow for the rest.** The 30 most-queried financial fields get their own columns for direct SQL. Everything else lives in `raw_json`.
4. **Dedicated economy tables, not generic.** Treasury yields, inflation, etc. each have their own table with named columns. The existing `economic_series` table (migration 003) stays for future FRED integration.
5. **`ReplacingMergeTree` everywhere.** Safe re-ingestion — run the backfill again and duplicates get merged away.

---

## Migration 004 (rewrite): `financials`

Replaces the current `004_fundamentals.sql` which uses a JSON blob. New version has structured columns.

```sql
DROP TABLE IF EXISTS fundamentals;  -- remove old schema

CREATE TABLE IF NOT EXISTS financials (
    -- Identifiers
    ticker                  LowCardinality(String),
    period_start            Date,
    period_end              Date,
    fiscal_year             String,
    fiscal_period           LowCardinality(String),  -- Q1, Q2, Q3, Q4, FY, TTM
    timeframe               LowCardinality(String),  -- quarterly, annual, ttm
    filing_date             Nullable(Date),
    cik                     Nullable(String),

    -- Income Statement
    revenue                 Nullable(Float64),
    cost_of_revenue         Nullable(Float64),
    gross_profit            Nullable(Float64),
    operating_expenses      Nullable(Float64),
    operating_income        Nullable(Float64),
    net_income              Nullable(Float64),
    basic_eps               Nullable(Float64),
    diluted_eps             Nullable(Float64),
    basic_shares            Nullable(UInt64),
    diluted_shares          Nullable(UInt64),
    research_and_dev        Nullable(Float64),
    sga_expenses            Nullable(Float64),
    income_tax              Nullable(Float64),

    -- Balance Sheet
    total_assets            Nullable(Float64),
    current_assets          Nullable(Float64),
    noncurrent_assets       Nullable(Float64),
    total_liabilities       Nullable(Float64),
    current_liabilities     Nullable(Float64),
    noncurrent_liabilities  Nullable(Float64),
    total_equity            Nullable(Float64),
    long_term_debt          Nullable(Float64),
    inventory               Nullable(Float64),
    accounts_payable        Nullable(Float64),

    -- Cash Flow
    operating_cash_flow     Nullable(Float64),
    investing_cash_flow     Nullable(Float64),
    financing_cash_flow     Nullable(Float64),
    net_cash_flow           Nullable(Float64),

    -- Overflow + metadata
    raw_json                String,
    source                  LowCardinality(String) DEFAULT 'polygon',
    ingested_at             DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
ORDER BY (ticker, period_end, fiscal_period)
PARTITION BY toYear(period_end)
```

**Why this shape:**
- 30 structured columns cover the fields you'd query 95% of the time: revenue, EPS, margins, debt, cash flow
- `raw_json` stores the full Polygon response for anything not extracted (comprehensive income details, per-share breakdowns, etc.)
- `ORDER BY (ticker, period_end, fiscal_period)` — fast range scans per ticker over time
- All financial values are `Nullable(Float64)` — not every company reports every field

**Example queries this enables:**

```sql
-- Revenue growth, all tickers, last 4 quarters
SELECT ticker, fiscal_period, fiscal_year, revenue,
    revenue / lagInFrame(revenue) OVER (PARTITION BY ticker ORDER BY period_end) - 1 AS rev_growth
FROM financials WHERE timeframe = 'quarterly' ORDER BY ticker, period_end;

-- Gross margin screening
SELECT ticker, revenue, gross_profit, gross_profit / revenue AS gross_margin
FROM financials WHERE fiscal_period = 'Q1' AND fiscal_year = '2026'
ORDER BY gross_margin DESC;

-- Cross-statement: free cash flow = operating CF - capex (from investing CF)
SELECT ticker, operating_cash_flow, investing_cash_flow,
    operating_cash_flow + investing_cash_flow AS free_cash_flow
FROM financials WHERE timeframe = 'annual' AND fiscal_year = '2025';
```

---

## Migration 002 (expand): `universe`

Add columns from Polygon's ticker-details endpoint. New migration `002b_universe_details.sql` uses ALTER TABLE:

```sql
ALTER TABLE universe
    ADD COLUMN IF NOT EXISTS description       Nullable(String),
    ADD COLUMN IF NOT EXISTS homepage_url      Nullable(String),
    ADD COLUMN IF NOT EXISTS total_employees   Nullable(UInt32),
    ADD COLUMN IF NOT EXISTS list_date         Nullable(Date),
    ADD COLUMN IF NOT EXISTS cik               Nullable(String),
    ADD COLUMN IF NOT EXISTS sic_description   Nullable(String),
    ADD COLUMN IF NOT EXISTS address_city      Nullable(String),
    ADD COLUMN IF NOT EXISTS address_state     Nullable(String),
    ADD COLUMN IF NOT EXISTS composite_figi    Nullable(String)
```

---

## Migration 007: `dividends`

```sql
CREATE TABLE IF NOT EXISTS dividends (
    ticker              LowCardinality(String),
    ex_dividend_date    Date,
    declaration_date    Nullable(Date),
    record_date         Nullable(Date),
    pay_date            Nullable(Date),
    cash_amount         Float64,
    currency            LowCardinality(String) DEFAULT 'USD',
    frequency           UInt8,               -- 0=one-time, 1=annual, 4=quarterly, 12=monthly
    dividend_type       LowCardinality(String), -- CD=cash, SC=special, LT=long-term, ST=short-term
    source              LowCardinality(String) DEFAULT 'polygon',
    ingested_at         DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
ORDER BY (ticker, ex_dividend_date)
```

**Example queries:**

```sql
-- Current dividend yield (join with latest price from daily MV)
SELECT d.ticker, d.cash_amount * d.frequency AS annual_div,
    p.close, d.cash_amount * d.frequency / p.close * 100 AS yield_pct
FROM dividends d
JOIN ohlcv_daily_mv p ON d.ticker = p.ticker
WHERE d.ex_dividend_date = (SELECT max(ex_dividend_date) FROM dividends d2 WHERE d2.ticker = d.ticker)
AND p.day = (SELECT max(day) FROM ohlcv_daily_mv)
ORDER BY yield_pct DESC;
```

---

## Migration 008: `stock_splits`

```sql
CREATE TABLE IF NOT EXISTS stock_splits (
    ticker              LowCardinality(String),
    execution_date      Date,
    split_from          Float64,
    split_to            Float64,
    source              LowCardinality(String) DEFAULT 'polygon',
    ingested_at         DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
ORDER BY (ticker, execution_date)
```

---

## Migration 009: `treasury_yields`

```sql
CREATE TABLE IF NOT EXISTS treasury_yields (
    date                Date,
    yield_1_month       Nullable(Float64),
    yield_3_month       Nullable(Float64),
    yield_1_year        Nullable(Float64),
    yield_2_year        Nullable(Float64),
    yield_5_year        Nullable(Float64),
    yield_10_year       Nullable(Float64),
    yield_30_year       Nullable(Float64),
    source              LowCardinality(String) DEFAULT 'polygon',
    ingested_at         DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
ORDER BY date
```

**Example queries:**

```sql
-- Yield curve inversion detector
SELECT date, yield_2_year, yield_10_year,
    yield_10_year - yield_2_year AS spread_2s10s,
    if(yield_10_year < yield_2_year, 'INVERTED', 'NORMAL') AS curve_status
FROM treasury_yields
WHERE date >= '2020-01-01'
ORDER BY date;

-- Correlate 10yr yield with stock prices
SELECT t.date, t.yield_10_year, p.close AS spy_close
FROM treasury_yields t
JOIN ohlcv_daily_mv p ON t.date = p.day AND p.ticker = 'AAPL'
WHERE t.date >= '2023-01-01'
ORDER BY t.date;
```

---

## Migration 010: `inflation`

```sql
CREATE TABLE IF NOT EXISTS inflation (
    date                Date,
    cpi                 Nullable(Float64),
    cpi_core            Nullable(Float64),
    pce                 Nullable(Float64),
    pce_core            Nullable(Float64),
    pce_spending        Nullable(Float64),
    source              LowCardinality(String) DEFAULT 'polygon',
    ingested_at         DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
ORDER BY date
```

---

## Migration 011: `inflation_expectations`

```sql
CREATE TABLE IF NOT EXISTS inflation_expectations (
    date                    Date,
    market_5_year           Nullable(Float64),
    market_10_year          Nullable(Float64),
    forward_years_5_to_10   Nullable(Float64),
    model_1_year            Nullable(Float64),
    model_5_year            Nullable(Float64),
    model_10_year           Nullable(Float64),
    model_30_year           Nullable(Float64),
    source                  LowCardinality(String) DEFAULT 'polygon',
    ingested_at             DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
ORDER BY date
```

---

## Migration 012: `labor_market`

```sql
CREATE TABLE IF NOT EXISTS labor_market (
    date                            Date,
    unemployment_rate               Nullable(Float64),
    labor_force_participation_rate  Nullable(Float64),
    avg_hourly_earnings             Nullable(Float64),
    job_openings                    Nullable(Float64),
    source                          LowCardinality(String) DEFAULT 'polygon',
    ingested_at                     DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
ORDER BY date
```

---

## Ingestion Strategy

### Economy Data (4 endpoints, ~18K total records)

**Dead simple.** Each endpoint returns the entire history in one paginated call. No per-ticker iteration needed.

```
For each of [treasury-yields, inflation, inflation-expectations, labor-market]:
  1. GET /fed/v1/{endpoint}?limit=50000 (one call, all history)
  2. Parse into Polars DataFrame
  3. insert_arrow() into ClickHouse
```

Total: **4 API calls.** Takes under 10 seconds.

### Company Data (per-ticker, ~2500 API calls for SPY)

```
For each ticker in universe:
  1. GET /vX/reference/financials?ticker={}&timeframe=quarterly  (paginate)
  2. GET /vX/reference/financials?ticker={}&timeframe=annual     (paginate)
  3. GET /v3/reference/dividends?ticker={}                       (paginate)
  4. GET /v3/reference/tickers/{}                                (single call, enriches universe)

Global (not per-ticker):
  5. GET /v3/reference/splits (paginate all, filter client-side)
```

For 503 SPY tickers: ~2,500 API calls. At Polygon's rate (no limit), ~15 minutes.

### CLI

```bash
# Economy (all 4 endpoints, one shot)
just backfill-fundamentals --economy

# Company fundamentals for SPY universe
just backfill-fundamentals --universe spy

# Single ticker
just backfill-fundamentals --tickers AAPL,MSFT

# Everything
just backfill-fundamentals --universe spy --economy
```

---

## Migration Summary

| Migration | Table | Action | Notes |
|---|---|---|---|
| `004_financials.sql` | `financials` | **Rewrite** (drops old `fundamentals`) | Wide table: income + balance + cash flow + JSON overflow |
| `002b_universe_details.sql` | `universe` | **ALTER TABLE** (add columns) | Description, employees, CIK, FIGI, etc. |
| `007_dividends.sql` | `dividends` | **New** | Per-ticker dividend history |
| `008_stock_splits.sql` | `stock_splits` | **New** | Per-ticker split history |
| `009_treasury_yields.sql` | `treasury_yields` | **New** | Daily yields, 1962–present |
| `010_inflation.sql` | `inflation` | **New** | Monthly CPI/PCE, 1947–present |
| `011_inflation_expectations.sql` | `inflation_expectations` | **New** | Monthly, 1982–present |
| `012_labor_market.sql` | `labor_market` | **New** | Monthly, 1948–present |

**Total new API calls for full backfill:** ~2,504 (2,500 company + 4 economy)
**Estimated time:** ~15 minutes
**Estimated storage:** < 100 MB (these are tiny compared to the 1-min OHLCV data)

---

## Cross-Dataset Query Examples

The real power comes from joining these tables together:

```sql
-- PE ratio from financials + latest price
SELECT f.ticker, u.name, u.sector,
    p.close AS price,
    f.diluted_eps * 4 AS annual_eps,  -- annualize quarterly EPS
    p.close / (f.diluted_eps * 4) AS pe_ratio
FROM financials f
JOIN universe u ON f.ticker = u.ticker
JOIN ohlcv_daily_mv p ON f.ticker = p.ticker
WHERE f.fiscal_period = 'Q1' AND f.fiscal_year = '2026'
AND p.day = (SELECT max(day) FROM ohlcv_daily_mv)
ORDER BY pe_ratio;

-- Earnings yield vs 10yr treasury (equity risk premium proxy)
SELECT f.ticker, 
    f.diluted_eps * 4 / p.close * 100 AS earnings_yield,
    t.yield_10_year,
    f.diluted_eps * 4 / p.close * 100 - t.yield_10_year AS equity_risk_premium
FROM financials f
JOIN ohlcv_daily_mv p ON f.ticker = p.ticker
CROSS JOIN (SELECT yield_10_year FROM treasury_yields ORDER BY date DESC LIMIT 1) t
WHERE f.fiscal_period = 'Q1' AND f.fiscal_year = '2026'
AND p.day = (SELECT max(day) FROM ohlcv_daily_mv)
ORDER BY equity_risk_premium DESC;

-- Recession indicator: inverted yield curve + rising unemployment
SELECT t.date, t.yield_10_year - t.yield_2_year AS spread_2s10s,
    l.unemployment_rate
FROM treasury_yields t
JOIN labor_market l ON toStartOfMonth(t.date) = l.date
WHERE t.date >= '2019-01-01'
ORDER BY t.date;
```
