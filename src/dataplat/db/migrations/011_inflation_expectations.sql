-- 011_inflation_expectations: Market and model-based inflation expectations (monthly, 1982-present)
-- Source: Polygon /fed/v1/inflation-expectations

CREATE TABLE IF NOT EXISTS inflation_expectations (
    date                    Date,
    market_5_year           Nullable(Float64),
    market_10_year          Nullable(Float64),
    forward_years_5_to_10   Nullable(Float64),
    model_1_year            Nullable(Float64),
    model_5_year            Nullable(Float64),
    model_10_year           Nullable(Float64),
    model_30_year           Nullable(Float64),
    source                  LowCardinality(String) DEFAULT 'polygon',
    ingested_at             DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
ORDER BY date
