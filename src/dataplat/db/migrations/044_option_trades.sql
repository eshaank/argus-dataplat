-- 044_option_trades: Tick-level option trade data with NBBO at time of trade
-- Source: ThetaData v3 /option/history/trade_quote endpoint
-- Every individual fill reported by OPRA, paired with prevailing NBBO
-- Enables BTO/STO/BTC/STC classification via aggressor side + OI delta
--
-- Expected volume: ~1.4M rows/day for SPY, ~820K for QQQ, ~14K for ARM
-- Partitioned by month (trade_date) for manageable part sizes

CREATE TABLE IF NOT EXISTS option_trades (
    -- Contract identity
    underlying        LowCardinality(String),
    expiration        Date                            CODEC(Delta(2), ZSTD(1)),
    strike            Float64                         CODEC(Delta(8), ZSTD(1)),
    put_call          Enum8('call' = 1, 'put' = 2),

    -- Trade
    trade_timestamp   DateTime64(3)                   CODEC(Delta(8), ZSTD(1)),
    price             Float64                         CODEC(Delta(8), ZSTD(1)),
    size              UInt32                           CODEC(Delta(4), ZSTD(1)),
    exchange          UInt8                            CODEC(ZSTD(1)),
    condition         UInt8                            CODEC(ZSTD(1)),

    -- NBBO at time of trade
    bid               Float64                         CODEC(Delta(8), ZSTD(1)),
    ask               Float64                         CODEC(Delta(8), ZSTD(1)),
    bid_size          UInt32                           CODEC(Delta(4), ZSTD(1)),
    ask_size          UInt32                           CODEC(Delta(4), ZSTD(1)),

    -- Derived: aggressor side (computed on insert)
    -- 1=buy (at/above ask), 2=sell (at/below bid), 3=mid
    aggressor_side    Enum8('buy' = 1, 'sell' = 2, 'mid' = 3),

    -- Materialized columns
    trade_date        Date                            MATERIALIZED toDate(trade_timestamp),
    notional          Float64                         MATERIALIZED price * size * 100,

    -- Metadata
    source            LowCardinality(String)           DEFAULT 'thetadata',
    ingested_at       DateTime                         DEFAULT now() CODEC(Delta(4), ZSTD(1))
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(toDate(trade_timestamp))
ORDER BY (underlying, toDate(trade_timestamp), expiration, strike, put_call, trade_timestamp, size);
