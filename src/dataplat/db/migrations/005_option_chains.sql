-- 005_option_chains: Option snapshots
-- Source: Schwab market data API (deferred implementation)

CREATE TABLE IF NOT EXISTS option_chains (
    underlying    LowCardinality(String),
    expiration    Date,
    strike        Float64,
    put_call      Enum8('call' = 1, 'put' = 2),
    bid           Float64,
    ask           Float64,
    last          Float64,
    volume        UInt32,
    open_interest UInt32,
    implied_vol   Float64,
    delta         Float64,
    gamma         Float64,
    theta         Float64,
    vega          Float64,
    snapshot_at   DateTime,
    ingested_at   DateTime                 DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(expiration)
ORDER BY (underlying, expiration, strike, put_call, snapshot_at)
