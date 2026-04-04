# DataPlat: Separated Data Platform Architecture

> Key decision change: **ClickHouse + Kafka in a separate Python repo**, not embedded DuckDB in Argus.

---

## Decision Record

### What Changed

`00_architecture-notes.md` proposed an embedded DuckDB global store inside the Electron app. That works for ~10M rows of US equities, but doesn't scale to the actual target workload: huge volumes of historical tick data, real-time streaming ingestion, cross-asset analysis across equities/options/crypto/macro, and concurrent analytical queries from multiple consumers (chat LLM, agents, notebooks, future web UI).

### Why ClickHouse Over DuckDB (for the central store)


| Concern                | DuckDB (embedded)                      | ClickHouse (server)                            |
| ---------------------- | -------------------------------------- | ---------------------------------------------- |
| Historical data volume | ~10M rows fine, billions uncomfortable | Built for billions+ rows, columnar compression |
| Real-time ingestion    | No streaming — batch inserts only      | Native Kafka engine, streaming inserts         |
| Concurrent access      | Single-process, one writer             | Multi-client, concurrent reads/writes          |
| Cross-asset joins      | Works but memory-bound on large joins  | Distributed joins, materialized views          |
| Operational cost       | Zero — it's a library                  | Runs as a server process                       |
| Live aggregations      | Manual — recompute on query            | Materialized views update on insert            |


**DuckDB stays in the architecture** — it moves to the edge as a local cache/workbench layer in Argus (the existing per-conversation session DB). ClickHouse becomes the central analytical store.

### Why a Separate Repo

Argus (TypeScript/Electron) is the intelligence and UX layer. The data platform (Python) is infrastructure. Different languages, different deployment lifecycles, different concerns. Coupling them creates friction in both directions.

- **Argus** owns: LLM orchestration, conversation management, auth, artifact rendering, the agent system, desktop UX
- **DataPlat** owns: data ingestion, Kafka consumers, ClickHouse schema management, materialized views, the MCP server interface

The boundary between them is the **MCP server** — a clean, tool-based API.

---

## Two-Repo Architecture

### Data Source Boundaries

Two primary data providers with no overlap:


| Provider    | Owns                         | Data Types                                                                                                                                  |
| ----------- | ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| **Schwab**  | ALL ticker-level data — prices AND fundamentals | OHLCV history (up to 20yr daily), real-time quotes/streaming, option chains + greeks, account positions + orders, quote-level fundamentals (EPS, PE, div yield) |
| **Polygon** | Non-ticker metadata & alt data ONLY              | Company reference data (universe, SIC, sectors), news, corporate actions (dividends, splits, IPOs), short interest, Polymarket |


Additional sources: FRED (economic indicators), SEC EDGAR (filings, full financial statements).

**Schwab is the single source of truth for ALL ticker-level data — price, options, and fundamentals. Polygon is NEVER used for historical price data, OHLCV, or any per-ticker market data.** Polygon is strictly the metadata and alternative data layer (company reference, news, corporate actions, alt data). This is a hard boundary — no exceptions.

---

## Two-Repo Architecture

```
┌──────────────────────────────────────────────────────┐
│                   Data Sources                        │
│                                                       │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐ │
│  │   Schwab    │  │   Polygon   │  │  FRED / SEC  │ │
│  │  (prices,   │  │  (reference,│  │  (macro,     │ │
│  │   options,  │  │   news,     │  │   filings)   │ │
│  │   quotes,   │  │   filings,  │  │              │ │
│  │   stream)   │  │   alt data) │  │              │ │
│  └──────┬──────┘  └──────┬──────┘  └──────┬───────┘ │
└─────────┼────────────────┼────────────────┼──────────┘
          │                │                │
          ▼                ▼                ▼
┌──────────────────────────────────────────────────────┐
│                  DATAPLAT REPO (Python)               │
│                                                       │
│  ┌─────────────┐    ┌──────────────┐                 │
│  │   Kafka      │───▶│  ClickHouse  │                 │
│  │  (Redpanda)  │    │   Server     │                 │
│  └─────────────┘    └──────┬───────┘                 │
│                            │                          │
│                            │                          │
│  ┌─────────────────────────▼────────────────────┐    │
│  │              MCP Server                       │    │
│  │  (Streamable HTTP transport, port 8811)       │    │
│  │                                               │    │
│  │  Tools:                                       │    │
│  │  • query_market_data    (OHLCV, quotes)       │    │
│  │  • query_financials     (income, balance, CF)  │    │
│  │  • query_economics      (FRED, macro)          │    │
│  │  • query_universe       (ticker metadata)      │    │
│  │  • query_options        (chains, greeks)       │    │
│  │  • query_alternative    (short interest, etc.) │    │
│  │  • run_sql              (raw SQL, read-only)   │    │
│  │  • get_schema           (table definitions)    │    │
│  └───────────────────────────────────────────────┘    │
└──────────────────────────┬───────────────────────────┘
                           │ MCP (streamable HTTP)
                           ▼
┌──────────────────────────────────────────────────────┐
│                  ARGUS REPO (TypeScript)              │
│                                                       │
│  ┌──────────────────────────────────────────────┐    │
│  │          Electron Main Process                │    │
│  │                                               │    │
│  │  MCP Client ──▶ LLM Chat Orchestration        │    │
│  │                      │                        │    │
│  │              Agent System (Pi)                 │    │
│  │                      │                        │    │
│  │  DuckDB (session cache) ◀── query results     │    │
│  └──────────────────────────────────────────────┘    │
│                                                       │
│  ┌──────────────────────────────────────────────┐    │
│  │          Electron Renderer (React)            │    │
│  │                                               │    │
│  │  Chat UI → Artifacts → Forge                  │    │
│  └──────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────┘
```

---

## DataPlat Repo — Design

### Language: Python

Python is the right choice for a data platform that combines Kafka consumers, ClickHouse queries, and an MCP server interface. The ecosystem support is unmatched: `confluent-kafka`, `clickhouse-connect`, and the `mcp` SDK are all first-class Python libraries.

### Polars Over Pandas — Everywhere

**Polars is the default DataFrame library in DataPlat. Pandas is not used.**

Rationale:

- **Performance**: Polars is written in Rust, uses Apache Arrow columnar format natively, and runs multi-threaded by default. For the data volumes we're handling (millions to billions of rows), the difference vs pandas is 5-50x on typical operations.
- **Memory efficiency**: Polars uses Arrow memory layout (zero-copy, cache-friendly). Pandas copies data on most operations. When processing large historical backfills or computing materialized aggregates, this matters.
- **Lazy evaluation**: Polars' lazy API builds a query plan and optimizes it before execution (predicate pushdown, projection pushdown, join reordering). This means you can write readable transformation chains without worrying about intermediate materializations.
- **Type safety**: Polars has strict typing — no silent type coercion, no mixed-type columns, no "object" dtype. Financial data demands type correctness.
- **ClickHouse interop**: Polars reads/writes Arrow and Parquet natively. ClickHouse exports both. Zero-copy handoff between query results and DataFrames.
- **No index**: Pandas' index is a footgun for financial time-series (multi-index hell, reset_index everywhere). Polars doesn't have indexes — data is always explicit columns.

Where Polars is used in the stack:


| Layer                   | How Polars is Used                                                              |
| ----------------------- | ------------------------------------------------------------------------------- |
| Kafka consumers         | Batch incoming messages into Polars DataFrames before bulk insert to ClickHouse |
| Ingestion pipelines     | Transform raw API responses (Polygon, FRED, SEC) into clean typed DataFrames    |
| Materialized view logic | Pre-compute rolling aggregates, factor scores, derived metrics                  |
| MCP tool handlers       | Query ClickHouse → Polars DataFrame → transform/filter → return to LLM          |
| Backfill scripts        | Process years of historical data efficiently with lazy evaluation               |
| Data validation         | Schema enforcement, null checks, range validation on incoming data              |


```python
# Example: Polars lazy pipeline for computing rolling volatility
import polars as pl

volatility = (
    pl.scan_parquet("ohlcv_2024.parquet")
    .filter(pl.col("ticker").is_in(universe))
    .sort("ticker", "date")
    .with_columns(
        pl.col("close").log().diff().over("ticker").alias("log_return")
    )
    .with_columns(
        pl.col("log_return")
        .rolling_std(window_size=21)
        .over("ticker")
        .mul(252**0.5)  # annualize
        .alias("realized_vol_21d")
    )
    .collect()
)
```

**The only exception**: if a third-party library *requires* a pandas DataFrame as input (some legacy quant libraries do), convert at the boundary with `.to_pandas()` and convert back immediately. Never let pandas DataFrames propagate through the codebase.

### Project Structure

```
dataplat/
├── pyproject.toml                    # uv/hatch project config
├── .env.example                      # Required env vars
├── docker-compose.yml                # ClickHouse + Redpanda (local dev)
├── justfile                          # Task runner (just build, just ingest, etc.)
│
├── src/
│   └── dataplat/
│       ├── __init__.py
│       ├── config.py                 # Env var loading, validation
│       │
│       ├── db/
│       │   ├── client.py             # ClickHouse client singleton
│       │   ├── migrations/           # Schema migrations (numbered SQL files)
│       │   │   ├── 001_ohlcv.sql
│       │   │   ├── 002_fundamentals.sql
│       │   │   ├── 003_economics.sql
│       │   │   ├── 004_universe.sql
│       │   │   └── 005_options.sql
│       │   └── migrate.py            # Migration runner
│       │
│       ├── ingestion/
│       │   ├── base.py               # Abstract ingestion pipeline
│       │   ├── schwab/
│       │   │   ├── __init__.py
│       │   │   ├── auth.py           # Schwab OAuth 2.0 PKCE token management
│       │   │   ├── historical.py     # OHLCV backfill (up to 20yr daily candles)
│       │   │   ├── stream.py         # Real-time quote/trade WebSocket consumer
│       │   │   ├── options.py        # Option chain snapshots + greeks
│       │   │   └── accounts.py       # Positions, orders, account balances
│       │   ├── polygon/
│       │   │   ├── __init__.py
│       │   │   ├── reference.py      # Ticker universe, company details, SIC codes
│       │   │   ├── news.py           # Company + market news
│       │   │   ├── corporate.py      # Dividends, splits, IPOs
│       │   │   ├── short_interest.py # Short interest, short volume, float
│       │   │   └── polymarket.py     # Prediction market events
│       │   ├── fred.py               # FRED — economic indicators
│       │   ├── sec.py                # SEC EDGAR — filings (supplements Polygon)
│       │   └── backfill.py           # Historical backfill orchestrator
│       │
│       ├── kafka/
│       │   ├── producer.py           # Publishes raw market events
│       │   ├── consumer.py           # Base consumer with Polars batching
│       │   └── topics.py             # Topic definitions and schemas
│       │
│       ├── transforms/
│       │   ├── ohlcv.py              # OHLCV cleaning, corporate action adjustment
│       │   ├── fundamentals.py       # Financial statement normalization
│       │   ├── derived.py            # Rolling volatility, moving averages, factor scores
│       │   └── validation.py         # Schema enforcement, data quality checks
│       │
│       ├── mcp/
│       │   ├── server.py             # MCP server entry point
│       │   ├── tools/
│       │   │   ├── market_data.py    # query_market_data tool
│       │   │   ├── financials.py     # query_financials tool
│       │   │   ├── economics.py      # query_economics tool
│       │   │   ├── universe.py       # query_universe tool
│       │   │   ├── options.py        # query_options tool
│       │   │   ├── alternative.py    # query_alternative tool (short interest, etc.)
│       │   │   ├── sql.py            # run_sql tool (read-only, with guardrails)
│       │   │   └── schema.py         # get_schema tool
│       │   └── transport.py          # Streamable HTTP config
│       │
│       └── cli/
│           ├── __init__.py
│           ├── serve.py              # Start MCP server
│           ├── ingest.py             # Run ingestion pipelines
│           ├── backfill.py           # Historical backfill
│           └── migrate.py            # Run DB migrations
│
├── tests/
│   ├── conftest.py                   # ClickHouse test fixtures
│   ├── test_ingestion/
│   ├── test_transforms/
│   ├── test_mcp/
│   └── test_kafka/
│
└── scripts/
    ├── seed_universe.py              # Initial ticker universe from Polygon
    └── benchmark_queries.py          # Query performance benchmarks
```

### Package Management: uv

`[uv](https://github.com/astral-sh/uv)` for dependency management and virtual environments. Fast, Rust-based, resolves dependencies correctly. No pip, no poetry, no conda.

```toml
# pyproject.toml (key dependencies)
[project]
name = "dataplat"
requires-python = ">=3.12"
dependencies = [
    "polars>=1.0",
    "clickhouse-connect>=0.8",
    "confluent-kafka>=2.6",
    "mcp>=1.0",
    "httpx>=0.28",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "ruff>=0.8",
]
```

### Local Dev: Docker Compose

ClickHouse and Redpanda (Kafka-compatible, lighter weight) run in containers. The Python code runs on the host.

```yaml
# docker-compose.yml
services:
  clickhouse:
    image: clickhouse/clickhouse-server:latest
    ports:
      - "8123:8123"   # HTTP
      - "9000:9000"   # Native TCP
    volumes:
      - clickhouse_data:/var/lib/clickhouse
    ulimits:
      nofile:
        soft: 262144
        hard: 262144

  redpanda:
    image: redpandadata/redpanda:latest
    command:
      - redpanda start
      - --smp 1
      - --memory 1G
      - --overprovisioned
      - --kafka-addr PLAINTEXT://0.0.0.0:29092
      - --advertise-kafka-addr PLAINTEXT://localhost:29092
    ports:
      - "29092:29092"  # Kafka API
      - "8082:8082"    # Schema Registry
      - "9644:9644"    # Admin API

  redpanda-console:
    image: redpandadata/console:latest
    ports:
      - "8080:8080"
    environment:
      KAFKA_BROKERS: redpanda:29092
    depends_on:
      - redpanda

volumes:
  clickhouse_data:
```

---

## ClickHouse Schema Design

### Core Tables

```sql
-- OHLCV: The primary time-series table
-- MergeTree ordered by (ticker, date) for fast range scans per symbol
CREATE TABLE ohlcv (
    ticker      LowCardinality(String),
    date        Date,
    open        Float64,
    high        Float64,
    low         Float64,
    close       Float64,
    volume      UInt64,
    vwap        Float64,
    transactions UInt32,
    source      LowCardinality(String) DEFAULT 'schwab',
    ingested_at DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYear(date)
ORDER BY (ticker, date);

-- Fundamentals: Income statements, balance sheets, cash flow
-- Source: SEC EDGAR for full financial statements, Schwab for quote-level fundamentals
CREATE TABLE fundamentals (
    ticker       LowCardinality(String),
    period_end   Date,
    report_type  Enum8('income' = 1, 'balance' = 2, 'cashflow' = 3),
    fiscal_year  UInt16,
    fiscal_quarter Enum8('Q1' = 1, 'Q2' = 2, 'Q3' = 3, 'Q4' = 4, 'FY' = 5),
    data         String,  -- JSON blob of all line items
    source       LowCardinality(String) DEFAULT 'sec_edgar',
    ingested_at  DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYear(period_end)
ORDER BY (ticker, period_end, report_type);

-- Economic series (FRED, etc.)
CREATE TABLE economic_series (
    series_id    LowCardinality(String),
    date         Date,
    value        Float64,
    source       LowCardinality(String) DEFAULT 'fred',
    ingested_at  DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYear(date)
ORDER BY (series_id, date);

-- Ticker universe
CREATE TABLE universe (
    ticker       String,
    name         String,
    type         LowCardinality(String),  -- CS, ETF, ADRC
    exchange     LowCardinality(String),  -- XNYS, XNAS
    sector       LowCardinality(String),
    sic_code     LowCardinality(String),
    market_cap   Float64,
    active       Bool DEFAULT true,
    last_sync    Date,
    updated_at   DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY ticker;

-- Option chains (future — Schwab data)
CREATE TABLE option_chains (
    underlying   LowCardinality(String),
    expiration   Date,
    strike       Float64,
    put_call     Enum8('call' = 1, 'put' = 2),
    bid          Float64,
    ask          Float64,
    last         Float64,
    volume       UInt32,
    open_interest UInt32,
    implied_vol  Float64,
    delta        Float64,
    gamma        Float64,
    theta        Float64,
    vega         Float64,
    snapshot_at  DateTime,
    ingested_at  DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(expiration)
ORDER BY (underlying, expiration, strike, put_call, snapshot_at);
```

### Materialized Views (auto-updating aggregations)

```sql
-- Daily OHLCV rollups from tick data (when tick ingestion is added)
CREATE MATERIALIZED VIEW ohlcv_daily_mv
ENGINE = ReplacingMergeTree()
PARTITION BY toYear(date)
ORDER BY (ticker, date)
AS SELECT
    ticker,
    toDate(timestamp) AS date,
    argMin(price, timestamp) AS open,
    max(price) AS high,
    min(price) AS low,
    argMax(price, timestamp) AS close,
    sum(size) AS volume,
    sum(price * size) / sum(size) AS vwap,
    count() AS transactions
FROM ticks
GROUP BY ticker, date;

-- 21-day rolling volatility (refreshed periodically, not real-time)
-- This would be computed by a scheduled Polars job, not a ClickHouse MV
```

---

## Kafka Topic Design

### Topics


| Topic                                    | Key          | Value                        | Source                     | Consumer            |
| ---------------------------------------- | ------------ | ---------------------------- | -------------------------- | ------------------- |
| **Schwab-sourced (price/market data)**   |              |                              |                            |                     |
| `schwab.ohlcv.daily`                     | `ticker`     | OHLCV bar (JSON)             | Schwab historical API      | ClickHouse consumer |
| `schwab.quotes.realtime`                 | `ticker`     | Quote snapshot (JSON)        | Schwab streaming WebSocket | ClickHouse consumer |
| `schwab.options.chains`                  | `underlying` | Option chain + greeks (JSON) | Schwab market data API     | ClickHouse consumer |
| `schwab.accounts.positions`              | `account_id` | Position snapshot (JSON)     | Schwab accounts API        | ClickHouse consumer |
| **Polygon-sourced (reference/alt data)** |              |                              |                            |                     |
| `polygon.universe`                       | `ticker`     | Ticker metadata (JSON)       | Polygon reference API      | ClickHouse consumer |
| `polygon.news`                           | `ticker`     | News article (JSON)          | Polygon news API           | ClickHouse consumer |
| `polygon.corporate_actions`              | `ticker`     | Dividend/split/IPO (JSON)    | Polygon reference API      | ClickHouse consumer |
| `polygon.short_interest`                 | `ticker`     | Short interest data (JSON)   | Polygon / Massive API      | ClickHouse consumer |
| **Other sources**                        |              |                              |                            |                     |
| `fred.economics`                         | `series_id`  | Data point (JSON)            | FRED API                   | ClickHouse consumer |
| `sec.filings`                            | `ticker`     | Filing metadata (JSON)       | SEC EDGAR                  | ClickHouse consumer |


### Consumer Pattern

Consumers batch messages into Polars DataFrames before writing to ClickHouse. This avoids per-row inserts and leverages ClickHouse's optimal batch insert path.

```python
import polars as pl
from confluent_kafka import Consumer

class ClickHouseConsumer:
    """Base consumer that batches Kafka messages into Polars DataFrames
    and bulk-inserts into ClickHouse."""

    def __init__(self, topic: str, table: str, schema: dict, batch_size: int = 5000):
        self.topic = topic
        self.table = table
        self.schema = schema
        self.batch_size = batch_size
        self.buffer: list[dict] = []

    def process_batch(self) -> None:
        if not self.buffer:
            return

        df = pl.DataFrame(self.buffer, schema=self.schema)

        # Validate before insert
        df = self.validate(df)

        # Bulk insert via clickhouse-connect
        self.ch_client.insert_df(self.table, df.to_pandas())  # .to_pandas() only at CH boundary
        self.buffer.clear()

    def validate(self, df: pl.DataFrame) -> pl.DataFrame:
        """Override per-topic: null checks, range validation, dedup."""
        return df
```

---

## MCP Server Interface

### Transport

Streamable HTTP on port `8811`. This allows Argus to connect over HTTP as a true separate service. Also allows other consumers (notebooks, CLI tools, future web UI) to connect to the same data.

### Tool Definitions

Each MCP tool maps to a scoped ClickHouse query pattern. The tool descriptions are written for LLM consumption — they specify **when** to use each tool, not just what it does.

```python
# mcp/tools/market_data.py
from mcp.server import Server
from mcp.types import Tool

query_market_data = Tool(
    name="query_market_data",
    description=(
        "Query historical OHLCV price data for stocks and ETFs. "
        "Returns date, open, high, low, close, volume, vwap. "
        "Use for: price charts, technical analysis, return calculations, "
        "volatility analysis, price comparisons across tickers. "
        "Supports date range filtering and multi-ticker queries."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "tickers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Stock ticker symbols (e.g., ['AAPL', 'MSFT'])"
            },
            "start_date": {
                "type": "string",
                "description": "Start date (YYYY-MM-DD). Defaults to 1 year ago."
            },
            "end_date": {
                "type": "string",
                "description": "End date (YYYY-MM-DD). Defaults to today."
            },
            "interval": {
                "type": "string",
                "enum": ["1d", "1w", "1mo"],
                "description": "Bar interval. Defaults to 1d."
            }
        },
        "required": ["tickers"]
    }
)
```

```python
# mcp/tools/sql.py — raw SQL for power users and complex analysis
run_sql = Tool(
    name="run_sql",
    description=(
        "Execute a read-only SQL query against the ClickHouse analytical database. "
        "Use for: complex cross-table joins, custom aggregations, screening queries, "
        "and any analysis not covered by the specialized query tools. "
        "The database contains: ohlcv, fundamentals, economic_series, universe, option_chains. "
        "Call get_schema first if you need column names and types."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "sql": {
                "type": "string",
                "description": "Read-only SQL query (SELECT only, no mutations)"
            }
        },
        "required": ["sql"]
    }
)
```

### SQL Guardrails

The `run_sql` tool enforces read-only access:

```python
BLOCKED_KEYWORDS = {"INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE", "GRANT"}

def validate_sql(sql: str) -> str:
    """Reject any mutation. Only SELECT and WITH (CTEs) allowed."""
    tokens = sql.upper().split()
    if tokens[0] not in ("SELECT", "WITH", "EXPLAIN"):
        raise ValueError("Only SELECT queries are allowed")
    if BLOCKED_KEYWORDS & set(tokens):
        raise ValueError(f"Mutation keywords detected: {BLOCKED_KEYWORDS & set(tokens)}")
    return sql
```

---

## Argus Integration — MCP Client

### What Changes in Argus

The Argus Electron main process connects to DataPlat's MCP server as a client. This replaces the current domain services that call external APIs directly.

**Removed (over time):**

- `electron/domains/financials/` — replaced by `query_financials` MCP tool
- `electron/domains/pricing/` — replaced by `query_market_data` MCP tool
- `electron/domains/economics/` — replaced by `query_economics` MCP tool
- `electron/domains/short_interest/` — replaced by `query_alternative` MCP tool
- `electron/domains/corporate_actions/` — merged into `query_market_data` / `query_universe`
- `electron/domains/news/` — kept (real-time, not historical — still hits Polygon API directly)
- `electron/domains/fred/` — replaced by `query_economics` MCP tool

**Stays in Argus:**

- `electron/domains/chat/` — LLM orchestration, tool registry, streaming
- `electron/domains/conversations/` — chat history CRUD
- `electron/domains/settings/` — API key management
- `electron/domains/schwab/` — OAuth flow, account auth (data flows through DataPlat after auth)
- `electron/agents/` — Pi agent system (agents use MCP tools like the chat LLM does)
- DuckDB session cache — per-conversation caching of MCP query results

**New in Argus:**

- MCP client configuration in settings (host, port, connection status)
- Tool registry discovers tools from MCP server at startup (dynamic, not hardcoded)
- Fallback mode: if MCP server is unavailable, fall back to direct API calls (graceful degradation)

### MCP Client in Electron

```typescript
// electron/mcp/client.ts
import { Client } from "@modelcontextprotocol/sdk/client";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp";

export async function createDataPlatClient(): Promise<Client> {
  const client = new Client({ name: "argus", version: "1.0.0" });

  const transport = new StreamableHTTPClientTransport(
    new URL("http://localhost:8811/mcp")
  );

  await client.connect(transport);
  return client;
}
```

### Tool Discovery

Instead of hardcoded tool definitions in `tool-defs.ts`, Argus discovers available tools from the MCP server:

```typescript
// On startup or reconnect
const tools = await mcpClient.listTools();
// Register each tool in the chat LLM's tool list
// Tool descriptions come from DataPlat — Argus doesn't define them
```

This means adding a new dataset to ClickHouse + adding an MCP tool in DataPlat automatically makes it available to the LLM in Argus with **zero code changes** in Argus.

---

## Migration Path

This is not a big-bang migration. The two systems coexist and domains move over incrementally.

### Phase A: Stand up DataPlat (greenfield)

1. Create the `dataplat` repo with the structure above
2. Docker Compose for ClickHouse + Redpanda
3. Schema migrations for core tables (ohlcv, fundamentals, economics, universe, option_chains)
4. Schwab OAuth flow + token management (the auth foundation for all market data)
5. Schwab historical ingestion — backfill OHLCV data (daily candles, up to 20yr)
6. Polygon reference ingestion — ticker universe, company metadata, sectors
7. MCP server with `query_market_data` and `run_sql` tools
8. Verify: LLM can query historical price data through MCP

### Phase B: Connect Argus

1. Add MCP client to Argus Electron main process
2. Add DataPlat MCP tools to the chat LLM's tool registry alongside existing tools
3. Both paths work — LLM can use either MCP tools or existing API-call tools
4. Verify: same questions get better answers with historical data context

### Phase C: Migrate Domains

1. Move `pricing` queries to `query_market_data` — remove Polygon API calls from Argus
2. Move `financials` queries to `query_financials` — remove Massive API calls from Argus
3. Move `economics` queries to `query_economics` — remove FRED API calls from Argus
4. Each migration: verify feature parity, then delete the old domain

### Phase D: Streaming + Options

1. Schwab streaming WebSocket → Kafka producer for real-time quotes/trades
2. Schwab option chain snapshots → scheduled ingestion into ClickHouse
3. Kafka consumers write streaming data to ClickHouse
4. MCP tools return live data (latest from ClickHouse, not cached)
5. Remove remaining direct API calls from Argus (Polygon reference calls may persist for news, which is real-time and not worth storing)

---

## Environment Variables

### DataPlat


| Variable                  | Required | Description                                                     |
| ------------------------- | -------- | --------------------------------------------------------------- |
| `CLICKHOUSE_HOST`         | Yes      | ClickHouse server host (default: `localhost`)                   |
| `CLICKHOUSE_PORT`         | Yes      | ClickHouse HTTP port (default: `8123`)                          |
| `CLICKHOUSE_DATABASE`     | Yes      | Database name (default: `dataplat`)                             |
| `KAFKA_BOOTSTRAP_SERVERS` | Yes      | Kafka broker address (default: `localhost:29092`)               |
| `SCHWAB_CLIENT_ID`        | Yes      | Schwab OAuth app client ID                                      |
| `SCHWAB_CLIENT_SECRET`    | Yes      | Schwab OAuth app client secret                                  |
| `SCHWAB_REDIRECT_URI`     | Yes      | OAuth callback URI (default: `https://127.0.0.1:5556/callback`) |
| `POLYGON_API_KEY`         | Yes      | Polygon.io API key (reference/alt data only)                    |
| `FRED_API_KEY`            | Yes      | FRED economic data API key                                      |
| `MCP_SERVER_PORT`         | No       | MCP server port (default: `8811`)                               |


### Argus (additions)


| Variable           | Required | Description                                                    |
| ------------------ | -------- | -------------------------------------------------------------- |
| `DATAPLAT_MCP_URL` | No       | DataPlat MCP server URL (default: `http://localhost:8811/mcp`) |


---

## Key Decisions

1. **ClickHouse over DuckDB for central store** — Server-based, handles streaming ingestion and concurrent access. DuckDB stays as edge cache in Argus.
2. **Separate repo, separate language** — Python for data infrastructure, TypeScript for UX. Clean boundary at MCP.
3. **Polars over pandas — everywhere** — Performance, memory efficiency, type safety, lazy evaluation. Pandas is not used in DataPlat.
4. **Schwab for all market data, Polygon for everything else** — Clean provider split with zero overlap. Schwab owns OHLCV, quotes, streaming, options. Polygon owns reference data, news, corporate actions, alt data.
5. **No Parquet storage layer (no Iceberg)** — ClickHouse MergeTree handles storage natively. Parquet is used only as an interchange format for bulk imports/exports, not as the storage engine.
6. **Redpanda over Apache Kafka** — Kafka-compatible API, simpler operations, single binary. Drop-in replacement if we ever need full Kafka.
7. **MCP as the interface** — Tool-based API that LLMs understand natively. Auto-discovery means zero Argus changes when DataPlat adds capabilities.
8. **Streamable HTTP transport** — Argus connects over HTTP, not stdio. Allows multiple clients and independent lifecycles.
9. **Incremental migration** — Both systems coexist. Domains move over one at a time. No big-bang cutover.
10. `**run_sql` with guardrails** — Power tool for complex analysis. Read-only, keyword-blocked, with `get_schema` for discoverability.
11. `**uv` for Python packaging** — Fast, correct, Rust-based. No pip/poetry/conda complexity.
12. **Docker Compose for local dev** — ClickHouse and Redpanda in containers, Python on host. Simple `docker compose up` to start.

