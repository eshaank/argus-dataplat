-- 035_commodities_ohlcv: Daily OHLCV for commodity futures from Yahoo Finance
-- Covers precious metals, energy, industrial metals, grains, softs, livestock

CREATE TABLE IF NOT EXISTS commodities_ohlcv (
    ticker              LowCardinality(String),    -- e.g. "gold", "wti_crude", "corn"
    date                Date,
    open                Float64                    CODEC(Delta, ZSTD(3)),
    high                Float64                    CODEC(Delta, ZSTD(3)),
    low                 Float64                    CODEC(Delta, ZSTD(3)),
    close               Float64                    CODEC(Delta, ZSTD(3)),
    volume              UInt64                     CODEC(Delta, ZSTD(3)),
    source              LowCardinality(String)     DEFAULT 'yfinance',
    ingested_at         DateTime                   DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYear(date)
ORDER BY (ticker, date)
