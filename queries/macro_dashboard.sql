-- Macro Dashboard — monthly snapshot of all economic indicators + market
-- One row per month, everything in one view

SELECT
    l.date AS month,
    l.unemployment_rate AS unemp,
    round(i.cpi, 1) AS cpi,
    round(ie.model_1_year, 1) AS infl_exp_1y,
    round(t.yield_10_year, 2) AS y10,
    round(t.yield_10_year - t.yield_1_year, 2) AS curve_1s10s,
    round(spy.close, 0) AS spy_avg,
    round(tlt.close, 0) AS tlt_avg,
    round(gld.close, 0) AS gld_avg
FROM labor_market l
LEFT JOIN inflation i ON l.date = i.date
LEFT JOIN inflation_expectations ie ON l.date = ie.date
LEFT JOIN (
    SELECT toStartOfMonth(date) AS month, avg(yield_10_year) AS yield_10_year, avg(yield_1_year) AS yield_1_year
    FROM treasury_yields GROUP BY month
) t ON l.date = t.month
LEFT JOIN (SELECT toStartOfMonth(day) AS month, avg(close) AS close FROM ohlcv_daily_mv WHERE ticker = 'SPY' GROUP BY month) spy ON l.date = spy.month
LEFT JOIN (SELECT toStartOfMonth(day) AS month, avg(close) AS close FROM ohlcv_daily_mv WHERE ticker = 'TLT' GROUP BY month) tlt ON l.date = tlt.month
LEFT JOIN (SELECT toStartOfMonth(day) AS month, avg(close) AS close FROM ohlcv_daily_mv WHERE ticker = 'GLD' GROUP BY month) gld ON l.date = gld.month
WHERE l.date >= '2022-01-01' AND l.unemployment_rate IS NOT NULL
ORDER BY l.date;
