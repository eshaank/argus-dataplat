-- 042_ohlcv_daily: First-class daily OHLCV table (direct inserts, not a materialized view)
-- Source: Polygon grouped daily endpoint
-- Separate from the 1-min ohlcv table to avoid MV corruption

CREATE TABLE IF NOT EXISTS ohlcv_daily (
    ticker       LowCardinality(String),
    day          Date,
    open         Float64                   CODEC(Delta, ZSTD(3)),
    high         Float64                   CODEC(Delta, ZSTD(3)),
    low          Float64                   CODEC(Delta, ZSTD(3)),
    close        Float64                   CODEC(Delta, ZSTD(3)),
    volume       UInt64                    CODEC(Delta, ZSTD(3)),
    vwap         Nullable(Float64)         CODEC(Delta, ZSTD(3)),
    transactions Nullable(UInt32)          CODEC(Delta, ZSTD(3)),
    source       LowCardinality(String)    DEFAULT 'polygon',
    ingested_at  DateTime DEFAULT now()    CODEC(Delta, ZSTD(3))
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYear(day)
ORDER BY (ticker, day);
