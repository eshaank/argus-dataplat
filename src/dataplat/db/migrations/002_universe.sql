-- 002_universe: Ticker metadata
-- Source: Polygon reference API (or manual seed)

CREATE TABLE IF NOT EXISTS universe (
    ticker       String,
    name         String,
    type         LowCardinality(String),
    exchange     LowCardinality(String),
    sector       LowCardinality(Nullable(String)),
    sic_code     LowCardinality(Nullable(String)),
    market_cap   Nullable(Float64),
    active       Bool                     DEFAULT true,
    updated_at   DateTime                 DEFAULT now()
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY ticker
