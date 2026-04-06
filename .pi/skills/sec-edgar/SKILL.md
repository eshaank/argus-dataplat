---
name: sec-edgar
description: >
  SEC EDGAR ingestion pipeline — financials, dilution tracking, insider trades (Form 4),
  institutional holders (SC 13G/13D), material events (8-K), and filing metadata.
  Use this skill when working on: SEC EDGAR API calls, the edgar/ ingestion directory,
  GAAP concept mapping, Form 4 XML parsing, 13G/13D parsing, dilution metrics (warrants,
  convertibles, options pool, authorized headroom), the financials ClickHouse table,
  sec_filings/material_events/insider_trades/institutional_holders tables, or any of the
  v_dilution_snapshot / v_insider_* / v_filings_* / v_events_* convenience views.
  Also trigger when discussing financial statement extraction, insider trading signals,
  or institutional ownership data.
---

# SEC EDGAR Skill

## Purpose

SEC EDGAR is the **canonical source** for company financials, replacing Polygon. It also provides insider trades, institutional holdings, material events, and a complete filing index — all free, no API key, from structured XBRL JSON and XML.

## Architecture Boundary

| Provider | Role | Tables |
|---|---|---|
| **SEC EDGAR** | Financials (income, balance, cashflow, dilution), insider trades, institutional holders, material events, filing index | `financials`, `sec_filings`, `material_events`, `insider_trades`, `institutional_holders` |
| **Polygon** | Dividends, splits, universe enrichment (NOT financials) | `dividends`, `stock_splits`, `universe` |
| **Schwab** | Ongoing OHLCV, quotes, options | `ohlcv`, `option_chains` |

## Plan Document

**`docs/SEC_EDGAR_PLAN.md`** — Full plan with schemas, API endpoints, performance estimates, risks.

## SEC EDGAR API Endpoints

| Endpoint | Returns | Rate Limit |
|----------|---------|------------|
| `data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json` | Every GAAP financial fact ever filed | 10 req/sec |
| `data.sec.gov/submissions/CIK{cik}.json` | All filing metadata + company info | 10 req/sec |
| `www.sec.gov/Archives/edgar/data/{cik}/{accession}/{doc}` | Individual filing documents (Form 4 XML, 13G XML) | 10 req/sec |
| `www.sec.gov/files/company_tickers_exchange.json` | Ticker → CIK + exchange mapping (10,433 entries) | Bulk file |

**Auth:** None. Just a `User-Agent` header set via `SEC_EDGAR_USER_AGENT` env var.

## Code Structure

```
src/dataplat/ingestion/edgar/
├── __init__.py
├── client.py           # HTTP client: rate limiter (100ms), retry on 429/5xx
│                       #   make_client(), get_companyfacts(), get_submissions()
│                       #   get_filing_doc(), get_filing_index()
│                       #   build_filing_url(), build_document_url()
│
├── cik_map.py          # CIKMap class: downloads + caches ticker→CIK mapping
│                       #   .load(), .lookup(ticker), .cik(ticker)
│                       #   Cache: .edgar_cik_map.json (gitignored)
│
├── concepts.py         # GAAP concept extraction
│                       #   CONCEPT_MAP: 65+ normalized fields → GAAP concept fallbacks
│                       #   extract_financials(companyfacts) → list[dict]
│                       #   Handles: GAAP naming variants, 10-K/10-Q/20-F filtering
│
├── financials.py       # Pipeline: companyfacts → financials table
│                       #   run_financials_backfill(tickers, cik_map, client)
│
├── filings.py          # Pipeline: submissions → sec_filings + material_events
│                       #   run_filings_backfill(tickers, cik_map, client)
│                       #   ITEM_CODE_MAP: 8-K item codes → descriptions
│
├── insider.py          # Pipeline: Form 4 XML → insider_trades table
│                       #   parse_form4_xml(xml_text) → list[dict]
│                       #   run_insider_backfill(tickers, years, cik_map, client)
│                       #   TX_CODE_MAP: P=buy, S=sell, M=exercise, F=tax, etc.
│
└── institutional.py    # Pipeline: SC 13G/13D XML → institutional_holders
                        #   parse_13g_xml(xml_text) → dict (structured XML, post-2025)
                        #   _try_parse_html_13g(html) → dict (best-effort, pre-2025)
                        #   run_institutional_backfill(tickers, cik_map, client)
```

## GAAP Concept Map

The `CONCEPT_MAP` in `concepts.py` maps ~65 normalized field names to ordered lists of GAAP concept alternatives. First match wins. Categories:

| Category | Fields | Example Concepts |
|----------|--------|-----------------|
| **Income** | revenue, cost_of_revenue, gross_profit, operating_expenses, operating_income, net_income, eps, R&D, SG&A, tax, interest, ebitda | `RevenueFromContractWithCustomerExcludingAssessedTax`, `Revenues`, `SalesRevenueNet` |
| **Balance** | assets (total/current/noncurrent), liabilities, equity, retained_earnings, debt (long/short), cash, inventory, AR, AP, goodwill | `Assets`, `StockholdersEquity`, `CashAndCashEquivalentsAtCarryingValue` |
| **Cash Flow** | operating/investing/financing cash flow, capex, dividends_paid, D&A | `NetCashProvidedByUsedInOperatingActivities` |
| **Dilution** | shares_outstanding/issued/authorized, weighted avg basic/diluted, SBC, buyback shares/value, options exercised, RSU vested/unvested, antidilutive, dividends_per_share, issuance_proceeds | `CommonStockSharesOutstanding`, `ShareBasedCompensation`, `PaymentsForRepurchaseOfCommonStock` |
| **Authorized Headroom** | shares_authorized, preferred_authorized, stock_plan_authorized, buyback_program_authorized | `CommonStockSharesAuthorized`, `StockRepurchaseProgramAuthorizedAmount1` |
| **Warrants** | warrants_outstanding, exercise_price, shares_callable, fair_value, proceeds | `ClassOfWarrantOrRightOutstanding`, `ClassOfWarrantOrRightExercisePriceOfWarrantsOrRights1` |
| **Convertible Debt** | convertible_debt (total/current), conversion_price/ratio, proceeds, repayments, shares_from_conversion | `ConvertibleDebt`, `DebtInstrumentConvertibleConversionPrice1` |
| **Options Pool** | options_outstanding, exercisable, weighted_avg_price, intrinsic_value | `ShareBasedCompensationArrangementByShareBasedPaymentAwardOptionsOutstandingNumber` |

**FUTURE:** S-3 shelf capacity, ATM offering remaining — requires filing text parsing (NLP).

## Tables

### financials (migration 019)

Canonical financial data — replaces Polygon. Wide table with ~65 explicit columns covering income, balance, cashflow, dilution, warrants, convertibles, options pool. Plus `filing_url` for clickable SEC links.

- **Source:** `companyfacts` API (1 call per company = all years, all quarters)
- **Key:** `(ticker, period_end, fiscal_period)`
- **Source tag:** `source = 'sec_edgar'`

### sec_filings (migration 015)

Every filing for every company — 10-K, 10-Q, 8-K, Form 4, 13G, S-3, 424B, etc.

- **Source:** `submissions` API (1 call per company)
- **Key:** `(ticker, filed_date, form_type, accession_number)`
- **Use:** "When did they file earnings?", filing type filtering, document links

### material_events (migration 016)

8-K items expanded into individual rows with human-readable descriptions.

- **Source:** `submissions` API (extracted from 8-K filings)
- **Key:** `(ticker, filed_date, item_code, accession_number)`
- **Item codes:** 2.02=Earnings, 5.02=Officer change, 2.05=Restructuring, etc.

### insider_trades (migration 017)

Form 4 transactions — key info extracted from XML.

- **Source:** Form 4 XML (1 fetch per filing, default last 3 years)
- **Key:** `(ticker, report_date, reporter_name, transaction_code, shares)`
- **Transaction codes:** P=buy, S=sell, M=exercise, F=tax_withhold, G=gift, A=award

### institutional_holders (migration 018)

SC 13G/13D institutional ownership — Vanguard, BlackRock, etc.

- **Source:** 13G/13D XML (structured post-2025, HTML best-effort pre-2025)
- **Key:** `(ticker, filed_date, holder_name, accession_number)`
- **Fields:** shares_held, class_percent, voting/dispositive power

## Convenience Views (migration 020)

| View | Query Pattern |
|------|--------------|
| `v_dilution_snapshot` | `SELECT * FROM v_dilution_snapshot WHERE ticker = 'LCID'` |
| `v_latest_financials` | `SELECT * FROM v_latest_financials WHERE ticker = 'AAPL'` |
| `v_filings_10k` | `SELECT * FROM v_filings_10k WHERE ticker = 'AAPL'` |
| `v_filings_registration` | `SELECT * FROM v_filings_registration WHERE ticker = 'LCID'` — S-1, S-3, S-8 |
| `v_filings_prospectus` | `SELECT * FROM v_filings_prospectus WHERE ticker = 'LCID'` — 424B (actual issuance) |
| `v_insider_buys_sells` | `SELECT * FROM v_insider_buys_sells WHERE ticker = 'AAPL'` — P/S only |
| `v_insider_monthly` | `SELECT * FROM v_insider_monthly WHERE ticker = 'AAPL'` — net buying signal |
| `v_events_timeline` | `SELECT * FROM v_events_timeline WHERE ticker = 'AAPL' LIMIT 20` |
| `v_institutional_latest` | `SELECT * FROM v_institutional_latest WHERE ticker = 'AAPL'` |

## CLI

```bash
# Everything for full universe
just backfill-edgar --all --universe all

# Just financials (fastest — 1 call per ticker, ~13 min for 8K tickers)
just backfill-edgar --financials --universe all

# Filings + material events (1 call per ticker)
just backfill-edgar --filings --universe spy

# Insider trades (slower — Form 4 XML fetches)
just backfill-edgar --insider --universe spy --insider-years 3

# Institutional holders (13G/13D XML fetches)
just backfill-edgar --institutional --universe spy

# Fill gaps only
just backfill-edgar --financials --gaps-only

# Specific tickers
just backfill-edgar --all --tickers NBIS,ARM,PLTR

# Dry run
just backfill-edgar --all --universe all --dry-run
```

## Filing URL Construction

Every table stores `cik`, `accession_number`, `primary_doc`. Build links:

```python
from dataplat.ingestion.edgar.client import build_filing_url, build_document_url

# Filing index page
url = build_filing_url(cik, accession_number)
# → https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/

# Direct document
url = build_document_url(cik, accession_number, primary_doc)
# → https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm
```

## Common Patterns

### Adding a New GAAP Concept

1. Add entry to `CONCEPT_MAP` in `concepts.py` — field name → list of GAAP concept names
2. Add matching column to `019_financials_v2.sql` migration (requires table recreate)
3. Add column name to `FINANCIALS_COLUMNS` in `financials.py`
4. Re-run: `just backfill-edgar --financials --tickers AAPL`

### Handling GAAP Naming Variants

Companies use different concept names for the same item. The fallback list in `CONCEPT_MAP` handles this — first match wins. If a new variant is found:
1. Check what the company actually files: `data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json`
2. Add the variant to the appropriate list in `CONCEPT_MAP`

### Pre-2025 vs Post-2025 Filing Formats

- **Post-2025 13G/13D:** Structured XML (`primary_doc.xml`) — clean parsing via `parse_13g_xml()`
- **Pre-2025 13G/13D:** Unstructured HTML — best-effort regex via `_try_parse_html_13g()`
- **Form 4:** Always structured XML (`ownershipDocument`) — reliable parsing

## Performance

| Mode | Calls/Ticker | Full Universe (8K) | Time |
|------|-------------|-------------------|------|
| `--financials` | 1 | 8,000 | ~13 min |
| `--filings` | 1 | 8,000 | ~13 min |
| `--insider` (3yr) | ~150 | ~1.2M | ~2 hours |
| `--institutional` | ~25 | ~200K | ~30 min |
| `--all` | ~178 | ~1.4M | ~2.5 hours |

Storage: ~985 MB compressed for full universe (all 5 tables).
