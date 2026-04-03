-- 007_dividends: Historical cash dividends
-- Source: Polygon /v3/reference/dividends

CREATE TABLE IF NOT EXISTS dividends (
    ticker              LowCardinality(String),
    ex_dividend_date    Date,
    declaration_date    Nullable(Date),
    record_date         Nullable(Date),
    pay_date            Nullable(Date),
    cash_amount         Float64,
    currency            LowCardinality(String) DEFAULT 'USD',
    frequency           UInt8,
    dividend_type       LowCardinality(String),
    source              LowCardinality(String) DEFAULT 'polygon',
    ingested_at         DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
ORDER BY (ticker, ex_dividend_date)
