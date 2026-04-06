-- Market breadth: advancers vs decliners from latest trading day
CREATE VIEW IF NOT EXISTS v_market_breadth AS
WITH latest AS (
    SELECT ticker, close, day,
        row_number() OVER (PARTITION BY ticker ORDER BY day DESC) as rn
    FROM ohlcv_daily_mv
    WHERE day >= today() - 7
),
prices AS (
    SELECT
        l1.ticker,
        l1.close as latest_close,
        l2.close as prev_close,
        round((l1.close - l2.close) / l2.close * 100, 2) as change_pct
    FROM latest l1
    JOIN latest l2 ON l1.ticker = l2.ticker AND l1.rn = 1 AND l2.rn = 2
    WHERE l2.close > 0
)
SELECT
    countIf(change_pct > 0) as advancers,
    countIf(change_pct < 0) as decliners,
    countIf(change_pct = 0) as unchanged,
    count() as total,
    round(avg(change_pct), 2) as avg_change,
    round(median(change_pct), 2) as median_change
FROM prices;

-- 52-week highs
CREATE VIEW IF NOT EXISTS v_52w_highs AS
WITH latest AS (
    SELECT ticker,
           argMax(close, day) as close,
           argMax(toFloat64(total_volume), day) as volume,
           max(day) as last_day
    FROM ohlcv_daily_mv
    WHERE day >= today() - 5
    GROUP BY ticker
),
prev AS (
    SELECT ticker, argMax(close, day) as prev_close
    FROM ohlcv_daily_mv
    WHERE day >= today() - 10 AND day < (SELECT max(day) FROM ohlcv_daily_mv WHERE day >= today() - 5)
    GROUP BY ticker
),
yr AS (
    SELECT ticker, max(close) as max_close
    FROM ohlcv_daily_mv
    WHERE day >= today() - 252 AND day < today() - 1
    GROUP BY ticker
)
SELECT l.ticker,
       coalesce(u.name, '') as name,
       l.close,
       round((l.close - p.prev_close) / p.prev_close * 100, 2) as change_pct,
       l.volume
FROM latest l
JOIN yr y ON l.ticker = y.ticker
LEFT JOIN prev p ON l.ticker = p.ticker
LEFT JOIN (SELECT ticker, name FROM universe FINAL) u ON l.ticker = u.ticker
WHERE l.close >= y.max_close AND u.name != '';

-- 52-week lows
CREATE VIEW IF NOT EXISTS v_52w_lows AS
WITH latest AS (
    SELECT ticker,
           argMax(close, day) as close,
           argMax(toFloat64(total_volume), day) as volume,
           max(day) as last_day
    FROM ohlcv_daily_mv
    WHERE day >= today() - 5
    GROUP BY ticker
),
prev AS (
    SELECT ticker, argMax(close, day) as prev_close
    FROM ohlcv_daily_mv
    WHERE day >= today() - 10 AND day < (SELECT max(day) FROM ohlcv_daily_mv WHERE day >= today() - 5)
    GROUP BY ticker
),
yr AS (
    SELECT ticker, min(close) as min_close
    FROM ohlcv_daily_mv
    WHERE day >= today() - 252 AND day < today() - 1
    GROUP BY ticker
)
SELECT l.ticker,
       coalesce(u.name, '') as name,
       l.close,
       round((l.close - p.prev_close) / p.prev_close * 100, 2) as change_pct,
       l.volume
FROM latest l
JOIN yr y ON l.ticker = y.ticker
LEFT JOIN prev p ON l.ticker = p.ticker
LEFT JOIN (SELECT ticker, name FROM universe FINAL) u ON l.ticker = u.ticker
WHERE l.close <= y.min_close AND u.name != '';

-- 52-week high/low counts (aggregate)
CREATE VIEW IF NOT EXISTS v_52w_hilo_counts AS
WITH latest AS (
    SELECT ticker, close, day FROM ohlcv_daily_mv
    WHERE day = (SELECT max(day) FROM ohlcv_daily_mv WHERE day >= today() - 5)
),
yr AS (
    SELECT ticker, max(close) as hi52, min(close) as lo52
    FROM ohlcv_daily_mv
    WHERE day >= today() - 252 AND day < today() - 1
    GROUP BY ticker
)
SELECT
    countIf(l.close >= y.hi52) as new_highs,
    countIf(l.close <= y.lo52) as new_lows,
    count() as total
FROM latest l
JOIN yr y ON l.ticker = y.ticker;

-- Dividend changes (YoY)
DROP VIEW IF EXISTS v_dividend_changes;
CREATE VIEW IF NOT EXISTS v_dividend_changes AS
WITH ranked AS (
    SELECT ticker, cash_amount, ex_dividend_date,
           row_number() OVER (PARTITION BY ticker ORDER BY ex_dividend_date DESC) as rn
    FROM dividends
    WHERE ex_dividend_date >= today() - 365
)
SELECT r1.ticker AS ticker,
       coalesce(u.name, '') as name,
       r2.cash_amount as prev_amount,
       r1.cash_amount as latest_amount,
       round((r1.cash_amount - r2.cash_amount) / r2.cash_amount * 100, 1) as change_pct,
       r1.ex_dividend_date as ex_date
FROM ranked r1
JOIN ranked r2 ON r1.ticker = r2.ticker AND r1.rn = 1 AND r2.rn = 2
LEFT JOIN (SELECT ticker, name FROM universe FINAL) u ON r1.ticker = u.ticker
WHERE r2.cash_amount > 0 AND r1.cash_amount != r2.cash_amount;

-- Notable insider buys (officers/directors, >$50K, last 14 days)
CREATE VIEW IF NOT EXISTS v_notable_insider_buys AS
SELECT ticker,
       reporter_name as name,
       reporter_title as title,
       shares,
       price,
       value,
       filed_date
FROM insider_trades
WHERE filed_date >= today() - 14
  AND transaction_code = 'P'
  AND NOT is_derivative
  AND value > 50000;

-- Upcoming ex-dividend dates (next 7 days)
CREATE VIEW IF NOT EXISTS v_upcoming_dividends AS
SELECT d.ticker,
       coalesce(u.name, '') as name,
       d.cash_amount,
       d.ex_dividend_date as ex_date
FROM dividends d
LEFT JOIN (SELECT ticker, name FROM universe FINAL) u ON d.ticker = u.ticker
WHERE d.ex_dividend_date >= today()
  AND d.ex_dividend_date <= today() + 7;
