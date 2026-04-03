-- 009_treasury_yields: US Treasury bond yields (daily, 1962-present)
-- Source: Polygon /fed/v1/treasury-yields

CREATE TABLE IF NOT EXISTS treasury_yields (
    date                Date,
    yield_1_month       Nullable(Float64),
    yield_3_month       Nullable(Float64),
    yield_1_year        Nullable(Float64),
    yield_2_year        Nullable(Float64),
    yield_5_year        Nullable(Float64),
    yield_10_year       Nullable(Float64),
    yield_30_year       Nullable(Float64),
    source              LowCardinality(String) DEFAULT 'polygon',
    ingested_at         DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
ORDER BY date
