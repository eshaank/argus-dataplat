-- 014_option_chains_v2: Expanded option chain snapshots with full greeks
-- Replaces 005_option_chains (which had no data)
-- Source: ThetaData v3 (8yr backfill) + Schwab (ongoing daily)
-- CODEC(Delta, ZSTD(1)) on all numeric columns — matches ohlcv pattern

DROP TABLE IF EXISTS option_chains;

CREATE TABLE IF NOT EXISTS option_chains (
    -- Contract identity
    underlying        LowCardinality(String),
    expiration        Date                            CODEC(Delta, ZSTD(1)),
    strike            Float64                         CODEC(Delta, ZSTD(1)),
    put_call          Enum8('call' = 1, 'put' = 2),

    -- OHLCV
    open              Nullable(Float64)               CODEC(Delta, ZSTD(1)),
    high              Nullable(Float64)               CODEC(Delta, ZSTD(1)),
    low               Nullable(Float64)               CODEC(Delta, ZSTD(1)),
    close             Nullable(Float64)               CODEC(Delta, ZSTD(1)),
    volume            UInt32                           DEFAULT 0   CODEC(Delta, ZSTD(1)),
    trade_count       UInt32                           DEFAULT 0   CODEC(Delta, ZSTD(1)),

    -- Quote
    bid               Float64                         CODEC(Delta, ZSTD(1)),
    ask               Float64                         CODEC(Delta, ZSTD(1)),
    bid_size          UInt32                           DEFAULT 0   CODEC(Delta, ZSTD(1)),
    ask_size          UInt32                           DEFAULT 0   CODEC(Delta, ZSTD(1)),

    -- Greeks — 1st order
    delta             Float64                         CODEC(ZSTD(1)),
    gamma             Float64                         CODEC(ZSTD(1)),
    theta             Float64                         CODEC(ZSTD(1)),
    vega              Float64                         CODEC(ZSTD(1)),
    rho               Float64                         CODEC(ZSTD(1)),

    -- Greeks -- 2nd order (ThetaData provides, Schwab does not)
    vanna             Nullable(Float64)               CODEC(ZSTD(1)),
    charm             Nullable(Float64)               CODEC(ZSTD(1)),
    vomma             Nullable(Float64)               CODEC(ZSTD(1)),
    veta              Nullable(Float64)               CODEC(ZSTD(1)),
    epsilon           Nullable(Float64)               CODEC(ZSTD(1)),
    lambda            Nullable(Float64)               CODEC(ZSTD(1)),

    -- Greeks — 3rd order (ThetaData bonus)
    vera              Nullable(Float64)               CODEC(ZSTD(1)),
    speed             Nullable(Float64)               CODEC(ZSTD(1)),
    zomma             Nullable(Float64)               CODEC(ZSTD(1)),
    color             Nullable(Float64)               CODEC(ZSTD(1)),
    ultima            Nullable(Float64)               CODEC(ZSTD(1)),

    -- Volatility
    implied_vol       Float64                         CODEC(ZSTD(1)),
    iv_error          Nullable(Float64)               CODEC(ZSTD(1)),

    -- Open interest
    open_interest     UInt32                           DEFAULT 0   CODEC(Delta, ZSTD(1)),

    -- Context
    underlying_price  Nullable(Float64)               CODEC(Delta, ZSTD(1)),

    -- Metadata
    snapshot_date     Date                            CODEC(Delta, ZSTD(1)),
    source            LowCardinality(String)           DEFAULT 'thetadata',
    ingested_at       DateTime                         DEFAULT now() CODEC(Delta, ZSTD(1))
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYear(snapshot_date)
ORDER BY (underlying, expiration, strike, put_call, snapshot_date);
