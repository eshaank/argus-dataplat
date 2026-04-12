# ClickHouse Kafka Integration & Real-Time Streaming Specification

> Research findings on ClickHouse's native Kafka integration vs. external Python consumers, and real-time query patterns for the DataPlat project.

**Researcher:** clickhouse-streaming-researcher  
**Date:** April 10, 2026  
**Context:** DataPlat uses ClickHouse 24.8, sophisticated ingestion pipelines via schwabdev/Polygon/SEC EDGAR, evaluating Kafka/Redpanda integration for streaming backbone.

---

## Executive Summary

ClickHouse's native Kafka table engine offers **simplified architecture** for streaming ingestion but comes with **significant tradeoffs** in error handling, schema evolution, and monitoring compared to external Python consumers. For DataPlat's use case with complex financial data transformations and robust error handling requirements, **external Python consumers remain the recommended approach**, with Kafka providing the streaming backbone and ClickHouse as the analytical store.

**Key Finding:** ClickHouse Kafka engine works best for simple, schema-stable use cases. Financial data requires sophisticated error handling, DLQ patterns, and transform logic that external consumers handle better.

---

## 1. ClickHouse Kafka Table Engine Analysis

### 1.1 How It Works

ClickHouse can directly consume from Kafka topics using the `Kafka` table engine:

```sql
CREATE TABLE kafka_ohlcv (
    ticker String,
    timestamp DateTime64(3, 'UTC'),
    open Float64,
    high Float64,
    low Float64,
    close Float64,
    volume UInt64,
    source String
) ENGINE = Kafka()
SETTINGS
    kafka_broker_list = 'localhost:29092',
    kafka_topic_list = 'schwab.ohlcv.realtime',
    kafka_group_name = 'clickhouse_ohlcv_consumer',
    kafka_format = 'JSONEachRow',
    kafka_num_consumers = 4,
    kafka_max_block_size = 65536;
```

**Consumption Model:**
- ClickHouse runs background threads that continuously poll Kafka
- Messages are parsed according to `kafka_format` (JSONEachRow, CSV, Protobuf, etc.)
- Parsed rows are immediately available for SELECT queries
- No manual consumer management - ClickHouse handles offsets, rebalancing

### 1.2 Materialized Views Integration

✅ **Materialized views DO fire on Kafka engine inserts:**

```sql
-- MV that automatically processes Kafka data into persistent storage
CREATE MATERIALIZED VIEW ohlcv_from_kafka_mv
TO ohlcv  -- Target table with ReplacingMergeTree
AS SELECT * FROM kafka_ohlcv;

-- Multiple MVs can consume from same Kafka table
CREATE MATERIALIZED VIEW ohlcv_daily_from_kafka_mv
TO ohlcv_daily
AS SELECT
    ticker,
    toDate(timestamp) AS date,
    argMin(open, timestamp) AS open,
    max(high) AS high,
    min(low) AS low,
    argMax(close, timestamp) AS close,
    sum(volume) AS volume
FROM kafka_ohlcv
GROUP BY ticker, date;
```

**Pattern:** Kafka table acts as a "virtual stream", MVs provide ETL logic and route to persistent storage.

### 1.3 Pros vs. External Python Consumers

| Aspect | ClickHouse Kafka Engine | External Python Consumers |
|---|---|---|
| **Architecture Simplicity** | ✅ Single process, no external consumers | ❌ Separate consumer processes |
| **Schema Evolution** | ❌ Requires table recreation | ✅ Handle in transform logic |
| **Error Handling** | ❌ Bad messages break consumption | ✅ DLQ, retry patterns, logging |
| **Transform Logic** | ❌ Limited to SQL expressions | ✅ Full Python/Polars transforms |
| **Monitoring** | ❌ Basic metrics only | ✅ Custom metrics, alerting |
| **Dead Letter Queue** | ❌ Not supported | ✅ Full DLQ implementation |
| **Backpressure** | ❌ Can cause consumer lag | ✅ Configurable batch sizes |
| **Multi-format Support** | ✅ Built-in JSONEachRow, Protobuf, etc. | ✅ Any format via Python |
| **Atomic Processing** | ❌ Row-by-row | ✅ Batch transactions |

### 1.4 Error Handling Limitations

**Critical Issue:** ClickHouse Kafka engine has **poor error resilience**:
- Single malformed message can **stop entire topic consumption**
- No built-in retry or DLQ mechanism
- Error logging is minimal
- Schema mismatches require manual intervention

**Example Failure Scenario:**
```json
// This message would break consumption if 'volume' field is missing
{"ticker": "AAPL", "timestamp": "2026-04-10T14:30:00Z", "open": 150.0}
```

**Python Consumer Resilience:**
```python
try:
    df = transform_message(message)
    batch.append(df)
except ValidationError as e:
    logger.error("Bad message: %s", e)
    send_to_dlq(message)
    continue  # Keep processing other messages
```

---

## 2. Real-Time Query Patterns

### 2.1 Latest Price Queries

**Challenge:** How to serve "latest price" efficiently from streaming data?

#### Option A: Query Main Table with ORDER BY DESC
```sql
SELECT ticker, timestamp, close 
FROM ohlcv 
WHERE ticker = 'AAPL' 
ORDER BY timestamp DESC 
LIMIT 1;
```
**Performance:** ❌ Slow on large tables, even with proper indexing

#### Option B: Dedicated Latest Prices Table (Recommended)
```sql
CREATE TABLE latest_prices (
    ticker String,
    timestamp DateTime64(3, 'UTC'),
    open Float64,
    high Float64,
    low Float64,
    close Float64,
    volume UInt64
) ENGINE = ReplacingMergeTree()
ORDER BY ticker;

-- MV that maintains latest price per ticker
CREATE MATERIALIZED VIEW latest_prices_mv
TO latest_prices
AS SELECT * FROM kafka_ohlcv;
```

**Lookup Query:**
```sql
SELECT * FROM latest_prices WHERE ticker = 'AAPL' FINAL;
```
**Performance:** ✅ O(1) lookup, optimal for real-time serving

#### Option C: ClickHouse Dictionaries
```sql
CREATE DICTIONARY latest_prices_dict (
    ticker String,
    price Float64,
    timestamp DateTime64(3, 'UTC')
)
PRIMARY KEY ticker
SOURCE(CLICKHOUSE(TABLE 'latest_prices'))
LAYOUT(HASHED())
LIFETIME(MIN 0 MAX 1000);  -- Reload every 0-1000 seconds
```

**Usage:**
```sql
SELECT dictGet('latest_prices_dict', 'price', 'AAPL');
```
**Performance:** ✅ In-memory, sub-millisecond lookups

### 2.2 Time-Series Window Queries

**Common Pattern:** Last N minutes/hours of data for charts

```sql
-- Last 4 hours of 1-minute bars
SELECT * FROM ohlcv_1min_mv 
WHERE ticker = 'AAPL' 
  AND bucket >= now() - INTERVAL 4 HOUR
ORDER BY bucket;

-- Streaming aggregation for live charts
CREATE MATERIALIZED VIEW ohlcv_5sec_mv
ENGINE = AggregatingMergeTree()
ORDER BY (ticker, bucket)
AS SELECT
    ticker,
    toStartOfFiveMinute(timestamp) AS bucket,
    argMinState(open, timestamp) AS open_state,
    maxState(high) AS high_state,
    minState(low) AS low_state,
    argMaxState(close, timestamp) AS close_state,
    sumState(volume) AS volume_state
FROM kafka_ohlcv
GROUP BY ticker, bucket;
```

---

## 3. Live Data Serving to Frontend

### 3.1 Architecture Options

#### Option A: WebSocket from ClickHouse
❌ **Not Recommended:** ClickHouse doesn't provide native WebSocket support

#### Option B: Polling from Argus Frontend
```typescript
// Poll latest prices every 1 second
const pollLatestPrices = async (tickers: string[]) => {
  const response = await fetch('/api/latest-prices', {
    method: 'POST',
    body: JSON.stringify({ tickers }),
  });
  return response.json();
};

setInterval(() => pollLatestPrices(['AAPL', 'MSFT']), 1000);
```
**Pros:** Simple, works with existing HTTP infrastructure  
**Cons:** Higher latency, more server load

#### Option C: Server-Sent Events (SSE) - Recommended
```python
# DataPlat MCP server endpoint
@app.route('/stream/prices')
async def stream_prices():
    async def event_generator():
        while True:
            latest = query_latest_prices()
            yield f"data: {json.dumps(latest)}\n\n"
            await asyncio.sleep(1)
    
    return StreamingResponse(event_generator(), media_type="text/plain")
```

```typescript
// Argus frontend
const eventSource = new EventSource('/api/stream/prices');
eventSource.onmessage = (event) => {
  const prices = JSON.parse(event.data);
  updatePriceDisplay(prices);
};
```

#### Option D: Kafka Consumer in Argus (Future)
```typescript
// Argus consumes directly from Kafka topics
const consumer = kafka.consumer({ groupId: 'argus-frontend' });
await consumer.subscribe({ topic: 'schwab.quotes.realtime' });

await consumer.run({
  eachMessage: async ({ message }) => {
    const quote = JSON.parse(message.value.toString());
    webSocket.send(JSON.stringify(quote)); // To React frontend
  },
});
```

**Recommendation:** Start with SSE (Option C), migrate to direct Kafka consumption (Option D) when real-time requirements increase.

---

## 4. ReplacingMergeTree + Real-Time Implications

### 4.1 Background Merge Behavior

**Issue:** ReplacingMergeTree doesn't deduplicate immediately
- Duplicates are removed during background merges
- Merges are triggered by data volume, not time
- Real-time queries may see duplicates without `FINAL`

### 4.2 Query Patterns for Real-Time

#### Without FINAL (Faster, May Have Duplicates)
```sql
-- Fast but may return duplicates during merge window
SELECT ticker, timestamp, close FROM latest_prices WHERE ticker = 'AAPL';
```

#### With FINAL (Slower, Guaranteed Deduplication)
```sql
-- Slower but guarantees single row per (ticker, timestamp)
SELECT ticker, timestamp, close FROM latest_prices WHERE ticker = 'AAPL' FINAL;
```

### 4.3 Optimization Strategies

#### Force More Frequent Merges
```sql
-- More aggressive merge settings for real-time tables
ALTER TABLE latest_prices MODIFY SETTING 
    merge_with_ttl_timeout = 3600,
    merge_with_recompression_ttl_timeout = 3600,
    max_suspicious_broken_parts = 100;
```

#### Application-Level Deduplication
```python
# Handle duplicates in application code instead of FINAL
def get_latest_price(ticker: str) -> dict:
    rows = ch_client.query(f"""
        SELECT timestamp, close FROM latest_prices 
        WHERE ticker = '{ticker}' 
        ORDER BY timestamp DESC 
        LIMIT 10
    """).result_rows
    
    # Return most recent timestamp (dedup in Python)
    return max(rows, key=lambda r: r[0])
```

---

## 5. Production Considerations

### 5.1 ClickHouse Keeper vs. Zookeeper

**Current Setup (Single Node):** No coordination service needed
- DataPlat runs ClickHouse in Docker, single replica
- ReplacingMergeTree works without external coordination

**Future Production (Multi-Node):**
```yaml
# docker-compose.yml additions for distributed setup
clickhouse-keeper-1:
  image: clickhouse/clickhouse-keeper:latest
  environment:
    KEEPER_SERVER_ID: 1
  volumes:
    - keeper-config:/etc/clickhouse-keeper/

clickhouse-1:
  environment:
    CLICKHOUSE_KEEPER_SERVERS: "clickhouse-keeper-1:2181"
```

**Distributed Tables:**
```sql
-- Replicated table across multiple nodes
CREATE TABLE ohlcv_distributed AS ohlcv
ENGINE = ReplicatedReplacingMergeTree('/clickhouse/tables/ohlcv', '{replica}', ingested_at)
ORDER BY (ticker, timestamp);
```

### 5.2 Resource Scaling

| Component | CPU | Memory | Storage | Network |
|---|---|---|---|---|
| ClickHouse (single) | 8-16 cores | 32-64 GB | SSD, 1TB+ | 10 Gbps |
| Kafka/Redpanda | 4-8 cores | 16-32 GB | SSD, 500GB+ | 1 Gbps |
| Python Consumers | 2-4 cores | 8-16 GB | Minimal | 1 Gbps |

---

## 6. Atomic vs. Batch Inserts Performance

### 6.1 Insert Pattern Comparison

#### Atomic (Row-by-Row) Inserts
```python
# Anti-pattern: One row per insert
for candle in stream_data:
    ch_client.command(
        "INSERT INTO ohlcv VALUES (%(ticker)s, %(timestamp)s, ...)",
        parameters=candle_dict
    )
```
**Performance:** ❌ ~100-1000 inserts/second, high overhead

#### Batch Inserts (Recommended)
```python
# Collect into DataFrame, insert as batch
batch = []
for message in kafka_consumer:
    batch.append(transform_message(message))
    
    if len(batch) >= 1000:  # Batch size: 1K rows
        df = pl.concat(batch)
        ch_client.insert_arrow("ohlcv", df.to_arrow())
        batch.clear()
```
**Performance:** ✅ ~50K-100K+ inserts/second

### 6.2 Optimal Batch Sizes

| Data Type | Recommended Batch Size | Reasoning |
|---|---|---|
| OHLCV (minute bars) | 1,000-5,000 rows | ~1-5 ticker-hours, good balance |
| Real-time quotes | 10,000-50,000 rows | High frequency, larger batches |
| Option chains | 100-1,000 rows | Large row size, smaller batches |
| Economic data | 100-500 rows | Low frequency, immediate insertion |

### 6.3 Streaming Insert Pattern
```python
class StreamingBatcher:
    def __init__(self, table: str, max_size: int = 1000, flush_interval: int = 5):
        self.table = table
        self.batch = []
        self.max_size = max_size
        self.last_flush = time.time()
        self.flush_interval = flush_interval
    
    def add(self, row: dict):
        self.batch.append(row)
        
        # Flush on size or time threshold
        if (len(self.batch) >= self.max_size or 
            time.time() - self.last_flush > self.flush_interval):
            self.flush()
    
    def flush(self):
        if self.batch:
            df = pl.DataFrame(self.batch)
            ch_client.insert_arrow(self.table, df.to_arrow())
            self.batch.clear()
            self.last_flush = time.time()
```

---

## 7. Recommendations for DataPlat

### 7.1 Recommended Architecture (Extends Existing IngestPipeline Pattern)

```
Schwab WebSocket → Python Consumer → Batch Buffer → ClickHouse
                     ↓
               Kafka Topic (durability)
                     ↓
            Secondary Consumers (analytics, alerts)
```

**Integration with Existing Patterns:**
- Leverage existing `IngestPipeline` base class with Extract/Transform/Load pattern
- Extend current Polars-based transforms and validation layers
- Build on existing materialized view system (ohlcv_5min_mv, ohlcv_daily_mv, etc.)
- Use current `ensure_schema()` pattern for table management

**Rationale:**
1. **Python consumers** align with existing schwabdev/Polygon pipeline patterns
2. **Kafka topics** provide durability and enable multiple consumers
3. **ClickHouse** already optimized for analytical queries via existing schema
4. **Hybrid approach** extends current batch-first, Kafka-ready interfaces

### 7.2 Implementation Phases

#### Phase 1: Add Kafka Producer to Existing Pipelines
```python
# Extend existing schwab.client.py with streaming + Kafka
from dataplat.ingestion.schwab.client import get_schwab_client
from dataplat.db.migrate import ensure_schema

class SchwabStreamingPipeline(IngestPipeline):
    def __init__(self):
        self.schwab_client = get_schwab_client()
        self.kafka_producer = get_kafka_producer()
        ensure_schema()  # Required before any ClickHouse writes
    
    async def consume_schwab_stream(self):
        # Current: direct to ClickHouse via batch inserts
        # New: send to Kafka topic + batch to ClickHouse
        async for quote in self.schwab_client.stream_quotes():
            await self.kafka_producer.send('schwab.quotes.realtime', quote)
```

#### Phase 2: Add Kafka Consumer with Batching
```python
# New Kafka → ClickHouse consumer (extends existing patterns)
from dataplat.ingestion.base import IngestPipeline
from dataplat.transforms.ohlcv import transform_schwab_candles
from dataplat.transforms.validation import validate_ohlcv

class KafkaOHLCVConsumer(IngestPipeline):
    def __init__(self):
        ensure_schema()  # Required pattern
        self.batcher = StreamingBatcher('ohlcv', max_size=1000)
    
    def extract(self, **params):
        # Consume from Kafka instead of API
        return consume_kafka_messages('schwab.quotes.realtime')
    
    def transform(self, raw_messages: list[dict]) -> pl.DataFrame:
        # Reuse existing transform logic
        return transform_schwab_candles(raw_messages, ticker='STREAM')
    
    def load(self, df: pl.DataFrame) -> int:
        # Use existing Arrow insert pattern
        return self.ch_client.insert_arrow('ohlcv', df.to_arrow())
```

#### Phase 3: Add Real-Time Query Layer (Future MCP Integration)

**A. Extend TypeScript SDK (argus-dataplat/sdk/)**
```typescript
// sdk/src/queries/streaming.ts
import { z } from 'zod';
import { client } from '../client';

const LatestPriceSchema = z.object({
  ticker: z.string(),
  close: z.number(),
  timestamp: z.string(),
  volume: z.number(),
});
type LatestPrice = z.infer<typeof LatestPriceSchema>;

export async function getLatestPrices(tickers: string[]): Promise<LatestPrice[]> {
  const result = await client.query(`
    SELECT ticker, close, timestamp, volume 
    FROM latest_prices 
    WHERE ticker IN {tickers:Array(String)} FINAL
  `, { tickers });
  
  return z.array(LatestPriceSchema).parse(result);
}
```

**B. Future MCP Tool Integration (when MCP server is implemented)**
```python
# Future MCP tool that chat-orchestration system would call
@mcp_tool(name="get_realtime_quotes")
async def get_realtime_quotes(tickers: list[str]) -> str:
    """Get latest price quotes for tickers. Use for current market data.
    
    Returns JSON array with ticker, price, timestamp, volume.
    Will be cached in session_quotes table for query_data access.
    """
    ensure_schema()
    result = ch_client.query("""
        SELECT ticker, close as price, timestamp, volume 
        FROM latest_prices 
        WHERE ticker IN %(tickers)s FINAL
    """, parameters={'tickers': tickers})
    
    # Format for LLM consumption (matches existing tool patterns)
    return json.dumps(result.result_rows, default=str)
```

**C. Integration with Chat Tool Registry**
```typescript
// This tool would be added to tool-defs.ts in the chat system
export const getRealtimeQuotes = tool({
  name: "get_realtime_quotes",
  description: "Get latest real-time price quotes for stocks. Use when user asks for current prices, 'what is AAPL trading at', or needs live market data. Do not use for historical price charts - use get_price_chart instead.",
  parameters: {
    type: "object",
    properties: {
      tickers: {
        type: "array",
        items: { type: "string" },
        description: "Stock ticker symbols (e.g. ['AAPL', 'MSFT'])",
      },
    },
    required: ["tickers"],
  },
});

// Would be added to TOOL_DOMAIN_MAP
const TOOL_DOMAIN_MAP = {
  // ... existing tools
  'get_realtime_quotes': 'pricing',
  // ...
};
```

### 7.3 What NOT to Do (DataPlat-Specific)

❌ **Don't use ClickHouse Kafka engine for financial data** - error handling too weak for Schwab/EDGAR data  
❌ **Don't query main OHLCV table for latest prices** - use existing materialized views pattern  
❌ **Don't do row-by-row inserts** - violates existing batch-first architecture  
❌ **Don't skip `ensure_schema()`** - violates required DataPlat pattern  
❌ **Don't import pandas** - violates Polars-everywhere rule  
❌ **Don't bypass schwabdev** - use existing client wrapper patterns  
❌ **Don't use FINAL in high-frequency queries** - contradicts existing ReplacingMergeTree usage  
❌ **Don't violate data source boundaries** - Schwab for prices, Polygon for reference only

---

## 8. Monitoring & Observability

### 8.1 Key Metrics to Track

#### Integration with Existing Chat System
When streaming data becomes available via MCP tools, it will integrate with the existing chat data cache pattern:

```python
# Future: streaming tool results cached in DuckDB session tables
def cache_realtime_quotes(results: list[dict], tool_call_id: str, conversation_id: str):
    """Cache streaming quote results in session_quotes table.
    Follows existing TOOL_CACHE_MAP pattern from chat-orchestration.
    """
    # This would extend the existing data-cache.ts pattern
    # to handle real-time data with timestamps
```

#### ClickHouse Performance Metrics

#### ClickHouse Metrics
```sql
-- Table row counts and sizes
SELECT 
    table,
    formatReadableSize(total_bytes) as size,
    total_rows as rows
FROM system.tables 
WHERE database = 'dataplat';

-- Query performance
SELECT 
    query_duration_ms,
    read_rows,
    result_rows,
    memory_usage
FROM system.query_log 
WHERE query LIKE '%ohlcv%' 
ORDER BY query_start_time DESC;
```

#### Kafka Metrics
```python
# Consumer lag monitoring
consumer_lag = kafka_admin.list_consumer_group_offsets('clickhouse_consumer')
for topic_partition, offset in consumer_lag.items():
    lag = get_high_water_mark(topic_partition) - offset.offset
    metrics.gauge('kafka.consumer_lag', lag, tags=[f'topic:{topic_partition.topic}'])
```

#### Custom Application Metrics
```python
# Batch insert performance
@metrics.timer('clickhouse.batch_insert.duration')
def insert_batch(df: pl.DataFrame):
    ch_client.insert_arrow('ohlcv', df.to_arrow())

# Transform success rate
@metrics.counter('transform.success_rate')
def transform_schwab_quote(raw_message: dict):
    # Transform logic with success/error counting
```

### 8.2 Alerting Thresholds

| Metric | Warning | Critical |
|---|---|---|
| Consumer lag | > 1 minute | > 5 minutes |
| Insert latency | > 100ms | > 1 second |
| Transform errors | > 1% | > 5% |
| ClickHouse CPU | > 70% | > 90% |
| Disk usage | > 80% | > 95% |

---

## 9. Future MCP Server Integration

### 9.1 Tool Design Patterns (Aligned with Chat System)

Based on existing tool patterns in the chat system, streaming MCP tools should follow these conventions:

```python
# Tool description pattern - specify WHEN to use, not just what
@mcp_tool(name="stream_market_events")
async def stream_market_events(symbols: list[str], event_types: list[str]) -> str:
    """Stream real-time market events (trades, quotes, news) for symbols.
    
    Use when user asks for 'live updates', 'stream prices', or 'watch AAPL'.
    DO NOT use for historical analysis - use get_price_chart instead.
    
    Returns: JSON stream of market events with timestamps.
    Events are automatically cached in session_market_events table.
    """
```

**Key Patterns:**
1. **Domain mapping** - each tool maps to a business domain (pricing, company, economics)
2. **Session caching** - results cached in DuckDB for `query_data` access
3. **Truncation for LLM** - large results truncated to 1500 chars for LLM, full results stored separately
4. **Error handling** - robust error handling with retry patterns

### 9.2 Advanced Real-Time Features

### 9.1 Advanced Real-Time Features

#### Time-Based Materialized Views
```sql
-- Auto-expiring recent data table
CREATE TABLE ohlcv_recent (
    ticker String,
    timestamp DateTime64(3, 'UTC'),
    close Float64
) ENGINE = MergeTree()
ORDER BY (ticker, timestamp)
TTL timestamp + INTERVAL 1 HOUR;  -- Auto-delete after 1 hour
```

#### Continuous Aggregation
```sql
-- Real-time VWAP calculation
CREATE MATERIALIZED VIEW vwap_realtime_mv
ENGINE = AggregatingMergeTree()
ORDER BY (ticker, bucket)
AS SELECT
    ticker,
    toStartOfMinute(timestamp) AS bucket,
    sumState(close * volume) AS notional_state,
    sumState(volume) AS volume_state
FROM kafka_ohlcv
GROUP BY ticker, bucket;

-- Query current VWAP
SELECT 
    ticker,
    sumMerge(notional_state) / sumMerge(volume_state) AS vwap
FROM vwap_realtime_mv 
WHERE bucket >= now() - INTERVAL 1 HOUR
GROUP BY ticker;
```

#### Complex Event Processing
```sql
-- Detect unusual volume spikes
CREATE MATERIALIZED VIEW volume_alerts_mv
ENGINE = MergeTree()
ORDER BY timestamp
AS SELECT
    ticker,
    timestamp,
    volume,
    avg(volume) OVER (
        PARTITION BY ticker 
        ORDER BY timestamp 
        RANGE BETWEEN INTERVAL 1 HOUR PRECEDING AND CURRENT ROW
    ) AS avg_volume_1h
FROM kafka_ohlcv
WHERE volume > avg_volume_1h * 3;  -- 3x volume spike
```

---

## Conclusion

ClickHouse's native Kafka integration provides **elegant simplicity** but sacrifices **operational robustness** required for financial data processing. For DataPlat's use case with complex market data transformations, error handling, and monitoring requirements, **external Python consumers with Kafka as the streaming backbone** remains the optimal architecture.

**Key Takeaway:** Use ClickHouse for what it does best (analytical queries) and Kafka for what it does best (stream processing), connected by robust Python consumers that handle the complex middle layer of financial data ingestion.

The existing DataPlat architecture is well-positioned for this streaming evolution - the transform layer abstracts the pipeline interface, making the transition from batch to streaming seamless.

---

**Next Steps (Integrated with Existing Architecture):**

1. **Phase 1: Kafka Infrastructure**
   - Add Redpanda to docker-compose.yml
   - Extend existing `IngestPipeline` base class with Kafka producer capabilities
   - Add Kafka topics following existing naming patterns

2. **Phase 2: Streaming Consumers**
   - Build Kafka → ClickHouse consumers using existing transform/validation patterns
   - Follow `ensure_schema()` requirement for all ClickHouse writers
   - Use existing Polars-first, batch insert patterns

3. **Phase 3: Real-Time Tables**
   - Add `latest_prices` table via new migration file
   - Create materialized views following existing MV patterns
   - Update existing SDK queries to support real-time data

4. **Phase 4: MCP Integration**
   - Implement MCP server following existing tool patterns
   - Add streaming tools that integrate with chat system's tool registry
   - Follow existing TOOL_DOMAIN_MAP and session caching patterns

5. **Phase 5: Frontend Streaming**
   - Add SSE endpoints that leverage existing tRPC/IPC architecture
   - Integrate with existing chat data cache and visualization systems