-- 012_labor_market: Labor market indicators (monthly, 1948-present)
-- Source: Polygon /fed/v1/labor-market

CREATE TABLE IF NOT EXISTS labor_market (
    date                            Date,
    unemployment_rate               Nullable(Float64),
    labor_force_participation_rate  Nullable(Float64),
    avg_hourly_earnings             Nullable(Float64),
    job_openings                    Nullable(Float64),
    source                          LowCardinality(String) DEFAULT 'polygon',
    ingested_at                     DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
ORDER BY date
