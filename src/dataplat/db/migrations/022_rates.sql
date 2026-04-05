-- 022_rates: Daily interest rates + credit spreads
-- Source: FRED (DFF, SOFR, DBAA, DAAA, BAMLH0A0HYM2, BAMLC0A0CM, DFII10, DFII5, DCPF3M)

CREATE TABLE IF NOT EXISTS rates (
    date                Date,
    fed_funds_rate      Nullable(Float64),         -- DFF: Effective federal funds rate
    sofr                Nullable(Float64),         -- SOFR: Secured Overnight Financing Rate
    baa_yield           Nullable(Float64),         -- DBAA: Moody's BAA corporate bond yield
    aaa_yield           Nullable(Float64),         -- DAAA: Moody's AAA corporate bond yield
    hy_oas              Nullable(Float64),         -- BAMLH0A0HYM2: ICE BofA High Yield OAS
    ig_oas              Nullable(Float64),         -- BAMLC0A0CM: ICE BofA Investment Grade OAS
    tips_10y            Nullable(Float64),         -- DFII10: 10Y TIPS real yield
    tips_5y             Nullable(Float64),         -- DFII5: 5Y TIPS real yield
    commercial_paper_3m Nullable(Float64),         -- DCPF3M: 3-month commercial paper rate
    source              LowCardinality(String)     DEFAULT 'fred',
    ingested_at         DateTime                   DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYear(date)
ORDER BY (date)
