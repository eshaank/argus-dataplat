# Infrastructure Plan: Kafka Streams (Redpanda)

This document details the deployment, scaling, and configuration strategy for the Redpanda/Kafka messaging layer within the DataPlat architecture.

## 1. Cluster Configuration

### Node Deployment
- **Broker Count**: 3 Nodes (Production Minimum).
- **Topology**: Distributed across 3 Availability Zones (AZs) to ensure fault tolerance against zone failure.
- **Hardware Profile (Per Node)**:
  - **CPU**: 8-16 vCPUs (Redpanda is highly multi-threaded and benefits from fast cores).
  - **Memory**: 32GB - 64GB (Optimized for page cache to reduce disk I/O for consumers).
  - **Storage**: NVMe SSDs (Required for high-throughput sequential writes/reads).
  - **Network**: 10Gbps+ low-latency interconnect.

### Redpanda Settings
- **Replication Factor**: 3 (Ensures no data loss on single node failure).
- **Min In-Sync Replicas (min.insync.replicas)**: 2 (Balances durability and availability).
- **Acks**: `all` for critical data (fundamentals, corporate actions); `1` for high-volume real-time quotes if slight loss is acceptable for speed.

---

## 2. Topic & Partitioning Strategy

The goal is to maximize parallel processing in the Python/Polars consumers while maintaining order per ticker.

### Partitioning Principles
- **Key-Based Partitioning**: All market data topics are keyed by `ticker` (or `underlying` for options) to ensure that all events for a specific symbol are processed in order by the same consumer instance.
- **Partition Count**: Targeted at **30-60 partitions** per high-volume topic. This allows for significant horizontal scaling of consumer groups (up to 60 concurrent pods) without needing to re-partition.

### Topic Specifications

| Topic | Key | Volume | Partitions | Retention | Purpose |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `schwab.quotes.realtime` | `ticker` | Ultra High | 60 | 24h | Real-time L1 quotes $\rightarrow$ CH |
| `schwab.ohlcv.daily` | `ticker` | Medium | 30 | 7d | Daily bars $\rightarrow$ CH |
| `schwab.options.chains` | `underlying` | High | 30 | 7d | Option snapshots $\rightarrow$ CH |
| `schwab.accounts.positions`| `account_id` | Low | 10 | 30d | Position updates $\rightarrow$ CH |
| `polygon.universe` | `ticker` | Low | 10 | 30d | Metadata $\rightarrow$ CH |
| `polygon.news` | `ticker` | Medium | 30 | 7d | News events $\rightarrow$ CH |
| `polygon.corporate_actions` | `ticker` | Low | 10 | 30d | Div/Splits $\rightarrow$ CH |
| `polygon.short_interest` | `ticker` | Medium | 30 | 7d | Short data $\rightarrow$ CH |
| `fred.economics` | `series_id` | Low | 10 | 30d | Macro data $\rightarrow$ CH |
| `sec.filings` | `ticker` | Medium | 30 | 7d | SEC metadata $\rightarrow$ CH |

---

## 3. Consumer Scaling Strategy

### Polars Batching Pattern
Consumers will not insert rows individually into ClickHouse. Instead, they will:
1. Accumulate messages in a local buffer.
2. Trigger a bulk insert when:
   - Buffer size reaches $N$ rows (e.g., 5,000).
   - A time interval expires (e.g., every 5 seconds).
3. Use **Polars** to convert the buffer to a DataFrame for high-performance type validation and cleaning before calling `ch_client.insert_df()`.

### Horizontal Scaling (K8s)
- **Deployment**: Each consumer topic will have its own K8s Deployment.
- **Scaling Trigger**: Horizontal Pod Autoscaler (HPA) based on **Consumer Lag**.
  - If `sum(lag)` for a consumer group exceeds a threshold, scale up pods (up to the partition count).
- **Resource Isolation**: Separating `quotes` consumers from `fundamentals` consumers ensures that a spike in market volatility doesn't delay critical corporate action processing.

## 4. Fault Tolerance & Recovery
- **Offset Management**: Use Kafka-managed offsets.
- **Idempotency**: Use `ReplacingMergeTree` in ClickHouse with `ingested_at` or a source-provided timestamp to handle duplicate messages resulting from consumer crashes/re-balances.
- **Dead Letter Queues (DLQ)**: Messages that fail Polars validation (e.g., malformed JSON) are routed to a `.dlq` topic for manual inspection.
