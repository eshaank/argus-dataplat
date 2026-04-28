-- 049_commodity_intraday_views: Aggregated views from intraday commodity tables
-- 30m from 15m, 2h from 1h

-- 30-minute bars from 15m source
CREATE OR REPLACE VIEW v_commodity_ohlcv_30m AS
SELECT
    ticker,
    name,
    toStartOfInterval(timestamp, INTERVAL 30 minute) AS timestamp,
    argMin(open, timestamp) AS open,
    max(high) AS high,
    min(low) AS low,
    argMax(close, timestamp) AS close,
    sum(volume) AS volume
FROM commodities_ohlcv_15m FINAL
GROUP BY ticker, name, toStartOfInterval(timestamp, INTERVAL 30 minute)
ORDER BY ticker, timestamp;

-- 2-hour bars from 1h source
CREATE OR REPLACE VIEW v_commodity_ohlcv_2h AS
SELECT
    ticker,
    name,
    toStartOfInterval(timestamp, INTERVAL 2 hour) AS timestamp,
    argMin(open, timestamp) AS open,
    max(high) AS high,
    min(low) AS low,
    argMax(close, timestamp) AS close,
    sum(volume) AS volume
FROM commodities_ohlcv_1h FINAL
GROUP BY ticker, name, toStartOfInterval(timestamp, INTERVAL 2 hour)
ORDER BY ticker, timestamp;
