-- Intraday Volume Profile — where does volume concentrate by minute of day?
-- Shows the U-shape: heavy at open, light midday, heavy at close

SELECT ticker,
    toHour(timestamp) AS hour,
    formatReadableQuantity(avg(volume)) AS avg_vol,
    bar(avg(volume), 0, 5000000, 40) AS profile
FROM ohlcv
WHERE ticker IN ('SPY', 'AAPL', 'NVDA')
    AND toHour(timestamp) BETWEEN 9 AND 16
GROUP BY ticker, hour
ORDER BY ticker, hour;
