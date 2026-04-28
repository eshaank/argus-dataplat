-- 032_eia_petroleum_monthly: Monthly international petroleum data from EIA
-- Source: EIA API v2 — international production + US imports by country
-- ~2 month lag on international data

CREATE TABLE IF NOT EXISTS eia_petroleum_monthly (
    date                   Date,

    -- Global production (thousand bbl/day)
    opec_production        Nullable(Float64)    CODEC(Delta, ZSTD(3)),
    us_production          Nullable(Float64)    CODEC(Delta, ZSTD(3)),
    russia_production      Nullable(Float64)    CODEC(Delta, ZSTD(3)),
    saudi_production       Nullable(Float64)    CODEC(Delta, ZSTD(3)),
    iran_production        Nullable(Float64)    CODEC(Delta, ZSTD(3)),
    iraq_production        Nullable(Float64)    CODEC(Delta, ZSTD(3)),
    uae_production         Nullable(Float64)    CODEC(Delta, ZSTD(3)),
    world_production       Nullable(Float64)    CODEC(Delta, ZSTD(3)),

    -- US imports by origin (thousand bbl/day)
    imports_persian_gulf   Nullable(Float64)    CODEC(Delta, ZSTD(3)),
    imports_canada         Nullable(Float64)    CODEC(Delta, ZSTD(3)),
    imports_mexico         Nullable(Float64)    CODEC(Delta, ZSTD(3)),
    imports_total          Nullable(Float64)    CODEC(Delta, ZSTD(3)),

    source                 LowCardinality(String) DEFAULT 'eia',
    ingested_at            DateTime               DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYear(date)
ORDER BY (date)
