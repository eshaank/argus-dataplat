-- Fundamentals Screener — value + quality metrics for all tickers
-- Combines latest financials with latest price

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
    -- Valuation
    round(p.close / nullIf(f.diluted_eps * 4, 0), 1) AS pe_ratio,
    round(p.close * f.diluted_shares / nullIf(f.revenue * 4, 0), 2) AS price_to_sales,
    -- Profitability
    round(f.gross_profit / nullIf(f.revenue, 0) * 100, 1) AS gross_margin,
    round(f.operating_income / nullIf(f.revenue, 0) * 100, 1) AS op_margin,
    round(f.net_income / nullIf(f.revenue, 0) * 100, 1) AS net_margin,
    -- Leverage
    round(f.total_liabilities / nullIf(f.total_equity, 0), 2) AS debt_to_equity,
    -- Cash flow
    formatReadableQuantity(f.operating_cash_flow + f.investing_cash_flow) AS fcf,
    -- R&D intensity
    round(f.research_and_dev / nullIf(f.revenue, 0) * 100, 1) AS rd_pct
FROM financials f
JOIN latest l ON f.ticker = l.ticker AND f.period_end = l.max_period
JOIN prices p ON f.ticker = p.ticker
WHERE f.timeframe = 'quarterly' AND f.revenue > 0
ORDER BY pe_ratio ASC NULLS LAST
LIMIT 30;
