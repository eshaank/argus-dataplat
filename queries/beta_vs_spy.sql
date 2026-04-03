-- Beta vs SPY — how much does each ticker move relative to the market?
-- Beta > 1 = more volatile than market, Beta < 1 = less volatile

WITH returns AS (
    SELECT ticker, day,
        log(close) - log(lagInFrame(close) OVER (PARTITION BY ticker ORDER BY day)) AS ret
    FROM ohlcv_daily_mv
    WHERE day >= today() - 252  -- 1 year
),
spy AS (
    SELECT day, ret AS spy_ret FROM returns WHERE ticker = 'SPY'
)
SELECT
    r.ticker,
    round(covarPop(r.ret, s.spy_ret) / varPop(s.spy_ret), 3) AS beta,
    round(corr(r.ret, s.spy_ret), 3) AS correlation,
    round(stddevPop(r.ret) * sqrt(252) * 100, 1) AS annual_vol_pct,
    count() AS trading_days
FROM returns r
JOIN spy s ON r.day = s.day
WHERE r.ticker != 'SPY'
GROUP BY r.ticker
HAVING trading_days > 100
ORDER BY beta DESC;
