-- 003_economic_series: FRED macro indicators

CREATE TABLE IF NOT EXISTS economic_series (
    series_id    LowCardinality(String),
    date         Date,
    value        Float64,
    source       LowCardinality(String)   DEFAULT 'fred',
    ingested_at  DateTime                 DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYear(date)
ORDER BY (series_id, date)
