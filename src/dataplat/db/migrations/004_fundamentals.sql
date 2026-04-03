-- 004_fundamentals: Financial statements
-- Source: SEC EDGAR (NOT Polygon)

CREATE TABLE IF NOT EXISTS fundamentals (
    ticker         LowCardinality(String),
    period_end     Date,
    report_type    Enum8('income' = 1, 'balance' = 2, 'cashflow' = 3),
    fiscal_year    UInt16,
    fiscal_quarter Enum8('Q1' = 1, 'Q2' = 2, 'Q3' = 3, 'Q4' = 4, 'FY' = 5),
    data           String,
    source         LowCardinality(String)   DEFAULT 'sec_edgar',
    ingested_at    DateTime                 DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYear(period_end)
ORDER BY (ticker, period_end, report_type)
