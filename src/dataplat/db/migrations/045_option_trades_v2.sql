-- 045_option_trades_v2: Add sequence to ORDER BY for trade uniqueness
-- The OPRA sequence number is the unique identifier per trade.
-- Without it, ReplacingMergeTree deduplicates trades that happen at the
-- same millisecond on the same contract with the same size (~5% data loss).

DROP TABLE IF EXISTS option_trades;

CREATE TABLE IF NOT EXISTS option_trades (
    -- Contract identity
    underlying        LowCardinality(String),
    expiration        Date                            CODEC(Delta(2), ZSTD(1)),
    strike            Float64                         CODEC(Delta(8), ZSTD(1)),
    put_call          Enum8('call' = 1, 'put' = 2),

    -- Trade
    trade_timestamp   DateTime64(3)                   CODEC(Delta(8), ZSTD(1)),
    sequence          Int64                            CODEC(Delta(8), ZSTD(1)),
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
ORDER BY (underlying, toDate(trade_timestamp), expiration, strike, put_call, trade_timestamp, sequence);
