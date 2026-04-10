-- 041_update_frequency_weekly_monthly: Add update_frequency to EIA petroleum tables

ALTER TABLE eia_petroleum_weekly ADD COLUMN IF NOT EXISTS update_frequency LowCardinality(String) DEFAULT 'weekly' AFTER source;

ALTER TABLE eia_petroleum_monthly ADD COLUMN IF NOT EXISTS update_frequency LowCardinality(String) DEFAULT 'monthly' AFTER source;
