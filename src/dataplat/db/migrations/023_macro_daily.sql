-- 023_macro_daily: Daily macro indicators
-- Source: FRED (VIXCLS, DTWEXBGS, T10Y2Y, T10Y3M, DCOILWTICO, GOLDAMGBD228NLBM)

CREATE TABLE IF NOT EXISTS macro_daily (
    date                Date,
    vix                 Nullable(Float64),         -- VIXCLS: CBOE Volatility Index
    usd_index           Nullable(Float64),         -- DTWEXBGS: Trade-weighted USD index (broad)
    yield_curve_10y2y   Nullable(Float64),         -- T10Y2Y: 10Y minus 2Y Treasury spread
    yield_curve_10y3m   Nullable(Float64),         -- T10Y3M: 10Y minus 3M Treasury spread
    wti_crude           Nullable(Float64),         -- DCOILWTICO: WTI crude oil $/barrel
    gold_price          Nullable(Float64),         -- GOLDAMGBD228NLBM: London gold fixing $/oz (discontinued on FRED)
    source              LowCardinality(String)     DEFAULT 'fred',
    ingested_at         DateTime                   DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYear(date)
ORDER BY (date)
