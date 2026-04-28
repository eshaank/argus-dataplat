-- 048_commodities_ohlcv_intraday: Intraday OHLCV tables for commodity futures
-- 15m, 1h, 4h intervals from yfinance intraday data

-- 15-minute bars
CREATE TABLE IF NOT EXISTS commodities_ohlcv_15m (
    ticker              LowCardinality(String),    -- e.g. "GC=F"
    name                LowCardinality(String)     DEFAULT '',
    timestamp           DateTime('UTC'),
    open                Float64                    CODEC(Delta, ZSTD(3)),
    high                Float64                    CODEC(Delta, ZSTD(3)),
    low                 Float64                    CODEC(Delta, ZSTD(3)),
    close               Float64                    CODEC(Delta, ZSTD(3)),
    volume              UInt64                     CODEC(Delta, ZSTD(3)),
    source              LowCardinality(String)     DEFAULT 'yfinance',
    update_frequency    LowCardinality(String)     DEFAULT '15m',
    ingested_at         DateTime                   DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(timestamp)
ORDER BY (ticker, timestamp);

-- 1-hour bars
CREATE TABLE IF NOT EXISTS commodities_ohlcv_1h (
    ticker              LowCardinality(String),
    name                LowCardinality(String)     DEFAULT '',
    timestamp           DateTime('UTC'),
    open                Float64                    CODEC(Delta, ZSTD(3)),
    high                Float64                    CODEC(Delta, ZSTD(3)),
    low                 Float64                    CODEC(Delta, ZSTD(3)),
    close               Float64                    CODEC(Delta, ZSTD(3)),
    volume              UInt64                     CODEC(Delta, ZSTD(3)),
    source              LowCardinality(String)     DEFAULT 'yfinance',
    update_frequency    LowCardinality(String)     DEFAULT '1h',
    ingested_at         DateTime                   DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(timestamp)
ORDER BY (ticker, timestamp);

-- 4-hour bars
CREATE TABLE IF NOT EXISTS commodities_ohlcv_4h (
    ticker              LowCardinality(String),
    name                LowCardinality(String)     DEFAULT '',
    timestamp           DateTime('UTC'),
    open                Float64                    CODEC(Delta, ZSTD(3)),
    high                Float64                    CODEC(Delta, ZSTD(3)),
    low                 Float64                    CODEC(Delta, ZSTD(3)),
    close               Float64                    CODEC(Delta, ZSTD(3)),
    volume              UInt64                     CODEC(Delta, ZSTD(3)),
    source              LowCardinality(String)     DEFAULT 'yfinance',
    update_frequency    LowCardinality(String)     DEFAULT '4h',
    ingested_at         DateTime                   DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(timestamp)
ORDER BY (ticker, timestamp);
