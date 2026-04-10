-- 030_commodity_prices: Daily commodity spot/futures prices
-- Sources: FRED (gold, silver), EIA (energy), Yahoo Finance (metals, agriculture)

CREATE TABLE IF NOT EXISTS commodity_prices (
    date                Date,

    -- Precious metals (FRED)
    gold                Nullable(Float64)    CODEC(Delta, ZSTD(3)),  -- $/oz London fixing
    silver              Nullable(Float64)    CODEC(Delta, ZSTD(3)),  -- $/oz London fixing

    -- Energy (EIA)
    wti_crude           Nullable(Float64)    CODEC(Delta, ZSTD(3)),  -- $/barrel Cushing WTI
    brent_crude         Nullable(Float64)    CODEC(Delta, ZSTD(3)),  -- $/barrel Brent Europe
    natural_gas         Nullable(Float64)    CODEC(Delta, ZSTD(3)),  -- $/MMBtu Henry Hub
    gasoline            Nullable(Float64)    CODEC(Delta, ZSTD(3)),  -- $/gal regular
    heating_oil         Nullable(Float64)    CODEC(Delta, ZSTD(3)),  -- $/gal NY Harbor

    -- Industrial metals (Yahoo Finance futures)
    copper              Nullable(Float64)    CODEC(Delta, ZSTD(3)),  -- $/lb HG=F
    aluminum            Nullable(Float64)    CODEC(Delta, ZSTD(3)),  -- $/lb ALI=F

    -- Agriculture (Yahoo Finance futures)
    wheat               Nullable(Float64)    CODEC(Delta, ZSTD(3)),  -- $/bushel ZW=F
    corn                Nullable(Float64)    CODEC(Delta, ZSTD(3)),  -- $/bushel ZC=F
    cotton              Nullable(Float64)    CODEC(Delta, ZSTD(3)),  -- $/lb CT=F
    sugar               Nullable(Float64)    CODEC(Delta, ZSTD(3)),  -- $/lb SB=F
    coffee              Nullable(Float64)    CODEC(Delta, ZSTD(3)),  -- $/lb KC=F

    source              LowCardinality(String) DEFAULT 'mixed',
    ingested_at         DateTime               DEFAULT now()
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYear(date)
ORDER BY (date)
