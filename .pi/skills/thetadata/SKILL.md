---
name: thetadata
description: >
  ThetaData historical options data API (v3) — EOD greeks, IV surfaces, open interest,
  and OHLCV for US equity and index options. Used for the one-time 8-year options
  backfill into ClickHouse. After backfill completes, Schwab takes over for daily
  ongoing snapshots. Use this skill when working on: ThetaData API calls, the options
  backfill pipeline, ThetaTerminal setup, historical greeks/IV ingestion, or any code
  in ingestion/thetadata/. Also trigger when discussing options data shapes, the
  option_chains ClickHouse table, or IV surface history.
---

# ThetaData Skill

## Purpose

ThetaData provides **historical** options data with pre-computed greeks and implied volatility going back 8+ years. This is the **one-time backfill source** for the `option_chains` table in ClickHouse. After the backfill, Schwab's live option chain API takes over for daily EOD snapshots going forward.

## Architecture Boundary

| Provider | Role | Ongoing? |
|---|---|---|
| **ThetaData** | Historical options backfill (8yr of EOD greeks/IV/OI) | No — one-time $80 subscription, cancel after backfill |
| **Schwab** | Daily EOD option chain snapshots (greeks/IV/OI) going forward | Yes — ongoing |
| **Polygon** | Options contract reference metadata (strikes, expirations, exercise style) | Yes — periodic sync |

## ThetaTerminal v3 (Required)

ThetaData requires **Theta Terminal v3** — a Java server that runs locally and serves the v3 REST API + MCP server.

**IMPORTANT: Must be v3, not v2.** The v2 terminal (port 25510, `/v2/` endpoints) does NOT support:
- `expiration=*` wildcard (get entire chain in one request)
- MCP server on port 25503
- `/v3/` URL scheme
- NDJSON / CSV response formats
- `strike_range` and `max_dte` filters

### Setup

```bash
# Requires Java 17+ (class file version 61.0)
brew install openjdk@17

# Add credentials to argus-dataplat/.env
THETADATA_USERNAME=your_email
THETADATA_PASSWORD=your_password
```

### Running

```bash
cd argus-dataplat

# Start (blocks terminal — runs Java server)
just thetadata up

# Stop
just thetadata down
```

### Ports (v3)

| Port | Protocol | Purpose |
|---|---|---|
| **25503** | HTTP REST + MCP SSE | v3 REST API + MCP server — **all queries go here** |

### MCP Server

Theta Terminal v3 exposes an MCP server at `http://127.0.0.1:25503/mcp/sse` (SSE transport). This is already configured in `.claude/mcp.json` and `.pi/mcp.json`. The MCP lets the LLM discover and call ThetaData endpoints via natural language.

## v3 REST API Reference

Base URL: `http://127.0.0.1:25503/v3`

### Response Formats

All endpoints support four formats via the `format` query param:

| Format | Content-Type | Use Case |
|---|---|---|
| `csv` (default) | `text/csv` | Bulk download, pipe to ClickHouse |
| `json` | `application/json` | Structured parsing |
| `ndjson` | `application/x-ndjson` | Streaming, line-by-line processing |
| `html` | `text/html` | Browser preview |

### Key Endpoints for Backfill

#### 1. EOD Greeks (PRIMARY — the money endpoint)

```
GET /v3/option/history/greeks/eod?symbol={underlying}&expiration={YYYYMMDD|*}&start_date={YYYYMMDD}&end_date={YYYYMMDD}
```

**`expiration=*` returns ALL contracts for the underlying in ONE request.**
(When using `expiration=*`, must request day-by-day: `start_date == end_date`)

Optional filters:
- `strike={price|*}` — specific strike in dollars (e.g., `200.00`) or `*` for all (default)
- `right={call|put|both}` — filter by right (default: `both`)
- `max_dte={int}` — only contracts with DTE ≤ this value
- `strike_range={int}` — only N strikes above/below spot + ATM

**Response fields (one row per contract per day):**

```
symbol, expiration, strike, right, timestamp,
open, high, low, close, volume, count,
bid_size, bid_exchange, bid, bid_condition,
ask_size, ask_exchange, ask, ask_condition,
delta, theta, vega, rho, epsilon, lambda, gamma,
vanna, charm, vomma, veta, vera, speed, zomma, color, ultima,
d1, d2, dual_delta, dual_gamma,
implied_vol, iv_error,
underlying_timestamp, underlying_price
```

**JSON response structure (grouped by contract):**
```json
{
  "response": [
    {
      "contract": {"symbol": "AAPL", "strike": 220.0, "right": "CALL", "expiration": "2024-11-08"},
      "data": [
        {
          "timestamp": "2024-11-04T15:59:59.828",
          "open": 3.90, "high": 4.85, "low": 3.35, "close": 4.15,
          "volume": 7425, "count": 1511,
          "bid": 4.10, "ask": 4.25, "bid_size": 9, "ask_size": 12,
          "delta": 0.6083, "gamma": 0.0495, "theta": -0.3892,
          "vega": 8.9221, "rho": 1.4334,
          "vanna": -0.2765, "charm": 3.6779, "vomma": 1.7667, "veta": 0.0149,
          "epsilon": -1.4791, "lambda": 32.3623,
          "vera": 0.0, "speed": 0.0, "zomma": 0.0, "color": -0.0163, "ultima": -15.6407,
          "d1": 0.275, "d2": 0.2401, "dual_delta": -0.5945, "dual_gamma": 0.0,
          "implied_vol": 0.3334, "iv_error": 0.0001,
          "underlying_price": 221.87, "underlying_timestamp": "2024-11-04T17:15:28.71"
        }
      ]
    }
  ]
}
```

**NDJSON format (flat, one line per contract-day — ideal for streaming into ClickHouse):**
```
{"symbol":"AAPL","strike":220.000,"right":"CALL","expiration":"2024-11-08","delta":0.6083,"gamma":0.0495,"theta":-0.3892,"vega":8.9221,"implied_vol":0.3334,...}
```

#### 2. Open Interest

```
GET /v3/option/history/open_interest?symbol={underlying}&expiration={YYYYMMDD|*}&date={YYYYMMDD}
```

Also supports `expiration=*` for full chain. Returns one row per contract:
```
symbol, expiration, strike, right, timestamp, open_interest
```

#### 3. EOD (OHLCV + Quote, no greeks)

```
GET /v3/option/history/eod?symbol={underlying}&expiration={YYYYMMDD|*}&start_date={YYYYMMDD}&end_date={YYYYMMDD}
```

Supports `expiration=*`. Returns OHLCV + bid/ask without greeks. Useful if you only need price/volume data.

### Discovery Endpoints

#### List Expirations
```
GET /v3/option/list/expirations?symbol={underlying}
```

#### List Strikes
```
GET /v3/option/list/strikes?symbol={underlying}&expiration={YYYYMMDD}
```

#### List Symbols (all option roots)
```
GET /v3/option/list/symbols
```

### Data Format Notes

**v3 vs v2 differences:**
- Strikes are **dollars** (e.g., `200.00`), NOT tenths-of-cent integers
- Dates accept `YYYY-MM-DD` or `YYYYMMDD` format
- `right` uses `call`/`put`/`both` (lowercase strings), not `C`/`P`
- `expiration=*` wildcard for full chain requests
- Responses include `symbol`, `expiration`, `strike`, `right` in every row (self-describing)
- JSON responses group data by contract: `{ "contract": {...}, "data": [...] }`

## Backfill Strategy (v3)

The `expiration=*` wildcard changes everything. Instead of one request per contract, we get one request per underlying per day.

**Algorithm:**
```
For each underlying in universe:
  For each trading day in 8-year window:
    GET /v3/option/history/greeks/eod?symbol={underlying}&expiration=*&start_date={date}&end_date={date}&format=ndjson
    → Stream NDJSON lines into Polars DataFrame
    → Bulk insert into ClickHouse

    GET /v3/option/history/open_interest?symbol={underlying}&expiration=*&date={date}&format=ndjson
    → Join OI onto greeks DataFrame by (symbol, expiration, strike, right)
    → Insert
```

**Request count:**
```
500 underlyings × 2,000 trading days × 2 endpoints = 2,000,000 requests
At 5 req/sec = ~111 hours = ~4.6 days
At 10 req/sec = ~56 hours = ~2.3 days
```

Feasible within a 1-month subscription. No need for `strike_range` or `max_dte` filters — just grab everything.

## Rate Limits

- **Unlimited requests** on both Standard and Pro plans
- Throughput bounded by ThetaTerminal processing speed
- No API-level rate limiting — go as fast as the server responds
- Test concurrency: ThetaTerminal may handle parallel requests

## Subscription

| Plan | Price | History | Key Feature |
|---|---|---|---|
| **Options Standard** | $80/mo | 8 years | Option Chain Snapshots — sufficient for backfill |
| Options Pro | $160/mo | 12 years | Option Root Snapshots + stream every trade |

**Recommendation:** Standard at $80/mo. Subscribe, backfill, cancel before month 2.

## Relationship to Other Skills

| Skill | Relationship |
|---|---|
| **dataplat** | ThetaData feeds the `option_chains` table in ClickHouse. Pipeline code lives in `argus-dataplat/src/dataplat/ingestion/thetadata/` |
| **massive-api** | Polygon provides options contract reference metadata (strikes, expirations). ThetaData provides the actual market data (greeks, IV, OI). |
| **duckdb-data-layer** | DuckDB is the edge cache. Historical options data lives in ClickHouse, not DuckDB. |

## Files

```
argus-dataplat/
├── src/dataplat/ingestion/thetadata/
│   ├── __init__.py
│   ├── options.py          # EOD greeks + OI backfill pipeline
│   └── client.py           # HTTP client wrapper for v3 REST API
├── justfile                # `just thetadata up/down`
├── .env                    # THETADATA_USERNAME, THETADATA_PASSWORD
└── OPTIONS_BACKFILL_PLAN.md
```

## OpenAPI Spec

The full v3 OpenAPI spec is at `.pi/skills/thetadata/openapiv3.yaml`. Use it as the authoritative reference for all endpoint parameters, response schemas, and sample URLs.
