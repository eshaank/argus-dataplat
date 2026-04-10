-- 033_drop_macro_daily_commodity_cols: Remove wti_crude and gold_price from macro_daily
-- These now live in commodity_prices (migration 030)

ALTER TABLE macro_daily DROP COLUMN IF EXISTS wti_crude;
ALTER TABLE macro_daily DROP COLUMN IF EXISTS gold_price;
