-- 018_institutional_holders: SC 13G/13D institutional ownership filings
-- Source: SEC EDGAR SC 13G/13D XML via /Archives/edgar/data/{cik}/{accession}/

CREATE TABLE IF NOT EXISTS institutional_holders (
    ticker              LowCardinality(String),
    cik                 String,
    accession_number    String,
    filed_date          Date,
    event_date          Nullable(Date),
    -- Holder
    holder_cik          Nullable(String),
    holder_name         String,
    holder_type         LowCardinality(String),
    holder_address      Nullable(String),
    -- Position
    shares_held         Float64,
    class_percent       Nullable(Float64),
    sole_voting_power   Nullable(Float64),
    shared_voting_power Nullable(Float64),
    sole_dispositive    Nullable(Float64),
    shared_dispositive  Nullable(Float64),
    -- Filing info
    form_type           LowCardinality(String),
    amendment_number    Nullable(UInt8),
    is_amendment        Bool                    DEFAULT false,
    -- Links
    primary_doc         String,
    filing_url          String                  DEFAULT '',
    source              LowCardinality(String)  DEFAULT 'sec_edgar',
    ingested_at         DateTime                DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYear(filed_date)
ORDER BY (ticker, filed_date, holder_name, accession_number)
