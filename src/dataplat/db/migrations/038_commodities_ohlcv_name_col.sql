-- 038_commodities_ohlcv_name_col: Add name column, truncate for re-insert with yf tickers
-- ticker will now be the Yahoo Finance symbol (e.g. "GC=F")
-- name will be the human-readable commodity name (e.g. "Gold")

ALTER TABLE commodities_ohlcv ADD COLUMN IF NOT EXISTS name LowCardinality(String) DEFAULT '' AFTER ticker;

TRUNCATE TABLE commodities_ohlcv;
