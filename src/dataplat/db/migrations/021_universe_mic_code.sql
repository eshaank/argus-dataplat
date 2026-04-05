-- 021_universe_mic_code: Store raw MIC code separately from human-readable exchange name
-- exchange column becomes human-readable (NYSE, NASDAQ, etc.)
-- mic_code column stores the ISO 10383 code (XNYS, XNAS, etc.)

ALTER TABLE universe ADD COLUMN IF NOT EXISTS mic_code LowCardinality(Nullable(String));

-- Backfill mic_code from existing exchange values (which are currently MIC codes)
ALTER TABLE universe UPDATE mic_code = exchange WHERE mic_code IS NULL OR mic_code = '';

-- Translate existing MIC codes in exchange to human-readable names
ALTER TABLE universe UPDATE exchange = 'NYSE'           WHERE exchange = 'XNYS';
ALTER TABLE universe UPDATE exchange = 'NASDAQ'         WHERE exchange = 'XNAS';
ALTER TABLE universe UPDATE exchange = 'NYSE American'  WHERE exchange = 'XASE';
ALTER TABLE universe UPDATE exchange = 'NYSE Arca'      WHERE exchange = 'ARCX';
ALTER TABLE universe UPDATE exchange = 'Cboe BZX'       WHERE exchange = 'BATS';
ALTER TABLE universe UPDATE exchange = 'Cboe EDGX'      WHERE exchange = 'EDGX';
ALTER TABLE universe UPDATE exchange = 'IEX'            WHERE exchange = 'IEXG';
ALTER TABLE universe UPDATE exchange = 'NASDAQ PSX'     WHERE exchange = 'XPHL';
ALTER TABLE universe UPDATE exchange = 'NASDAQ BX'      WHERE exchange = 'XBOS';
ALTER TABLE universe UPDATE exchange = 'Chicago SE'     WHERE exchange = 'XCHI';
ALTER TABLE universe UPDATE exchange = 'OTC Markets'    WHERE exchange IN ('OTCM', 'OOTC');
