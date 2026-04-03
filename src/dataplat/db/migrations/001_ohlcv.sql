-- 001_ohlcv: 1-minute OHLCV base table
-- Source: Polygon (one-off backfill) + Schwab (ongoing)
-- CODEC(Delta, ZSTD(1)) on all numeric columns — benchmarked at ~21 bytes/row

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
    source       LowCardinality(String)    DEFAULT 'schwab',
    ingested_at  DateTime                  CODEC(Delta, ZSTD(1))
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYear(timestamp)
ORDER BY (ticker, timestamp)
