-- Cross-Asset Correlation Matrix — stocks vs bonds vs gold vs dollar
-- Shows what's moving together (risk-on) vs diverging (rotation)

WITH returns AS (
    SELECT ticker, day,
        log(close) - log(lagInFrame(close) OVER (PARTITION BY ticker ORDER BY day)) AS ret
    FROM ohlcv_daily_mv
    WHERE day >= today() - 90
    AND ticker IN ('SPY', 'QQQ', 'TLT', 'GLD', 'UUP', 'HYG', 'IWM', 'VIXY')
)
SELECT
    a.ticker AS t1,
    b.ticker AS t2,
    round(corr(a.ret, b.ret), 3) AS correlation
FROM returns a
JOIN returns b ON a.day = b.day
WHERE a.ticker < b.ticker
GROUP BY t1, t2
ORDER BY t1, t2;
