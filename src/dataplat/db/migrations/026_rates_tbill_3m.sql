-- 026_rates_tbill_3m: Add 3-month T-bill rate to rates table
-- Source: FRED TB3MS
-- Unlocks: TED spread (CP - Tbill), real fed funds, short-end yield curve anchor

ALTER TABLE rates ADD COLUMN IF NOT EXISTS tbill_3m Nullable(Float64);
