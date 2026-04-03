-- 010_inflation: CPI and PCE inflation metrics (monthly, 1947-present)
-- Source: Polygon /fed/v1/inflation

CREATE TABLE IF NOT EXISTS inflation (
    date                Date,
    cpi                 Nullable(Float64),
    cpi_core            Nullable(Float64),
    pce                 Nullable(Float64),
    pce_core            Nullable(Float64),
    pce_spending        Nullable(Float64),
    source              LowCardinality(String) DEFAULT 'polygon',
    ingested_at         DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
ORDER BY date
