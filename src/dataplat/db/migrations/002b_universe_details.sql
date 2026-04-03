-- 002b_universe_details: Enrich universe with ticker-details fields
-- Source: Polygon /v3/reference/tickers/{ticker}

ALTER TABLE universe ADD COLUMN IF NOT EXISTS description     Nullable(String);
ALTER TABLE universe ADD COLUMN IF NOT EXISTS homepage_url    Nullable(String);
ALTER TABLE universe ADD COLUMN IF NOT EXISTS total_employees Nullable(UInt32);
ALTER TABLE universe ADD COLUMN IF NOT EXISTS list_date       Nullable(Date);
ALTER TABLE universe ADD COLUMN IF NOT EXISTS cik             Nullable(String);
ALTER TABLE universe ADD COLUMN IF NOT EXISTS sic_description Nullable(String);
ALTER TABLE universe ADD COLUMN IF NOT EXISTS address_city    Nullable(String);
ALTER TABLE universe ADD COLUMN IF NOT EXISTS address_state   Nullable(String);
ALTER TABLE universe ADD COLUMN IF NOT EXISTS composite_figi  Nullable(String)
