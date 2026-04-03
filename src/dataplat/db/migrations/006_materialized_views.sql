-- 006_materialized_views: Auto-aggregated OHLCV at coarser resolutions
-- All views fire on every INSERT to ohlcv — zero manual maintenance.

-- 5-minute bars
CREATE MATERIALIZED VIEW IF NOT EXISTS ohlcv_5min_mv
ENGINE = ReplacingMergeTree()
PARTITION BY toYear(bucket)
ORDER BY (ticker, bucket)
AS SELECT
    ticker,
    toStartOfFiveMinutes(timestamp) AS bucket,
    argMin(open, timestamp)         AS open,
    max(high)                       AS high,
    min(low)                        AS low,
    argMax(close, timestamp)        AS close,
    sum(volume)                     AS volume,
    sumIf(volume * vwap, vwap IS NOT NULL)
        / nullIf(sumIf(volume, vwap IS NOT NULL), 0) AS vwap,
    sum(transactions)               AS transactions,
    min(source)                     AS source
FROM ohlcv
GROUP BY ticker, bucket;

-- 15-minute bars
CREATE MATERIALIZED VIEW IF NOT EXISTS ohlcv_15min_mv
ENGINE = ReplacingMergeTree()
PARTITION BY toYear(bucket)
ORDER BY (ticker, bucket)
AS SELECT
    ticker,
    toStartOfFifteenMinutes(timestamp) AS bucket,
    argMin(open, timestamp)            AS open,
    max(high)                          AS high,
    min(low)                           AS low,
    argMax(close, timestamp)           AS close,
    sum(volume)                        AS volume,
    sumIf(volume * vwap, vwap IS NOT NULL)
        / nullIf(sumIf(volume, vwap IS NOT NULL), 0) AS vwap,
    sum(transactions)                  AS transactions,
    min(source)                        AS source
FROM ohlcv
GROUP BY ticker, bucket;

-- 1-hour bars
CREATE MATERIALIZED VIEW IF NOT EXISTS ohlcv_1h_mv
ENGINE = ReplacingMergeTree()
PARTITION BY toYear(bucket)
ORDER BY (ticker, bucket)
AS SELECT
    ticker,
    toStartOfHour(timestamp) AS bucket,
    argMin(open, timestamp)  AS open,
    max(high)                AS high,
    min(low)                 AS low,
    argMax(close, timestamp) AS close,
    sum(volume)              AS volume,
    sumIf(volume * vwap, vwap IS NOT NULL)
        / nullIf(sumIf(volume, vwap IS NOT NULL), 0) AS vwap,
    sum(transactions)        AS transactions,
    min(source)              AS source
FROM ohlcv
GROUP BY ticker, bucket;

-- Daily bars
CREATE MATERIALIZED VIEW IF NOT EXISTS ohlcv_daily_mv
ENGINE = ReplacingMergeTree()
PARTITION BY toYear(day)
ORDER BY (ticker, day)
AS SELECT
    ticker,
    toDate(timestamp)        AS day,
    argMin(open, timestamp)  AS open,
    max(high)                AS high,
    min(low)                 AS low,
    argMax(close, timestamp) AS close,
    sum(volume)              AS volume,
    sumIf(volume * vwap, vwap IS NOT NULL)
        / nullIf(sumIf(volume, vwap IS NOT NULL), 0) AS vwap,
    sum(transactions)        AS transactions,
    min(source)              AS source
FROM ohlcv
GROUP BY ticker, day
