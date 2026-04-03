-- Equity Risk Premium — earnings yield vs 10yr treasury
-- Higher = stocks are cheap relative to bonds

WITH latest AS (
    SELECT ticker, max(period_end) AS max_period
    FROM financials WHERE timeframe = 'quarterly' GROUP BY ticker
),
prices AS (
    SELECT ticker, close FROM ohlcv_daily_mv
    WHERE day = (SELECT max(day) FROM ohlcv_daily_mv)
)
SELECT
    f.ticker,
    round(p.close, 2) AS price,
    round(f.diluted_eps * 4, 2) AS annual_eps,
    round(f.diluted_eps * 4 / p.close * 100, 2) AS earnings_yield,
    t.yield_10_year AS treasury_10y,
    round(f.diluted_eps * 4 / p.close * 100 - t.yield_10_year, 2) AS equity_risk_premium
FROM financials f
JOIN latest l ON f.ticker = l.ticker AND f.period_end = l.max_period
JOIN prices p ON f.ticker = p.ticker
CROSS JOIN (SELECT yield_10_year FROM treasury_yields WHERE yield_10_year IS NOT NULL ORDER BY date DESC LIMIT 1) t
WHERE f.timeframe = 'quarterly' AND f.diluted_eps > 0
ORDER BY equity_risk_premium DESC
LIMIT 30;
