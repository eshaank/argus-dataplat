-- Dividend Yield Ranking — current yield from latest dividend + price

WITH latest_div AS (
    SELECT ticker,
        argMax(cash_amount, ex_dividend_date) AS last_amount,
        argMax(frequency, ex_dividend_date) AS freq,
        max(ex_dividend_date) AS last_ex_date
    FROM dividends
    GROUP BY ticker
),
prices AS (
    SELECT ticker, close FROM ohlcv_daily_mv
    WHERE day = (SELECT max(day) FROM ohlcv_daily_mv)
)
SELECT
    d.ticker,
    round(p.close, 2) AS price,
    round(d.last_amount, 4) AS last_div,
    d.freq AS frequency,
    d.last_ex_date,
    round(d.last_amount * d.freq / p.close * 100, 2) AS annual_yield_pct
FROM latest_div d
JOIN prices p ON d.ticker = p.ticker
WHERE d.freq > 0 AND p.close > 0
ORDER BY annual_yield_pct DESC
LIMIT 20;
