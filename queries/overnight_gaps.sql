-- Biggest Overnight Gaps — price gaps between previous close and next open
-- Large gaps often signal news events or earnings

WITH gaps AS (
    SELECT ticker, day, open, close,
        lagInFrame(close) OVER (PARTITION BY ticker ORDER BY day) AS prev_close,
        (open - lagInFrame(close) OVER (PARTITION BY ticker ORDER BY day))
            / lagInFrame(close) OVER (PARTITION BY ticker ORDER BY day) * 100 AS gap_pct
    FROM ohlcv_daily_mv
    WHERE day >= today() - 30
)
SELECT ticker, day,
    round(prev_close, 2) AS prev_close,
    round(open, 2) AS open,
    round(gap_pct, 2) AS gap_pct
FROM gaps
WHERE abs(gap_pct) > 2
ORDER BY abs(gap_pct) DESC
LIMIT 30;
