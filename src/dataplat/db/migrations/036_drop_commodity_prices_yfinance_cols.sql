-- 036_drop_commodity_prices_yfinance_cols: Remove yfinance columns from commodity_prices
-- These now live in commodities_ohlcv (migration 035) with full OHLCV data

ALTER TABLE commodity_prices DROP COLUMN IF EXISTS gold;
ALTER TABLE commodity_prices DROP COLUMN IF EXISTS silver;
ALTER TABLE commodity_prices DROP COLUMN IF EXISTS copper;
ALTER TABLE commodity_prices DROP COLUMN IF EXISTS aluminum;
ALTER TABLE commodity_prices DROP COLUMN IF EXISTS wheat;
ALTER TABLE commodity_prices DROP COLUMN IF EXISTS corn;
ALTER TABLE commodity_prices DROP COLUMN IF EXISTS cotton;
ALTER TABLE commodity_prices DROP COLUMN IF EXISTS sugar;
ALTER TABLE commodity_prices DROP COLUMN IF EXISTS coffee;
