-- 043_zbt_breadth: Zweig Breadth Thrust daily indicator table
-- Populated by: just zbt (Python compute pipeline)
-- Source data: ohlcv_daily (NYSE tickers)

CREATE TABLE IF NOT EXISTS zbt_breadth (
    day              Date,
    advancing        UInt32                CODEC(Delta, ZSTD(3)),
    declining        UInt32                CODEC(Delta, ZSTD(3)),
    unchanged        UInt32                CODEC(Delta, ZSTD(3)),
    total            UInt32                CODEC(Delta, ZSTD(3)),
    breadth_ratio    Float64               CODEC(Delta, ZSTD(3)),
    ema_10           Float64               CODEC(Delta, ZSTD(3)),
    oversold         Bool,      -- ema_10 < 0.40
    thrust           Bool,      -- ema_10 > 0.615
    signal_active    Bool,      -- oversold triggered, window still open
    days_in_window   Nullable(UInt8),      -- days since oversold trigger (NULL if no active setup)
    signal_fired     Bool,      -- ZBT signal confirmed
    ingested_at      DateTime DEFAULT now() CODEC(Delta, ZSTD(3))
)
ENGINE = ReplacingMergeTree(ingested_at)
ORDER BY (day);
