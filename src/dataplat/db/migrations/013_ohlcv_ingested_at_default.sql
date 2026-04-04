-- 013_ohlcv_ingested_at_default: Add DEFAULT now() to ingested_at
-- Fixes rows inserting with epoch 1970 when ingested_at is not explicitly set.

ALTER TABLE ohlcv MODIFY COLUMN ingested_at DateTime DEFAULT now() CODEC(Delta, ZSTD(1))
