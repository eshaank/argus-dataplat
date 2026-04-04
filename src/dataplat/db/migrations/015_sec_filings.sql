-- 015_sec_filings: Index of every SEC filing per company
-- Source: SEC EDGAR /submissions/CIK{cik}.json

CREATE TABLE IF NOT EXISTS sec_filings (
    ticker              LowCardinality(String),
    cik                 String,
    accession_number    String,
    form_type           LowCardinality(String),
    filed_date          Date,
    report_date         Nullable(Date),
    primary_doc         String,
    primary_doc_desc    Nullable(String),
    items               Nullable(String),
    is_xbrl             Bool                    DEFAULT false,
    filing_url          String                  DEFAULT '',
    source              LowCardinality(String)  DEFAULT 'sec_edgar',
    ingested_at         DateTime                DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYear(filed_date)
ORDER BY (ticker, filed_date, form_type, accession_number)
