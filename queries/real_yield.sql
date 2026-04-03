-- Real Yield — nominal treasury minus inflation expectations
-- Positive = savers earn real return. Negative = financial repression.

SELECT t.date,
    round(t.yield_10_year, 2) AS nominal_10y,
    round(ie.market_10_year, 2) AS breakeven_10y,
    round(t.yield_10_year - ie.market_10_year, 2) AS real_yield_10y,
    bar(t.yield_10_year - ie.market_10_year, -2, 3, 30) AS visual
FROM treasury_yields t
JOIN inflation_expectations ie ON toStartOfMonth(t.date) = ie.date
WHERE t.date >= '2020-01-01'
    AND t.yield_10_year IS NOT NULL
    AND ie.market_10_year IS NOT NULL
ORDER BY t.date;
