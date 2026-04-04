# SEC EDGAR Ingestion Pipeline — Full Plan

> **Goal:** Pull everything useful from SEC EDGAR in one pipeline. Five tables, two API calls per ticker as the base, plus targeted XML fetches for insider trades and institutional holders.

## What SEC EDGAR Gives Us

Free. No API key. Just a `User-Agent` header. Rate limit: 10 req/sec.

### Endpoints

| Endpoint | Returns |
|----------|---------|
| `/api/xbrl/companyfacts/CIK{cik}.json` | Every GAAP financial fact ever filed |
| `/submissions/CIK{cik}.json` | All filing metadata, company info, officer/insider filings |
| `/Archives/edgar/data/{cik}/{accession}/{doc}` | Individual filing documents (Form 4 XML, 13G XML, etc.) |
| `/files/company_tickers_exchange.json` | Ticker → CIK + exchange mapping (10,433 entries) |

### Filing Links

Every filing gets a permanent URL. We store the `accession_number` and can construct two links:

```
Index page:  https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/
Document:    https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/{primary_doc}
```

Example (AAPL 10-K):
- Index: `https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/`
- Doc: `https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm`

We store `cik`, `accession_number`, and `primary_doc` in every table so the SDK/UI can construct clickable links.

---

## Five Tables

### 1. `financials` (already exists — migration 004)

Source: `/api/xbrl/companyfacts` — one call per company returns all years, all quarters.

We extract ~35 GAAP line items per period using a fallback concept map (companies use different names for the same item — e.g. `Revenues` vs `RevenueFromContractWithCustomerExcludingAssessedTax`). All line items for one period go into a single JSON blob.

**Reuses existing table.** We set `source = 'sec_edgar'`. ReplacingMergeTree dedupes.

```sql
-- Already exists: migration 004_fundamentals.sql
CREATE TABLE IF NOT EXISTS financials (
    ticker         LowCardinality(String),
    period_end     Date,
    report_type    Enum8('income' = 1, 'balance' = 2, 'cashflow' = 3),
    fiscal_year    UInt16,
    fiscal_quarter Enum8('Q1' = 1, 'Q2' = 2, 'Q3' = 3, 'Q4' = 4, 'FY' = 5),
    data           String,                                    -- JSON blob: {"revenue": 394328000000, "net_income": 93736000000, ...}
    source         LowCardinality(String) DEFAULT 'sec_edgar',
    ingested_at    DateTime               DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYear(period_end)
ORDER BY (ticker, period_end, report_type)
```

**Line items extracted (stored in `data` JSON):**

Income: `revenue`, `cost_of_revenue`, `gross_profit`, `operating_expenses`, `operating_income`, `net_income`, `eps_basic`, `eps_diluted`, `research_and_dev`, `sga_expenses`, `income_tax`, `interest_expense`, `ebitda`

Balance: `total_assets`, `current_assets`, `noncurrent_assets`, `total_liabilities`, `current_liabilities`, `noncurrent_liabilities`, `stockholders_equity`, `retained_earnings`, `cash_and_equivalents`, `long_term_debt`, `short_term_debt`, `inventory`, `accounts_receivable`, `accounts_payable`, `goodwill`

Cash Flow: `operating_cash_flow`, `investing_cash_flow`, `financing_cash_flow`, `capex`, `dividends_paid`, `buybacks`, `depreciation_amortization`

Per-Share: `dividends_per_share`, `shares_outstanding`

---

### 2. `sec_filings` (new — migration 015)

Source: `/submissions` — already fetched, zero extra calls.

Tracks every filing for every company. Powers "when did they file earnings?", "show me all 8-Ks this week", and provides the link to every document.

```sql
CREATE TABLE IF NOT EXISTS sec_filings (
    ticker              LowCardinality(String),
    cik                 String,
    accession_number    String,                                -- e.g. "0000320193-25-000079"
    form_type           LowCardinality(String),                -- 10-K, 10-Q, 8-K, 4, SC 13G, DEF 14A, etc.
    filed_date          Date,
    report_date         Nullable(Date),                        -- period covered (null for some forms)
    primary_doc         String,                                -- filename for direct link
    primary_doc_desc    Nullable(String),                      -- "10-K", "FORM 4", etc.
    items               Nullable(String),                      -- 8-K item codes: "2.02,9.01"
    is_xbrl             Bool                DEFAULT false,
    filing_url          String              DEFAULT '',        -- constructed: https://sec.gov/Archives/...
    source              LowCardinality(String) DEFAULT 'sec_edgar',
    ingested_at         DateTime            DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYear(filed_date)
ORDER BY (ticker, filed_date, form_type, accession_number)
```

---

### 3. `material_events` (new — migration 016)

Source: `/submissions` — zero extra calls. Just filters `sec_filings` to 8-K forms and expands item codes into individual rows with human-readable descriptions.

```sql
CREATE TABLE IF NOT EXISTS material_events (
    ticker              LowCardinality(String),
    cik                 String,
    accession_number    String,
    filed_date          Date,
    report_date         Nullable(Date),
    item_code           LowCardinality(String),                -- "2.02", "5.02", etc.
    item_description    LowCardinality(String),                -- "Results of Operations", "Officer Departure"
    primary_doc         String,
    filing_url          String              DEFAULT '',
    source              LowCardinality(String) DEFAULT 'sec_edgar',
    ingested_at         DateTime            DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYear(filed_date)
ORDER BY (ticker, filed_date, item_code, accession_number)
```

**8-K Item Code Map:**

| Code | Description | Signal |
|------|-------------|--------|
| 1.01 | Material Agreement | M&A, partnerships |
| 1.02 | Termination of Material Agreement | Deal fell through |
| 1.03 | Bankruptcy/Receivership | Distress |
| 2.01 | Acquisition/Disposition Completed | M&A closed |
| 2.02 | Results of Operations | Earnings release |
| 2.03 | Direct Financial Obligation Created | New debt |
| 2.05 | Restructuring/Exit Costs | Layoffs, cost-cutting |
| 2.06 | Material Impairments | Asset writedowns |
| 3.01 | Delisting Notice | Distress |
| 3.02 | Unregistered Sales of Equity | Dilution |
| 4.01 | Change of Accountant | Red flag |
| 4.02 | Non-Reliance on Prior Financials | Restatement |
| 5.02 | Officer Departure/Appointment | Leadership change |
| 5.03 | Bylaw Amendments | Governance change |
| 7.01 | Reg FD Disclosure | Forward guidance |
| 8.01 | Other Events | Catch-all |

---

### 4. `insider_trades` (new — migration 017)

Source: Form 4 XML — one extra fetch per filing. We extract **key fields only** from the XML (not full text).

Default: last 3 years of Form 4s. ~200-500 filings per company, ~1-3 transactions each.

```sql
CREATE TABLE IF NOT EXISTS insider_trades (
    ticker              LowCardinality(String),
    cik                 String,
    accession_number    String,
    filed_date          Date,
    report_date         Date,                                  -- periodOfReport from XML
    -- Reporter
    reporter_cik        Nullable(String),
    reporter_name       String,
    reporter_title      Nullable(String),                      -- "CEO", "CFO", "SVP", "Director"
    is_officer          Bool                DEFAULT false,
    is_director         Bool                DEFAULT false,
    is_ten_pct_owner    Bool                DEFAULT false,
    -- Transaction
    security_title      LowCardinality(String),                -- "Common Stock", "Restricted Stock Units"
    transaction_code    LowCardinality(String),                -- P=purchase, S=sale, M=exercise, F=tax, G=gift, A=award
    transaction_type    LowCardinality(String),                -- human-readable: "buy", "sell", "exercise", "tax_withhold", "gift", "award"
    is_derivative       Bool                DEFAULT false,     -- derivative (options) vs non-derivative (stock)
    shares              Float64,
    price               Nullable(Float64),
    value               Nullable(Float64),                     -- shares × price (computed)
    acquired_or_disposed LowCardinality(String),               -- A=acquired, D=disposed
    shares_owned_after  Nullable(Float64),
    ownership_type      LowCardinality(String),                -- D=direct, I=indirect
    -- Links
    primary_doc         String,
    filing_url          String              DEFAULT '',
    source              LowCardinality(String) DEFAULT 'sec_edgar',
    ingested_at         DateTime            DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYear(report_date)
ORDER BY (ticker, report_date, reporter_name, transaction_code, shares)
```

**Transaction code mapping:**

| Code | Type | Signal |
|------|------|--------|
| P | Open market purchase | 🟢 Bullish — insider buying with own money |
| S | Open market sale | 🔴 Bearish — insider selling |
| M | Exercise of options/RSUs | Neutral — scheduled conversion |
| F | Tax withholding on vesting | Neutral — automatic, not a real sell decision |
| G | Gift | Neutral — estate planning |
| A | Award/grant | Neutral — company compensation |
| C | Conversion of derivative | Neutral |
| J | Other | Varies |

---

### 5. `institutional_holders` (new — migration 018)

Source: SC 13G / SC 13D XML — one extra fetch per filing. ~20-40 filings per company total.

Post-2025 filings are structured XML (easy). Pre-2025 are HTML (harder, but few — we can backfill key fields or skip).

```sql
CREATE TABLE IF NOT EXISTS institutional_holders (
    ticker              LowCardinality(String),
    cik                 String,                                -- company CIK
    accession_number    String,
    filed_date          Date,
    event_date          Nullable(Date),                        -- date that triggered the filing
    -- Holder
    holder_cik          Nullable(String),                      -- institution's CIK
    holder_name         String,                                -- "The Vanguard Group", "BlackRock Inc."
    holder_type         LowCardinality(String),                -- IA=investment adviser, BD=broker-dealer, BK=bank, IC=investment company, etc.
    holder_address      Nullable(String),
    -- Position
    shares_held         Float64,
    class_percent       Nullable(Float64),                     -- percent of outstanding shares
    sole_voting_power   Nullable(Float64),
    shared_voting_power Nullable(Float64),
    sole_dispositive    Nullable(Float64),
    shared_dispositive  Nullable(Float64),
    -- Filing info
    form_type           LowCardinality(String),                -- SC 13G, SC 13G/A, SC 13D, SC 13D/A
    amendment_number    Nullable(UInt8),
    is_amendment        Bool                DEFAULT false,
    -- Links
    primary_doc         String,
    filing_url          String              DEFAULT '',
    source              LowCardinality(String) DEFAULT 'sec_edgar',
    ingested_at         DateTime            DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYear(filed_date)
ORDER BY (ticker, filed_date, holder_name, accession_number)
```

---

## Filing URL Construction

Every table stores `cik`, `accession_number`, and `primary_doc`. The SDK constructs links:

```typescript
function filingUrl(cik: string, accessionNumber: string): string {
  const nodash = accessionNumber.replace(/-/g, '');
  return `https://www.sec.gov/Archives/edgar/data/${cik.replace(/^0+/, '')}/${nodash}/`;
}

function documentUrl(cik: string, accessionNumber: string, primaryDoc: string): string {
  const nodash = accessionNumber.replace(/-/g, '');
  return `https://www.sec.gov/Archives/edgar/data/${cik.replace(/^0+/, '')}/${nodash}/${primaryDoc}`;
}
```

These generate permanent, clickable links:
- **Filing index:** `https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/`
- **Direct document:** `https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm`

---

## Pipeline Architecture

### Files

```
src/dataplat/ingestion/edgar/
├── __init__.py
├── client.py               # HTTP client (User-Agent, 100ms rate limiter, retry on 429/5xx)
│                            #   get_companyfacts(cik) → dict
│                            #   get_submissions(cik) → dict
│                            #   get_filing_doc(cik, accession, doc) → str
│
├── cik_map.py              # Ticker → CIK resolution
│                            #   Downloads company_tickers_exchange.json (cached per run)
│                            #   lookup(ticker) → (cik, exchange) | None
│
├── concepts.py             # GAAP concept extraction + fallback map
│                            #   CONCEPT_MAP: normalized_name → [gaap_variant_1, gaap_variant_2, ...]
│                            #   extract_financials(companyfacts_json) → list[FinancialPeriod]
│
├── financials.py           # Pipeline: companyfacts → financials table
├── filings.py              # Pipeline: submissions → sec_filings + material_events tables
├── insider.py              # Pipeline: Form 4 XML → insider_trades table
│                            #   Parses <nonDerivativeTransaction> and <derivativeTransaction>
│                            #   Extracts: reporter, code, shares, price, holdings
│
├── institutional.py        # Pipeline: SC 13G/13D XML → institutional_holders table
│                            #   Post-2025: structured XML (easy)
│                            #   Pre-2025: HTML (best-effort regex extraction)
│
└── transforms.py           # Shared Polars transforms + URL construction

src/dataplat/cli/
└── backfill_edgar.py       # CLI entry point

src/dataplat/db/migrations/
├── 015_sec_filings.sql
├── 016_material_events.sql
├── 017_insider_trades.sql
└── 018_institutional_holders.sql
```

### Flow Per Ticker

```
resolve ticker → CIK (from cached map)
       │
       ├──▶ GET /api/xbrl/companyfacts/CIK{cik}.json ─────▶ financials table
       │         (1 call — all financial data, all years)
       │
       └──▶ GET /submissions/CIK{cik}.json
                  │
                  ├──▶ sec_filings table (all filing metadata)
                  ├──▶ material_events table (8-K items expanded)
                  │
                  ├──▶ For each Form 4 (last 3 years):
                  │       GET /Archives/.../form4.xml ──▶ insider_trades table
                  │
                  └──▶ For each SC 13G/13D:
                          GET /Archives/.../primary_doc.xml ──▶ institutional_holders table
```

### CLI Interface

```bash
# Everything for full universe
just backfill-edgar --all --universe all

# Just financials (fastest — 1 call per ticker)
just backfill-edgar --financials --universe all

# Just filings index + material events (fast — 1 call per ticker)
just backfill-edgar --filings --universe spy

# Insider trades (slower — needs Form 4 XML fetches)
just backfill-edgar --insider --universe spy --insider-years 3

# Institutional holders (moderate — needs 13G XML fetches)
just backfill-edgar --institutional --universe spy

# Specific tickers
just backfill-edgar --all --tickers NBIS,ARM,PLTR

# Fill gaps only (tickers missing from financials)
just backfill-edgar --financials --gaps-only

# Dry run
just backfill-edgar --all --universe all --dry-run
```

### justfile

```just
# Backfill from SEC EDGAR
# Examples:
#   just backfill-edgar --all --universe all
#   just backfill-edgar --financials --tickers NBIS,ARM
#   just backfill-edgar --insider --universe spy --insider-years 3
#   just backfill-edgar --all --gaps-only
backfill-edgar *ARGS:
    uv run python -m dataplat.cli.backfill_edgar {{ARGS}}
```

---

## Performance Estimates

| Mode | API Calls / Ticker | Full Universe (8K) | Time @ 10 req/sec |
|------|-------------------|-------------------|-------------------|
| `--financials` | 1 | 8,000 | ~13 min |
| `--filings` (includes events) | 1 | 8,000 | ~13 min |
| `--financials --filings` | 2 | 16,000 | ~27 min |
| `--insider` (3yr) | ~150 avg | ~1,200,000 | ~2 hours |
| `--institutional` | ~25 avg | ~200,000 | ~30 min |
| `--all` (3yr insider) | ~178 avg | ~1,424,000 | ~2.5 hours |

### Storage (compressed in ClickHouse)

| Table | Rows (full universe) | Compressed Size |
|-------|---------------------|----------------|
| `financials` | ~1.2M | ~280 MB |
| `sec_filings` | ~8M | ~400 MB |
| `material_events` | ~600K | ~35 MB |
| `insider_trades` | ~3.2M | ~250 MB |
| `institutional_holders` | ~250K | ~20 MB |
| **Total** | **~13.3M** | **~985 MB** |

For context: your OHLCV table is already 4 GB. This is small.

---

## Dependencies

- `httpx` (already installed)
- `xml.etree.ElementTree` (stdlib) — Form 4 + 13G XML parsing
- `re` (stdlib) — pre-2025 13G HTML extraction
- No new packages needed

---

## Build Order

| Step | What | Effort |
|------|------|--------|
| 1 | `client.py` + `cik_map.py` | 30 min |
| 2 | `concepts.py` + `financials.py` + migration | 1.5 hours |
| 3 | `filings.py` (sec_filings + material_events) + migrations | 1 hour |
| 4 | `insider.py` (Form 4 XML parsing) + migration | 1.5 hours |
| 5 | `institutional.py` (13G XML parsing) + migration | 1.5 hours |
| 6 | `backfill_edgar.py` CLI + justfile | 30 min |
| 7 | Test on SPY universe, verify data quality | 1 hour |
| **Total** | | **~7-8 hours** |

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| GAAP concept names vary | Fallback map with 2-3 alternatives per line item; log unmapped |
| Some companies file IFRS not US-GAAP | Check for `ifrs-full` taxonomy; log and skip |
| Pre-2025 13G filings are HTML not XML | Best-effort regex extraction; flag `parsed_ok` column |
| Form 4 XML structure varies slightly | Defensive parsing with try/except per field |
| Submissions only has last ~1,000 filings | Sufficient for most; paginate `files` array for older |
| Rate limit (10/sec) | 100ms sleep + exponential backoff on 429 |
| CIK mapping stale for brand-new tickers | Re-download at start of each run |

## What We're NOT Getting (and Why)

| Data | Why Not (Yet) |
|------|---------------|
| **13F institutional positions** | Filed from fund CIK, not company. Need separate fund registry. Different pipeline. |
| **Proxy / exec comp (DEF 14A)** | Unstructured HTML. Would need NLP. |
| **Full 10-K/10-Q text** | Massive docs. Available via EFTS search API if needed. |
| **XBRL custom extensions** | Company-specific concepts. The ~35 standard items cover 95%. |
