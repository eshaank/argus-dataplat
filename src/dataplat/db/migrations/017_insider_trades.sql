-- 017_insider_trades: Form 4 insider transaction data
-- Source: SEC EDGAR Form 4 XML via /Archives/edgar/data/{cik}/{accession}/

CREATE TABLE IF NOT EXISTS insider_trades (
    ticker              LowCardinality(String),
    cik                 String,
    accession_number    String,
    filed_date          Date,
    report_date         Date,
    -- Reporter
    reporter_cik        Nullable(String),
    reporter_name       String,
    reporter_title      Nullable(String),
    is_officer          Bool                    DEFAULT false,
    is_director         Bool                    DEFAULT false,
    is_ten_pct_owner    Bool                    DEFAULT false,
    -- Transaction
    security_title      LowCardinality(String),
    transaction_code    LowCardinality(String),
    transaction_type    LowCardinality(String),
    is_derivative       Bool                    DEFAULT false,
    shares              Float64,
    price               Nullable(Float64),
    value               Nullable(Float64),
    acquired_or_disposed LowCardinality(String),
    shares_owned_after  Nullable(Float64),
    ownership_type      LowCardinality(String),
    -- Links
    primary_doc         String,
    filing_url          String                  DEFAULT '',
    source              LowCardinality(String)  DEFAULT 'sec_edgar',
    ingested_at         DateTime                DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYear(report_date)
ORDER BY (ticker, report_date, reporter_name, transaction_code, shares)
