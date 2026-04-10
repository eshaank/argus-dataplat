-- 040_update_frequency_col: Add update_frequency to commodity tables
-- Indicates how often the data source publishes new values (daily, weekly, monthly)

ALTER TABLE commodity_prices ADD COLUMN IF NOT EXISTS update_frequency LowCardinality(String) DEFAULT 'daily' AFTER source;

ALTER TABLE commodities_ohlcv ADD COLUMN IF NOT EXISTS update_frequency LowCardinality(String) DEFAULT 'daily' AFTER source;
