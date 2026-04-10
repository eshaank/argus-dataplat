-- 037_update_commodity_views: Update views after splitting yfinance into commodities_ohlcv
-- commodity_prices now only has EIA energy spot prices
-- commodities_ohlcv has full OHLCV for all commodity futures

-- Replace v_commodity_latest: now only EIA energy spot prices
CREATE OR REPLACE VIEW v_commodity_latest AS
SELECT
    (SELECT toString(max(date)) FROM commodity_prices) AS date,
    (SELECT wti_crude FROM commodity_prices WHERE wti_crude IS NOT NULL ORDER BY date DESC LIMIT 1) AS wti_crude,
    (SELECT brent_crude FROM commodity_prices WHERE brent_crude IS NOT NULL ORDER BY date DESC LIMIT 1) AS brent_crude,
    (SELECT natural_gas FROM commodity_prices WHERE natural_gas IS NOT NULL ORDER BY date DESC LIMIT 1) AS natural_gas,
    (SELECT gasoline FROM commodity_prices WHERE gasoline IS NOT NULL ORDER BY date DESC LIMIT 1) AS gasoline,
    (SELECT heating_oil FROM commodity_prices WHERE heating_oil IS NOT NULL ORDER BY date DESC LIMIT 1) AS heating_oil;

-- Latest close for each commodity future
CREATE OR REPLACE VIEW v_commodities_ohlcv_latest AS
SELECT
    ticker,
    toString(date) AS date,
    open,
    high,
    low,
    close,
    volume
FROM commodities_ohlcv FINAL
WHERE (ticker, date) IN (
    SELECT ticker, max(date)
    FROM commodities_ohlcv
    GROUP BY ticker
)
ORDER BY ticker;

-- Daily returns per commodity
CREATE OR REPLACE VIEW v_commodity_returns AS
SELECT
    ticker,
    date,
    close,
    lagInFrame(close) OVER (PARTITION BY ticker ORDER BY date) AS prev_close,
    round((close - lagInFrame(close) OVER (PARTITION BY ticker ORDER BY date))
        / lagInFrame(close) OVER (PARTITION BY ticker ORDER BY date) * 100, 2) AS return_pct
FROM commodities_ohlcv FINAL
ORDER BY ticker, date;
