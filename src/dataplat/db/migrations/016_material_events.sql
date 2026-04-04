-- 016_material_events: 8-K material events with item codes
-- Source: SEC EDGAR /submissions/CIK{cik}.json (filtered to 8-K forms)

CREATE TABLE IF NOT EXISTS material_events (
    ticker              LowCardinality(String),
    cik                 String,
    accession_number    String,
    filed_date          Date,
    report_date         Nullable(Date),
    item_code           LowCardinality(String),
    item_description    LowCardinality(String),
    primary_doc         String,
    filing_url          String                  DEFAULT '',
    source              LowCardinality(String)  DEFAULT 'sec_edgar',
    ingested_at         DateTime                DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYear(filed_date)
ORDER BY (ticker, filed_date, item_code, accession_number)
