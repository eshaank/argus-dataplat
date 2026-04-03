-- 008_stock_splits: Historical stock splits
-- Source: Polygon /v3/reference/splits

CREATE TABLE IF NOT EXISTS stock_splits (
    ticker              LowCardinality(String),
    execution_date      Date,
    split_from          Float64,
    split_to            Float64,
    source              LowCardinality(String) DEFAULT 'polygon',
    ingested_at         DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
ORDER BY (ticker, execution_date)
