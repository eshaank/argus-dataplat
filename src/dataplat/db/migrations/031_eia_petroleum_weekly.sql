-- 031_eia_petroleum_weekly: Weekly Petroleum Status Report from EIA
-- Source: EIA API v2 (https://api.eia.gov/v2/)
-- Released every Wednesday 10:30 AM ET

CREATE TABLE IF NOT EXISTS eia_petroleum_weekly (
    date                   Date,

    -- Supply (thousand bbl/day)
    crude_production       Nullable(Float64)    CODEC(Delta, ZSTD(3)),
    crude_imports          Nullable(Float64)    CODEC(Delta, ZSTD(3)),
    crude_exports          Nullable(Float64)    CODEC(Delta, ZSTD(3)),

    -- Stocks (thousand barrels)
    crude_stocks           Nullable(Float64)    CODEC(Delta, ZSTD(3)),
    spr_stocks             Nullable(Float64)    CODEC(Delta, ZSTD(3)),
    gasoline_stocks        Nullable(Float64)    CODEC(Delta, ZSTD(3)),
    distillate_stocks      Nullable(Float64)    CODEC(Delta, ZSTD(3)),

    -- Demand / product supplied (thousand bbl/day)
    product_supplied       Nullable(Float64)    CODEC(Delta, ZSTD(3)),
    gasoline_supplied      Nullable(Float64)    CODEC(Delta, ZSTD(3)),
    distillate_supplied    Nullable(Float64)    CODEC(Delta, ZSTD(3)),
    jet_fuel_supplied      Nullable(Float64)    CODEC(Delta, ZSTD(3)),

    -- Refining
    refinery_utilization   Nullable(Float64)    CODEC(Delta, ZSTD(3)),
    refinery_inputs        Nullable(Float64)    CODEC(Delta, ZSTD(3)),

    source                 LowCardinality(String) DEFAULT 'eia',
    ingested_at            DateTime               DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYear(date)
ORDER BY (date)
