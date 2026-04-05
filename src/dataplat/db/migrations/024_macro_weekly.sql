-- 024_macro_weekly: Weekly macro indicators
-- Source: FRED (STLFSI2, NFCI, MORTGAGE30US, ICSA, CCSA)

CREATE TABLE IF NOT EXISTS macro_weekly (
    date                    Date,
    financial_stress        Nullable(Float64),     -- STLFSI2: St. Louis Fed Financial Stress Index
    financial_conditions    Nullable(Float64),     -- NFCI: Chicago Fed National Financial Conditions Index
    mortgage_rate_30y       Nullable(Float64),     -- MORTGAGE30US: 30-year fixed mortgage rate
    initial_claims          Nullable(Float64),     -- ICSA: Initial jobless claims (thousands)
    continued_claims        Nullable(Float64),     -- CCSA: Continued jobless claims (thousands)
    source                  LowCardinality(String) DEFAULT 'fred',
    ingested_at             DateTime               DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYear(date)
ORDER BY (date)
