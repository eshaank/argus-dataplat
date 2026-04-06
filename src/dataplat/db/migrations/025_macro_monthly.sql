-- 025_macro_monthly: Monthly + quarterly macro indicators
-- Source: FRED

CREATE TABLE IF NOT EXISTS macro_monthly (
    date                    Date,
    m2_money_supply         Nullable(Float64),     -- M2SL: M2 money stock (billions $)
    consumer_sentiment      Nullable(Float64),     -- UMCSENT: UMich Consumer Sentiment Index
    retail_sales            Nullable(Float64),     -- RSAFS: Retail sales (millions $)
    personal_savings_rate   Nullable(Float64),     -- PSAVERT: Personal savings as % of disposable income
    real_personal_income    Nullable(Float64),     -- RPI: Real personal income (billions 2017$)
    housing_starts          Nullable(Float64),     -- HOUST: Housing starts (thousands)
    case_shiller            Nullable(Float64),     -- CSUSHPINSA: S&P/Case-Shiller US Home Price Index
    industrial_production   Nullable(Float64),     -- INDPRO: Industrial Production Index (2017=100)
    capacity_utilization    Nullable(Float64),     -- TCU: Capacity Utilization (% of capacity)
    leading_index           Nullable(Float64),     -- USSLIND: Leading Index for the US
    nonfarm_payrolls        Nullable(Float64),     -- PAYEMS: Total nonfarm payrolls (thousands)
    auto_sales              Nullable(Float64),     -- TOTALSA: Total vehicle sales (millions, SAAR)
    bank_lending            Nullable(Float64),     -- BUSLOANS: Commercial & industrial loans (billions $)
    real_gdp                Nullable(Float64),     -- GDPC1: Real GDP (billions 2017$, quarterly)
    recession               Nullable(UInt8),       -- USREC: NBER recession indicator (0 or 1)
    sahm_rule               Nullable(Float64),     -- SAHMREALTIME: Sahm Rule recession indicator
    source                  LowCardinality(String) DEFAULT 'fred',
    ingested_at             DateTime               DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYear(date)
ORDER BY (date)
