-- 039_update_commodities_views: Update views for ticker=yf symbol, name=human label

CREATE OR REPLACE VIEW v_commodities_ohlcv_latest AS
SELECT
    ticker,
    name,
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
ORDER BY name;

CREATE OR REPLACE VIEW v_commodity_returns AS
SELECT
    ticker,
    name,
    date,
    close,
    lagInFrame(close) OVER (PARTITION BY ticker ORDER BY date) AS prev_close,
    round((close - lagInFrame(close) OVER (PARTITION BY ticker ORDER BY date))
        / lagInFrame(close) OVER (PARTITION BY ticker ORDER BY date) * 100, 2) AS return_pct
FROM commodities_ohlcv FINAL
ORDER BY ticker, date;
