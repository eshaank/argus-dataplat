-- Sector Rotation — relative performance of sector ETFs vs SPY
-- Positive = outperforming the market, negative = underperforming

   WITH
   returns AS (
       SELECT ticker, day,
           log(close) - log(lagInFrame(close) OVER (PARTITION BY ticker ORDER BY day)) AS ret
       FROM ohlcv_daily_mv
       WHERE ticker IN ('SPY', 'XLK', 'XLF', 'XLE', 'HYG', 'TLT', 'GLD', 'IWM')
       AND day >= today() - 60
   ),
   spy AS (
       SELECT day, ret AS spy_ret FROM returns WHERE ticker = 'SPY'
   )
   SELECT
       r.ticker,
       round(sum(r.ret) * 100, 2) AS total_return_pct,
       round(sum(s.spy_ret) * 100, 2) AS spy_return_pct,
       round((sum(r.ret) - sum(s.spy_ret)) * 100, 2) AS relative_pct,
       if(sum(r.ret) > sum(s.spy_ret), '🟢 OUTPERFORM', '🔴 UNDERPERFORM') AS vs_spy
   FROM returns r
   JOIN spy s ON r.day = s.day
   WHERE r.ticker != 'SPY'
       AND isFinite(r.ret) AND isFinite(s.spy_ret)
   GROUP BY r.ticker
   ORDER BY relative_pct DESC;