# Kafka/Redpanda Implementation Specification

> Detailed implementation spec for deploying Redpanda locally and in production, plus Python Kafka consumer layer that integrates with the existing DataPlat ClickHouse pipeline.

---

## Executive Summary

This spec provides production-ready implementations for:
1. **Local development**: Redpanda + Console in docker-compose.yml (single node, overprovisioned)
2. **Production reference**: 3-node cluster configuration (NVMe, replication factor 3)
3. **Python client choice**: confluent-kafka with detailed rationale vs alternatives
4. **Consumer architecture**: Polars batching pattern integrated with existing IngestPipeline interface
5. **Schema registry**: Avro with detailed encoding strategy
6. **Operational patterns**: Topic creation, monitoring, dead letter queues

The design preserves the existing Extract → Transform → Load pipeline architecture, inserting Kafka between Extract and Transform with zero changes to the Transform/Load layers.

---

## 1. Redpanda Local Development Setup

### 1.1 Docker Compose Configuration

Add to the existing `docker-compose.yml` (alongside ClickHouse):

```yaml
services:
  clickhouse:
    # ... existing ClickHouse config ...

  redpanda:
    image: redpandadata/redpanda:v24.2.7
    command:
      - redpanda start
      - --smp 1                                    # Single thread for dev
      - --memory 1G                                # Memory limit
      - --overprovisioned                          # Skip hardware checks
      - --node-id 0
      - --kafka-addr PLAINTEXT://0.0.0.0:29092    # Kafka API
      - --advertise-kafka-addr PLAINTEXT://localhost:29092
      - --pandaproxy-addr 0.0.0.0:8082             # Schema Registry
      - --advertise-pandaproxy-addr localhost:8082
      - --rpc-addr 0.0.0.0:33145                   # Internal RPC
      - --set redpanda.empty_seed_starts_cluster=false
      - --seeds redpanda:33145
    ports:
      - "29092:29092"   # Kafka API
      - "8082:8082"     # Schema Registry (Pandaproxy)
      - "9644:9644"     # Admin API
    volumes:
      - redpanda_data:/var/lib/redpanda/data
    healthcheck:
      test: ["CMD-SHELL", "rpk cluster health | grep -q healthy"]
      interval: 10s
      timeout: 5s
      retries: 5

  redpanda-console:
    image: redpandadata/console:v2.7.0
    depends_on:
      redpanda:
        condition: service_healthy
    ports:
      - "8080:8080"
    environment:
      KAFKA_BROKERS: redpanda:29092
      KAFKA_SCHEMAREGISTRY_ENABLED: "true"
      KAFKA_SCHEMAREGISTRY_URLS: http://redpanda:8082
      KAFKA_PROTOBUF_ENABLED: "false"
      KAFKA_CONNECT_ENABLED: "false"
    restart: unless-stopped

volumes:
  clickhouse_data:
  redpanda_data:
```

### 1.2 Key Configuration Choices

**Why Redpanda over Apache Kafka for local dev:**
- Single binary vs Kafka's JVM + ZooKeeper complexity
- Built-in Schema Registry (Pandaproxy) vs separate Confluent Schema Registry
- Kafka-compatible APIs (drop-in replacement when scaling to production Kafka)
- Lighter resource usage in development

**Single node with `--overprovisioned`:**
- Skips production hardware checks (SSDs, dedicated cores)
- Perfect for MacBook development where performance isn't critical
- Still provides the full Kafka API surface for development

### 1.3 justfile Commands

Add to existing `justfile`:

```makefile
# Start Redpanda + ClickHouse
kafka-up:
    docker compose up -d redpanda redpanda-console clickhouse

# Stop Kafka services
kafka-down:
    docker compose stop redpanda redpanda-console

# View Redpanda logs
kafka-logs:
    docker compose logs -f redpanda

# Create a topic for testing
kafka-create-topic TOPIC:
    docker exec -it $(docker compose ps -q redpanda) \
        rpk topic create {{TOPIC}} --partitions 10 --replicas 1

# List all topics
kafka-topics:
    docker exec -it $(docker compose ps -q redpanda) rpk topic list

# Produce test message
kafka-produce TOPIC:
    docker exec -it $(docker compose ps -q redpanda) \
        rpk topic produce {{TOPIC}}

# Consume messages
kafka-consume TOPIC:
    docker exec -it $(docker compose ps -q redpanda) \
        rpk topic consume {{TOPIC}} --print-headers

# Kafka cluster health check
kafka-health:
    docker exec -it $(docker compose ps -q redpanda) rpk cluster health

# Open Redpanda Console (UI)
kafka-ui:
    open http://localhost:8080
```

---

## 2. Production Configuration Reference

### 2.1 Hardware Requirements (Per Node)

```yaml
# Production 3-node cluster (reference only)
Hardware per node:
  CPU: 16+ vCPUs (preferably dedicated cores)
  Memory: 64GB RAM
    - 32GB for Redpanda process
    - 32GB for OS page cache (critical for consumer performance)
  Storage: 2TB+ NVMe SSDs in RAID 0
    - Redpanda requires low-latency sequential writes
    - Network storage (EBS gp3) is NOT suitable for production
  Network: 10Gbps+ with low latency between zones

Deployment:
  Nodes: 3 (minimum for fault tolerance)
  AZs: 3 (one node per availability zone)
  Replication: 3 (ensures no data loss on single node failure)
```

### 2.2 Production Redpanda Configuration

```yaml
# /etc/redpanda/redpanda.yaml (each node)
redpanda:
  data_directory: /var/lib/redpanda/data
  node_id: 1  # 1, 2, 3 for the three nodes
  rack: "rack1"  # Different rack per AZ
  
  # Inter-node communication
  rpc_server:
    address: 10.0.1.10  # Private IP of this node
    port: 33145
  
  # Kafka API
  kafka_api:
    - name: internal
      address: 10.0.1.10
      port: 9092
    - name: external  # For clients outside cluster
      address: kafka-1.company.com
      port: 9094
  
  # Admin API
  admin:
    - address: 10.0.1.10
      port: 9644
  
  # Cluster discovery
  seed_servers:
    - host:
        address: 10.0.1.10
        port: 33145
    - host:
        address: 10.0.1.11  
        port: 33145
    - host:
        address: 10.0.1.12
        port: 33145

  # Performance tuning
  developer_mode: false
  tune_network: true
  tune_disk_scheduler: true
  tune_cpu: true
  tune_aio_events: true
  
  # Memory allocation
  memory_abort_on_alloc_failure: true
  
  # Compaction settings for log retention
  log_compaction_interval_ms: 5000
  log_segment_size: 1073741824  # 1GB segments

# Default topic configuration  
rpk:
  tune_network: true
  tune_disk_scheduler: true
  tune_cpu: true
  overprovisioned: false
```

### 2.3 Production Topic Settings

```bash
# High-volume real-time topics (quotes, trades)
rpk topic create schwab.quotes.realtime \
  --partitions 60 \
  --replicas 3 \
  --config min.insync.replicas=2 \
  --config retention.ms=86400000 \
  --config segment.ms=3600000 \
  --config compression.type=snappy

# Medium-volume persistent topics (OHLCV, fundamentals)  
rpk topic create schwab.ohlcv.daily \
  --partitions 30 \
  --replicas 3 \
  --config min.insync.replicas=2 \
  --config retention.ms=604800000 \
  --config compression.type=lz4
```

---

## 3. Python Kafka Client Choice: confluent-kafka

### 3.1 Decision Matrix

| Library | Async Support | Performance | Maintenance | Schema Registry | Verdict |
|---------|---------------|-------------|-------------|-----------------|---------|
| **confluent-kafka** | ✅ (asyncio wrapper) | 🔥 (librdkafka C) | ✅ Confluent-backed | ✅ Native support | **CHOSEN** |
| aiokafka | ✅ Native async | 🔥 Good (pure Python) | ⚠️ Community | ❌ Manual integration | Runner-up |
| kafka-python | ❌ Sync only | 📉 Slowest | ⚠️ Minimal maintenance | ❌ None | Ruled out |

### 3.2 confluent-kafka Rationale

**Performance:** Built on librdkafka (C library) used in production by Confluent, Netflix, Uber. Handles high throughput with minimal Python overhead.

**Schema Registry Integration:** First-class support for Avro, JSON, Protobuf schemas. Handles serialization/deserialization automatically.

**Producer Features:**
- Idempotent production (exactly-once semantics)
- Batching and compression
- Async callbacks for delivery confirmation
- Transactional guarantees

**Consumer Features:**  
- Automatic offset management
- Consumer group rebalancing
- Configurable commit strategies
- Pause/resume for backpressure

**Maintenance:** Actively developed and supported by Confluent. Regular updates for new Kafka features.

### 3.3 Dependencies Update

Add to `pyproject.toml`:

```toml
[project]
dependencies = [
    # ... existing deps ...
    "confluent-kafka[avro]>=2.6.0",     # Kafka client with Avro support
    "fastavro>=1.9.0",                  # Fast Avro serialization  
    "confluent-kafka-helpers>=0.8.0",   # Async wrappers
]
```

---

## 4. Schema Registry Strategy: Avro

### 4.1 Schema Choice: Avro vs JSON vs Protobuf

| Format | Size | Schema Evolution | Python Support | Verdict |
|--------|------|------------------|----------------|---------|
| **Avro** | Smallest (binary) | ✅ Built-in evolution | ✅ fastavro | **CHOSEN** |
| JSON | Largest (text) | ❌ Manual versioning | ✅ Native | Too verbose |
| Protobuf | Medium (binary) | ✅ Good evolution | ⚠️ Complex setup | Over-engineering |

**Why Avro:**
- **Compact:** Binary format is ~60% smaller than JSON for financial data
- **Schema evolution:** Built-in forward/backward compatibility
- **Self-describing:** Schema ID in message header
- **Fast:** fastavro is highly optimized
- **Standard:** De facto standard in data engineering

### 4.2 Schema Definitions

Create `schemas/` directory with Avro schema files:

```
src/dataplat/schemas/
├── ohlcv.avsc          # OHLCV bar schema
├── quote.avsc          # Real-time quote schema  
├── option_chain.avsc   # Options data schema
├── fundamental.avsc    # Financial metrics schema
└── economic.avsc       # FRED macro indicators
```

**schemas/ohlcv.avsc:**
```json
{
  "type": "record",
  "name": "OHLCVBar",
  "namespace": "dataplat.schemas",
  "doc": "OHLCV candlestick bar with volume",
  "fields": [
    {
      "name": "ticker",
      "type": "string",
      "doc": "Stock symbol (e.g., AAPL)"
    },
    {
      "name": "timestamp", 
      "type": "long",
      "logicalType": "timestamp-millis",
      "doc": "Bar timestamp in UTC epoch milliseconds"
    },
    {
      "name": "open",
      "type": "double",
      "doc": "Opening price"
    },
    {
      "name": "high", 
      "type": "double",
      "doc": "Highest price during the bar"
    },
    {
      "name": "low",
      "type": "double", 
      "doc": "Lowest price during the bar"
    },
    {
      "name": "close",
      "type": "double",
      "doc": "Closing price"
    },
    {
      "name": "volume",
      "type": "long",
      "doc": "Total volume traded"
    },
    {
      "name": "vwap",
      "type": ["null", "double"],
      "default": null,
      "doc": "Volume-weighted average price"
    },
    {
      "name": "transactions",
      "type": ["null", "int"],
      "default": null,
      "doc": "Number of individual transactions"
    },
    {
      "name": "source",
      "type": {
        "type": "enum",
        "name": "DataSource",
        "symbols": ["schwab", "polygon", "polygon_backfill", "thetadata"]
      },
      "doc": "Data provider source"
    }
  ]
}
```

**schemas/quote.avsc:**
```json
{
  "type": "record", 
  "name": "Quote",
  "namespace": "dataplat.schemas",
  "doc": "Real-time Level 1 quote",
  "fields": [
    {"name": "ticker", "type": "string"},
    {"name": "timestamp", "type": "long", "logicalType": "timestamp-millis"},
    {"name": "bid", "type": ["null", "double"], "default": null},
    {"name": "ask", "type": ["null", "double"], "default": null}, 
    {"name": "bid_size", "type": ["null", "int"], "default": null},
    {"name": "ask_size", "type": ["null", "int"], "default": null},
    {"name": "last", "type": ["null", "double"], "default": null},
    {"name": "last_size", "type": ["null", "int"], "default": null},
    {"name": "volume", "type": ["null", "long"], "default": null},
    {"name": "source", "type": "dataplat.schemas.DataSource", "default": "schwab"}
  ]
}
```

### 4.3 Schema Registry Client

```python
# src/dataplat/kafka/schema_client.py
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer, AvroDeserializer
import json
from pathlib import Path

class SchemaManager:
    """Manages Avro schemas and serializers for Kafka topics."""
    
    def __init__(self, schema_registry_url: str = "http://localhost:8082"):
        self.client = SchemaRegistryClient({"url": schema_registry_url})
        self.schemas_dir = Path(__file__).parent.parent / "schemas"
        self._serializers = {}
        self._deserializers = {}
    
    def load_schema(self, schema_name: str) -> str:
        """Load Avro schema from .avsc file."""
        schema_path = self.schemas_dir / f"{schema_name}.avsc"
        return schema_path.read_text()
    
    def get_serializer(self, schema_name: str) -> AvroSerializer:
        """Get cached Avro serializer for schema."""
        if schema_name not in self._serializers:
            schema_str = self.load_schema(schema_name)
            self._serializers[schema_name] = AvroSerializer(
                schema_registry_client=self.client,
                schema_str=schema_str
            )
        return self._serializers[schema_name]
    
    def get_deserializer(self, schema_name: str) -> AvroDeserializer:
        """Get cached Avro deserializer for schema."""  
        if schema_name not in self._deserializers:
            schema_str = self.load_schema(schema_name)
            self._deserializers[schema_name] = AvroDeserializer(
                schema_registry_client=self.client,
                schema_str=schema_str
            )
        return self._deserializers[schema_name]

# Module singleton
schema_manager = SchemaManager()
```

---

## 5. Topic Creation and Management

### 5.1 Topic Configuration Strategy

**Partition Count Philosophy:**
- Key by ticker → ensures all events for a symbol go to same consumer
- 30-60 partitions per topic → allows 30-60 concurrent consumers max
- Over-partition rather than under-partition (can't increase easily)

**Retention Policy:**
- Real-time data: 24-48 hours (just for replay/debugging)
- Daily OHLCV: 7-30 days (enough for reprocessing)
- Fundamentals/reference: 90+ days (infrequent changes)

### 5.2 Topic Specification

Based on `INFRA_KAFKA_PLAN.md` but with concrete implementation details:

```python
# src/dataplat/kafka/topics.py
from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class TopicConfig:
    name: str
    partitions: int
    replication_factor: int
    config: Dict[str, Any]

# Topic definitions with production-ready configuration
TOPIC_CONFIGS = {
    # High-volume real-time streams
    "schwab.quotes.realtime": TopicConfig(
        name="schwab.quotes.realtime",
        partitions=60,
        replication_factor=3,
        config={
            "min.insync.replicas": 2,
            "retention.ms": 86400000,  # 24 hours
            "segment.ms": 3600000,     # 1 hour segments
            "compression.type": "snappy",  # Fast compression
            "cleanup.policy": "delete"
        }
    ),
    
    # Daily OHLCV data
    "schwab.ohlcv.daily": TopicConfig(
        name="schwab.ohlcv.daily", 
        partitions=30,
        replication_factor=3,
        config={
            "min.insync.replicas": 2,
            "retention.ms": 604800000,  # 7 days
            "compression.type": "lz4",   # Better compression
            "cleanup.policy": "delete"
        }
    ),
    
    # Option chains (moderate volume)
    "schwab.options.chains": TopicConfig(
        name="schwab.options.chains",
        partitions=30,
        replication_factor=3,
        config={
            "min.insync.replicas": 2,
            "retention.ms": 604800000,  # 7 days  
            "compression.type": "lz4",
            "cleanup.policy": "delete"
        }
    ),
    
    # Account positions (low volume)
    "schwab.accounts.positions": TopicConfig(
        name="schwab.accounts.positions",
        partitions=10,
        replication_factor=3, 
        config={
            "min.insync.replicas": 2,
            "retention.ms": 2592000000,  # 30 days
            "compression.type": "lz4",
            "cleanup.policy": "delete"
        }
    ),
    
    # Reference data from Polygon
    "polygon.universe": TopicConfig(
        name="polygon.universe",
        partitions=10,
        replication_factor=3,
        config={
            "min.insync.replicas": 2,
            "retention.ms": 2592000000,  # 30 days
            "compression.type": "lz4", 
            "cleanup.policy": "compact"  # Keep latest universe state
        }
    ),
    
    "polygon.news": TopicConfig(
        name="polygon.news",
        partitions=30, 
        replication_factor=3,
        config={
            "min.insync.replicas": 2,
            "retention.ms": 604800000,  # 7 days
            "compression.type": "lz4",
            "cleanup.policy": "delete"
        }
    ),
    
    "polygon.corporate_actions": TopicConfig(
        name="polygon.corporate_actions",
        partitions=10,
        replication_factor=3,
        config={
            "min.insync.replicas": 2, 
            "retention.ms": 2592000000,  # 30 days
            "compression.type": "lz4",
            "cleanup.policy": "delete"
        }
    ),
    
    # Economic data from FRED
    "fred.economics": TopicConfig(
        name="fred.economics",
        partitions=10,
        replication_factor=3,
        config={
            "min.insync.replicas": 2,
            "retention.ms": 2592000000,  # 30 days
            "compression.type": "lz4",
            "cleanup.policy": "compact"  # Keep latest economic state
        }
    ),
    
    # SEC filings
    "sec.filings": TopicConfig(
        name="sec.filings",
        partitions=30,
        replication_factor=3,
        config={
            "min.insync.replicas": 2,
            "retention.ms": 604800000,  # 7 days
            "compression.type": "lz4", 
            "cleanup.policy": "delete"
        }
    )
}
```

### 5.3 Topic Creation Script

```python
# src/dataplat/cli/create_topics.py
"""Create all Kafka topics with proper configuration."""

import logging
from confluent_kafka.admin import AdminClient, NewTopic, ConfigResource, ResourceType
from dataplat.config import settings
from dataplat.kafka.topics import TOPIC_CONFIGS

logger = logging.getLogger(__name__)

def create_topics(dry_run: bool = False) -> None:
    """Create all topics defined in TOPIC_CONFIGS."""
    
    admin_client = AdminClient({
        "bootstrap.servers": settings.kafka_bootstrap_servers,
    })
    
    # Check which topics already exist
    existing_topics = admin_client.list_topics(timeout=10).topics
    
    topics_to_create = []
    for topic_config in TOPIC_CONFIGS.values():
        if topic_config.name in existing_topics:
            logger.info(f"Topic {topic_config.name} already exists")
            continue
            
        new_topic = NewTopic(
            topic=topic_config.name,
            num_partitions=topic_config.partitions,
            replication_factor=topic_config.replication_factor,
            config=topic_config.config
        )
        topics_to_create.append(new_topic)
    
    if not topics_to_create:
        logger.info("All topics already exist")
        return
        
    if dry_run:
        logger.info(f"DRY RUN: Would create topics: {[t.topic for t in topics_to_create]}")
        return
    
    # Create topics
    futures = admin_client.create_topics(topics_to_create, validate_only=False)
    
    for topic, future in futures.items():
        try:
            future.result()  # Block until topic is created
            logger.info(f"Created topic: {topic}")
        except Exception as e:
            logger.error(f"Failed to create topic {topic}: {e}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    
    create_topics(dry_run=args.dry_run)
```

Add to `justfile`:
```makefile
# Create all Kafka topics
kafka-create-topics:
    uv run python -m dataplat.cli.create_topics

# Dry run topic creation
kafka-create-topics-dry:
    uv run python -m dataplat.cli.create_topics --dry-run
```

---

## 6. Consumer Group Design and Polars Batching Pattern

### 6.1 Consumer Architecture

Each topic has a dedicated consumer group to avoid head-of-line blocking:

```python
# src/dataplat/kafka/consumer.py
"""Base Kafka consumer with Polars batching for ClickHouse insertion."""

import logging
import asyncio
from typing import List, Dict, Any, Optional, Callable
from confluent_kafka import Consumer, KafkaError
import polars as pl
from dataplat.config import settings
from dataplat.db.client import get_clickhouse_client
from dataplat.kafka.schema_client import schema_manager

logger = logging.getLogger(__name__)

class PolarsKafkaConsumer:
    """
    Kafka consumer that batches messages into Polars DataFrames 
    and bulk-inserts into ClickHouse.
    """
    
    def __init__(
        self,
        topic: str,
        table: str,
        schema_name: str,
        group_id: str,
        batch_size: int = 5000,
        flush_interval: float = 5.0,
        transform_fn: Optional[Callable[[List[Dict]], pl.DataFrame]] = None
    ):
        self.topic = topic
        self.table = table
        self.schema_name = schema_name
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.transform_fn = transform_fn or self._default_transform
        
        # Kafka consumer config
        self.consumer = Consumer({
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "group.id": group_id,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,  # Manual commit after successful insert
            "max.poll.interval.ms": 300000,  # 5 minutes for batch processing
            "fetch.min.bytes": 50000,        # Wait for decent batch size
            "fetch.wait.max.ms": 1000,       # But don't wait too long
        })
        
        self.deserializer = schema_manager.get_deserializer(schema_name)
        self.ch_client = get_clickhouse_client()
        self.buffer: List[Dict[str, Any]] = []
        self.last_flush = asyncio.get_event_loop().time()
        
    def _default_transform(self, records: List[Dict]) -> pl.DataFrame:
        """Default: convert list of dicts to Polars DataFrame."""
        return pl.DataFrame(records)
        
    async def start(self) -> None:
        """Start consuming messages and processing batches."""
        self.consumer.subscribe([self.topic])
        logger.info(f"Started consumer for {self.topic} -> {self.table}")
        
        try:
            while True:
                # Poll for messages
                msg = self.consumer.poll(timeout=1.0)
                
                if msg is None:
                    # Check if we should flush on timeout
                    if self._should_flush_timeout():
                        await self._flush_buffer()
                    continue
                    
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    else:
                        logger.error(f"Consumer error: {msg.error()}")
                        continue
                
                # Deserialize message
                try:
                    record = self.deserializer(msg.value(), None)
                    self.buffer.append(record)
                except Exception as e:
                    logger.error(f"Failed to deserialize message: {e}")
                    # Send to dead letter queue (implemented below)
                    await self._send_to_dlq(msg)
                    continue
                
                # Flush if batch is full
                if len(self.buffer) >= self.batch_size:
                    await self._flush_buffer()
                    
        except KeyboardInterrupt:
            logger.info("Consumer interrupted, shutting down...")
        finally:
            # Flush remaining buffer
            if self.buffer:
                await self._flush_buffer()
            self.consumer.close()
    
    def _should_flush_timeout(self) -> bool:
        """Check if flush interval has elapsed."""
        if not self.buffer:
            return False
        current_time = asyncio.get_event_loop().time()
        return (current_time - self.last_flush) >= self.flush_interval
    
    async def _flush_buffer(self) -> None:
        """Transform buffer to DataFrame and insert into ClickHouse."""
        if not self.buffer:
            return
            
        try:
            # Transform records to Polars DataFrame
            df = self.transform_fn(self.buffer)
            
            if df.is_empty():
                logger.warning("Transform produced empty DataFrame, skipping insert")
                self.buffer.clear()
                return
            
            # Insert into ClickHouse
            rows_inserted = await self._insert_dataframe(df)
            
            # Commit offsets only after successful insert  
            self.consumer.commit()
            
            logger.info(f"Inserted {rows_inserted} rows into {self.table}")
            self.buffer.clear()
            self.last_flush = asyncio.get_event_loop().time()
            
        except Exception as e:
            logger.error(f"Failed to flush buffer: {e}")
            # Don't clear buffer on error - will retry
            raise
    
    async def _insert_dataframe(self, df: pl.DataFrame) -> int:
        """Insert Polars DataFrame into ClickHouse table."""
        try:
            # Use Arrow for zero-copy insertion
            arrow_table = df.to_arrow()
            self.ch_client.insert_arrow(self.table, arrow_table)
            return len(df)
        except Exception as e:
            logger.warning(f"Arrow insert failed, falling back to pandas: {e}")
            # Fallback to pandas (the one sanctioned exception)
            pandas_df = df.to_pandas() 
            self.ch_client.insert_df(self.table, pandas_df)
            return len(df)
    
    async def _send_to_dlq(self, msg) -> None:
        """Send malformed message to dead letter queue."""
        # Implemented in Dead Letter Queue section below
        pass
```

### 6.2 Topic-Specific Consumer Implementations

```python
# src/dataplat/kafka/consumers/ohlcv_consumer.py
"""OHLCV consumer with validation and OHLC sanity checks."""

import polars as pl
from dataplat.kafka.consumer import PolarsKafkaConsumer
from dataplat.transforms.ohlcv import validate_ohlcv_dataframe

class OHLCVConsumer(PolarsKafkaConsumer):
    """Consumer for OHLCV data with market data validation."""
    
    def __init__(self):
        super().__init__(
            topic="schwab.ohlcv.daily",
            table="ohlcv", 
            schema_name="ohlcv",
            group_id="ohlcv-consumer-group",
            batch_size=5000,
            transform_fn=self._transform_ohlcv
        )
    
    def _transform_ohlcv(self, records: List[Dict]) -> pl.DataFrame:
        """Transform OHLCV records with validation."""
        df = pl.DataFrame(records)
        
        # Convert timestamp from epoch millis to datetime
        df = df.with_columns(
            pl.col("timestamp").map_elements(
                lambda x: pl.from_epoch(x, time_unit="ms")
            ).alias("timestamp")
        )
        
        # Validate OHLC relationships
        df = validate_ohlcv_dataframe(df)
        
        # Add ingested_at timestamp
        df = df.with_columns(
            pl.lit(pl.datetime.now()).alias("ingested_at")
        )
        
        return df

# src/dataplat/kafka/consumers/quotes_consumer.py  
"""Real-time quotes consumer for high-frequency data."""

import polars as pl
from dataplat.kafka.consumer import PolarsKafkaConsumer

class QuotesConsumer(PolarsKafkaConsumer):
    """Consumer for real-time quote data."""
    
    def __init__(self):
        super().__init__(
            topic="schwab.quotes.realtime", 
            table="quotes_realtime",
            schema_name="quote",
            group_id="quotes-consumer-group", 
            batch_size=10000,  # Higher batch for high frequency
            flush_interval=2.0,  # Faster flush for real-time
            transform_fn=self._transform_quotes
        )
    
    def _transform_quotes(self, records: List[Dict]) -> pl.DataFrame:
        """Transform quote records.""" 
        df = pl.DataFrame(records)
        
        # Convert timestamp
        df = df.with_columns(
            pl.col("timestamp").map_elements(
                lambda x: pl.from_epoch(x, time_unit="ms")
            ).alias("timestamp")
        )
        
        # Filter out invalid quotes (both bid and ask zero)
        df = df.filter(
            ~((pl.col("bid").is_null() | (pl.col("bid") == 0)) &
              (pl.col("ask").is_null() | (pl.col("ask") == 0)))
        )
        
        return df
```

### 6.3 Consumer Group Management

```python
# src/dataplat/kafka/consumer_manager.py
"""Manages multiple consumer groups for different topics."""

import asyncio
import logging
from typing import List
from dataplat.kafka.consumers.ohlcv_consumer import OHLCVConsumer
from dataplat.kafka.consumers.quotes_consumer import QuotesConsumer

logger = logging.getLogger(__name__)

class ConsumerManager:
    """Manages multiple Kafka consumers as async tasks."""
    
    def __init__(self):
        self.consumers = [
            OHLCVConsumer(),
            QuotesConsumer(),
            # Add other topic consumers here
        ]
        self.tasks: List[asyncio.Task] = []
    
    async def start_all(self) -> None:
        """Start all consumers as concurrent tasks."""
        for consumer in self.consumers:
            task = asyncio.create_task(consumer.start())
            self.tasks.append(task)
            logger.info(f"Started consumer task for {consumer.topic}")
        
        # Wait for all tasks (they run indefinitely)
        await asyncio.gather(*self.tasks)
    
    async def stop_all(self) -> None:
        """Gracefully stop all consumer tasks."""
        for task in self.tasks:
            task.cancel()
        
        await asyncio.gather(*self.tasks, return_exceptions=True)
        logger.info("All consumer tasks stopped")

# CLI entry point
# src/dataplat/cli/consume.py
async def main():
    manager = ConsumerManager()
    try:
        await manager.start_all()
    except KeyboardInterrupt:
        await manager.stop_all()

if __name__ == "__main__":
    asyncio.run(main())
```

Add to justfile:
```makefile
# Start all Kafka consumers
kafka-consume:
    uv run python -m dataplat.cli.consume

# Start specific consumer
kafka-consume-ohlcv:
    uv run python -c "
    import asyncio
    from dataplat.kafka.consumers.ohlcv_consumer import OHLCVConsumer
    asyncio.run(OHLCVConsumer().start())
    "
```

---

## 7. Dead Letter Queue Pattern

### 7.1 DLQ Topic Configuration

```python
# Add to TOPIC_CONFIGS in topics.py
"dlq.failed_messages": TopicConfig(
    name="dlq.failed_messages",
    partitions=10,
    replication_factor=3,
    config={
        "min.insync.replicas": 2,
        "retention.ms": 2592000000,  # 30 days for investigation
        "compression.type": "lz4",
        "cleanup.policy": "delete"
    }
)
```

### 7.2 DLQ Producer Implementation

```python
# src/dataplat/kafka/dlq.py
"""Dead Letter Queue for failed message processing."""

import json
import logging
from typing import Dict, Any, Optional
from confluent_kafka import Producer, Message
from dataplat.config import settings

logger = logging.getLogger(__name__)

class DeadLetterQueue:
    """Produces failed messages to DLQ topic with error metadata."""
    
    def __init__(self):
        self.producer = Producer({
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "acks": "all",
            "retries": 3,
        })
        self.dlq_topic = "dlq.failed_messages"
    
    async def send_message(
        self,
        original_message: Message,
        error: Exception,
        consumer_group: str,
        processing_timestamp: str
    ) -> None:
        """Send failed message to DLQ with error context."""
        
        # Create DLQ payload with original message + error metadata
        dlq_payload = {
            "original_topic": original_message.topic(),
            "original_partition": original_message.partition(),
            "original_offset": original_message.offset(),
            "original_key": original_message.key().decode() if original_message.key() else None,
            "original_value": original_message.value().decode() if original_message.value() else None,
            "original_headers": dict(original_message.headers()) if original_message.headers() else {},
            "error_message": str(error),
            "error_type": type(error).__name__,
            "consumer_group": consumer_group,
            "processing_timestamp": processing_timestamp,
            "failed_at": "timestamp_now_iso"
        }
        
        try:
            self.producer.produce(
                topic=self.dlq_topic,
                key=f"{original_message.topic()}:{consumer_group}",
                value=json.dumps(dlq_payload),
                callback=self._delivery_callback
            )
            self.producer.flush()
            
        except Exception as e:
            logger.error(f"Failed to send message to DLQ: {e}")
    
    def _delivery_callback(self, err: Optional[Exception], msg: Message) -> None:
        """Callback for DLQ message delivery confirmation."""
        if err:
            logger.error(f"DLQ message delivery failed: {err}")
        else:
            logger.info(f"Message sent to DLQ: {msg.topic()}[{msg.partition()}]")

# Module singleton
dlq = DeadLetterQueue()
```

### 7.3 Integration with Consumer

Update the consumer's `_send_to_dlq` method:

```python
async def _send_to_dlq(self, msg: Message) -> None:
    """Send malformed message to dead letter queue."""
    from dataplat.kafka.dlq import dlq
    import datetime
    
    await dlq.send_message(
        original_message=msg,
        error=Exception("Deserialization failed"),
        consumer_group=self.consumer._group_id,
        processing_timestamp=datetime.datetime.now().isoformat()
    )
```

### 7.4 DLQ Monitoring

```python
# src/dataplat/cli/monitor_dlq.py
"""Monitor and analyze dead letter queue messages."""

from confluent_kafka import Consumer
import json

def monitor_dlq():
    """Print recent DLQ messages for debugging."""
    consumer = Consumer({
        "bootstrap.servers": "localhost:29092",
        "group.id": "dlq-monitor",
        "auto.offset.reset": "latest"
    })
    
    consumer.subscribe(["dlq.failed_messages"])
    
    try:
        while True:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
                
            if msg.error():
                continue
            
            payload = json.loads(msg.value())
            print(f"DLQ Message:")
            print(f"  Original Topic: {payload['original_topic']}")
            print(f"  Error: {payload['error_message']}")
            print(f"  Consumer Group: {payload['consumer_group']}")
            print(f"  Failed At: {payload['failed_at']}")
            print("---")
            
    except KeyboardInterrupt:
        pass
    finally:
        consumer.close()

if __name__ == "__main__":
    monitor_dlq()
```

---

## 8. Integration with Existing IngestPipeline

### 8.1 Kafka Producer Integration

Modify the existing pipeline to produce to Kafka instead of direct ClickHouse insertion:

```python
# src/dataplat/kafka/producer.py
"""Kafka producer for ingestion pipelines."""

import logging
from typing import Dict, Any, List
from confluent_kafka import Producer
from dataplat.config import settings
from dataplat.kafka.schema_client import schema_manager

logger = logging.getLogger(__name__)

class DataPlatProducer:
    """Kafka producer for sending extracted data to topics."""
    
    def __init__(self):
        self.producer = Producer({
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "acks": "all",          # Wait for all replicas
            "retries": 3,           # Retry failed sends
            "batch.size": 16384,    # Batch messages for throughput
            "linger.ms": 5,         # Small delay to batch messages
            "compression.type": "snappy",
        })
        self._serializers = {}
    
    def get_serializer(self, schema_name: str):
        """Get cached Avro serializer for schema."""
        if schema_name not in self._serializers:
            self._serializers[schema_name] = schema_manager.get_serializer(schema_name)
        return self._serializers[schema_name]
    
    async def produce_records(
        self,
        topic: str,
        records: List[Dict[str, Any]],
        schema_name: str,
        key_field: str = "ticker"
    ) -> None:
        """Produce list of records to Kafka topic."""
        
        serializer = self.get_serializer(schema_name)
        
        for record in records:
            try:
                key = record.get(key_field, "").encode('utf-8')
                value = serializer(record, None)  # Serialize with Avro
                
                self.producer.produce(
                    topic=topic,
                    key=key,
                    value=value,
                    callback=self._delivery_callback
                )
                
            except Exception as e:
                logger.error(f"Failed to produce record {record}: {e}")
        
        # Flush to ensure all messages are sent
        self.producer.flush()
    
    def _delivery_callback(self, err, msg):
        """Callback for message delivery confirmation."""
        if err:
            logger.error(f"Message delivery failed: {err}")
        else:
            logger.debug(f"Message delivered to {msg.topic()}[{msg.partition()}]")
    
    def close(self):
        """Clean shutdown of producer."""
        self.producer.flush()

# Module singleton
producer = DataPlatProducer()
```

### 8.2 Modified IngestPipeline with Kafka

```python
# src/dataplat/ingestion/kafka_pipeline.py
"""IngestPipeline with Kafka integration."""

from typing import List, Dict
import polars as pl
from dataplat.ingestion.base import IngestPipeline
from dataplat.kafka.producer import producer

class KafkaIngestPipeline(IngestPipeline):
    """
    Pipeline that produces extracted data to Kafka instead of direct ClickHouse.
    Consumer handles the Transform → Load phases.
    """
    
    def __init__(self, topic: str, schema_name: str):
        self.topic = topic
        self.schema_name = schema_name
    
    def transform(self, raw: List[dict]) -> pl.DataFrame:
        """Not used in Kafka mode - transform happens in consumer."""
        raise NotImplementedError("Transform happens in Kafka consumer")
    
    def load(self, df: pl.DataFrame) -> int:
        """Not used in Kafka mode - load happens in consumer."""
        raise NotImplementedError("Load happens in Kafka consumer")
    
    async def run(self, **params) -> int:
        """Extract → Produce to Kafka (consumer handles transform/load)."""
        raw = self.extract(**params)
        if not raw:
            return 0
        
        await producer.produce_records(
            topic=self.topic,
            records=raw,
            schema_name=self.schema_name
        )
        
        return len(raw)
```

### 8.3 Schwab Historical Pipeline with Kafka

```python
# src/dataplat/ingestion/schwab/kafka_historical.py
"""Schwab historical pipeline that produces to Kafka."""

from dataplat.ingestion.kafka_pipeline import KafkaIngestPipeline
from dataplat.ingestion.schwab.client import get_schwab_client

class SchwabKafkaHistoricalPipeline(KafkaIngestPipeline):
    """Schwab historical OHLCV → Kafka topic."""
    
    def __init__(self):
        super().__init__(
            topic="schwab.ohlcv.daily",
            schema_name="ohlcv"
        )
        self.client = get_schwab_client()
    
    def extract(self, ticker: str, years: int = 20) -> List[Dict]:
        """Extract historical OHLCV from Schwab API."""
        response = self.client.price_history(
            symbol=ticker,
            periodType="year",
            period=years,
            frequencyType="daily",
            frequency=1
        )
        
        raw_records = []
        for candle in response.get("candles", []):
            record = {
                "ticker": ticker,
                "timestamp": candle["datetime"],  # Epoch millis
                "open": candle["open"],
                "high": candle["high"], 
                "low": candle["low"],
                "close": candle["close"],
                "volume": candle["volume"],
                "vwap": None,  # Schwab daily doesn't provide
                "transactions": None,  # Schwab daily doesn't provide
                "source": "schwab"
            }
            raw_records.append(record)
        
        return raw_records
```

### 8.4 Migration Strategy: Dual Mode

Support both direct ClickHouse and Kafka modes during transition:

```python
# src/dataplat/ingestion/schwab/historical.py
"""Schwab historical pipeline with dual mode support."""

from dataplat.config import settings
from dataplat.ingestion.base import IngestPipeline

class SchwabHistoricalPipeline(IngestPipeline):
    
    def run(self, **params) -> int:
        """Route to Kafka or direct ClickHouse based on config."""
        if settings.kafka_enabled:
            # Use Kafka mode
            return await self._run_kafka_mode(**params)
        else:
            # Use direct ClickHouse mode (existing)
            return self._run_direct_mode(**params)
            
    async def _run_kafka_mode(self, **params) -> int:
        """Extract → Kafka (transform/load in consumer)."""
        raw = self.extract(**params)
        await producer.produce_records(...)
        return len(raw)
        
    def _run_direct_mode(self, **params) -> int:
        """Extract → Transform → Load (existing path)."""
        raw = self.extract(**params)
        df = self.transform(raw)
        return self.load(df)
```

Add to config.py:
```python
class Settings(BaseSettings):
    # ... existing settings ...
    
    # ── Kafka ──────────────────────────────────────────
    kafka_enabled: bool = False
    kafka_bootstrap_servers: str = "localhost:29092"
    kafka_schema_registry_url: str = "http://localhost:8082"
```

---

## 9. Monitoring and Observability

### 9.1 Consumer Lag Monitoring

```python
# src/dataplat/monitoring/consumer_lag.py
"""Monitor Kafka consumer lag for scaling decisions."""

from confluent_kafka.admin import AdminClient
from confluent_kafka import TopicPartition, Consumer
import time

class ConsumerLagMonitor:
    """Monitor consumer lag across all topics and groups."""
    
    def __init__(self):
        self.admin_client = AdminClient({
            "bootstrap.servers": settings.kafka_bootstrap_servers
        })
    
    def get_consumer_lag(self, group_id: str, topic: str) -> Dict[int, int]:
        """Get lag per partition for a consumer group."""
        consumer = Consumer({
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "group.id": f"{group_id}-lag-monitor"  # Separate group for monitoring
        })
        
        # Get committed offsets
        partitions = [TopicPartition(topic, p) for p in range(60)]  # Max partitions
        committed = consumer.committed(partitions)
        
        # Get high water marks (latest offsets)
        high_water_marks = consumer.get_watermark_offsets(partitions)
        
        lag_by_partition = {}
        for tp in committed:
            if tp.offset >= 0:  # Valid committed offset
                high_water = high_water_marks[tp.partition][1] 
                lag = high_water - tp.offset
                lag_by_partition[tp.partition] = lag
                
        consumer.close()
        return lag_by_partition
    
    def total_lag(self, group_id: str, topic: str) -> int:
        """Get total lag across all partitions."""
        lag_by_partition = self.get_consumer_lag(group_id, topic)
        return sum(lag_by_partition.values())
    
    def should_scale_up(self, group_id: str, topic: str, threshold: int = 100000) -> bool:
        """Check if consumer group should be scaled up."""
        total_lag = self.total_lag(group_id, topic)
        return total_lag > threshold

# CLI monitoring command
# src/dataplat/cli/monitor_lag.py
def monitor_all_consumer_lag():
    """Print consumer lag for all groups.""" 
    monitor = ConsumerLagMonitor()
    
    consumer_groups = [
        ("ohlcv-consumer-group", "schwab.ohlcv.daily"),
        ("quotes-consumer-group", "schwab.quotes.realtime"),
        ("options-consumer-group", "schwab.options.chains"),
    ]
    
    while True:
        print("\n=== Consumer Lag Report ===")
        for group_id, topic in consumer_groups:
            try:
                total_lag = monitor.total_lag(group_id, topic)
                should_scale = monitor.should_scale_up(group_id, topic)
                
                print(f"{group_id:30} {topic:30} Lag: {total_lag:>8} {'🔥 SCALE UP' if should_scale else '✅'}")
            except Exception as e:
                print(f"{group_id:30} {topic:30} Error: {e}")
        
        time.sleep(30)  # Check every 30 seconds
```

### 9.2 Health Checks

```python
# src/dataplat/monitoring/health.py
"""Health checks for Kafka infrastructure."""

import asyncio
from confluent_kafka import Producer, Consumer
from dataplat.config import settings

class KafkaHealthChecker:
    """Check Kafka cluster and consumer health."""
    
    async def check_broker_connectivity(self) -> bool:
        """Test connection to Kafka brokers."""
        try:
            producer = Producer({
                "bootstrap.servers": settings.kafka_bootstrap_servers,
                "socket.timeout.ms": 5000,
            })
            # Get broker metadata (will fail if brokers unreachable)
            metadata = producer.list_topics(timeout=5)
            producer.flush()
            return len(metadata.brokers) > 0
        except Exception:
            return False
    
    async def check_schema_registry(self) -> bool:
        """Test Schema Registry connectivity."""
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{settings.kafka_schema_registry_url}/subjects",
                    timeout=5.0
                )
                return response.status_code == 200
        except Exception:
            return False
    
    async def check_clickhouse_connectivity(self) -> bool:
        """Test ClickHouse connectivity (for consumers)."""
        try:
            from dataplat.db.client import get_clickhouse_client
            client = get_clickhouse_client()
            result = client.execute("SELECT 1")
            return result[0][0] == 1
        except Exception:
            return False
    
    async def full_health_check(self) -> Dict[str, bool]:
        """Run all health checks."""
        return {
            "kafka_brokers": await self.check_broker_connectivity(),
            "schema_registry": await self.check_schema_registry(), 
            "clickhouse": await self.check_clickhouse_connectivity(),
        }

# Health check CLI
# src/dataplat/cli/health.py
async def main():
    checker = KafkaHealthChecker()
    health = await checker.full_health_check()
    
    print("\n=== DataPlat Health Check ===")
    for component, status in health.items():
        emoji = "✅" if status else "❌"
        print(f"{emoji} {component:20} {'OK' if status else 'FAILED'}")
    
    overall = all(health.values())
    print(f"\nOverall Status: {'✅ HEALTHY' if overall else '❌ DEGRADED'}")

if __name__ == "__main__":
    asyncio.run(main())
```

Add to justfile:
```makefile
# Check DataPlat health
kafka-health:
    uv run python -m dataplat.cli.health

# Monitor consumer lag
kafka-lag:
    uv run python -m dataplat.cli.monitor_lag

# Monitor DLQ for failed messages
kafka-dlq:
    uv run python -m dataplat.cli.monitor_dlq
```

### 9.3 Metrics Collection (Future)

For production, integrate with Prometheus/Grafana:

```python
# src/dataplat/monitoring/metrics.py (future implementation)
"""Prometheus metrics for Kafka consumers."""

from prometheus_client import Counter, Histogram, Gauge

# Metrics
messages_processed = Counter('dataplat_messages_processed_total', 
                           'Total messages processed', ['topic', 'consumer_group'])

processing_duration = Histogram('dataplat_processing_duration_seconds',
                              'Time spent processing batches', ['topic'])

consumer_lag = Gauge('dataplat_consumer_lag',
                    'Current consumer lag', ['topic', 'consumer_group', 'partition'])

clickhouse_insert_errors = Counter('dataplat_clickhouse_errors_total',
                                 'ClickHouse insert errors', ['table'])
```

---

## 10. Configuration Updates

### 10.1 Environment Variables

Add to `config.py`:

```python
class Settings(BaseSettings):
    # ... existing settings ...
    
    # ── Kafka ──────────────────────────────────────────
    kafka_enabled: bool = False
    kafka_bootstrap_servers: str = "localhost:29092"
    kafka_schema_registry_url: str = "http://localhost:8082"
    
    # Consumer settings
    kafka_consumer_batch_size: int = 5000
    kafka_consumer_flush_interval: float = 5.0
    kafka_consumer_group_prefix: str = "dataplat"
    
    # Producer settings  
    kafka_producer_acks: str = "all"
    kafka_producer_retries: int = 3
    kafka_producer_batch_size: int = 16384
    kafka_producer_linger_ms: int = 5
    kafka_producer_compression: str = "snappy"
```

### 10.2 .env.example Updates

```env
# === Kafka/Redpanda ===
KAFKA_ENABLED=false
KAFKA_BOOTSTRAP_SERVERS=localhost:29092
KAFKA_SCHEMA_REGISTRY_URL=http://localhost:8082

# Consumer tuning
KAFKA_CONSUMER_BATCH_SIZE=5000
KAFKA_CONSUMER_FLUSH_INTERVAL=5.0

# Producer tuning
KAFKA_PRODUCER_ACKS=all
KAFKA_PRODUCER_COMPRESSION=snappy
```

---

## 11. Build Order and Migration Path

### 11.1 Phase 1: Infrastructure Setup (Week 1)

**Deliverables:**
- [ ] Update `pyproject.toml` with confluent-kafka dependencies
- [ ] Update `docker-compose.yml` with Redpanda + Console
- [ ] Update `justfile` with Kafka commands
- [ ] Create topic configuration and schema definitions
- [ ] Add Kafka settings to `config.py` and `.env.example`

**Verification:**
```bash
just kafka-up
just kafka-health  # All green
just kafka-create-topics
just kafka-topics  # Shows all defined topics
```

### 11.2 Phase 2: Base Consumer Framework (Week 2)

**Deliverables:**
- [ ] Schema registry client and Avro schema management
- [ ] Base `PolarsKafkaConsumer` with batching logic
- [ ] Dead Letter Queue producer and monitoring
- [ ] Health checks and lag monitoring

**Verification:**
```bash
# Produce test message
echo '{"ticker":"AAPL","timestamp":1693612800000,"open":180.0,"high":181.0,"low":179.5,"close":180.5,"volume":50000000,"source":"test"}' | \
  kafka-console-producer --broker-list localhost:29092 --topic schwab.ohlcv.daily

# Start consumer
just kafka-consume-ohlcv

# Verify data in ClickHouse
just ch-shell
SELECT * FROM ohlcv WHERE source = 'test';
```

### 11.3 Phase 3: Pipeline Integration (Week 3)

**Deliverables:**
- [ ] Kafka producer integration
- [ ] Topic-specific consumers (OHLCV, quotes, fundamentals)
- [ ] Modified ingestion pipelines with dual-mode support
- [ ] Consumer manager for orchestrating multiple consumers

**Verification:**
```bash
# Test end-to-end pipeline
just backfill --source schwab --tickers AAPL --kafka-mode
just kafka-consume  # Should process and insert into ClickHouse
just ch-stats  # Verify row counts
```

### 11.4 Phase 4: Production Readiness (Week 4)

**Deliverables:**
- [ ] Production topic configurations
- [ ] Comprehensive monitoring and alerting
- [ ] Consumer scaling automation based on lag
- [ ] Documentation and runbooks

**Verification:**
```bash
# Load test
just backfill --source polygon --universe spy --kafka-mode --concurrency 10
just kafka-lag  # Monitor consumer performance
just kafka-health  # All systems operational
```

---

## 12. Open Questions and Considerations

### 12.1 Schema Evolution Strategy

**Question:** How do we handle schema changes without breaking consumers?

**Recommendation:** Use Avro's schema evolution features:
- Only add optional fields with defaults
- Never remove fields or change types
- Use schema registry compatibility modes
- Version schemas with semantic versioning

### 12.2 Exactly-Once Semantics

**Question:** Do we need exactly-once delivery guarantees?

**Analysis:**
- **OHLCV/fundamentals:** ClickHouse `ReplacingMergeTree` handles duplicates
- **Real-time quotes:** Some duplication acceptable for speed
- **Account positions:** Need exactly-once (money involved)

**Recommendation:** 
- Use idempotent producer + `ReplacingMergeTree` for most data
- Implement transactional consumers only for financial account data

### 12.3 Cross-Region Deployment

**Question:** How do we handle multi-region deployments?

**Future consideration:** 
- Redpanda supports rack awareness and cross-region replication
- MirrorMaker 2.0 for cross-region topic mirroring
- Regional consumers for latency optimization

### 12.4 Cost vs Benefit Analysis

**Question:** Is Kafka complexity worth it for current scale?

**Analysis:**
| Factor | Direct ClickHouse | With Kafka |
|--------|------------------|------------|
| Complexity | Low | High |
| Real-time capability | Limited | Excellent |
| Horizontal scaling | Manual | Automatic |
| Monitoring needs | Simple | Complex |
| Infrastructure cost | Lower | Higher |

**Recommendation:** Start with Kafka infrastructure but begin in "pass-through" mode (minimal buffering). Scale up Kafka usage as real-time requirements grow.

---

## Summary

This implementation spec provides a complete production-ready Kafka infrastructure for the DataPlat project:

1. **Local Development**: Single-node Redpanda with Console UI
2. **Production Reference**: 3-node cluster with proper replication
3. **Python Client**: confluent-kafka with Avro schema registry
4. **Consumer Pattern**: Polars batching with automatic offset management
5. **Operational**: Dead letter queues, health checks, lag monitoring
6. **Integration**: Preserves existing pipeline interfaces

The design prioritizes simplicity and incremental adoption - existing pipelines continue to work while new Kafka capabilities can be enabled feature by feature.

**Next Steps:**
1. Review and approve this spec with the team
2. Begin Phase 1 implementation (infrastructure setup)
3. Validate with small-scale testing before full deployment
4. Document operational procedures for production deployment